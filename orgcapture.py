import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
import fnmatch
import OrgExtended.orgparse.loader as loader
import OrgExtended.orgparse.node as node
from   OrgExtended.orgparse.sublimenode import * 
import OrgExtended.orgutil.util as util
import OrgExtended.orgutil.navigation as nav
import OrgExtended.orgutil.template as templateEngine
import OrgExtended.orgparse.date as orgdate
import OrgExtended.orgextension as ext
import OrgExtended.orgclocking as clk
import logging
import sys
import traceback 
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
import OrgExtended.orgproperties as props
import OrgExtended.pymitter as evt
import OrgExtended.orgdaypage as daypage
import time

log = logging.getLogger(__name__)
captureBufferName = "*capture*"
lastHeader        = None

def GetViewById(id):
    win = sublime.active_window()
    for v in win.views():
        if(v.id() == id):
            return v
    return None

def GetDict():
    tempDict = {
        'refile' : sets.Get('refile',''),
        'daypage' : daypage.dayPageGetName(daypage.dayPageGetToday()),
    } 
    return tempDict

def GetCaptureFile(view, template, target):
    temp = templateEngine.TemplateFormatter(sets.Get)
    filename = templateEngine.ExpandTemplate(view, target[1], GetDict(), sets.Get)[0]
    return filename

def GetCaptureFileAndParam(view, template, target):
    temp = templateEngine.TemplateFormatter(sets.Get)
    tempDict = GetDict()
    filename = templateEngine.ExpandTemplate(view, target[1], tempDict, sets.Get)[0]
    headline = None
    if(len(target) > 2):
        headline = templateEngine.ExpandTemplate(view, target[2], tempDict, sets.Get)[0]
    return (filename, headline)

def FindNodeByPath(n, target, idx):
    if(idx >= len(target)):
        return n
    for c in n.children:
        if(c.heading == target[idx]):
            return FindNodeByPath(c, target, idx+1)
    return None

def GetCapturePath(view, template):
    target    = ['file', '{refile}']
    if 'target' in template:
        target    = template['target']
    filename = None
    file = None
    at = None
    toinsert = ""
    if('file' in target[0]):
        filename = GetCaptureFile(view, template, target)
    if('file+headline' in target[0]):
        filename, headline = GetCaptureFileAndParam(view, template, target)
        file = db.Get().LoadNew(filename)
        if(file and headline):
            at = file.FindOrCreateNode(headline)
            if(at):
                at = at.local_end_row
    elif('file+regexp' in target[0]):
        filename, reg = GetCaptureFileAndParam(view, template, target)
        file = db.Get().LoadNew(filename)
        if(file and reg):
            r = re.compile(reg)
            row = 0
            for n in file.org:
                for line in n._lines:
                    m = r.search(line)
                    if(m):
                        at = row
                        break
                    row += 1
    elif('file+olp+datetree' in target[0]):
        filename, reg = GetCaptureFileAndParam(view, template, target)
        file = db.Get().FindInfo(filename)
        n = FindNodeByPath(file.org,target,2)
        if(not n):
            n = file.org
        # Now we assume this is a date tree. Default is per day.
        t = datetime.datetime.now() 
        yearformat  = t.strftime(GetProp(template, "year-format",  "%Y"))
        monthformat = t.strftime(GetProp(template, "month-format", "%Y-%m %B"))
        dayformat   = t.strftime(GetProp(template, "day-format",   "%Y-%m-%d %A"))
        nyear  = None
        nmonth = None
        nday   = None
        prefix   = ""
        if(n.level > 0):
            prefix = "*" * n.level
        for c in n.children:
            if(c.heading == yearformat):
                nyear = c
                break
        if(nyear == None):
            toinsert += "{prefix}* {yearformat}\n".format(prefix=prefix,yearformat=yearformat)
        else:
            n = nyear
            for c in nyear.children:
                if(c.heading == monthformat):
                    nmonth = c
                    break
        if(nmonth == None):
            toinsert += "{prefix}** {monthformat}\n".format(prefix=prefix,monthformat=monthformat)
        else:
            n = nmonth
            for c in nmonth.children:
                if(c.heading == dayformat):
                    nday = c
                    break
        if(nday == None):
            toinsert += "{prefix}*** {dayformat}\n".format(prefix=prefix,dayformat=dayformat)
        else:
            n = nday
        if(n and toinsert == ""):
            at = n.local_end_row
        else:
            at = n.end_row
    elif('file+olp' in target[0]):
        filename, reg = GetCaptureFileAndParam(view, template, target)
        file = db.Get().LoadNew(filename)
        n = FindNodeByPath(file.org,target,2)
        if(n):
            at = n.local_end_row

    elif('id' == target[0]):
        file, at = db.Get().FindByCustomId(target[1])
        if(file == None):
            log.error("Could not find id: " + target[1])
            return
        filename = file.filename
    elif('clock' == target[0]):
        if(not clk.ClockManager.ClockRunning()):
            log.debug("ERROR: clock is not running!")
            raise "ERROR: clock is not running"
        filename = clk.ClockManager.GetActiveClockFile()
        at       = clk.ClockManager.GetActiveClockAt()
    # Try to create my capture file if I can
    try:
        if(not os.path.isfile(str(filename))):
            with open(filename,"w",encoding=sets.Get("captureWriteFormat","utf-8")) as fp:
                fp.write("#+TAGS: refile\n")
    except:
        log.error("@@@@@@@@@@@@\nFailed to create capture file: " + str(filename))
    # Now make sure that file is loaded in the DB
    # it might not be in my org path
    if(file == None):
        file = db.Get().LoadNew(filename)
    else:
        file = db.Get().FindInfo(filename)
    if(not at and file):
        at = file.org.start_row
    return (target, filename, file, at, toinsert)


# This is a bit hokey. We track the last header so
# if you change the header we can still find it
# in your target file. Every time you swap your
# mouse away from the capture window we auto save
# the capture to your target location.
# TODO: Add more target locations than your refile file.
def onDeactivated(view):
    global captureBufferName
    global lastHeader
    if(view.name() == captureBufferName):
        tempIndex = view.settings().get('cap_index')
        templates = sets.Get("captureTemplates",[])
        template  = templates[tempIndex]
        #outpath, outfile = GetCaptureOutput()
        #print('template index was: ' + str(tempIndex))
        target, capturePath, captureFile, at, toinsert = GetCapturePath(GetViewById(view.settings().get('cap_view')), template)
        #refilePath = sets.Get("refile","UNKNOWN")
        #refile = load(refilePath)
        captureFileRoot = None
        if(captureFile != None):
            captureFileRoot = captureFile.org

        bufferContentsToInsert = view.substr(sublime.Region(0, view.size()))
        if not bufferContentsToInsert.endswith('\n'):
            bufferContentsToInsert += "\n"
        didInsert = False
        # Get a capture node
        captureNode = loader.loads(bufferContentsToInsert)
        # if we moused out of the window we might be replacing
        # ourselves again.
        if(lastHeader == None):
            lastHeader = str(captureNode[1].heading)
        # We may haved moved around in the capture file
        # so find the old heading.
        for heading in captureFileRoot:
            if(type(heading) is node.OrgRootNode):
                continue
            if str(heading.heading) == lastHeader:
                #log.debug("REPLACING: " + str(heading.heading))
                heading.replace_node(captureNode[1])
                didInsert = True
                continue
        if(not didInsert):
            insertAt = captureFileRoot
            inserted = captureNode[1]
            if(at != None and at > 0):
                # This does not work? its a node not a file
                insertAt = captureFile.At(at)
            insertAt.insert_child(inserted)
        f = open(capturePath,"w+",encoding=sets.Get("captureWriteFormat","utf-8"))
        # reauthor the ENTIRE file.
        # This can get expensive!
        for item in captureFileRoot:
            f.write(str(item))
        f.close()
        lastHeader = str(captureNode[1].heading)
        log.debug("***************>>>>> [" + view.name() + "] is no more")

# Respond to panel events. If the panel is hidden we stop
# tracking the last header.
def onPostWindowCommand(window, cmd, args):
    if cmd == "hide_panel":
        global lastHeader
        # This stops the capture refiling
        # From finding an entry across capture
        # window openings
        lastHeader = None


class OrgCopyCommand(sublime_plugin.TextCommand):
    def on_done_st4(self,index,modifers):
        self.on_done(index)
    def on_done(self, index):
        file, fileIndex = db.Get().FindFileInfoByAllHeadingsIndex(index)
        node = db.Get().AtInView(self.view)
        if(fileIndex != None):
            #print(str(file.key))
            file.org[fileIndex].insert_child(node)
            file.Save()
        else:
            log.error("Failed to copy, fileindex not found")

    def run(self, edit):
        self.headings = db.Get().AllHeadingsWContext(self.view)
        if(int(sublime.version()) <= 4096):
            self.view.window().show_quick_panel(self.headings, self.on_done, -1, -1)
        else:
            self.view.window().show_quick_panel(self.headings, self.on_done_st4, -1, -1)

class OrgOpenRefileCommand(sublime_plugin.TextCommand):
    def run(self,edit):
        refile = sets.Get("refile",None)
        log.debug("REFILE: ", refile)
        if(refile):
           self.view.window().open_file(refile) 
        else:
            log.error("Could not find refile file, have you set it in your config?")

# Archiving will push the current item to an archive file (with some tags etc)
class OrgArchiveSubtreeCommand(sublime_plugin.TextCommand):

    def close_tempView(self):
        self.tempView.run_command("close")

    def finish_archive_on_loaded(self):
        while(self.tempView.is_loading()):
            sublime.set_timeout_async(lambda: self.finish_archive_on_loaded(), 100)
        node = self.file.At(self.result.start_row)
        #:ARCHIVE_TIME: 2017-11-30 Thu 18:15
        #:ARCHIVE_FILE: ~/notes/inxile/worklog.org
        #:ARCHIVE_OLPATH: Daily
        #:ARCHIVE_CATEGORY: InXile
        #:ARCHIVE_ITAGS: InXile
        props.UpdateProperty(self.tempView,node, "ARCHIVE_TIME", datetime.datetime.now().strftime("%Y-%m-%d %a %H:%M"))
        props.UpdateProperty(self.tempView,node, "ARCHIVE_FILE", self.view.file_name())
        self.tempView.run_command("save")
        sublime.set_timeout_async(lambda: self.close_tempView(), 1000)
        # Now remove the old node
        self.sourceNode.remove_node()
        fromFile = db.Get().FindInfo(self.view)
        fromFile.Save()
        fromFile.Reload()

    def run(self,edit):
        globalArchive = sets.Get("archive","%s_archive::")
        node          = db.Get().AtInView(self.view)
        archive       = node.archive(globalArchive)
        if(archive == None or archive.strip() == ""):
            node = db.Get().AtInView(self.view)
            node.add_tag("ARCHIVE")
            file = db.Get().FindInfo(self.view)
            file.Save()
            print(str(node))
            return
        # Set the root to empty if not provided
        if('::' not in archive):
            archive = archive + "::"
        (fileTemplate, headingTarget) = archive.split('::')
        if('%' in fileTemplate):
            filename      = fileTemplate % (self.view.file_name()) 
        else:
            filename = fileTemplate
        log.debug("ARCHIVE FILE:    " + filename)
        log.debug("ARCHIVE HEADING: " + headingTarget)

        # Ensure the file actually exists.
        if(not os.path.dirname(filename).strip() == ''):
            os.makedirs(os.path.dirname(filename), exist_ok=True)
        # Okay the file is probably a local path
        # Get the full path from our file.
        else:
            localDirname = os.path.dirname(self.view.file_name())
            if('/' not in filename and '\\' not in filename):
                filename = os.path.join(localDirname, filename)
        with open(filename, "a",encoding=sets.Get("captureWriteFormat","utf-8")) as f:
            log.debug("  Archive file created...")
        # Okay now open the file.
        file       = db.Get().FindInfo(filename)
        sourceNode = db.Get().AtInView(self.view)
        if(sourceNode != None):
            log.debug("Find or create: " + headingTarget)
            targetNode = file.FindOrCreateNode(headingTarget)
            if(targetNode == None):
                targetNode = file.Root()
                self.result = targetNode.insert_child(sourceNode)
                self.result.update_property("ARCHIVE_TIME", datetime.datetime.now().strftime("%Y-%m-%d %a %H:%M"))
                self.result.update_property("ARCHIVE_FILE", self.view.file_name())
                for n in file.org[1:]:
                    print(n.full_heading)
            else:
                log.debug("Inserting heading at: " + targetNode.heading)
                log.debug("Inserting: " + sourceNode.heading)
                self.result = targetNode.insert_child(sourceNode)

                self.result.update_property("ARCHIVE_TIME", datetime.datetime.now().strftime("%Y-%m-%d %a %H:%M"))
                self.result.update_property("ARCHIVE_FILE", self.view.file_name())
                for n in file.org[1:]:
                    print(n.full_heading)
            log.debug("Saving the source file")
            file.Save()
            file.Reload()


            sourceNode.remove_node()
            fromFile = db.Get().FindInfo(self.view)
            fromFile.Save()
            fromFile.Reload()
            #self.tempView = self.view.window().open_file(file.filename, sublime.ENCODED_POSITION)
            #self.file = file
            #self.sourceNode = sourceNode
            #sublime.set_timeout_async(lambda: self.finish_archive_on_loaded(), 1000)
        else:
            log.error("Failed to archive subtree! Could not find source Node")  


def RefileCurNode(view, file, nodeIndex):
    (curRow,curCol) = view.curRowCol()
    node = db.Get().At(view, curRow)

    if(node == None):
        log.error("COULD NOT REFILE: Node at line " + str(curRow) + " not found")
        return
    if(nodeIndex == None):
        log.error("Could not refile node index is out of bounds")
        return 
    log.debug("Inserting child into: " + str(nodeIndex) + " vs " + str(len(file.org)) + " in file: " + file.filename)

    fromFile = db.Get().FindInfo(view)
    file.org[nodeIndex].insert_child(node)
    node.remove_node()
    # Have to save down here in case
    # file and fromFile are the same!
    file.Save()
    file.Reload()
    fromFile.Save()
    fromFile.Reload()

# This refile gives you a list of all headings to make it quicker to jump to
# "That heading" This one is bound to R for really quick refiling.
class OrgRefileCommand(sublime_plugin.TextCommand):
    def on_done_st4(self,index,modifiers):
        self.on_done(index)
    def on_done(self, index):
        if(index < 0):
            return
        file, fileIndex = db.Get().FindFileInfoByAllHeadingsIndex(index)
        RefileCurNode(self.view, file, fileIndex)

    def run(self, edit):
        self.headings = db.Get().AllHeadingsWContext(self.view)
        if(int(sublime.version()) <= 4096):
            self.view.window().show_quick_panel(self.headings, self.on_done, -1, -1)
        else:
            self.view.window().show_quick_panel(self.headings, self.on_done_st4, -1, -1)

# This refile, files to the end of the file.
class OrgRefileToFileCommand(sublime_plugin.TextCommand):
    def on_done_st4(self,index,modifiers):
        self.on_done(index)
    def on_done(self, index):
        if(index < 0):
            return
        file = db.Get().FindFileByIndex(index)
        fileIndex = 0
        RefileCurNode(self.view, file, fileIndex)

    def run(self, edit):
        self.headings = db.Get().AllFiles(self.view)
        if(int(sublime.version()) <= 4096):
            self.view.window().show_quick_panel(self.headings, self.on_done, -1, -1)
        else:
            self.view.window().show_quick_panel(self.headings, self.on_done_st4, -1, -1)

# This refile version takes a filename prompt first
# then it shows the headings in the file.
class OrgRefileToFileAndHeadlineCommand(sublime_plugin.TextCommand):
    def on_done_st4(self,index,modifiers):
        self.on_done(index)
    def on_done(self, index):
        if(index < 0):
            return
        self.file = db.Get().FindFileByIndex(index)
        self.headings = db.Get().AllHeadingsForFile(self.file)
        if(int(sublime.version()) <= 4096):
            self.view.window().show_quick_panel(self.headings, self.on_done_v2, -1, -1)
        else:
            self.view.window().show_quick_panel(self.headings, self.on_done_st4_v2, -1, -1)

    def on_done_st4_v2(self,index,modifiers):
        self.on_done_v2(index)
    def on_done_v2(self, index):
        if(index < 0):
            return
        RefileCurNode(self.view, self.file, index+1)
        pass

    def run(self, edit):
        headings = db.Get().AllFiles(self.view)
        if(int(sublime.version()) <= 4096):
            self.view.window().show_quick_panel(headings, self.on_done, -1, -1)
        else:
            self.view.window().show_quick_panel(headings, self.on_done_st4, -1, -1)

class OrgCaptureBaseCommand(sublime_plugin.TextCommand):
    def on_done(self, index):
        pass
    def on_done_base_st3(self, index):
        if(index < 0):
            return
        self.templates         = sets.Get("captureTemplates",[])
        self.on_done(index)
    def on_done_base_st4(self, index, modifiers):
        self.on_done_base_st3(index)
    def run(self, edit):
        templates = sets.Get("captureTemplates",[])
        temps = []
        for temp in templates:
            log.debug("TEMPLATE: ", temp)
            temps.append(temp['name'])
        if(int(sublime.version()) >= 4096):
            self.view.window().show_quick_panel(temps, self.on_done_base_st4, -1, -1)
        else:
            self.view.window().show_quick_panel(temps, self.on_done_base_st3, -1, -1)

def IsType(val,template):
    return 'type' in template and template['type'].strip() == val

def GetProp(template,name,defaultVal=None):
    if('properties' in template):
        props = template['properties']
        if(isinstance(props,dict)):
            if(name in props):
                return props[name]
    return defaultVal


# Capture some text into our refile org file
class OrgCaptureCommand(OrgCaptureBaseCommand):
    def insert_template(self, template, panel):
        #template          = templates[index]['template']
        startPos = -1
        template, startPos = templateEngine.ExpandTemplate(self.view, template)

        panel.run_command("insert",{"characters": template})
        if(startPos >= 0):
            startPos = sublime.Region(startPos)
        else:
            startPos = panel.sel()[0]
        return startPos

    def cleanup_capture_panel(self):
        global captureBufferName
        if(not self.openas):
            self.panel.set_syntax_file('Packages/OrgExtended/OrgExtended.sublime-syntax')
            self.panel.set_name(captureBufferName)

    # In OpenAs mode we insert some pre-heading stars
    # Before inserting the snippet. This SHOULD get our
    # heading where it needs to be?
    def on_added_stars(self):
        self.pt = self.panel.text_point(self.insertRow,0)
        linev = self.panel.line(self.pt)
        linetxt = self.panel.substr(linev)
        self.panel.sel().clear()
        self.panel.sel().add(linev.begin() + len(linetxt.rstrip()))
        self.insert_snippet(self.index)

    def find_end_of_thing(self, panel, insertAt, itemre):
        self.insertRow = insertAt.local_end_row
        self.pt = panel.text_point(insertAt.local_end_row,0)
        #item_line_regex   = re.compile(r'^(\s*)([-+])\s*[^\[]')
        have = False
        itemtype = '-'
        preprefix = " " * (insertAt.level+1)
        for row in range(insertAt.start_row, insertAt.local_end_row+1):
            pt = panel.text_point(row,0)
            line  = panel.substr(panel.line(pt))
            m = itemre.search(line)
            if(m):
                preprefix = m.group(1)
                itemtype = m.group(2)
                have = True
            elif(have):
                self.insertRow = row
                self.pt = pt
                break
        return (preprefix, itemtype)

    def on_panel_ready(self, index, openas, panel,cnt=0):
        self.panel = panel
        global captureBufferName
        captureBufferName = sets.Get("captureBufferName", captureBufferName)
        window = self.view.window()
        template = self.templates[index]
        target, capturePath, captureFile, at, toinsert = GetCapturePath(self.view, template)
        if(panel.is_loading()):
            sublime.set_timeout_async(lambda: self.on_panel_ready(index, openas, panel), 100)
            return

        if(toinsert != "" and cnt==0):
            pt = panel.text_point(at,0)
            linev = panel.line(pt)
            linetxt = panel.substr(linev)
            if((linetxt and not linetxt.strip() == "") or at == 0 or panel.lastRow() == at):
                toinsert = "\n" + toinsert
                pt = linev.end()
            else:
                pt = linev.begin()
            panel.Insert(pt, toinsert, evt.Make(lambda: self.on_panel_ready(index,openas,panel,cnt+1)))
            return

        startPos = -1
        # Try to store the capture index
        panel.settings().set('cap_index',index)
        panel.settings().set('cap_view',self.view.id())
        self.openas = openas
        if((IsType('item',template) or IsType('checkitem',template) or IsType('plain',template) or IsType('table-line',template)) and not 'snippet' in template):
            template['snippet'] = 'plain_template'
            if('template' in template):
                del template['template']

        if('template' in template):
            startPos = self.insert_template(template['template'], panel)
            window.run_command('show_panel', args={'panel': 'output.orgcapture'})
            panel.sel().clear()
            panel.sel().add(startPos)
            window.focus_view(panel)
            self.cleanup_capture_panel()
        elif('snippet' in template):
            self.level = 0
            self.pt = None
            prefix = ""
            preprefix = ""
            itemtype = '-'
            if(self.openas):
                insertAt = captureFile.At(at)
                if(IsType('plain',template)):
                    self.pt = panel.text_point(insertAt.local_end_row,0)
                    self.insertRow = insertAt.local_end_row
                elif(IsType('checkitem',template)):
                    preprefix, itemtype = self.find_end_of_thing(panel, insertAt, re.compile(r'^(\s*)([-+])\s*(\[[xX\- ]\])\s+'))
                elif(IsType('item',template)):
                    preprefix, itemtype = self.find_end_of_thing(panel, insertAt, re.compile(r'^(\s*)([-+])\s*[^\[]'))
                elif(IsType('table-line',template)):
                    preprefix, itemtype = self.find_end_of_thing(panel, insertAt, re.compile(r'^(\s*)([|])'))
                else:
                    self.pt = panel.text_point(insertAt.end_row,0)
                    self.insertRow = insertAt.end_row
                linev = panel.line(self.pt)
                linetxt = panel.substr(linev)
                if((linetxt and not linetxt.strip() == "") or at == 0 or (insertAt and panel.lastRow() == insertAt.end_row)):
                    prefix = "\n"
                    self.pt = linev.end()
                    self.insertRow += 1
                else:
                    self.pt = linev.begin()
                panel.sel().clear()
                panel.sel().add(self.pt)
                self.level = insertAt.level
            else:
                window.run_command('show_panel', args={'panel': 'output.orgcapture'})
            if(self.openas and self.level > 0):
                self.index = index
                self.panel = panel
                if(IsType('plain',template)):
                    self.panel.Insert(self.pt, prefix + (" " * (self.level+1)), evt.Make(self.on_added_stars))
                elif(IsType('item',template)):
                    self.panel.Insert(self.pt, prefix + preprefix + itemtype + " ", evt.Make(self.on_added_stars))
                elif(IsType('checkitem',template)):
                    self.panel.Insert(self.pt, prefix + preprefix + itemtype + " [ ] ", evt.Make(self.on_added_stars))
                elif(IsType('table-line',template)):
                    self.panel.Insert(self.pt, prefix + preprefix + itemtype, evt.Make(self.on_added_stars))
                else:
                    self.panel.Insert(self.pt, prefix + ("*" * self.level), evt.Make(self.on_added_stars))
            else:
                if(IsType('plain',template)):
                    self.panel.Insert(self.pt, prefix, evt.Make(self.on_added_stars))
                elif(prefix != ""):
                    self.index = index
                    self.panel = panel
                    self.panel.Insert(self.pt, prefix, evt.Make(self.on_added_stars))
                else:
                    self.insert_snippet(index)

    def insert_snippet(self, index):
        window = self.view.window()
        template = self.templates[index]
        ai = sublime.active_window().active_view().settings().get('auto_indent')
        self.panel.settings().set('auto_indent',False)
        snippet = template['snippet']
        snipName = ext.find_extension_file('orgsnippets',snippet,'.sublime-snippet')
        window.focus_view(self.panel)
        #panel.meta_info("shellVariables", 0)[0]['TM_EMAIL'] = "Trying to set email value"
        self.panel.run_command('_enter_insert_mode', {"count": 1, "mode": "mode_internal_normal"})
        now = datetime.datetime.now()
        inow = orgdate.OrgDate.format_date(now, False)
        anow = orgdate.OrgDate.format_date(now, True)
        # "Packages/OrgExtended/orgsnippets/"+snippet+".sublime-snippet"
        # OTHER VARIABLES:
        # TM_FULLNAME - Users full name
        # TM_FILENAME - File name of the file being edited
        # TM_CURRENT_WORD - Word under cursor when snippet was triggered
        # TM_SELECTED_TEXT - Selected text when snippet was triggered
        # TM_CURRENT_LINE - Line of snippet when snippet was triggered
        self.panel.run_command("insert_snippet", 
            { "name" : snipName
            , "ORG_INACTIVE_DATE": inow
            , "ORG_ACTIVE_DATE":   anow
            , "ORG_DATE":          str(datetime.date.today())
            , "ORG_TIME":          datetime.datetime.now().strftime("%H:%M:%S")
            , "ORG_CLIPBOARD":     sublime.get_clipboard()
            , "ORG_SELECTION":     self.view.substr(self.view.sel()[0])
            , "ORG_LINENUM":       str(self.view.curRow())
            , "ORG_FILENAME":      self.view.file_name()
            })
        sublime.active_window().active_view().settings().set('auto_indent',ai)
        self.cleanup_capture_panel()

    def on_done_st4(self,index,modifiers):
        self.on_done(index)
    def on_done(self, index):
        if(index < 0):
            return
        global captureBufferName
        captureBufferName = sets.Get("captureBufferName", captureBufferName)
        window = self.view.window()
        template = self.templates[index]
        target, capturePath, captureFile, at, toinsert = GetCapturePath(self.view, template)
        openas = False
        if('openas' in template and 'direct' == template['openas']):
            panel = window.open_file(capturePath)
            openas = True
        else:
            panel = window.create_output_panel("orgcapture")
        self.on_panel_ready(index, openas, panel)


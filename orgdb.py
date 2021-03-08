import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
import fnmatch
import OrgExtended.orgparse.loader as loader
import OrgExtended.orgparse.node as node
import OrgExtended.orgutil.util as util
import OrgExtended.orgutil.navigation as nav
import OrgExtended.orgutil.template as templateEngine
import logging
import sys
import traceback 
import OrgExtended.orgfolding
import OrgExtended.asettings as sets
import OrgExtended.pymitter as evt

log = logging.getLogger(__name__)
headingRe = re.compile("^([*]+) (.+)")

class FileInfo:
    def __init__(self, file, parsed, orgPaths):
        self.org      = parsed
        self.filename = file
        self.key      = file.lower() if file else None
        self.change_count = 0
        self.org.setFile(self)
        displayFn = self.key
        oldLen = len(displayFn) if displayFn else 0
        if(not displayFn):
            self.displayFn = "<BUFFER>"
            return
        for prefix in orgPaths:
            displayFn = displayFn.replace(prefix,"") 
            displayFn = displayFn.replace(prefix.lower(),"")
        # Max Slashes!
        # No prefixes. We should count the slashes and truncate
        # if there are to many.
        maxSlash = 3
        if(oldLen == len(displayFn)):
           scount = displayFn.count('/')
           if(scount > maxSlash):
               llist = displayFn.split('/')
               displayFn = '/'.join(llist[-maxSlash:]) 
           scount = displayFn.count('\\')
           if(scount > maxSlash):
               llist = displayFn.split('\\')
               displayFn = '\\'.join(llist[-maxSlash:]) 

        if(len(displayFn) > 1 and (displayFn[0] == '\\' or displayFn[0] == '/')): 
            displayFn = displayFn[1:]
        self.displayName = displayFn

    def Root(self):
        return self.org[0]
        
    def LoadS(self,view):
        bufferContents = view.substr(sublime.Region(0, view.size()))
        self.org = loader.loads(bufferContents)
        self.org.setFile(self)
        # Keep track of last change count.
        self.change_count = view.change_count()

    def Reload(self):
        self.org = loader.load(self.filename)
        self.org.setFile(self)

    def ResetChangeCount(self):
        self.change_count = 0

    def HeadingCount(self):
        return len(self.org) - 1

    def Save(self):
        f = open(self.filename,"w+")
        for item in self.org:
            f.write(str(item))
        f.close()

    def ReloadIfChanged(self,view):
        if(self.HasChanged(view)):
            self.LoadS(view)

    def FindInfoAndReloadIfChanged(self, view):
        if(self.HasChanged(view)):
            self.LoadS(view)
        return self.FindInfo(view)

    def HasChanged(self,view):
        return self.change_count < view.change_count()

    def At(self, row):
        return self.org.at(row)

    def AtPt(self, view, pt):
        self.ReloadIfChanged(view)
        row,col = view.rowcol(pt)
        return self.org.at(row)

    def AtRegion(self, view, reg):
        row,col = view.rowcol(reg.begin())
        return self.org.at(row)

    def AtInView(self, view):
        self.ReloadIfChanged(view)
        (row,col) = view.curRowCol()
        return self.org.at(row)

    def AgendaFilenameTag(self):
        return os.path.splitext(os.path.basename(self.filename))[0] + ":" 

    def FindOrCreateNode(self, heading):
        for n in self.org[1:]:
            if(heading == n.full_heading):
                return n

        # Okay got here and didn't find the node, have to make it.
        m = headingRe.search(heading)
        if(m == None):
            log.error("FindorCreateNode: failed to parse heading: " + heading)
            return None
        levelGroup = m.group(1)
        level = len(levelGroup)
        cur         = self.org[0]
        parentLevel = level-1
        while(cur.level < parentLevel):
            if(cur.num_children == 0):
                tree = loader.loads("* " + str(datetime.datetime()))
                cur.insert_child(tree[1])
            cur = cur.get_last_child()
        if(heading == None or heading.isspace() or heading.strip() == ""):
            return cur
        else:
            tree = loader.loads(heading)
            cur.insert_child(tree[1])
            cur = cur.get_last_child()
        return cur



class OrgDb:
    def __init__(self):
        self.files    = {}
        self.Files    = []
        self.orgPaths = None
        self.customids    = []
        self.customidmaps = []
        self.tags = set()


    def OnTags(self, tags):
        for i in tags:
            self.tags.add(i)

    def RebuildCustomIds(self):
        self.customids    = []
        self.customidmaps = []
        for file in self.Files:
            for id in file.org.env.customids:
                self.customids.append(id)
                self.customidmaps.append(file)    

    def LoadNew(self, fileOrView):
        if(fileOrView == None):
            return None
        if(not hasattr(self,'orgPaths') or self.orgPaths == None):
            self.orgPaths = sets.Get("orgDirs",None)
        filename = self.FilenameFromFileOrView(fileOrView)
        if(util.isPotentialOrgFile(filename)):
            file = FileInfo(filename, loader.load(filename), self.orgPaths)
            self.AddFileInfo(file)
            return file
        elif(util.isView(fileOrView) and util.isOrgSyntax(fileOrView)):
            bufferContents = fileOrView.substr(sublime.Region(0, fileOrView.size()))
            file = FileInfo(filename if filename else util.getKey(fileOrView), loader.loads(bufferContents), self.orgPaths)
            self.AddFileInfo(file)
            return file
        else:
            log.debug("File is not an org file, not loading into the database: " + str(filename))
            return None

    def Remove(self, fileOrView):
        if(type(fileOrView) is sublime.View):
            filename = fileOrView.file_name().lower()
        else:
            filename = fileOrView.lower()
        for i in range(len(self.Files)-1,-1,-1):
            if(self.Files[i].key == filename):
                del self.Files[i]

        if(filename in self.files):
            del self.files[filename]
        #self.files.pop(filename,None)

    def Reload(self, fileOrView):
        self.orgPaths = sets.Get("orgDirs",None)
        fi = self.FindInfo(fileOrView)
        if(fi != None):
            fi.Reload()
            self.RebuildCustomIds()
            return fi
        else:
            rv = self.LoadNew(fileOrView)
            self.RebuildCustomIds()
            return rv


    def GetIndentForRegion(self, view, region):
        node = self.AtRegion(view, region)
        return node.level + 1

    def FilenameFromFileOrView(self,fileOrView):
        filename = None
        if(type(fileOrView) is sublime.View):
            filename = fileOrView.file_name()
        else:
            filename = fileOrView
        return filename

    def AddFileInfo(self, fi):
        if(self.files == None):
            self.files = {}
        self.files[fi.key] = fi
        if(self.Files == None):
            self.Files = []
        self.Files.append(fi)
        self.SortFiles()

    def SortFiles(self):
        self.Files.sort(key=lambda x: x.key) 

    @staticmethod
    def IsExcluded(filename, excludedPaths, excludedFiles):
        if(excludedPaths):
            excludedPaths = [x.lower().replace('\\','/') for x in excludedPaths] 
            mypath = os.path.dirname(filename).lower().replace('\\','/')
            for item in excludedPaths:
                if mypath.startswith(item):
                    return True
        if(excludedFiles):
            excludedFiles = [x.lower().replace('\\','/') for x in excludedFiles] 
            myfile = os.path.basename(filename).lower().replace('\\','/')
            for item in excludedFiles:
                if(item == myfile):
                    return True
        return False 

    def RebuildDb(self):
        if(evt.Get().listeners('tagsfound')):
            evt.Get().clear_listeners('tagsfound')
        evt.Get().on("tagsfound",self.OnTags)
        self.Files = []
        self.files = {}
        self.orgPaths = sets.Get("orgDirs",None)
        self.orgFiles = sets.Get("orgFiles",None)
        self.orgExcludePaths = sets.Get("orgExcludeDirs",None)
        self.orgExcludeFiles = sets.Get("orgExcludeFiles",None)
        matches = []
        if(self.orgPaths):
            for orgPath in self.orgPaths:
                orgPath = orgPath.replace('\\','/')
                globSuffix = sets.Get("validOrgExtensions",[".org"])
                for suffix in globSuffix:
                    if('archive' in suffix):
                        continue
                    suffix = "*" + suffix
                    dirGlobPos = orgPath.find("**")
                    if(dirGlobPos > 0):
                        suffix  = os.path.join(orgPath[dirGlobPos:],suffix)
                        orgPath = orgPath[0:dirGlobPos]
                    if("*" in orgPath):
                        log.error(" orgDirs only supports double star style directory wildcards! Anything else is not supported: " + str(orgPath))
                        if(sublime.active_window().active_view()):
                            sublime.active_window().active_view().set_status("Error: ","orgDirs only supports double star style directory wildcards! Anything else is not supported: " + str(orgPath))
                        log.error(" skipping orgDirs value: " + str(orgPath))
                        continue
                    for path in Path(orgPath).glob(suffix):
                        if OrgDb.IsExcluded(str(path), self.orgExcludePaths, self.orgExcludeFiles):
                            continue
                        try:
                            filename = str(path)
                            file = FileInfo(filename,loader.load(filename), self.orgPaths)
                            self.AddFileInfo(file)
                        except Exception as e:
                            #x = sys.exc_info()
                            log.warning("FAILED PARSING: %s\n  %s",str(path),traceback.format_exc())
        if(self.orgFiles):
            for orgFile in self.orgFiles:
                path = orgFile.replace('\\','/')
                if OrgDb.IsExcluded(str(path), self.orgExcludePaths, self.orgExcludeFiles):
                    continue
                try:
                    filename = str(path)
                    file = FileInfo(filename,loader.load(filename), self.orgPaths)
                    self.AddFileInfo(file)
                except Exception as e:
                    #x = sys.exc_info()
                    log.warning("FAILED PARSING: %s\n  %s",str(path),traceback.format_exc())
        self.SortFiles()
        self.RebuildCustomIds()

    def FindInfo(self, fileOrView):
        try:
            if(not fileOrView):
                return None
            key = util.getKey(fileOrView).lower()
            if(key and key in self.files):
                f = self.files[key]
            else:
                f = self.LoadNew(fileOrView)
            if(f and util.isView(fileOrView)):
                f.ReloadIfChanged(fileOrView)
            return f
        except:
            try:
                #log.debug("Trying to load file anew")
                f = self.LoadNew(fileOrView)            
                if(type(fileOrView) is sublime.View):
                    f.ReloadIfChanged(fileOrView)
                return f
            except:
                log.warning("FAILED PARSING: \n  %s",traceback.format_exc())
                return None

    def Find(self, fileOrView):
        n = self.FindInfo(fileOrView)
        if(n != None):
            return n.org
        return None

    def At(self, fileOrView, line):
        x = self.Find(fileOrView)
        if(x != None):
            return x.at(line)
        return None

    def AtInView(self, view):
        (row,col) = view.curRowCol()
        return self.At(view, row)

    def AtPt(self, view, pt):
        file = self.FindInfo(view)
        return file.AtPt(view, pt)

    def AtRegion(self, view, reg):
        file = self.FindInfo(view)
        return file.AtRegion(view, reg)

    def NodeAtIndex(self, fileOrView, index):
        return self.Find(fileOrView).node_at(index + 1)

    def Headings(self, view):
        f = self.Find(view)
        headings = []
        if(None != f):
            for n in f[1:]:
                headings.append((". " * (n.level)) + n.heading)
        return headings

    # This is paired with FindFileInfo
    def AllHeadings(self, view):
        headings = []
        for o in self.Files:
            displayFn = o.displayName
            f = o.org
            for n in f[1:]:
                formattedHeading = "{0:35}::{1}{2}".format(displayFn , (". " * (n.level)) , n.heading)
                #print(formattedHeading)
                headings.append(formattedHeading)
        return headings

    # This is paired with FindFileInfo
    def AllHeadingsWContext(self, view):
        headings = []
        count = 0
        for o in self.Files:
            displayFn = o.displayName
            f = o.org
            for n in f[1:]:
                parents = ""
                t = n
                while(type(t.parent) != node.OrgRootNode and t.parent != None):
                    t = t.parent
                    parents = t.heading + ":" + parents 
                #formattedHeading = "{0:35}::{1}{2}".format(displayFn , parents, n.heading)
                formattedHeading = ["{0}{1}".format(parents,n.heading),displayFn]
                #print(formattedHeading)
                headings.append(formattedHeading)
                count += 1
        return headings

    # This is a pair with AllHeadings, it can go from an index in that BACK to the
    # fileinfo
    def FindFileInfoByAllHeadingsIndex(self, index):
        curVal = 0
        for o in self.Files:
            if(index >= curVal and index < (curVal + o.HeadingCount())):
                return (o, (index - curVal) + 1) # remember to account for header
            curVal += o.HeadingCount()
        return None


    # Try to find a node by filename and locator
    def FindNode(self, filename, locator):
        file = self.FindInfo(filename)
        if(not file):
            return None

        # Basic locator search through the headings
        headings = locator.split(":")
        cur = file.org[0]
        for index in range(len(headings)):
            heading = headings[index]
            for n in cur.children:
                if(n.heading == heading):
                    cur = n
                    break
            # Did not find it darn
            if(cur.heading != heading):
                break
        heading = headings[len(headings)-1]
        if(cur.heading == heading):
            return cur

        if(len(headings) > 1):
            parent = headings[-1]
        bestMatch = None
        
        # fuzzy search, heading must match (hopefully)
        for n in file.org[1:]:
            if(n.heading == heading):
                bestMatch = n
                if(n.parent and n.parent.heading == parent):
                    return n
        return bestMatch
        
    def JumpToCustomId(self, id):
        path = None
        file, at = self.FindByCustomId(id)
        if(file != None):
            path = "{0}:{1}".format(file.filename,at + 1)
        if(path):
            #print("Found ID jumping to it: " + path)
            sublime.active_window().open_file(path, sublime.ENCODED_POSITION)
        else:
            log.debug("Could not locate ID failed to jump there")

    def FindByCustomId(self, id):
        for i in range(0, len(self.customids)):
            cid = self.customids[i]
            if(cid == id):
                file = orgDb.customidmaps[i]
                at   = file.org.env.customids[id][1]
                return (file, at)
        return (None, None)


# EXPORTED ORGDB
orgDb = OrgDb()
def Get():
    global orgDb
    return orgDb


# rebuild our org database from our org directory
class OrgRebuildDbCommand(sublime_plugin.TextCommand):
    def run(self,edit):
        Get().RebuildDb()


# Just reload the current file.
class OrgReloadFileCommand(sublime_plugin.TextCommand):
    def run(self,edit):
        file = Get().FindInfo(self.view)
        if(file):
            file.LoadS(self.view)
            orgDb.RebuildCustomIds()
        else:
            log.debug("FAILED TO FIND FILE INFO?")

class OrgJumpToCustomIdCommand(sublime_plugin.TextCommand):
    def on_done_st4(self,index,modifers):
        self.on_done(index)
    def on_done(self, index):
        if(index < 0):
            return
        file = orgDb.customidmaps[index]
        id   = orgDb.customids[index]
        at   = file.org.env.customids[id][1]
        path = "{0}:{1}".format(file.filename,at + 1)
        self.view.window().open_file(path, sublime.ENCODED_POSITION)

    def run(self, edit):
        if(int(sublime.version()) <= 4096):
            self.view.window().show_quick_panel(orgDb.customids, self.on_done, -1, -1)
        else:
            self.view.window().show_quick_panel(orgDb.customids, self.on_done_st4, -1, -1)


class OrgJumpToTodayCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        file, at = Get().FindByCustomId("TODAY")
        path = "{0}:{1}".format(file.filename,at + 1)
        self.view.window().open_file(path, sublime.ENCODED_POSITION)

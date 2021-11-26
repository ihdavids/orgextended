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
        self.isOrgDir = False
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
        self.isOrgDir = displayFn != self.key
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

    def RebuildBacklinks(self):
        links = self.org.env.links
        for link in links:
            if(link.IsFile()):
                f = link.link
                if(not os.path.isabs(f)):
                    f = os.path.normpath(os.path.join(os.path.dirname(self.filename),f))
                Get().AddBacklink(f, link, self)
                #print("TRIED TO BACKLINK: " + str(f))

    def Root(self):
        return self.org[0]

    def RootInView(self, view, db):
        self.ReloadIfChanged(view, db)
        return self.Root()
        
    def LoadS(self,view):
        bufferContents = view.substr(sublime.Region(0, view.size()))
        self.org = loader.loads(bufferContents,view.file_name() if view.file_name() else "<string>")
        self.org.setFile(self)
        # Keep track of last change count.
        self.change_count = view.change_count()
        self.RebuildBacklinks()

    def Reload(self):
        self.org = loader.load(self.filename)
        self.org.setFile(self)
        self.RebuildBacklinks()

    def ResetChangeCount(self):
        self.change_count = 0

    def HeadingCount(self):
        return len(self.org) - 1

    def Save(self):
        f = open(self.filename,"w+",encoding="utf-8")
        for item in self.org:
            f.write(str(item))
        f.close()

    def ReloadIfChanged(self,view,db):
        if(self.HasChanged(view)):
            self.LoadS(view)
            db.RebuildAllIdsForFile(self)

    #def FindInfoAndReloadIfChanged(self, view, db):
    #    if(self.HasChanged(view)):
    #        self.LoadS(view)
    #        db.RebuildAllIdsForFile(self)
    #   return self.FindInfo(view)

    def HasChanged(self,view):
        return self.change_count < view.change_count()

    def At(self, row):
        return self.org.at(row)

    def AtPt(self, view, pt, db):
        self.ReloadIfChanged(view, db)
        row,col = view.rowcol(pt)
        return self.org.at(row)

    def AtRegion(self, view, reg):
        row,col = view.rowcol(reg.begin())
        return self.org.at(row)

    def AtInView(self, view, db):
        self.ReloadIfChanged(view, db)
        (row,col) = view.curRowCol()
        return self.org.at(row)

    def AgendaFilenameTag(self):
        return os.path.splitext(os.path.basename(self.filename))[0] + ":" 

    def FindOrCreateNode(self, heading):
        for n in self.org[1:]:
            if(heading == n.full_heading):
                return n

        for n in self.org[1:]:
            if(heading == n.heading):
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

class OrgFileId:
    def __init__(self, file, id, index):
        self.file  =file
        self.id    = id
        self.index = index

class OrgDb:
    def __init__(self):
        self.files    = {}
        self.Files    = []
        self.orgPaths = None
        self.customids    = []
        self.customidmaps = {}
        self.ids          = []
        self.idmaps       = {}
        self.tags = set()
        self.backlinks = {}

    def GetBacklinks(self, view):
        fn = view.file_name()
        if( fn in self.backlinks):
            l = self.backlinks[fn]
            return l
        return None

    def AddBacklink(self, f, link, fi):
        link.fromFile   = fi
        link.targetName = f
        if(not f in self.backlinks):
            self.backlinks[f] = []
        for i in range(len(self.backlinks[f])):
            ff = self.backlinks[f][i]
            if(link.row == ff.row):
                self.backlinks[f][i] = link
                return
        self.backlinks[f].append(link)

    def OnTags(self, tags):
        for i in tags:
            self.tags.add(i)

    def RebuildCustomIdsForFile(self,file):
        for id in file.org.env.customids:
            if(not id in self.customidmaps):
                index = len(self.customids)
                fid = OrgFileId(file,id,index)
                self.customids.append(fid)
                self.customidmaps[id] = fid

    def RebuildIdsForFile(self,file):
        for id in file.org.env.ids:
            if(not id in self.idmaps):
                index = len(self.ids)
                fid = OrgFileId(file,id,index)
                self.ids.append(fid)
                self.idmaps[id] = fid

    def RebuildAllIdsForFile(self,file):
        self.RebuildIdsForFile(file)
        self.RebuildCustomIdsForFile(file)

    def RebuildIds(self):
        self.ids          = []
        self.idmaps       = {}
        self.customids    = []
        self.customidmaps = {}
        for file in self.Files:
            self.RebuildAllIdsForFile(file)

    def LoadNew(self, fileOrView):
        if(fileOrView == None):
            return None
        if(not hasattr(self,'orgPaths') or self.orgPaths == None):
            self.orgPaths = self.__GetPaths("orgDirs")
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
        self.orgPaths = self.__GetPaths("orgDirs")
        fi = self.FindInfo(fileOrView)
        if(fi != None):
            fi.Reload()
            self.RebuildIds()
            fi.RebuildBacklinks()
            return fi
        else:
            rv = self.LoadNew(fileOrView)
            self.RebuildIds()
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
        fi.RebuildBacklinks()

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
        self.orgPaths = self.__GetPaths("orgDirs")
        self.orgFiles = self.__GetPaths("orgFiles")
        self.orgExcludePaths = self.__GetPaths("orgExcludeDirs")
        self.orgExcludeFiles = self.__GetPaths("orgExcludeFiles")
        matches = []
        if(self.orgPaths):
            # Just in case the user gave us a string instead of a list.
            if(isinstance(self.orgPaths,str)):
                self.orgPaths = [ self.orgPaths ]
            for orgPath in self.orgPaths:
                orgPath = orgPath.replace('\\','/')
                globSuffix = sets.Get("validOrgExtensions",[".org"])
                for suffix in globSuffix:
                    if('archive' in suffix):
                        continue
                    suffix = "*" + suffix
                    dirGlobPos = orgPath.find("*")
                    if(dirGlobPos > 0):
                        suffix  = os.path.join(orgPath[dirGlobPos:],suffix)
                        orgPath = orgPath[0:dirGlobPos]
                    if("*" in orgPath):
                        log.error(" orgDirs only supports double star style directory wildcards! Anything else is not supported: " + str(orgPath))
                        if(sublime.active_window().active_view()):
                            sublime.active_window().active_view().set_status("Error: ","orgDirs only supports double star style directory wildcards! Anything else is not supported: " + str(orgPath))
                        log.error(" skipping orgDirs value: " + str(orgPath))
                        continue
                    try:
                        if not Path(orgPath).exists():
                            log.warning('orgDir path {} does not exist!'.format(orgPath))
                            continue
                    except:
                        log.warning('could not add org path: {} - does not seem to exist'.format(orgPath))
                        continue
                    try:
                        for path in Path(orgPath).glob(suffix):
                            if OrgDb.IsExcluded(str(path), self.orgExcludePaths, self.orgExcludeFiles):
                                continue
                            try:
                                filename = str(path)
                                log.debug("PARSING: " + filename)
                                file = FileInfo(filename,loader.load(filename), self.orgPaths)
                                file.isOrgDir = True
                                self.AddFileInfo(file)
                            except Exception as e:
                                #x = sys.exc_info()
                                log.warning("FAILED PARSING: %s\n  %s",str(path),traceback.format_exc())
                    except Exception as e:
                        log,logging.warning("ERROR globbing {}\n{}".format(orgPath, traceback.format_exc()))
        if(self.orgFiles):
            # Just in case the user gave us a string instead of a list.
            if(isinstance(self.orgFiles,str)):
                self.orgFiles = [ self.orgFiles ]
            for orgFile in self.orgFiles:
                path = orgFile.replace('\\','/')
                if OrgDb.IsExcluded(str(path), self.orgExcludePaths, self.orgExcludeFiles):
                    continue
                try:
                    filename = str(path)
                    file = FileInfo(filename,loader.load(filename), self.orgPaths)
                    file.isOrgDir = True
                    self.AddFileInfo(file)
                except Exception as e:
                    #x = sys.exc_info()
                    log.warning("FAILED PARSING: %s\n  %s",str(path),traceback.format_exc())
        self.SortFiles()
        self.RebuildIds()

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
                f.ReloadIfChanged(fileOrView, self)
            return f
        except:
            try:
                #log.debug("Trying to load file anew")
                f = self.LoadNew(fileOrView)            
                if(type(fileOrView) is sublime.View):
                    f.ReloadIfChanged(fileOrView, self)
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
        return file.AtPt(view, pt, self)

    def RootInView(self, view):
        file = self.FindInfo(view)
        if file:
            return file.RootInView(view, self)
        return None

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
    
    def AllHeadingsForFile(self, file):
        headings = []
        count = 0
        f = file.org
        for n in f[1:]:
            parents = ""
            t = n
            while(type(t.parent) != node.OrgRootNode and t.parent != None):
                t = t.parent
                parents = t.heading + ":" + parents 
            #formattedHeading = "{0:35}::{1}{2}".format(displayFn , parents, n.heading)
            formattedHeading = "{0}{1}".format(parents,n.heading)
            #print(formattedHeading)
            headings.append(formattedHeading)
            count += 1
        return headings

    # This is paired with FindFileInfo
    def AllFiles(self, view):
        files = []
        count = 0
        for o in self.Files:
            displayFn = o.displayName
            files.append(displayFn)
        return files

    def FindFileByIndex(self, index):
        return self.Files[index]

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
            #print("Found Custom ID jumping to it: " + path)
            sublime.active_window().open_file(path, sublime.ENCODED_POSITION)
            return True
        else:
            log.info("Could not locate Custom ID failed to jump there")
            return False
    
    def JumpToId(self, id):
        path = None
        file, at = self.FindById(id)
        if(file != None):
            path = "{0}:{1}".format(file.filename,at + 1)
        if(path):
            #print("Found Normal ID jumping to it: " + path)
            sublime.active_window().open_file(path, sublime.ENCODED_POSITION)
            return True
        else:
            log.info("Could not locate ID failed to jump there")
            return False

    def JumpToAnyId(self, id):
        if(not self.JumpToId(id)):
            return self.JumpToCustomId(id)
        return True

    def FindByAnyId(self, id):
        v = self.FindById(id)
        if(not v or v[0] == None):
            return self.FindByCustomId(id)
        return v

    def FindNodeByAnyId(self, id):
        v = self.FindByAnyId(id)
        #print(str(v))
        if(v and v[0]):
            return v[0].At(v[1])
        return None

    def FindFileByFilename(self,filename):
        for f in self.Files:
            if(filename in f.filename):
                return f
        return None

    def FindByCustomId(self, id):
        if(id in self.customidmaps):
            fid = self.customidmaps[id]
            file = fid.file
            at = file.org.env.customids[id][1]
            return (file,at)
        return (None, None)
    
    def FindById(self, id):
        if(id in self.idmaps):
            fid = self.idmaps[id]
            file = fid.file
            at = file.org.env.ids[id][1]
            return (file,at)
        return (None, None)

    def __GetPaths(self, name):
        paths = sets.Get(name, None)
        if (str == type(paths)):
            return os.path.expanduser(paths)
        if (list == type(paths)):
            return list(map(os.path.expanduser, paths))
        return None


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
            orgDb.RebuildIds()
        else:
            log.debug("FAILED TO FIND FILE INFO?")

class OrgJumpToCustomIdCommand(sublime_plugin.TextCommand):
    def on_done_st4(self,index,modifers):
        self.on_done(index)
    def on_done(self, index):
        if(index < 0 or index >= len(orgDb.customids)):
            return
        fid  = orgDb.customids[index]
        file = fid.file
        id   = fid.id
        at   = file.org.env.customids[id][1]
        path = "{0}:{1}".format(file.filename,at + 1)
        self.view.window().open_file(path, sublime.ENCODED_POSITION)

    def run(self, edit):
        if(int(sublime.version()) <= 4096):
            self.view.window().show_quick_panel(orgDb.customids, self.on_done, -1, -1)
        else:
            self.view.window().show_quick_panel(orgDb.customids, self.on_done_st4, -1, -1)

class OrgJumpToIdCommand(sublime_plugin.TextCommand):
    def on_done_st4(self,index,modifers):
        self.on_done(index)
    def on_done(self, index):
        if(index < 0 or index >= len(orgDb.ids)):
            return
        fid = orgDb.ids[index]
        file = fid.file
        id   = fid.id
        at   = file.org.env.ids[id][1]
        path = "{0}:{1}".format(file.filename,at + 1)
        self.view.window().open_file(path, sublime.ENCODED_POSITION)

    def run(self, edit):
        if(int(sublime.version()) <= 4096):
            self.view.window().show_quick_panel(orgDb.ids, self.on_done, -1, -1)
        else:
            self.view.window().show_quick_panel(orgDb.ids, self.on_done_st4, -1, -1)


class OrgJumpToTodayCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        file, at = Get().FindByCustomId("TODAY")
        path = "{0}:{1}".format(file.filename,at + 1)
        self.view.window().open_file(path, sublime.ENCODED_POSITION)

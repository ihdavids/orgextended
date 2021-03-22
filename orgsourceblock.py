import ast
import logging
import os
import re
import tempfile
import traceback 

import OrgExtended.orgdb as db
import OrgExtended.orgextension as ext
import OrgExtended.orglist as lst
import OrgExtended.orgtableformula as tbl
import OrgExtended.orgutil.util as util
import OrgExtended.pymitter as evt
import sublime
import sublime_plugin
from   OrgExtended.orgparse.sublimenode import * 
from   OrgExtended.orgplist import *


log = logging.getLogger(__name__)

RE_END = re.compile(r"^\s*\#\+(END_SRC|end_src)")
RE_SRC_BLOCK = re.compile(r"^\s*\#\+(BEGIN_SRC|begin_src)\s+(?P<name>[^: ]+)\s*")
RE_FN_MATCH = re.compile(r"\s*[:]([a-zA-Z0-9-_]+)\s+([^: ]+)\s*")
RE_RESULTS = re.compile(r"^\s*\#\+(RESULTS|results)[:]\s*$")
RE_HEADING = re.compile(r"^[*]+\s+")
RE_PROPERTY_DRAWER = re.compile(r"^\s*[:][a-zA-Z0-9]+[:]\s*$")
RE_END_PROPERTY_DRAWER = re.compile(r"^\s*[:](END|end)[:]\s*$")
RE_BLOCK = re.compile(r"^\s*\#\+(BEGIN_|begin_)[a-zA-Z]+\s+")
RE_END_BLOCK = re.compile(r"^\s*\#\+(END_|end_)[a-zA-Z]+\s+")
RE_IS_BLANK_LINE = re.compile(r"^\s*$")
RE_FAIL = re.compile(r"\b([Ff][Aa][Ii][Ll][Ee][Dd])|([Ff][Aa][Ii][Ll][Uu][Rr][Ee][Ss]?)|([Ff][Aa][Ii][Ll])|([Ee][Rr][Rr][Oo][Rr][Ss]?)\b")


def IsSourceBlock(view):
    at = view.sel()[0]
    return (view.match_selector(at.begin(),'orgmode.fence.sourceblock') or view.match_selector(at.begin(),'orgmode.sourceblock.content'))

def IsSourceFence(view,row):
    #line = view.getLine(view.curRow())
    line = view.getLine(row)
    return RE_SRC_BLOCK.search(line) or RE_END.search(line)


def HasFailure(output):
    os = " ".join(output)
    return RE_FAIL.search(os)

RE_TEXT_PREFIX = re.compile(r'^\s*[:]\s')
def IsPrefixedTextBlob(view,pt):
    line = view.line(pt)
    line = view.substr(line)
    return RE_TEXT_PREFIX.search(line)

class TextDef:
    def __init__(self,view=None,pt=None):
        self.lines = []
        if(None != view):
            row,_        = view.rowcol(pt)
            last_row = view.lastRow()
            for r in range(row,last_row+1):
                point = view.text_point(r,0)
                line = view.line(point)
                line = view.substr(line)
                line = RE_TEXT_PREFIX.sub("",line)
                if(line.strip() == ""):
                    break
                self.lines.append(line)

    @staticmethod
    def CreateTextFromText(txt):
        tdef = TextDef()
        for t in txt:
            t = RE_TEXT_PREFIX.sub("",t)
            tdef.lines.append(t)
        return tdef

def ProcessPotentialFileOrgOutput(cmd):
    outputs = list(filter(None, cmd.outputs)) 
    if(cmd.params and cmd.params.Get('file',None)):
        out = cmd.params.Get('file',None)
        if(hasattr(cmd,'output') and cmd.output):
            if(not out or HasFailure(cmd.output)):
                out = cmd.output
        if(out):
            sourcepath = os.path.dirname(cmd.sourcefile)
            destFile    = os.path.join(sourcepath,out)
            destFile = os.path.relpath(destFile, sourcepath)
            if(out and not HasFailure(outputs)):
                outputs = []
            outputs.append("[[file:" + destFile + "]]")
            return outputs,destFile


def BuildFullParamList(cmd,language,cmdArgs):
    # First Add from global settings
    # First Add from PROPERTIES
    plist = PList.createPList("")
    view = sublime.active_window().active_view()
    if(view):
        plist.AddFromPList(sets.Get('babel-args',None))
        plist.AddFromPList(sets.Get('babel-args-'+language,None))
        node = db.Get().AtInView(view)
        if(node):
            props = node.get_comment('PROPERTY',None)
            if(props):
                for prop in props:
                    prop = prop.strip()
                    if(prop.startswith('header-args:' + language + ":")):
                        plist.AddFromPList(prop.replace('header-args:'+language+":",""))
                    elif(prop.startswith('header-args:')):
                        plist.AddFromPList(prop.replace('header-args:',""))
            pname = 'header-args:' + language
            if('header-args' in node.properties):
                #print(str(node.properties['header-args']))
                plist.AddFromPList(node.properties['header-args'])
            if(pname in node.properties):
                plist.AddFromPList(node.properties[pname])
            if('var' in node.properties):
                vs = node.properties['var'].strip()
                plist.Add('var',vs)
    plist.AddFromPList(cmdArgs)
    cmd.params = plist


def SetupOutputHandler(cmd,skipFile = False):
    res = cmd.params.Get('results',['raw','output','verbatim'])
    if(not skipFile and cmd.params.Has('file')):
        return FileHandler(cmd,cmd.params)
    elif(re.search(r'\btable\b',res) or re.search(r'\bvector\b',res)):
        return TableHandler(cmd,cmd.params)
    elif(re.search(r'\braw\b',res)):
        return RawHandler(cmd,cmd.params)
    elif(re.search(r'\blist\b',res)):
        return ListHandler(cmd,cmd.params)
    # Verbatim is the default
    # Scalar is also allowed for this
    else:
        return TextHandler(cmd,cmd.params)

def SetupOutputFormatter(cmd):
    res = cmd.params.Get('results',['raw','output','verbatim'])
    if(re.search(r'\bdrawer\b',res)):
        return DrawerFormatter(cmd)
    elif(re.search(r'\bcode\b', res)):
        return CodeFormatter(cmd)
    elif(re.search(r'\borg\b', res)):
        return OrgFormatter(cmd)
    elif(re.search(r'\bhtml\b', res)):
        return HtmlFormatter(cmd)
    elif(re.search(r'\blatex\b', res)):
        return LatexFormatter(cmd)
    # Raw is the default
    else:
        return None

def GetGeneratorForRow(table,params,r):
    for c in range(1,table.Width()+1):
        yield table.GetCellText(r,c)

def GetGeneratorForTable(table,params):
    for r in range(1,table.Height()+1):
        yield GetGeneratorForRow(table,params,r)


RE_ISCOMMENT = re.compile(r"^\s*[#][+]")
def LookupNamedSourceBlockInFile(name):
    view = sublime.active_window().active_view()
    if(view):
        node = db.Get().AtInView(view)
        if(node):
            # Look for named objects in the file.
            names = node.names
            if(names and name in names):
                row = names[name]['row']
                last_row = view.lastRow()
                for r in range(row,last_row):
                    if(IsSourceFence(view,r)):
                        row = r
                        break
                    pt = view.text_point(r, 0)
                    line = view.substr(view.line(pt))
                    m = RE_ISCOMMENT.search(line)
                    if(m):
                        continue
                    elif(line.strip() == ""):
                        continue
                    else:
                        row = r
                        break
                pt = view.text_point(row,0)
                reg = view.line(pt)
                line = view.substr(reg)
                if(IsSourceFence(view,row)):
                    return pt
    return None

# We want to first build up the full list of vars
# from options, comments, properties and everything else
#
# Then any var we want to post process them so they become
# data sources that reference their various potential
# locations.
def ProcessPossibleSourceObjects(cmd,language,cmdArgs):
    #BuildFullParamList(cmd,language,cmdArgs)
    var = cmd.params.GetDict('var',None)
    cmd.params.Replace('var',var)
    cmd.deferedSources = 0
    hadDeferred = False
    if(var):
        for k in var:
            n = var[k]
            if(not util.numberCheck(n)):
                td = tbl.LookupTableFromNamedObject(n)
                if(td):
                    # I think it's better to just pass through the table here.
                    # Each language may want to do something very different and abstracting away
                    # What the data source actually is may actually be a disservice
                    #var[k] = GetGeneratorForTable(td,cmd.params)
                    var[k] = td
                else:
                    l = lst.LookupNamedListInFile(n)
                    if(l):
                        var[k] = l
                    else:
                        pt = LookupNamedSourceBlockInFile(n)
                        if(None != pt):
                            if(not n in cmd.sourcefns):
                                cmd.deferedSources += 1
                                hadDeferred = True
                                cmd.sourcefns[n] = {'at': pt, 'key': k,'name': n}
                                cmd.view.run_command('org_execute_source_block',{'at':pt, 'onDoneResultsPos': evt.Make(cmd.OnDoneFunction), 'onDoneFnName': n})
    return hadDeferred

class ResultsFormatter:
    def __init__(self,cmd):
        self.cmd = cmd
    def SetIndent(self,level):
        self.level = level
    def GetIndent(self):
        return (" " * self.level) + " "
    def FormatOutput(self,output):
        return (output,0)

class DrawerFormatter(ResultsFormatter):
    def __init__(self,cmd):
        super(DrawerFormatter,self).__init__(cmd)

    def FormatOutput(self,output):
        output = ":results:\n" + self.GetIndent() + output + "\n" + self.GetIndent() + ":end:"
        return (output,1)

class CodeFormatter(ResultsFormatter):
    def __init__(self,cmd):
        super(CodeFormatter,self).__init__(cmd)

    def FormatOutput(self,output):
        output = "#+begin_src "+self.cmd.language+"\n" + self.GetIndent() + output + "\n" + self.GetIndent() + "#+end_src"
        return (output,1)

class HtmlFormatter(ResultsFormatter):
    def __init__(self,cmd):
        super(HtmlFormatter,self).__init__(cmd)

    def FormatOutput(self,output):
        output = "#+begin_export html\n" + self.GetIndent() + output + "\n" + self.GetIndent() + "#+end_export"
        return (output,1)

class LatexFormatter(ResultsFormatter):
    def __init__(self,cmd):
        super(LatexFormatter,self).__init__(cmd)

    def FormatOutput(self,output):
        output = "#+begin_export latex\n" + self.GetIndent() + output + "\n" + self.GetIndent() + "#+end_export"
        return (output,1)

class OrgFormatter(ResultsFormatter):
    def __init__(self,cmd):
        super(OrgFormatter,self).__init__(cmd)

    def FormatOutput(self,output):
        output = "#+begin_src org\n" + self.GetIndent() + output + "\n" + self.GetIndent() + "#+end_src"
        return (output,1)

class ResultsHandler:
    def __init__(self, cmd, params):
        self.params = params
        self.cmd    = cmd
    def SetIndent(self,level):
        self.level = level
    def GetIndent(self):
        if(self.level == 0):
            return ""
        else:
            return (" " * self.level) + " "
    def FormatOutput(self, output):
        pass
    def PostProcess(self, view, outPos, onDone):
        onDone()

class TextHandler(ResultsHandler):
    def __init__(self,cmd,params):
        super(TextHandler,self).__init__(cmd,params)

    def GetIndent(self):
        if(self.level == 0):
            return ""
        if(not self.cmd.outFormatter):
            return (" " * self.level) + " : "
        else:
            return (" " * self.level) + " "

    def FormatOutput(self, output):
        indent = "\n"+ self.GetIndent()
        be = len(output)-1
        for i in range(len(output)-1,0,-1):
            if(output[i].strip() == ""):
                be = i
            else:
                break
        if(be > 0):
            output = output[0:be]
        output = indent.join(output).rstrip()
        output = output.lstrip()
        if(not self.cmd.outFormatter):
            return ": " + output
        else:
            return output

class ListHandler(ResultsHandler):
    def __init__(self,cmd,params):
        super(ListHandler,self).__init__(cmd,params)

    def GetIndent(self):
        if(self.level == 0):
            return "- "
        return (" " * self.level) + " - "

    def FormatOutput(self, output):
        indent = "\n"+ self.GetIndent()
        # Strip whitespace from the end of this.
        be = len(output)-1
        for i in range(len(output)-1,0,-1):
            if(output[i].strip() == ""):
                be = i
            else:
                break
        if(be > 0):
            output = output[0:be]
        # Try to convert AST to list.
        for i in range(0,len(output)):
            try:
                l = ast.literal_eval(output[i])
                if(isinstance(l,list)):
                    del output[i]
                    for r in reversed(l):
                        output.insert(i,str(r))
            except:
                #print("EXCEPTION")
                #print(traceback.format_exc())
                pass
        output = indent.join(output).rstrip()
        output = output.lstrip()
        return "- " + output

class RawHandler(ResultsHandler):
    def __init__(self,cmd,params):
        super(RawHandler,self).__init__(cmd,params)

    def FormatOutput(self, output):
        indent = "\n"+ self.GetIndent()
        be = len(output)-1
        for i in range(len(output)-1,0,-1):
            if(output[i].strip() == ""):
                be = i
            else:
                break
        if(be > 0):
            output = output[0:be]
        output = indent.join(output).rstrip()
        output = output.lstrip()
        return output

class FileHandler(ResultsHandler):
    def __init__(self,cmd, params):
        super(FileHandler,self).__init__(cmd,params)

    def FormatOutput(self, output):
        out,fname = ProcessPotentialFileOrgOutput(self.cmd)
        indent = "\n"+ self.GetIndent()
        rawoutput = output
        if(not hasattr(self.cmd.curmod,"GeneratesImages") or not self.cmd.curmod.GeneratesImages(self)):
            dn = os.path.dirname(fname)
            p = os.path.dirname(self.cmd.sourcefile)
            fp = os.path.join(p,dn)
            if(fp.strip() != ""):
                os.makedirs(fp, exist_ok=True)
            ffname = os.path.join(p,fname)
            with open(ffname,'w') as f:
                # We setup an output handler for the file.
                outHandler = SetupOutputHandler(self.cmd, True)
                outHandler.SetIndent(0)
                rawoutput = outHandler.FormatOutput(rawoutput)
                f.write(rawoutput)
            # TODO Modify file attribs of generated file.
            #st = os.stat(fname)
            #os.chmod(fname, st.st_mode | stat.S_IEXEC)
        output = indent.join(out).rstrip()
        return output.lstrip()


class TableHandler(ResultsHandler):
    def __init__(self,cmd,params):
        super(TableHandler,self).__init__(cmd,params)

    def FormatOutput(self, output):
        indent = "\n"+ self.GetIndent()
        output = indent.join(output).rstrip()
        output,self.isTable = tbl.TableConversion(self.level,output)
        output = output.strip()
        return output

    def PostProcess(self, view, outPos, onDone):
        view.sel().clear()
        view.sel().add(outPos)
        view.run_command("table_editor_align")
        sublime.set_timeout(onDone,1)


class OrgExecuteSourceBlockCommand(sublime_plugin.TextCommand):
    def run(self,edit, onDone=None, onDoneResultsPos=None,onDoneFnName=None,at=None):
        value = str(uuid.uuid4())
        self.exc = OrgExecuteSourceBlock(self.view,value)
        self.exc.run(edit,onDone,onDoneResultsPos,onDoneFnName,at)

class OrgExecuteSourceBlock:

    def __init__(self,view,id):
        self.id = id
        self.view = view

    def CheckResultsFor(self,val):
        res = self.params.Get('results',[])
        return (val in res)

    def OnDone(self):
        evt.EmitIf(self.onDone)
        if(self.silent != None):
            evt.EmitIfParams(self.onDoneResultsPos,postFormat=self.formattedOutput,preFormat=self.preFormattedOutput,name=self.onDoneFnName)
        else:
            evt.EmitIfParams(self.onDoneResultsPos,pos=self.resultsTxtStart,name=self.onDoneFnName)

    def OnPostProcess(self):
        self.curPt = self.view.sel()[0]
        self.outHandler.PostProcess(self.view, self.resultsTxtStart, self.OnPostPostProcess)

    def OnPostPostProcess(self):
        if(hasattr(self.curmod,"GeneratesImages") and self.curmod.GeneratesImages(self)):
            self.view.run_command("org_cycle_images",{"onDone": evt.Make(self.OnDone)})
        else:
            self.OnDone()

    def OnReplaced(self):
        if(hasattr(self.curmod,"PostExecute")):
            self.curmod.PostExecute(self)
        self.OnPostProcess()


    def EndResults(self,rw):
        self.endResults     = rw
        self.resultsStartPt = self.view.text_point(self.startResults+1,0)
        self.resultsEndPt   = self.view.text_point(self.endResults,0)
        self.resultsRegion  = sublime.Region(self.resultsStartPt, self.resultsEndPt)

    def FindResults(self,edit,at):
        self.createdResults = False
        row              = self.endRow+1
        fileEndRow,_     = self.view.rowcol(self.view.size())
        inResults        = False
        inPropertyDrawer = False
        inBlock          = False
        for rw in range(row, fileEndRow):
            line = self.view.substr(self.view.line(self.view.text_point(rw,0)))
            if(not inResults and RE_RESULTS.search(line)):
                self.startResults = rw
                inResults = True
                continue
            # A new heading ends the results.
            if(RE_HEADING.search(line)):
                if(inResults):
                    self.EndResults(rw)
                    return True
                else:
                    break
            if(inResults and not inPropertyDrawer and RE_PROPERTY_DRAWER.search(line)):
                inPropertyDrawer = True
                continue
            if(inResults and not inBlock and RE_BLOCK.search(line)):
                inBlock = True
                continue
            if(inResults and not inBlock and not inPropertyDrawer and inResults and RE_IS_BLANK_LINE.search(line)):
                self.EndResults(rw)
                return True
            if(inPropertyDrawer and RE_END_PROPERTY_DRAWER.search(line)):
                self.EndResults(rw+1)
                return True
            if(inBlock and RE_END_BLOCK.search(line)):
                self.EndResults(rw+1)
                return True
        # We just hit the end of the file.
        if(inResults):
            self.EndResults(fileEndRow)
            return True
        # We hit the end of the file and didn't find a results tag.
        # We need to make one.
        if(not inResults):
            log.debug("Could not locate #+RESULTS tag adding one!")
            if(self.endRow == self.view.endRow()):
                pt = self.view.text_point(self.endRow,0)
                pt = self.view.line(pt).end()
            else:
                pt = self.view.text_point(self.endRow,0)
                pt = self.view.line(pt).end() + 1
            indent = db.Get().AtPt(self.view,at).indent()
            if(not self.CheckResultsFor('silent') and self.silent == None):
                self.view.insert(edit, pt, "\n" +indent+ "#+RESULTS:\n")
            self.startResults   = self.endRow + 2 
            self.endResults     = self.startResults + 1
            self.resultsStartPt = self.view.text_point(self.startResults+1,0)
            self.resultsEndPt   = self.view.text_point(self.endResults,0)
            self.resultsRegion  = sublime.Region(self.resultsStartPt, self.resultsEndPt)
            self.createdResults = True
            return True

    def OnWarningSaved(self):
        if(self.view.is_dirty()):
            self.view.set_status("Error: ","Failed to save the view. ABORT, cannot execute source block since it is dirty")
            log.error("Failed to save the view. ABORT, cannot execute source code")
            return
        self.view.run_command("org_execute_source_block", {"onDone": self.onDone})

    def run(self, edit, onDone=None, onDoneResultsPos=None,onDoneFnName=None,at=None,silent=None):
        self.onDone = onDone
        self.onDoneResultsPos = onDoneResultsPos
        self.onDoneFnName=onDoneFnName
        self.silent = silent
        view = self.view
        if(at == None):
            at = view.sel()[0].begin()
        if(view.match_selector(at,'orgmode.fence.sourceblock') or view.match_selector(at,'orgmode.sourceblock.content')):
            # Scan up till we find the start of the block.
            row,_ = view.rowcol(at)
            while(row > 0):
                if(IsSourceFence(view, row)):
                    at = sublime.Region(view.text_point(row,1),view.text_point(row,1))
                    break
                row -= 1
            # Okay we have a dynamic block, now we need to know where it ends.
            start = at
            end   = None
            erow = view.endRow()
            for rw in range(row,erow+1):
                line = view.substr(view.line(view.text_point(rw,0)))
                if(RE_END.search(line)):
                    end = rw
                    break
            if(not end):
                log.error("Could not locate #+END_SRC tag")
                return

            # Okay now we have a start and end to build a region out of.
            # time to run a command and try to get the output.
            extensions = ext.find_extension_modules('orgsrc', ["plantuml", "graphviz", "ditaa", "powershell", "python", "gnuplot"])
            line = view.substr(view.line(start))
            m = RE_SRC_BLOCK.search(line)
            if(not m):
                log.error("FAILED TO PARSE SOURCE BLOCK: " + line)
                return
            fnname = m.group('name')
            log.debug("SRC NAME: " + fnname)
            self.paramdata = line[len(m.group(0)):]
            self.language = fnname
            # Now find me that function!
            if(fnname not in extensions):
                log.error("Function not found in src folder! Cannot execute!")
                return

            # Start setting up our execution state.
            self.curmod   = extensions[fnname]
            self.startRow = row + 1
            self.endRow   = end
            self.s        = view.text_point(self.startRow,0)
            self.e        = view.text_point(self.endRow,0)
            self.region   = sublime.Region(self.s,self.e)
            self.sourcefile = view.file_name()
            self.sourcefns = {}
            # Sanity check that the file exists on disk
            if(not self.sourcefile or not os.path.exists(self.sourcefile)):
                self.view.set_status("Error: ","Your source org file must exist on disk. ABORT.")
                log.error("Your source org file must exist on disk to generate images. The path is used when setting up relative paths.")
                self.OnDone()
                return
            if(view.is_dirty()):
                log.warning("Your source file has unsaved changes. We cannot run source modifications without saving the buffer.")
                view.run_command("save", {"async": False})
                sublime.set_timeout(self.OnWarningSaved,1)
                return
            BuildFullParamList(self,self.language,self.paramdata)
            # We need to find and or buid a results block
            # so we can replace it with the results.
            # ORG is super flexible about this, we are NOT!
            self.FindResults(edit,self.s)
            # TODO: Early out if this is a chain and we have already computed our
            #       results.
            self.ParamsPhase()
        else:
            log.error("NOT in A Source Block, nothing to run, place cursor on first line of source block")

    def ParamsPhase(self):
            view = self.view
            # Setup formatting and parameters now that we have execution state. 
            if(ProcessPossibleSourceObjects(self,self.language,self.paramdata)):
                # We are deferred! We do not continue form here!
                return
            else:
                self.Execute()
    def OnDoneFunction(self,otherParams=None):
        #results = otherParams['results']
        name    = otherParams['name']
        #print("DONE: " + str(results))
        #print("DONE2: " + str(name))
        #print("SOURCES: " + str(self.sourcefns))
        # Process the source here!
        var = self.params.Get('var',None) 
        fn = self.sourcefns[name]
        # Our goal is determine what is at results location
        # convert it and insert it into var.
        if('pos' in otherParams):
            pos = otherParams['pos']
            if(tbl.isTable(self.view,pos)):
                td = tbl.create_table(self.view, pos)
                var[fn['key']] = td
            else:
                l = lst.IfListExtract(self.view, pos)
                if(l):
                    var[fn['key']] = l
                else:
                    # Assume blank text
                    txt = TextDef(self.view,pos)
                    l = "\n".join(txt.lines)
                    l = l.strip()
                    var[fn['key']] = l
        # We didn't output, so we have to parse the contents
        # but not from the buffer
        if('preFormat' in otherParams):
            preFormat = otherParams['preFormat']
            preFormat = preFormat.split('\n')
            if(lst.isListLine(preFormat[0])):
                l = lst.CreateListFromList(preFormat)
                var[fn['key']] = l
            elif(tbl.isTableLine(preFormat[0])):
                pass
            else:
                t = TextDef.CreateTextFromText(preFormat)
                l = "\n".join(t.lines)
                l = l.strip()
                var[fn['key']] = l
            pass
        # TODO: Handle lists, text and other things.
        self.deferedSources -= 1
        if(self.deferedSources <= 0):
            self.FindResults(0,self.s)
            self.Execute()
    def Execute(self):
            view = self.view
            self.outHandler   = SetupOutputHandler(self)
            self.outFormatter = SetupOutputFormatter(self)

            # Run the "writer"
            if(hasattr(self.curmod,"Execute")):
                # Okay now time to replace the contents of the block
                self.source = view.substr(self.region)
                if(hasattr(self.curmod,"PreProcessSourceFile")):
                    self.curmod.PreProcessSourceFile(self)
                if(hasattr(self.curmod,"Extension")):
                    tmp = tempfile.NamedTemporaryFile(delete=False,suffix=self.curmod.Extension(self))
                    try:
                        self.filename = tmp.name
                        if(hasattr(self.curmod,"WrapStart")):
                            tmp.write((self.curmod.WrapStart(self) + "\n").encode("ascii"))
                        tmp.write(self.source.encode('ascii'))
                        if(hasattr(self.curmod,"WrapEnd")):
                            tmp.write(("\n" + self.curmod.WrapEnd(self)).encode("ascii"))
                        tmp.close() 
                        self.outputs = self.curmod.Execute(self,sets)
                    except:
                        log.debug(" " + traceback.format_exc())
                    finally:
                        pass
                else:
                    self.filename = None
                    self.outputs = self.curmod.Execute(self,sets)
                log.debug("OUTPUT: " + str(self.outputs))
            else:
                log.error("No execute in module, abort")
                return
            # Reformat adding indents to each line!
            # No bad formatting allowed!
            n = db.Get().AtPt(view,self.s)
            self.level = n.level
            self.outHandler.SetIndent(n.level)
            if(self.outFormatter):
                self.outFormatter.SetIndent(n.level)
            output = self.outHandler.FormatOutput(self.outputs)
            self.preFormattedOutput = output
            self.resultsTxtStart = self.resultsStartPt + self.level + 1
            rowadjust = 0
            if(self.outFormatter):
                output,rowadjust = self.outFormatter.FormatOutput(output)
            # If our formatter wrapped us we have to adjust our text point for post processing
            # and results text.
            if(rowadjust > 0):
                row,col = self.view.rowcol(self.resultsTxtStart)
                row += rowadjust
                self.resultsTxtStart = self.view.text_point(row,col)
            ## Keep track of this so we know where we are inserting the text.
            self.formattedOutput = (" " * self.level + " ") + output+'\n'
            if(self.CheckResultsFor('silent')):
                # We only echo to the console in silent mode.
                print(self.formattedOutput)
                self.silent = True
                self.OnReplaced()
            # Add after other text
            elif(self.CheckResultsFor('append')):
                self.view.run_command("org_internal_replace", {"start": self.resultsEndPt, "end": self.resultsEndPt, "text": self.formattedOutput,"onDone": evt.Make(self.OnReplaced)})
            # Add before other text
            elif(self.CheckResultsFor('prepend')):
                self.view.run_command("org_internal_replace", {"start": self.resultsStartPt, "end": self.resultsStartPt, "text": self.formattedOutput,"onDone": evt.Make(self.OnReplaced)})
            # Replace mode
            else:
                self.view.run_command("org_internal_replace", {"start": self.resultsStartPt, "end": self.resultsEndPt, "text": self.formattedOutput,"onDone": evt.Make(self.OnReplaced)})

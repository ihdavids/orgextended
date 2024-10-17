import ast
import logging
import os
import re
import tempfile
import traceback 
import hashlib
import getpass
import datetime

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
RE_INL_SRC_BLOCK = re.compile(r"(?P<block>(SRC_|src_)(?P<name>[a-zA-Z0-9_-]+)(\[(?P<params>[^\]]+)\])?\{(?P<code>[^}]+)\})(?P<resblock>\s*\{\{\{results\(\s*=(?P<res>[^)]*)=\s*\)\}\}\})?")
RE_INL_RESULTS_BLOCK = re.compile(r"\{\{\{results\(=(?P<val>.*)=\)\}\}\}")
RE_FN_MATCH = re.compile(r"\s*[:]([a-zA-Z0-9-_]+)\s+([^: ]+)\s*")
RE_RESULTS = re.compile(r"^\s*\#\+(RESULTS|results)(\s*\[\s*(?P<hash>[a-fA-F0-9]+)\s*\]\s*)?[:]\s*(?P<comment>[a-zA-Z0-9_-]+)?$")
RE_HEADING = re.compile(r"^[*]+\s+")
RE_PROPERTY_DRAWER = re.compile(r"^\s*[:][a-zA-Z0-9]+[:]\s*$")
RE_END_PROPERTY_DRAWER = re.compile(r"^\s*[:](END|end)[:]\s*$")
RE_BLOCK = re.compile(r"^\s*\#\+(BEGIN_|begin_)[a-zA-Z]+\s+")
RE_END_BLOCK = re.compile(r"^\s*\#\+(END_|end_)[a-zA-Z]+\s*")
RE_IS_BLANK_LINE = re.compile(r"^\s*$")
RE_FAIL = re.compile(r"\b([Ff][Aa][Ii][Ll][Ee][Dd])|([Ff][Aa][Ii][Ll][Uu][Rr][Ee][Ss]?)|([Ff][Aa][Ii][Ll])|([Ee][Rr][Rr][Oo][Rr][Ss]?)\b")
RE_HEADER_PARAMS = re.compile(r"^\s*\#\+(HEADER|header)[:]\s*(?P<params>.*)$")
RE_TABLE = re.compile(r"^\s*[|]")
RE_NOWEB = re.compile(r'^\s*[<][<](?P<noweb>[^>(]+)(\s*\(\s*(?P<params>[^)]*)\s*\))?[>][>]')


# Interface that can be used to wrap a TableDef OR a simple list
# Very simple table wrapper!
class TableData:
    def __init__(self,data):
        self.data = data
        if(isinstance(self.data,tbl.TableDef)):
            self.tabledef = True
        else:
            self.tabledef = False
    def Width(self):
        if(self.tabledef):
            return self.data.Width()
        else:
            return len(self.data[0]) if self.data and len(self.data) > 0 else 0
    def Height(self):
        if(self.tabledef):
            return self.data.Height()
        else:
            return len(self.data) if self.data else 0
    def ForEachRow(self):
        if(self.tabledef):
            return self.data.ForEachRow()
        else:
            return range(1,self.Height() + 1)
    def ForEachCol(self):
        if(self.tabledef):
            return self.data.ForEachCol()
        else:
            return range(1,self.Width() + 1)
    def GetCell(self,r,c):
        if(self.tabledef):
            return tbl.Cell(r,c,self.data).GetVal()
        else:
            r -= 1
            c -= 1
            if(r >= 0 and r <= self.Height() and c >= 0 and c <= self.Width()):
                return self.data[r][c]
            return None
    @staticmethod
    def ParseTable(data):
        if(isinstance(data,str)):
            data = data.split('\n')
        out = []
        for line in data:
            lineOut = []
            cells = line.split('|')
            for i in range(1,len(cells)-1):
                c = cells[i].strip()
                lineOut.append(c)
            out.append(lineOut)
        return TableData(out)

class NoWebRefs:
    def __init__(self,view):
        self.refs = {}
        self.change_count = view.change_count()
        self.view = view

    def ParseParamsInternal(self,view,pt):
        row,_ = view.rowcol(pt)
        language, paramdata, fenceLine = GetModuleAndParams(view,row)
        if(not language):
            log.error(" Could not find language value from source row: " + str(language))
            return None
        log.debug(" CACHE: {}".format(fenceLine))
        p = type('', (), {})() 
        p.s = pt
        BuildFullParamList(p, language, paramdata)
        row,_ = view.rowcol(pt)
        end   = FindEndOfSourceBlock(view,row)
        if(not end):
            log.error("Could not find the end of the source block! " + str(end))
            return None
        p.refName = p.params.Get('noweb-ref',None)
        p.at       = pt
        p.language = language
        p.end      = end
        p.start    = row
        return p

    def ParseParams(self,view,pt):
        p = self.ParseParamsInternal(view,pt)
        if(p and p.refName):
            if(not p.refName in self.refs):
                self.refs[p.refName] = []
            self.refs[p.refName].append(p)
    def Find(self,name):
        if(name in self.refs):
            return self.refs[name]
        else:
            pt = tbl.LookupNamedSourceBlockInFile(name)
            if(pt != None):
                p = self.ParseParamsInternal(self.view,pt)
                return [p]
        return None

class NoWebRefCache:
    def __init__(self):
        self.files = {}

    def ParseFile(self,view):
        filename = view.file_name()
        if(not filename):
            return
        refs = NoWebRefs(view)
        self.files[filename] = refs
        last_row = view.endRow()
        cur      = 0
        inBlock  = False
        for r in range(cur,last_row):
            cur = r
            pt = view.text_point(r,1)
            if(not inBlock and IsSourceBlock(view,pt)):
                refs.ParseParams(view,pt)
                inBlock = True
                continue
            elif(inBlock and IsEndSourceBlock(view,pt)):
                inBlock = False

    def GetFile(self,view):
        filename = view.file_name()
        if(not filename):
            return None
        if(not filename in self.files or self.files[filename].change_count < view.change_count()):
            self.ParseFile(view)
        return self.files[filename]


refCache = NoWebRefCache()

def IsSourceBlockStartFence(view,row):
    line = view.getLine(row)
    return RE_SRC_BLOCK.search(line)

def IsSourceBlock(view,at=None):
    if(None == at):
        at = view.sel()[0].begin()
    return (view.match_selector(at,'orgmode.fence.sourceblock') or view.match_selector(at,'orgmode.sourceblock.content'))

def IsEndSourceBlock(view,at=None):
    if(None == at):
        at = view.sel()[0].begin()
    row,_ = view.rowcol(at)
    line = view.getLine(row)
    return RE_END.search(line)

# inline source blocks are inline with the text: src_python[:var x=5]{print('hello'+str(x))}
def IsInlineSourceBlock(view,at=None):
    if(None == at):
        at = view.sel()[0].begin()
    return (view.match_selector(at,'orgmode.sourceblock.inline') or view.match_selector(at,'orgmode.sourceblock.content.inline'))

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


def BuildFullParamList(cmd,language,cmdArgs,node=None):
    # First Add from global settings
    # First Add from PROPERTIES
    # Global properties are all controlled from our settings file.
    plist = PList.createPList()
    # The exclusion list forces replacement of keywords in the plist
    # Each of these are exclusive.
    # Collection
    plist.exList.AddList('results',['output','value'])
    # Type
    plist.exList.AddList('results',['table','vector','list','scalar','file', 'verbatim'])
    # Format
    plist.exList.AddList('results',['code','drawer','html','latex','link','graphics','org','pp','raw'])
    # Handling
    plist.exList.AddList('results',['silent','replace','prepend','append'])
    # Exports
    plist.exList.AddList('exports',['code','results','both','none', 'default'])
    plist.exList.AddBool('cache')
    plist.exList.AddBool('noweb')
    plist.exList.AddList('eval',['never','no','query','never-export','no-export','query-export'])
    defaultPlist = sets.Get("orgBabelDefaultHeaderArgs",":session none :results replace :exports default :cache no :noweb no")
    plist.AddFromPList(defaultPlist)
    view = None
    if(node == None):
        view = sublime.active_window().active_view()
    if(view or node):
        plist.AddFromPList(sets.Get('babel-args',None))
        plist.AddFromPList(sets.Get('babel-args-'+language,None))
        if(node == None):
            node = db.Get().AtPt(view,cmd.s)
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
    # At this point we have added all the global properties.
    # We need to check if there is a header block somewhere near us.
    if(node):
        header = node.get_comment("HEADER",None)
        if(header and view):
            # We have to scan for it!
            sr,_ = view.rowcol(cmd.s)
            for r in range(sr,node.start_row,-1):
                line = view.getLine(r)
                if(RE_HEADING.search(line) or RE_END.search(line) or RE_END_PROPERTY_DRAWER.search(line) or RE_TABLE.search(line)):
                    break
                m = RE_HEADER_PARAMS.search(line)
                if(m):
                    plist.AddFromPList(m.group('params'))
                    break
    plist.AddFromPList(cmdArgs)
    cmd.params = plist

# Determine the output handler to user from our parameters
def SetupOutputHandler(cmd,skipFile = False):
    res = cmd.params.GetStr('results','')
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

# Determine the output formatter to used based on our parameters
def SetupOutputFormatter(cmd):
    res = cmd.params.GetStr('results','')
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

def IsOutputEmpty(output):
    if(output == None):
        return True
    if(isinstance(output,str)):
        return output.strip() == ""
    if(isinstance(output,list)):
        if(len(output) == 0):
            return True
        for o in output:
            if(o.strip() != ""):
                return False
        return True
    return False

# We want to first build up the full list of vars
# from options, comments, properties and everything else
#
# Then any var we want to post process them so they become
# data sources that reference their various potential
# locations.
def ProcessPossibleSourceObjects(cmd,language,cmdArgs):
    #BuildFullParamList(cmd,language,cmdArgs)
    var = cmd.params.Get('var',None)
    cmd.deferedSources = 0
    hadDeferred = False
    if(var):
        for k in var:
            n = var[k]
            if(isinstance(n,tbl.Cell)):
                n = str(n)
                var[k] = n
            if(not util.numberCheck(n)):
                td = tbl.LookupTableFromNamedObject(n)
                if(td):
                    # I think it's better to just pass through the table here.
                    # Each language may want to do something very different and abstracting away
                    # What the data source actually is may actually be a disservice
                    #var[k] = GetGeneratorForTable(td,cmd.params)
                    var[k] = TableData(td)
                else:
                    l = lst.LookupNamedListInFile(n)
                    if(l):
                        var[k] = l
                    else:
                        pt = tbl.LookupNamedSourceBlockInFile(n)
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
        output = "#+begin_src html\n" + self.GetIndent() + output + "\n" + self.GetIndent() + "#+end_src"
        return (output,1)

class LatexFormatter(ResultsFormatter):
    def __init__(self,cmd):
        super(LatexFormatter,self).__init__(cmd)

    def FormatOutput(self,output):
        output = "#+begin_src latex\n" + self.GetIndent() + output + "\n" + self.GetIndent() + "#+end_src"
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
        self.isTable = False

    def FormatOutput(self, output):
        indent = "\n"+ self.GetIndent()
        output = indent.join(output).rstrip()
        if(IsOutputEmpty(output)):
            return output
        output,self.isTable = tbl.TableConversion(self.level,output)
        output = output.strip()
        return output

    def PostProcess(self, view, outPos, onDone):
        if(not self.cmd.CheckResultsFor('silent') and None == self.cmd.silent and self.isTable):
            view.sel().clear()
            view.sel().add(outPos)
            view.run_command("table_editor_align")
            sublime.set_timeout(onDone,1)
        else:
            sublime.set_timeout(onDone,1)



class OrgExecuteSourceBlockCommand(sublime_plugin.TextCommand):
    def run(self,edit, onDone=None, onDoneResultsPos=None,onDoneFnName=None,at=None,silent=None,onAdjustParams=None,skipSaveWarning=None,amExporting=False):
        value = str(uuid.uuid4())
        self.exc = OrgExecuteSourceBlock(self.view,value)
        self.exc.run(edit,onDone,onDoneResultsPos,onDoneFnName,at,silent,onAdjustParams,skipSaveWarning,amExporting)


def FormatParam(x):
    if(x.startswith("\"")):
        x = x[1:]
    if(x.endswith("\"")):
        x = x[:-1]
    return x

def GetDict(strData):
    rc = {}
    vals = strData.strip().split(',')
    for va in vals:
        if(va.strip() != ""):
            if("=" in va):
                k,v = va.strip().split('=')
                rc[k.strip()] = v.strip()
            else:
                log.error(" Params are not valid: " + str(va))
    return rc

def FindEndOfSourceBlock(view,row):
    end   = None
    erow  = view.endRow()
    for rw in range(row,erow+1):
        line = view.substr(view.line(view.text_point(rw,0)))
        if(RE_END.search(line)):
            end = rw
            break
    if(not end):
        log.error("Could not locate #+END_SRC tag")
        return None
    return end

def HasModule(fname):
    builtInModules = sets.Get("builtinSourceBlockHandlers",[])
    extensions = ext.find_extension_modules('orgsrc', builtInModules)
    aliases = sets.Get("builtinSourceBlockAliases",{})
    if(fname in aliases):
        fname = aliases[fname]
    return fname in extensions

def GetModule(fname):
    builtInModules = sets.Get("builtinSourceBlockHandlers",[])
    extensions = ext.find_extension_modules('orgsrc', builtInModules)
    aliases = sets.Get("builtinSourceBlockAliases",{})
    if(fname in aliases):
        fname = aliases[fname]
    return extensions[fname]

def GetModuleAndParams(view,row):
    pt = view.text_point(row,0)
    line = view.substr(view.line(pt))
    m = RE_SRC_BLOCK.search(line)
    if(not m):
        log.error("FAILED TO PARSE SOURCE BLOCK: @" + str(row) + " " + line + "\n" )
        log.debug("FAILURE AT:\n"+ '\n'.join(traceback.format_stack()))
        return (None, None, None)
    fnname = m.group('name')
    log.debug("SRC NAME: " + fnname)
    paramdata = line[len(m.group(0)):]
    # Now find me that function!
    if(not HasModule(fnname)):
        log.error("Function not found in src folder! Cannot execute!")
        return (None, None, None)
    return (fnname,paramdata,line)

RE_FUNCTION=re.compile(r'\s+[#][+][Cc][Aa][Ll][Ll][:]\s*(?P<name>[a-zA-Z][a-zA-Z0-9_-]+)\s*\((?P<params>[^)]*)\)')
def IsCallCommentBlock(view):
    line = view.substr(view.line(view.sel()[0]))
    return RE_FUNCTION.search(line)

class OrgExecuteCallCommentCommand(sublime_plugin.TextCommand):
    def run(self,edit,onDone=None):
        exc = ExecuteCallComment(self.view)
        exc.run(edit,onDone)

class ExecuteCallComment:
    def __init__(self,view):
        self.view = view

    def OnReplaced(self):
        evt.EmitIfParams(self.onDone)

    def OnDoneFunction(self,otherParams=None):
        if('postFormat' in otherParams):
            postFormat = otherParams['postFormat']
            self.view.run_command("org_internal_replace", {"start": self.resultsStartPt, "end": self.resultsEndPt, "text": postFormat,"onDone": evt.Make(self.OnReplaced)})

    def AdjustParams(self,otherParams=None):
        if('cmd' in otherParams):
            cmd = otherParams['cmd']
            self.cmd = cmd
            var = cmd.params.Get('var',None)
            if(var):
                for k in self.params:
                    var[k] = self.params[k]

    def run(self,edit, onDone=None):
        self.onDone = onDone
        # TODO: Parse Params
        self.sourcefns      = {}
        self.deferedSources = 0
        hasDeferred         = False
        reg = self.view.sel()[0]
        row,_ = self.view.rowcol(reg.begin())
        line = self.view.substr(self.view.line(reg))
        m = RE_FUNCTION.search(line)
        if(m):
            n = m.group('name')
            ps = m.group('params')
            self.params = GetDict(ps)
            pt = tbl.LookupNamedSourceBlockInFile(n)
            self.s = reg.begin()
            if(None != pt):
                self.startRow = row
                self.endRow   = row
                FindResults(self,edit,reg.begin(),False)
                if(not n in self.sourcefns):
                    self.deferedSources += 1
                    hadDeferred = True
                    self.sourcefns[n] = {'at': pt, 'name': n}
                    self.view.run_command('org_execute_source_block',{'at':pt, 'onDoneResultsPos': evt.Make(self.OnDoneFunction), 'onDoneFnName': n, 'onAdjustParams': evt.Make(self.AdjustParams), 'silent': True})

def EndResults(self,rw):
    self.endResults     = rw
    self.resultsStartPt = self.view.text_point(self.startResults+1,0)
    self.resultsEndPt   = self.view.text_point(self.endResults,0)
    self.resultsRegion  = sublime.Region(self.resultsStartPt, self.resultsEndPt)

def FindResults(self,edit,at,checkSilent=True):
    self.createdResults = False
    row              = self.endRow+1
    fileEndRow,_     = self.view.rowcol(self.view.size())
    inResults        = False
    inPropertyDrawer = False
    inBlock          = False
    m                = None
    self.resultsHash        = None
    for rw in range(row, fileEndRow):
        line = self.view.substr(self.view.line(self.view.text_point(rw,0)))
        if(not inResults):
            m = RE_RESULTS.search(line)
            if(m):
                self.resultsHash = m.group('hash')
                self.startResults = rw
                inResults = True
                continue
        if(RE_FUNCTION.search(line)):
            if(inResults):
                EndResults(self,rw)
                return True
            else:
                break
        # A new heading ends the results.
        if(RE_HEADING.search(line)):
            if(inResults):
                EndResults(self,rw)
                return True
            else:
                break
        if(RE_PROPERTY_DRAWER.search(line)):
            if(inResults and not inPropertyDrawer):
                inPropertyDrawer = True
                continue
            else:
                break
        if(RE_BLOCK.search(line)):
            if(inResults and not inBlock):
                inBlock = True
                continue
            else:
                break
        if(inResults and not inBlock and not inPropertyDrawer and inResults and RE_IS_BLANK_LINE.search(line)):
            EndResults(self,rw)
            return True
        if(inPropertyDrawer and RE_END_PROPERTY_DRAWER.search(line)):
            EndResults(self,rw+1)
            return True
        if(inBlock and RE_END_BLOCK.search(line)):
            EndResults(self,rw+1)
            return True
    # We just hit the end of the file.
    if(inResults):
        EndResults(self,fileEndRow)
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
        if(not checkSilent or not self.CheckResultsFor('silent') and self.silent == None and not self.CheckEval(('no','never'))):
            self.view.insert(edit, pt, "\n" +indent+ "#+RESULTS:\n")
        self.startResults   = self.endRow + 2 
        self.endResults     = self.startResults + 1
        self.resultsStartPt = self.view.text_point(self.startResults+1,0)
        self.resultsEndPt   = self.view.text_point(self.endResults,0)
        self.resultsRegion  = sublime.Region(self.resultsStartPt, self.resultsEndPt)
        self.createdResults = True
        return True
# ============================================================
class OrgExecuteSourceBlock:

    def __init__(self,view,id):
        self.id = id
        self.view = view

    def CheckResultsFor(self,val):
        res = self.params.Get('results',[])
        return (val in res)
    
    def CheckEval(self,val):
        evalParam = self.params.Get('eval',[])
        if(isinstance(val,list) or isinstance(val,tuple)):
            for x in val:
                if( x in evalParam):
                    return True
        else:
            if(val in evalParam):
                return True
        return False

    def OnDone(self):
        evt.EmitIf(self.onDone)
        if(self.silent != None):
            evt.EmitIfParams(self.onDoneResultsPos,postFormat=self.formattedOutput,preFormat=self.preFormattedOutput,name=self.onDoneFnName)
        else:
            self.resultsTxtStart = self.view.text_point(self.resultsTxtStartRow,self.resultsTxtStartCol)
            evt.EmitIfParams(self.onDoneResultsPos,pos=self.resultsTxtStart,name=self.onDoneFnName)

    def OnPostProcess(self):
        self.curPt = self.view.sel()[0]
        self.resultsTxtStart = self.view.text_point(self.resultsTxtStartRow,self.resultsTxtStartCol)
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

    def OnWarningSaved(self):
        if(self.view.is_dirty()):
            self.view.set_status("Error: ","Failed to save the view. ABORT, cannot execute source block since it is dirty")
            log.error("Failed to save the view. ABORT, cannot execute source code")
            return
        self.view.run_command("org_execute_source_block", {"onDone": self.onDone})

    def run(self, edit, onDone=None, onDoneResultsPos=None,onDoneFnName=None,at=None,silent=None,onAdjustParams=None,skipSaveWarning=None,amExporting=False):
        self.onDone = onDone
        self.onDoneResultsPos = onDoneResultsPos
        self.onDoneFnName=onDoneFnName
        self.silent = silent
        self.onAdjustParams = onAdjustParams
        self.amExporting = amExporting
        self.resultsTxtStartRow = 0
        self.resultsTxtStartCol = 0
        view = self.view
        if(at == None):
            at = view.sel()[0].begin()
        row = 0
        if(IsSourceBlock(view,at)):
            #if(view.match_selector(at,'orgmode.fence.sourceblock') or view.match_selector(at,'orgmode.sourceblock.content')):
            # Scan up till we find the start of the block.
            row,_ = view.rowcol(at)
            while(row > 0):
                if(IsSourceFence(view, row)):
                    at = sublime.Region(view.text_point(row,1),view.text_point(row,1))
                    break
                row -= 1
            # Okay we have a dynamic block, now we need to know where it ends.
            start = at
            end   = FindEndOfSourceBlock(view,row)
            if(not end):
                log.error("Could not find end of source block")
                self.OnDone()
                return

            # Okay now we have a start and end to build a region out of.
            # time to run a command and try to get the output.
            self.language, self.paramdata, fenceLine = GetModuleAndParams(view,row)
            if(not self.language):
                self.OnDone()
                return

            # Start setting up our execution state.
            self.curmod   = GetModule(self.language)
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
            if(not skipSaveWarning and view.is_dirty()):
                log.warning("Your source file has unsaved changes. We cannot run source modifications without saving the buffer.")
                view.run_command("save", {"async": False})
                sublime.set_timeout(self.OnWarningSaved,1)
                return
            BuildFullParamList(self,self.language,self.paramdata)
            # We need to find and or buid a results block
            # so we can replace it with the results.
            # ORG is super flexible about this, we are NOT!
            FindResults(self,edit,self.s)
            # TODO: Early out if this is a chain and we have already computed our
            #       results.
            self.source = None
            if(self.params.GetBool('noweb')):
                self.NoWebPhase()
            else:
                self.ParamsPhase()
        else:
            log.error("NOT in A Source Block, nothing to run, place cursor on first line of source block")

    # Each remote noweb call will hit this when complete. We integrate the results
    # back into our source block that we are constructing.
    def NoWebSourceDone(self,otherParams=None):
        self.deferredNoWeb -= 1
        name = otherParams['name']
        res = self.nowebfn[name]
        result = res['result']
        r      = res['r']
        idx    = res['idx']
        # Insert the output from our execution into our results
        if('preFormat' in otherParams):
            preFormat = otherParams['preFormat']
            result[idx] = preFormat
        # Paste our results into our source block where it belongs line by line
        if(len(result) > 0):
            self.source[r] = result[0]
            result = result[1:]
            if(len(result) > 0):
                for i in range(len(result)):
                    self.source.insert(r+i+1,result[i])
        # If this was the LAST source block executing then join up our source block
        # and prepare for the full parameters phase!
        if(self.deferredNoWeb <= 0):
            self.source = '\n'.join(self.source)
            self.ParamsPhase()
    
    # NoWeb <<my-function(x=1) calls another block but
    # with different params. This adjusts those params
    # during the remote call.
    def NoWebAdjustParams(self,otherParams=None):
        # Punch our noweb parameters into the remote blocks
        # parameter list!
        if('cmd' in otherParams):
            cmd = otherParams['cmd']
            var = cmd.params.Get('var',None)
            name = otherParams['name']
            if(var and name in self.nowebfn):
                res = self.nowebfn[name]
                ps  = res['ps']
                if(ps): 
                    params = GetDict(ps)
                    for k in params:
                        var[k] = params[k]

    # If the :noweb yes param is turned on 
    # Then we need to replace any <<NAME>> blocks
    # in our source code.
    def NoWebPhase(self):
        self.deferredNoWeb = 0
        self.nowebfn = {}
        sp = self.view.text_point(self.startRow,0)
        ep = self.view.line(self.view.text_point(self.endRow,0)).end()
        myRegion = sublime.Region(sp,ep)
        self.source = self.view.substr(self.region).split('\n')
        hadAnyDeferred = False
        for r in range(len(self.source)-1,-1,-1):
            txt = self.source[r]
            m = RE_NOWEB.search(txt)
            if(m):
                ps = m.group('params')
                if(None != ps):
                    continue
                nw = m.group('noweb')
                href = refCache.GetFile(self.view)
                ref = href.Find(nw)
                if(ref):
                    result = []
                    for rr in ref:
                        s = self.view.text_point(rr.start+1,0)
                        e = self.view.line(self.view.text_point(rr.end-1,0)).end()
                        if(myRegion.contains(s)):
                            continue
                        cpFrom = self.view.substr(sublime.Region(s,e))
                        result.append(cpFrom.rstrip())
                    if(len(result) > 0):
                        self.source[r] = result[0]
                        result = result[1:]
                        if(len(result) > 0):
                            for i in range(len(result)):
                                self.source.insert(r+i+1,result[i])
                else:
                    log.error(" NoWeb: No match for reference")
        for r in range(len(self.source)-1,-1,-1):
            txt = self.source[r]
            m = RE_NOWEB.search(txt)
            if(m):
                ps = m.group('params')
                if(ps == None):
                    continue
                href = refCache.GetFile(self.view)
                nw = m.group('noweb')
                ref = href.Find(nw)
                if(ref):
                    result = []
                    for rr in ref:
                        hadAnyDeferred = True
                        self.deferredNoWeb += 1
                        # Reserve a slot to insert into!
                        idx = len(result)
                        result.append("")
                        name = 'result_' + str(idx) + '_' + str(r)
                        self.nowebfn[name] = {'idx': idx, 'result': result,'r': r, 'ps': ps}
                        self.view.run_command('org_execute_source_block',{'at':rr.at, 'silent': True, 'onDoneResultsPos': evt.Make(self.NoWebSourceDone),"onAdjustParams": evt.Make(self.NoWebAdjustParams), 'onDoneFnName': name})
                else:
                    log.error(" NoWeb: No match for reference")
        if(not hadAnyDeferred):
            self.source = '\n'.join(self.source)
            self.ParamsPhase()

    # We have parameters BUT we do not have the full story
    # There are elements in there that may require deferred execution!
    #
    # Also these are OUR params not necessarily the ones from our caller if we are
    # being evaluated from a call.
    # 
    #   ParamPhase --> #+CALL::onAdjustParams() // set my params from your scope
    #
    #   ProcessPossibleSourceObjects --> Evaluate other source blocks
    #                                          |
    #            OnDoneFunction     <---------+
    def ParamsPhase(self):
            view = self.view
            # Turn our variable table into a dictionary
            var = self.params.GetDict('var',None)
            if(var):
                self.params.Replace('var',var)
            # If we are being called from elsewhere let the caller adjust our parameter list
            evt.EmitIfParams(self.onAdjustParams,cmd=self,name=self.onDoneFnName)
            # Setup formatting and parameters now that we have execution state. 
            if(ProcessPossibleSourceObjects(self,self.language,self.paramdata)):
                # We are deferred! We do not continue form here!
                return
            else:
                self.QueryCheckExecute()

    def AmExporting(self):
        return self.amExporting

    # We may not want to execute. This is a barrier to ACTUALLY executing this block!
    # We support querying the user and just bailing if need be.
    def QueryCheckExecute(self):
        if(self.CheckEval('query') or (self.CheckEval('query-export') and self.AmExporting())):
            if(sublime.DIALOG_YES == sublime.yes_no_cancel_dialog("Should we execute", "Yes Please", "No Thank You")):
                self.Execute()
            else:
                self.resultsTxtStartRow, self.resultsTxtStartCol = self.view.rowcol(self.resultsStartPt)
                self.OnDone()
        else:
            self.Execute()

    # Param() - paramters referencing other source blocks will call this back
    #           when evaluation is complete.
    def OnDoneFunction(self,otherParams=None):
        #results = otherParams['results']
        name    = otherParams['name']
        # Process the source here!
        var = self.params.Get('var',None) 
        fn = self.sourcefns[name]
        # Our goal is determine what is at results location
        # convert it and insert it into var.
        if('pos' in otherParams):
            pos = otherParams['pos']
            if(tbl.isTable(self.view,pos)):
                td = tbl.create_table(self.view, pos)
                var[fn['key']] = TableData(td)
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
            preFormat1 = preFormat.split('\n')
            preFormat = []
            for l in preFormat1:
                preFormat.append(l.strip())
            if(lst.isListLine(preFormat[0])):
                l = lst.ListData.CreateListFromList(preFormat)
                var[fn['key']] = l
            elif(tbl.isTableLine(preFormat[0])):
                td = TableData.ParseTable(preFormat)
                var[fn['key']] = td
            else:
                t = TextDef.CreateTextFromText(preFormat)
                l = "\n".join(t.lines)
                l = l.strip()
                var[fn['key']] = l
            pass
        # TODO: Handle lists, text and other things.
        self.deferedSources -= 1
        if(self.deferedSources <= 0):
            FindResults(self,0,self.s)
            self.QueryCheckExecute()

    def OnCached(self):
        self.formattedOutput    = self.view.substr(self.resultsRegion)
        self.preFormattedOutput = self.formattedOutput
        res = self.formattedOutput.split('\n')
        if(len(res) >= 2):
            if(re.search(r"\s*(([:]results[:])|[#][+]begin_)",res[0])):
                self.preFormattedOutput = '\n'.join(res[1:-1])
        ## Keep track of this so we know where we are inserting the text.
        self.OnReplaced()

    def Execute(self):
            view = self.view
            self.outHandler   = SetupOutputHandler(self)
            self.outFormatter = SetupOutputFormatter(self)
            self.hashVal      = None
            # Compute our expected results location. We may need to adjust
            # it based on formatting later though.
            n                 = db.Get().AtPt(view,self.s)
            self.level        = n.level
            self.resultsTxtStartRow, self.resultsTxtStartCol = self.view.rowcol(self.resultsStartPt + self.level + 1)

            # If we have a never eval param this block is NOT ALLOWED
            # to be executed! So we bail!
            if(self.CheckEval(('no','never'))):
                self.OnDone()
                return

            # Run the "writer"
            self.outputs = "Did not execute, something is wrong!"
            if(hasattr(self.curmod,"Execute")):
                # Okay now time to replace the contents of the block
                if(self.source == None):
                    self.source = view.substr(self.region)
                if(hasattr(self.curmod,"PreProcessSourceFile")):
                    self.curmod.PreProcessSourceFile(self)
                if(self.params.GetBool('cache')):
                    self.hashVal = hashlib.sha1(bytes(self.source,'utf-8')).hexdigest()
                    if(self.hashVal == self.resultsHash):
                        log.warning(' Hash matches, skipping execution')
                        self.OnCached()
                        return
                    #print(self.hashVal)
                # Is this a file backed execution?
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
                # This is an inline execution
                else:
                    self.filename = None
                    self.outputs = self.curmod.Execute(self,sets)
                log.debug("OUTPUT: " + str(self.outputs))
            else:
                log.error("No execute in module, abort")
                return
            # Reformat adding indents to each line!
            # No bad formatting allowed!
            self.outHandler.SetIndent(n.level)
            if(self.outFormatter):
                self.outFormatter.SetIndent(n.level)
            output = self.outHandler.FormatOutput(self.outputs)
            self.preFormattedOutput = output
            rowadjust = 0
            if(self.outFormatter):
                output,rowadjust = self.outFormatter.FormatOutput(output)
            # If our formatter wrapped us we have to adjust our text point for post processing
            # and results text.
            if(rowadjust > 0):
                self.resultsTxtStartRow += rowadjust
            ## Keep track of this so we know where we are inserting the text.
            self.formattedOutput = (" " * self.level + " ") + output+'\n'
            if(self.CheckResultsFor('silent') or self.silent == True):
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
                # Hash means we have to update the hash!
                if(self.hashVal):
                    row,col = view.rowcol(self.resultsStartPt)
                    row -= 1
                    self.resultsStartPt = view.text_point(row,col)
                    self.formattedOutput = (" " * self.level + " ") + "#+RESULTS[{}]:\n".format(self.hashVal) + self.formattedOutput
                self.view.run_command("org_internal_replace", {"start": self.resultsStartPt, "end": self.resultsEndPt, "text": self.formattedOutput,"onDone": evt.Make(self.OnReplaced)})

# ============================================================
class OrgExecuteInlineSourceBlock:

    def __init__(self,view,id):
        self.id = id
        self.view = view

    def FindInlineResults(self):
        self.startResults   = self.row
        self.endResults     = self.row
        if(self.m.group('resblock')):
            self.resultsStartPt = self.view.text_point(self.row, self.m.start('resblock'))
            self.resultsEndPt   = self.view.text_point(self.row, self.m.end('resblock'))
            self.resultsRegion  = sublime.Region(self.resultsStartPt, self.resultsEndPt)
            self.createdResults = False
        else:
            self.resultsStartPt = self.view.text_point(self.row, self.m.end('code') + 1)
            self.resultsEndPt   = self.view.text_point(self.row, self.m.end('code') + 1)
            self.resultsRegion  = sublime.Region(self.resultsStartPt, self.resultsEndPt)
            self.createdResults = True

    def CheckResultsFor(self,val):
        res = self.params.Get('results',[])
        return (val in res)

    def OnDone(self):
        evt.EmitIf(self.onDone)
        if(self.silent != None):
            evt.EmitIfParams(self.onDoneResultsPos,postFormat=self.formattedOutput,preFormat=self.preFormattedOutput,name=self.onDoneFnName)
        else:
            self.resultsTxtStart = self.view.text_point(self.resultsTxtStartRow,self.resultsTxtStartCol)
            evt.EmitIfParams(self.onDoneResultsPos,pos=self.resultsTxtStart,name=self.onDoneFnName)

    def OnPostProcess(self):
        self.curPt = self.view.sel()[0]
        self.resultsTxtStart = self.view.text_point(self.resultsTxtStartRow,self.resultsTxtStartCol)
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

    def OnWarningSaved(self):
        if(self.view.is_dirty()):
            self.view.set_status("Error: ","Failed to save the view. ABORT, cannot execute source block since it is dirty")
            log.error("Failed to save the view. ABORT, cannot execute source code")
            return
        self.view.run_command("org_execute_inline_source_block", {"onDone": self.onDone})

    def run(self, edit, onDone=None, onDoneResultsPos=None,onDoneFnName=None,at=None,silent=None,onAdjustParams=None,skipSaveWarning=None):
        self.onDone           = onDone
        self.onDoneResultsPos = onDoneResultsPos
        self.onDoneFnName     =onDoneFnName
        self.silent = silent
        self.onAdjustParams = onAdjustParams
        view = self.view
        if(at == None):
            at = view.sel()[0].begin()
        if(IsInlineSourceBlock(view,at)):
            # Scan up till we find the start of the block.
            row,col = view.rowcol(at)
            line = view.getLine(row)
            self.m = None
            for tm in RE_INL_SRC_BLOCK.finditer(line):
                if(tm.start('block') <= col and tm.end('block') >= col):
                    self.m = tm
                    break
            if(self.m == None):
                log.warning("Failed to execute inline script block could not locate bounds")
                return
            
            start = self.m.start('code')
            end   = self.m.end('code') 

            self.paramdata = tm.group('params')
            self.language  = tm.group('name')
            self.row       = row

            # Okay now we have a start and end to build a region out of.
            # time to run a command and try to get the output.
            if(not HasModule(self.language)):
                log.error("Function not found in src folder! Cannot execute!")
                self.OnDone()
                return

            # Start setting up our execution state.
            self.curmod   = GetModule(self.language)
            self.startRow = row
            self.endRow   = row
            self.s        = view.text_point(row,start)
            self.e        = view.text_point(row,end)
            self.region   = sublime.Region(self.s,self.e)
            self.sourcefile = view.file_name()
            self.sourcefns = {}
            # Sanity check that the file exists on disk
            if(not self.sourcefile or not os.path.exists(self.sourcefile)):
                self.view.set_status("Error: ","Your source org file must exist on disk. ABORT.")
                log.error("Your source org file must exist on disk to generate images. The path is used when setting up relative paths.")
                self.OnDone()
                return
            if(not skipSaveWarning and view.is_dirty()):
                log.warning("Your source file has unsaved changes. We cannot run source modifications without saving the buffer.")
                view.run_command("save", {"async": False})
                sublime.set_timeout(self.OnWarningSaved,1)
                return
            BuildFullParamList(self,self.language,self.paramdata)
            # We need to find and or buid a results block
            # so we can replace it with the results.
            # ORG is super flexible about this, we are NOT!
            self.FindInlineResults()
            self.ParamsPhase()
        else:
            log.error("NOT in A Source Block, nothing to run, place cursor on first line of source block")

    # We have parameters BUT we do not have the full story
    # There are elements in there that may require deferred execution!
    #
    # Also these are OUR params not necessarily the ones from our caller if we are
    # being evaluated from a call.
    # 
    #   ParamPhase --> #+CALL::onAdjustParams() // set my params from your scope
    #
    #   ProcessPossibleSourceObjects --> Evaluate other source blocks
    #                                          |
    #            OnDoneFunction     <---------+
    def ParamsPhase(self):
            view = self.view
            # Turn our variable table into a dictionary
            var = self.params.GetDict('var',None)
            if(var):
                self.params.Replace('var',var)
            # If we are being called from elsewhere let the caller adjust our parameter list
            evt.EmitIfParams(self.onAdjustParams,cmd=self)
            # Setup formatting and parameters now that we have execution state. 
            if(ProcessPossibleSourceObjects(self,self.language,self.paramdata)):
                # We are deferred! We do not continue form here!
                return
            else:
                self.Execute()
    # Param() - paramters referencing other source blocks will call this back
    #           when evaluation is complete.
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
                var[fn['key']] = TableData(td)
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
            preFormat1 = preFormat.split('\n')
            preFormat = []
            for l in preFormat1:
                preFormat.append(l.strip())
            if(lst.isListLine(preFormat[0])):
                l = lst.ListData.CreateListFromList(preFormat)
                var[fn['key']] = l
            elif(tbl.isTableLine(preFormat[0])):
                td = TableData.ParseTable(preFormat)
                var[fn['key']] = td
            else:
                t = TextDef.CreateTextFromText(preFormat)
                l = "\n".join(t.lines)
                l = l.strip()
                var[fn['key']] = l
            pass
        # TODO: Handle lists, text and other things.
        self.deferedSources -= 1
        if(self.deferedSources <= 0):
            self.FindInlineResults()
            self.Execute()
    def Execute(self):
            view = self.view
            self.outHandler   = RawHandler(self, self.params)

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
            self.level = 0
            self.outHandler.SetIndent(0)
            output = self.outHandler.FormatOutput(self.outputs)
            self.preFormattedOutput = output
            self.resultsTxtStartRow,self.resultsTxtStartCol = self.view.rowcol(self.resultsStartPt)
            self.resultsTxtStart = self.resultsStartPt
            self.formattedOutput = " {{{results(=" + output.replace("\n","") + "=)}}} "
            if(self.CheckResultsFor('silent') or self.silent == True):
                # We only echo to the console in silent mode.
                print(str(output))
                self.silent = True
                self.OnReplaced()
            # We only support replace mode for inline source blocks
            self.view.run_command("org_internal_replace", {"start": self.resultsStartPt, "end": self.resultsEndPt, "text": self.formattedOutput,"onDone": evt.Make(self.OnReplaced)})

# ================================================================================
class OrgExecuteInlineSourceBlockCommand(sublime_plugin.TextCommand):
    def run(self,edit, onDone=None, onDoneResultsPos=None,onDoneFnName=None,at=None,silent=None,onAdjustParams=None,skipSaveWarning=None):
        value = str(uuid.uuid4())
        self.exc = OrgExecuteInlineSourceBlock(self.view,value)
        self.exc.run(edit,onDone,onDoneResultsPos,onDoneFnName,at,silent,onAdjustParams,skipSaveWarning)

# ================================================================================
class OrgExecuteAllSourceBlocksCommand(sublime_plugin.TextCommand):
    def ContinueRun(self):
        # I have to go bottom to top 
        for r in range(self.cur,0,-1):
            self.cur = r
            pt = self.view.text_point(r,0)
            line = self.view.line(pt)
            txt = self.view.substr(line)
            if(self.inBlock and IsSourceBlockStartFence(self.view,r)):
                self.cur -= 1
                self.view.run_command('org_execute_source_block',{"at":pt,"onDone":evt.Make(self.ContinueRun),"amExporting":self.amExporting,"skipSaveWarning": True})
                self.inBlock = False
                break
            elif(not self.inBlock and IsEndSourceBlock(self.view,pt)):
                self.inBlock = True
        if(self.cur <= 1):
            evt.EmitIf(self.onDone)

    def run(self,edit,at=None,onDone=None,amExporting=False):
        # Do we want to avoid re-execution?
        self.last_row = self.view.endRow()
        self.cur = self.last_row
        self.inBlock = False
        self.onDone = onDone
        self.amExporting = amExporting
        self.ContinueRun()



# ================================================================================
class OrgTangleFileCommand(sublime_plugin.TextCommand):
    def OnDone(self):
        evt.EmitIf(self.onDone)

    def CheckResultsFor(self,val):
        res = self.params.Get('results',[])
        return (val in res)

    def ParseFile(self,at):
        view = self.view
        if(IsSourceBlock(view,at)):
            filename = self.view.file_name()

            # Okay we have a dynamic block, now we need to know where it ends.
            start   = at
            row,col = view.rowcol(at)
            end = FindEndOfSourceBlock(view,row)
            if(not end):
                return
            # Okay now we have a start and end to build a region out of.
            # time to run a command and try to get the output.
            self.language, self.paramdata, fenceLine = GetModuleAndParams(view,row)
            if(not self.language):
                return

            log.debug(" TANGLE: {}".format(fenceLine))

            # Start setting up our execution state.
            self.curmod   = GetModule(self.language)
            self.startRow = row + 1
            self.endRow   = end
            self.s        = view.text_point(self.startRow,0)
            self.e        = view.text_point(self.endRow,0)
            self.region   = sublime.Region(self.s,self.e)
            self.sourcefile = view.file_name()
            self.sourcefns = {}
            # We mark as silent so we don't execute here.
            self.silent    = True
            BuildFullParamList(self,self.language,self.paramdata)
            #FindResults(self,edit,self.s)
            var = self.params.GetDict('var',None)
            if(var):
                self.params.Replace('var',var)
            #if(self.CheckEval(('no','never'))):
            #    return
            if(not self.params.Get('tangle',None) or not self.params.GetBool('tangle')):
                return
            # Run the "writer"
            if(hasattr(self.curmod,"Execute")):
                # Okay now time to replace the contents of the block
                self.source = view.substr(self.region)
                self.source = re.sub(r"^(\s+)(.*)$",
                    lambda m: re.sub("^" + " "*len(m.group(1)),"",m.group(2),flags=re.MULTILINE)
                    ,self.source,flags=re.MULTILINE|re.DOTALL)
                if(hasattr(self.curmod,"PreProcessSourceFile")):
                    self.curmod.PreProcessSourceFile(self)
                # Is this a file backed execution?
                if(hasattr(self.curmod,"Extension")):
                    filename = os.path.splitext(filename)[0]+self.curmod.Extension(self)
                    try:
                        if(hasattr(self.curmod,"WrapStart")):
                            self.source = ((self.curmod.WrapStart(self) + "\n").encode("ascii")) + self.source
                        if(hasattr(self.curmod,"WrapEnd")):
                            self.source += (("\n" + self.curmod.WrapEnd(self)).encode("ascii"))
                    except:
                        log.debug(" " + traceback.format_exc())
                else:
                    filename = os.path.splitext(filename)[0]+".py"
                comStart = None
                if(hasattr(self.curmod,"LineCommentPrefix")):
                    comStart = self.curmod.LineCommentPrefix()
                    temp = "\n{} -- Line: {}\n".format(comStart,str(self.startRow))
                    self.source = temp + self.source

                if(not filename in self.fileData):
                    if(comStart):
                        dt = datetime.datetime.now()
                        dateString = dt.strftime("%Y %m %d %a %H:%M")
                        temp = "{} Generated From: {}\n{} Author: {}\n{} Date: {}\n".format(comStart,view.file_name(),comStart,getpass.getuser(),comStart,dateString)
                        self.source = temp + self.source
                    self.fileData[filename] = self.source
                else:
                    self.fileData[filename] += self.source
                #log.debug("TANGLE: " + str(self.source)
        else:
            log.error("NOT in A Source Block, nothing to run, place cursor on first line of source block")

    def ContinueRun(self):
        for r in range(self.cur,self.last_row):
            self.cur = r
            pt = self.view.text_point(r,1)
            if(not self.inBlock and IsSourceBlock(self.view,pt)):
                self.ParseFile(pt)
                self.inBlock = True
                continue
            elif(self.inBlock and IsEndSourceBlock(self.view,pt)):
                self.inBlock = False
        for filename in self.fileData:
            with open(filename,"w") as f:
                f.write(self.fileData[filename])
                #print("WROTE: " + filename)
        if(self.cur >= self.last_row):
            self.OnDone()

    def run(self,edit,onDone=None):
        self.fileData = {}
        self.onDone = onDone
        self.last_row = self.view.endRow()
        self.cur = 0
        self.inBlock = False
        self.ContinueRun()

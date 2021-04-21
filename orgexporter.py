import sublime
import sublime_plugin
import re
import regex
from pathlib import Path
import os
import fnmatch
import logging
import sys
import traceback 
import OrgExtended.asettings as sets
import OrgExtended.orgdb as db
import OrgExtended.orgparse.date as date

log = logging.getLogger(__name__)

RE_TITLE = regex.compile(r"^\s*[#][+](TITLE|title)[:]\s*(?P<data>.*)")
RE_AUTHOR = regex.compile(r"^\s*[#][+](AUTHOR|author)[:]\s*(?P<data>.*)")
RE_NAME = regex.compile(r"^\s*[#][+](NAME|name)[:]\s*(?P<data>.*)")
RE_DATE = regex.compile(r"^\s*[#][+](DATE|date)[:]\s*(?P<data>.*)")
RE_EMAIL = regex.compile(r"^\s*[#][+](EMAIL|email)[:]\s*(?P<data>.*)")
RE_LANGUAGE = regex.compile(r"^\s*[#][+](LANGUAGE|language)[:]\s*(?P<data>.*)")



def ExportFilename(view,extension,suffix=""):
    fn = view.file_name()
    fn,ext = os.path.splitext(fn)
    return fn + suffix + extension

def GetGlobalOption(file, name, settingsName, defaultValue):
    value = sets.Get(settingsName, defaultValue)
    value = ' '.join(file.org[0].get_comment(name, [str(value)]))
    return value


class OrgExporter:

    def __init__(self,filename,file,**kwargs):
        self.file = file
        self.fs   = open(filename,"w",encoding="utf-8")
        self.outputFilename = filename
        self.InitExportComments()
        self.PreScan()

    def InitExportComments(self):
        self.title    = None
        self.author   = None
        self.language = None
        self.email    = None
        self.date     = None
        self.name     = None

    def GetOption(self,name,settingsName,defaultValue):
        return GetGlobalOption(self.file, name, settingsName, defaultValue)

    def PreScanExportCommentsGather(self, l):
        m = RE_TITLE.match(l)
        if(m):
            self.title = m.captures('data')[0]
            return True
        m = RE_AUTHOR.match(l)
        if(m):
            self.author = m.captures('data')[0]
            return True
        m = RE_LANGUAGE.match(l)
        if(m):
            self.language = m.captures('data')[0]
            return True
        m = RE_EMAIL.match(l)
        if(m):
            self.email = m.captures('data')[0]
            return True
        m = RE_DATE.match(l)
        if(m):
            self.date = m.captures('data')[0]
            return True
        m = RE_NAME.match(l)
        if(m):
            self.name = m.captures('data')[0]
            return True

    # Called at the start of export to scan the file for game changing properties
    def PreScan(self):
        for l in self.file.org._lines:
            self.PreScanExportCommentsGather(l)
            self.PreScanCustom(l)
        self.PostPreScanCustom()
    
    # This is called when the document is being destroyed
    def Close(self):
        self.FinishDocCustom()
        self.fs.close()

    # Override this to add to the pre-scan phase
    def PreScanCustom(self,l):
        pass

    # Called after the pre scan is complete
    def PostPreScanCustom(self):
        pass

    # Override this to close off the document for exporting
    def FinishDocCustom(self):
        pass


    # Document header metadata should go in here
    def AddExportMetaCustom(self):
        pass

    # Setup to start the export of a node
    def StartNode(self, n):
        pass 

    # Export the heading of this node
    def NodeHeading(self,n):
        pass

    # We are about to start exporting the nodes body
    def StartNodeBody(self,n):
        pass

    # Actually buid the node body in the document
    def NodeBody(self,n):
        pass

    # We are done exporting the nodes body so finish it off
    def EndNodeBody(self,n):
        pass

    # We are now done the node itself so finish that off
    def EndNode(self,n):
        pass

    # def about to start exporting nodes
    def StartNodes(self):
        pass

    # done exporting nodes
    def EndNodes(self):
        pass

    def StartDocument(self, file):
        pass

    def EndDocument(self):
        pass

    def InsertScripts(self,file):
        pass

    def StartHead(self):
        pass

    def EndHead(self):
        pass

    def StartBody(self):
        pass

    def EndBody(self):
        pass


class OrgExportHelper:

    def __init__(self,view,index):
        self.view = view
        self.file = db.Get().FindInfo(self.view)
        self.index = index


    # Extend this for this format
    def CustomBuildHead(self):
        pass

    def BuildHead(self):
        self.CustomBuildHead()
        self.doc.AddExportMetaCustom()

    def BuildNode(self, n):
        self.doc.StartNode(n)
        self.doc.NodeHeading(n)
        self.doc.StartNodeBody(n)
        self.doc.NodeBody(n)
        for c in n.children:
            self.BuildNode(c)
        self.doc.EndNodeBody(n)
        self.doc.EndNode(n)

    def BuildNodes(self):
        if(self.index == None):
            nodes = self.file.org
            for n in nodes.children:
                self.BuildNode(n)
        else:
            n = self.file.org.env._nodes[self.index]
            self.BuildNode(n)

    def BuildDocument(self):
        self.doc.StartNodes()
        self.BuildNodes()
        self.doc.EndNodes()

    def BuildBody(self):
        self.doc.StartDocument(self.file)
        self.BuildDocument()
        self.doc.EndDocument()
        self.doc.InsertScripts(self.file)

    def Run(self,outputFilename,doc):
        try:
            self.doc = doc
            self.doc.StartHead()
            self.BuildHead()
            self.doc.EndHead()

            self.doc.StartBody()
            self.BuildBody()
            self.doc.EndBody()
        finally:    
            if(None != self.doc):
                self.doc.Close()
            log.log(51,"EXPORT COMPLETE: " + str(outputFilename))
            self.view.set_status("ORG_EXPORT","EXPORT COMPLETE: " + str(outputFilename))
            sublime.set_timeout(self.ClearStatus, 1000*10)

    def ClearStatus(self):
        self.view.set_status("ORG_EXPORT","")



class BlockState:
    def __init__(self,startre,endre,doc,exportEndLine=False):
        self.startre      = startre
        self.endre        = endre
        self.e            = doc
        self.exportEndLine = exportEndLine
    def Handle(self, lines, orgnode):
        amIn = False
        for line in lines:
            if(amIn):
                m = self.endre.search(line)
                if(m):
                    amIn = False
                    self.e.SetAmInBlock(False)
                    self.HandleExiting(m,line,orgnode)
                    if(self.exportEndLine):
                        yield line
                    continue
                else:
                    self.HandleIn(line,orgnode)
                    continue
            else:
                if(not self.e.AmInBlock()):
                    m = self.startre.search(line)
                    if(m):
                        amIn = True
                        self.e.SetAmInBlock(True)
                        self.HandleEntering(m,line,orgnode)
                        continue
                yield line
        if(amIn):
            amIn = False
            self.e.SetAmInBlock(False)
            self.HandleExiting(None,None,orgnode)
    def HandleIn(self, line, orgnode):
        pass
    def HandleExiting(self, m, line, orgnode):
        pass
    def HandleEntering(self, m, line, orgnode):
        pass 

class ListBlockState:
    def __init__(self,listre,doc):
        self.listre      = listre
        self.e           = doc
    def Handle(self, lines, orgnode):
        inList    = 0
        curIndent = 0
        for l in lines:
            m = self.listre.search(l)
            if(m):
                thisIndent = len(m.group('indent'))
                if(not inList):
                    if(not self.e.AmInBlock()):
                        curIndent = thisIndent
                        self.HandleEntering(m,l,orgnode)
                        inList += 1
                    else:
                        yield l
                        continue
                elif(thisIndent > curIndent):
                    curIndent = thisIndent
                    self.HandleEntering(m,l,orgnode)
                    inList += 1
                elif(thisIndent < curIndent and inList > 1):
                    inList -= 1
                    self.HandleExiting(m,l,orgnode)
                self.HandleItem(m,l,orgnode)
                continue
            elif(inList):
                while(inList > 0):
                    inList -= 1
                    self.HandleExiting(m,l,orgnode)
                yield l
            else:
                yield l
        while(inList > 0):
            inList -= 1
            self.HandleExiting(m,l,orgnode)
    def HandleItem(self, m, line, orgnode):
        pass
    def HandleExiting(self, m, line, orgnode):
        pass
    def HandleEntering(self, m, line, orgnode):
        pass 

class AttributeParser:
    def __init__(self,name,sre,doc):
        self.sre      = sre
        self.name     = name
        self.e        = doc
    def Handle(self, lines, orgnode):
        for line in lines:
            m = self.sre.search(line)
            if(m):
                self.HandleData(m,line,orgnode)
                continue
            yield line
    def HandleData(self, m, line, orgnode):
        self.e.AddAttrib(self.name,m.group('data'))

class StripParser:
    def __init__(self,sre,doc):
        self.sre      = sre
        self.e        = doc
    def Handle(self, lines, orgnode):
        for line in lines:
            m = self.sre.search(line)
            if(m):
                continue
            yield line

# This parser expects the item to live and consume the entire line
# Match will replace the entire line
class LineParser:
    def __init__(self,sre,doc):
        self.sre      = sre
        self.e        = doc
    def Handle(self, lines, orgnode):
        for line in lines:
            m = self.sre.search(line)
            if(m):
                self.HandleLine(m,line,orgnode)
                continue
            yield line
    def HandleLine(self,m,l,orgnode):
        pass
# This parser expects a match to be "within" a line.
# This is complicated because we may still have to foward off
# the other portions of the line 
class SubLineParser:
    def __init__(self,sre,doc):
        self.sre      = sre
        self.e        = doc
    def Handle(self, lines, orgnode):
        for line in lines:
            start = 0
            llen = len(self.e.doc)
            for m in self.sre.finditer(line):
                s,e = m.span()
                if(s >= start):
                    segment = line[start:s]
                    yield segment
                    start = e
                self.HandleSegment(m,line,orgnode)
            if(start != 0 and len(line) > start):
                segment = line[start:]
                yield segment
            elif(start == 0):
                yield line
            # We generated more than one line here! need to collapse
            nlen = len(self.e.doc) - llen
            if(nlen > 1):
                ls = "".join(self.e.doc[llen:])
                del self.e.doc[-nlen:]
                self.e.doc.append(ls)
    def HandleSegment(self,m,l,orgnode):
        pass

RE_STARTSRC = re.compile(r"^\s*#\+(BEGIN_SRC|begin_src)\s+(?P<lang>[a-zA-Z0-9]+)")
RE_ENDSRC = re.compile(r"^\s*#\+(END_SRC|end_src)")

class SourceBlockState(BlockState):
    def __init__(self,doc):
        super(SourceBlockState,self).__init__(RE_STARTSRC, RE_ENDSRC,doc)

RE_STARTDYN = re.compile(r"^\s*#\+(BEGIN[:]|begin[:])\s+(?P<lang>[a-zA-Z0-9]+)")
RE_ENDDYN = re.compile(r"^\s*#\+(end[:]|END[:])")

class DynamicBlockState(BlockState):
    def __init__(self,doc):
        super(DynamicBlockState,self).__init__(RE_STARTDYN, RE_ENDDYN,doc)

RE_STARTEXPORT = re.compile(r"^\s*#\+(BEGIN_EXPORT|begin_export)\s+(?P<lang>[a-zA-Z0-9]+)")
RE_ENDEXPORT = re.compile(r"^\s*#\+(END_EXPORT|end_export)")

class ExportBlockState(BlockState):
    def __init__(self,doc):
        super(ExportBlockState,self).__init__(RE_STARTEXPORT, RE_ENDEXPORT,doc)

RE_STARTQUOTE = re.compile(r"^\s*#\+(BEGIN_QUOTE|begin_quote)")
RE_ENDQUOTE = re.compile(r"^\s*#\+(END_QUOTE|end_quote)")

class QuoteBlockState(BlockState):
    def __init__(self,doc):
        super(QuoteBlockState,self).__init__(RE_STARTQUOTE, RE_ENDQUOTE,doc)

RE_STARTEXAMPLE = re.compile(r"^\s*#\+(BEGIN_EXAMPLE|begin_example)")
RE_ENDEXAMPLE = re.compile(r"^\s*#\+(END_EXAMPLE|end_example)")

class ExampleBlockState(BlockState):
    def __init__(self,doc):
        super(ExampleBlockState,self).__init__(RE_STARTEXAMPLE, RE_ENDEXAMPLE,doc)

RE_STARTGENERIC = re.compile(r"#\+(BEGIN_|begin_)(?P<data>[a-zA-Z0-9-]+)(\s|$)")
RE_ENDGENERIC   = re.compile(r"#\+(END_|end_)([a-zA-Z0-9-]+)(\s|$)")

class GenericBlockState(BlockState):
    def __init__(self,doc):
        super(GenericBlockState,self).__init__(RE_STARTGENERIC, RE_ENDGENERIC,doc)

RE_TABLE_ROW = re.compile(r"^\s*[|]")
RE_NOT_TABLE_ROW = re.compile(r"^\s*[^| ]")

class TableBlockState(BlockState):
    def __init__(self,doc):
        super(TableBlockState,self).__init__(RE_TABLE_ROW, RE_NOT_TABLE_ROW,doc,True)

RE_DRAWER_LINE = re.compile(r"^\s*[:].+[:]\s*$")
RE_END_DRAWER_LINE = re.compile(r"^\s*[:](END|end)[:]\s*$")
class DrawerBlockState(BlockState):
    def __init__(self,doc):
        super(DrawerBlockState,self).__init__(RE_DRAWER_LINE, RE_END_DRAWER_LINE,doc)

RE_CAPTION = regex.compile(r"^\s*[#][+]CAPTION[:]\s*(?P<data>.*)")
class CaptionAttributeParser(AttributeParser):
    def __init__(self,doc):
        super(CaptionAttributeParser,self).__init__('caption',RE_CAPTION,doc)

RE_TBLFM = regex.compile(r"^\s*[#][+]TBLFM[:].*")
class TblFmStripper(StripParser):
    def __init__(self,doc):
        super(TblFmStripper,self).__init__(RE_TBLFM,doc)

RE_ATTR_HTML = re.compile(r"^\s*[#][+](ATTR_HTML|attr_html)[:].*")
class AttrHtmlStripper(StripParser):
    def __init__(self,doc):
        super(AttrHtmlStripper,self).__init__(RE_ATTR_HTML,doc)

RE_ATTR_ORG = re.compile(r"^\s*[#][+](ATTR_ORG|attr_org)[:].*")
class AttrOrgStripper(StripParser):
    def __init__(self,doc):
        super(AttrOrgStripper,self).__init__(RE_ATTR_ORG,doc)

RE_KEYWORDSTRIP = re.compile(r"^\s*[#][+](PRIORITIES|priorities|PLOT|plot)[:].*")
class KeywordStripper(StripParser):
    def __init__(self,doc):
        super(KeywordStripper,self).__init__(RE_KEYWORDSTRIP,doc)

RE_SCHEDULING_LINE = re.compile(r"^\s*(SCHEDULED|CLOSED|DEADLINE|CLOCK)[:].*")
class SchedulingStripper(StripParser):
    def __init__(self,doc):
        super(SchedulingStripper,self).__init__(RE_SCHEDULING_LINE,doc)

RE_UL   = re.compile(r"^(?P<indent>\s*)(-|[+])\s+(?P<data>.+)")
class UnorderedListBlockState(ListBlockState):
    def __init__(self,doc):
        super(UnorderedListBlockState,self).__init__(RE_UL,doc)

RE_CL   = re.compile(r"^(?P<indent>\s*)(-|[+])\s+\[(?P<state>[ xX-])\]\s+(?P<data>.+)")
class CheckboxListBlockState(ListBlockState):
    def __init__(self,doc):
        super(CheckboxListBlockState,self).__init__(RE_CL,doc)

RE_OL   = re.compile(r"^(?P<indent>\s*)[0-9]+[).]\s+(?P<data>.+)")
class OrderedListBlockState(ListBlockState):
    def __init__(self,doc):
        super(OrderedListBlockState,self).__init__(RE_OL,doc)


RE_BOLD = re.compile(r"\*(?P<data>.+?)\*")
RE_ITALICS = re.compile(r"/(?P<data>.+?)/")
RE_UNDERLINE = re.compile(r"[_](?P<data>.+?)[_]")
RE_STRIKETHROUGH = re.compile(r"\+(?P<data>.+?)\+")
RE_CODE = re.compile(r"~(?P<data>.+?)~")
RE_VERBATIM = re.compile(r"=(?P<data>.+?)=")

class BoldParser(SubLineParser):
    def __init__(self,doc):
        super(BoldParser,self).__init__(RE_BOLD,doc)

class ItalicsParser(SubLineParser):
    def __init__(self,doc):
        super(ItalicsParser,self).__init__(RE_ITALICS,doc)

class UnderlineParser(SubLineParser):
    def __init__(self,doc):
        super(UnderlineParser,self).__init__(RE_UNDERLINE,doc)

class StrikethroughParser(SubLineParser):
    def __init__(self,doc):
        super(StrikethroughParser,self).__init__(RE_STRIKETHROUGH,doc)

class CodeParser(SubLineParser):
    def __init__(self,doc):
        super(CodeParser,self).__init__(RE_CODE,doc)

class VerbatimParser(SubLineParser):
    def __init__(self,doc):
        super(VerbatimParser,self).__init__(RE_VERBATIM,doc)

RE_LINK = re.compile(r"\[\[(?P<link>[^\]]+)\](\[(?P<desc>[^\]]+)\])?\]")
class LinkParser(SubLineParser):
    def __init__(self,doc):
        super(LinkParser,self).__init__(RE_LINK,doc)

RE_HR = re.compile(r"^((\s*-----+\s*)|(\s*---\s+[a-zA-Z0-9 ]+\s+---\s*))$")
class HrParser(LineParser):
    def __init__(self,doc):
        super(HrParser,self).__init__(RE_HR,doc)

RE_TARGET = regex.compile(r"<<(?P<data>.+?)>>")
class TargetParser(SubLineParser):
    def __init__(self,doc):
        super(TargetParser,self).__init__(RE_TARGET,doc)

RE_MATH = regex.compile(r"\$(?P<data>.+?)\$")
class MathParser(SubLineParser):
    def __init__(self,doc):
        super(MathParser,self).__init__(RE_MATH,doc)

RE_EMPTY = re.compile(r"^\s*$")
class EmptyParser(LineParser):
    def __init__(self,doc):
        super(EmptyParser,self).__init__(RE_EMPTY,doc)

class ActiveDateParser(LineParser):
    def __init__(self,doc):
        super(ActiveDateParser,self).__init__(date.gene_timestamp_regex('active'),doc)

class InactiveDateParser(LineParser):
    def __init__(self,doc):
        super(InactiveDateParser,self).__init__(date.gene_timestamp_regex('inactive'),doc)

class NameParser(LineParser):
    def __init__(self,doc):
        super(NameParser,self).__init__(RE_NAME,doc)

RE_LATEX_HEADER = regex.compile(r"^\s*[#][+](LATEX_HEADER|latex_header)[:]\s*(?P<data>.*)")
class LatexHeaderParser(LineParser):
    def __init__(self,doc):
        super(LatexHeaderParser,self).__init__(RE_LATEX_HEADER,doc)

RE_LATEX_CLASS_OPTIONS = regex.compile(r"^\s*[#][+](LATEX_CLASS_OPTIONS|latex_class_options)[:]\s*(?P<data>.*)")
class LatexClassOptionsParser(LineParser):
    def __init__(self,doc):
        super(LatexClassOptionsParser,self).__init__(RE_LATEX_CLASS_OPTIONS,doc)

RE_SETUPFILE = regex.compile(r"^\s*[#][+](SETUPFILE|setupfile)[:]\s*(?P<data>.*)")
class SetupFileParser(LineParser):
    def __init__(self,doc):
        super(SetupFileParser,self).__init__(RE_SETUPFILE,doc)
    def Handle(self, lines, orgnode):
        for line in lines:
            m = self.sre.search(line)
            if(m):
                filename = m.group('data').strip()
                try:
                    with open(filename,"r") as f:
                        for setupline in f:
                            yield setupline
                except:
                    log.warning("Setup file not found: " + str(filename))
                continue
            yield line

RE_RESULTS = regex.compile(r"^\s*[#][+](RESULTS|results)[:]\s*(?P<data>.*)")
class ResultsParser(LineParser):
    def __init__(self,doc):
        super(ResultsParser,self).__init__(RE_RESULTS,doc)
    def Handle(self, lines, orgnode):
        skip = False
        for line in lines:
            if(skip):
                if(line.strip() == ""):
                    skip = False
                elif(RE_ENDSRC.search(line) or RE_END_DRAWER_LINE.search(line)):
                    skip = False
                    continue
            m = self.sre.search(line)
            if(m):
                if(hasattr(self.e.doc,'sparams')):
                    exp = self.e.doc.sparams.Get("exports","")
                    if(exp == 'code' or exp == 'non'):
                        skip = True 
                        continue
                else:
                    continue
            yield line

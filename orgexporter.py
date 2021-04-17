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

log = logging.getLogger(__name__)

RE_TITLE = regex.compile(r"^\s*[#][+](TITLE|title)[:]\s*(?P<data>.*)")
RE_AUTHOR = regex.compile(r"^\s*[#][+](AUTHOR|author)[:]\s*(?P<data>.*)")
RE_NAME = regex.compile(r"^\s*[#][+](NAME|name)[:]\s*(?P<data>.*)")
RE_DATE = regex.compile(r"^\s*[#][+](DATE|date)[:]\s*(?P<data>.*)")
RE_EMAIL = regex.compile(r"^\s*[#][+](EMAIL|email)[:]\s*(?P<data>.*)")
RE_LANGUAGE = regex.compile(r"^\s*[#][+](LANGUAGE|language)[:]\s*(?P<data>.*)")

RE_BOLD = re.compile(r"\*(?P<data>.+)\*")
RE_ITALICS = re.compile(r"/(?P<data>.+)/")
RE_UNDERLINE = re.compile(r"_(?P<data>.+)_")
RE_STRIKETHROUGH = re.compile(r"\+(?P<data>.+)\+")
RE_CODE = re.compile(r"~(?P<data>.+)~")
RE_VERBATIM = re.compile(r"=(?P<data>.+)=")

RE_HR = re.compile(r"^((\s*-----+\s*)|(\s*---\s+[a-zA-Z0-9 ]+\s+---\s*))$")

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
    
    # This is called when the document is being destroyed
    def Close(self):
        self.FinishDocCustom()
        self.fs.close()

    # Override this to add to the pre-scan phase
    def PreScanCustom(self,l):
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
    def __init__(self,startre,endre,doc):
        self.startre      = startre
        self.endre        = endre
        self.e            = doc
    def Handle(self, lines, orgnode):
        amIn = False
        for line in lines:
            if(amIn):
                m = self.endre.search(line)
                if(m):
                    amIn = False
                    self.HandleExiting(m,line,orgnode)
                    continue
                else:
                    self.HandleIn(line,orgnode)
                    continue
            else:
                m = self.startre.search(line)
                if(m):
                    amIn = True
                    self.HandleEntering(m,line,orgnode)
                else:
                    yield line
        if(amIn):
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
                    curIndent = thisIndent
                    self.HandleEntering(m,l,orgnode)
                    inList += 1
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


RE_STARTQUOTE = re.compile(r"^\s*#\+(BEGIN_QUOTE|begin_quote)")
RE_ENDQUOTE = re.compile(r"^\s*#\+(END_QUOTE|end_quote)")

class QuoteBlockState(BlockState):
    def __init__(self,doc):
        super(QuoteBlockState,self).__init__(RE_STARTQUOTE, RE_ENDQUOTE,doc)

RE_STARTGENERIC = re.compile(r"#\+(BEGIN_|begin_)(?P<data>[a-zA-Z0-9-]+)(\s|$)")
RE_ENDGENERIC   = re.compile(r"#\+(END_|end_)([a-zA-Z0-9-]+)(\s|$)")

class GenericBlockState(BlockState):
    def __init__(self,doc):
        super(GenericBlockState,self).__init__(RE_STARTGENERIC, RE_ENDGENERIC,doc)

RE_TABLE_ROW = re.compile(r"^\s*[|]")
RE_NOT_TABLE_ROW = re.compile(r"^\s*[^| ]")

class TableBlockState(BlockState):
    def __init__(self,doc):
        super(TableBlockState,self).__init__(RE_TABLE_ROW, RE_NOT_TABLE_ROW,doc)

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

RE_SCHEDULING_LINE = re.compile(r"^\s*(SCHEDULED|CLOSED|DEADLINE|CLOCK)[:].*")
class SchedulingStripper(StripParser):
    def __init__(self,doc):
        super(SchedulingStripper,self).__init__(RE_SCHEDULING_LINE,doc)

RE_UL   = re.compile(r"^(?P<indent>\s*)(-|[+])\s+(?P<data>.+)")
class UnorderedListBlockState(ListBlockState):
    def __init__(self,doc):
        super(UnorderedListBlockState,self).__init__(RE_UL,doc)

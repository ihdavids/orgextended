import sublime
import sublime_plugin
import datetime
import re
import regex
from pathlib import Path
import os
import fnmatch
import OrgExtended.orgparse.node as node
from   OrgExtended.orgparse.sublimenode import * 
import OrgExtended.orgutil.util as util
import OrgExtended.orgutil.navigation as nav
import OrgExtended.orgutil.template as templateEngine
import logging
import sys
import traceback 
import OrgExtended.orgfolding as folding
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
import OrgExtended.orgcapture as capture
import OrgExtended.orgproperties as props
import OrgExtended.orgutil.temp as tf
import OrgExtended.pymitter as evt
import OrgExtended.orgnotifications as notice
import OrgExtended.orgextension as ext
import OrgExtended.orgsourceblock as src
import OrgExtended.orgexporter as exp
import yaml
import sys
import subprocess
import html

log = logging.getLogger(__name__)



#\documentclass{article}
# PREAMBLE
#\begin{document}
#Hello, \LaTeX\ world.
#\end{document}

sectionTypes = [
r"\chapter{{{heading}}}",
r"\section{{{heading}}}",
r"\subsection{{{heading}}}",
r"\subsubsection{{{heading}}}",
r"\paragraph{{{heading}}}",
r"\subparagraph{{{heading}}}"
]


class LatexDoc(exp.OrgExporter):
    def __init__(self,filename,file,**kwargs):
        super(LatexDoc, self).__init__(filename, file, **kwargs)
        self.documentclass = r'\documentclass{article}'
        self.pre      = []
        self.doc      = []

    def setClass(self,className):
        self.documentclass = r'\documentclass{{{docclass}}}'.format(docclass=className)

    def BuildDoc(self):
        out = self.documentclass + '\n' + '\n'.join(self.pre) + '\n' + r'\begin{document}' + '\n' + '\n'.join(self.doc) + '\n' + r'\end{document}' + '\n'
        return out

    # Document header metadata should go in here
    def AddExportMetaCustom(self):
        if(self.author):
            self.pre.append(r"\author{{{data}}}".format(data=self.author))
        if(self.title):
            self.pre.append(r"\title{{{data}}}".format(data=self.title))
        pass

    # Setup to start the export of a node
    def StartNode(self, n):
        pass 

    def Escape(self,str):
        str,cnt = self.SingleLineReplacements(str)
        if(not cnt):
            return self.TexFullEscape(str)
        return self.TexCommandEscape(str)

    def TexFullEscape(self,text):
        conv = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
        '\\': r'\textbackslash{}',
        '<': r'\textless{}',
        '>': r'\textgreater{}',
        }
        cleanre = re.compile('|'.join(re.escape(str(key)) for key in sorted(conv.keys(), key = lambda item: - len(item))))
        return cleanre.sub(lambda match: conv[match.group()], text)        
    
    def TexCommandEscape(self,text):
        conv = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
        '<': r'\textless{}',
        '>': r'\textgreater{}',
        }
        cleanre = re.compile('|'.join(re.escape(str(key)) for key in sorted(conv.keys(), key = lambda item: - len(item))))
        return cleanre.sub(lambda match: conv[match.group()], text)        

    def SingleLineReplace(self,reg,rep,text,ok):
        nt = reg.sub(rep,text)
        ok = ok or nt != text
        return (nt,ok)

    def SingleLineReplacements(self,text):
        didRep = False
        text = exp.RE_TITLE.sub("",text)
        text = exp.RE_AUTHOR.sub("",text)
        text = exp.RE_LANGUAGE.sub("",text)
        text = exp.RE_EMAIL.sub("",text)
        text = exp.RE_DATE.sub("",text)
        text,didRep = self.SingleLineReplace(exp.RE_NAME,r"\label{{\g<data>}}",text,didRep)
        text,didRep = self.SingleLineReplace(exp.RE_BOLD,r"\\textbf{{\g<data>}}",text,didRep)
        text,didRep = self.SingleLineReplace(exp.RE_ITALICS,r"\\textit{{\g<data>}}",text,didRep)
        text,didRep = self.SingleLineReplace(exp.RE_UNDERLINE,r"\underline{{\g<data>}}",text,didRep)
        text,didRep = self.SingleLineReplace(exp.RE_CODE,r"\\texttt{{\g<data>}}",text,didRep)
        text,didRep = self.SingleLineReplace(exp.RE_VERBATIM,r"\\texttt{{\g<data>}}",text,didRep)
        text,didRep = self.SingleLineReplace(exp.RE_HR,r"\hrulefill",text,didRep)

        return (text,didRep)


    # Export the heading of this node
    def NodeHeading(self,n):
        heading = self.Escape(n.heading)
        level = n.level
        if(level >= len(sectionTypes)):
            level = len(sectionTypes)-1
        self.doc.append(sectionTypes[level].format(heading=heading))

    # We are about to start exporting the nodes body
    def StartNodeBody(self,n):
        pass

    # Actually buid the node body in the document
    def NodeBody(self,n):
        for l in n._lines[1:]:
            # TODO Build processor!
            self.doc.append(self.Escape(l))
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

    def FinishDocCustom(self):
        self.fs.write(self.BuildDoc())

    def Execute(self):
        cmdStr = sets.Get("latex2Pdf","C:\\texlive\\2021\\bin\\win32\\pdflatex.exe")
        commandLine = [cmdStr, self.outputFilename]
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        except:
            startupinfo = None
        # cwd=working_dir, env=my_env,
        cwd = os.path.join(sublime.packages_path(),"User") 
        popen = subprocess.Popen(commandLine, universal_newlines=True, cwd=cwd, startupinfo=startupinfo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        #popen.wait()
        (o,e) = popen.communicate()
        log.debug(o)
        log.debug(e)
        #log.debug(o.split('\n') + e.split('\n'))

# ============================================================
class OrgExportFileAsLatexCommand(sublime_plugin.TextCommand):

    def OnDoneSourceBlockExecution(self):
        # Reload if necessary
        self.file = db.Get().FindInfo(self.view)
        self.doc  = None
        self.docClass = exp.GetGlobalOption(self.file,"LATEX_CLASS","latexClass","article").lower()
        try:
            outputFilename = exp.ExportFilename(self.view,".tex",self.suffix)
            self.doc       = LatexDoc(outputFilename,self.file)
            self.doc.setClass(self.docClass)
            self.helper    = exp.OrgExportHelper(self.view,self.index)
            self.helper.Run(outputFilename, self.doc)
            self.doc.Execute()
        finally:    
            evt.EmitIf(self.onDone)


    def run(self,edit, onDone=None, index=None, suffix=""):
        self.file = db.Get().FindInfo(self.view)
        self.onDone = onDone
        self.suffix = suffix
        if(index != None):
            self.index = index
        else:
            self.index = None
        if(None == self.file):
            log.error("Not an org file? Cannot build reveal document")
            evt.EmitIf(onDone)  
            return
        if(sets.Get("latexExecuteSourceOnExport",False)):
            self.view.run_command('org_execute_all_source_blocks',{"onDone":evt.Make(self.OnDoneSourceBlockExecution),"amExporting": True})
        else:
            self.OnDoneSourceBlockExecution()


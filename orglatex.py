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
r"\\chapter\{{heading}\}",
r"\\section\{{heading}\}",
r"\\subsection\{{heading}\}",
r"\\subsubsection\{{heading}\}",
r"\\subsubsubsection\{{heading}\}",
r"\\subsubsubsubsection\{{heading}\}",
r"\\subsubsubsubsubsection\{{heading}\}",
]


class LatexDoc(exp.OrgExporter):
    def __init__(self,filename,file,**kwargs):
        super(LatexDoc, self).__init__(filename, file, **kwargs)
        self.documentclass = r'\\documentclass{article}'
        self.pre      = []
        self.doc      = []

    def setClass(self,className):
        self.documentclass = r'\\documentclass\{{}\}'.format(className)

    def BuildDoc(self):
        doc = self.documentclass + '\n' + '\n'.join(self.pre) + r'\\begin{document}\n' + '\n'.join(self.doc) + r'\\end{document}\n'

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
            self.helper    = exp.OrgExportHelper(self.view,self.index)
            self.helper.Run(outputFilename, self.doc)
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


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


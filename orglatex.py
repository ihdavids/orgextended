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

def TexFilename(view,suffix=""):
	fn = view.file_name()
	fn,ext = os.path.splitext(fn)
	return fn + suffix + ".tex"

def GetGlobalOption(file, name, settingsName, defaultValue):
	value = sets.Get(settingsName, defaultValue)
	value = ' '.join(file.org[0].get_comment(name, [str(value)]))
	return value


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
	def build_head(self, doc):
		highlight      = GetGlobalOption(self.file,"HTML_HIGHLIGHT","HtmlHighlight","zenburn").lower()
		doc.AddInlineStyle(GetHighlightJsCss(highlight))
		doc.AddInlineStyle(GetCollapsibleCss())
		doc.AddInlineStyle(GetStyleData(self.style, self.file))
		doc.AddExportMeta()

	def build_node(self, doc, n):
		doc.StartNode(n)
		doc.NodeHeading(n)
		doc.StartNodeBody(n)
		doc.NodeBody(n)
		for c in n.children:
			self.build_node(doc, c)
		doc.EndNodeBody(n)
		doc.EndNode(n)

	def build_nodes(self, doc):
		if(self.index == None):
			nodes = self.file.org
			for n in nodes.children:
				self.build_node(doc, n)
		else:
			n = self.file.org.env._nodes[self.index]
			self.build_node(doc,n)

	def build_document(self, doc):
		doc.StartNodes()
		self.build_nodes(doc)
		doc.EndNodes()

	def build_body(self, doc):
		doc.StartDocument(self.file)
		self.build_document(doc)
		doc.EndDocument()
		doc.InsertScripts(self.file)

	def OnDoneSourceBlockExecution(self):
		# Reload if necessary
		self.file = db.Get().FindInfo(self.view)
		doc = None
		self.docClass = GetGlobalOption(self.file,"LATEX_CLASS","latexClass","article").lower()
		try:
			outputFilename = LatexFilename(self.view,self.suffix)
			self.doc = LatexDoc(outputFilename,self.file)
			self.doc.setClass(self.docClass)
			doc.StartHead()
			self.build_head(doc)
			doc.EndHead()

			doc.StartBody()
			self.build_body(doc)
			doc.EndBody()
		finally:	
			if(None != doc):
				doc.Close()
			log.log(51,"EXPORT COMPLETE: " + str(outputFilename))
			self.view.set_status("ORG_EXPORT","EXPORT COMPLETE: " + str(outputFilename))
			sublime.set_timeout(self.clear_status, 1000*10)
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

	def clear_status(self):
		self.view.set_status("ORG_EXPORT","")

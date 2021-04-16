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



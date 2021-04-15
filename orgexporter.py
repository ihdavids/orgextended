import re
import regex
from pathlib import Path
import os
import fnmatch
import logging
import sys
import traceback 

log = logging.getLogger(__name__)

RE_TITLE = regex.compile(r"^\s*[#][+](TITLE|title)[:]\s*(?P<data>.*)")
RE_AUTHOR = regex.compile(r"^\s*[#][+](AUTHOR|author)[:]\s*(?P<data>.*)")
RE_NAME = regex.compile(r"^\s*[#][+](NAME|name)[:]\s*(?P<data>.*)")
RE_DATE = regex.compile(r"^\s*[#][+](DATE|date)[:]\s*(?P<data>.*)")
RE_EMAIL = regex.compile(r"^\s*[#][+](EMAIL|email)[:]\s*(?P<data>.*)")
RE_LANGUAGE = regex.compile(r"^\s*[#][+](LANGUAGE|language)[:]\s*(?P<data>.*)")

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


	def PreScan(self):
		for l in self.file.org._lines:
			self.PreScanExportCommentsGather(l)
			self.PreScanCustom(l)

	# Override this to add to the pre-scan phase
	def PreScanCustom(self,l):
		pass

	# Override this to close off the document for exporting
	def FinishDoc(self):
		pass

	# This is called when the document is being destroyed
	def Close(self):
		self.FinishDoc()
		self.fs.close()

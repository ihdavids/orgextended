
import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
import fnmatch
import OrgExtended.orgparse.node as node
from   OrgExtended.orgparse.sublimenode import * 
import OrgExtended.orgutil.util as util
import OrgExtended.orgutil.navigation as nav
import OrgExtended.orgutil.template as templateEngine
import OrgExtended.orgutil.temp as tf
import logging
import sys
import traceback 
import OrgExtended.orgfolding as folding
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
import OrgExtended.orgcapture as capture
import OrgExtended.orgproperties as props
import yaml
import sys
import subprocess

log = logging.getLogger(__name__)

DEFAULT_COMMANDS = dict(
	# Standard universal can opener for OSX.
	darwin=['open'],
	win32=['cmd', '/C'],
	linux=['xdg-open'],
)

def Execute(op):
	cmd = DEFAULT_COMMANDS[sys.platform]
	cmd = op
	print(str(cmd))
	if sys.platform != 'win32':
		process = subprocess.Popen(
			cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	else:
		process = subprocess.Popen(
			cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
	stdout, stderr = process.communicate()
	if stdout:
		stdout = str(stdout, sys.getfilesystemencoding())
		sublime.status_message(stdout)
		print(stdout)
	if stderr:
		stderr = str(stderr, sys.getfilesystemencoding())
		sublime.error_message(stderr)

def GetCssForHtmlExport(style):
	# Include user created styles!
	css = os.path.join(sublime.packages_path(),"OrgExtended", "pandoc", style + ".css")
	return css

def GetHeaderData(style):
	inHeader = os.path.join(sublime.packages_path(),"OrgExtended", "pandoc", style + "_inheader.html")
	if(os.path.isfile(inHeader)):
		return ["-H", inHeader]

def Pandoc():
	return sets.Get("PandocPath",r'C:\Program Files\Pandoc\pandoc.exe')

# Export the entire file using pandoc 
class OrgExportFileAsHtmlCommand(sublime_plugin.TextCommand):
	def run(self,edit):
		style    = sets.Get("PandocStyle","blocky")
		css      = GetCssForHtmlExport(style)
		outFile  = tf.GetViewFileAs(self.view, ".html")
		cmd     = [Pandoc(), "-s","-c",css]
		inHeader = GetHeaderData(style)
		if(inHeader):
			cmd.extend(inHeader)
		cmd.extend(["-o", outFile, self.view.file_name()])
		print(cmd)
		Execute(cmd)
		#Execute([r'C:\Program Files\Pandoc\pandoc.exe', '-h'])


class OrgExportSubtreeAsHtmlCommand(sublime_plugin.TextCommand):
	def run(self,edit):
		n = db.Get().AtInView(self.view)
		s = self.view.text_point(n.start_row,0)
		e = self.view.line(self.view.text_point(n.end_row,0)).end()
		r = sublime.Region(s,e)
		ct = self.view.substr(r)
		start = ""
		if "#+TITLE:" not in ct:
			start = "#+TITLE: " + os.path.splitext(os.path.basename(self.view.file_name()))[0]

		tempFile = tf.CreateTempFileFromRegion(self.view, r, ".org", start)
		outFile  = tf.GetViewFileAs(self.view, ".html")
		style = sets.Get("PandocStyle","blocky")
		css = GetCssForHtmlExport(style)
		cmd     = [Pandoc(), "-s","-c",css]
		inHeader = GetHeaderData(style)
		if(inHeader):
			cmd.extend(inHeader)
		cmd = cmd.extend(["-o", outFile, tempFile])	
		Execute(cmd)
# pandoc -s -o output.html input.txt
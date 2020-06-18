import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
import fnmatch
from .orgparse.__init__ import *
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
import OrgExtended.orglinks as links
import OrgExtended.orgclocking as clocking
import OrgExtended.orgextension as ext
import OrgExtended.pymitter as evt
import importlib

log = logging.getLogger(__name__)


RE_END = re.compile(r"^\s*\#\+(END|end)[:]")
RE_DYN_BLOCK = re.compile(r"^\s*\#\+(BEGIN|begin)[:]\s+(?P<name>[^: ]+)\s*")
RE_FN_MATCH = re.compile(r"\s*[:]([a-zA-Z0-9-_]+)\s+([^: ]+)\s*")


def IsDynamicBlock(view):
	line = view.getLine(view.curRow())
	return RE_DYN_BLOCK.search(line) or RE_END.search(line)

class OrgExecuteDynamicBlockCommand(sublime_plugin.TextCommand):
	def on_replaced(self):
		if(hasattr(self.curmod,"PostExecute")):
			self.curmod.PostExecute(self.view, self.params, self.region)

	def run(self, edit):
		view = self.view
		at = view.sel()[0]
		if(view.match_selector(at.begin(),'orgmode.fence.dynamicblock')):
			# Okay we have a dynamic block, now we need to know where it ends.
			start = at.begin()
			end   = None
			erow = view.endRow()
			row  = view.curRow()
			for rw in range(row,erow+1):
				line = view.substr(view.line(view.text_point(rw,0)))
				if(RE_END.search(line)):
					end = rw
					break
			if(not end):
				log.debug("Could not locate #+END: tag")
				return
			# Okay now we have a start and end to build a region out of.
			# time to run a command and try to get the output.
			dynamic = ext.find_extension_modules('dynamic')
			line = view.substr(view.line(start))
			m = RE_DYN_BLOCK.search(line)
			if(not m):
				log.error("FAILED TO PARSE DYNAMIC BLOCK: " + line)
				return
			fnname = m.group('name')
			#log.debug("DYN NAME: " + fnname)
			paramstr = line[len(m.group(0)):]
			params = {}
			for m in RE_FN_MATCH.finditer(paramstr):
				params[m.group(1)] = m.group(2)
			# Now find me that function!
			if(fnname not in dynamic):
				log.error("Function not found in dynamic folder! Cannot execute!")
				return
			# Run the "writer"
			if(hasattr(dynamic[fnname],"Execute")):
				self.curmod = dynamic[fnname]
				self.params = params
				outputs = self.curmod.Execute(view, params)
				#log.debug("OUTPUT: " + str(outputs))

			# Okay now time to replace the contents of the block
			s = view.text_point(row+1,0)
			e = view.text_point(end,0)
			self.region = sublime.Region(s,e)
			# Reformat adding indents to each line!
			# No bad formatting allowed!
			n = db.Get().AtInView(view)
			level = n.level
			indent = "\n " * level + " "
			#outputs = output.split('\n')
			output = indent.join(outputs)
			self.view.run_command("org_internal_replace", {"start": s, "end": e, "text": (" " * level + " ") + output+"\n","onDone": evt.Make(self.on_replaced)})
		else:
			log.error("NOT in A DynamicBlock, nothing to run")

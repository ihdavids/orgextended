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
import logging
import sys
import traceback 
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
import OrgExtended.orgproperties as props
import yaml
import OrgExtended.pymitter as evt

log = logging.getLogger(__name__)



class ClockManager:
	Clock = None

	@staticmethod
	def ClockInRecord(file, onode, dt):
		parentHeading = ""
		if(onode.parent and type(onode.parent) != node.OrgRootNode):
			parentHeading = onode.parent.heading

		ClockManager.Clock = {
			'file': file.filename,
			'start': dt,
			'heading': onode.get_locator()
		}
		ClockManager.SaveClock()

	@staticmethod
	def ClockRunning():
		return ClockManager.Clock != None

	@staticmethod
	def FormatClock(now):
		return now.strftime("[%Y-%m-%d %a %H:%M]")	

	@staticmethod
	def FormatDuration(d):
		hours   = d.seconds/3600
		minutes = (d.seconds/60)%60	
		return "{0:02d}:{1:02d}".format(int(hours),int(minutes))	

	@staticmethod
	def ClockPath():
	   return os.path.join(sublime.packages_path(), "User","OrgExtended_Clocks.yaml")


	@staticmethod
	def SaveClock():
	   f = open(ClockManager.ClockPath(),"w")
	   data = yaml.dump(ClockManager.Clock, f)
	   f.close() 

	@staticmethod
	def LoadClock():
		cpath = ClockManager.ClockPath()
		if(os.path.isfile(cpath)):
			stream = open(cpath, 'r')
			ClockManager.Clock = yaml.load(stream, Loader=yaml.SafeLoader)
			stream.close()

	@staticmethod
	def ClockIn(view):
		if(ClockManager.ClockRunning()):
			view.set_status("Clock","CLOCK")
			ClockManager.ClockOut(view)
		# Handle clock already running
		node = db.Get().AtInView(view)
		if(node):
			file = db.Get().FindInfo(view)
			if(file):
				dt = datetime.datetime.now()
				ClockManager.ClockInRecord(file, node, dt)
				if(sets.Get("clockInPropertyBlock",False)):
					props.AddProperty(view, node, "CLOCK", ClockManager.FormatClock(dt) + "--")
				else:
					props.AddLogbook(view, node, "CLOCK:", ClockManager.FormatClock(dt) + "--")

	@staticmethod
	def UpdateClockStart(view):
		if(not ClockManager.ClockRunning()):
			log.error("Clock not running, nothing to update")
			return
		# Eventually we want to navigate to this node
		# rather than doing this.
		node = db.Get().FindNode(ClockManager.Clock["file"], ClockManager.Clock["heading"])
		newStart = None
		if(node):
			tview = view.window().open_file(ClockManager.Clock["file"], sublime.ENCODED_POSITION)
			if(sets.Get("clockInPropertyBlock",False)):
				val = props.GetProperty(tview, node, "CLOCK")
			else:
				val = props.GetLogbook(tview, node, r"CLOCK:")
			if val:
				clock = OrgDateClock.from_str(val)
				if clock:
					newStart = clock.start
		if newStart:
			file = db.Get().FindInfo(ClockManager.Clock["file"])
			ClockManager.ClockInRecord(file, node, newStart)
	@staticmethod
	def ClockOut(view):
		if(not ClockManager.ClockRunning()):
			return
		# Eventually we want to navigate to this node
		# rather than doing this.
		node = db.Get().FindNode(ClockManager.Clock["file"], ClockManager.Clock["heading"])
		if(node):
			end   = datetime.datetime.now()
			start = ClockManager.Clock["start"]
			duration = end - start
			# Should we keep clocking entries less than a minute?
			shouldKeep = sets.Get("clockingSubMinuteClocks",True)
			tview = view.window().open_file(ClockManager.Clock["file"], sublime.ENCODED_POSITION)
			if(not shouldKeep and duration.seconds < 60):
				if(sets.Get("clockInPropertyBlock",False)):
					props.RemoveProperty(tview, node, "CLOCK")
				else:
					props.RemoveLogbook(tview, node, r"CLOCK:")
			else:
				if(sets.Get("clockInPropertyBlock",False)):
					props.UpdateProperty(tview, node, "CLOCK", ClockManager.FormatClock(start) + "--" + ClockManager.FormatClock(end) + " => " + ClockManager.FormatDuration(duration))
				else:
					props.UpdateLogbook(tview, node, "CLOCK:", ClockManager.FormatClock(start) + "--" + ClockManager.FormatClock(end) + " => " + ClockManager.FormatDuration(duration))
			view.window().focus_view(view)
			tview.run_command("save")
			ClockManager.ClearClock()
			view.run_command("save")
		else:
			log.error("Failed to clock out, couldn't find node")

	@staticmethod
	def ClearClock():
		ClockManager.Clock = None
		cpath = ClockManager.ClockPath()
		if(os.path.isfile(cpath)):
			os.remove(cpath)

	@staticmethod
	def GetActiveClockFile():
		if(not ClockManager.ClockRunning()):
			return None
		return ClockManager.Clock["file"]

	@staticmethod
	def GetActiveClockAt():
		if(not ClockManager.ClockRunning()):
			return None
		node = db.Get().FindNode(ClockManager.Clock["file"], ClockManager.Clock["heading"])
		if(node):
			return node.start_row


# Load the clock cache.
def Load():
	ClockManager.LoadClock()

# Clock in a task
class OrgClockInCommand(sublime_plugin.TextCommand):
	def run(self,edit,onDone=None):
		ClockManager.LoadClock()
		ClockManager.ClockIn(self.view)
		evt.EmitIf(onDone)

# Clock out a task
class OrgClockOutCommand(sublime_plugin.TextCommand):
	def run(self,edit,onDone=None):
		ClockManager.LoadClock()
		ClockManager.ClockOut(self.view)
		evt.EmitIf(onDone)

# Jump to an active clock
class OrgJumpToClockCommand(sublime_plugin.TextCommand):
	def run(self,edit,onDone=None):
		ClockManager.LoadClock()
		at = ClockManager.GetActiveClockAt()
		filename = ClockManager.GetActiveClockFile()
		if at and filename:	
			path = "{0}:{1}".format(filename,at + 1)
			self.view.window().open_file(path, sublime.ENCODED_POSITION)
		else:
			print("No active clock")
		evt.EmitIf(onDone)

# Clear the currently running clock (if there is one)
class OrgClearClockCommand(sublime_plugin.TextCommand):
	def run(self,edit):
		ClockManager.ClearClock()

# Update the currently running command based on an open clock manual update
class OrgUpdateClockCommand(sublime_plugin.TextCommand):
	def run(self,edit):
		ClockManager.UpdateClockStart(self.view)

# Recalculate all the clock values in a node (Crtl-c Ctrl-c on a clock entry)
class OrgRecalculateClockCommand(sublime_plugin.TextCommand):
	def run(self,edit):
		node = db.Get().AtInView(self.view)
		clockList = copy.copy(node.clock)
		log.debug(str(clockList))
		log.debug(str(len(clockList)))
		if(sets.Get("clockInPropertyBlock",False)):
			props.RemoveAllInstances(self.view, node, "CLOCK")
		else:
			props.RemoveAllLogbookInstances(self.view, node, r"^\s*CLOCK:")
		log.debug(str(clockList))
		log.debug(str(len(clockList)))
		for clock in clockList:
			# File is reloaded have to regrab node
			node = db.Get().At(self.view, node.start_row)
			if(sets.Get("clockInPropertyBlock",False)):
				props.AddProperty(self.view, node, "CLOCK", clock.format_clock_str())
			else:
				props.AddLogbook(self.view, node, "CLOCK:", clock.format_clock_str())

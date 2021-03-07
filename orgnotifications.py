import sublime
import sublime_plugin
import threading, time, signal
from datetime import timedelta
from datetime import datetime
import os
import sys
import OrgExtended.orgagenda as agenda
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
from   OrgExtended.orgparse.date import OrgDate
import logging
import subprocess, os

CHECK_PERIOD = 60*1

log = logging.getLogger(__name__)

class Notification(agenda.TodoView):
	def Show(self, notifications, newItem):
		# Windows notice.
		n = newItem['node']
		f = newItem['file']
		heading = ""
		if(n.scheduled):
			heading = OrgDate.format_clock(n.scheduled.start,active=False)
		else:
			heading = "SOON!"
		body = f.AgendaFilenameTag() + "  " + n.heading
		ShowBalloon(body, heading)
		# Show the in sublime version, clear out other
		# todos and just show our notices.
		self.entries = []
		if(notifications and type(notifications) is dict):
			for key,item in notifications.items():
				self.AddEntry(item['node'],item['file'])
		window = sublime.active_window() 
		window.active_view().run_command('org_show_notifications')
		return

notification = None
class OrgShowNotifications(sublime_plugin.TextCommand):
	def run(self, edit):	
		notification.DoRenderView(edit)

def ShowBalloon(todo, time):
	log.debug("SHOW BALLOON POPUP")
	formatDict = {
	"time": time,
	"todo": todo
	}
	if(sublime.platform() == 'windows'):
		commandLine = sets.Get("ExternalNotificationCommand",[r"C:\\Windows\\SysWOW64\\WindowsPowerShell\\v1.0\\powershell.exe", "-ExecutionPolicy", "Unrestricted", ".\\balloontip.ps1", "\"{todo}\"", "\"{time}\""], formatDict)
	elif(sublime.platform() == 'osx'):
		commandLine = sets.Get("ExternalNotificationCommand",['osascript','-e',"display notification \"{time}\" with title \"{todo}\" subtitle \""+"Org Mode TODO"+"\""], formatDict)
	else:
		print("ERROR: platform not yet supported for notifications")
	# Expand all potential macros.
	for i in range(len(commandLine)):
		commandLine[i] = commandLine[i].format(todo=todo,time=time)
	try:
		startupinfo = subprocess.STARTUPINFO()
		startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
	except:
		startupinfo = None
	# cwd=working_dir, env=my_env,
	cwd = os.path.join(sublime.packages_path(),"OrgExtended") 
	if(sublime.platform() == 'windows'):
		popen = subprocess.Popen(commandLine, universal_newlines=True, cwd=cwd, startupinfo=startupinfo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		popen.wait()
	elif(sublime.platform() == 'osx'):
		subprocess.check_call(commandLine,stderr=subprocess.STDOUT)

def IsWithinNotificationWindow(n, hours, minutes):
	if(not n.scheduled):
		return False
	now = datetime.now()
	hour = now.hour
	mins = now.minute
	if(n.scheduled.repeating):
		next = n.scheduled.next_repeat_from_today
		return ((next.hour-hours) == hour and (next.minute - mins) <= minutes) 
	next = agenda.EnsureDateTime(n.scheduled.start)
	return ((next.hour-hours) == hour and (next.minute - mins) <= minutes) 

def GetUID(item):
	n = item['node']
	f = item['file']
	return f.filename + "@" + n.get_locator() + "@" + str(n.scheduled)

class NotificationSystem(threading.Thread):
	def __init__(self, interval):
		threading.Thread.__init__(self)
		self.daemon     = False
		self.stopped    = threading.Event()
		self.interval   = interval
		self.today      = None
		self.notified   = {}
		self.todaysDate = datetime.now().day
		self.checkcount = 1
		
	def stop(self):
		self.stopped.set()
		self.join()

	def run(self):
		while not self.stopped.wait(self.interval.total_seconds()):
			self.CheckNotifications()

	def HaveNotifiedFor(self, item):
		return GetUID(item) in self.notified


	def DoNotify(self,item):
		self.notified[GetUID(item)] = item
		global notification
		notification = Notification("Notifications")
		notification.Show(self.notified, item)
		
	def CheckNotifications(self):
		log.debug("CHECKING...")
		if(datetime.now().day > self.todaysDate or self.today == None):
			self.todaysDate = datetime.now().day
			self.notified = {}
			self.BuildToday()
		# Periodically rebuild the day.
		if((self.checkcount % 4) == 0):
			self.checkcount += 1
			self.BuildToday()

		hours   = sets.Get("notifyHoursBefore", 0)
		minutes = sets.Get("notifyMinsBefore", 15)
		for item in self.today:
			n = item['node']
			if(IsWithinNotificationWindow(n, hours, minutes) and not self.HaveNotifiedFor(item)):
				log.debug("DO NOTIFY CALLED")
				self.DoNotify(item)

	def AddEntry(self,n,f):
		self.today.append({'node': n, 'file': f})

	def BuildToday(self):
		self.today = []
		for file in db.Get().Files:
			for n in file.org[1:]:
				if(self.TodayCheck(n, file)):
					self.AddEntry(n, file)

	def TodayCheck(self, n, file):
		try:
			now = datetime.now()
			return (agenda.IsTodo(n) and agenda.IsToday(n, now))
		except:
			if(n):
				log.error("NOTIFICATIONS FAILED TO PARSE: " + str(n.heading))
			return False


notice = None

def Setup():
	global notice
	checkPeriod = sets.Get("noticePeriod",1)*60
	if(checkPeriod < 60):
		checkPeriod = 60
	notice = NotificationSystem(interval=timedelta(seconds=checkPeriod))
	notice.start()
	log.debug("NOTIFICATION SYSTEM IS UP AND RUNNING: " + str(checkPeriod))

def Get():
	return notice   

class OrgRebuildNotificationsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
    	global notice
    	if(notice == None):
    		Setup()
    	notice.BuildToday()


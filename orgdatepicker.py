import calendar
import sublime
import sublime_plugin
import datetime
from OrgExtended.orgparse.date import *
import OrgExtended.pymitter as evt

def CreateUniqueViewNamed(name, mapped=None):
	# Close the view if it exists
	win = sublime.active_window()
	for view in win.views():
		if view.name() == name:
			win.focus_view(view)
			win.run_command('close')
	win.run_command('new_file')
	view = win.active_view()
	view.set_name(name)
	# TODO: Change this.
	view.set_syntax_file("Packages/OrgExtended/orgdatepicker.sublime-syntax")
	#ViewMappings[view.name()] = mapped
	return view

class DateView:
	def __init__(self, dayhighlight=None):
		self.months = []
		self.columnsPerMonth = 30                     # 7 * 3 = 21 + 9
		self.columnsInDay    = 2  
		self.columnsPerDay   = self.columnsInDay + 1  # 2 digits plus a space
		self.midmonth        = datetime.datetime.now().month 
		self.monthdata       = None
		self.headingLines    = 2
		self.output          = None
		self.cdate           = OrgDateFreeFloating(datetime.datetime.now())
		self.startrow        = 0
		self.endrow          = 7
		self.dayhighlight    = dayhighlight


	def SetView(self, view):
		self.output = view


	def SetStartRow(self, row):
		self.startrow = row


	def DateToRegion(self, date):
		# Convert 
		monthIndex = (date.month - self.midmonth + 1)
		if(monthIndex < 0 or monthIndex >= len(self.monthdata)):
			return
		monthData = self.monthdata[monthIndex]
		weekIndex = 0
		dayIndex  = 0
		for weekId in range(0,len(monthData)):
			weekData = monthData[weekId]
			for dayId in range(0,len(weekData)):
				day = weekData[dayId]
				if(day == date.day):
					weekIndex = weekId
					dayIndex  = dayId
		# 2 row heading?
		# We should have an offset? Probably
		row = self.headingLines + weekIndex
		col = monthIndex * self.columnsPerMonth + dayIndex*self.columnsPerDay
		#print("ROW: " + str(row) + " COL: " + str(col))
		s = self.output.text_point(row,col)
		e = self.output.text_point(row,col+2)
		return sublime.Region(s, e)

	def HighlightDay(self, date):
		reg = self.DateToRegion(date)
		style = self.dayhighlight
		if(style == None):
			style = "orgdatepicker.monthheader"
		self.output.add_regions("cur",[reg],style,"",sublime.DRAW_NO_OUTLINE)	

	def AddToDayHighlights(self, date, key, highlight, drawtype = sublime.DRAW_NO_OUTLINE):
		reg = self.DateToRegion(date)
		regs = self.output.get_regions(key)
		if not regs:
			regs = []
		regs.append(reg)
		self.output.add_regions(key,regs,highlight,"",drawtype)	


	def MapRowColToDate(self,row,col):
		weekid   = int(row - self.headingLines)
		monthid  = int(col / self.columnsPerMonth)
		dayid    = int((col % self.columnsPerMonth) / self.columnsPerDay)
		day      = self.monthdata[monthid][weekid][dayid]
		month    = monthid + self.midmonth - 1
		year     = self.cdate.start.year
		time     = self.cdate.start.time()
		duration = None
		if(time):
			result = datetime.datetime(year, month, day, time.hour, time.minute, time.second, time.microsecond)
		else:
			result = datetime.datetime(year, month, day)
		return result

	def MoveCDateToDate(self, now):
		self.cdate           = OrgDateFreeFloating(now)
		self.ReShow()
		self.HighlightDay(self.cdate.start)

	def MoveCDateToNextDay(self):
		self.cdate.add_days(1)
		self.ReShow()
		self.HighlightDay(self.cdate.start)

	def MoveCDateToPrevDay(self):
		self.cdate.add_days(-1)
		self.ReShow()
		self.HighlightDay(self.cdate.start)

	def MoveCDateToNextWeek(self):
		self.cdate.add_days(7)
		self.ReShow()
		self.HighlightDay(self.cdate.start)

	def MoveCDateToPrevWeek(self):
		self.cdate.add_days(-7)
		self.ReShow()
		self.HighlightDay(self.cdate.start)

	def MoveCDateToNextMonth(self):
		self.cdate.add_months(1)
		self.ReShow()
		self.HighlightDay(self.cdate.start)

	def MoveCDateToPrevMonth(self):
		self.cdate.add_months(-1)
		self.ReShow()
		self.HighlightDay(self.cdate.start)

	def ReShow(self):
		now = self.cdate.start
		mid = (now.month - self.midmonth + 1)
		if(mid < 0 or mid > 2):
			self.Render(now)
			self.ResetRenderState()

	@staticmethod
	def NextMonth(now):
		month = now.month + 1
		year  = now.year
		if(month > 12):
			year += 1
			month = 1
		return (month, year)

	@staticmethod
	def PrevMonth(now):
		month = now.month - 1
		year  = now.year
		if(month <= 0):
			year -= 1
			month = 12
		return (month, year)

	def Render(self,now):
		c = calendar.TextCalendar(calendar.SUNDAY)
		str = c.formatmonth(now.year, now.month)
		calendar.setfirstweekday(calendar.SUNDAY)
		self.midmonth  = now.month
		pmonth, pyear = DateView.PrevMonth(now)
		nmonth, nyear = DateView.NextMonth(now)
		self.monthdata = [ calendar.monthcalendar(pyear, pmonth),
						   calendar.monthcalendar(now.year, now.month),
						   calendar.monthcalendar(nyear, nmonth)]
		#print(str)
		m2 = str.split('\n')
		month, year = DateView.NextMonth(now)
		str = c.formatmonth(year, month)
		#print(str)
		m3 = str.split('\n')
		month, year = DateView.PrevMonth(now)
		str = c.formatmonth(year, month)
		#print(str)
		m1 = str.split('\n')

		self.output.set_read_only(False)
		self.output.sel().clear()
		pt = self.output.text_point(self.startrow,0)
		self.output.sel().add(pt)
		l = max(len(m1),len(m2),len(m3))
		self.endrow = self.startrow + l
		row = self.startrow
		for i in range(0,l):
			pt = self.output.text_point(row,0)
			row += 1
			ml1 = m1[i] if i < len(m1) else ""
			ml2 = m2[i] if i < len(m2) else ""
			ml3 = m3[i] if i < len(m3) else ""
			line = "{0:30}{1:30}{2:30}".format(ml1,ml2,ml3)
			lreg = self.output.line(pt)
			lreg = sublime.Region(lreg.begin(), lreg.end() + 1)
			self.output.ReplaceRegion(lreg, line + "\n")

		self.HighlightDay(now)

	def ResetRenderState(self):
		self.output.set_read_only(True)
		self.output.set_scratch(True)
		self.output.set_name("DatePicker")


class DatePicker:
	def __init__(self):
		self.dateView = DateView()
		self.months = []

	def on_done(self, text):
		self.dateView.output.close()
		if(self.onDone):
			evt.Get().emit(self.onDone, self.dateView.cdate)

	def on_canceled(self):
		self.dateView.output.close()
		if(self.onDone):
			evt.Get().emit(self.onDone, None)

	def on_changed(self, text):
		#print("CHANGED: " + text)
		self.dateView.cdate = OrgDateFreeFloating.from_str(text)
		if(self.dateView.cdate):
			self.dateView.HighlightDay(self.dateView.cdate.start)
		self.dateView.ReShow()

	def MapRowColToNewDate(self,row,col):
		time     = self.dateView.cdate.start.time()
		duration = None
		if(self.dateView.cdate.has_end()):
			duration = self.dateView.cdate.end - self.dateView.cdate.start
		self.dateView.cdate._start = self.dateView.MapRowColToDate(row,col)
		if(duration):
			self.dateView.cdate._end = self.dateView.cdate.start + duration
		self.inputpane.ReplaceRegion(self.inputpane.line(self.inputpane.text_point(0,0)), OrgDate.format_datetime(self.dateView.cdate.start))
		self.dateView.HighlightDay(self.dateView.cdate.start)

	def RefreshInputPanelFromDateView(self):
		self.inputpane.ReplaceRegion(self.inputpane.line(self.inputpane.text_point(0,0)), OrgDate.format_datetime(self.dateView.cdate.start))

	def MoveNextDay(self):
		self.dateView.MoveCDateToNextDay()
		self.RefreshInputPanelFromDateView()

	def MovePrevDay(self):
		self.dateView.MoveCDateToPrevDay()
		self.RefreshInputPanelFromDateView()

	def MoveNextWeek(self):
		self.dateView.MoveCDateToNextWeek()
		self.RefreshInputPanelFromDateView()

	def MovePrevWeek(self):
		self.dateView.MoveCDateToPrevWeek()
		self.RefreshInputPanelFromDateView()

	def MoveNextMonth(self):
		self.dateView.MoveCDateToNextMonth()
		self.RefreshInputPanelFromDateView()

	def MovePrevMonth(self):
		self.dateView.MoveCDateToPrevMonth()
		self.RefreshInputPanelFromDateView()

	def Show(self,now, onDone):
		self.onDone	= onDone
		window      = sublime.active_window()
		self.output = CreateUniqueViewNamed("DatePicker")
		self.dateView.SetView(self.output)
		self.dateView.Render(now)
		self.dateView.ResetRenderState()
		curstr = OrgDate.format_datetime(now)
		self.cdate = OrgDateFreeFloating.from_str(curstr)
		self.inputpane = window.show_input_panel(
					"Date:",
					curstr,
					self.on_done,
					self.on_changed,
					self.on_canceled)
		pt = self.inputpane.text_point(0,0)
		self.inputpane.set_syntax_file("Packages/OrgExtended/orgdateeditor.sublime-syntax")

# =============================================================
datePicker = None

def is_pt_date_view(view, pt):
    return 'source.orgdatepicker' in view.scope_name(pt)

def onMouse(pt, view, edit):
    if(not is_pt_date_view(view, pt)):
    	return
    row, col = view.rowcol(pt)
    if(datePicker):
    	datePicker.MapRowColToNewDate(row,col)
    # TODO Convert point back to a date and push that into
    #      the input box.

def SetupMouse():
	evt.Get().on("orgmouse",onMouse)


class OrgDatePickerCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		global datePicker
		datePicker = DatePicker()
		datePicker.Show(datetime.datetime.now(),None)

class OrgDatePickerNextDayCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		global datePicker
		datePicker.MoveNextDay()

class OrgDatePickerPrevDayCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		global datePicker
		datePicker.MovePrevDay()

class OrgDatePickerPrevWeekCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		global datePicker
		datePicker.MovePrevWeek()

class OrgDatePickerNextWeekCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		global datePicker
		datePicker.MoveNextWeek()

class OrgDatePickerPrevMonthCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		global datePicker
		datePicker.MovePrevMonth()

class OrgDatePickerNextMonthCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		global datePicker
		datePicker.MoveNextMonth()

def Pick(onDone):
	global datePicker
	datePicker = DatePicker()
	datePicker.Show(datetime.datetime.now(), onDone)
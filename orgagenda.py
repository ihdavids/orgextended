import re
import os
import time
import sublime, sublime_plugin
import datetime
import fnmatch
import OrgExtended.orgparse.node as node
import OrgExtended.orgparse.date as orgdate
import OrgExtended.orgutil.util as util
import OrgExtended.orgutil.navigation as nav
import OrgExtended.orgutil.template as templateEngine
import logging
import sys
import traceback 
import OrgExtended.orgfolding as folding
import OrgExtended.orgdb as db
import OrgExtended.orgdatepicker as dpick
import OrgExtended.asettings as sets
import OrgExtended.pymitter as evt
import calendar

import dateutil.rrule as dr
import dateutil.parser as dp
import dateutil.relativedelta as drel

log = logging.getLogger(__name__)
AGENDA_VIEW = "Org Mode Agenda"
TODO_VIEW   = "Org Todos"

ViewMappings = {}

def FindMappedView(view):
    if(view.name() in ViewMappings):
        return ViewMappings[view.name()]
    log.debug("Could not find view named: " + view.name())
    return None

def move_file_other_group(myview, view):
    window = sublime.active_window()
    if (window.num_groups() < 2):
        #self.window.run_command('clone_file')
        window.set_layout({
            "cols": [0.0, 0.5, 1.0],
            "rows": [0.0, 1.0],
            "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]
            })
        mygroup    = 0
        othergroup = 1
    else:
        window.focus_view(view)
        mygroup    = 1
        othergroup = 0
        if (window.get_view_index(myview)[0] == 0):
            othergroup = 1
            mygroup    = 0
    window.focus_view(view)
    window.run_command('move_to_group', {'group': othergroup})
    window.run_command('focus_group', {'group': mygroup})
    window.focus_view(myview)
        #view0 = self.window.active_view_in_group(0)
        #view1 = self.window.active_view_in_group(1)

        # Same file open in each of the two windows, cull to 1 if possible
        #if (view0.file_name() == view1.file_name()):
        #    self.window.focus_view(view1)

#class CloneFileToNewViewCommand(sublime_plugin.WindowCommand):
#    def run(self):

def get_view_for_silent_edit_file(file):
    # First check all sheets for this file.
    window = sublime.active_window()
    view = window.find_open_file(file.filename)
    if(view):
        return view
    # Okay the file is not opened, we have to open it
    # but we don't want it having focus
    # So keep the old view so we can refocus just to
    # be sure.
    currentView = window.active_view()
    view = window.open_file(file.filename, sublime.ENCODED_POSITION)
    window.focus_view(currentView)
    return view

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
    view.set_syntax_file("Packages/OrgExtended/orgagenda.sublime-syntax")
    ViewMappings[view.name()] = mapped
    return view


def IsPhone(n):
    return n and n.todo and "PHONE" in n.todo

def IsMeeting(n):
    return n and n.todo and "MEETING" in n.todo

def IsNote(n):
    return n and n.todo and "NOTE" in n.todo

def IsTodo(n):
    return n.todo and n.todo in n.env.todo_keys

def IsDone(n):
    return n.todo and n.todo in n.env.done_keys

def IsProjectTask(n):
    return (IsTodo(n) and n.parent and (n.parent.is_root() or IsTodo(n.parent)))

def IsBlockedProject(n):
    if(IsTodo(n) and n.num_children > 0):
        isProject = False
        isBlocked = True
        for c in n.children:
            if(IsTodo(c)):
                isProject = True
            if(c.todo and c.todo == 'NEXT'):
                isBlocked = False
        return isProject and isBlocked
    else:
        return False

def IsProject(n):
    #if(n.heading == "Project1"):
    #    print("CHILDREN: " + str(n.num_children))
    #    for c in n.children:
    #        print(c.heading)
    #        if(IsTodo(c)):
    #            print("FOUND TASK")
    if(IsTodo(n) and n.num_children > 0):
        for c in n.children:
            if(IsTodo(c)):
                return True
    return False

def IsTodaysDate(check, today):
    if(not type(check) == datetime.date):
        check = check.date()
    if(not type(today) == datetime.date):
        today = today.date()
    return today == check

def IsToday(n, today):
    if(n.scheduled):
        if(n.scheduled.repeating):
            next = n.scheduled.next_repeat_from_today
            return IsTodaysDate(next, today)
        else:
            return n.scheduled.has_overlap(today)
    return False

def IsAllDay(n):
    if(not n.scheduled):
        return False
    if(n.scheduled.repeating):
        dt = n.scheduled.next_repeat_from_today
        if(dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0):
            return True
        else:
            return False
    else:
        if(n.scheduled.has_end()):
            return False
        if(n.scheduled.has_time()):
            return False
        return True


def IsInHour(n, hour):
    if(not n or not n.scheduled):
        return False

    if(not n.scheduled.has_time()):
        return False

    if(n.scheduled.repeating):
        next = n.scheduled.next_repeat_from_today
        return next.hour == hour
    s = n.scheduled.start
    e = n.scheduled.end
    if(not e):
        # TODO Make this configurable
        e = s + datetime.timedelta(minutes=30)
    # Either this task is a ranged task OR it is a single point task
    # Ranged tasks have to fit within the hour, point tasks have to 
    if( Overlaps(s.hour*60 + s.minute, e.hour*60 + e.minute, hour*60, hour*60 + 59)):
        return True
    #if((not n.scheduled.end and n.scheduled.start.hour == hour) 
    #    or 
    #    (n.scheduled.end and n.scheduled.start.hour >= hour and n.scheduled.end.hour <= hour)):
    #    return True
    return False


def Overlaps(s,e,rs,re):
    # s | e |
    # +---+
    if(s <= rs and e >= rs and e <= re):
        return True
    # | s | e
    #   +---+
    if(s >= rs and s < re and e >= re):
        return True
    # | s  e |
    #   +-+
    if(s >= rs and e <= re):
        return True
    # s |    | e
    # +-------+
    if(s <= rs and e >= re):
        return True
    return False

def IsInHourAndMinute(n, hour, mstart, mend):
    if(not n.scheduled):
        return False

    if(not n.scheduled.has_time()):
        return False

    if(n.scheduled.repeating):
        next = n.scheduled.next_repeat_from_today
        return next.hour == hour
    s = n.scheduled.start
    e = n.scheduled.end
    if(not e):
        # TODO Make this configurable
        e = s + datetime.timedelta(minutes=30)

    # Either this task is a ranged task OR it is a single point task
    # Ranged tasks have to fit within the hour, point tasks have to 
    if( Overlaps(s.hour*60 + s.minute, e.hour*60 + e.minute, hour*60 + mstart, hour*60 + mend)):
        return True
    return False

def distanceFromStart(n, hour, minSlot):
    rv = 5*(hour - n.scheduled.start.hour) + (minSlot - int(n.scheduled.start.minute/12))
    return rv

# ================================================================================
# IDEA Make a base class that has all the functionality needed to
#      render an agenda view. Then create an agenda folder with
#      all my views, like dynamic blocks.
#
#      The goal being to allow people to extend and create custom
#      agenda views from their user folder, without having to
#      write all the "stuff"
#
#      Also create a BUNCH of filters that filter by tag, properties
#      and other things so there are example versions of each.
class AgendaBaseView:
    def __init__(self, name, setup=True, **kwargs):
        self.name = name
        self.SetTagFilter(kwargs)
        self.SetPriorityFilter(kwargs)
        self.hasclock = "hasclock" in kwargs
        self.hasclose = "hasclose" in kwargs
        self.hasdeadline = "hasdeadline" in kwargs
        self.hasschedule = "hasschedule" in kwargs
        self.noclock = "noclock" in kwargs
        self.noclose = "noclose" in kwargs
        self.nodeadline = "nodeadline" in kwargs
        self.noschedule = "noschedule" in kwargs

        if(setup):
            self.SetupView()
        else:
            self.BasicSetup()

    def BasicSetup(self):
        self.UpdateNow()
        self.entries = []

    def SetPriorityFilter(self,kwargs):
        if("priorityfilter" in kwargs):
            self._priorityFilter = kwargs["priorityfilter"]
        else:
            self._priorityFilter = None
            return
        self._inPriorityTags     = []
        self._oneofPriorityTags  = []
        self._outPriorityTagsags    = []
        tags = self._priorityFilter.split(' ')
        for tag in tags:
            tag = tag.strip()
            if not tag or len(tag) <= 0:
                continue
            m = RE_IN_OUT_TAG.search(tag)
            if(m):
                inout = m.group('inout')
                tagdata = m.group('tag')
                if(not inout or inout == '+'):
                    self._inPriorityTags.append(tagdata.strip())
                elif(inout == '|'):
                    self._oneofPriorityTags.append(tagdata.strip())
                else:
                    self._outPriorityTags.append(tagdata.strip())

    def SetTagFilter(self,kwargs):
        if("tagfilter" in kwargs):
            self._tagfilter = kwargs["tagfilter"]
        else:
            self._tagfilter = None
            return
        self._intags     = []
        self._oneoftags  = []
        self._outtags    = []
        tags = self._tagfilter.split(' ')
        for tag in tags:
            tag = tag.strip()
            if not tag or len(tag) <= 0:
                continue
            m = RE_IN_OUT_TAG.search(tag)
            if(m):
                inout = m.group('inout')
                tagdata = m.group('tag')
                if(not inout or inout == '+'):
                    self._intags.append(tagdata.strip())
                elif(inout == '|'):
                    self._oneoftags.append(tagdata.strip())
                else:
                    self._outtags.append(tagdata.strip())

    def MatchHas(self, node):
        if(self.hasclock and not n.clock):
            return False
        if(self.hasdeadline and not n.deadline):
            return False
        if(self.hasclose and not n.closed):
            return False
        if(self.hasschedule and not n.scheduled):
            return False
        if(self.noclock and n.clock):
            return False
        if(self.nodeadline and n.deadline):
            return False
        if(self.noclose and n.closed):
            return False
        if(self.noschedule and n.scheduled):
            return False
        return True

    def MatchTags(self, node):
        if(not self._tagfilter):
            return True
        if(self._intags and len(self._intags) > 0 and not all(elem in node.tags  for elem in self._intags)):
            return False
        if(self._outtags and any(elem in node.tags for elem in self._outtags)):
            return False
        if(self._oneoftags and len(self._oneoftags) > 0 and not any(elem in node.tags for elem in self._oneoftags)):
            return False
        return True

    def MatchPriorities(self, node):
        if(not self._priorityFilter):
            return True
        if(self._inPriorityTags and len(self._inPriorityTags) > 0 and not all(elem in node.priority  for elem in self._inPriorityTags)):
            return False
        if(self._outPriorityTags and any(elem in node.priority for elem in self._outPriorityTags)):
            return False
        if(self._oneofPriorityTags and len(self._oneofPriorityTags) > 0 and not any(elem in node.priority for elem in self._oneofPriorityTags)):
            return False
        return True

    def SetupView(self):
        self.view = CreateUniqueViewNamed(self.name, self)
        self.view.set_read_only(True)
        self.view.set_scratch(True)
        self.view.set_name(self.name)
        self.BasicSetup()
        self.FilterEntries()
        # Keep ourselves attached to this agenda
        # This doesn't work BOO
        self.view.agenda = self

    def DoRenderView(self,edit):
        self.StartEditing()
        self.RenderView(edit)
        self.DoneEditing()


    def InsertAgendaHeading(self, edit):
        if(hasattr(self,'_tagfilter') and self._tagfilter):
            self.view.insert(edit, self.view.size(), self.name + "\t\t TAGS( " + self._tagfilter + " )\n")
        else:
            self.view.insert(edit, self.view.size(), self.name + "\n")

    def UpdateNow(self, now=None):
        if(now == None):
            self.now = datetime.datetime.now()
        else:
            self.now = now
            self.entries = []
            self.FilterEntries()

    # You have to bookend your editing session with these
    def StartEditing(self):
        self.view.set_read_only(False)

    def DoneEditing(self):
        self.view.set_read_only(True)

    def RestoreCursor(self, pos):
        # Restore the cursor
        self.view.sel().clear()
        self.view.sel().add(pos)

    def AddEntry(self, node, file):
        self.entries.append({"node": node, "file": file})

    def MarkEntryAt(self, entry):
        if(not 'at' in entry):
            entry['at'] = []
        entry['at'].append(self.view.rowcol(self.view.size())[0])
    
    def MarkEntryAtRegion(self, entry, reg):
        if(not 'at' in entry):
            entry['at'] = []
        entry['at'].append(reg)

    def At(self, row, col):
        for e in self.entries:
            if 'at' in e:
                for  ea in e['at']:
                    if(type(ea) == int):
                        if(ea == row):
                            return (e['node'], e['file'])
                    elif(type(ea) == sublime.Region):
                        if(ea.contains(self.view.text_point(row,col))):
                            return (e['node'], e['file'])
        return (None, None)

    def Clear(self, edit):
        self.StartEditing()
        self.view.erase(edit, sublime.Region(0,self.view.size()))
        self.DoneEditing()

    # ----------------------------------------------
    # These are user extended views!
    def RenderView(self, edit):
        pass

    def FilterEntries(self):
        for file in db.Get().Files:
            #if(not "habits" in file.filename):
            #    continue
            #print("AGENDA: " + file.filename + " " + file.key)
            for n in file.org[1:]:
                if(self.MatchHas(n) and self.MatchPriorities(n) and self.MatchTags(n) and self.FilterEntry(n, file)):
                    self.AddEntry(n, file)

    def FilterEntry(self, node, file):
        pass

def IsBeforeNow(n, now):
    return n.scheduled and (not n.scheduled.has_time() or n.scheduled.start.time() < now.time())

def IsAfterNow(n, now):
    return n.scheduled and n.scheduled.has_time() and n.scheduled.start.time() >= now.time()

# ============================================================ 
class CalendarView(AgendaBaseView):
    def __init__(self, name, setup=True,**kwargs):
        super(CalendarView, self).__init__(name, setup, **kwargs)
        self.dv = dpick.DateView("orgagenda.now")

    def UpdateNow(self, now=None):
        if(now == None):
            self.now = datetime.datetime.now()
        else:
            self.now = now
            self.dv.MoveCDateToDate(self.now)

    def AddRepeating(self, date):
        self.dv.AddToDayHighlights(date, "repeat", "orgagenda.blocked")

    def AddTodo(self, date):
        self.dv.AddToDayHighlights(date, "todo", "orgagenda.todo", sublime.DRAW_NO_FILL)
    #def AddToDayHighlights(self, date, key, hightlight, drawtype = sublime.DRAW_NO_OUTLINE):
    def RenderView(self, edit):
        self.InsertAgendaHeading(edit)
        self.dv.SetView(self.view)
        self.dv.Render(self.now)
        toHighlight = []
        for entry in self.entries:
            n = entry['node']
            if(n.scheduled.start.month >= (self.now.month-1) and n.scheduled.start.month <= (self.now.month+1)):
                self.AddTodo(n.scheduled.start)
            if(n.scheduled.repeating):
                next = n.scheduled.next_repeat_from_today
                if(next.month >= (self.now.month-1) and next.month <= (self.now.month+1)):
                    self.AddRepeating(next)

    def FilterEntry(self, n, filename):
        return IsTodo(n) and not IsProject(n) and n.scheduled

def bystartdate(a, b):
    if a.scheduled.start > b.scheduled.start:
        return 1
    if a.scheduled.start < b.scheduled.start:
        return -1
    return 0

def bystartdatekey(a):
    return a.scheduled.start

def bystartnodedatekey(a):
    n = a['node']
    return n.scheduled.start

# ============================================================ 
class WeekView(AgendaBaseView):
    def __init__(self, name, setup=True,**kwargs):
        super(WeekView, self).__init__(name, setup, **kwargs)


    def HighlightTime(self, date):
        reg = self.DateToRegion(date)
        style = self.dayhighlight
        if(style == None):
            style = "orgdatepicker.monthheader"
        self.output.add_regions("curweek",[reg],style,"",sublime.DRAW_NO_OUTLINE)   

    def InsertTimeHeading(self, edit, hour):
        self.startOffset = 9
        self.cellSize    = 5
        pt = self.view.size()
        row, c = self.view.rowcol(pt)
        header = "         0    1    2    3    4    5    6    7    8    9    10   11   12   13   14   15   16   17   18   19   20   21   22   23  \n"
        self.view.insert(edit, self.view.size(), header)
        col = self.startOffset + hour*self.cellSize
        s = self.view.text_point(row,col)
        e = self.view.text_point(row,col+2)
        reg = sublime.Region(s, e)
        style = "orgagenda.now"
        self.view.add_regions("curw",[reg],style,"",sublime.DRAW_NO_OUTLINE)   

    def InsertDay(self, name, date, edit):
        pt = self.view.size()
        row, c = self.view.rowcol(pt)
        if(date.day == datetime.datetime.now().day):
            if(date.day == self.now.day):
                self.view.insert(edit, self.view.size(),"@" + name + " " + "{0:2}".format(date.day) + "W[")
            else:
                self.view.insert(edit, self.view.size(),"#" + name + " " + "{0:2}".format(date.day) + "W[")
        elif(date.day == self.now.day):
            self.view.insert(edit, self.view.size(),"&" + name + " " + "{0:2}".format(date.day) + "W[")
        else:
            self.view.insert(edit, self.view.size()," " + name + " " + "{0:2}".format(date.day) + "W[")

        daydata = []
        for entry in self.entries:
            n = entry['node']
            if(n.scheduled.start.day == date.day):
                daydata.append(entry)
        daydata.sort(key=bystartnodedatekey)

        lastMatchStart = 0
        lastMatch      = None
        lastMatchEntry = None
        matchCount     = 0
        doneMatchCount = 0
        for hour in range(0,24):
            for minSlot in range(0,self.cellSize):
                match = None
                matche = None
                for entry in daydata:
                    n = entry['node']
                    if(IsInHourAndMinute(n, hour, minSlot*12, (minSlot+1)*12)):
                        match = n
                        matche = entry
                if(lastMatch != match and lastMatch != None):
                    s = self.view.text_point(row,lastMatchStart)
                    e = self.view.text_point(row,self.startOffset + hour*self.cellSize + minSlot)
                    reg = sublime.Region(s, e)
                    if(IsDone(lastMatch)):
                        style = "orgagenda.week.done." + str(doneMatchCount)
                        doneMatchCount = (doneMatchCount + 1) % 2
                        self.MarkEntryAtRegion(lastMatchEntry,reg)
                        self.view.add_regions("week_done_" + str(date.day) + "_" + str(hour) + "_" + str(minSlot),[reg],style,"", sublime.DRAW_SQUIGGLY_UNDERLINE)   
                    else:
                        style = "orgagenda.week." + str(matchCount)
                        matchCount = (matchCount + 1) % 10
                        self.MarkEntryAtRegion(lastMatchEntry,reg)
                        self.view.add_regions("week_" + str(date.day) + "_" + str(hour) + "_" + str(minSlot),[reg],style,"",sublime.DRAW_NO_FILL)   
                if(match != None):
                    if(lastMatch != match):
                        lastMatch      = match
                        lastMatchEntry = matche
                        lastMatchStart = self.startOffset + hour*self.cellSize + minSlot
                    d = distanceFromStart(match, hour, minSlot)
                    # If the time slot is larger than the name we space pad it
                    c = " "
                    if(d < len(match.heading) and d >= 0):
                        c = match.heading[d:d+1]
                    self.view.insert(edit, self.view.size(), c)
                else:
                    if(lastMatch != match):
                        lastMatch      = match
                        lastMatchStart = self.startOffset + hour*self.cellSize + minSlot
                        lastMatchEntry = matche
                    if(minSlot < 4):
                        self.view.insert(edit, self.view.size(), ".")
                    else:
                        self.view.insert(edit, self.view.size(), "_")
        self.view.insert(edit, self.view.size(),"]\n")

    def RenderView(self, edit):
        self.InsertAgendaHeading(edit)
        self.InsertTimeHeading(edit,self.now.hour)
        toHighlight = []
        #print(str(self.now))
        wday   = self.now.weekday()
        # Adjust for Sunday being day 6 and we start with dunday
        if(wday >= 6):
            wday = -1
        wstart = self.now + datetime.timedelta(days=-(wday+1))
        dayNames  = ["Sun","Mon", "Tue", "Wed", "Thr", "Fri", "Sat"]
        dayOffset = sets.Get("agendaFirstDay",0)
        numDays   = sets.Get("agendaWeekViewNumDays",7)
        for i in range(0,numDays):
            index = dayOffset + i
            if(index == 0):
                self.InsertDay(dayNames[index % len(dayNames)], wstart, edit)
            else:
                self.InsertDay(dayNames[index % len(dayNames)], wstart + datetime.timedelta(days=index) , edit)

    def FilterEntry(self, n, filename):
        return (IsTodo(n) or IsDone(n)) and not IsProject(n) and n.scheduled


# ============================================================ 
class AgendaView(AgendaBaseView):
    def __init__(self, name, setup=True, **kwargs):
        super(AgendaView, self).__init__(name, setup, **kwargs)
        self.blocks = [None,None,None,None,None,None,None]
        self.sym     = ("$","@","!","#","%","^","&")
        self.symUsed = [-1,-1,-1,-1,-1,-1,-1]

    def RenderDateHeading(self, edit, now):
        headerFormat = sets.Get("agendaHeaderFormat","%A \t%d %B %Y")
        self.view.insert(edit, self.view.size(), now.strftime(headerFormat) + "\n\n")

    def BuildHabitDisplay(self, n):
        if(n.scheduled and n.get_property("STYLE",None)):
            #OrgDateRepeatedTask
            repeats = n.repeated_tasks
            habitbar = "[_____________________]"
            hb = list(habitbar) 
            # not schedule but done
            # not schedule not done
            # scheduled but not done
            # scheduled but last day
            # late
            # done
            if(repeats):
                start = self.now-drel.relativedelta(days=20)
                cur = self.now-drel.relativedelta(days=21)
                while(cur < self.now):
                   cur = n.scheduled.next_repeat_from(cur)
                   if(cur < self.now):
                        diff = (self.now - cur).days
                        diff = 21 - diff
                        hb[diff] = '.'
                for i in range(0,21):
                    cur = start + drel.relativedelta(days=i)
                    for r in repeats:
                        if r.has_overlap(cur):
                            hb[i+1] = '*'
                pass
            return "H" + ''.join(hb)
        return ""

    def GetUnusedSymbol(self, blk):
        start = 0
        for i in range(0,len(self.symUsed)):
            if(self.symUsed[i] >= 0):
                start = i
                break
        for i in range(start,len(self.symUsed)):
            if(self.symUsed[i] < 0):
                self.symUsed[i] = blk
                return i
        return -1

    def ReleaseSymbol(self, blk):
        for i in range(0,len(self.symUsed)):
            if(self.symUsed[i] == blk):
                self.symUsed[i] = -1
                break

    def FindSymbol(self, blk):
        for i in range(0,len(self.symUsed)):
            if(self.symUsed[i] == blk):
                return i
        return 0


    def ClearAgendaBlocks(self,h):
        for i in range(0, len(self.blocks)):
            n = self.blocks[i]
            if(not IsInHour(n, h)):
                self.ReleaseSymbol(i)
                self.blocks[i] = None

    def UpdateWithThisBlock(self, n, h):
        idx = -1
        for i in range(0, len(self.blocks)):
            if(idx == -1 and self.blocks[i] == None):
                idx = i
            if(self.blocks[i] == n):
                idx = -1
                return i
        if(idx != -1):
            self.blocks[idx] = n
            return idx
        return 0

    def GetAgendaBlocks(self,n,h):
        out = ""
        if(n != None):
            symIdx = self.GetUnusedSymbol(0)
            self.ClearAgendaBlocks(h)
            myIdx = self.UpdateWithThisBlock(n, h)
            self.symUsed[symIdx] = myIdx
        else:
            self.ClearAgendaBlocks(h)
        spaceSym = "."
        for i in range(0, len(self.blocks)):
            if(self.blocks[i]):
                spaceSym = " "
        if(spaceSym == "."):
            out = ".."
        for i in range(0, len(self.blocks)):
            if(not self.blocks[i]):
                out = out + spaceSym
            else:
                symIdx = self.FindSymbol(i)
                out = out + self.sym[symIdx]
        return out

    def RenderAgendaEntry(self,edit,filename,n,h):
        view = self.view
        view.insert(edit, view.size(), "{0:12} {1:02d}:{2:02d}B[{6}] {3} {4:55} {5}\n".format(filename, h, n.scheduled.start.minute, n.todo, n.heading, self.BuildHabitDisplay(n), self.GetAgendaBlocks(n,h)))


    def RenderView(self, edit):
        self.InsertAgendaHeading(edit)
        self.RenderDateHeading(edit, self.now)
        view     = self.view
        dayStart = sets.Get("agendaDayStart",6)
        dayEnd   = sets.Get("agendaDayEnd",19)  
        allDat = []
        before = True
        for h in range(dayStart, dayEnd):
            didNotInsert = True
            if(self.now.hour == h):
                foundItems = []
                for entry in self.entries:
                    n = entry['node']
                    #filename = entry['file'].AgendaFilenameTag()
                    if(IsBeforeNow(n, self.now) and IsInHour(n, h)):
                        if(not 'found' in entry):
                            foundItems.append(entry)
                            entry['found'] = 'b'
                if(len(foundItems) > 0):
                    foundItems.sort(key=bystartnodedatekey)
                    for it in foundItems:
                        n = it['node']
                        filename = it['file'].AgendaFilenameTag()
                        self.MarkEntryAt(it)
                        self.RenderAgendaEntry(edit,filename,n,h)
                        didNotInsert = False
                view.insert(edit, view.size(), "{0:12} {1:02d}:{2:02d} - - - - - - - - - - - - - - - - - - - - - \n".format("now =>", self.now.hour, self.now.minute) )
                foundItems = []
                for entry in self.entries:
                    n = entry['node']
                    #filename = entry['file'].AgendaFilenameTag()
                    if(IsAfterNow(n, self.now) and IsInHour(n, h)):
                        if(not 'found' in entry or entry['found'] == 'b'):
                            foundItems.append(entry)
                            entry['found'] = 'a'
                if(len(foundItems) > 0):
                    foundItems.sort(key=bystartnodedatekey)
                    for it in foundItems:
                        n = it['node']
                        filename = it['file'].AgendaFilenameTag()
                        self.MarkEntryAt(it)
                        self.RenderAgendaEntry(edit,filename,n,h)
                        didNotInsert = False
                before = False
            else:
                for entry in self.entries:
                    n = entry['node']
                    filename = entry['file'].AgendaFilenameTag()
                    if(IsInHour(n, h) and (not 'found' in entry or (not before and entry['found'] == 'b'))):
                        if(before):
                            entry['found'] = 'b'
                        else:
                            entry['found'] = 'a'
                        self.MarkEntryAt(entry)
                        self.RenderAgendaEntry(edit,filename,n,h)
                        didNotInsert = False
            if(didNotInsert):
                empty = " " * 12
                blocks = self.GetAgendaBlocks(None,h)
                sep = ""
                esep = " "
                if(not '.' in blocks):
                    sep = "B["
                    esep = "]"
                view.insert(edit, view.size(), "{0:12} {1:02d}:00{3}{2}{4}---------------------\n".format(empty, h, blocks, sep, esep))
        view.insert(edit,view.size(),"\n")
        for entry in self.entries:
            n = entry['node']
            filename = entry['file'].AgendaFilenameTag()
            if(IsAllDay(n)):
                self.MarkEntryAt(entry)
                view.insert(edit, view.size(), "{0:12} {1} {2:69} {3}\n".format(filename, n.todo, n.heading, self.BuildHabitDisplay(n)))

    def FilterEntry(self, node, file):
        return (IsTodo(node) and IsToday(node, self.now))

RE_IN_OUT_TAG = re.compile('(?P<inout>[|+-])?(?P<tag>[^ ]+)')
# ================================================================================
class TodoView(AgendaBaseView):
    def __init__(self, name, setup=True, **kwargs):
        super(TodoView, self).__init__(name, setup, **kwargs)

    def RenderView(self, edit):
        self.InsertAgendaHeading(edit)
        for entry in self.entries:
            n        = entry['node']
            filename = entry['file'].AgendaFilenameTag()
            self.MarkEntryAt(entry)
            self.RenderEntry(n, filename, edit)

    def RenderEntry(self, n, filename, edit):
        self.view.insert(edit, self.view.size(), "{0:15} {1:12} {2}\n".format(filename, n.todo, n.heading))

    def FilterEntry(self, n, filename):
        return IsTodo(n) and not IsProject(n)

# ================================================================================
class ProjectsView(TodoView):
    def __init__(self, name, setup=True, **kwargs):
        super(ProjectsView, self).__init__(name, setup, **kwargs)

    def FilterEntry(self, n, filename):
        return IsProject(n) and not IsBlockedProject(n)

# ================================================================================
class BlockedProjectsView(TodoView):
    def __init__(self, name, setup=True, **kwargs):
        super(BlockedProjectsView, self).__init__(name, setup, **kwargs)

    def FilterEntry(self, n, filename):
        return IsBlockedProject(n)

# ================================================================================
class LooseTasksView(TodoView):
    def __init__(self, name, setup=True, **kwargs):
        super(LooseTasksView, self).__init__(name, setup, **kwargs)

    def FilterEntry(self, n, filename):
        return IsTodo(n) and not IsProject(n) and not IsProjectTask(n)


# ================================================================================
class NextTasksProjectsView(TodoView):
    def __init__(self, name, setup=True, **kwargs):
        super(NextTasksProjectsView, self).__init__(name, setup, **kwargs)

    # TODO Print project and then the next task
    def RenderView(self, edit):
        self.InsertAgendaHeading(edit)
        newEntries = []
        for entry in self.entries:
            n        = entry['node']
            filename = entry['file'].AgendaFilenameTag()
            self.MarkEntryAt(entry)
            self.view.insert(edit, self.view.size(), "{0:15} {1:12} {2}\n".format(filename,"-------", n.heading))
            #self.RenderEntry(n, filename, edit)
            for c in n.children:
                if(c.todo and c.todo == "NEXT"):
                    nentry = {'node': c, 'file': entry['file']}
                    newEntries.append(nentry)
                    self.MarkEntryAt(nentry)
                    self.view.insert(edit, self.view.size(), "{0:15} {1:12} {2}\n".format(" ", c.todo, c.heading))
                    #self.RenderEntry(c, filename, edit)
        for e in newEntries:
            self.entries.append(e)
                    
    def FilterEntry(self, n, filename):
        return IsProject(n) and not IsBlockedProject(n)


# ================================================================================
class NoteView(TodoView):
    def __init__(self, name, setup=True,**kwargs):
        super(NoteView, self).__init__(name, setup, **kwargs)

    def FilterEntry(self, n, filename):
        return IsNote(n) and not IsProject(n) and not IsProjectTask(n)

# ================================================================================
class PhoneView(TodoView):
    def __init__(self, name, setup=True,**kwargs):
        super(PhoneView, self).__init__(name, setup, **kwargs)

    def FilterEntry(self, n, filename):
        return IsPhone(n) and not IsProject(n) and not IsProjectTask(n) and self.MatchTags(n)

# ================================================================================
class MeetingView(TodoView):
    def __init__(self, name, setup=True,**kwargs):
        super(MeetingView, self).__init__(name, setup, **kwargs)

    def FilterEntry(self, n, filename):
        return IsMeeting(n) and not IsProject(n) and not IsProjectTask(n) and self.MatchTags(n)

# ================================================================================
class CompositeViewListener(sublime_plugin.ViewEventListener):

    @classmethod
    def is_applicable(cls, settings):
        return "orgagenda" in settings.get("color_scheme","not here")

    def __init__(self, view):
        super(CompositeViewListener, self).__init__(view)
        self.agenda = FindMappedView(self.view)
        self.phantoms = []

    def clear_phantoms(self):
        for f in self.phantoms:
            self.view.erase_phantoms(f)
        self.phantoms = []

    def on_hover_done(self):
        self.clear_phantoms()
    
    def on_hover(self, point, hover_zone):
        if(hover_zone == sublime.HOVER_TEXT):
            row,col = self.view.rowcol(point)
            n, f = self.agenda.At(row, col)
            if(n and f):
                self.clear_phantoms()
                line = self.view.line(point)
                reg = sublime.Region(point, line.end())
                body = """
                <body id="agenda-week-popup">
                <style>
                    div.block {{
                        display: block;
                        background-color: #333333;
                        border-style: solid;
                        border: 1px;
                        border-color: #666666;
                    }}
                    div.heading {{
                        color: #880077;
                        padding: 5px;
                        font-size: 20px;
                        font-weight: bold;
                        }}
                    div.file {{
                        color: grey;
                        padding-left: 5px;
                        font-size: 15px;
                        }}
                </style>
                <div class="block"/>
                <div class="heading">{0}</div>
                <div class="file">{1}</div>
                </div>
                </body>
                """.format(n.heading,f.filename)

                self.view.add_phantom(n.heading, reg, body, sublime.LAYOUT_INLINE)
                #sublime.Phantom(sublime.Region(point, point), "<html><body>" + n.heading + "</body></html>",sublime.LAYOUT_INLINE, None) 
                self.phantoms.append(n.heading)
                print(n.heading)
                sublime.set_timeout(self.on_hover_done, 1000*2) 

# ================================================================================
# ORG has this custom composite view feature.
# I want that. Make a view up of a couple of views.
class CompositeView(AgendaBaseView):
    def __init__(self, name, views):
        self.agendaViews = views
        super(CompositeView, self).__init__(name)
        self.SetupView()

    def RenderView(self, edit):
        first = True
        for v in self.agendaViews:
            if not first:
                self.view.insert(edit, self.view.size(), ("=" * 75) + "\n")
            first = False
            v.view = self.view
            v.RenderView(edit)
        # These get updated when rendered
        self.entries = []
        for v in self.agendaViews:
            self.entries += v.entries

    def UpdateNow(self, now=None):
        if(now == None):
            self.now = datetime.datetime.now()
        else:
            self.now = now
        for v in self.agendaViews:
            v.UpdateNow(now)

    def FilterEntries(self):
        self.entries = []
        for v in self.agendaViews:
            v.entries = []
            v.FilterEntries()
            self.entries += v.entries

    def At(self, row, col):
        for av in self.agendaViews:
            n, f  = av.At(row,col)
            if(n and f):
                return (n,f)
        return (None, None)

# ================================================================================
class OrgTodoViewCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        todo = TodoView(TODO_VIEW)
        todo.DoRenderView(edit)

# ================================================================================
# Right now this is a composite view... Need to allow the user to define
# Their own versions of this.
class OrgAgendaDayViewCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        pos = None
        if(self.view.name() == "Agenda"):
            pos = self.view.sel()[0]
        # Save and restore the cursor
        views = [CalendarView("Calendar",False), WeekView("Week", False), AgendaView("Agenda", False), BlockedProjectsView("Blocked Projects",False), NextTasksProjectsView("Next",False), LooseTasksView("Loose Tasks",False)]
        #views = [AgendaView("Agenda", False), TodoView("Global Todo List", False)]
        agenda = CompositeView("Agenda", views)
        #agenda = AgendaView(AGENDA_VIEW)
        agenda.DoRenderView(edit)
        if(self.view.name() == "Agenda"):
            agenda.RestoreCursor(pos)
        log.info("Day view refreshed")

# ================================================================================
# Goto the file in the current window (ENTER)
class OrgAgendaGoToCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        agenda = FindMappedView(self.view)
        if(agenda):
            row, col    = self.view.curRowCol()
            n, f = agenda.At(row, col)
            if(f):
                if(n):
                    path = "{0}:{1}".format(f.filename,n.start_row + 1)
                    self.view.window().open_file(path, sublime.ENCODED_POSITION)
            else:
                log.warning("COULD NOT LOCATE AGENDA ROW")

# ================================================================================
class RunEditingCommandOnNode:
    def __init__(self, view, command):
        self.view = view
        self.command = command

    def onSaved(self):
        self.view.run_command("org_agenda_day_view")

    def onEdited(self):
        # NOTE the save here doesn't seem to be working
        # Not sure why. BUT...
        view = self.savedView
        view.run_command("save")
        sublime.set_timeout_async(lambda: self.onSaved(), 100)

    def onLoaded(self):
        view = self.savedView
        self.n.move_cursor_to(view)
        eventName = util.RandomString()
        evt.Get().once(eventName, self.onEdited)
        log.debug("Trying to run: " + self.command)
        view.run_command(self.command, {"onDone": eventName })

    def Run(self):
        agenda = FindMappedView(self.view)
        if(agenda):
            row, col  = self.view.curRowCol()
            n, f = agenda.At(row,col)
            if(f):
                if(n):
                    self.n         = n
                    self.f         = f
                    self.savedView = get_view_for_silent_edit_file(f)
                    # Give time for the document to be opened.
                    sublime.set_timeout_async(lambda: self.onLoaded(), 200)
            else:
                log.warning("COULD NOT LOCATE AGENDA ROW")

# ================================================================================
class CalendarViewRegistry:
    def __init__(self):
        self.KnownViews = {}
        self.AddView("Calendar", CalendarView)
        self.AddView("Day", AgendaView)
        self.AddView("Blocked Projects", BlockedProjectsView)
        self.AddView("Next Tasks", NextTasksProjectsView)
        self.AddView("Loose Tasks", LooseTasksView)
        self.AddView("Todos", TodoView)
        self.AddView("Notes", NoteView)
        self.AddView("Meetings", MeetingView)
        self.AddView("Phone", PhoneView)
        self.AddView("Week", WeekView)

    def AddView(self,name,cls):
        self.KnownViews[name] = cls

    def ParseArgs(self, n ):
        tokens = n.split(':')
        name = tokens[0].strip()
        args = {}
        i = 1
        while(i < len(tokens)):
            p = tokens[i].strip()
            if(len(p) > 0):
                idx = p.find(' ')
                if(idx > 0):
                    pname = p[:idx].strip()
                    pval = p[idx:].strip()
                    args[pname] = pval
                    #print(pname + " -> " + pval)
                else:
                    args[p] = True
            i += 1
        return (name, args)

    def CreateCompositeView(self,views,name="Agenda"):
        vlist = []
        for v in views:
            n, args = self.ParseArgs(v)
            vv = None
            if(args == None):
                vv = self.KnownViews[n](n, False)
            else:
                vv = self.KnownViews[n](n, False, **args)
            if(vv):
                vlist.append(vv)
        cview = CompositeView(name, vlist)
        return cview

viewRegistry = CalendarViewRegistry()


# ================================================================================
class OrgAgendaCustomViewCommand(sublime_plugin.TextCommand):
    def run(self, edit, toShow="Default"):
        pos = None
        if(self.view.name() == "Agenda"):
            pos = self.view.sel()[0]
        views = sets.Get("AgendaCustomViews",{ "Default": ["Calendar", "Week", "Day", "Blocked Projects", "Next Tasks", "Loose Tasks"]})
        views = views[toShow]
        nameOfShow = toShow
        if(toShow == "Default"):
            nameOfShow = "Agenda"
        agenda = viewRegistry.CreateCompositeView(views, nameOfShow)
        #agenda = CompositeView("Agenda", views)
        #agenda = AgendaView(AGENDA_VIEW)
        agenda.DoRenderView(edit)
        if(self.view.name() == "Agenda"):
            agenda.RestoreCursor(pos)
        log.info("Custom view refreshed")


# ================================================================================
# TODO: This is a work in progress that only lists them right now.
#       The goal is add parameters for filtered todos and support
#       multiple calendar views in the end. I should probably
#       rename the command above so we know it is intended to directly
#       select a view rather than use a quick panel.
#       I would like to add:
#       1. Vertical Week View (Org Style)
#       2. Horizontal Week View (Calendar Style)
#       3. Month View (Vim Style)
#       4. Month View Quick Highlight (My Style)
#       5. Various Filtered Todo lists.
#       6. Try an HTML version of a todo?
class OrgAgendaChooseCustomViewCommand(sublime_plugin.TextCommand):
    def on_done(self, index):
        if(index < 0):
            return
        key = self.keys[index]
        self.view.run_command("org_agenda_custom_view", { "toShow": key })
        evt.EmitIf(self.onDone)

    def run(self, edit, onDone=None):
        self.onDone = onDone
        self.views = sets.Get("AgendaCustomViews",{ "Default": ["Calendar", "Day", "Blocked Projects", "Next Tasks", "Loose Tasks"]})
        self.keys = list(self.views.keys())
        self.view.window().show_quick_panel(self.keys, self.on_done, -1, -1)

# ================================================================================
# Change the TODO status of the node.
class OrgAgendaChangeTodoCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.ed = RunEditingCommandOnNode(self.view, "org_todo_change")
        self.ed.Run()


# ================================================================================
class OrgAgendaChangePriorityCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.ed = RunEditingCommandOnNode(self.view, "org_priority_change")
        self.ed.Run()

# ================================================================================
class OrgAgendaClockInCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.ed = RunEditingCommandOnNode(self.view,"org_clock_in")
        self.ed.Run()

# ================================================================================
class OrgAgendaClockOutCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.ed = RunEditingCommandOnNode(self.view,"org_clock_out")
        self.ed.Run()

# ================================================================================
# Goto the file but in a split (SPACE)
class OrgAgendaGoToSplitCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        agenda = FindMappedView(self.view)
        if(agenda):
            row, col    = self.view.curRowCol()
            n, f = agenda.At(row,col)
            if(f):
                if(n):
                    path = "{0}:{1}".format(f.filename,n.start_row + 1)
                    newView = self.view.window().open_file(path, sublime.ENCODED_POSITION)
                    move_file_other_group(self.view, newView)
                    #sublime.set_timeout_async(lambda: move_file_other_group(self.view, newView), 100)
            else:
                log.warning("COULD NOT LOCATE AGENDA ROW")

# ================================================================================
class OrgTagFilteredTodoViewInternalCommand(sublime_plugin.TextCommand):
    def run(self,edit,tags):
        # TODO: add filtering to this and name it nicely
        todo = TodoView(TODO_VIEW + " Filtered By: " + tags,tagfilter=tags)
        todo.DoRenderView(edit)

# ================================================================================
class OrgTagFilteredTodoViewCommand(sublime_plugin.TextCommand):
    def run(self,edit):
        self.view.window().show_input_panel(
                    "Tags:",
                    "",
                    self.showTodos, None, None)

    def showTodos(self, tags):
        if(not tags):
            return
        self.view.run_command('org_tag_filtered_todo_view_internal', {"tags": tags})

# ================================================================================
class OrgAgendaGotoNextDayCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        agenda = FindMappedView(self.view)
        now = agenda.now
        now = now + datetime.timedelta(days=1)
        agenda.UpdateNow(now)
        agenda.Clear(edit)
        agenda.DoRenderView(edit)

# ================================================================================
class OrgAgendaGotoPrevDayCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        agenda = FindMappedView(self.view)
        now = agenda.now
        now = now + datetime.timedelta(days=-1)
        agenda.UpdateNow(now)
        agenda.Clear(edit)
        agenda.DoRenderView(edit)

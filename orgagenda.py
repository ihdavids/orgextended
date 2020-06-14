import re
import os
import time
import sublime, sublime_plugin
import datetime
from pathlib import Path
import fnmatch
from .orgparse.__init__ import *
import OrgExtended.orgparse.node as node
import OrgExtended.orgparse.date as orgdate
from   OrgExtended.orgparse.sublimenode import * 
import OrgExtended.orgutil.util as util
import OrgExtended.orgutil.navigation as nav
import OrgExtended.orgutil.template as templateEngine
import logging
import sys
import traceback 
import OrgExtended.orgfolding as folding
import OrgExtended.orgdb as db
from   OrgExtended.orgdatepicker import *
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
    return ViewMappings[view.name()]

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

def IsTodo(n):
    return n.todo and n.todo in n.env.todo_keys

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
    if(not n.scheduled):
        return False

    if(n.scheduled.repeating):
        next = n.scheduled.next_repeat_from_today
        return next.hour == hour
    # Either this task is a ranged task OR it is a single point task
    # Ranged tasks have to fit within the hour, point tasks have to 
    if((not n.scheduled.end and n.scheduled.start.hour == hour) 
        or 
        (n.scheduled.end and n.scheduled.start.hour >= hour and n.scheduled.end.hour <= hour)):
        return True
    return False


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
    def __init__(self, name, setup=True):
        self.name = name
        if(setup):
            self.SetupView()
        else:
            self.BasicSetup()

    def BasicSetup(self):
        self.UpdateNow()
        self.entries = []

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
        self.view.insert(edit, self.view.size(), self.name + "\n")

    def UpdateNow(self):
        self.now = datetime.datetime.now()

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
        entry['at'] = self.view.rowcol(self.view.size())[0]

    def At(self, row):
        for e in self.entries:
            if 'at' in e:
                if(e['at'] == row):
                    return (e['node'], e['file'])
        return (None, None)


    # ----------------------------------------------
    # These are user extended views!
    def RenderView(self, edit):
        pass

    def FilterEntries(self):
        for file in db.Get().Files:
            #if(not "habits" in file.filename):
            #    continue
            print("AGENDA: " + file.filename + " " + file.key)
            for n in file.org[1:]:
                if(self.FilterEntry(n, file)):
                    self.AddEntry(n, file)

    def FilterEntry(self, node, file):
        pass

def IsBeforeNow(n, now):
    return n.scheduled and (not n.scheduled.has_time() or n.scheduled.start.time() < now.time())

def IsAfterNow(n, now):
    return n.scheduled and n.scheduled.has_time() and n.scheduled.start.time() >= now.time()

class CalendarView(AgendaBaseView):
    def __init__(self, name, setup=True,tagfilter=None):
        super(CalendarView, self).__init__(name, setup)
        self.dv = DateView()


    def AddRepeating(self, date):
        self.dv.AddToDayHighlights(date, "repeat", "orgagenda.blocked", sublime.DRAW_NO_FILL)

    def AddTodo(self, date):
        self.dv.AddToDayHighlights(date, "todo", "orgagenda.todo")
    #def AddToDayHighlights(self, date, key, hightlight, drawtype = sublime.DRAW_NO_OUTLINE):
    def RenderView(self, edit):
        now = datetime.datetime.now()
        self.InsertAgendaHeading(edit)
        self.dv.SetView(self.view)
        self.dv.Render(now)
        toHighlight = []
        for entry in self.entries:
            n = entry['node']
            if(n.scheduled.start.month >= (now.month-1) and n.scheduled.start.month <= (now.month+1)):
                self.AddTodo(n.scheduled.start)
            if(n.scheduled.repeating):
                next = n.scheduled.next_repeat_from_today
                if(next.month >= (now.month-1) and next.month <= (now.month+1)):
                    self.AddRepeating(next)

    def FilterEntry(self, n, filename):
        return IsTodo(n) and not IsProject(n) and n.scheduled


class AgendaView(AgendaBaseView):
    def __init__(self, name, setup=True):
        super(AgendaView, self).__init__(name, setup)

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

    def RenderAgendaEntry(self,edit,filename,n,h):
        view = self.view
        view.insert(edit, view.size(), "{0:12} {1:02d}:{2:02d}         {3} {4:55} {5}\n".format(filename, h, n.scheduled.start.minute, n.todo, n.heading, self.BuildHabitDisplay(n)))

    def RenderView(self, edit):
        self.InsertAgendaHeading(edit)
        self.RenderDateHeading(edit, self.now)
        view     = self.view
        dayStart = sets.Get("agendaDayStart",6)
        dayEnd   = sets.Get("agendaDayEnd",19)  
        allDat = []
        for h in range(dayStart, dayEnd):
            didNotInsert = True
            if(self.now.hour == h):
                for entry in self.entries:
                    n = entry['node']
                    filename = entry['file'].AgendaFilenameTag()
                    if(IsBeforeNow(n, self.now) and IsInHour(n, h)):
                        self.MarkEntryAt(entry)
                        self.RenderAgendaEntry(edit,filename,n,h)
                        didNotInsert = False
                view.insert(edit, view.size(), "{0:12} {1:02d}:{2:02d} - - - - - - - - - - - - - - - - - - - - - \n".format("now =>", self.now.hour, self.now.minute) )
                for entry in self.entries:
                    n = entry['node']
                    filename = entry['file'].AgendaFilenameTag()
                    if(IsAfterNow(n, self.now) and IsInHour(n, h)):
                        self.MarkEntryAt(entry)
                        self.RenderAgendaEntry(edit,filename,n,h)
                        didNotInsert = False
            else:
                for entry in self.entries:
                    n = entry['node']
                    filename = entry['file'].AgendaFilenameTag()
                    if(IsInHour(n, h)):
                        self.MarkEntryAt(entry)
                        self.RenderAgendaEntry(edit,filename,n,h)
                        didNotInsert = False
            if(didNotInsert):
                empty = " " * 12
                view.insert(edit, view.size(), "{0:12} {1:02d}:00........ ---------------------\n".format(empty, h))
        view.insert(edit,view.size(),"\n")
        for entry in self.entries:
            n = entry['node']
            filename = entry['file'].AgendaFilenameTag()
            if(IsAllDay(n)):
                self.MarkEntryAt(entry)
                view.insert(edit, view.size(), "{0:12} {1} {2:69} {3}\n".format(filename, n.todo, n.heading, self.BuildHabitDisplay(n)))

    def FilterEntry(self, node, file):
        return (IsTodo(node) and IsToday(node, self.now))

RE_IN_OUT_TAG = re.compile('(?P<inout>[+-])?(?P<tag>[^ ]+)')
class TodoView(AgendaBaseView):
    def __init__(self, name, setup=True,tagfilter=None):
        self.SetTagFilter(tagfilter)
        super(TodoView, self).__init__(name, setup)

    def SetTagFilter(self,filter):
        self._tagfilter = filter
        if(not filter):
            return
        self._intags  = []
        self._outtags = []
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
                    self._intags.append(tagdata)
                else:
                    self._outtags.append(tagdata)


    def MatchTags(self, node):
        if(self._intags and len(self._intags) > 0 and not all(elem in node.tags  for elem in self._intags)):
            return False
        if(self._outtags and any(elem in node.tags for elem in self._outtags)):
            return False
        return True

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
        if(self._tagfilter):
            return IsTodo(n) and not IsProject(n) and self.MatchTags(n) 
        else:
            return IsTodo(n) and not IsProject(n)

class ProjectsView(TodoView):
    def __init__(self, name, setup=True):
        super(ProjectsView, self).__init__(name, setup)

    def FilterEntry(self, n, filename):
        return IsProject(n) and not IsBlockedProject(n)

class BlockedProjectsView(TodoView):
    def __init__(self, name, setup=True):
        super(BlockedProjectsView, self).__init__(name, setup)

    def FilterEntry(self, n, filename):
        return IsBlockedProject(n)

class LooseTasksView(TodoView):
    def __init__(self, name, setup=True):
        super(LooseTasksView, self).__init__(name, setup)

    def FilterEntry(self, n, filename):
        return IsTodo(n) and not IsProject(n) and not IsProjectTask(n)


class NextTasksProjectsView(TodoView):
    def __init__(self, name, setup=True):
        super(NextTasksProjectsView, self).__init__(name, setup)

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

    def FilterEntries(self):
        self.entries = []
        for v in self.agendaViews:
            v.entries = []
            v.FilterEntries()
            self.entries += v.entries


class OrgTodoViewCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        todo = TodoView(TODO_VIEW)
        todo.DoRenderView(edit)

# Right now this is a composite view... Need to allow the user to define
# Their own versions of this.
class OrgAgendaDayViewCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        pos = None
        if(self.view.name() == "Agenda"):
            pos = self.view.sel()[0]
        # Save and restore the cursor
        views = [CalendarView("Calendar",False), AgendaView("Agenda", False), BlockedProjectsView("Blocked Projects",False), NextTasksProjectsView("Next",False), LooseTasksView("Loose Tasks",False)]
        #views = [AgendaView("Agenda", False), TodoView("Global Todo List", False)]
        agenda = CompositeView("Agenda", views)
        #agenda = AgendaView(AGENDA_VIEW)
        agenda.DoRenderView(edit)
        if(self.view.name() == "Agenda"):
            agenda.RestoreCursor(pos)
        log.info("Day view refreshed")

# Goto the file in the current window (ENTER)
class OrgAgendaGoToCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        agenda = FindMappedView(self.view)
        if(agenda):
            row    = self.view.curRow()
            n, f = agenda.At(row)
            if(f):
                if(n):
                    path = "{0}:{1}".format(f.filename,n.start_row + 1)
                    self.view.window().open_file(path, sublime.ENCODED_POSITION)
            else:
                log.warning("COULD NOT LOCATE AGENDA ROW")

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
            row  = self.view.curRow()
            n, f = agenda.At(row)
            if(f):
                if(n):
                    self.n         = n
                    self.f         = f
                    self.savedView = get_view_for_silent_edit_file(f)
                    # Give time for the document to be opened.
                    sublime.set_timeout_async(lambda: self.onLoaded(), 200)
            else:
                log.warning("COULD NOT LOCATE AGENDA ROW")


class CalendarViewRegistry:
    def __init__(self):
        self.KnownViews = {}
        self.AddView("Calendar", CalendarView)
        self.AddView("Day", AgendaView)
        self.AddView("Blocked Projects", BlockedProjectsView)
        self.AddView("Next Tasks", NextTasksProjectsView)
        self.AddView("Loose Tasks", LooseTasksView)
        self.AddView("Todos", TodoView)

    def AddView(self,name,cls):
        self.KnownViews[name] = cls

    def CreateCompositeView(self,views):
        vlist = []
        for v in views:
            vv = self.KnownViews[v](v, False)
            vlist.append(vv)
        cview = CompositeView("Agenda", vlist)
        return cview

viewRegistry = CalendarViewRegistry()


class OrgAgendaCustomViewCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        pos = None
        if(self.view.name() == "Agenda"):
            pos = self.view.sel()[0]
        views = sets.Get("CompositeView",["Calendar", "Day", "Blocked Projects", "Next Tasks", "Loose Tasks"])
        agenda = viewRegistry.CreateCompositeView(views)
        #agenda = CompositeView("Agenda", views)
        #agenda = AgendaView(AGENDA_VIEW)
        agenda.DoRenderView(edit)
        if(self.view.name() == "Agenda"):
            agenda.RestoreCursor(pos)
        log.info("Custom view refreshed")


# Change the TODO status of the node.
class OrgAgendaChangeTodoCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.ed = RunEditingCommandOnNode(self.view, "org_todo_change")
        self.ed.Run()


class OrgAgendaChangePriorityCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.ed = RunEditingCommandOnNode(self.view, "org_priority_change")
        self.ed.Run()

class OrgAgendaClockInCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.ed = RunEditingCommandOnNode(self.view,"org_clock_in")
        self.ed.Run()

class OrgAgendaClockOutCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.ed = RunEditingCommandOnNode(self.view,"org_clock_out")
        self.ed.Run()

# Goto the file but in a split (SPACE)
class OrgAgendaGoToSplitCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        agenda = FindMappedView(self.view)
        if(agenda):
            row    = self.view.curRow()
            n, f = agenda.At(row)
            if(f):
                if(n):
                    path = "{0}:{1}".format(f.filename,n.start_row + 1)
                    newView = self.view.window().open_file(path, sublime.ENCODED_POSITION)
                    move_file_other_group(self.view, newView)
                    #sublime.set_timeout_async(lambda: move_file_other_group(self.view, newView), 100)
            else:
                log.warning("COULD NOT LOCATE AGENDA ROW")

class OrgTagFilteredTodoViewInternalCommand(sublime_plugin.TextCommand):
    def run(self,edit,tags):
        # TODO: add filtering to this and name it nicely
        todo = TodoView(TODO_VIEW + " Filtered By: " + tags,tagfilter=tags)
        todo.DoRenderView(edit)

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

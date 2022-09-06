import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
import fnmatch
import OrgExtended.orgparse.node as node
from   OrgExtended.orgparse.sublimenode import * 
import logging
import sys
import traceback 
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
import OrgExtended.pymitter as evt
import OrgExtended.orgduration as dur
import OrgExtended.orgagenda as ag
import uuid
import subprocess


log = logging.getLogger(__name__)


class OrgTimesheet(ag.TodoView):
    def __init__(self, name, setup=True, **kwargs):
        super(OrgTimesheet, self).__init__(name, False, **kwargs)

    def InsertTableHeadings(self, edit):
        self.view.insert(edit,self.view.sel()[0].begin(),"|Name|Estimate|Start|End|Dep|Assigned|Spent|X|\n|-\n")

    # Dependencies are marked with the AFTER tag or an ORDERED list.
    def GetAfter(self, n):
        dep = n.get_property("AFTER","")
        if dep and not dep == "":
            d = db.Get().FindById(dep)
            if not d:
                d = db.Get().FindByCustomId(dep)
            if d:
                dep = d
            else:
                dep = None
        if not dep or dep == "":
            if n.parent != None and not n.parent.is_root:
                orde = n.parent.get_property("ORDERED",None)
                if orde != None:
                    dep = n.get_sibling_up()
        return dep

    def GetGlobalProperty(self, name, n, ass):
        props = n.list_comment('PROPERTY',None)
        if(props):
            for i in range(0,len(props),2):
                prop = props[i]
                prop = prop.strip()
                if(prop.startswith('ASSIGNED') and len(props) > i+1):
                    ass = props[i+1]
                    return ass
        return ass

    def GetAssigned(self, n):
        ass = sets.Get("timesheetDefaultAssigned","")
        ass = self.GetGlobalProperty("ASSIGNED",n,ass)
        ass = n.get_property("ASSIGNED",ass)
        return ass

    def GetClockingData(self, n):
        if n.clock:
            return n.duration()
        return ""

    def PreprocessAfter(self):
        for entry in self.entries:
            n        = entry['node']
            dep = self.GetAfter(n)
            if dep:
                entry['after'] = dep
                index = 0
                for dp in self.entries:
                    index += 1
                    d = entry['node']
                    if d == dep:
                        entry['after_offset'] = index


    def RenderSheet(self, edit, view):
        self.view = view
        self.InsertTableHeadings(edit)
        newEntries = []
        self.PreprocessAfter()

        for entry in self.entries:
            n        = entry['node']
            filename = entry['file'].AgendaFilenameTag()
            estimate = n.get_property("EFFORT","")
            dt = None
            timestamps = n.get_timestamps(active=True,point=True,range=True)
            end = ""
            start = ""
            if timestamps and len(timestamps) > 0:
                dt = timestamps[0].start
            if n.deadline:
                dt = n.deadline.start
            if n.scheduled:
                dt = n.scheduled.start
            if dt:
                start = dt.strftime("<%Y-%m-%d>")
                if estimate != "":
                    duration = dur.OrgDuration.Parse(estimate)
                    endtm = dt + duration.timedelta()
                    end = endtm.strftime("<%Y-%m-%d>")  
                    pass
            else:
                start = ""
            done = ""
            if ag.IsDone(n):
                done = "x"

            spent = self.GetClockingData(n)
            dependenton = entry['after_offset'] if 'after_offset' in entry else ""
            # TODO: Adjust index to match table separators
            assigned = self.GetAssigned(n)
            self.view.insert(edit, self.view.sel()[0].begin(), "|{0:15}|{1:12}|{2}|{3}|{4}|{5}|{6}|{7}|\n".format(n.heading,estimate,start,end,dependenton,assigned,spent,done))

    def RenderMermaidGanttFile(self):
        filename = "C:\\Users\\ihdav\\repos\\gtd\\schedule.mermaid"
        with open(filename,"w") as f:
            self.CreateMermaidGanttFile(f)
        self.GenerateMermaidGanttChartFromFile(filename)

    def GenerateMermaidGanttChartFromFile(self, filename):
        execs = sets.Get("timesheetExed","C:\\Users\\ihdav\\node_modules\\.bin\\mmdc.ps1")
        outputFilename = ".\\schedule.png"
        #inputFilename = "D:\\Git\\notes\\worklog\\schedule.mermaid"
        commandLine = ["powershell.exe", execs, "-i", filename, "-o", outputFilename, "--width", "2500"]
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        except:
            startupinfo = None
        view = sublime.active_window().active_view()
        cwd = os.path.dirname(view.file_name())
        popen = subprocess.Popen(commandLine, universal_newlines=True, cwd=cwd, startupinfo=startupinfo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        #popen.wait()
        (o,e) = popen.communicate()
        log.debug(o)
        log.debug(e)

    # This is REALLY rough it gives us a non functional, really basic view.
    def CreateMermaidGanttFile(self,f):
        import re
        idx = 0
        f.write("gantt\n")
        f.write("\tdateFormat YYYY-MM-DD\n")
        f.write("\taxisFormat %m-%d\n")
        f.write("\ttitle Telem Schedule\n")
        f.write("\ttodayMarker off\n")
        f.write("\texcludes    weekends\n")
        curSection = None
        for entry in self.entries:
            n        = entry['node']
            filename = entry['file'].AgendaFilenameTag()
            section  = entry['section'] if 'section' in entry else None
            estimate = n.get_property("EFFORT","")
            dt = None
            timestamps = n.get_timestamps(active=True,point=True,range=True)
            end = ""
            start = ""
            duration = "1d"
            if timestamps and len(timestamps) > 0:
                dt = timestamps[0].start
            if n.deadline:
                dt = n.deadline.start
            if n.scheduled:
                dt = n.scheduled.start
            if dt:
                start = dt.strftime("%Y-%m-%d")
                if estimate != "":
                    duration = dur.OrgDuration.Parse(estimate)
                    endtm = dt + duration.timedelta()
                    end = endtm.strftime("%Y-%m-%d")  
                    pass
            else:
                start = ""
            done = False
            if ag.IsDone(n):
                done = True

            spent = self.GetClockingData(n)
            dependenton = entry['after_offset'] if 'after_offset' in entry else ""
            # TODO: Adjust index to match table separators
            assigned = self.GetAssigned(n)
            #self.view.insert(edit, self.view.sel()[0].begin(), "|{0:15}|{1:12}|{2}|{3}|{4}|{5}|{6}|{7}|\n".format(n.heading,estimate,start,end,dependenton,assigned,spent,done))
            idx += 1
            if(idx > 1):
                if(done):
                    continue
                if(curSection != section and section != None):
                    f.write("section {name}".format(name=section))
                    curSection = section
                date = start
                dep = dependenton
                prefix = ""
                if(assigned=='N'):
                        prefix = "active,"
                if(assigned == 'R'):
                    prefix = 'crit,'
                if(date == ""):
                    date = sets.Get("timesheetDefaultStartDate","2021-05-18")
                line = ""
                if(dep != None and dep != ""):
                    line = "\t{name}\t:{prefix}{idx},{start},{duration}\n".format(prefix=prefix,name=n.heading,idx=idx,start="after " + str(dep),duration=duration)
                else:
                    line = "\t{name}\t:{prefix}{idx},{start},{duration}\n".format(prefix=prefix,name=n.heading,idx=idx,start=date,duration=duration)
                f.write(line)
    def FilterEntry(self, n, filename):
        return (ag.IsDone(n) or ag.IsTodo(n)) and not ag.IsProject(n) and not ag.IsArchived(n)

# ================================================================================
class TimesheetRegistry:
    def __init__(self):
        self.KnownViews = {}
        self.AddView("Todos", OrgTimesheet)

    def AddView(self,name,cls):
        self.KnownViews[name] = cls

    # ViewName: <NAME> <ARGS> : <NAME> <ARGS>
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

    def CreateCompositeView(self,views,name="Timesheet"):
        vlist = []
        for v in views:
            n, args = self.ParseArgs(v)
            vv = None
            if(args == None):
                vv = self.KnownViews[n](n, False)
            else:
                vv = self.KnownViews[n](n, False, **args)
            if(vv):
                return vv
        return None

timesheetRegistry = TimesheetRegistry()

class OrgInsertTimesheetCommand(sublime_plugin.TextCommand):
    def run(self, edit, toShow="Default", onDone=None):
        self.onDone=onDone
        pos = self.view.sel()[0]
        ag.ReloadAllUnsavedBuffers()
        views = sets.Get("TimesheetCustomViews",{ "Default": ["Todos"]})
        views = views[toShow]
        nameOfShow = toShow
        ts = timesheetRegistry.CreateCompositeView(views, nameOfShow)
        ts.FilterEntries()
        ts.RenderSheet(edit, self.view)
        self.view.sel().clear()
        self.view.sel().add(pos)
        self.view.run_command('table_editor_next_field')
        evt.EmitIf(self.onDone)

class OrgGenerateMermaidGanttChart(sublime_plugin.TextCommand):
    def run(self, edit, toShow='Default', onDone=None ):
        self.onDone=onDone
        pos = self.view.sel()[0]
        ag.ReloadAllUnsavedBuffers()
        views = sets.Get("TimesheetCustomViews",{ "Default": ["Todos"]})
        views = views[toShow]
        nameOfShow = toShow
        ts = timesheetRegistry.CreateCompositeView(views, nameOfShow)
        ts.FilterEntries()
        ts.RenderMermaidGanttFile()
        #self.view.sel().clear()
        #self.view.sel().add(pos)
        #self.view.run_command('table_editor_next_field')
        evt.EmitIf(self.onDone)
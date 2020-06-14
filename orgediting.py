import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
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
import OrgExtended.asettings as sets
import OrgExtended.pymitter as evt
import OrgExtended.orgproperties as props
import OrgExtended.orgdatepicker as datep
import OrgExtended.orginsertselected as insSel

defaultPriorities = ["A","B","C","D","E"]

log = logging.getLogger(__name__)

# MOVING TO ANY DONE STATE:
# Support these:
#+STARTUP: lognotedone   Prompt and stored below the item with a Closing Note heading.
#+STARTUP: logdone       CLOSED: [TIMESTAMP] in LOGBOOK
# As well as configuration options
#
# PER TRANSITON MOVEMENT:
# @ - note
# ! - timestamp
# / - when leaving the state if next state doesn't log
#
# Then they go futher with: :LOGGING: WAIT(@) logrepeat properties
#
# - 1) We need the transitions recorded in the node (in the todos list)
# - 2) We need a method to insert CLOSED: and or prompt and note
# - 3) We need to track the state transitions themselves (from / to)
#
# - 4) Habits break all this with LAST_REPEAT and To From transition text.
# 


RE_CLOSED = re.compile(r"^\s*CLOSED:\s*\[.*\]")
def LocateClosed(view,node):
    for row in range(node.start_row, node.local_end_row + 1):
        pt = view.text_point(row,0)
        line = view.line(pt)
        lstr = view.substr(line)
        m = RE_CLOSED.search(lstr)
        if(m):
            return line
    return None

def InsertClosed(view, node, onDone=None):
    stamp = OrgDate.format_clock(datetime.datetime.now(),active=False)
    closedPt = LocateClosed(view,node)
    if(closedPt):
        text = node.indent() + "CLOSED: " + stamp
        view.ReplaceRegion(closedPt, text, onDone)
    else:
        row = node.start_row+1
        pt = view.text_point(row,0)
        newline = "\n" if view.isBeyondLastRow(row) else ""
        text = newline + node.indent() + "CLOSED: " + stamp + "\n"
        view.Insert(pt, text, onDone)
        #props.UpdateLogbook(view,node, "CLOSED:", stamp)

def RemoveClosed(view, node, onDone=None):
    closedPt = LocateClosed(view, node)
    if(closedPt):
        view.ReplaceRegion(closedPt.IncEnd(),"",onDone)
        #view.run_command("org_internal_replace", {"start": closedPt.begin(), "end": closedPt.end() + 1, "text": "", "onDone": onDone})
    else:
        evt.EmitIf(onDone)

def IsDoneState(node, toState):
    return toState in node.env.done_keys

def ShouldRecur(node, fromState, toState):
    if(IsDoneState(node, toState) and node.scheduled and node.scheduled.repeating):
        return True
    return False

def ShouldClose(node, fromState, toState):
    if(ShouldRecur(node,fromState,toState)):
        return False
    # NOTE: We need to get the todo transitions
    #       into this as well!
    toState = toState.strip()
    globalStartup = sets.Get("startup",[])
    startup = node.root.startup(globalStartup)
    if(IsDoneState(node, toState) and Startup.logdone in startup):
        return True

def InsertRecurrence(view, node, fromState, toState, onDone=None):
    #   - State "DONE"       from "TODO"       [2009-09-29 Tue]"
    stamp = OrgDate.format_clock(datetime.datetime.now(),active=False)
    def OnLogAdded():
        props.UpdateProperty(view, node, "LAST_REPEAT", stamp, onDone)
    props.AddLogbook(view,node, "- State {0:12} from {1:12} ".format('"' + toState + '"', '"' + fromState + '"'), stamp, evt.Make(OnLogAdded))

def InsertNote(view, node, text, fromState, toState, onDone=None):
    stamp = OrgDate.format_clock(datetime.datetime.now(),active=False)
    props.AddLogbook(view,node, "Note (to:{0},at:{1}): ".format(toState,stamp), text, onDone)

def ShouldNote(node, fromState, toState):
    if(ShouldRecur(node,fromState,toState)):
        return False
    # NOTE: We need to get the todo transitions
    #       into this as well!
    toState = toState.strip()
    globalStartup = sets.Get("startup",[])
    startup = node.root.startup(globalStartup)
    if(IsDoneState(node,toState) and Startup.lognotedone in startup):
        return True



# Use a menu to change the todo state of an item
class OrgTodoChangeCommand(sublime_plugin.TextCommand):
    def on_totally_done(self):
        evt.EmitIf(self.onDone)

    def do_recurrence_if_needed(self):
        if(ShouldRecur(self.node,self.fromState,self.newState)):
            InsertRecurrence(self.view, self.node, self.fromState, self.newState, evt.Make(self.on_totally_done))
        else:
            self.on_totally_done()

    def do_close_if_needed(self):
        if(ShouldClose(self.node,self.fromState,self.newState)):
            InsertClosed(self.view, self.node, evt.Make(self.do_recurrence_if_needed))
        else:
            RemoveClosed(self.view, self.node, evt.Make(self.do_recurrence_if_needed))

    def on_insert_note(self, text):
        InsertNote(self.view, self.node, text, self.fromState, self.newState, evt.Make(self.do_close_if_needed))

    def do_note_if_needed(self):
        if(ShouldNote(self.node,self.fromState, self.newState)):
            self.view.window().show_input_panel("("+self.fromState + ">>" + self.newState + ") Note:","", self.on_insert_note, None, None)
        else:
            self.do_close_if_needed()

    def on_done(self, index):
        if(index < 0):
            return
        newState = self.todoStates[index]
        if(newState == "none"):
            newState = ""
        # if we don't have a TODO state then we have to handle that as well.
        m = self.todoRe.search(self.bufferContents)
        fromState = None
        if(m == None):
            self.todoRe = re.compile(r"^([*]+ (\[\#[a-zA-Z0-9]+\]\s+)?)( )*")
        else:
            fromState = m.group(3)
        if(newState != ""):
            newState += " "
        self.bufferContents = self.todoRe.sub(r"\g<1>" + newState, self.bufferContents)
        # We have to do the editing in sequence because the reloads can get mixed up otherwise
        if(fromState):
            self.fromState = fromState.strip()
        else:
            self.fromState = ""
        self.newState  = newState.strip()
        # Recurring events do not hit the done state when you toggle them
        # They bounce back to TODO they just get a new note in them
        if(ShouldRecur(self.node, self.fromState,self.newState)):
            self.do_note_if_needed()
        else:
            self.view.ReplaceRegion(self.row,self.bufferContents, evt.Make(self.do_note_if_needed))

    def run(self, edit, onDone=None):
        self.onDone = onDone
        self.node = db.Get().AtInView(self.view)
        #self.todoStates = sets.Get("todoStates", sets.defaultTodoStates)
        todos = self.node.env.all_todo_keys
        if(len(todos) > 0):
            self.todoStates = todos
            self.todoStates += ["none"]
        else:
            for i in range(0, len(self.todoStates)):
                if(self.todoStates[i] == "|"):
                    self.todoStates[i] = "none" 
        # ACTION vs DONE states
        # TODO" "FEEDBACK" "VERIFY" "|" "DONE" "DELEGATED
        row = self.node.start_row
        self.todoRe = r"^([*]+ (\[\#[a-zA-Z0-9]+\]\s+)?)("
        haveFirst = False
        for state in self.todoStates:
            if state != "|":
                if(haveFirst):
                    self.todoRe += "|"
                self.todoRe += state
                haveFirst = True
        self.todoRe += r")( )*"
        self.todoRe = re.compile(self.todoRe)
        sp  = self.view.text_point(row,0)
        self.row = self.view.line(sp)
        self.bufferContents = self.view.substr(self.row)
        self.view.window().show_quick_panel(self.todoStates, self.on_done, -1, -1)

# Use a menu to change the priority of an item
class OrgPriorityChangeCommand(sublime_plugin.TextCommand):
    def on_done(self, index):
        if(index < 0):
            return
        newState = self.priorities[index]
        if(newState == "none"):
            newState = ""
        # if we don't have a TODO state then we have to handle that as well.
        m = self.Re.search(self.bufferContents)
        if(m == None):
            self.Re = re.compile(r"^([*]+ )( )*")
        if(newState != ""):
            newState = "[#" + newState + "] " 
        self.bufferContents = self.Re.sub(r"\g<1>" + newState, self.bufferContents)
        self.view.ReplaceRegion(self.row, self.bufferContents, self.onDone)
        #self.view.run_command("org_internal_replace", {"start": self.row.begin(), "end": self.row.end(), "text": self.bufferContents, "onDone": self.onDone})
        #self.view.replace(self.edit, self.row, self.bufferContents)

    def run(self, edit, onDone = None):
        self.onDone = onDone
        self.node = db.Get().AtInView(self.view)
        self.priorities = sets.Get("priorities", defaultPriorities)
        self.priorities = copy.copy(self.priorities)
        self.priorities.append("none")
        row = self.node.start_row
        self.Re = r"^([*]+ )(\[\#[a-zA-Z0-9]+\]\s+)"
        self.Re = re.compile(self.Re)
        sp  = self.view.text_point(row,0)
        self.row = self.view.line(sp)
        self.bufferContents = self.view.substr(self.row)
        self.view.window().show_quick_panel(self.priorities, self.on_done, -1, -1)

def indent_node(view, node, edit):
    # Indent the node itself
    sp  = view.text_point(node.start_row,0)
    view.insert(edit,sp,"*")
    # Indent MY content
    for i in range(node.start_row+1,node.local_end_row+1):
        sp  = view.text_point(i,0)
        view.insert(edit,sp," ")
    # Find my children and indent them.
    for n in node.children:
        indent_node(view, n, edit)

def deindent_node(view, node, edit):
    # Get my position and ensure this node CAN de-indent
    sp  = view.text_point(node.start_row,0)
    ep  = view.text_point(node.start_row,1)
    np  = view.text_point(node.start_row,2)
    bufferContents = view.substr(sublime.Region(ep,np))
    if(bufferContents == "*"):
        view.erase(edit,sublime.Region(sp,ep))
        # Now erase a space at the front of my contents.
        for i in range(node.start_row+1,node.local_end_row+1):
            sp  = view.text_point(i,0)
            ep  = view.text_point(i,1)
            bufferContents = view.substr(sublime.Region(sp,ep))
            if(bufferContents == " " or bufferContents == "\t"):
                view.erase(edit,sublime.Region(sp,ep))
        for n in node.children:
            deindent_node(view, n, edit)
    else:
        log.debug("Did not get star, not deindenting it " + str(len(bufferContents)) + " " + bufferContents)

class OrgChangeIndentCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        n = db.Get().AtInView(self.view)
        if(n and type(n) != node.OrgRootNode):
            indent_node(self.view, n, edit)
            file = db.Get().FindInfo(self.view)
            file.LoadS(self.view)

# This does not handle indention of sub trees! Need to fix that!
class OrgChangeDeIndentCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        node = db.Get().AtInView(self.view)
        if(node and type(node) != node.OrgRootNode):
            deindent_node(self.view, node, edit)
            file = db.Get().FindInfo(self.view)
            file.LoadS(self.view)

# This doesn't work, it is inserting as a child rather than as a sibling AT the point in question.
# I will need a new insertion command for this.
class OrgMoveHeadingUpCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        curNode = db.Get().AtInView(self.view)
        if(curNode and type(curNode) != node.OrgRootNode and curNode._index > 1):
            targetNode = curNode.env._nodes[curNode._index - 1]
            index = targetNode._index - 1
            sp    = self.view.text_point(curNode.start_row, 0)
            ep    = self.view.text_point(curNode.end_row, 0)
            r     = self.view.line(ep)
            reg   = sublime.Region(sp, r.end())

            # Extract the text and make a new tree
            nodetext = self.view.substr(reg)
            extraTree = loads(nodetext)
            # Remove the old node
            curNode.remove_node()

            # Now try to insert at this point.
            targetNode.insert_at(extraTree[1], index)
            # Now refile effectively
            file = db.Get().FindInfo(self.view)
            #targetNode.insert_at(curNode, )
            #curNode.remove_node()
            file.Save()
            file.Reload()

# This doesn't work, it is inserting as a child rather than as a sibling AT the point in question.
# I will need a new insertion command for this.
class OrgMoveHeadingDownCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        curNode = db.Get().AtInView(self.view)
        if(curNode and type(curNode) != node.OrgRootNode and curNode._index < (len(curNode.env._nodes) - 1)):
            targetNode = curNode.env._nodes[curNode._index + 1]
            index = targetNode._index
            sp    = self.view.text_point(curNode.start_row, 0)
            ep    = self.view.text_point(curNode.end_row, 0)
            r     = self.view.line(ep)
            reg   = sublime.Region(sp, r.end())

            # Extract the text and make a new tree
            nodetext = self.view.substr(reg)
            extraTree = loads(nodetext)
            # Remove the old node
            curNode.remove_node()

            # Now try to insert at this point, but we removed ourselves
            # so take us out of the equation for where we want to be inserted
            targetNode.insert_at(extraTree[1], index - 1)
            # Now refile effectively
            file = db.Get().FindInfo(self.view)
            #targetNode.insert_at(curNode, )
            #curNode.remove_node()
            file.Save()
            file.Reload()

class OrgInsertHeadingSiblingCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        curNode = db.Get().AtInView(self.view)
        level = curNode.level
        reg = curNode.region(self.view)
        if(level == 0):
            level = 1
            here = sublime.Region(view.size(),view.size())
        else:
            here = sublime.Region(reg.end(),reg.end())
        self.view.sel().clear()
        self.view.sel().add(reg.end())
        self.view.show(here)
        self.view.run_command("insert_snippet", {"name" : "Packages/OrgExtended/snippets/heading"+str(level)+".sublime-snippet"})
        
class OrgInsertHeadingChildCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        curNode = db.Get().AtInView(self.view)
        level = curNode.level
        reg = curNode.region(self.view)
        if(level == 0):
            level = 1
            here = sublime.Region(view.size(),view.size())
        else:
            here = sublime.Region(reg.end(),reg.end())
        self.view.sel().clear()
        self.view.sel().add(reg.end())
        self.view.show(here)
        self.view.run_command("insert_snippet", {"name" : "Packages/OrgExtended/snippets/heading"+str((level+1))+".sublime-snippet"})
        
class OrgInsertTodayInactiveCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        now = datetime.datetime.now()
        toInsert = orgdate.OrgDate.format_date(now, False)
        self.view.insert(edit,self.view.sel()[0].begin(), toInsert)


class OrgInsertTodayActiveCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        now = datetime.datetime.now()
        toInsert = orgdate.OrgDate.format_date(now, True)
        self.view.insert(edit,self.view.sel()[0].begin(), toInsert)

class OrgInsertDateInactiveCommand(sublime_plugin.TextCommand):
    def insert(self, date):
        if(date):
            self.view.Insert(self.view.sel()[0].begin(), OrgDate.format_clock(date.start, active=False))

    def run(self, edit):
        datep.Pick(evt.Make(self.insert))


class OrgInsertDateActiveCommand(sublime_plugin.TextCommand):
    def insert(self, date):
        if(date):
            self.view.Insert(self.view.sel()[0].begin(), OrgDate.format_clock(date.start, active=True))

    def run(self, edit):
        datep.Pick(evt.Make(self.insert))


class OrgScheduleCommand(sublime_plugin.TextCommand):
    def insert(self, date):
        if(date):
            self.view.Insert(self.view.sel()[0].begin(), OrgDate.format_clock(date.start, active=True))
        self.view.sel().clear()
        self.view.sel().add(self.oldsel)

    def run(self, edit):
        # TODO: Find scheduled and replace it as well.
        node = db.Get().AtInView(self.view)
        if(not node.is_root()):
            self.oldsel = self.view.sel()[0]
            pt = self.view.text_point(node.start_row,0)
            l = self.view.line(pt)
            # Last row handling If we are the last row we can't jump over the newline
            # we have to add one.
            nl = ""
            addnl = 1
            if(self.view.isBeyondLastRow(node.start_row+1)):
                nl = "\n"
                addnl = 0
            self.view.insert(edit, l.end() + addnl, nl + node.indent() + "SCHEDULED:  \n")
            pt = self.view.text_point(node.start_row+1,0)
            l = self.view.line(pt)
            self.view.sel().clear()
            self.view.sel().add(l.end())
            datep.Pick(evt.Make(self.insert))

RE_TAGS = re.compile(r'^(?P<heading>[*]+[^:]+\s*)(\s+(?P<tags>[:]([^: ]+[:])+))?$')
class OrgInsertTagCommand(sublime_plugin.TextCommand):
    def on_done(self, text):
        node = db.Get().AtInView(self.view)
        if(node):
            if not text in node.tags:
                (region, line) = self.view.getLineAndRegion(node.start_row)
                m = RE_TAGS.search(line)
                if(m.group('tags') != None):
                    tags = m.group('tags') + text + ":"
                else:
                    tags = "    :" + text + ":" 
                toline = "{0:70}{1}".format(m.group('heading'), tags)
                self.view.ReplaceRegion(region,toline,self.onDone)
            else:
                log.debug("Tag already part of node")
                evt.EmitIf(self.onDone)

    def run(self, edit, onDone = None):
        self.onDone = onDone
        self.input = insSel.OrgInput()
        self.input.run("Tag:",db.Get().tags,evt.Make(self.on_done))


class OrgInsertCustomIdCommand(sublime_plugin.TextCommand):
    def on_done(self, text):
        if(text):
            node = db.Get().AtInView(self.view)
            if(node and not node.is_root()):
               props.UpdateProperty(self.view,node,"CUSTOM_ID",text,self.onDone)

    def run(self, edit, onDone=None):
        self.onDone = onDone
        self.input = insSel.OrgInput()
        print(str(db.Get().customids))
        self.input.run("Custom Id:",db.Get().customids, evt.Make(self.on_done))
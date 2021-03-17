import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
import fnmatch
import OrgExtended.orgparse.loader as loader
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
import OrgExtended.orglinks as orglink
import OrgExtended.orgneovi as nvi
import OrgExtended.orgagenda as oa
import OrgExtended.orgcheckbox as checkbox
import OrgExtended.orgnumberedlist as numberedlist

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
    if(IsDoneState(node, toState)):
        if(node.scheduled and node.scheduled.repeating):
            return node.scheduled
        if(node.deadline and node.deadline.repeating):
            return node.deadline
        timestamps = node.get_timestamps(active=True,point=True,range=True)
        for t in timestamps:
            if(t and t.repeating):
                return t
    return None

def ShouldClose(node, fromState, toState):
    if(ShouldRecur(node,fromState,toState)):
        return False
    # NOTE: We need to get the todo transitions
    #       into this as well!
    toState = toState.strip()
    startup = node.root.startup()
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
    startup = node.root.startup()
    if(IsDoneState(node,toState) and Startup.lognotedone in startup):
        return True



RE_T = re.compile(r'\s(?P<time><\s*\d+-\d+-\d+\s+[^>]+>)(\s+|$)')
# Use a menu to change the todo state of an item
class OrgTodoChangeCommand(sublime_plugin.TextCommand):
    def on_totally_done(self):
        evt.EmitIf(self.onDone)

    # recurrence needs to update the base timestamp!
    # This needs to respect the .+ ++ and + markers
    def on_update_timestamps_if_needed(self, row=0):
        # We have to reload our node as we updated things.
        self.node = db.Get().At(self.view, self.node.start_row)
        if(row > (self.node.local_end_row+1)):
            self.on_totally_done()
        for i in range(self.node.start_row+row, self.node.local_end_row+1):
            pt = self.view.text_point(i, 0)
            line = self.view.line(pt)
            txt = self.view.substr(line)
            m = RE_T.search(txt)
            now = datetime.datetime.now()
            if(m):
                tsl = OrgDate.list_from_str(m.group('time'))
                if(tsl):
                    t = tsl[0]
                    if(t.repeating):
                        next  = t.start
                        next2 = t.end
                        if(t.repeatpre == "+"):
                            next = t.next_repeat_from(oa.EnsureDateTime(next))
                        elif(t.repeatpre == "++"):
                            while(next < now):
                                next = t.next_repeat_from(oa.EnsureDateTime(next))
                        elif(t.repeatpre == ".+"):
                            next = t.next_repeat_from(now)
                        s = m.start(1)
                        e = m.end(1)
                        rpt = t.repeatpre + str(t.repeatnum) + t.repeatdwmy
                        wrn = ""
                        if(t.warning):
                            wrn = " " + t.warnpre + str(t.warnnum) + t.warndwmy
                        if(t.has_end()):
                            if(t.has_time()):
                                nout = txt[:s] + next.strftime("<%Y-%m-%d %a %H:%M-") + t.end.strftime("%H:%M ")+ rpt + wrn + ">"  + txt[e:]
                            else:
                                # This really shouldn't happen.
                                nout = txt[:s] + next.strftime("<%Y-%m-%d %a ")+ rpt + wrn + ">" + txt[e:]
                        else:
                            if(t.has_time()):
                                nout = txt[:s] + next.strftime("<%Y-%m-%d %a %H:%M ") + rpt + wrn + ">" +txt[e:]
                            else:
                                nout = txt[:s] + next.strftime("<%Y-%m-%d %a ")+ rpt + wrn + ">" + txt[e:]
                        self.view.run_command("org_internal_replace", {"start": line.begin(), "end": line.end(), "text": nout, "onDone": evt.Make(lambda:self.on_update_timestamps_if_needed(i+1)) })
                        return
        self.on_totally_done()

    def do_recurrence_if_needed(self):
        self.rec = ShouldRecur(self.node,self.fromState,self.newState)
        if(self.rec):
            InsertRecurrence(self.view, self.node, self.fromState, self.newState, evt.Make(self.on_update_timestamps_if_needed))
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

    def on_done_st4(self,index,modifers):
        self.on_done(index)

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
        if(int(sublime.version()) <= 4096):
            self.view.window().show_quick_panel(self.todoStates, self.on_done, -1, -1)
        else:
            self.view.window().show_quick_panel(self.todoStates, self.on_done_st4, -1, -1)

# Use a menu to change the priority of an item
class OrgPriorityChangeCommand(sublime_plugin.TextCommand):
    def on_done_st4(self,index,modifers):
        self.on_done(index)
    def on_done(self, index):
        if(index < 0):
            return
        newState = self.priorities[index]
        if(newState == "none"):
            newState = ""
        # if we don't have a TODO state then we have to handle that as well.
        m = self.Re.search(self.bufferContents)
        if(m == None):
            todos = self.node.env.all_todo_keys
            todos = '|'.join(todos)
            self.Re = re.compile(r"^([*]+\s+(" + todos + r")?\s*)( )*")
        if(newState != ""):
            newState = "[#" + newState + "] " 
        self.bufferContents = self.Re.sub(r"\g<1>" + newState, self.bufferContents)
        self.view.ReplaceRegion(self.row, self.bufferContents, self.onDone)
        #self.view.run_command("org_internal_replace", {"start": self.row.begin(), "end": self.row.end(), "text": self.bufferContents, "onDone": self.onDone})
        #self.view.replace(self.edit, self.row, self.bufferContents)

    def run(self, edit, onDone = None):
        self.onDone = onDone
        self.node = db.Get().AtInView(self.view)
        self.priorities = self.node.priorities()
        self.priorities = copy.copy(self.priorities)
        self.priorities.append("none")
        row = self.node.start_row
        self.Re = r"^([*]+ [^\[\]]*\s*)(\[\#[a-zA-Z0-9]+\]\s+)"
        self.Re = re.compile(self.Re)
        sp  = self.view.text_point(row,0)
        self.row = self.view.line(sp)
        self.bufferContents = self.view.substr(self.row)
        if(int(sublime.version()) <= 4096):
            self.view.window().show_quick_panel(self.priorities, self.on_done, -1, -1)
        else:
            self.view.window().show_quick_panel(self.priorities, self.on_done_st4, -1, -1)

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

def indent_list(view, row, edit):
    # Indent the node itself
    sp  = view.text_point(row,0)
    view.insert(edit,sp,"  ")

    line = view.lineAt(row)
    children,crow = numberedlist.findChildrenByIndent(view, line)
    for r in range(row+1,crow):
        sp  = view.text_point(r,0)
        view.insert(edit,sp,"  ")

def deindent_list(view, row, edit):
    # Get my position and ensure this node CAN de-indent
    sp  = view.text_point(row,0)
    ep  = view.text_point(row,1)
    np  = view.text_point(row,2)
    bufferContents = view.substr(sublime.Region(sp,np))
    bufferContentsS = view.substr(sublime.Region(sp,ep))
    wasTab = bufferContentsS == "\t"
    if(bufferContents == "  " or wasTab):
        if(wasTab):
            view.erase(edit,sublime.Region(sp,ep))
        else:
            view.erase(edit,sublime.Region(sp,np))
        line = view.lineAt(row)
        children,crow = numberedlist.findChildrenByIndent(view, line)
        for r in range(row+1,crow):
            sp  = view.text_point(r,0)
            ep  = view.text_point(r,1)
            np  = view.text_point(r,2)
            bufferContents = view.substr(sublime.Region(sp,np))
            bufferContentsS = view.substr(sublime.Region(sp,ep))
            wasTab = bufferContentsS == "\t"
            if(bufferContents == "  " or wasTab):
                if(wasTab):
                    view.erase(edit,sublime.Region(sp,ep))
                else:
                    view.erase(edit,sublime.Region(sp,np))

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

# Thing is a region, and first line of the thing tuple
# things is a list of thing
def sort_things_alphabetically(things,reverse=False):
    things.sort(key=lambda thing: thing[1],reverse=reverse)


class OrgSortListCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        # Get a list of things
        things = None
        wasNumbered = False
        if(numberedlist.isNumberedLine(self.view)):
            wasNumbered = True
            things = numberedlist.getListAtPoint(self.view)
        elif(checkbox.isUnorderedList(self.view.getLine(self.view.curRow()))):
            things = checkbox.getListAtPoint(self.view)
        if(not things):
            log.error(" Could not sort at point")
            return
        # Build macro region
        start = things[0][0][0]
        end   = things[len(things)-1][0][1]
        sp  = self.view.text_point(start,0)
        ep  = self.view.text_point(end,0)
        ep  = self.view.line(ep).end()
        reg = sublime.Region(sp,ep)

        # Sort the things
        sort_things_alphabetically(things)

        # Copy from macro region to sorted version
        buffer = ""
        for thing in things:
            bs = self.view.text_point(thing[0][0],0)
            be = self.view.text_point(thing[0][1]-1,0)
            be = self.view.line(be).end()
            breg = sublime.Region(bs,be)
            ss = self.view.substr(breg).rstrip() + "\n"
            buffer += ss
        # Replace the macro region with new str
        self.view.replace(edit, reg, buffer)
        if(wasNumbered):
            self.view.run_command('org_update_numbered_list')
        pass



class OrgSelectSubtreeCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        curNode = db.Get().AtInView(self.view)
        if(curNode and type(curNode) != node.OrgRootNode and curNode._index > 1):
            sp    = self.view.text_point(curNode.start_row, 0)
            ep    = self.view.text_point(curNode.end_row, 0)
            r     = self.view.line(ep)
            reg   = sublime.Region(sp, r.end()+1)
            self.view.sel().clear()
            self.view.sel().add(reg)

class OrgCopySubtreeCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        curNode = db.Get().AtInView(self.view)
        if(curNode and type(curNode) != node.OrgRootNode and curNode._index > 1):
            sp    = self.view.text_point(curNode.start_row, 0)
            ep    = self.view.text_point(curNode.end_row, 0)
            r     = self.view.line(ep)
            reg   = sublime.Region(sp, r.end()+1)
            nodetext = self.view.substr(reg)
            sublime.set_clipboard(nodetext)
            nvi.TestAndSetClip(self.view, nodetext)

class OrgSelectEntityCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        curNode = db.Get().AtInView(self.view)
        if(curNode and type(curNode) != node.OrgRootNode and curNode._index > 1):
            sp    = self.view.text_point(curNode.start_row, 0)
            ep    = self.view.text_point(curNode.local_end_row, 0)
            r     = self.view.line(ep)
            reg   = sublime.Region(sp, r.end()+1)
            self.view.sel().clear()
            self.view.sel().add(reg)

class OrgCopyEntityCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        curNode = db.Get().AtInView(self.view)
        if(curNode and type(curNode) != node.OrgRootNode and curNode._index > 1):
            sp    = self.view.text_point(curNode.start_row, 0)
            ep    = self.view.text_point(curNode.local_end_row, 0)
            r     = self.view.line(ep)
            reg   = sublime.Region(sp, r.end()+1)
            nodetext = self.view.substr(reg)
            sublime.set_clipboard(nodetext)
            nvi.TestAndSetClip(self.view, nodetext)

class OrgCopyLinkHrefCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if(self.view.match_selector(self.view.sel()[0].begin(), "orgmode.link")):
            pt = self.view.sel()[0].end()
            links = self.view.find_by_selector("orgmode.link")
            hrefs = self.view.find_by_selector("orgmode.link.href")
            reg = None
            for link in links:
                line = self.view.line(link.begin())
                if(line.contains(pt)):
                    for href in hrefs:
                        if(line.contains(href.begin())):
                            reg = href
                            break
                    break
            if(reg):
                nodetext = self.view.substr(reg)
                sublime.set_clipboard(nodetext)
                nvi.TestAndSetClip(self.view, nodetext)

class OrgSelectLinkHrefCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if(self.view.match_selector(self.view.sel()[0].begin(), "orgmode.link")):
            pt = self.view.sel()[0].end()
            links = self.view.find_by_selector("orgmode.link")
            hrefs = self.view.find_by_selector("orgmode.link.href")
            reg = None
            for link in links:
                line = self.view.line(link.begin())
                if(line.contains(pt)):
                    for href in hrefs:
                        if(line.contains(href.begin())):
                            reg = href
                            break
                    break
            if(reg):
                self.view.sel().clear()
                self.view.sel().add(reg)

class OrgMoveHeadingUpCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        curNode = db.Get().AtInView(self.view)
        if(curNode and type(curNode) != node.OrgRootNode and curNode._index > 1):
            targetNode = curNode.get_sibling_up()
            if(targetNode):
                index = targetNode._index - 1
                r,c   = self.view.curRowCol()
                sp    = self.view.text_point(curNode.start_row, 0)
                ep    = self.view.text_point(curNode.end_row, 0)
                r     = self.view.line(ep)
                reg   = sublime.Region(sp, r.end()+1)

                nodetext = self.view.substr(reg)
                sp    = self.view.text_point(targetNode.start_row, 0)
                treg   = sublime.Region(sp, sp)

                self.view.erase(edit,reg)
                self.view.insert(edit,sp,nodetext)
                self.view.sel().clear()
                np = self.view.text_point(targetNode.start_row, c)
                self.view.sel().add(np)

class OrgMoveHeadingDownCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        curNode = db.Get().AtInView(self.view)
        if(curNode and type(curNode) != node.OrgRootNode and curNode._index < (len(curNode.env._nodes) - 1)):
            targetNode = curNode.get_sibling_down()
            if(targetNode):
                temp = curNode
                curNode = targetNode
                targetNode = temp
                index = targetNode._index - 1
                sp    = self.view.text_point(curNode.start_row, 0)
                ep    = self.view.text_point(curNode.end_row, 0)
                r     = self.view.line(ep)
                reg   = sublime.Region(sp, r.end()+1)

                nodetext = self.view.substr(reg)
                sp    = self.view.text_point(targetNode.start_row, 0)
                treg   = sublime.Region(sp, sp)

                self.view.erase(edit,reg)
                self.view.insert(edit,sp,nodetext)

class OrgInsertHeadingSiblingCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        curNode = db.Get().AtInView(self.view)
        needsNewline = False
        if(not curNode):
            level = 1
            here = sublime.Region(self.view.size(),self.view.size())
            reg  = here
        else:
            level = curNode.level
            reg = curNode.region(self.view,True)  # trim ending whitespace
            if(level == 0):
                level = 1
                here = sublime.Region(view.size(),view.size())
            else:
                here = sublime.Region(reg.end(),reg.end())
                text = self.view.substr(self.view.line(here))
                if(text.strip() != ""):
                    needsNewline = True
        self.view.sel().clear()
        self.view.sel().add(reg.end())
        self.view.show(here)
        if(needsNewline):
            self.view.insert(edit,self.view.sel()[0].begin(),'\n')
        ai = sublime.active_window().active_view().settings().get('auto_indent')
        self.view.settings().set('auto_indent',False)
        self.view.run_command("insert_snippet", {"name" : "Packages/OrgExtended/snippets/heading"+str(level)+".sublime-snippet"})
        sublime.active_window().active_view().settings().set('auto_indent',ai)
        
class OrgInsertHeadingChildCommand(sublime_plugin.TextCommand):
    def run(self, edit, onDone=None):
        curNode = db.Get().AtInView(self.view)
        needsNewline = False
        if(not curNode):
            file = db.Get().FindInfo(self.view)
            if(len(file.org) > 0):
                curNode = file.org[len(file.org) - 1]
        if(not curNode):
            level = 1
            l = self.view.line(self.view.size())
            reg = sublime.Region(l.start(),l.start())
            reg  = here
        else:
            level = curNode.level
            reg = curNode.region(self.view, True)
            if(level == 0):
                level = 1
                here = sublime.Region(view.size(),view.size())
            else:
                here = sublime.Region(reg.end(),reg.end())
                text = self.view.substr(self.view.line(here))
                if(text.strip() != ""):
                    needsNewline = True
        self.view.sel().clear()
        self.view.sel().add(reg.end())
        self.view.show(here)
        if(needsNewline):
            self.view.insert(edit,self.view.sel()[0].begin(),'\n')
        ai = sublime.active_window().active_view().settings().get('auto_indent')
        self.view.settings().set('auto_indent',False)
        self.view.run_command("insert_snippet", {"name" : "Packages/OrgExtended/snippets/heading"+str((level+1))+".sublime-snippet"})
        sublime.active_window().active_view().settings().set('auto_indent',ai)
        evt.EmitIf(onDone)

# This will insert whatever text you provide as a child heading of the current node
class OrgInsertTextAsChildHeadingCommand(sublime_plugin.TextCommand):
    def run(self, edit, heading=None, onDone=None):
        curNode = db.Get().AtInView(self.view)
        if(not curNode):
            file = db.Get().FindInfo(self.view)
            if(len(file.org) > 0):
                curNode = file.org[len(file.org) - 1]
        if(not curNode):
            level = 1
            l = self.view.line(self.view.size())
            reg = sublime.Region(l.start(),l.start())
            reg  = here
        else:
            level = curNode.level
            reg = curNode.region(self.view)
            if(level == 0):
                level = 1
                here = sublime.Region(view.size(),view.size())
            else:
                here = sublime.Region(reg.end(),reg.end())
        self.view.sel().clear()
        self.view.sel().add(reg.end()+1)
        #self.view.show(here)
        self.view.insert(edit,self.view.sel()[0].begin(),'\n' + ('*'*(level+1)) + ' ' + heading)
        evt.EmitIf(onDone)
        
class OrgInsertTodayInactiveCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        now = datetime.datetime.now()
        toInsert = orgdate.OrgDate.format_date(now, False)
        self.view.insert(edit,self.view.sel()[0].begin(), toInsert)

class OrgInsertNowInactiveCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        now = datetime.datetime.now()
        toInsert = orgdate.OrgDate.format_clock(now, False)
        self.view.insert(edit,self.view.sel()[0].begin(), toInsert)

class OrgInsertTodayActiveCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        now = datetime.datetime.now()
        toInsert = orgdate.OrgDate.format_date(now, True)
        self.view.insert(edit,self.view.sel()[0].begin(), toInsert)

class OrgInsertNowActiveCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        now = datetime.datetime.now()
        toInsert = orgdate.OrgDate.format_clock(now, True)
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


class OrgBaseTimestampCommand(sublime_plugin.TextCommand):
    def __init__(self,unknown=None, prefix=None):
        super(OrgBaseTimestampCommand, self).__init__(unknown)
        self.prefix = prefix

    def insert(self, date):
        if(date):
            self.view.Insert(self.view.sel()[0].begin(), OrgDate.format_clock(date.start, active=True))
        else:
            self.view.Erase(self.reg)
        self.view.sel().clear()
        self.view.sel().add(self.oldsel)

    def run(self, edit, dateval=None):
        if(type(dateval) == str):
            dateval = orgdate.OrgDateFreeFloating.from_str(dateval)
        # TODO: Find scheduled and replace it as well.
        node = db.Get().AtInView(self.view)
        if(node and not node.is_root()):
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
            insertpt = l.end() + addnl
            endpt = insertpt + len(nl) + len(node.indent()) + len(self.prefix)
            self.reg = sublime.Region(insertpt, endpt)
            self.view.insert(edit, insertpt, nl + node.indent() + self.prefix)
            pt = self.view.text_point(node.start_row+1,0)
            l = self.view.line(pt)
            self.view.sel().clear()
            self.view.sel().add(l.end())
            if(dateval == None):
                datep.Pick(evt.Make(self.insert))
            else:
                self.insert(dateval)

class OrgScheduleCommand(OrgBaseTimestampCommand):
    def __init__(self,unknown=None):
        super(OrgScheduleCommand, self).__init__(unknown,"SCHEDULED:  \n")

class OrgDeadlineCommand(OrgBaseTimestampCommand):
    def __init__(self,unknown=None):
        super(OrgDeadlineCommand, self).__init__(unknown,"DEADLINE:  \n")

class OrgActiveTimestampCommand(OrgBaseTimestampCommand):
    def __init__(self,unknown=None):
        super(OrgActiveTimestampCommand, self).__init__(unknown,"  \n")

class OrgInsertClosedCommand(sublime_plugin.TextCommand):
    def run(self, edit):
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
            now = datetime.datetime.now()
            toInsert = orgdate.OrgDate.format_clock(now, False)
            self.view.insert(edit, l.end() + addnl, nl + node.indent() + "CLOSED: "+toInsert+"\n")

# ================================================================================
RE_TAGS = re.compile(r'^(?P<heading>[*]+[^:]+\s*)(\s+(?P<tags>[:]([^: ]+[:])+))?$')
class OrgInsertTagCommand(sublime_plugin.TextCommand):
    def OnDone(self, text):
        if(not text):
            return
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

    def run(self, edit, text=None, onDone=None):
        self.onDone = onDone
        self.text = text.strip() if text != None else text
        if(self.text != None and self.text != ""):
            self.OnDone(self.text)
        else:
            self.input = insSel.OrgInput()
            self.input.run("Tag:",db.Get().tags,evt.Make(self.OnDone))

# ================================================================================
class OrgInsertArchiveTagCommand(sublime_plugin.TextCommand):
    def OnDone(self):
        evt.EmitIf(self.onDone)
    def run(self, edit, onDone=None):
        self.onDone = onDone
        self.view.run_command("org_insert_tag",{"onDone": evt.Make(self.OnDone), "text": "ARCHIVE"})

# ================================================================================
class OrgInsertCustomIdCommand(sublime_plugin.TextCommand):
    def on_done(self, text):
        if(text):
            # No spaces allowed in a custom id
            text = text.replace(" ","-")
            node = db.Get().AtInView(self.view)
            if(node and not node.is_root()):
               props.UpdateProperty(self.view,node,"CUSTOM_ID",text,self.onDone)

    def run(self, edit, onDone=None):
        self.onDone = onDone
        self.input = insSel.OrgInput()
        #print(str(db.Get().customids))
        self.input.run("Custom Id:",db.Get().customids, evt.Make(self.on_done))

# ================================================================================
class OrgSetTodayCommand(sublime_plugin.TextCommand):
    def run(self, edit, onDone=None):
        self.onDone = onDone
        idValue = "TODAY"
        node = db.Get().AtInView(self.view)
        if(not node or node.is_root()):
            log.debug("Cannot update root node or non existent node as today")
            return
        file, at = db.Get().FindByCustomId(idValue)
        if(file != None and at != None):
            node = file.At(at)
            if(node):
                props.RemoveProperty(self.view, node, "CUSTOM_ID")
        node = db.Get().AtInView(self.view)
        if(node and not node.is_root()):
            props.UpdateProperty(self.view,node,"CUSTOM_ID",idValue,self.onDone)


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

# ================================================================================
class RunEditingCommandOnToday:
    def __init__(self, view, command, cmds = {}):
        self.view    = view
        self.command = command
        self.cmds    = cmds

    def onSaved(self):
        db.Get().Reload(self.savedView)
        evt.EmitIf(self.onDone)

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
        cmds = self.cmds
        cmds["onDone"] = eventName
        view.run_command(self.command, cmds)

    def Run(self,onDone = None):
        self.onDone = onDone
        idValue = "TODAY"
        file, at = db.Get().FindByCustomId(idValue)
        if(file != None and at != None):
            node = file.At(at)
            if(node):
                self.n         = node
                self.f         = file
                self.savedView = get_view_for_silent_edit_file(file)
                # Give time for the document to be opened.
                sublime.set_timeout_async(lambda: self.onLoaded(), 200)
                return
            else:
                log.warning("COULD NOT LOCATE TODAY")
        else:
            log.warning("Could not locate today")

# Append text to a node
class OrgAppendTextCommand(sublime_plugin.TextCommand):
    def run(self, edit, text="", onDone=None):
        curNode = db.Get().AtInView(self.view)
        if(not curNode):
            file = db.Get().FindInfo(self.view)
            if(len(file.org) > 0):
                curNode = file.org[len(file.org) - 1]
        if(not curNode):
            level = 1
            l = self.view.line(self.view.size())
            reg = sublime.Region(l.start(),l.start())
            reg  = here
        else:
            level = curNode.level
            reg = curNode.region(self.view)
            if(level == 0):
                level = 1
                here = sublime.Region(view.size(),view.size())
            else:
                here = sublime.Region(reg.end(),reg.end())
        self.view.sel().clear()
        self.view.sel().add(reg.end() + 1)
        #self.view.show(here)
        self.view.insert(edit,self.view.sel()[0].begin(),'\n' + (' '*(level*2)) + text)
        evt.EmitIf(onDone)

class OrgLinkToTodayCommand(sublime_plugin.TextCommand):
    def OnDone(self):
        evt.EmitIf(self.onDone)

    def InsertLink(self):
        self.ed = RunEditingCommandOnToday(self.view, "org_append_text", {'text': self.link})
        self.ed.Run(evt.Make(self.OnDone))

    def run(self, edit, onDone=None):
        self.onDone = onDone
        # Schedule this item so it is in the agenda
        self.view.run_command("org_schedule", {"dateval": str(datetime.datetime.now())})
        # Create a link to the current location so we can insert it in our today item
        self.link = orglink.CreateLink(self.view)
        curNode = db.Get().AtInView(self.view)
        # Should we add a heading to this?
        if(curNode and not curNode.is_root()):
            self.ed = RunEditingCommandOnToday(self.view, "org_insert_text_as_child_heading", {'heading': curNode.heading})
            self.ed.Run(evt.Make(self.InsertLink))
        else:
            self.InsertLink()



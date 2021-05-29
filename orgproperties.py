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
import OrgExtended.pymitter as evt
import OrgExtended.orgduration as dur
import uuid
#import yaml

log = logging.getLogger(__name__)

RE_SDC = re.compile(r'^\s*(SCHEDULED|DEADLINE|CLOSED):')
def InsertDrawerIfNotPresent(view, node, drawer = ":PROPERTIES:", onDone=None):
    if(drawer == ":PROPERTIES:"):
        if(node.property_drawer_location):
            evt.EmitIf(onDone)
            return False
    else:
        for d in node.drawers:
            if((":" + d["name"] + ":") == drawer):
                evt.EmitIf(onDone)
                return False
    level = node.level
    indent = " " + (" " * level)
    drawerRow = node.body_lines_start
    # Properties should be the first drawer...
    if(drawer != ":PROPERTIES:" and node.property_drawer_location):
        drawerRow = node.property_drawer_location[1] + 1
    # Also skip over SCHEDULED, DEADLINE and CLOSED lines
    for row in range(drawerRow, node.local_end_row + 1):
        pt = view.text_point(row, 0)
        line = view.line(pt)
        txt = view.substr(line)
        m = RE_SDC.search(txt)
        if(not m):
            drawerRow = row
            break
        else:
            drawerRow = row + 1

    drawerHere = view.text_point(drawerRow, 0)
    newline = "\n" if view.isBeyondLastRow(drawerRow) else ""
    if(drawer == ":PROPERTIES:"):
        node.set_property_drawer_location((drawerRow,drawerRow+1))
    view.run_command("org_internal_insert", {"location": drawerHere, "text": newline + indent + drawer +"\n" + indent + ":END:\n","onDone":onDone})
    return True

def AddProperty(view, node, key, value, onDone=None):
    if(InsertDrawerIfNotPresent(view, node)):
        # File is reloaded have to regrab node
        node = db.Get().At(view, node.start_row)
    end = node.property_drawer_location[1]
    pt = view.text_point(end, 0)
    level = node.level
    indent = "   " + (" " * level)
    view.run_command("org_internal_insert", {"location": pt, "text": indent + ":" + str(key) + ": " + str(value) + "\n", "onDone": onDone})
    node.set_property_drawer_location((node.property_drawer_location[0],node.property_drawer_location[1] + 1))

# KEY has to have : and everything.
def AddLogbook(view, node, key, value, onDone=None):
    if(InsertDrawerIfNotPresent(view, node, ":LOGBOOK:")):
        # File is reloaded have to regrab node
        node = db.Get().At(view, node.start_row)
    drawer = node.get_drawer("LOGBOOK")
    loc = drawer['loc']
    end = loc[1]
    pt = view.text_point(end, 0)
    level = node.level
    indent = "   " + (" " * level)
    drawer['loc'] = (loc[0], loc[1] + 1)
    view.run_command("org_internal_insert", {"location": pt, "text": indent + str(key) + " " + str(value) + "\n", "onDone": onDone})


RE_PROPERTY_EXTRACT = re.compile(r"^\s*:([a-zA-Z0-9_@-]+):\s*(.*)")
def GetProperty(view, node, key):
    if(not node or not node.property_drawer_location):
        return False
    start = node.property_drawer_location[0]
    end   = node.property_drawer_location[1]
    lkey = key.lower()
    v = None
    mrow = None
    # Work backwards, want to find the latest incarnation of this
    for row in range(end-1, start, -1):
        line = view.getLine(row)
        m = RE_PROPERTY_EXTRACT.search(line)
        if(m != None):
            k = m.group(1).strip()
            v = m.group(2).strip()
            if(k.lower() == lkey):
                mrow = row
                break
    return v

def UpdateProperty(view, node, key, value, onDone=None):
    def OnDrawer():
        # File is reloaded have to regrab node
        n = db.Get().At(view, node.start_row)
        if(not n):
            log.error("Failed to look up property drawer! Something is wrong!")
        start, end = n.property_drawer_location
        lkey = key.lower().strip()
        mrow = None
        # Work backwards, want to find the latest incarnation of this
        for row in range(end-1, start, -1):
            line = view.getLine(row)
            m = RE_PROPERTY_EXTRACT.search(line)
            if(m):
                k = m.group(1).strip()
                v = m.group(2).strip()
                if(k.lower() == lkey):
                    mrow = row
                    break
        # We found our property, replace it!
        if(mrow != None):
            pt = view.text_point(mrow, 0)
            rw = view.line(pt)
            text = "  {0}:{1}: {2}".format(n.indent(),key,value)
            view.ReplaceRegion(rw,text,onDone)
        # Otherwise add a new property
        else:
            AddProperty(view, n, key, value, onDone)
    InsertDrawerIfNotPresent(view, node, ":PROPERTIES:", evt.Make(OnDrawer))


def UpdateLogbook(view, node, key, value, onDone=None):
    if(InsertDrawerIfNotPresent(view, node, ":LOGBOOK:")):
        # File is reloaded have to regrab node
        node = db.Get().At(view, node.start_row)
    drawer = node.get_drawer("LOGBOOK")
    loc    = drawer['loc']
    start  = loc[0]
    end    = loc[1]
    lkey   = key.lower()
    mrow   = None
    extract = re.compile(r'^\s*' + key)
    # Work backwards, want to find the latest incarnation of this
    for row in range(end-1, start, -1):
        line = view.getLine(row)
        m = extract.search(line)
        if(m != None):
            mrow = row
            break
    level = node.level
    indent = "   " + (" " * level)
    # We found our property, replace it!
    if(mrow != None):
        pt = view.text_point(mrow, 0)
        rw = view.line(pt)
        view.run_command("org_internal_replace", {"start": rw.begin(), "end": rw.end(), "text": indent + str(key) + " " + str(value), "onDone": onDone})
    # Otherwise add a new property
    else:
        AddLogbook(view, node, key, value, onDone)

def RemoveProperty(view, node, key):
    if(not node or not node.property_drawer_location):
        return False
    start = node.property_drawer_location[0]
    end   = node.property_drawer_location[1]
    lkey = key.lower()
    mrow = None
    # Work backwards, want to find the latest incarnation of this
    for row in range(end-1, start, -1):
        line = view.getLine(row)
        m = RE_PROPERTY_EXTRACT.search(line)
        if(m != None):
            k = m.group(1).strip()
            v = m.group(2).strip()
            if(k.lower() == lkey):
                mrow = row
                break
    # We found our property, erase it!
    if(mrow != None):
        pt = view.text_point(mrow, 0)
        rw = view.line(pt)
        view.run_command("org_internal_erase", {"start": rw.begin(), "end": (rw.end()+1)})
        node.set_property_drawer_location((node.property_drawer_location[0],node.property_drawer_location[1] - 1))
        return True
    return False

def RemoveLogbook(view, node, key):
    if(not node):
        return False
    drawer = node.get_drawer("LOGBOOK")
    if(not drawer):
        return False
    loc    = drawer['loc']
    start  = loc[0]
    end    = loc[1]
    lkey   = key.lower()
    mrow   = None
    # Work backwards, want to find the latest incarnation of this
    for row in range(end-1, start, -1):
        line = view.getLine(row)
        m = re.search(key,line)
        if(m != None):
            mrow = row
            break
    # We found our property, erase it!
    if(mrow != None):
        pt = view.text_point(mrow, 0)
        rw = view.line(pt)
        view.run_command("org_internal_erase", {"start": rw.begin(), "end": (rw.end()+1)})
        drawer['loc'] = (start,end-1)
        return True
    return False

# Removes all instances of a named property from the drawer.
def RemoveAllInstances(view, node, key):
    while(RemoveProperty(view, node, key)):
        pass

# Removes all instances of a named logbook entry from the drawer.
def RemoveAllLogbookInstances(view, node, key):
    while(RemoveLogbook(view, node, key)):
        pass

# Insert a new drawer into the node.
class OrgInsertDrawerCommand(sublime_plugin.TextCommand):
    def run(self,edit):
        self.view.window().show_input_panel(
                    "Drawer Name:",
                    "",
                    self.createDrawer, None, None)

    def createDrawer(self, drawer):
        if(not drawer):
            return
        node = db.Get().AtInView(self.view)
        if(node and node.level > 0):
            InsertDrawerIfNotPresent(self.view, node, ":" + drawer + ":")

class OrgInsertPropertyDrawerCommand(sublime_plugin.TextCommand):
    def run(self,edit):
        node = db.Get().AtInView(self.view)
        if(node and node.level > 0):
            InsertDrawerIfNotPresent(self.view, node, ":PROPERTIES:")

class OrgInsertPropertyCommand(sublime_plugin.TextCommand):
    def run(self,edit,onDone=None):
        self.onDone=onDone
        self.view.window().show_input_panel(
                    "Property Name:",
                    "",
                    self.createProperty, None, None)

    def createProperty(self, prop):
        if(not prop):
            return
        self.pname = prop
        self.view.window().show_input_panel(
                    "Property Value:",
                    "",
                    self.createPropertyV2, None, None)

    def createPropertyV2(self, prop):
        if(not prop):
            return
        node = db.Get().AtInView(self.view)
        if(node and node.level > 0):
            UpdateProperty(self.view, node, self.pname, prop, self.onDone)

class OrgInsertEffortCommand(sublime_plugin.TextCommand):
    def run(self,edit,onDone=None):
        self.onDone=onDone
        node = db.Get().AtInView(self.view)
        if(node and node.level > 0):
            v = GetProperty(self.view, node, "EFFORT")
            if(not v):
                v = ""
            self.view.window().show_input_panel(
                    "Effort:",
                    v,
                    self.createProperty, None, None)

    def createProperty(self, prop):
        if(not prop):
            return
        isint = False
        try:
            i = int(prop)
            isint = True
        except:
            pass
        if(isint):
            inc = sets.Get("defaultEffortEstimateUnit","d")
            prop = prop + inc
        d = dur.OrgDuration.Parse(prop)
        if(d):
            node = db.Get().AtInView(self.view)
            if(node and node.level > 0):
                UpdateProperty(self.view, node, "Effort", str(d), self.onDone)
        else:
            log.error("Could not generate effort, please use org duration formation for your estimate")
            view.set_status("Error: ", prop + "is not a valid effort, please use org duration formation 1y 1d 1h 1min")
            evt.EmitIf(self.onDone)

class OrgCreateHeadingIdCommand(sublime_plugin.TextCommand):
    def run(self,edit,onDone=None):
        self.onDone=onDone
        node = db.Get().AtInView(self.view)
        if(node and node.level > 0):
            v = GetProperty(self.view, node, "ID")
            if(not v):
                value = uuid.uuid4()
                UpdateProperty(self.view, node, "ID", str(value), self.onDone)

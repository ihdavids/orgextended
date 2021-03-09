import sublime
import sublime_plugin
import os
from OrgExtended.orgutil.addmethod import *
import OrgExtended.orgparse.node as node
import re
import itertools
try:
  from collections.abc import Sequence
except ImportError:
  from collections import Sequence
from .date import OrgDate, OrgDateClock, OrgDateRepeatedTask, parse_sdc
from .inline import to_plain_text
from .utils.py3compat import PY3, unicode
import copy
from .startup import *
import OrgExtended.asettings as sets


@add_method(node.OrgBaseNode)
def priorities(self, defaultValue = None):
    if(defaultValue == None):
        defaultValue = ["A","B","C","D","E"]
    priorityValues = sets.Get("priorities", defaultValue)
    return self.list_comment("PRIORITIES", priorityValues)


@add_method(node.OrgBaseNode)
def startup(self, defaultVal = None):
    if(defaultVal == None):
        defaultVal = []
    globalStartup = sets.Get("startup",defaultVal)
    return self.list_comment("STARTUP", globalStartup)

# Returns true if this is more than just a heading
@add_method(node.OrgBaseNode)
def spans_lines(self, view):
    s = self.start_row
    e = self.end_row
    return e > s

@add_method(node.OrgBaseNode)
def local_spans_lines(self, view):
    s = self.start_row
    e = self.local_end_row
    return e > s

# returns a sublime region that this node encompases
# including all children
@add_method(node.OrgBaseNode)
def region(self, view, trimEnd = False):
    s  = self.start_row
    e  = self.end_row
    sp = view.text_point(s,0)
    r  = view.line(sp)
    ep = view.text_point(e,0)
    re = view.line(ep)
    # Trim whitespace off end if we can
    if(trimEnd):
        while(e > s):
            ep = view.text_point(e,0)
            re = view.line(ep)
            sl = view.substr(re)
            if(sl.strip() != ""):
                break
            e -= 1
    return sublime.Region(r.end(),re.end()) 

@add_method(node.OrgBaseNode)
def local_region(self, view, trimEnd = False):
    s  = self.start_row
    e  = self.local_end_row
    sp = view.text_point(s,0)
    r  = view.line(sp)
    ep = view.text_point(e,0)
    re = view.line(ep)
    # Trim whitespace off end if we can
    if(trimEnd):
        while(e > s):
            ep = view.text_point(e,0)
            re = view.line(ep)
            sl = view.substr(re)
            if(sl.strip() != ""):
                break
            e -= 1
    return sublime.Region(r.end(),re.end())

@add_method(node.OrgBaseNode)
def heading_region(self, view):
    s  = self.start_row
    sp = view.text_point(s,0)
    return sublime.Region(sp) 

@add_method(node.OrgBaseNode)
def is_folded(self, view):
    reg = self.region(view)
    return view.isRegionFolded(reg)

@add_method(node.OrgBaseNode)
def is_heading_visible(self, view):
    reg = self.heading_region(view)
    if(not view.isRegionFolded(reg)):
        return True
    return False

@add_method(node.OrgBaseNode)
def fold(self, view):
    if(self.spans_lines(view)):
        view.fold(self.region(view))

@add_method(node.OrgBaseNode)
def fold_content(self, view):
    if(self.local_spans_lines(view)):
        view.fold(self.local_region(view))

@add_method(node.OrgBaseNode)
def is_content_folded(self, view):
    if(self.local_spans_lines(view)):
        return view.isRegionFolded(self.local_region(view))
    return False

@add_method(node.OrgBaseNode)
def unfold(self, view):
    if(self.spans_lines(view)):
        reg = self.region(view)
        if(view.isRegionFolded(reg)):
            view.unfold(reg)
        self.fold_drawers(view)

@add_method(node.OrgBaseNode)
def has_substance(self):
    return (self.end_row > self.start_row or self.num_children > 0)

# This will create a sublime region from an item in the
# view.
@add_method(node.OrgBaseNode)
def create_region_from_item(self, view, item):
    s  = item[0]
    e  = item[1]
    sp = view.text_point(s,0)
    ep = view.text_point(e,0)
    r  = view.line(ep)
    rs = view.line(sp)
    return sublime.Region(rs.end(),r.end()) 

# For an item IN in the heading this will try to let
# you fold it.
@add_method(node.OrgBaseNode)
def get_foldable_item_region(self, view, row):
    if(self.property_drawer_location):
        i = self.property_drawer_location
        if(row >= i[0] and row <= i[1]):
            return self.create_region_from_item(view, i)
    if(self.blocks):
        for i in self.blocks:
            if(i != None and row >= i[0] and row <= i[1]):
                return self.create_region_from_item(view, i)
    if(self.dynamicblocks):
        for i in self.dynamicblocks:
            if(i != None and row >= i[0] and row <= i[1]):
                return self.create_region_from_item(view, i)
    if(self.drawers):
        for d in self.drawers:
            i = d['loc']
            if(i != None and row >= i[0] and row <= i[1]):
                return self.create_region_from_item(view, i)
    return None

@add_method(node.OrgBaseNode)
def is_item_folded(self, view, row):
    (row,col) = view.curRowCol()
    reg = self.get_foldable_item_region(view, row)
    if(reg != None):
        return view.isRegionFolded(reg)
    return False

# Iterate over all foldable items and see if this row is
# a foldable row in the document.
@add_method(node.OrgBaseNode)
def is_foldable_item(self, view, row):
    return self.get_foldable_item_region(view, row) != None


@add_method(node.OrgBaseNode)
def fold_item(self, view, row):
    reg = self.get_foldable_item_region(view, row)
    if(reg != None):
        view.fold(reg)

@add_method(node.OrgBaseNode)
def unfold_item(self, view, row):
    reg = self.get_foldable_item_region(view, row)
    if(reg != None):
        view.unfold(reg)

@add_method(node.OrgBaseNode)
def properties_region(self, view):
    s  = self.property_drawer_location[0]
    e  = self.property_drawer_location[1]
    sp = view.text_point(s,0)
    ep = view.text_point(e,0)
    r  = view.line(ep)
    rs = view.line(sp)
    return sublime.Region(rs.end(),r.end()) 

@add_method(node.OrgBaseNode)
def fold_drawers(self, view):
    if(self.property_drawer_location):
        view.fold(self.properties_region(view))
    if(self.drawers):
        for d in self.drawers:
            i = d['loc']
            view.fold(self.create_region_from_item(view, i))

@add_method(node.OrgBaseNode)
def unfold_drawers(self, view):
    if(self.property_drawer_location):
        view.unfold(self.properties_region(view))
    if(self.drawers):
        for d in self.drawers:
            i = d['loc']
            if(i != None and row >= i[0] and row <= i[1]):
                view.unfold(self.create_region_from_item(view, i))

@add_method(node.OrgBaseNode)
def is_properties_folded(self, view):
    reg = self.properties_region(view)
    return view.isRegionFolded(reg)


@add_method(node.OrgBaseNode)
def move_cursor_to(self, view):
    view.sel().clear()
    pt = view.text_point(self.start_row,0)
    view.sel().add(pt)

@add_method(node.OrgBaseNode)
def indent(self):
    level = self.level
    return (" " + (" " * level))


import sublime
import sublime_plugin
import datetime
import re
import os
import fnmatch
import OrgExtended.orgparse.node as node
import OrgExtended.orgutil.util as util
import OrgExtended.orgutil.navigation as nav
import OrgExtended.orgutil.template as templateEngine
import logging
import sys
import traceback 
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
import OrgExtended.orgcapture as capture
import sys
import os.path
import fnmatch


log = logging.getLogger(__name__)

# Stolen from the original orgmode

class CheckState:
    Unchecked, Checked, Indeterminate, Error = range(1, 5)

indent_regex     = re.compile(r'^(\s*).*$')
summary_regex    = re.compile(r'(\[\d*[/%]\d*\])')
checkbox_regex   = re.compile(r'(\[[xX\- ]\])')
checkbox_line_regex   = re.compile(r'\s*[-+]?\s*(\[[xX\- ]\])\s+')

# Extract the indent of this checkbox.
# RETURNS: a string with the indent of this line.
def get_indent(view, content):
    if isinstance(content, sublime.Region):
        content = view.substr(content)
    match = indent_regex.match(content)
    if(match):
        return match.group(1)
    else:
        log.debug("Could not match indent: " + content)
        return ""

RE_HEADING = re.compile('^[*]+ ')
# Try to find the parent of a region (by indent)
def find_parent(view, region):
    row, col = view.rowcol(region.begin())
    content  = view.substr(view.line(region))
    indent   = len(get_indent(view, content))
    row     -= 1
    found    = False
    # Look upward 
    while row >= 0:
        point = view.text_point(row, 0)
        content = view.substr(view.line(point))
        if len(content.strip()):
            if(RE_HEADING.search(content)):
                break
            cur_indent = len(get_indent(view, content))
            if cur_indent < indent:
                found = True
                break
        row -= 1
    if found:
        # return the parent we found.
        return view.line(view.text_point(row,0))

def find_children(view, region, cre = checkbox_regex, includeSiblings=False):
    row, col = view.rowcol(region.begin())
    line = view.line(region)
    content = view.substr(line)
    # print content
    indent = get_indent(view, content)
    if(not indent):
        log.debug("Unable to locate indent for line: " + str(row))
    indent = len(indent)
    # print repr(indent)
    row += 1
    child_indent = None
    children = []
    last_row, _ = view.rowcol(view.size())
    while row <= last_row:
        point = view.text_point(row, 0)
        line = view.line(point)
        content = view.substr(line)
        summary = get_summary(view, line)
        if summary and content.lstrip().startswith("*"):
             break
        if cre.search(content):
            cur_indent = len(get_indent(view, content))
            # check for end of descendants
            if includeSiblings and cur_indent < indent:
                break
            elif not includeSiblings and cur_indent <= indent:
                break
            # only immediate children (and siblings)
            if child_indent is None:
                child_indent = cur_indent
            if cur_indent == child_indent:
                children.append(line)
            if(includeSiblings and cur_indent < child_indent):
                children.append(line)
        row += 1
    return children

def find_siblings(view, child, parent):
    row, col      = view.rowcol(parent.begin())
    parent_indent = get_indent(view, parent)
    child_indent  = get_indent(view, child)
    siblings = []
    row += 1
    last_row, _ = view.rowcol(view.size())
    while row <= last_row:  # Don't go past end of document.
        line = view.text_point(row, 0)
        line = view.line(line)
        content = view.substr(line)
        # print content
        if len(content.strip()):
            cur_indent = get_indent(view, content)
            if len(cur_indent) <= len(parent_indent):
                break  # Indent same as parent found!
            if len(cur_indent) == len(child_indent):
                siblings.append((line, content))
        row += 1
    return siblings

def get_summary(view, line):
    row, _ = view.rowcol(line.begin())
    content = view.substr(line)
    match = summary_regex.search(content)
    if not match:
        return None
    col_start, col_stop = match.span()
    return sublime.Region(
        view.text_point(row, col_start),
        view.text_point(row, col_stop),
    )

def get_checkbox(view, line):
    row, _ = view.rowcol(line.begin())
    content = view.substr(line)
    # print content
    match = checkbox_regex.search(content)
    if not match:
        return None
    # checkbox = match.group(1)
    # print repr(checkbox)
    # print dir(match), match.start(), match.span()
    col_start, col_stop = match.span()
    return sublime.Region(
        view.text_point(row, col_start),
        view.text_point(row, col_stop),
    )

def get_check_state(view, line):
    if '[-]' in view.substr(line):
        return CheckState.Indeterminate
    if '[ ]' in view.substr(line):
        return CheckState.Unchecked 
    if '[X]' in view.substr(line) or '[x]' in view.substr(line):
        return CheckState.Checked
    return CheckState.Error

def get_check_char(view, check_state):
    if check_state == CheckState.Unchecked:
        return ' '
    elif check_state == CheckState.Checked:
        return 'x'
    elif check_state == CheckState.Indeterminate:
        return '-'
    else:
        return 'E'

def recalc_summary(view, region):
    children = find_children(view, region)
    if not len(children) > 0:
        return (0, 0)
    num_children = len(children)
    checked_children = len(
        [child for child in children if (get_check_state(view,child) == CheckState.Checked)])
    # print ('checked_children: ' + str(checked_children) + ', num_children: ' + str(num_children))
    return (num_children, checked_children)

def update_line(view, edit, region, parent_update=True):
    #print ('update_line', self.view.rowcol(region.begin())[0]+1)
    (num_children, checked_children) = recalc_summary(view, region)
    # No children we don't have to update anything else.
    if num_children <= 0:
        return False
    # update region checkbox
    if checked_children == num_children:
        newstate = CheckState.Checked
    else:
        if checked_children != 0:
            newstate = CheckState.Indeterminate
        else:
            newstate = CheckState.Unchecked
    toggle_checkbox(view, edit, region, newstate)
    # update region summary
    update_summary(view, edit, region, checked_children, num_children)
    children = find_children(view, region)
    for child in children:
        line = view.line(child)
        summary = get_summary(view, view.line(child))
        if summary:
            return update_line(view, edit, line, parent_update=False)
    if parent_update:
        parent = find_parent(view, region)
        if parent:
            update_line(view, edit, parent)
    return True

def update_summary(view, edit, region, checked_children, num_children):
    # print('update_summary', self.view.rowcol(region.begin())[0]+1)
    summary = get_summary(view, region)
    if not summary:
        return False
    # print('checked_children: ' + str(checked_children) + ', num_children: ' + str(num_children))
    line = view.substr(summary)
    if("%" in line):
        view.replace(edit, summary, '[{0}%]'.format(int(checked_children/num_children*100)))
    else:
        view.replace(edit, summary, '[%d/%d]' % (checked_children, num_children))

def toggle_checkbox(view, edit, region, checked=None, recurse_up=False, recurse_down=False):
    # print 'toggle_checkbox', self.view.rowcol(region.begin())[0]+1
    checkbox = get_checkbox(view, region)
    if not checkbox:
        return False
    if checked is None:
        check_state = get_check_state(view, region)
        if (check_state == CheckState.Unchecked) | (check_state == CheckState.Indeterminate):
            check_state = CheckState.Checked
        elif (check_state == CheckState.Checked):
            check_state = CheckState.Unchecked
    else:
        check_state = checked
    view.replace(edit, checkbox, '[%s]' % ( get_check_char(view, check_state)))
    if recurse_down:
        # all children should follow
        children = find_children(view, region)
        for child in children:
            toggle_checkbox(view, edit, child, check_state, recurse_down=True)
    if recurse_up:
        # update parent
        parent = find_parent(view, region)
        if parent:
            update_line(view, edit, parent)

def is_checkbox(view, sel):
    names = view.scope_name(sel.end())
    return 'orgmode.checkbox' in names or 'orgmode.checkbox.checked' in names or 'orgmode.checkbox.blocked' in names

def is_checkbox_line(view,sel=None):
    point = None
    if(sel == None):
        row = view.curRow()
        point = view.text_point(row, 0)
    else:
        point = sel.end()
    line = view.line(point)
    content = view.substr(line)
    return checkbox_line_regex.search(content)

def find_all_summaries(view):
    return view.find_by_selector("orgmode.checkbox.summary")

def recalculate_checkbox_summary(view, sel, edit):
    line    = view.line(sel.begin())
    update_line(view, edit, line)

def recalculate_all_checkbox_summaries(view, edit):
    sums = find_all_summaries(view)
    for sel in sums:
        recalculate_checkbox_summary(view, sel, edit)

cline_info_regex = re.compile(r'^(\s*)([-+0-9](\.)?)?.*$')
class OrgInsertCheckboxCommand(sublime_plugin.TextCommand):
    def run(self, edit,insertHere=True):
        row = self.view.curRow()
        line = self.view.getLine(row)
        match = cline_info_regex.match(line)
        indent = match.group(1)
        start  = match.group(2)
        if(start):
            indent = indent + start + " [ ] "
        reg = self.view.curLine()
        list_regex   = re.compile(r'\s*(([-+]\s\[)|[^#*|+-])')
        children = find_children(self.view, reg, list_regex, not insertHere)
        if(children and len(children) > 0):
            reg = children[len(children) - 1]
            row,_ =self.view.rowcol(reg.begin())
        self.view.insert(edit,reg.end(),"\n" + indent)
        # Move to end of line
        row = row + 1
        pt = self.view.text_point(row,0)
        ln = self.view.line(pt)
        self.view.sel().clear()
        self.view.sel().add(ln.end())

uline_info_regex = re.compile(r'^(\s*)([-+]) .*$')
def isUnorderedList(line):
    return uline_info_regex.match(line)


RE_THING = re.compile(r'^\s*[+-](\s\[[ xX-]\])?\s(?P<data>.*)$')
RE_NOTHEADERS = re.compile(r'^\s*[\#|0-9]')
def getListAtPoint(view):
    parent = view.findParentByIndent(view.curLine(),RE_NOTHEADERS, RE_THING)
    print(str(parent))
    if(None != parent):
        prow, _ = view.rowcol(parent.begin())
        list_regex   = re.compile(r'\s*(([-+]\s\[)|[^#*|+-])')
        children = find_children(view, parent, list_regex, True)
        sortby = view.getLine(prow)
        m = RE_THING.search(sortby)
        if(m):
            sortby = m.group('data')
        things = [[[prow,0],sortby]]
        for c in children:
            srow, _ = view.rowcol(c.begin())
            if(len(things) > 0):
                things[len(things)-1][0][1] = srow 
            sortby = view.getLine(srow)
            m = RE_THING.search(sortby)
            if(m):
                sortby = m.group('data')
            things.append([[srow,0],sortby])
        if(len(things) > 0):
            srow, _ = view.rowcol(children[len(children)-1].end())
            things[len(things)-1][0][1] = srow+1
        return things
    return None


class OrgInsertUnorderedListCommand(sublime_plugin.TextCommand):
    def run(self, edit,insertHere=True):
        row = self.view.curRow()
        line = self.view.getLine(row)
        match = uline_info_regex.match(line)
        indent = match.group(1)
        start  = match.group(2)
        if(start):
            indent = indent + start + " "
        reg = self.view.curLine()
        list_regex   = re.compile(r'\s*([-+]|[^#*|])')
        children = find_children(self.view, reg, list_regex, not insertHere)
        if(children and len(children) > 0):
            reg = children[len(children) - 1]
            row,_ =self.view.rowcol(reg.begin())
        self.view.insert(edit,reg.end(),"\n" + indent)
        # Move to end of line
        row = row + 1
        pt = self.view.text_point(row,0)
        ln = self.view.line(pt)
        self.view.sel().clear()
        self.view.sel().add(ln.end())

cbsline_info_regex = re.compile(r'^(\s*)(.*)\[\s*[0-9]*/[0-9]\s*\]\s*$')
class OrgInsertCheckboxSummaryCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        row = self.view.curRow()
        line = self.view.getLine(row)
        match = cbsline_info_regex.match(line)
        if(not match):
            reg = self.view.curLine()
            self.view.insert(edit,reg.end()," [/] ")
            recalculate_all_checkbox_summaries(self.view, edit)

class OrgToggleCheckboxCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        for sel in view.sel():
            if(not is_checkbox_line(view, sel)):
                continue
            line     = view.line(sel.end())
            toggle_checkbox(view, edit, line, recurse_up=True, recurse_down=True)
        recalculate_all_checkbox_summaries(self.view, edit)


class OrgRecalcCheckboxSummaryCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        backup = []
        for sel in view.sel():
            if 'orgmode.checkbox.summary' not in view.scope_name(sel.end()):
                continue
            backup.append(sel)
            #summary = view.extract_scope(sel.end())
            line = view.line(sel.end())
            update_line(view, edit, line)
        view.sel().clear()
        for region in backup:
            view.sel().add(region)


class OrgRecalcAllCheckboxSummariesCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        recalculate_all_checkbox_summaries(self.view, edit)

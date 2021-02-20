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
import OrgExtended.orgcapture as capture
import sys
import os.path
import fnmatch

log = logging.getLogger(__name__)

RE_HEADING = re.compile('^[*]+ ')
RE_NUMLINE = re.compile(r"^\s*(?P<num>[0-9]+)(?P<sep>[.)])(?P<data>\s+(([^:]+\s+)(::))?.*)")

# Returns a list of regions one per line with the children
# of the current line. This is done by testing for headings
# or a change in indent.
def findChildrenByIndent(view, region):
    row, col = view.rowcol(region.begin())
    line = view.line(region)
    content = view.substr(line)
    # print content
    indent = view.getIndent(content)
    if(not indent):
        log.debug("Unable to locate indent for line: " + str(row))
    indent = len(indent)
    # print repr(indent)
    row += 1
    child_indent = None
    children = []
    last_row, _ = view.rowcol(view.size())
    while row <= last_row:
        point   = view.text_point(row, 0)
        line    = view.line(point)
        content = view.substr(line)
        cstrip = content.lstrip()
        if cstrip.startswith("*") or cstrip.startswith('-') or cstrip.startswith('+'):
            break
        if RE_NUMLINE.search(content):
            cur_indent = len(view.getIndent(content))
            # check for end of descendants
            if cur_indent < indent:
                break
            # only immediate children
            if child_indent is None:
                child_indent = cur_indent
            if cur_indent == child_indent:
                children.append(line)
        row += 1
    return (children, row)

def UpdateLine(view, edit):
    crow = view.curRow()
    parent = view.findParentByIndent(view.curLine())
    prow, _ = view.rowcol(parent.begin())
    children, erow = findChildrenByIndent(view, view.curLine())
    cur = 1
    curIndent = view.getIndent(view.getLine(prow+1))
    curLen    = len(curIndent)
    indentStack = []
    for r in range(prow + 1, erow):
        line = view.getLine(r)
        if(r < crow and len(line.strip()) <= 0):
            continue
        thisIndent = view.getIndent(line)
        thisLen    = len(thisIndent)
        if(thisLen > curLen):
            indentStack.append((curIndent,curLen, cur))
            curIndent = thisIndent
            curLen    = thisLen
            cur       = 1

        while(thisLen < curLen and len(indentStack) > 0):
            curIndent, curLen, cur = indentStack.pop()

        if(thisLen == curLen):
            m = RE_NUMLINE.search(line)
            if(m):
                num = int(m.group('num'))
                if(num != cur):
                    region = view.lineAt(r)
                    view.replace(edit, region, '{0}{1}{2}{3}'.format(curIndent, cur, m.group('sep'), m.group('data')))
                cur += 1


def AppendLine(view, edit, insertHere=True, veryEnd=False):
    crow = view.curRow()
    parent = view.findParentByIndent(view.curLine())
    prow, _ = view.rowcol(parent.begin())
    children, erow = findChildrenByIndent(view, view.curLine())
    cur = 1
    curIndent = view.getIndent(view.getLine(crow))
    curLen    = len(curIndent)
    indentStack = []
    sep = '.'
    for r in range(prow + 1, erow+1):
        line = view.getLine(r)
        if(r < crow and len(line.strip()) <= 0):
            continue
        thisIndent = view.getIndent(line)
        thisLen    = len(thisIndent)
        if(thisLen > curLen and veryEnd):
            indentStack.append((curIndent,curLen, cur))
            curIndent = thisIndent
            curLen    = thisLen
            cur       = 1

        while(thisLen < curLen and len(indentStack) > 0):
            curIndent, curLen, cur = indentStack.pop()

        if(thisLen == curLen):
            m = RE_NUMLINE.search(line)
            if(m and (not insertHere or r <= crow)):
                num = int(m.group('num'))
                sep = m.group('sep')
                if(num != cur):
                    region = view.lineAt(r)
                    view.replace(edit, region, '{0}{1}{2}{3}'.format(curIndent, cur, m.group('sep'), m.group('data')))
                cur += 1
            else:
                prefix = ""
                last_row, _ = view.rowcol(view.size())
                if(r > last_row):
                    prefix = "\n"
                point  = view.text_point(r, 0)
                view.insert(edit,point,'{4}{0}{1}{2}{3}\n'.format(curIndent, cur, sep, ' ',prefix))
                view.sel().clear()
                view.sel().add(point + len(curIndent) + 3)
                UpdateLine(view,edit)
                return
        else:
            prefix = ""
            last_row, _ = view.rowcol(view.size())
            if(r > last_row):
                prefix = "\n"
            point  = view.text_point(r, 0)
            view.insert(edit,point,'{4}{0}{1}{2}{3}\n'.format(curIndent, cur, sep, ' ',prefix))
            view.sel().clear()
            view.sel().add(point + len(curIndent) + 3)
            UpdateLine(view,edit)
            return
    # Okay we didn't insert, have to now
    last_row, _ = view.rowcol(view.size())
    prefix = ""
    if(erow > last_row):
        prefix = "\n"
        point  = view.size()
    else:
        point  = view.text_point(erow, 0)
        line = view.getLine(erow)
        newLine = ''
        if(len(line) > 0):
            newLine = '\n'
    view.insert(edit,point,'{5}{0}{1}{2}{3}{4}'.format(curIndent, cur, sep, ' ', newLine,prefix))
    view.sel().clear()
    view.sel().add(point + len(curIndent) + 3)
    UpdateLine(view,edit)


def isNumberedLine(view,sel=None):
    point = None
    if(sel == None):
        row = view.curRow()
        point = view.text_point(row, 0)
    else:
        point = sel.end()
    line = view.line(point)
    content = view.substr(line)
    return RE_NUMLINE.search(content)


class OrgUpdateNumberedListCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        UpdateLine(view, edit)


class OrgAppendNumberedListCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        AppendLine(view, edit)

class OrgAppendToEndOfNumberedListCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        AppendLine(view, edit,insertHere=False,veryEnd=False)

class OrgAppendChildToNumberedListCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        view = self.view
        AppendLine(view, edit,insertHere=False, veryEnd=True)

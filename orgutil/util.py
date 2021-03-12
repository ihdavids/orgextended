import sublime
import sublime_plugin
import os
import base64
import urllib.request
import OrgExtended.asettings as sets 
import uuid
import re

from OrgExtended.orgutil.addmethod import *

def isPotentialOrgFile(filename):
    if(not filename):
        return False
    fn = os.path.splitext(filename)
    exts = sets.Get("validOrgExtensions",[".org", ".org_archive"])
    return (len(fn) > 1 and (fn[1] in exts))

def isOrgSyntax(fileOrView):
    if(type(fileOrView) is sublime.View):
        cur = fileOrView.sel()[0]
        names = fileOrView.scope_name(cur.begin())
        return 'text.orgmode' in names
    return False

def isPotentialOrgFileOrBuffer(fileOrView):
    if(isOrgSyntax(fileOrView)):
        return True
    if(type(fileOrView) is sublime.View and fileOrView.file_name()):
        return isPotentialOrgFile(fileOrView.file_name())
    elif(type(fileOrView) is str):
        return isPotentialOrgFile(fileOrView)
    return False

def isView(fileOrView):
    return (type(fileOrView) is sublime.View)

def getTempBufferId(view):
    return "buffer_" + str(view.id())

def getKey(fileOrView):
    if(isView(fileOrView)):
        id = fileOrView.file_name()
        if(not id):
            return getTempBufferId(fileOrView)
        return id.lower()
    else:
        return fileOrView.lower()

# Sublime doesn't seem to have svg support in minihtml?
image_extensions = [".jpg", ".png", ".gif"]

def is_image(url):
    for ext in image_extensions:
        if(url.endswith(ext)):
            return True
    return False

def get_as_base64(url):
    image = urllib.request.urlopen(url)
    return base64.encodestring(image.read()).decode('ascii').replace('\n', '')

def get_as_string(url):
    image = urllib.request.urlopen(url)
    return image.read().decode('ascii').replace('\n', '')

def RandomString():
    randomString = uuid.uuid4().hex
    return randomString.lower()


# Extension methods for View.
# These just make life a little cleaner
@add_method(sublime.View)
def line_count(self):
	return self.rowcol(self.size())[0] + 1

@add_method(sublime.View)
def curRowCol(self):
    if(len(self.sel())>0):
	   return self.rowcol(self.sel()[0].begin())
    return None

@add_method(sublime.View)
def curRow(self):
    return self.rowcol(self.sel()[0].begin())[0]

@add_method(sublime.View)
def lastRow(self):
    last_row, _ = self.rowcol(self.size())
    return last_row

# Returns a region that is the current line
@add_method(sublime.View)
def curLine(self):
    row = self.curRow()
    pt = self.text_point(row, 0)
    return self.line(pt)

# Returns a region that is the current line
@add_method(sublime.View)
def curLineText(self):
    return self.substr(self.curLine())

@add_method(sublime.View)
def lineAt(self,row):
    pt = self.text_point(row, 0)
    return self.line(pt)

@add_method(sublime.View)
def endRow(self):
    return self.rowcol(self.size())[0]

@add_method(sublime.View)
def isRegionFolded(self, region):
	for i in self.folded_regions():
		if i.contains(region):
			return True
	return False

@add_method(sublime.View)
def getSourceScope(view):
    all_scopes = view.scope_name(view.sel()[0].begin())
    split_scopes = all_scopes.split(" ")
    for scope in split_scopes:
        if scope.find("source.") != -1  or \
         scope.find("embedding.") != -1 or \
         scope.find("text.") != -1:
            return scope
    return None

RE_INDENT  = re.compile(r'^(\s*).*$')
# RETURNS: a string with the indent of this line.
@add_method(sublime.View)
def getIndent(view, regionOrLine):
    content = regionOrLine
    if isinstance(regionOrLine, sublime.Region):
        content = view.substr(regionOrLine)
    match = RE_INDENT.match(content)
    if(match):
        return match.group(1)
    else:
        log.debug("Could not match indent: " + content)
        return ""

# Extract a line of text at row
# from the buffer
@add_method(sublime.View)
def getLine(view, row):
    pt = view.text_point(row, 0)
    reg = view.line(pt)
    if(reg.begin() == reg.end()):
        return ""
    if(reg.begin() >= view.size()):
        return ""
    return view.substr(reg)

RE_HEADING = re.compile('^[*]+ ')
# Try to find the parent of a region (by indent)
# parent
#   of
#   a
#   region
#   search up
@add_method(sublime.View)
def findParentByIndent(view, region, exceptionRe=None, headingRe=None):
    row, col = view.rowcol(region.begin() + 1)
    content  = view.substr(view.line(region))
    indent   = len(view.getIndent(content))
    row     -= 1
    found    = False
    lastHeading = row
    # Look upward 
    while row >= 0:
        content = view.getLine(row)
        if len(content.strip()):
            if(headingRe and headingRe.search(content)):
                lastHeading = row
            if(RE_HEADING.search(content) or exceptionRe and exceptionRe.search(content)):
                if(not headingRe):
                    lastHeading = row
                found = True
                break
            cur_indent = len(view.getIndent(content))
            if cur_indent < indent:
                if(not headingRe):
                    lastHeading = row
                found = True
                break
        row -= 1
    if found:
        # return the parent we found.
        return view.line(view.text_point(lastHeading,0))
    return None


@add_method(sublime.View)
def getLineAndRegion(view, row):
    pt = view.text_point(row, 0)
    reg = view.line(pt)
    return (reg,view.substr(reg))

# Is this the last point in the buffer
@add_method(sublime.View)
def isBeyondLastRow(view,row):
    return view.rowcol(view.size())[0] < row

@add_method(sublime.View)
def ReplaceRegion(view, reg, text, onDone=None):
    view.run_command("org_internal_replace", {"start": reg.begin(), "end": reg.end(), "text": text, "onDone": onDone})

@add_method(sublime.View)
def Insert(view, pt, text, onDone=None): 
    view.run_command("org_internal_insert", {"location": pt, "text": text, "onDone": onDone})

@add_method(sublime.View)
def Erase(view, reg, onDone=None): 
    view.run_command("org_internal_erase", {"start": reg.begin(),"end": reg.end(), "onDone": onDone})

@add_method(sublime.View)
def InsertEnd(view, text, onDone=None): 
    view.run_command("org_internal_insert", {"location": view.size(), "text": text, "onDone": onDone})

@add_method(sublime.View)
def RelativeTo(view, filepath):
    fp = filepath.strip()
    # We can't handle absolute paths at the moment
    if(len(fp) > 2 and fp[0] == '/' or fp[1] == ':'):
        return fp
    return os.path.normpath(os.path.join(os.path.dirname(view.file_name()), fp))

@add_method(sublime.Region)
def IncEnd(reg): 
    return sublime.Region(reg.begin(), reg.end() + 1)

# Convert a list string: (a b c d) to an actual list
spacesplit = re.compile(r"\s+")
def ToIntList(val):
    t = val.replace('(',"").replace(")","")
    ts = spacesplit.split(t)
    vals = []
    for x in ts:
        if(x.strip() != ""):
            vals.append(int(x.strip()))
    return vals

def ToList(val):
    t = val.replace('(',"").replace(")","")
    ts = spacesplit.split(t)
    vals = []
    for x in ts:
        if(x.strip() != ""):
            vals.append(x.strip())
    return vals

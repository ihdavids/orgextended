import sublime
import sublime_plugin
import os
import base64
import urllib.request
import OrgExtended.asettings as sets 
import uuid

from OrgExtended.orgutil.addmethod import *

def isPotentialOrgFile(filename):
    if(not filename):
        return False
    fn = os.path.splitext(filename)
    exts = sets.Get("validOrgExtensions",[".org", ".org_archive"])
    return (len(fn) > 1 and (fn[1] in exts))

image_extensions = [".jpg", ".png", ".gif"]

def is_image(url):
    for ext in image_extensions:
        if(url.endswith(ext)):
            return True
    return False

def get_as_base64(url):
    image = urllib.request.urlopen(url)
    return base64.encodestring(image.read()).decode('ascii').replace('\n', '')


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
	return self.rowcol(self.sel()[0].begin())

@add_method(sublime.View)
def curRow(self):
    return self.rowcol(self.sel()[0].begin())[0]

@add_method(sublime.View)
def curLine(self):
    row = self.curRow()
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

# Extract a line of text at row
# from the buffer
@add_method(sublime.View)
def getLine(view, row):
    pt = view.text_point(row, 0)
    reg = view.line(pt)
    return view.substr(reg)

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



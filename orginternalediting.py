import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
import OrgExtended.orgparse.node as node
import OrgExtended.orgparse.date as orgdate
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





class OrgInternalEraseCommand(sublime_plugin.TextCommand):
    def run(self, edit, start, end, onDone=None):
        region = sublime.Region(start, end)
        self.view.erase(edit, region)
        # Reload the file automatically when we edit it.
        file = db.Get().FindInfo(self.view.file_name())
        if(file != None):
            file.LoadS(self.view)
        evt.EmitIf(onDone)

class OrgInternalReplaceCommand(sublime_plugin.TextCommand):
    def run(self, edit, start, end, text, onDone=None):
        region = sublime.Region(start, end)
        self.view.replace(edit, region, text)
        # Reload the file automatically when we edit it.
        file = db.Get().FindInfo(self.view.file_name())
        if(file != None):
            file.LoadS(self.view)
        evt.EmitIf(onDone)

class OrgInternalInsertCommand(sublime_plugin.TextCommand):
    def run(self, edit, location, text, onDone=None):
        self.view.insert(edit, location, text)
        # Reload the file automatically when we edit it.
        file = db.Get().FindInfo(self.view.file_name())
        if(file != None):
            file.LoadS(self.view)
        evt.EmitIf(onDone)

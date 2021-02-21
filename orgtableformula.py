import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
import fnmatch
import OrgExtended.orgparse.node as node
import OrgExtended.orgutil.util as util
import logging
import sys
import traceback 
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
import OrgExtended.pymitter as evt
import OrgExtended.orginsertselected as ins

log = logging.getLogger(__name__)

def insert_file_data(data, view, edit):
    # figure out what our separator is.
    # replace the separator with |
    view.insert(edit, view.sel()[0], data)


class OrgImportTableFromCsvCommand(sublime_plugin.TextCommand):
    def OnFile(self, filename):
        if(os.path.exists(text)):
            fileData = ""
            with open(filename,'r') as f:
                fileData = f.read()
            insert_file_data(fileData,self.view, self.edit)
        self.OnDone()

    def OnDone(self):
        evt.EmitIf(self.onDone)

    def run(self, edit, onDone=None):
        self.edit = edit
        self.onDone = onDone
        self.input = ins.OrgInput()
        self.input.run("CSV", None, evt.Make(self.OnFile))

class OrgInsertBlankTableCommand(sublime_plugin.TextCommand):
    def OnDims(self, text):
        dims = text.split('x')
        if(len(dims) != 2):
            log.error("DIMENSIONS ARE NOT RIGHT!")
            return
        w = int(dims[0])
        h = int(dims[1])
        data = ""
        for y in range(0,h+1):
            line = "|"
            for x in range(0,w):
                line += "|"
            data += line + '\n'
            if(y == 0):
                data += '|-\n'
        self.pos = self.view.sel()[0]
        self.view.run_command("org_internal_insert", {"location": self.view.sel()[0].begin(), "text": data, "onDone": self.onDone})
        #self.view.insert(self.edit,self.view.sel()[0], data)
        self.OnDone()

    def OnDone(self):
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(self.pos.begin() +1, self.pos.end()+1))
        self.view.run_command('table_editor_next_field')
        evt.EmitIf(self.onDone)

    def run(self, edit, onDone=None):
        self.edit = edit
        self.onDone = onDone
        self.input = ins.OrgInput()
        self.input.run("WxH", None, evt.Make(self.OnDims))

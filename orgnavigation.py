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
import OrgExtended.orgfolding as folding
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
import OrgExtended.orgcapture as capture
import OrgExtended.orgcheckbox as checkbox
import OrgExtended.orgnumberedlist as numberedlist
import OrgExtended.orgdynamicblock as dynamic
import OrgExtended.orgsourceblock as src

log = logging.getLogger(__name__)

# Jump to previous heading from current location.
class OrgUpCommand(sublime_plugin.TextCommand):
    def run(self,edit):
        nav.navigate_up(self.view)

class OrgDownCommand(sublime_plugin.TextCommand):
    def run(self,edit):
        nav.navigate_down(self.view)


class OrgJumpInFileCommand(sublime_plugin.TextCommand):
    def on_done_st4(self,index,modifers):
        self.on_done(index)
    def on_done(self, index):
        view = self.view
        (curRow,curCol) = view.curRowCol()
        node = db.Get().NodeAtIndex(view.file_name(), index)
        print(str(node))
        if(node != None):
            row = node.start_row
            linePos = view.text_point(row,curCol)
            view.show_at_center(linePos)
            view.sel().clear()
            view.sel().add(linePos)
        else:
            view.set_status("Error: ", "filename {0} not found in orgDb".format(view.file_name()))
    def run(self, edit):
        headings = db.Get().Headings(self.view)
        if(int(sublime.version()) <= 4096):
            self.view.window().show_quick_panel(headings, self.on_done, -1, -1)
        else:
            self.view.window().show_quick_panel(headings, self.on_done_st4, -1, -1)

RE_TABLE_MATCH = re.compile(r"^\s*\|")
def table_tabbing(view):
    cur = view.sel()[0]
    l = view.line(cur.begin())
    line = view.substr(l)
    return RE_TABLE_MATCH.search(line)


# Org Mode style tab cycling.
# Not really navigation but as good a place as any for this
class OrgTabCyclingCommand(sublime_plugin.TextCommand):
    """
    Bind to TAB key, and if the current line is not
    a headline, a \t would be inserted?
    Or do we want something else here?
    """
    def run(self, edit):
        # Keep track of if the buffer has changed. The in memory image
        # will be out of date if it has, so loads it.
        file = db.Get().FindInfo(self.view.file_name())
        if(file != None and file.HasChanged(self.view)):
            file.LoadS(self.view)
        
        if(folding.fold_local_cycle(self.view)):
            return
        elif(file != None and type(file.AtInView(self.view)) is node.OrgRootNode):
            folding.fold_global_cycle(self.view)
            return
        elif(folding.am_in_link(self.view)):
            folding.toggle_link(self.view)
            return
        # In a table, our tab expansion will take priority over Table Editor
        # So we have to own it and if we are in a table forward the command
        # All the other commands (at the moment) are okay
        elif(table_tabbing(self.view)):
            self.view.run_command("table_editor_next_field")
        elif(folding.ShouldFoldCheckbox(self.view)):
            folding.FoldCheckbox(self.view)
        else:
            log.debug("tab expansion")
            self.view.run_command("insert_best_completion", {"default": "\t", "exact": False})
            # {"name" : "Packages/vhdl-mode/Snippets/vhdl-header.sublime_snippet"}
            #self.view.run_command("insert_snippet") 
            #self.view.insert(edit,self.view.sel()[0].begin(), "\t")

# Global cycling
class OrgGlobalTabCyclingCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        folding.fold_global_cycle(self.view)



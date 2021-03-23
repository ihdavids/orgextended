import sublime
import sublime_plugin
import os
import OrgExtended.orgparse.node as node
from   OrgExtended.orgparse.sublimenode import * 
import OrgExtended.orgutil.util as util
import logging
import sys
import traceback 
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
import OrgExtended.orgcheckbox as checkbox
import OrgExtended.orgnumberedlist as numberedlist
import OrgExtended.orgdynamicblock as dynamic
import OrgExtended.orgsourceblock as src
import OrgExtended.orgediting as editing
import OrgExtended.orgtableformula as tbl 

log = logging.getLogger(__name__)


# ====================================================================
# Another Do What I Mean style command.
# Contextually looks at where you are and "does the right thing."
# All about inserting things state.
class OrgGenericInsertCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        line = self.view.curLine()
        cb = checkbox.get_checkbox(self.view, line)
        if(cb):
            self.view.run_command('org_insert_checkbox')
            return
        if(checkbox.isUnorderedList(self.view.substr(line))):
            self.view.run_command('org_insert_unordered_list')
            return
        if(numberedlist.isNumberedLine(self.view)):
            numberedlist.AppendLine(self.view, edit)
            return
        n = db.Get().AtInView(self.view)
        if(not n.is_root()):
            self.view.run_command('org_insert_heading_sibling')

# ====================================================================
class OrgGenericInsertAuxCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        line = self.view.curLine()
        cb = checkbox.get_checkbox(self.view, line)
        if(cb):
            self.view.run_command('org_insert_checkbox',{'insertHere': False})
            return
        if(checkbox.isUnorderedList(self.view.substr(line))):
            self.view.run_command('org_insert_unordered_list',{'insertHere': False})
            return
        if(numberedlist.isNumberedLine(self.view)):
            numberedlist.AppendLine(self.view, edit, insertHere=False)
            return
        n = db.Get().AtInView(self.view)
        if(not n.is_root()):
            self.view.run_command('org_insert_heading_child')

# ====================================================================
# Another Do What I Mean style command.
# Contextually looks at where you are and "does the right thing."
# Recalculates checkboxes, recalculates blocks etc.
class OrgRecalcCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        if(dynamic.IsDynamicBlock(self.view)):
            self.view.run_command('org_execute_dynamic_block')
            return
        if(src.IsSourceBlock(self.view)):
            self.view.run_command('org_execute_source_block')
            return
        if(src.IsCallCommentBlock(self.view)):
            self.view.run_command('org_execute_call_comment')
            return
        if(tbl.isTable(self.view)):
            self.view.run_command('org_execute_table')
            return
        checkbox.recalculate_all_checkbox_summaries(self.view, edit)
        numberedlist.UpdateLine(self.view, edit)

# ====================================================================
# Another Do What I Mean style command.
# Contextually looks at where you are and "does the right thing."
# All about toggling things state.
class OrgToggleCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        line = self.view.curLine()
        cb = checkbox.is_checkbox_line(self.view)
        #cb = checkbox.get_checkbox(self.view, line)
        if(cb):
            self.view.run_command('org_toggle_checkbox')
            return
        else:
            self.view.run_command('org_todo_change')


# ====================================================================
class OrgChangeIndentCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        line = self.view.curLine()
        cb = checkbox.get_checkbox(self.view, line)
        if(cb):
            editing.indent_list(self.view,self.view.curRow(), edit)
            return
        if(checkbox.isUnorderedList(self.view.substr(line))):
            editing.indent_list(self.view,self.view.curRow(), edit)
            return
        if(numberedlist.isNumberedLine(self.view)):
            editing.indent_list(self.view,self.view.curRow(), edit)
            return
        n = db.Get().AtInView(self.view)
        if(n and type(n) != node.OrgRootNode):
            editing.indent_node(self.view, n, edit)
            file = db.Get().FindInfo(self.view)
            file.LoadS(self.view)

# ====================================================================
# This does not handle indention of sub trees! Need to fix that!
class OrgChangeDeIndentCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        line = self.view.curLine()
        cb = checkbox.get_checkbox(self.view, line)
        if(cb):
            editing.deindent_list(self.view,self.view.curRow(), edit)
            return
        if(checkbox.isUnorderedList(self.view.substr(line))):
            editing.deindent_list(self.view,self.view.curRow(), edit)
            return
        if(numberedlist.isNumberedLine(self.view)):
            editing.deindent_list(self.view,self.view.curRow(), edit)
            return
        n = db.Get().AtInView(self.view)
        if(n and type(n) != node.OrgRootNode):
            editing.deindent_node(self.view, n, edit)
            file = db.Get().FindInfo(self.view)
            file.LoadS(self.view)

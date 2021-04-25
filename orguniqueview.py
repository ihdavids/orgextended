import sublime, sublime_plugin
import logging

log = logging.getLogger(__name__)


ViewMappings = {}

def CreateUniqueViewNamed(name, syntax):
    # Close the view if it exists
    win = sublime.active_window()
    for view in win.views():
        if view.name() == name:
            win.focus_view(view)
            win.run_command('close')
    win.run_command('new_file')
    view = win.active_view()
    view.set_name(name)
    view.set_syntax_file("Packages/OrgExtended/{}.sublime-syntax".format(syntax))
    return view

def CreateOrFindUniqueViewNamed(name, syntax):
    # Return the view if it exists
    win = sublime.active_window()
    for view in win.views():
        if view.name() == name:
            win.focus_view(view)
            return view
    win.run_command('new_file')
    view = win.active_view()
    view.set_name(name)
    view.set_syntax_file("Packages/OrgExtended/{}.sublime-syntax".format(syntax))
    return view

def MoveViewToOtherGroup(view,myview):
    window = sublime.active_window()
    if (window.num_groups() < 2):
        #self.window.run_command('clone_file')
        window.set_layout({
            "cols": [0.0, 0.5, 1.0],
            "rows": [0.0, 1.0],
            "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]
            })
        mygroup    = 0
        othergroup = 1
    else:
        window.focus_view(view)
        mygroup    = 1
        othergroup = 0
        if (window.get_view_index(myview)[0] == 0):
            othergroup = 1
            mygroup    = 0
    window.focus_view(view)
    window.run_command('move_to_group', {'group': othergroup})
    window.run_command('focus_group', {'group': mygroup})
    window.focus_view(myview)

class UniqueView:
    def __init__(self, name, syntax, reuse=False,curview=None):
        self.name = name
        if(reuse):
            self._view = CreateOrFindUniqueViewNamed(name,syntax=syntax)
        else:
            self._view = CreateUniqueViewNamed(name,syntax=syntax)
        self._view.set_name(self.name)
        if(curview != None):
            MoveViewToOtherGroup(self._view,curview)
        self._view.set_read_only(True)
        self._view.set_scratch(True)
        ViewMappings[name] = self

    @property
    def view(self):
        return self._view

    @staticmethod
    def Get(name,syntax="OrgExtended",reuse=True,curview=None):
        if(name in ViewMappings):
            return ViewMappings[name]
        else:
            return UniqueView(name,syntax,reuse,curview)

    @staticmethod
    def IsShowing(name):
        return name in ViewMappings

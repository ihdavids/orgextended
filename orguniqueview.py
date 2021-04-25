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

class UniqueView:
    def __init__(self, name, syntax, reuse=False):
        self.name = name
        if(reuse):
            self._view = CreateOrFindUniqueViewNamed(name,syntax=syntax)
        else:
            self._view = CreateUniqueViewNamed(name,syntax=syntax)
        self._view.set_read_only(True)
        self._view.set_scratch(True)
        self._view.set_name(self.name)
        ViewMappings[name] = self

    @property
    def view(self):
        return self._view

    @staticmethod
    def Get(name,syntax="OrgExtended",reuse=True):
        if(name in ViewMappings):
            return ViewMappings[name]
        else:
            return UniqueView(name,syntax,reuse)

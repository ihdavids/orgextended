import sublime
import sublime_plugin
import datetime
import re
import os
import logging
import getpass
import OrgExtended.asettings as sets
import OrgExtended.pymitter as evt

log = logging.getLogger(__name__)

class OrgDayPageCreateCommand(sublime_plugin.TextCommand):
    def OnDone(self):
        evt.EmitIf(self.onDone)

    def run(self, edit, onDone=None):
        self.edit   = edit
        self.onDone = onDone
        self.dt = datetime.datetime.now()
        dpPath = sets.Get("dayPagePath",None)
        os.makedirs(dpPath, exist_ok=True)
        if(dpPath == None):
            sublime.status_message("Day Page error. dayPagePath setting is not set!")
            log.error(" Cannot create day page without dayPathPath in configuration")
            return
        dateString = self.dt.strftime("%a_%Y_%m_%d")
        dpPath = os.path.join(dpPath,dateString + ".org")
        if(not os.path.exists(dpPath)):
            with open(dpPath,"w") as f:
                f.write("#+TITLE: {}\n".format(dateString))
                f.write("#+AUTHOR: {}\n".format(getpass.getuser()))
        sublime.active_window().open_file(dpPath, sublime.ENCODED_POSITION)
        self.OnDone()


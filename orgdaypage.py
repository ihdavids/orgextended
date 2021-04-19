import sublime
import sublime_plugin
import datetime
import re
import os
import logging
import getpass
import OrgExtended.asettings as sets
import OrgExtended.pymitter as evt
import OrgExtended.orgextension as ext
import OrgExtended.orgparse.date as orgdate

log = logging.getLogger(__name__)

# I think I will model this feature after org-roam dailies.
# olBc has not really gotten back to me on the subject and I think
# dailies makes a lot of sense.

def dayPageGetPath():
    dpPath = sets.Get("dayPagePath",None)
    if(dpPath == None):
        sublime.status_message("Day Page error. dayPagePath setting is not set!")
        log.error(" Cannot create day page without dayPathPath in configuration")
        return None
    os.makedirs(dpPath, exist_ok=True)
    return dpPath

def dayPageGetDateString(dt):
    formatStr = sets.Get("dayPageNameFormat","%a_%Y_%m_%d")
    return dt.strftime(formatStr)

def dayPageGetName(dt):
    return os.path.join(dayPageGetPath(),dayPageGetDateString(dt) + ".org")

def dayPageInsertSnippet(view,dt):
    window   = view.window()
    snippet  = sets.Get("dayPageSnippet","dayPageSnippet")
    snipName = ext.find_extension_file('orgsnippets',snippet,'.sublime-snippet')
    if(snipName == None):
        log.error(" Could not locate snippet file: " + str(snippet) + ".sublime-snippet using default")
        snipName = ext.find_extension_file('orgsnippets','dayPageSnippet.sublime-snippet')
    ai = view.settings().get('auto_indent')
    view.settings().set('auto_indent',False)
    window.focus_view(view)
    view.run_command('_enter_insert_mode', {"count": 1, "mode": "mode_internal_normal"})
    now  = dt
    inow = orgdate.OrgDate.format_date(now, False)
    anow = orgdate.OrgDate.format_date(now, True)
    # "Packages/OrgExtended/snippets/"+snippet+".sublime-snippet"
    # OTHER VARIABLES:
    # TM_FULLNAME - Users full name
    # TM_FILENAME - File name of the file being edited
    # TM_CURRENT_WORD - Word under cursor when snippet was triggered
    # TM_SELECTED_TEXT - Selected text when snippet was triggered
    # TM_CURRENT_LINE - Line of snippet when snippet was triggered
    view.run_command("insert_snippet",
        { "name" : snipName
        , "ORG_INACTIVE_DATE": inow
        , "ORG_ACTIVE_DATE":   anow
        , "ORG_DATE":          str(dt.date().today())
        , "ORG_TIME":          dt.strftime("%H:%M:%S")
        , "ORG_CLIPBOARD":     sublime.get_clipboard()
        , "ORG_SELECTION":     view.substr(view.sel()[0])
        , "ORG_LINENUM":       str(view.curRow())
        , "ORG_FILENAME":      dayPageGetDateString(dt)
        , "ORG_AUTHOR":        getpass.getuser()
        })
    view.settings().set('auto_indent',ai)

class OrgDayPageCreateCommand(sublime_plugin.TextCommand):
    def OnDone(self):
        evt.EmitIf(self.onDone)

    def run(self, edit, onDone=None):
        self.edit   = edit
        self.onDone = onDone
        self.dt     = datetime.datetime.now()
        dpPath      = dayPageGetName(self.dt)
        dateString  = dayPageGetDateString(self.dt)
        didCreate   = False
        if(not os.path.exists(dpPath)):
            with open(dpPath,"w") as f:
                f.write("")
                didCreate = True
        tview = sublime.active_window().open_file(dpPath, sublime.ENCODED_POSITION)
        if(didCreate):
            dayPageInsertSnippet(tview,self.dt)
        self.OnDone()


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
import OrgExtended.orgdb as db

log = logging.getLogger(__name__)

# I think I will model this feature after org-roam dailies.
# olBc has not really gotten back to me on the subject and I think
# dailies makes a lot of sense.

def dayPageGetToday():
    dt     = datetime.datetime.now()
    change = ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"]
    if(sets.Get("dayPageMode","day") == "week"):
        firstDay = sets.Get("dayPageModeWeekDay","Monday").lower()
        startAt = [idx for idx, element in enumerate(change) if element.startswith(firstDay)]
        if(len(startAt) > 0):
            startAt = startAt[0]
        else:
            startAt = 0
        offset = (dt.weekday() - startAt)
        if(offset != 0):
            dt = dt - datetime.timedelta(days=offset)
    return dt

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

def dayPageFilenameToDateTime(view):
    filename = view.file_name()
    if(not filename):
        return None
    formatStr = sets.Get("dayPageNameFormat","%a_%Y_%m_%d")
    filename = os.path.splitext(os.path.basename(filename))[0]
    return datetime.datetime.strptime(filename,formatStr)

def dayPageGetName(dt):
    return os.path.join(dayPageGetPath(),dayPageGetDateString(dt) + ".org")


def OnLoaded(view,dt):
    view.sel().clear()    
    view.sel().add(0)
    snippet  = sets.Get("dayPageSnippet","dayPageSnippet")
    snipName = ext.find_extension_file('orgsnippets',snippet,'.sublime-snippet')
    if(snipName == None):
        log.error(" Could not locate snippet file: " + str(snippet) + ".sublime-snippet using default")
        snipName = ext.find_extension_file('orgsnippets','dayPageSnippet.sublime-snippet')
    # NeoVintageous users probably prefern not to have to hit insert when editing things.
    view.run_command('_enter_insert_mode', {"count": 1, "mode": "mode_internal_normal"})
    now  = dt
    inow = orgdate.OrgDate.format_date(now, False)
    anow = orgdate.OrgDate.format_date(now, True)
    ai = view.settings().get('auto_indent')
    view.settings().set('auto_indent',False)
    # "Packages/OrgExtended/orgsnippets/"+snippet+".sublime-snippet"
    # OTHER VARIABLES:
    # TM_FULLNAME - Users full name
    # TM_FILENAME - File name of the file being edited
    # TM_CURRENT_WORD - Word under cursor when snippet was triggered
    # TM_SELECTED_TEXT - Selected text when snippet was triggered
    # TM_CURRENT_LINE - Line of snippet when snippet was triggered
    #insert_snippet {"name": "Packages/OrgExtended/orgsnippets/page.sublime-snippet"}
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

def LoadedCheck(view,dt):
    if(view.is_loading()):
        sublime.set_timeout(lambda: LoadedCheck(view,dt),1)
    else:
        OnLoaded(view,dt)

def LoadedCheck2(view,dt, onDone):
    if(view.is_loading()):
        sublime.set_timeout(lambda: onDone(view,dt),1)
    else:
        onDone(view,dt)

def dayPageInsertSnippet(view,dt):
    window   = view.window()
    window.focus_view(view)
    LoadedCheck(view,dt)

def dayPageFindOldPage(dt):
    maxScan     = 90
    for i in range(maxScan):
        dt = dt - datetime.timedelta(days=1)
        fn = dayPageGetName(dt)
        if(os.path.exists(fn)):
            return fn
    return None

def dayPageArchiveOld(dt):
    fn = dayPageFindOldPage(dt)
    if(fn == None):
        return
    f = db.Get().FindFileByFilename(os.path.basename(fn))
    if(f == None):
        return
    if(f.org[0].set_comment("FILETAGS","ARCHIVE")):
        f.Save()

def IsTodo(n):
    return n.todo and n.todo in n.env.todo_keys

def dayPageCopyOpenTasks(tview, dt):
    fn = dayPageFindOldPage(dt)
    if(fn == None):
        return
    f = db.Get().FindFileByFilename(os.path.basename(fn))
    if(f == None):
        return
    out = ""
    for h in f.org[0].children:
        if IsTodo(h):
            for line in h._lines:
                out += line + "\n"
    if(out != ""):
        LoadedCheck2(tview, dt, lambda a,b: tview.run_command("org_internal_insert", {"location": 0, "text": out, "onDone": evt.Make(lambda : dayPageInsertSnippet(tview, dt))}))
    else:
        dayPageInsertSnippet(tview,dt)
    pass

def dayPageCreateOrOpen(dt):
    dpPath      = dayPageGetName(dt)
    dateString  = dayPageGetDateString(dt)
    didCreate   = False
    if(not os.path.exists(dpPath)):
        with open(dpPath,"w") as f:
            f.write("")
            didCreate = True
    tview = sublime.active_window().open_file(dpPath, sublime.ENCODED_POSITION)
    if(didCreate):
        if(sets.Get("dayPageArchiveOld", True)):
            dayPageArchiveOld(dt)
        if(sets.Get("dayPageCopyOpenTasks", True)):
            dayPageCopyOpenTasks(tview, dt)
        else:
            dayPageInsertSnippet(tview,dt)

class OrgDayPagePreviousCommand(sublime_plugin.TextCommand):
    def OnDone(self):
        evt.EmitIf(self.onDone)

    def run(self, edit, onDone=None):
        self.edit   = edit
        self.onDone = onDone
        self.dt     = datetime.datetime.now()
        dt          = dayPageFilenameToDateTime(self.view)
        maxScan     = 90
        for i in range(maxScan):
            dt = dt - datetime.timedelta(days=1)
            if(sets.Get("dayPageCreateOldPages",False)):
                dayPageCreateOrOpen(dt)
                break
            else:
                fn = dayPageGetName(dt)
                if(os.path.exists(fn)):
                    tview = sublime.active_window().open_file(fn, sublime.ENCODED_POSITION)
                    sublime.active_window().focus_view(tview)
                    break
                else:
                    #log.warning("Day page does not exist: " + fn)
                    pass

class OrgDayPageNextCommand(sublime_plugin.TextCommand):
    def OnDone(self):
        evt.EmitIf(self.onDone)

    def run(self, edit, onDone=None):
        self.edit   = edit
        self.onDone = onDone
        self.now    = datetime.datetime.now()
        dt          = dayPageFilenameToDateTime(self.view)
        maxScan     = 90
        for i in range(maxScan):
            dt = dt + datetime.timedelta(days=1)
            if(dt.date() < self.now.date()):
                fn = dayPageGetName(dt)
                if(os.path.exists(fn)):
                    tview = sublime.active_window().open_file(fn, sublime.ENCODED_POSITION)
                    sublime.active_window().focus_view(tview)
                    break
                else:
                    #log.warning("Day page does not exist: " + fn)
                    pass
            elif(dt.date() == self.now.date()):
                dayPageCreateOrOpen(dt)
                break
            else:
                fn = dayPageGetName(dt)
                log.error(" Create day page in the future? " + fn)
                break



class OrgDayPageCreateCommand(sublime_plugin.TextCommand):
    def OnDone(self):
        evt.EmitIf(self.onDone)

    def run(self, edit, onDone=None):
        self.edit   = edit
        self.onDone = onDone
        self.dt = dayPageGetToday()
        dayPageCreateOrOpen(self.dt)
        self.OnDone()


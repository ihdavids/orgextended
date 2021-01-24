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
import OrgExtended.orglinks as links
import OrgExtended.orgclocking as clocking
import OrgExtended.orgnotifications as notice
import OrgExtended.orgdatepicker as datepicker
import OrgExtended.pymitter as evt
import OrgExtended.packagecon as pkgcon

log = None

def InstallIfNeeded(pkg, name):
    log.debug("Checking for " + name)
    if(not pkgcon.IsInstalled(pkg)):
        log.debug("Installing " + name)
        pkgcon.Install(pkg)

# Lets get our windows in sync now that we are loaded.
def sync_up_on_loaded():
    window = sublime.active_window()
    window.run_command("org_on_load_sync_up", {})
    notice.Setup()
    datepicker.SetupMouse()
    # Install required packages to operate org extended
    InstallIfNeeded(pkgcon.TABLE_PACKAGE, "Table Editor")
    InstallIfNeeded(pkgcon.PS_PACKAGE, "Powershell")

# This is where we can start to load our DB!
def plugin_loaded():
    evt.Get().off("tagsfound",db.Get().OnTags)
    sets.setup_user_settings()
    # Load our settings file.
    # We probably need a command to reload it
    # When it is modified, and probably to reload
    # the DB automatically when your orgs change.
    sets.Load()
    clocking.Load()

    # To enable debug logging, set the env var to a non-blank value.
    # This is the same pattern that neovintageous uses and I think
    # it is a reasonably decent mechanism
    _DEBUG = bool(os.getenv('SUBLIME_ORGEXTENDED_DEBUG'))
    #_DEBUG = True
    if _DEBUG:
        logger = logging.getLogger('OrgExtended')
        logger.propagate = 0
        if not logger.hasHandlers():
            logger.setLevel(logging.DEBUG)
            stream_handler = logging.StreamHandler()
            stream_handler.setFormatter(logging.Formatter(
                'Org: %(levelname)-7s [%(filename)15s:%(lineno)4d] %(message)s'
            ))
            logger.addHandler(stream_handler)
            logger.debug('debug logger initialized')
    global log
    log = logging.getLogger(__name__)
    db.Get().RebuildDb()
    #window = sublime.active_window()
    #if window is None:
    sublime.set_timeout_async(lambda: sync_up_on_loaded(), 1000)
    log.debug("DONE INITIALIZING ORG CAPTURE")

# This is called when our plugin unloads!
def plugin_unloaded():
    links.onShutdown()
    if(notice):
        notice.Get().stop()

def onLoad(view):
    if(view and view.file_name() and util.isPotentialOrgFile(view.file_name())):
        folding.onLoad(view)
        links.onLoad(view)

RE_TABLE_MATCH = re.compile(r"^\s*\|")
# Core events to dispatch to each of our subsystems.
# This simple direct call is sufficient for our needs
class OrgCore(sublime_plugin.EventListener):

    def on_load(self, view):
        # If this is an org file we need to let the
        # folding system and others get a crack at this
        # file. OnLoad will potentially pre-fold the file
        # or show images in the file.
        onLoad(view)

    def on_post_window_command(self, window, cmd, args):
        #print("****** CMD: " + cmd)
        capture.onPostWindowCommand(window,cmd,args)

    def on_post_save(self, view):
        if(util.isPotentialOrgFile(view.file_name())):
            db.Get().Reload(view)

    def on_deactivated(self, view):
        capture.onDeactivated(view)

    def ShouldLocalFold(self, view):
        file = db.Get().FindInfo(view.file_name())
        if(file != None and file.HasChanged(view)):
            file.LoadS(view)
        return folding.ShouldFoldLocalCycle(view)

    def ShouldGlobalFold(self, view):
        file = db.Get().FindInfo(view.file_name())
        return (not self.ShouldLocalFold(view)) and (file != None and type(file.AtInView(view)) is node.OrgRootNode)

    def ShouldFoldLinks(self, view):
        return (not self.ShouldGlobalFold(view)) and folding.am_in_link(view)

    def ShouldTableTab(self,view):
        cur = view.sel()[0]
        l = view.line(cur.begin())
        line = view.substr(l)
        return RE_TABLE_MATCH.search(line)
    
    def ShouldFoldBlock(self,view):
        cur = view.sel()[0]
        names = view.scope_name(cur.begin())
        return 'dynamicblock' in names

    def ShouldFoldCheckbox(self, view):
        return (not self.ShouldGlobalFold(view)) and folding.ShouldFoldCheckbox(view)

    def on_query_context(self, view, key, operator, operand, match_all):
        # A key wants to be inserted, what context are we in for that?
        if(operator == sublime.OP_EQUAL and util.isPotentialOrgFile(view.file_name())):
            if(key == 'org_heading'):
                 return operand == self.ShouldLocalFold(view)
            elif(key == 'org_global'):
                return operand == self.ShouldGlobalFold(view)
            elif(key == 'org_link'):
                return operand == self.ShouldFoldLinks(view)
            elif(key == 'org_table'):
                return operand == self.ShouldTableTab(view)
            elif(key == 'org_block'):
                return operand == self.ShouldFoldBlock(view)
            elif(key == 'org_checkbox'):
                return operand == self.ShouldFoldCheckbox(view)
        return False



# Create a new file.
class OrgNewFileCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.new_file()
        view.set_syntax_file('Packages/OrgExtended/orgextended.sublime-syntax')

# Iterate over all open "tabs" and sync them up so they are folded the way they are supposed to be.
class OrgOnLoadSyncUpCommand(sublime_plugin.WindowCommand):
    def run(self):
        sheets = self.window.sheets()
        for sheet in sheets:
            view = sheet.view()
            if(view and view.file_name()):
                # Todo detect buffer type as well in the future?
                # for now we can only do files on disk
                log.debug("OnLoad: " + view.file_name())
                onLoad(view)
            

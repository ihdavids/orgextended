import OrgExtended.orgdb as db
import sublime
import sublime_plugin
import logging
import OrgExtended.orgparse.node as node
from OrgExtended.orgparse.sublimenode import * 
from OrgExtended.orgparse.startup import *
import OrgExtended.asettings as sets
import OrgExtended.orgcheckbox as checkbox

log = logging.getLogger(__name__)

# Link management in the org file.
def am_in_link(view):
    return view.match_selector(view.sel()[0].begin(), "orgmode.link")


def find_all_links(view):
    links = view.find_by_selector("orgmode.link.hrefblock")
    return links

def toggle_link(view):
    pt = view.sel()[0].end()
    links = view.find_by_selector("orgmode.link")
    hrefs = view.find_by_selector("orgmode.link.hrefblock")
    reg = None
    for link in links:
        line = view.line(link.begin())
        if(line.contains(pt)):
            for href in hrefs:
                if(line.contains(href.begin())):
                    reg = href
                    break
            break
    if(reg):
        if(view.isRegionFolded(reg)):
            view.unfold(reg)
        else:
            view.fold(reg)

def fold_all_links(view):
    links = find_all_links(view)
    view.fold(links)

class OrgFoldAllLinksCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        fold_all_links(self.view)

def fold_content(view):
    file = db.Get().FindInfo(view)
    if(file):
        for it in file.org[1:]:
            it.fold_content(view)
    else:
        log.warning("Could not locate file in DB for folding")

def fold_all_but_my_tree(view):
    node = db.Get().AtInView(view)
    if(node):
        node.unfold(view)
        while(node and node.parent):
            for c in node.parent.children:
                if(c != node):
                    c.fold(view)
            node = node.parent

def fold_all(view):
    file = db.Get().FindInfo(view)
    if(file):
        for it in file.org[1:]:
            it.fold(view)
    else:
        log.warning("Could not locate file in DB for folding")

def unfold_all(view):
    file = db.Get().FindInfo(view)
    if(file):
        for it in file.org[1:]:
            it.unfold(view)
    else:
        log.warning("Could not locate file in DB for folding")

# hail mary, if things go wrong, remove all the folds in the buffer
def remove_all_folds(view):
	reg = sublime.Region(0,view.size())
	view.unfold(reg)

def fold_showall(view):
    remove_all_folds(view)
    file = db.Get().FindInfo(view)
    for n in file.org[1:]:
        n.fold_drawers(view)
    fold_all_links(view)

# When we load a file, it could have
# been modified out of scope and this CAN
# cause us grief since our custom folds are
# persisted and those can be a problem.
def onLoad(view):
    remove_all_folds(view)
    # Now lets respect the fold state if we have any.
    file = db.Get().FindInfo(view)
    if(file):
        r = file.org[0]
        globalStartup = sets.Get("startup",["showall"])
        startup = r.startup(globalStartup)
        if(Startup.overview in startup or Startup.fold in startup):
            fold_all(view)
        elif(Startup.content in startup):
            fold_content(view)
            #if(Startup.showall in startup or Startup.nofold in startup):
        else:
            fold_showall(view)
        fold_all_links(view)
        # showeverything is implicit

def onActivated(view):
    shouldHandleActivationFolding = sets.Get("onFocusRespectStartupFolds",None)
    if(shouldHandleActivationFolding):
        # Now lets respect the fold state if we have any.
        file = db.Get().FindInfo(view)
        if(file):
            r = file.org[0]
            globalStartup = sets.Get("startup",["showall"])
            startup = r.startup(globalStartup)
            if(Startup.overview in startup or Startup.fold in startup):
                fold_all_but_my_tree(view)
            elif(Startup.content in startup):
                fold_all_but_my_tree(view)
        fold_all_links(view)

class OrgFoldAllButMeCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        fold_all_but_my_tree(self.view)

class OrgFoldAllCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        fold_all(self.view)

class OrgUnfoldAllCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        unfold_all(self.view)

class OrgRemoveAllFoldsCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		remove_all_folds(self.view)

class OrgFoldContentsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        remove_all_folds(self.view)
        fold_content(view)

class OrgFoldThingCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.view.fold(self.view.sel()[0])

# ,-> OVERVIEW -> CONTENTS -> SHOW ALL --.
# '--------------------------------------'
def fold_global_cycle(view):
    file = db.Get().FindInfo(view)
    # A quick scan of the file to see if we are in
    # overview: everything is folded to the highest level.
    # contents: all headings but no content. (like a TOC)
    # showall:  no property drawers.
    if(file):
        allheadersfolded = True
        allchildrenhidden = True
        allchildrenvisible = True
        allchildrencontentvisible = True
        for n in file.org[0].children:
            for c in n.children:
                if(c.is_heading_visible(view)):
                    allchildrenhiden = False
                else:
                    # log.debug("Child Not Visible: " + str(c.heading))
                    allchildrenvisible = False
                if(c.is_content_folded(view)):
                    #log.debug("Child Content Not Visible: " + str(c.heading))
                    allchildrencontentvisible = False
            if(n.has_substance() and not n.is_folded(view)):
                allheadersfolded = False

        if(allheadersfolded):
            #log.debug("To: CONTENTS")
            remove_all_folds(view)
            fold_content(view)
            return True
        else:
            # contents -> showall
            if(allchildrenvisible and not allchildrencontentvisible):
                #log.debug("To: SHOWALL")
                fold_showall(view)
                return True
            else:
                #log.debug("CV: " + str(allchildrenvisible) + " ACCV: " + str(allchildrencontentvisible))
                #log.debug("To: FOLDALL")
                remove_all_folds(view)
                fold_all(view)
                return True
    return False


def ShouldFoldLocalCycle(view):
    fnode = db.Get().AtInView(view)
    if(fnode):
        row, col = view.curRowCol()
        if(fnode.start_row == row):
            return True
        else:
            # This could be a property drawer. We want to fold that if so.
            if(not type(fnode) is node.OrgRootNode and fnode.is_foldable_drawertype(view, row)):
                return True
            else:
                return False
            pass
    return False

# ,-> FOLDED -> CHILDREN -> SUBTREE --.
# '-----------------------------------'
def fold_local_cycle(view):
    fnode = db.Get().AtInView(view)
    if(fnode and not fnode.is_root()):
        row, col = view.curRowCol()
        if(fnode.start_row == row):
            if(fnode.is_folded(view)):
                fnode.unfold(view)
                if(fnode.num_children > 0):
                    for n in fnode.children:
                        n.fold(view)
            else:
                if(fnode.num_children > 0 and fnode.children[0].is_folded(view)):
                    for n in fnode.children:
                        n.unfold(view)
                else:
                    fnode.fold(view)
            fold_all_links(view)
            return True
        else:
            # This could be a property drawer. We want to fold that if so.
            if(not type(fnode) is node.OrgRootNode and fnode.is_foldable_item(view, row)):
                if(fnode.is_item_folded(view, row)):
                    fnode.unfold_item(view, row)
                    fold_all_links(view)
                    return True
                else:
                    fnode.fold_item(view, row)
                    fold_all_links(view)
                    return True
            #linePos = view.text_point(row,0)
            #reg     = view.line(linePos)
            #bufferContents = view.substr(reg)
            #if(":PROPERTIES:" in bufferContents or ":END:" in bufferContents):
            #    if(node.is_properties_folded(view)):
            #        node.unfold_properties(view)
            #    else:
            #        node.fold_properties(view)
            #    return True
            else:
                return False
    return False

def ShouldFoldCheckbox(view):
    line = view.curLine()
    cb = checkbox.get_checkbox(view, line)
    if(cb != None):
        childs = checkbox.find_children(view, line)
        rv = childs != None and len(childs) > 0
        return rv
    return False

def FoldCheckbox(view):
    line = view.curLine()
    cb = checkbox.get_checkbox(view, line)
    if(cb != None):
        if(view.isRegionFolded(cb)):
            view.unfold(cb)
            return
        childs = checkbox.find_children(view, line)
        if(childs != None and len(childs) > 0):
            reg = sublime.Region(line.end(), childs[len(childs) - 1].end())
            if(view.isRegionFolded(reg)):
                view.unfold(reg)
            else:
                view.fold(reg)


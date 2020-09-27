import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
import fnmatch
from .orgparse.__init__ import *
import OrgExtended.orgparse.node as node
import OrgExtended.orgutil.util as util
import OrgExtended.orgutil.navigation as nav
import OrgExtended.orgutil.template as templateEngine
import logging
import sys
import traceback 
import OrgExtended.orgfolding
import OrgExtended.asettings as sets
import OrgExtended.pymitter as evt

log = logging.getLogger(__name__)


# TODO: Move this to it's own file and give me customId and Tag versions of this.
inputCommand = None
class OrgInput:
    def __init__(self):
        self.current = None
        self.havePopup = False
        self.skipRecalc = False
        global inputCommand
        inputCommand = self

    def on_done(self, text):
        if(self.onDone):
            evt.Get().emit(self.onDone,text)

    def popup(self,content, count = 0):
        if(count > 2):
            return
        try:
            if(not self.inputpanel.is_popup_visible()):
                self.inputpanel.show_popup(content,0,-1) 
                self.havePopup = True
            else:
                self.inputpanel.update_popup(content)
        except Exception as inst:
            print('Exception on popup? Trying to recreate popup')
            print(str(inst))
            self.havePopup = False
            self.popup(content, count + 1)
            # This can be brought up after the popup goes away
            # just ignore it.
            pass


    def redraw(self):
        ff = sets.Get("input_font_face","Arial")
        content = "<html><body id=\"orgselect\">"
        content += """<style>
        div.orgselect {
            background-color: #202020;
            font-family: """ + ff + """;
            padding: 7px;
            border: 2px solid #73AD21;
            border-style: none none none solid;
        }
        div.currentsel {
            background-color: #353555;
        }
        </style><div class=\"orgselect\">"""
        if(not self.current in self.matched and len(self.matched) > 0):
            self.current = self.matched[0]
        for i in self.matched:
            if(i == self.current):
                content += "<div class=\"currentsel\">" + i + "</div>"
            else:
                content += i + "<br>"
        content += "</div></body></html>"
        #self.inputpanel.show_popup_menu(self.matched,None) 
        #self.inputpanel.show_popup(content,sublime.COOPERATE_WITH_AUTO_COMPLETE,-1) 
        self.popup(content)

    def recalculate(self,text):
        se = re.compile(text.replace(" ",".*"))
        self.matched = []
        for i in self.options:
            m = se.search(i)
            if(m):
                self.matched.append(i)

    def on_change(self, text):
        if(self.skipRecalc):
            self.skipRecalc = False
        else:
            self.recalculate(text)
        self.redraw()

    def on_cancel(self):
        if(self.onDone):
            evt.Get().emit(self.onDone,None)

    def down(self):
        self.skipRecalc = True
        mlen = len(self.matched)
        for i in range(0,mlen):
            if(self.matched[i] == self.current):
                if(i == (mlen - 1)):
                    self.current = self.matched[0]
                else:
                    self.current = self.matched[i+1]
                self.redraw() 
                self.inputpanel.ReplaceRegion(self.inputpanel.line(self.inputpanel.text_point(0,0)), self.current)
                return
        self.current = None
        self.redraw()

    def up(self):
        self.skipRecalc = True
        mlen = len(self.matched)
        for i in range(0,mlen):
            if(self.matched[i] == self.current):
                if(i == 0):
                    self.current = self.matched[mlen - 1]
                else:
                    self.current = self.matched[i-1]
                self.redraw() 
                self.inputpanel.ReplaceRegion(self.inputpanel.line(self.inputpanel.text_point(0,0)), self.current)
                return
        self.current = None
        self.redraw()

    def run(self, name, options, onDone = None):
        window = sublime.active_window()
        self.name    = name
        self.view    = window.active_view()
        self.onDone  = onDone
        self.options = options
        #self.outputpanel = CreateUniqueViewNamed("OrgOptions")
        self.inputpanel = self.view.window().show_input_panel(self.name,"",self.on_done,self.on_change,self.on_cancel)
        self.inputpanel.set_name("OrgInput")
        self.inputpanel.set_syntax_file("Packages/OrgExtended/orginput.sublime-syntax")
        #self.view.window().show_quick_panel(self.tags, self.on_done, -1, -1)

class OrgInputDownCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        print("DOWN")
        global inputCommand
        if(inputCommand):
            inputCommand.down()

class OrgInputUpCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        print("DOWN")
        global inputCommand
        if(inputCommand):
            inputCommand.up()

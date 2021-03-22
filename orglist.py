import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
import fnmatch
import OrgExtended.orgparse.loader as loader
import OrgExtended.orgparse.node as node
import OrgExtended.orgparse.date as orgdate
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
import OrgExtended.pymitter as evt
import OrgExtended.orgproperties as props
import OrgExtended.orgdatepicker as datep
import OrgExtended.orginsertselected as insSel
import OrgExtended.orglinks as orglink
import OrgExtended.orgneovi as nvi
import OrgExtended.orgagenda as oa
import OrgExtended.orgcheckbox as checkbox
import OrgExtended.orgnumberedlist as numberedlist

log = logging.getLogger(__name__)

class ListData:
    def __init__(self,view,pt=None):
        reg = view.line(pt)
        line = view.substr(reg)
        if(numberedlist.isNumberedLine(view,reg)):
            wasNumbered = True
            self.data = numberedlist.getListAtPoint(view,pt)
        elif(checkbox.isUnorderedList(line)):
            self.data = checkbox.getListAtPoint(view,pt)
        else:
            self.data = None

    def __iter__(self):
        return self.Iterate()

    def Iterate(self):
        for row in self.data:
            yield row[1]
        return None

RE_ISCOMMENT = re.compile(r"^\s*[#][+]")
def LookupNamedListInFile(name):
    l = None
    view = sublime.active_window().active_view()
    if(view):
        node = db.Get().AtInView(view)
        if(node):
            # Look for named objects in the file.
            names = node.names
            if(names and name in names):
                row = names[name]['row']
                last_row = view.lastRow()
                for r in range(row,last_row):
                    pt = view.text_point(r, 0)
                    line = view.substr(view.line(pt))
                    m = RE_ISCOMMENT.search(line)
                    if(m):
                        continue
                    elif(line.strip() == ""):
                        continue
                    else:
                        row = r
                        break
                pt = view.text_point(row,0)
                reg = view.line(pt)
                line = view.substr(reg)
                if(numberedlist.isNumberedLine(view,reg) or checkbox.isUnorderedList(line)):
                    l = ListData(view,pt)
    return l

def IfListExtract(view,pt):
    l = None
    reg = view.line(pt)
    line = view.substr(reg)
    if(numberedlist.isNumberedLine(view,reg) or checkbox.isUnorderedList(line)):
        l = ListData(view,pt)
    return l

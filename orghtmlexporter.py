import sublime
import sublime_plugin
import datetime
import re
import regex
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
import OrgExtended.orgproperties as props
import OrgExtended.orgexporter as exp
import OrgExtended.pymitter as evt
import OrgExtended.orgplist as plist
import OrgExtended.orgsourceblock as src
import yaml
import sys
import subprocess
import html

log = logging.getLogger(__name__)

# <!-- multiple_stores height="50%" width="50%" --> 
RE_COMMENT_TAG = re.compile(r"^\s*[<][!][-][-]\s+(?P<name>[a-zA-Z0-9_-]+)\s+(?P<props>.*)\s+[-][-][>]")


def mapLanguage(lang):
  if(lang == 'html'):
    return 'language-html'
  elif(lang == 'python'):
    return 'language-python'
  else:
    return lang

def haveLang(lang):
  return True

class HtmlSourceBlockState(exp.SourceBlockState):
    def __init__(self,doc):
        super(HtmlSourceBlockState,self).__init__(doc)
        self.skipSrc = False

    def HandleOptions(self):
        attr = self.e.GetAttrib("attr_html")
        optionsOp = ""
        if(attr):
            p = plist.PList.createPList(attr)
        else:
            p = plist.PList.createPList("")
        ops = p.Get("options",None)
        if(ops):
            optionsOp = ops
        caption = self.e.GetAttrib("caption")
        cc = p.Get("caption",None)
        if(cc):
            caption = cc
        floatOp = GetOption(p,"float",None)
        if(caption and not floatOp):
            floatOp = "t"
        if(floatOp and floatOp != "nil"):
            if(floatOp == "multicolumn"):
                figure = "figure*"
            elif(floatOp == "sideways"):
                figure = "sidewaysfigure" 
            elif(floatOp == "wrap"):
                figure = "wrapfigure"
                figureext = "{l}"
        if(optionsOp.strip() != ""):
            optionsOp = "[" + optionsOp + "]"
        # There is a discrepancy between orgmode docs and
        # actual emacs export.. I need to figure this out so
        # nuke it for now till I understand it
        optionsOp = ""
        return (optionsOp,floatOp,caption)

    def HandleEntering(self, m, l, orgnode):
        self.skipSrc = False
        language = m.group('lang')
        paramstr = l[len(m.group(0)):]
        p = type('', (), {})() 
        src.BuildFullParamList(p,language,paramstr,orgnode)
        exp = p.params.Get("exports",None)
        # Have to pass on parameter to the results block
        self.e.sparams = p
        if(isinstance(exp,list) and len(exp) > 0):
            exp = exp[0]
        if(exp == 'results' or exp == 'none'):
            self.skipSrc = True
            return
        # Some languages we skip source by default
        skipLangs = sets.Get("revealDefaultSkipSrc",[])
        if(exp == None and language == skipLangs):
            self.skipSrc = True
            return
        attribs = ""
        if(p.params.Has("data-noescape")):
            attribs += " data-noescape"
        if(p.params.Has('data-trim')):
            attribs += " data-trim"
        if(p.params.Has("data-line-numbers")):
            attribs += " data-line-numbers=\"{nums}\"".format(nums=p.params.Get("data-line-numbers",1))
        self.options, self.float, self.caption = self.HandleOptions()
        if(haveLang(language)):
            self.e.doc.append("    <pre><code language=\"{language}\" {attribs}>".format(language=mapLanguage(language),attribs=attribs))
        else:
            self.e.doc.append("    <pre><code {attribs}>".format(attribs=attribs))

    def HandleExiting(self, m, l , orgnode):
        if(not self.skipSrc):
            self.e.doc.append(r"  </code></pre>")
        skipSrc = False

    def HandleIn(self,l, orgnode):
        if(not self.skipSrc):
            self.e.doc.append(l)

# Skips over contents not intended for an http buffer
class HtmlExportBlockState(exp.ExportBlockState):
    def __init__(self,doc):
        super(HtmlExportBlockState,self).__init__(doc)
        self.skipExport = False

    def HandleEntering(self, m, l, orgnode):
        self.skipExport = False
        language = m.group('lang').strip().lower()
        if(language != "http"):
            self.skipExport = True
            return

    def HandleExiting(self, m, l , orgnode):
        self.skipExport = False

    def HandleIn(self,l, orgnode):
        if(not self.skipExport):
            self.e.doc.append(l)


class HtmlDynamicBlockState(exp.DynamicBlockState):
    def __init__(self,doc):
        super(HtmlDynamicBlockState,self).__init__(doc)
        self.skip = False
    def HandleEntering(self,m,l,orgnode):
        self.skip = False
        language = m.group('lang')
        paramstr = l[len(m.group(0)):]
        p = type('', (), {})() 
        src.BuildFullParamList(p,language,paramstr,orgnode)
        exp = p.params.Get("exports",None)
        if(isinstance(exp,list) and len(exp) > 0):
            exp = exp[0]
        if(exp == 'results' or exp == 'none'):
            self.skip = True
            return
        self.e.doc.append(r"  <pre>")
    def HandleExiting(self, m, l , orgnode):
        if(not self.skip):
            self.e.doc.append(r"  </pre>")
        self.skip = False
    def HandleIn(self,l, orgnode):
        if(not self.skip):
            self.e.doc.append(l)

class HtmlQuoteBlockState(exp.QuoteBlockState):
    def __init__(self,doc):
        super(HtmlQuoteBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        self.e.doc.append(r"  <blockquote>")
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"  </blockquote>")
    def HandleIn(self,l, orgnode):
        self.e.doc.append(l)

class HtmlNotesBlockState(exp.NotesBlockState):
    def __init__(self,doc):
        super(HtmlNotesBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        self.e.doc.append("  <aside class=\"notes\">")
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"  </aside>")
    def HandleIn(self,l, orgnode):
        self.e.doc.append(l)

class HtmlExampleBlockState(exp.ExampleBlockState):
    def __init__(self,doc):
        super(HtmlExampleBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        self.e.doc.append(r"  <blockquote>")
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"  </blockquote>")
    def HandleIn(self,l, orgnode):
        self.e.doc.append(l)

class HtmlGenericBlockState(exp.GenericBlockState):
    def __init__(self,doc):
        super(HtmlGenericBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        self.data = m.group('data').strip().lower()
        self.e.doc.append(r"  <pre>".format(data=self.data))
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"  </pre>".format(data=self.data))
    def HandleIn(self,l, orgnode):
        self.e.doc.append(l)


class HtmlUnorderedListBlockState(exp.UnorderedListBlockState):
    def __init__(self,doc):
        super(HtmlUnorderedListBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        self.e.doc.append(r"    <ul>")
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"     </ul>")
    def StartHandleItem(self,m,l, orgnode):
        definit = m.group('definition')
        if(definit):
            self.e.doc.append(r"     <li><b>{definition}</b> ".format(definition=definit))
        else:
            self.e.doc.append(r"     <li> ")
    def EndHandleItem(self,m,l,orgnode):
        self.e.doc.append("    </li>")


class HtmlOrderedListBlockState(exp.OrderedListBlockState):
    def __init__(self,doc):
        super(HtmlOrderedListBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        self.e.doc.append(r"    <ol>")
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"    </ol>")
    def StartHandleItem(self,m,l, orgnode):
        #data = self.e.Escape(m.group('data'))
        #self.e.doc.append(r"     \item {content}".format(content=data))
        definit = m.group('definition')
        if(definit):
            self.e.doc.append(r"     <li><b>{definition}</b> ".format(definition=definit))
        else:
            self.e.doc.append(r"     <li>")
    def EndHandleItem(self,m,l,orgnode):
        self.e.doc.append("    </li>")

class HtmlCheckboxListBlockState(exp.CheckboxListBlockState):
    def __init__(self,doc):
        super(HtmlCheckboxListBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        self.e.doc.append(r"    <ul>")
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"    </ul>")
    def StartHandleItem(self,m,l, orgnode):
        #data = self.e.Escape(m.group('data'))
        state = m.group('state')
        definit = m.group('definition')
        if(definit):
            #self.e.doc.append(r"     <li><b>{definition}</b> ".format(definition=definit))
            if(state == 'x'):
                self.e.doc.append("     <li><input type=\"checkbox\" checked><b>{definition}</b> ".format(definition=definit))
            elif(state == '-'):
                self.e.doc.append("     <li><input type=\"checkbox\"><b>{definition}</b> ".format(definition=definit))
                #self.e.doc.append("     \item[\inp] {content}".format(content=data))
            else:
                self.e.doc.append("     <li><input type=\"checkbox\"><b>{definition}</b> ".format(definition=definit))
        else:
            if(state == 'x'):
                self.e.doc.append("     <li><input type=\"checkbox\" checked>")
            elif(state == '-'):
                self.e.doc.append("     <li><input type=\"checkbox\"> ")
                #self.e.doc.append("     \item[\inp] {content}".format(content=data))
            else:
                self.e.doc.append("     <li><input type=\"checkbox\"> ")
    def EndHandleItem(self,m,l,orgnode):
        self.e.doc.append("    </li></input>")


RE_TABLE_SEPARATOR = re.compile(r"^\s*[|][-]")
class HtmlTableBlockState(exp.TableBlockState):
    def __init__(self,doc):
        super(HtmlTableBlockState,self).__init__(doc)
        self.tablecnt = 1

    def WriteRow(self,l,orgnode):
        tds = None
        if(not RE_TABLE_SEPARATOR.search(l)):
          tds = l.split('|')
          if(len(tds) > 3):
            self.e.doc.append("    <tr>")
            for td in tds[1:-1]:
              self.e.doc.append("     <th>{0}</th>".format(self.e.TextFullEscape(td)))
            self.e.doc.append("    </tr>")
        else:
            self.e.doc.append("")

    def HandleEntering(self,m,l,orgnode):
        attr = self.e.GetAttrib("attr_html")
        if(attr):
            p = plist.PList.createPList(attr)
        else:
            p = plist.PList.createPList("")
        caption = self.e.GetAttrib("caption")
        cc = p.Get("caption",None)
        if(cc):
            caption = cc
        self.e.doc.append("  <table>")
        if(caption):
          self.e.doc.append("    <caption class=\"t-above\"><span class=\"table-number\">Table {index}:</span>{caption}</caption>".format(index=self.tablecnt,caption=caption))
        self.WriteRow(l,orgnode)
        self.e.ClearAttrib()

    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append("  </table>")
        self.tablecnt += 1

    def HandleIn(self,l, orgnode):
        self.WriteRow(l, orgnode)

class HtmlEmptyParser(exp.EmptyParser):
    def __init__(self,doc):
        super(HtmlEmptyParser,self).__init__(doc)
    def HandleLine(self,m,l,n):
        self.e.doc.append(r"<br/>")

class HtmlActiveDateParser(exp.EmptyParser):
    def __init__(self,doc):
        super(HtmlActiveDateParser,self).__init__(doc)
    def HandleLine(self,m,l,n):
        self.e.doc.append(r"<p class=\"date\">{date}</p>".format(date=m.group()))

class HtmlBoldParser(exp.BoldParser):
    def __init__(self,doc):
        super(HtmlBoldParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(self.sre.sub(r"<b>\g<data></b>",m.group()))

class HtmlItalicsParser(exp.ItalicsParser):
    def __init__(self,doc):
        super(HtmlItalicsParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(self.sre.sub(r"<i>\g<data></i>",m.group()))

class HtmlUnderlineParser(exp.UnderlineParser):
    def __init__(self,doc):
        super(HtmlUnderlineParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(self.sre.sub(r"<u>\g<data></u>",m.group()))

class HtmlStrikethroughParser(exp.StrikethroughParser):
    def __init__(self,doc):
        super(HtmlStrikethroughParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(self.sre.sub(r"<strike>\g<data></strike>",m.group()))

class HtmlCodeParser(exp.CodeParser):
    def __init__(self,doc):
        super(HtmlCodeParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(self.sre.sub(r"<code>\g<data></code>",m.group()))

class HtmlVerbatimParser(exp.VerbatimParser):
    def __init__(self,doc):
        super(HtmlVerbatimParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(self.sre.sub(r"<pre>\g<data></pre>",m.group()))

def FindImageFile(view, url):
    # ABS
    if(os.path.isabs(url)):
        return url
    # Relative
    if(view != None):
        curDir = os.path.dirname(view.file_name())
        filename = os.path.join(curDir, url)
        if(os.path.isfile(filename)):
            return filename
    # In search path
    searchHere = sets.Get("imageSearchPath",[])
    for direc in searchHere:
        filename = os.path.join(direc, url)
        if(os.path.isfile(filename)):
            return filename
    searchHere = sets.Get("orgDirs",[])
    for direc in searchHere:
        filename = os.path.join(direc, "images", url) 
        if(os.path.isfile(filename)):
            return filename

def IsImageFile(fn):
    # Todo make this configurable
    if(fn.endswith(".gif") or fn.endswith(".png") or fn.endswith(".jpg") or fn.endswith(".svg")):
        return True
    return False

def AddOption(p,name,ops):
    val = p.Get(name,None)
    if(val):
        if(ops != ""):
            ops += ","
        ops += name + "=" + val.strip() 
    return ops

def GetOption(p,name,ops):
    val = p.Get(name,None)
    if(val):
        return val.strip()
    return ops

# Simple links are easy. The hard part is images, includes and results
class HtmlLinkParser(exp.LinkParser):
    def __init__(self,doc):
        super(HtmlLinkParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        link = m.group('link').strip()
        desc = m.group('desc')
        if(desc):
            desc = self.e.Escape(desc.strip())

        if(link.startswith("file:")):
            link = re.sub(r'^file:','',link)
        view = sublime.active_window().active_view()
        imgFile = FindImageFile(view,link)
        if(imgFile and os.path.isfile(imgFile) and IsImageFile(imgFile)):
            relPath = view.MakeRelativeToMe(imgFile)
            imagePath = os.path.dirname(relPath)
            imageToken = os.path.splitext(os.path.basename(relPath))[0]
            # The figures let this float around to much. I can't control the positioning with
            # that. Also the scale is crazy at 1.0. So I auto scale to .5? Probably not the best choice.
            # Attributes will solve this at some point.
            attr = self.e.GetAttrib("attr_reveal")
            optionsOp = ""
            floatOp = None
            figure = "figure"
            align  = "center"
            figureext = ""
            if(attr):
                p = plist.PList.createPList(attr)
            else:
                p = plist.PList.createPList("")
            ops = p.Get("options",None)
            if(ops):
                optionsOp = ops
            caption = self.e.GetAttrib("caption")
            cc = p.Get("caption",None)
            if(cc):
                caption = cc
            optionsOp = AddOption(p,"width",optionsOp)
            optionsOp = AddOption(p,"height",optionsOp)
            optionsOp = AddOption(p,"scale",optionsOp)
            val = p.Get("center",None)
            if(val and val == "nil"):
                align = None
            if(optionsOp == ""):
                optionsOp = r""
            extradata = ""  
            tbl = self.e.GetAttrib("http_comment")
            if(tbl):
                for cName in tbl.keys():
                    if(cName in link):
                        extradata =  " " + tbl[cName]
                        del tbl[cName]
                        break
            self.e.doc.append("<img src=\"{link}\" alt=\"{desc}\"{extradata}/>".format(link=link,desc=desc,extradata=extradata))
        else:
            if(link.startswith("http") or ("/" not in link and "\\" not in link and "." not in link)):
                if(desc):
                    self.e.doc.append("<a href=\"{link}\">{desc}</a>".format(link=link,desc=desc))
                else:
                    self.e.doc.append("<a href=\"{link}\">{link}</a>".format(link=link))
            else:
                link = re.sub(r"[:][:][^/].*","",link)
                link = link.replace("\\","/")
                text = m.group()
                if(desc):
                    self.e.doc.append("<a href=\"{link}\">{desc}</a>".format(link=link,desc=desc))
                else:
                    self.e.doc.append("<a href=\"{link}\">{link}</a>".format(link=link))
        self.e.ClearAttrib()

# <<TARGET>>
class HtmlTargetParser(exp.TargetParser):
    def __init__(self,doc):
        super(HtmlTargetParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(r"<a name=\"{data}\"/>".format(data=m.group('data')))

# Line of html gets emitted
RE_HTML_HTML = regex.compile(r"^\s*[#][+]HTML[:]\s*(?P<data>.*)")
class HtmlHtmlHtmlParser(exp.LineParser):
    def __init__(self,doc):
        super(HtmlHtmlHtmlParser,self).__init__(RE_HTML_HTML, doc)
    def HandleLine(self,m,l,n):
        self.e.doc.append(m.group('data').strip())


# 
class HtmlCommentParser(exp.LineParser):
    def __init__(self,doc):
        super(HtmlCommentParser,self).__init__(RE_COMMENT_TAG, doc)
    def HandleLine(self,m,l,n):
        commentData = m.group('props')
        commentName = m.group('name')
        tbl = self.e.GetAttrib("http_comment")
        if(tbl == None):
            tbl = {}
        tbl[commentName] = commentData.strip()
        self.e.AddAttrib("http_comment", tbl)

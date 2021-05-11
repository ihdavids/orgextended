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
import yaml
import sys
import subprocess
import html

log = logging.getLogger(__name__)



def RevealFilename(view):
    fn = view.file_name()
    fn,ext = os.path.splitext(fn)
    return fn + ".html"

# Global properties I AT LEAST want to support.
# Both as a property on the document and in our settings.
#+OPTIONS: num:nil toc:nil
#+REVEAL_TRANS: None/Fade/Slide/Convex/Concave/Zoom
#+REVEAL_THEME: Black/White/League/Sky/Beige/Simple/Serif/Blood/Night/Moon/Solarized
#+Title: Title of Your Talk
#+Author: Your Name
#+Email: Your Email Address or Twitter Handle

def GetGlobalOption(file, name, settingsName, defaultValue):
    value = sets.Get(settingsName, defaultValue)
    value = ' '.join(file.org[0].get_comment(name, [str(value)]))
    return value


propMappings = {
    "reveal_background":              "data-background-image",
    "reveal_background_image":        "data-background-image",
    "reveal_background_size":         "data-background-size",
    "reveal_background_trans":        "data-background-transition",
    "reveal_trans":                   "data-transition",
    "reveal_trans_speed":             "data-transition-speed",
    "reveal_background_position":     "data-background-position",
    "reveal_background_repeat":       "data-background-repeat",
    "reveal_background_opacity":      "data-background-opacity",
    "reveal_background_color":        "data-background-color",
    "reveal_background_video":        "data-background-video",
    "reveal_background_video_loop":   "data-background-video-loop",
    "reveal_background_video_muted":  "data-background-video-muted"
}

RE_SCHEDULING_LINE = re.compile(r"^\s*(SCHEDULED|CLOSED|DEADLINE)[:].*")
RE_DRAWER_LINE = re.compile(r"^\s*[:].+[:]\s*$")
RE_END_DRAWER_LINE = re.compile(r"^\s*[:](END|end)[:]\s*$")
RE_LINK = re.compile(r"\[\[(?P<link>[^\]]+)\](\[(?P<desc>[^\]]+)\])?\]")
RE_UL   = re.compile(r"^\s*(-|[+])\s+(?P<data>.+)")
RE_BOLD = re.compile(r"\*(?P<data>.+)\*")
RE_ITALICS = re.compile(r"/(?P<data>.+)/")
RE_UNDERLINE = re.compile(r"_(?P<data>.+)_")
RE_STRIKETHROUGH = re.compile(r"\+(?P<data>.+)\+")
RE_CODE = re.compile(r"~(?P<data>.+)~")
RE_VERBATIM = re.compile(r"=(?P<data>.+)=")
RE_STARTQUOTE = re.compile(r"#\+(BEGIN_QUOTE|BEGIN_EXAMPLE|BEGIN_VERSE|BEGIN_CENTER|begin_quote|begin_example|begin_verse|begin_center)")
RE_ENDQUOTE = re.compile(r"#\+(END_QUOTE|END_EXAMPLE|END_VERSE|END_CENTER|end_quote|end_example|end_verse|end_center)")
RE_STARTNOTE = re.compile(r"#\+(BEGIN_NOTES|begin_notes)")
RE_ENDNOTE = re.compile(r"#\+(END_NOTES|end_notes)")
RE_FN_MATCH = re.compile(r"\s*[:]([a-zA-Z0-9-_]+)\s+([^: ]+)?\s*")
RE_STARTSRC = re.compile(r"^\s*#\+(BEGIN_SRC|begin_src)\s+(?P<lang>[a-zA-Z0-9]+)")
RE_ENDSRC = re.compile(r"^\s*#\+(END_SRC|end_src)")
RE_RESULTS = re.compile(r"^\s*#\+RESULTS.*")


# <!-- multiple_stores height="50%" width="50%" --> 
RE_COMMENT_TAG = re.compile(r"^\s*[<][!][-][-]\s+(?P<name>[a-zA-Z0-9_-]+)\s+(?P<props>.*)\s+[-][-][>]")
#https://cdn.jsdelivr.net/npm/reveal.js@3.8.0/js/reveal.min.js
cdn = "https://cdn.jsdelivr.net/npm/reveal.js"
#cdn = "https://cdnjs.cloudflare.com/ajax/libs/reveal.js"
ver = "@4.1.0"
cdn = cdn + ver + "/"


def mapLanguage(lang):
    if(lang == 'html'):
        return 'language-html'
    elif(lang == 'python'):
        return 'language-python'
    else:
        return lang


class HtmlSourceBlockState(exp.SourceBlockState):
    def __init__(self,doc):
        super(HtmlSourceBlockState,self).__init__(doc)
        self.skipSrc = False

    def HandleOptions(self):
        attr = self.e.GetAttrib("attr_reveal")
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
        if(optionsOp.strip() != ""):
            optionsOp = "[" + optionsOp + "]"
        # There is a discrepancy between orgmode docs and
        # actual emacs export.. I need to figure this out so
        # nuke it for now till I understand it
        optionsOp = ""
        return (optionsOp,caption)

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
        if("data-noescape" in params):
            attribs += " data-noescape"
        if("data-trim" in params):
            attribs += " data-trim"
        if("data-line-numbers" in params):
            attribs += " data-line-numbers=\"{nums}\"".format(nums=params["data-line-numbers"])
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
        self.e.doc.append(r"    \begin{todolist}")
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"     \end{todolist}")
    def StartHandleItem(self,m,l, orgnode):
        #data = self.e.Escape(m.group('data'))
        state = m.group('state')
        if(state == 'x'):
            self.e.doc.append(r"     <input type=\"checkbox\" checked>")
        elif(state == '-'):
            self.e.doc.append(r"     <input type=\"checkbox\"> ")
            #self.e.doc.append(r"     \item[\inp] {content}".format(content=data))
        else:
            self.e.doc.append(r"     <input type=\"checkbox\"> ")
    def EndHandleItem(self,m,l,orgnode):
        self.e.doc.append("    </input>")

class LatexTableBlockState(exp.TableBlockState):
    def __init__(self,doc):
        super(LatexTableBlockState,self).__init__(doc)
        self.tablecnt = 1
    def HandleEntering(self,m,l,orgnode):
        attr = self.e.GetAttrib("attr_latex")
        floatOp = None
        align  = "center"
        self.modeDelimeterStart = ""
        self.modeDelimeterEnd   = ""
        self.environment = "tabular"
        self.figure = "center"
        figureext = ""
        if(attr):
            p = plist.PList.createPList(attr)
        else:
            p = plist.PList.createPList("")
        caption = self.e.GetAttrib("caption")
        cc = p.Get("caption",None)
        if(cc):
            caption = cc
        self.environment = GetOption(p,"environment",self.environment)
        mode = GetOption(p,"mode",None)
        if(mode == "math"):
            self.modeDelimeterStart = r"\["
            self.modeDelimeterEnd   = r"\]"
        if(mode == "inline-math"):
            self.modeDelimeterStart = r"\("
            self.modeDelimeterEnd   = r"\)"
        val = p.Get("center",None)
        if(val and val == "nil"):
            align = None
        floatOp = GetOption(p,"float",None)
        if(caption and not floatOp):
            floatOp = "t"
        if(floatOp and floatOp != "nil"):
            if(floatOp):
                self.figure = "table"
                figureext = "[!htp]"
            if(floatOp == "multicolumn"):
                self.figure = "table*"
            elif(floatOp == "sideways"):
                self.figure = "sidewaysfigure" 
            elif(floatOp == "wrap"):
                self.figure = "wrapfigure"
                figureext = "{l}"
            placement = p.Get("placement",None)
            if(placement):
                figureext = placement
        tabledef = ""
        tds = None
        if(not RE_TABLE_SEPARATOR.search(l)):
            tds = l.split('|')
            if(len(tds) > 1):
                if(mode == "math"):
                    tabledef = ""
                else:
                    tabledef = "{" + ("|c" * (len(tds)-2)) + "|}" 
        self.e.doc.append(r"    \begin{{{figure}}}{figureext}".format(figure=self.figure,figureext=figureext))
        if(caption):
            self.e.doc.append(r"    \caption{{{caption}}}".format(caption=self.e.GetAttrib('caption')))
            #self.fs.write("    <caption class=\"t-above\"><span class=\"table-number\">Table {index}:</span>{caption}</caption>".format(index=self.tableIndex,caption=self.caption))
            #self.tableIndex += 1
        if(align == "center" and self.environment == 'tabular'):
            self.e.doc.append(r"    \centering\renewcommand{\arraystretch}{1.2}")
        self.e.doc.append(self.modeDelimeterStart)
        self.e.doc.append(r"    \begin{{{environment}}}{tabledef}".format(tabledef=tabledef,environment=self.environment))
        self.e.ClearAttrib()
        if(self.environment == 'tabular'):
            self.e.doc.append(r"    \hline") 
        if(tds):
            self.HandleData(tds,True)
    def HandleExiting(self, m, l , orgnode):
        if(self.environment == 'tabular'):
            self.e.doc.append(r"    \hline") 
        self.e.doc.append(r"    \end{{{environment}}}".format(environment=self.environment))
        self.e.doc.append(self.modeDelimeterEnd)
        self.e.doc.append(r"    \label{{table:{cnt}}}".format(cnt=self.tablecnt))
        self.e.doc.append(r"    \end{{{figure}}}".format(figure=self.figure))
        self.tablecnt += 1

    def HandleData(self,tds,head=False): 
        if(len(tds) > 3):
            # An actual table row, build a row
            first = True
            line = "    "
            for td in tds[1:-1]:
                if(not first):
                    line += " & "
                first = False
                if(head and self.environment == 'tabular'):
                    line += r"\textbf{{{data}}}".format(data=self.e.Escape(td))
                else:
                    line += self.e.Escape(td)
            line += " \\\\"
            self.e.doc.append(line)
            haveTableHeader = True

    def HandleIn(self,l, orgnode):
        if(RE_TABLE_SEPARATOR.search(l)):
            self.e.doc.append(r'    \hline')
        else:
            tds = l.split('|')
            self.HandleData(tds)

class RevealHrParser(exp.HrParser):
    def __init__(self,doc):
        super(RevealHrParser,self).__init__(doc)
    def HandleLine(self,m,l,n):
        self.e.doc.append(r"<hr/>")

class RevealNameParser(exp.NameParser):
    def __init__(self,doc):
        super(RevealNameParser,self).__init__(doc)
    def HandleLine(self,m,l,n):
        self.e.doc.append(r"<a name=\"{data}\"/>".format(data=m.group('data')))


# class RevealMathParser(exp.MathParser):
#     def __init__(self,doc):
#         super(LatexMathParser,self).__init__(doc)
#     def HandleSegment(self,m,l,n):
#         self.e.doc.append(r"\({data}\)".format(data=m.group('data')))

# class LatexInlineMathParser(exp.InlineMathParser):
#     def __init__(self,doc):
#         super(LatexInlineMathParser,self).__init__(doc)
#     def HandleSegment(self,m,l,n):
#         self.e.doc.append(r"\({data}\)".format(data=m.group('data')))

# class LatexEqMathParser(exp.EqMathParser):
#     def __init__(self,doc):
#         super(LatexEqMathParser,self).__init__(doc)
#     def HandleSegment(self,m,l,n):
#         self.e.doc.append(r"\[{data}\]".format(data=m.group('data')))

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

RE_ATTR_REVEAL = regex.compile(r"^\s*[#][+]ATTR_REVEAL[:]\s*(?P<data>.*)")
class RevealAttributeParser(exp.AttributeParser):
    def __init__(self,doc):
        super(RevealAttributeParser,self).__init__('attr_reveal',RE_ATTR_REVEAL,doc)

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


class RevealDoc(exp.OrgExporter):
    def __init__(self,filename,file,**kwargs):
        super(RevealDoc, self).__init__(filename, file, **kwargs)
        self.pre      = []
        self.doc      = []
        self.attribs  = {}
        self.amInBlock = False
        self.pre.append("<!doctype html>")
        self.pre.append("<html lang=\"en\" class>")
        self.commentName = None
        self.nodeParsers = [
        exp.SetupFileParser(self),
        exp.CaptionAttributeParser(self),
        RevealAttributeParser(self),
        exp.ResultsParser(self),
        HtmlCommentParser(self),
        LatexTableBlockState(self),
        HtmlSourceBlockState(self),
        HtmlDynamicBlockState(self),
        HtmlQuoteBlockState(self),
        HtmlExampleBlockState(self),
        HtmlNotesBlockState(self),
        HtmlCheckboxListBlockState(self),
        HtmlUnorderedListBlockState(self),
        HtmlOrderedListBlockState(self),
        HtmlExportBlockState(self),
        HtmlGenericBlockState(self),
        exp.DrawerBlockState(self),
        exp.SchedulingStripper(self),
        exp.TblFmStripper(self),
        exp.AttrHtmlStripper(self),
        exp.AttrOrgStripper(self),
        exp.KeywordStripper(self),
        HtmlEmptyParser(self),
        HtmlLinkParser(self),
        RevealHrParser(self),
        RevealNameParser(self),
        HtmlHtmlHtmlParser(self),
        HtmlActiveDateParser(self),
        HtmlBoldParser(self),
        HtmlItalicsParser(self),
        HtmlUnderlineParser(self),
        HtmlStrikethroughParser(self),
        HtmlCodeParser(self),
        HtmlVerbatimParser(self),
        HtmlTargetParser(self)
        ]

    def SetAmInBlock(self,inBlock):
        self.amInBlock = inBlock

    def AmInBlock(self):
        return self.amInBlock

    def AddAttrib(self,name,val):
        if(type(val) == str):
            self.attribs[name] = val.strip()
        else:
            self.attribs[name] = val
    
    def GetAttrib(self,name):
        if(name in self.attribs):
            return self.attribs[name]
        return None

    def ClearAttrib(self):
        self.attribs.clear()
    def AddJs(self,link):
        self.pre.append("    <script type=\"text/javascript\" src=\"" + link + "\"></script>")

    def AddStyle(self,link,id=None):
        if(id == None):
            self.pre.append("    <link rel=\"stylesheet\" href=\""+link+"\">")
        else:
            self.pre.append("    <link rel=\"stylesheet\" href=\""+link+"\" id=\""+id+"\">")

    def AddInlineStyle(self,style):
        self.pre.append("    <style>{}</style>".format(style))
    # Okay
    def StartHead(self):
        self.pre.append("  <head>")
        self.pre.append("  <meta charset=\"utf-8\">")
        self.pre.append("  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no\">")

    def AddExportMetaCustom(self):
        self.AddStyle(cdn + "dist/reset.css")
        self.AddStyle(cdn + "dist/reveal.css")

        cssData      = GetGlobalOption(self.file,"REVEAL_CSS","RevealCss",None)
        if(cssData):
            self.AddInlineStyle(cssData)    


        # black: Black background, white text, blue links (default theme)
        # white: White background, black text, blue links
        # league: Gray background, white text, blue links (default theme for reveal.js < 3.0.0)
        # beige: Beige background, dark text, brown links
        # sky: Blue background, thin dark text, blue links
        # night: Black background, thick white text, orange links
        # serif: Cappuccino background, gray text, brown links
        # simple: White background, black text, blue links
        # solarized: Cream-colored background, dark green text, blue links
        # moon: Dark green background.
        theme      = GetGlobalOption(self.file,"REVEAL_THEME","RevealTheme","league").lower()
        # TODO: Validate the theme here.
        self.AddStyle(cdn + "dist/theme/{theme}.css".format(theme=theme),id="theme")
        #doc.AddStyle(cdn + "css/print/paper.css")


        highlight      = GetGlobalOption(self.file,"REVEAL_HIGHLIGHT","RevealHighlight","zenburn").lower()
        #doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/lib/css/monokai.min.css")
        #doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/lib/css/zenburn.min.css")
        #doc.AddStyle("https://cdn.jsdelivr.net/npm/highlightjs-themes@1.0.0/{hl}.css".format(hl=highlight),"highlight-theme")
        self.AddStyle(cdn + "plugin/highlight/{hl}.css".format(hl=highlight),"highlight-theme")
        
        #doc.AddStyle(cdn + "lib/css/{hl}.css".format(hl=highlight))
        #doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/lib/font/league-gothic/league-gothic.min.css")
        #doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/lib/font/source-sans-pro/source-sans-pro.min.css")
        self.vlevel = int(GetGlobalOption(self.file,"REVEAL_VLEVEL","RevealVLevel",1))
    # Okay
    def EndHead(self):
        self.pre.append("  </head>")

    # Start presentation
    def StartDocument(self, file):
        # This doesn't work have to do it as a parameter!
        transition      = GetGlobalOption(file,"REVEAL_TRANS","RevealTransition","none").lower()
        transitionSpeed = GetGlobalOption(file,"REVEAL_TRANS_SPEED","RevealTransitionSpeed","default").lower()
        self.doc.append("  <div class=\"reveal slide center has-vertical-slides has-horizontal-slides ready\" role=\"application\" data-transition-speed=\"{tspeed}\" data-background-transition=\"{transition}\">".format(
            transition=transition,
            tspeed=transitionSpeed))

    # End presentation
    def EndDocument(self):
        self.doc.append("  </div>")

    # Start slides
    def StartNodes(self):
        self.doc.append("    <div class=\"slides\">")

    # End slides
    def EndNodes(self):
        self.doc.append("    </div>")

    # Per slide properties
    #:PROPERTIES:
    #:reveal_background: images/name-of-image
    #:reveal_background_size: width-of-image
    #:reveal_background_trans: slide
    #:END:
    def StartNode(self,slide):
        # data-background-trans:        slide
        # data-background-image         URL of the image to show. GIFs restart when the slide opens.
        # data-background-size          cover   See background-size on MDN.
        # data-background-position      center  See background-position on MDN.
        # data-background-repeat        no-repeat   See background-repeat on MDN.
        # data-background-opacity
        # data-background-color 
        # data-background-video         A single video source, or a comma separated list of video sources.
        # data-background-video-loop    false   Flags if the video should play repeatedly.
        # data-background-video-muted   false   Flags if the audio should be muted.
        properties = ""
        for prop in slide.properties:
            if prop in propMappings:
                properties = "{0} {1}=\"{2}\"".format(properties,propMappings[prop],slide.properties[prop])

        self.doc.append("      <section {0}>".format(properties))

    def EndNode(self,slide):
        self.doc.append("      </section>")

    def NodeHeading(self,slide):
        heading = html.escape(slide.heading)
        level = slide.level + 1
        self.doc.append("      <h{level}>{heading}</h{level}>".format(level=level,heading=heading))


    def EscAndLinks(self, l):
        line = html.escape(l)
        m = RE_LINK.search(line)
        if(m):
            link = m.group('link').strip()
            desc = m.group('desc')
            if(not desc):
                desc = link
            else:
                desc = desc.strip()
            if(link.endswith(".png") or link.endswith(".jpg") or link.endswith(".gif")):
                if(link.startswith("file:")):
                    link = re.sub(r'^file:','',link)    
                extradata = ""  
                if(self.commentName and self.commentName in link):
                    extradata =  " " + self.commentData
                    self.commentName = None
                line = RE_LINK.sub("<img src=\"{link}\" alt=\"{desc}\"{extradata}>".format(link=link,desc=desc,extradata=extradata),line)
            else:
                line = RE_LINK.sub("<a href=\"{link}\">{desc}</a>".format(link=link,desc=desc),line)
        else:
            line = RE_BOLD.sub(r"<b>\1</b>",line)
            line = RE_ITALICS.sub(r"<i>\1</i>",line)
            line = RE_UNDERLINE.sub(r"<u>\1</u>",line)
            line = RE_STRIKETHROUGH.sub(r"<strike>\1</strike>",line)
            line = RE_VERBATIM.sub(r"<pre>\1</pre>",line)
            line = RE_CODE.sub(r"<code>\1</code>",line)
            line = RE_STARTQUOTE.sub(r"<blockquote>",line)
            line = RE_ENDQUOTE.sub(r"</blockquote>",line)
            line = RE_STARTNOTE.sub(r'<aside class="notes">',line)
            line = RE_ENDNOTE.sub(r"</aside>",line)
        if(line.strip() == ""):
            line = "<br/>"
        return line

    def TexFullEscape(self,text):
        return html.escape(text)
    def NodeBody(self,n):
        ilines = n._lines[1:]
        for parser in self.nodeParsers:
            ilines = parser.Handle(ilines,n)
        for line in ilines:
            self.doc.append(self.TexFullEscape(line))
        return
        inDrawer = False
        inUl     = False
        inSrc    = False
        skipSrc  = False
        for l in slide._lines[1:]:
            if(inDrawer):
                if(RE_END_DRAWER_LINE.search(l)):
                    inDrawer = False
                continue
            if(inSrc):
                if(RE_ENDSRC.search(l)):
                    inSrc = False
                    if(skipSrc):
                        skipSrc = False
                        continue
                    self.doc.append("    </code></pre>")
                    continue
                else:
                    if(not skipSrc):
                        self.doc.append("     " + l + "\n")
                    continue
            m = RE_STARTSRC.search(l)
            if(m):
                inSrc = True
                if(m.group('lang') == 'plantuml'):
                    skipSrc = True
                    continue
                paramstr = l[len(m.group(0)):]
                params = {}
                for ps in RE_FN_MATCH.finditer(paramstr):
                    params[ps.group(1)] = ps.group(2)
                attribs = ""
                if("data-noescape" in params):
                    attribs += " data-noescape"
                if("data-trim" in params):
                    attribs += " data-trim"
                if("data-line-numbers" in params):
                    attribs += " data-line-numbers=\"{nums}\"".format(nums=params["data-line-numbers"])
                self.doc.append("    <pre><code language=\"{language}\" {attribs}>".format(language=mapLanguage(m.group('lang')),attribs=attribs))
                continue
            if(RE_DRAWER_LINE.search(l)):
                inDrawer = True
                continue
            if(RE_SCHEDULING_LINE.search(l)):
                continue
            if(RE_RESULTS.search(l)):
                continue
            m = RE_COMMENT_TAG.search(l)
            if(m):
                self.commentData = m.group('props')
                self.commentName = m.group('name')
                continue
            m = RE_UL.search(l)
            if(m):
                if(not inUl):
                    self.doc.write("     <ul>")
                    inUl = True
                data = self.EscAndLinks(m.group('data'))
                self.doc.append("     <li>{content}</li>".format(content=data))
                continue
            elif(inUl):
                inUl = False
                self.doc.append("     </ul>")
            line = self.EscAndLinks(l)
            self.doc.append("     " + line)
        if(inUl):
            inUl = False
            self.doc.append("     </ul>")

        pass

    def StartBody(self):
        self.doc.append("  <body style=\"transition: -webkit-transform 0.8s ease 0s; transform-origin: 0px 0px;\">")

    def EndBody(self):
        self.doc.append("  </body>")

    def Progress(self):
        self.doc.append("  <div class=\"progress\" style=\"display: block;\">")
        self.doc.append("    <span style=\"width: 265px;\"></span>")
        self.doc.append("    ::after")
        self.doc.append("  </div>")

    def Dep(self, file, link, last=False):
        #location = "https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/"
        location = cdn
        location = GetGlobalOption(file,"REVEAL_LOCATION","RevealLocation",location)    
        location = location + "plugin/"
        comma =","
        if(last):
            comma = ""
        self.doc.append("              { src: '"+location+link+"', async: true }"+comma) 

    def SDep(self,js):
        self.doc.append("  <script src=\"{location}plugin/{js}\"></script>".format(location=cdn,js=js))

    def InsertScripts(self,file):
        #location = "https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/"
        location = cdn
        location = GetGlobalOption(file,"REVEAL_LOCATION","RevealLocation",location)    
        self.doc.append("  <script src=\"{location}dist/reveal.min.js\"></script>".format(location=location))
        self.SDep("markdown/markdown.js")
        self.SDep("highlight/highlight.js")
        self.SDep("search/search.js")
        self.SDep("zoom/zoom.js")
        self.SDep("notes/notes.js")
        self.SDep("math/math.js")
        self.doc.append("  <script>")
        #self.fs.write("       Reveal.initialize();\n")
        self.doc.append("      Reveal.initialize({")
        self.doc.append("          hash: true,") # Allow browsing back to this slide.
        transition      = GetGlobalOption(file,"REVEAL_TRANS","RevealTransition","none").lower()
        transitionSpeed = GetGlobalOption(file,"REVEAL_TRANS_SPEED","RevealTransitionSpeed","default").lower()
        # Transition style
        self.doc.append("          transition: '{transition}',".format(transition=transition)) # none/fade/slide/convex/concave/zoom
        self.doc.append("          transitionSpeed: '{transitionSpeed}',".format(transitionSpeed=transitionSpeed)) # default/fast/slow
        #self.fs.write("          showNotes: false,\n")
        self.doc.append("          dependencies: [") 
        #self.Dep(file, "markdown/marked.js")
        self.Dep(file, "markdown/markdown.js")
        self.Dep(file, "highlight/highlight.js")
        self.Dep(file, "search/search.js")
        #self.Dep(file, "zoom-js/zoom.js")
        self.Dep(file, "zoom/zoom.js")
        self.Dep(file, "notes/notes.js")
        #self.Dep("print-pdf/print-pdf.min.js")
        self.Dep(file, "math/math.js",True)
        self.doc.append("          ],") 
        self.doc.append("          plugins: [ RevealMarkdown, RevealHighlight, RevealNotes ]")
        self.doc.append("      });")
        self.doc.append("  </script>")

    def BuildDoc(self):
        out = '\n'.join(self.pre) + '\n' + '\n'.join(self.doc) + '\n'
        return out

    def FinishDocCustom(self):
        self.fs.write(self.BuildDoc())
        self.fs.write("</html>\n")

class OrgExportFileRevealJsCommand(sublime_plugin.TextCommand):
    def OnDoneSourceBlockExecution(self):
        # Reload if necessary
        self.file = db.Get().FindInfo(self.view)
        self.doc  = None
        try:
            outputFilename = exp.ExportFilename(self.view,".html",self.suffix)
            self.doc = RevealDoc(outputFilename,self.file)
            self.helper    = exp.OrgExportHelper(self.view,self.index)
            self.helper.Run(outputFilename, self.doc)
        finally:    
            evt.EmitIf(self.onDone)

    def run(self,edit, onDone=None, index=None, suffix=""):
        self.file = db.Get().FindInfo(self.view)
        self.onDone = onDone
        self.suffix = suffix
        if(index != None):
            self.index = index
        else:
            self.index = None
        if(None == self.file):
            log.error("Not an org file? Cannot build reveal document")
            evt.EmitIf(onDone)  
            return
        if(sets.Get("revealExecuteSourceOnExport",False)):
            self.view.run_command('org_execute_all_source_blocks',{"onDone":evt.Make(self.OnDoneSourceBlockExecution),"amExporting": True})
        else:
            self.OnDoneSourceBlockExecution()

# pandoc -s -o output.html input.txt

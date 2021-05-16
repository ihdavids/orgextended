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
import OrgExtended.orghtmlexporter as hexp
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


RE_ATTR_REVEAL = regex.compile(r"^\s*[#][+]ATTR_REVEAL[:]\s*(?P<data>.*)")
class RevealAttributeParser(exp.AttributeParser):
    def __init__(self,doc):
        super(RevealAttributeParser,self).__init__('attr_reveal',RE_ATTR_REVEAL,doc)

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
        hexp.HtmlCommentParser(self),
        hexp.HtmlTableBlockState(self),
        hexp.HtmlSourceBlockState(self),
        hexp.HtmlDynamicBlockState(self),
        hexp.HtmlQuoteBlockState(self),
        hexp.HtmlExampleBlockState(self),
        hexp.HtmlNotesBlockState(self),
        hexp.HtmlCheckboxListBlockState(self),
        hexp.HtmlUnorderedListBlockState(self),
        hexp.HtmlOrderedListBlockState(self),
        hexp.HtmlExportBlockState(self),
        hexp.HtmlGenericBlockState(self),
        exp.DrawerBlockState(self),
        exp.SchedulingStripper(self),
        exp.TblFmStripper(self),
        exp.AttrHtmlStripper(self),
        exp.AttrOrgStripper(self),
        exp.KeywordStripper(self),
        hexp.HtmlEmptyParser(self),
        hexp.HtmlLinkParser(self),
        RevealHrParser(self),
        RevealNameParser(self),
        hexp.HtmlHtmlHtmlParser(self),
        hexp.HtmlActiveDateParser(self),
        hexp.HtmlBoldParser(self),
        hexp.HtmlItalicsParser(self),
        hexp.HtmlUnderlineParser(self),
        hexp.HtmlStrikethroughParser(self),
        hexp.HtmlCodeParser(self),
        hexp.HtmlVerbatimParser(self),
        hexp.HtmlTargetParser(self)
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

    def TextFullEscape(self,text):
        return html.escape(text)

    def NodeBody(self,n):
        ilines = n._lines[1:]
        for parser in self.nodeParsers:
            ilines = parser.Handle(ilines,n)
        for line in ilines:
            self.doc.append(self.TextFullEscape(line))
        return

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
        global cdn        
        cdn = GetGlobalOption(self.file,"REVEAL_LOCATION","RevealLocation",cdn)
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

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
import OrgExtended.orgutil.temp as tf
import OrgExtended.pymitter as evt
import OrgExtended.orgnotifications as notice
import OrgExtended.orgextension as ext
import OrgExtended.orgsourceblock as src
import OrgExtended.orgexporter as exp
import OrgExtended.orghtmlexporter as hexp
import yaml
import sys
import subprocess
import html

log = logging.getLogger(__name__)



# Global properties I AT LEAST want to support.
# Both as a property on the document and in our settings.
#+OPTIONS: num:nil toc:nil
#+REVEAL_TRANS: None/Fade/Slide/Convex/Concave/Zoom
#+REVEAL_THEME: Black/White/League/Sky/Beige/Simple/Serif/Blood/Night/Moon/Solarized
#+Title: Title of Your Talk
#+Author: Your Name
#+Email: Your Email Address or Twitter Handle

def GetCollapsibleCodeOld():
  return """
var coll = document.getElementsByClassName("collapsible");
var i;

for (i = 0; i < coll.length; i++) {
  coll[i].addEventListener("click", function() {
    this.classList.toggle("active");
    var content = this.nextElementSibling;
    if (content.style.display === "block") {
      content.style.display = "none";
    } else {
      content.style.display = "block";
    }
  });
}
"""


def GetCollapsibleCode():
  return """
var coll = document.getElementsByClassName("collapsible");
var i;
var accume = 0;
for (i = 0; i < coll.length; i++) {
  coll[i].addEventListener("click", function() {
    this.classList.toggle("active");
    var content = this.nextElementSibling;
    if (content.style.maxHeight) {
      content.style.maxHeight = null;
    } else {
      content.style.maxHeight = content.scrollHeight + "px";
    }
    accume += content.scrollHeight + 5;
    while(content.parentNode && (content.parentNode.nodeName == 'DIV' || content.parentNode.nodeName == 'SECTION')) {
      if(content.parentNode.nodeName == 'DIV') {
        //alert(content.parentNode.nodeName);
        content.parentNode.style.maxHeight = (accume + content.parentNode.scrollHeight) + "px";
        accume += content.parentNode.scrollHeight;
      }
      content = content.parentNode;
    }
  });
  coll[i].click();
}
"""

def GetCollapsibleCss():
  return """
  .node-body {
  padding: 0 18px;
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.2s ease-out;
  }
  .active, .collapsible:hover {
  background-color: #ccc;
  }
  .collapsible:after {
    content: '\\002b';
    font-size: 22px;
    float: right;
    margin-right: 20px;
  }
  .active:after {
  content: '\\2212';
  font-size: 22px;
  margin-right: 20px;
  }
"""


RE_CAPTION = regex.compile(r"^\s*[#][+]CAPTION[:]\s*(?P<caption>.*)")
RE_ATTR = regex.compile(r"^\s*[#][+]ATTR_HTML[:](?P<params>\s+[:](?P<name>[a-zA-Z0-9._-]+)\s+(?P<value>([^:]|((?<! )[:]))+))+$")
RE_ATTR_ORG = regex.compile(r"^\s*[#][+]ATTR_ORG[:] ")
RE_SCHEDULING_LINE = re.compile(r"^\s*(SCHEDULED|CLOSED|DEADLINE|CLOCK)[:].*")
RE_DRAWER_LINE = re.compile(r"^\s*[:].+[:]\s*$")
RE_END_DRAWER_LINE = re.compile(r"^\s*[:](END|end)[:]\s*$")
RE_LINK = re.compile(r"\[\[(?P<link>[^\]]+)\](\[(?P<desc>[^\]]+)\])?\]")
RE_UL   = re.compile(r"^(?P<indent>\s*)(-|[+])\s+(?P<data>.+)")
RE_STARTQUOTE = re.compile(r"#\+(BEGIN_QUOTE|BEGIN_EXAMPLE|BEGIN_VERSE|BEGIN_CENTER|begin_quote|begin_example|begin_verse|begin_center)")
RE_ENDQUOTE = re.compile(r"#\+(END_QUOTE|END_EXAMPLE|END_VERSE|END_CENTER|end_quote|end_example|end_verse|end_center)")
RE_STARTNOTE = re.compile(r"#\+(BEGIN_NOTES|begin_notes)")
RE_ENDNOTE = re.compile(r"#\+(END_NOTES|end_notes)")
RE_FN_MATCH = re.compile(r"\s*[:]([a-zA-Z0-9-_]+)\s+([^: ]+)?\s*")
RE_STARTSRC = re.compile(r"^\s*#\+(BEGIN_SRC|begin_src|BEGIN:|begin:)\s+(?P<lang>[a-zA-Z0-9]+)")
RE_ENDSRC = re.compile(r"^\s*#\+(END_SRC|end_src|end:|END:)")
RE_RESULTS = re.compile(r"^\s*#\+RESULTS.*")
RE_TABLE_ROW = re.compile(r"^\s*[|]")
RE_TABLE_SEPARATOR = re.compile(r"^\s*[|][-]")
RE_CHECKBOX         = re.compile(r"^\[ \] ")
RE_CHECKED_CHECKBOX = re.compile(r"^\[[xX]\] ")
RE_PARTIAL_CHECKBOX = re.compile(r"^\[[-]\] ")
RE_EMPTY_LINE = re.compile(r"^\s*$")


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

def GetStyleRelatedData(style, extension):
  inHeader = os.path.join(sublime.packages_path(),"User", "htmlstyles", style + extension)
  if(os.path.isfile(inHeader)):
    with open(inHeader) as f:
      contents = f.read()
      return contents
  resourceName = "Packages/OrgExtended/htmlstyles/" + style + extension
  try:
    contents = sublime.load_resource(resourceName)
    return contents
  except:
    pass
  #inHeader = os.path.join(sublime.packages_path(),"OrgExtended", "htmlstyles", style + extension)
  #if(os.path.isfile(inHeader)):
  # with open(inHeader) as f:
  #   contents = f.read()
  #   return contents
  return ""


def GetStyleRelatedPropertyData(file, key, setting):
  val = exp.GetGlobalOption(file, key, setting, "")
  if("<" in val or "{" in val):
    return val
  elif(os.path.isfile(val)):
    with open(val) as f:
      contents = f.read()
      return contents
  else:
    return val


def GetHighlightJsCss(style):
  import OrgExtended.orgutil.webpull as wp
  wp.download_highlightjs()
  data = os.path.join(sublime.packages_path(),"User", "highlightjs", "styles", style + ".css")
  if(os.path.isfile(data)):
    with open(data) as f:
      contents = f.read()
      return contents


def GetHighlightJs():
  import OrgExtended.orgutil.webpull as wp
  wp.download_highlightjs()
  data = os.path.join(sublime.packages_path(),"User", "highlightjs", "highlight.pack.js")
  if(os.path.isfile(data)):
    with open(data) as f:
      contents = f.read()
      return contents


def GetHeaderData(style, file):
  d1 = GetStyleRelatedData(style,"_inheader.html")
  d2 = GetStyleRelatedPropertyData(file, "HtmlInHeader", "HTML_INHEADER")
  return d1 + d2

def GetHeadingData(style, file):
  d1 = GetStyleRelatedData(style,"_heading.html")
  d2 = GetStyleRelatedPropertyData(file, "HtmlHeading", "HTML_HEADING")
  return d1 + d2

def GetFootingData(style, file):
  d1 = GetStyleRelatedData(style,"_footing.html")
  d2 = GetStyleRelatedPropertyData(file, "HtmlFooting", "HTML_FOOTING")
  return d1 + d2

def GetStyleData(style, file):
  d1 = GetStyleRelatedData(style,".css")
  d2 = GetStyleRelatedPropertyData(file, "HtmlCss", "HTML_CSS")
  return d1 + d2

class HtmlHrParser(exp.HrParser):
    def __init__(self,doc):
        super(HtmlHrParser,self).__init__(doc)
    def HandleLine(self,m,l,n):
        self.e.doc.append(r"<hr/>")

class HtmlNameParser(exp.NameParser):
    def __init__(self,doc):
        super(HtmlNameParser,self).__init__(doc)
    def HandleLine(self,m,l,n):
        self.e.doc.append("<a name=\"{data}\"/>".format(data=m.group('data')))


RE_ATTR_HTML = regex.compile(r"^\s*[#][+]ATTR_HTML[:]\s*(?P<data>.*)")
class HtmlAttributeParser(exp.AttributeParser):
    def __init__(self,doc):
        super(HtmlAttributeParser,self).__init__('attr_html',RE_ATTR_HTML,doc)

class HtmlDoc(exp.OrgExporter):
  def __init__(self, filename, file,**kwargs):
    super(HtmlDoc, self).__init__(filename, file, **kwargs)
    self.pre      = []
    self.doc      = []
    self.attribs  = {}
    self.amInBlock = False
    self.pre.append("<!DOCTYPE html>\n")
    self.pre.append("<!-- exported by orgextended html exporter -->\n")
    if(self.language):
      self.pre.append("<html xmlns=\"http://www.w3.org/1999/xhtml\" lang=\"{language}\" xml:lang=\"{language}\">".format(language=self.language))
    else: 
      self.pre.append("<html lang=\"en\" class>\n")
    self.commentName = None
    self.figureIndex = 1
    self.tableIndex  = 1
    self.nodeParsers = [
    exp.SetupFileParser(self),
    exp.CaptionAttributeParser(self),
    HtmlAttributeParser(self),
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
    HtmlHrParser(self),
    HtmlNameParser(self),
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
    self.pre.append("    <script type=\"text/javascript\" src=\"" + link + "\"></script>\n")

  def AddStyle(self,link):
    self.pre.append("    <link rel=\"stylesheet\" href=\""+link+"\"></link>\n")

  def AddInlineStyle(self,content):
    # <style>
    #    BLOCK
    # </style> 
    self.pre.append("   <style>\n{0}\n   </style>\n".format(content))

  def InsertJs(self,content):
    # <style>
    #    BLOCK
    # </style> 
    self.doc.append("   <script>\n{0}\n   </script>\n".format(content))

  def StartHead(self):
    self.pre.append("  <head>\n")

  def EndHead(self):
    data = GetHeaderData(self.style, self.file)
    self.pre.append(data)
    self.pre.append("  </head>\n")

  def AddExportMetaCustom(self):
    if(self.title):
      self.pre.append("<title>{title}</title>".format(title=self.title))
    if(self.author):
      self.pre.append("<meta name=\"author\" content=\"{author}\" />".format(author=self.author))

  def StartDocument(self, file):
    self.doc.append("  <div class=\"ready\">\n")

  def EndDocument(self):
    self.doc.append("  </div>\n")

  def StartNodes(self):
    self.doc.append("    <div class=\"orgmode\">\n")

  def EndNodes(self):
    self.doc.append("    </div>\n")

  # Per slide properties
  #:PROPERTIES:
  #:css_property: value
  #:END:
  def StartNode(self,n):
    properties = ""
    for prop in n.properties:
      properties = "{0} {1}=\"{2}\"".format(properties, prop, n.properties[prop])
    self.doc.append("      <section {0}>\n".format(properties))

  def StartNodeBody(self, n):
    level = n.level + 1
    self.doc.append("      <div class=\"node-body h{level}\">\n".format(level=level))

  def EndNodeBody(self,n):
    self.doc.append("      </div>\n")

  def EndNode(self,n):
    self.doc.append("      </section>\n")

  def NodeHeading(self,n):
    heading = html.escape(n.heading)
    level = n.level + 1
    self.doc.append("      <h{level} class=\"collapsible\">{heading}</h{level}>\n".format(level=level,heading=heading))

  def ClearAttributes(self):
    self.attrs = {}
    self.caption = None

  def AttributesGather(self, l):
    if(self.PreScanExportCommentsGather(l)):
      return True
    m = RE_CAPTION.match(l)
    if(not hasattr(self, 'caption')):
      self.caption = None
    if(m):
      self.caption = m.captures('caption')[0]
      return True
    m = RE_ATTR.match(l)
    # We capture #+ATTR_HTML: lines
    if(m):
      keys = m.captures('name')
      vals = m.captures('value')
      if not hasattr(self,'attrs'):
        self.attrs = {}
      for i in range(len(keys)):
        self.attrs[keys[i]] = vals[i]
      return True
    # We skip #+ATTR_ORG: lines
    m = RE_ATTR_ORG.match(l)
    if(m):
      return True
    return False

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
      if(link.endswith(".png") or link.endswith(".jpg") or link.endswith(".jpeg") or link.endswith(".gif")):
        if(link.startswith("file:")):
          link = re.sub(r'^file:','',link)  
        extradata = ""  
        if(self.commentName and self.commentName in link):
          extradata =  " " + self.commentData
          self.commentName = None
        if(hasattr(self,'attrs')):
          for key in self.attrs:
            extradata += " " + str(key) + "=\"" + str(self.attrs[key]) + "\""
        preamble = ""
        postamble = ""
        if(hasattr(self,'caption') and self.caption):
          preamble = "<div class=\"figure\"><p>"
          postamble = "</p><p><span class=\"figure-number\">Figure {index}: </span>{caption}</p></div>".format(index=self.figureIndex,caption=self.caption)
          self.figureIndex += 1
        line = RE_LINK.sub("{preamble}<img src=\"{link}\" alt=\"{desc}\"{extradata}>{postamble}".format(preamble=preamble,link=link,desc=desc,extradata=extradata,postamble=postamble),line)
        self.ClearAttributes()
      else:
        line = RE_LINK.sub("<a href=\"{link}\">{desc}</a>".format(link=link,desc=desc),line)
        self.ClearAttributes()
    else:
      line = exp.RE_BOLD.sub(r"<b>\1</b>",line)
      line = exp.RE_ITALICS.sub(r"<i>\1</i>",line)
      line = exp.RE_UNDERLINE.sub(r"<u>\1</u>",line)
      line = exp.RE_STRIKETHROUGH.sub(r"<strike>\1</strike>",line)
      line = exp.RE_VERBATIM.sub(r"<pre>\1</pre>",line)
      line = exp.RE_CODE.sub(r"<code>\1</code>",line)
      line = RE_STARTQUOTE.sub(r"<blockquote>",line)
      line = RE_ENDQUOTE.sub(r"</blockquote>",line)
      line = RE_STARTNOTE.sub(r'<aside class="notes">',line)
      line = RE_ENDNOTE.sub(r"</aside>",line)
      line = RE_CHECKBOX.sub(r'<input type="checkbox">',line)
      line = RE_CHECKED_CHECKBOX.sub(r'<input type="checkbox" checked>',line)
      if(sets.Get("htmlExportPartialCheckboxChecked",True)):
        line = RE_PARTIAL_CHECKBOX.sub(r'<input type="checkbox" checked>',line)
      else:
        line = RE_PARTIAL_CHECKBOX.sub(r'<input type="checkbox">',line)
      line = exp.RE_HR.sub(r'<hr>',line)
    return line

  def TextFullEscape(self,text):
      return html.escape(text)


  def Escape(self,str):
    return self.TextFullEscape(str)

  def NodeBody(self,slide):
    ilines = slide._lines[1:]
    for parser in self.nodeParsers:
        ilines = parser.Handle(ilines, slide)
    for line in ilines:
        self.doc.append(self.TextFullEscape(line))
    return
    inDrawer = False
    inResults= False
    inUl     = 0
    ulIndent = 0
    inTable  = False
    haveTableHeader = False
    inSrc    = False
    skipSrc  = False
    exp      = None
    for l in slide._lines[1:]:
      if(self.AttributesGather(l)):
        continue
      if(inResults):
        if(l.strip() == ""):
          inResults = False
        elif(RE_ENDSRC.search(l) or RE_END_DRAWER_LINE.search(l)):
          inResults = False
          continue
        if(inResults):
          if(exp == 'code' or exp == 'none'):
            continue
          else:
            line = self.EscAndLinks(l)
            self.fs.write("     " + line + "\n")
            continue
      if(inDrawer):
        if(RE_END_DRAWER_LINE.search(l)):
          inDrawer = False
        continue
      if(inTable):
        if(RE_TABLE_ROW.search(l)):
          if(RE_TABLE_SEPARATOR.search(l)):
            continue
          else:
            tds = l.split('|')
            if(len(tds) > 3):
              # An actual table row, build a row
              self.fs.write("    <tr>\n")
              for td in tds[1:-1]:
                if(haveTableHeader):
                  self.fs.write("     <td>{0}</td>\n".format(self.EscAndLinks(td)))
                else:
                  self.fs.write("     <th>{0}</th>\n".format(self.EscAndLinks(td)))
              haveTableHeader = True
              # Fill in the tds
              self.fs.write("    </tr>\n")
              continue
        else:
          self.fs.write("    </table>\n")
          inTable         = False
          haveTableHeader = False
      if(inSrc):
        if(RE_ENDSRC.search(l)):
          inSrc = False
          if(skipSrc):
            skipSrc = False
            continue
          self.fs.write("    </code></pre>\n")
          continue
        else:
          if(not skipSrc):
            self.fs.write("     " + l + "\n")
          continue
      # src block
      m = RE_STARTSRC.search(l)
      if(m):
        inSrc = True
        language = m.group('lang')
        paramstr = l[len(m.group(0)):]
        p = type('', (), {})() 
        src.BuildFullParamList(p,language,paramstr,slide)
        exp = p.params.Get("exports",None)
        if(isinstance(exp,list) and len(exp) > 0):
          exp = exp[0]
        if(exp == 'results' or exp == 'none'):
          skipSrc = True
          continue
        # Some languages we skip source by default
        skipLangs = sets.Get("htmlDefaultSkipSrc",[])
        if(exp == None and language == skipLangs):
          skipSrc = True
          continue
        #params = {}
        #for ps in RE_FN_MATCH.finditer(paramstr):
        # params[ps.group(1)] = ps.group(2)
        attribs = ""
        # This is left over from reveal.
        if(p.params.Get("data-line-numbers",None)):
          attribs += " data-line-numbers=\"{nums}\"".format(nums=p.params.Get("data-line-numbers",""))
        self.fs.write("    <pre><code language=\"{lang}\" {attribs}>\n".format(lang=mapLanguage(language),attribs=attribs))
        continue
      # property drawer
      if(RE_DRAWER_LINE.search(l)):
        inDrawer = True
        continue
      # scheduling
      if(RE_SCHEDULING_LINE.search(l)):
        continue
      if(RE_RESULTS.search(l)):
        inResults = True
        continue
      m = RE_COMMENT_TAG.search(l)
      if(m):
        self.commentData = m.group('props')
        self.commentName = m.group('name')
        continue

      m = RE_TABLE_ROW.search(l)
      if(m):
        self.fs.write("    <table>\n")
        if(hasattr(self,'caption') and self.caption):
          self.fs.write("    <caption class=\"t-above\"><span class=\"table-number\">Table {index}:</span>{caption}</caption>".format(index=self.tableIndex,caption=self.caption))
          self.tableIndex += 1
          self.ClearAttributes()
        if(not RE_TABLE_SEPARATOR.search(l)):
          tds = l.split('|')
          if(len(tds) > 3):
            self.fs.write("    <tr>\n")
            for td in tds[1:-1]:
              self.fs.write("     <th>{0}</th>".format(self.EscAndLinks(td)))
            self.fs.write("    </tr>\n")
          haveTableHeader = True
        inTable = True
        continue
      m = RE_UL.search(l)
      if(m):
        thisIndent = len(m.group('indent'))
        if(not inUl):
          ulIndent = thisIndent
          self.fs.write("     <ul>\n")
          inUl += 1
        elif(thisIndent > ulIndent):
          ulIndent = thisIndent
          self.fs.write("     <ul>\n")
          inUl += 1
        elif(thisIndent < ulIndent and inUl > 1):
          inUl -= 1
          self.fs.write("     </ul>\n")
        data = self.EscAndLinks(m.group('data'))
        self.fs.write("     <li>{content}</li>\n".format(content=data))
        continue
      elif(inUl):
        while(inUl > 0):
          inUl -= 1
          self.fs.write("     </ul>\n")
      if(RE_EMPTY_LINE.search(l)):
        self.fs.write("    <br>\n")
      # Normal Write
      line = self.EscAndLinks(l)
      self.fs.write("     " + line + "\n")
    if(inUl):
      inUl -= 1
      self.fs.write("     </ul>\n")

    pass

  def StartBody(self):
    self.doc.append("  <body>\n")
    data = GetHeadingData(self.style, self.file)
    if(data):
      self.doc.append(data)

  def EndBody(self):
    data = GetFootingData(self.style, self.file)
    if(data):
      self.doc.append(data)
    self.doc.append("  </body>\n")

  def InsertScripts(self,file):
    #self.InsertJs(GetHighlightJs())
    self.AddJs('https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.6.0/highlight.min.js')
    self.doc.append("<script>hljs.initHighlightingOnLoad();</script>\n")
    self.InsertJs(GetCollapsibleCode())

  def Postamble(self):
    self.doc.append("<div id=\"postamble\" class=\"status\">")
    if(self.date):
      self.doc.append("<p class=\"date\">Date: {date}</p>".format(date=self.date))
    if(self.author):
      self.doc.append("<p class=\"author\">Author: {author}</p>".format(author=self.author))
    self.doc.append("<p class=\"date\">Created: {date}</p>".format(date=str(datetime.datetime.now())))
    self.doc.append("</div>")

  def BuildDoc(self):
      out = '\n'.join(self.pre) + '\n' + '\n'.join(self.doc) + '\n'
      return out

  def FinishDocCustom(self):
    self.Postamble()
    self.doc.append("</html>\n")
    self.fs.write(self.BuildDoc())

class HtmlExportHelper(exp.OrgExportHelper):
  def __init__(self,view,index):
    super(HtmlExportHelper,self).__init__(view,index)

  def CustomBuildHead(self):
    highlight      = exp.GetGlobalOption(self.file,"HTML_HIGHLIGHT","HtmlHighlight","zenburn").lower()
    #self.doc.AddInlineStyle(GetHighlightJsCss(highlight))
    self.doc.AddStyle('https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.6.0/styles/default.min.css')
    self.doc.AddInlineStyle(GetCollapsibleCss())
    self.doc.AddInlineStyle(GetStyleData(self.doc.style, self.file))

# Export the entire file using our internal exporter
class OrgExportFileOrgHtmlCommand(sublime_plugin.TextCommand):
  def OnDoneSourceBlockExecution(self):
    # Reload if necessary
    self.file = db.Get().FindInfo(self.view)
    doc = None
    self.style = exp.GetGlobalOption(self.file,"HTML_STYLE","HtmlStyle","blocky").lower()
    log.log(51,"EXPORT STYLE: " + self.style)
    try:
      outputFilename = exp.ExportFilename(self.view,".html", self.suffix)
      doc            = HtmlDoc(outputFilename, self.file)
      doc.style      = self.style
      self.helper    = HtmlExportHelper(self.view, self.index)
      self.helper.Run(outputFilename, doc)
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
    if(sets.Get("htmlExecuteSourceOnExport",True)):
      self.view.run_command('org_execute_all_source_blocks',{"onDone":evt.Make(self.OnDoneSourceBlockExecution),"amExporting": True})
    else:
      self.OnDoneSourceBlockExecution()

def sync_up_on_closed():
  notice.Get().BuildToday()


class OrgDownloadHighlighJs(sublime_plugin.TextCommand):
  def run(self,edit):
    log.info("Trying to download highlightjs")
    import OrgExtended.orgutil.webpull as wp
    wp.download_highlightjs()

class OrgExportSubtreeAsOrgHtmlCommand(sublime_plugin.TextCommand):
  def OnDone(self):
    evt.EmitIf(self.onDone)

  def run(self,edit,onDone=None):
    self.onDone = onDone
    n = db.Get().AtInView(self.view)
    if(n == None):
      log.error(" Failed to find node! Subtree cannot be exported!")
      return
    index = 0
    for i in range(0,len(n.env._nodes)):
      if(n == n.env._nodes[i]):
        index = i
    if(index == 0):
      log.error(" Failed to find node in file! Something is wrong. Cannot export subtree!")
      return
    self.view.run_command('org_export_file_org_html', {"onDone": evt.Make(self.OnDone), "index": index, "suffix":"_subtree"})

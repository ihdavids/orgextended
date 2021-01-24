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
import OrgExtended.orgproperties as props
import OrgExtended.orgutil.temp as tf
import OrgExtended.pymitter as evt
import OrgExtended.orgnotifications as notice
import OrgExtended.orgextension as ext
import yaml
import sys
import subprocess
import html

log = logging.getLogger(__name__)



def HtmlFilename(view):
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

for (i = 0; i < coll.length; i++) {
  coll[i].addEventListener("click", function() {
    this.classList.toggle("active");
    var content = this.nextElementSibling;
    if (content.style.maxHeight) {
      content.style.maxHeight = null;
    } else {
      content.style.maxHeight = content.scrollHeight + "px";
    }
    var accume = content.scrollHeight + 5;
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


RE_SCHEDULING_LINE = re.compile(r"^\s*(SCHEDULED|CLOSED|DEADLINE|CLOCK)[:].*")
RE_DRAWER_LINE = re.compile(r"^\s*[:].+[:]\s*$")
RE_END_DRAWER_LINE = re.compile(r"^\s*[:](END|end)[:]\s*$")
RE_LINK = re.compile(r"\[\[(?P<link>[^\]]+)\](\[(?P<desc>[^\]]+)\])?\]")
RE_UL   = re.compile(r"^(?P<indent>\s*)(-|[+])\s+(?P<data>.+)")
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
RE_STARTSRC = re.compile(r"^\s*#\+(BEGIN_SRC|begin_src|BEGIN:|begin:)\s+(?P<lang>[a-zA-Z0-9]+)")
RE_ENDSRC = re.compile(r"^\s*#\+(END_SRC|end_src|end:|END:)")
RE_RESULTS = re.compile(r"^\s*#\+RESULTS.*")
RE_TABLE_ROW = re.compile(r"^\s*[|]")
RE_TABLE_SEPARATOR = re.compile(r"^\s*[|][-]")
RE_CHECKBOX         = re.compile(r"^\[ \] ")
RE_CHECKED_CHECKBOX = re.compile(r"^\[[xX]\] ")
RE_PARTIAL_CHECKBOX = re.compile(r"^\[[-]\] ")
RE_EMPTY_LINE = re.compile(r"^\s*$")
RE_HR = re.compile(r"^((\s*-----+\s*)|(\s*---\s+[a-zA-Z0-9 ]+\s+---\s*))$")


# <!-- multiple_stores height="50%" width="50%" --> 
RE_COMMENT_TAG = re.compile(r"^\s*[<][!][-][-]\s+(?P<name>[a-zA-Z0-9_-]+)\s+(?P<props>.*)\s+[-][-][>]")


def mapLanguage(lang):
	if(lang == 'html'):
		return 'language-html'
	elif(lang == 'python'):
		return 'language-python'
	else:
		return lang

def GetStyleRelatedData(style, extension):
	inHeader = os.path.join(sublime.packages_path(),"User", "htmlstyles", style + extension)
	if(os.path.isfile(inHeader)):
		with open(inHeader) as f:
			contents = f.read()
			return contents
	inHeader = os.path.join(sublime.packages_path(),"OrgExtended", "htmlstyles", style + extension)
	if(os.path.isfile(inHeader)):
		with open(inHeader) as f:
			contents = f.read()
			return contents
	return ""


def GetStyleRelatedPropertyData(file, key, setting):
	val = GetGlobalOption(file, key, setting, "")
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

class HtmlDoc:
	def __init__(self, filename, file):
		self.file = file
		self.fs = open(filename,"w")
		self.fs.write("<!DOCTYPE html>\n")
		self.fs.write("<!-- exported by orgextended html exporter -->\n")
		self.fs.write("<html lang=\"en\" class>\n")
		self.commentName = None

	def AddJs(self,link):
		self.fs.write("    <script type=\"text/javascript\" src=\"" + link + "\"></script>\n")

	def AddStyle(self,link):
		self.fs.write("    <link rel=\"stylesheet\" href=\""+link+"\"></link>\n")

	def AddInlineStyle(self,content):
		# <style>
		#    BLOCK
		# </style> 
		self.fs.write("   <style>\n{0}\n   </style>\n".format(content))

	def InsertJs(self,content):
		# <style>
		#    BLOCK
		# </style> 
		self.fs.write("   <script>\n{0}\n   </script>\n".format(content))

	def StartHead(self):
		self.fs.write("  <head>\n")

	def EndHead(self):
		data = GetHeaderData(self.style, self.file)
		self.fs.write(data)
		self.fs.write("  </head>\n")

	def StartDocument(self, file):
		self.fs.write("  <div class=\"ready\">\n")

	def EndDocument(self):
		self.fs.write("  </div>\n")

	def StartNodes(self):
		self.fs.write("    <div class=\"orgmode\">\n")

	def EndNodes(self):
		self.fs.write("    </div>\n")

	# Per slide properties
	#:PROPERTIES:
	#:css_property: value
	#:END:
	def StartNode(self,n):
		properties = ""
		for prop in n.properties:
			properties = "{0} {1}=\"{2}\"".format(properties, prop, n.properties[prop])
		self.fs.write("      <section {0}>\n".format(properties))

	def StartNodeBody(self, n):
		level = n.level + 1
		self.fs.write("      <div class=\"node-body h{level}\">\n".format(level=level))

	def EndNodeBody(self,n):
		self.fs.write("      </div>\n")

	def EndNode(self,n):
		self.fs.write("      </section>\n")

	def NodeHeading(self,n):
		heading = html.escape(n.heading)
		level = n.level + 1
		self.fs.write("      <h{level} class=\"collapsible\">{heading}</h{level}>\n".format(level=level,heading=heading))


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
			line = RE_CHECKBOX.sub(r'<input type="checkbox">',line)
			line = RE_CHECKED_CHECKBOX.sub(r'<input type="checkbox" checked>',line)
			line = RE_PARTIAL_CHECKBOX.sub(r'<input type="checkbox" checked>',line)
			line = RE_HR.sub(r'<hr>',line)
		return line

	def NodeBody(self,slide):
		inDrawer = False
		inUl     = 0
		ulIndent = 0
		inTable  = False
		haveTableHeader = False
		inSrc    = False
		skipSrc  = False
		for l in slide._lines[1:]:
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
				if(m.group('lang') == 'plantuml'):
					skipSrc = True
					continue
				paramstr = l[len(m.group(0)):]
				params = {}
				for ps in RE_FN_MATCH.finditer(paramstr):
					params[ps.group(1)] = ps.group(2)
				attribs = ""
				# This is left over from reveal.
				if("data-line-numbers" in params):
					attribs += " data-line-numbers=\"{nums}\"".format(nums=params["data-line-numbers"])
				self.fs.write("    <pre><code language=\"{language}\" {attribs}>\n".format(language=mapLanguage(m.group('lang')),attribs=attribs))
				continue
			# property drawer
			if(RE_DRAWER_LINE.search(l)):
				inDrawer = True
				continue
			# scheduling
			if(RE_SCHEDULING_LINE.search(l)):
				continue
			if(RE_RESULTS.search(l)):
				continue
			m = RE_COMMENT_TAG.search(l)
			if(m):
				self.commentData = m.group('props')
				self.commentName = m.group('name')
				continue

			m = RE_TABLE_ROW.search(l)
			if(m):
				self.fs.write("    <table>\n")
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
					inul -= 1
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
		self.fs.write("  <body>\n")
		data = GetHeadingData(self.style, self.file)
		if(data):
			self.fs.write(data)

	def EndBody(self):
		data = GetFootingData(self.style, self.file)
		if(data):
			self.fs.write(data)
		self.fs.write("  </body>\n")

	def InsertScripts(self,file):
		self.InsertJs(GetHighlightJs())
		self.fs.write("<script>hljs.initHighlightingOnLoad();</script>\n")
		self.InsertJs(GetCollapsibleCode())

	def Close(self):
		self.fs.write("</html>\n")
		self.fs.close()


# Export the entire file using pandoc 
class OrgExportFileOHtmlCommand(sublime_plugin.TextCommand):
	def build_head(self, doc):
		highlight      = GetGlobalOption(self.file,"HTML_HIGHLIGHT","HtmlHighlight","zenburn").lower()
		doc.AddInlineStyle(GetHighlightJsCss(highlight))
		doc.AddInlineStyle(GetCollapsibleCss())
		doc.AddInlineStyle(GetStyleData(self.style, self.file))

	def build_node(self, doc, n):
		doc.StartNode(n)
		doc.NodeHeading(n)
		doc.StartNodeBody(n)
		doc.NodeBody(n)
		for c in n.children:
			self.build_node(doc, c)
		doc.EndNodeBody(n)
		doc.EndNode(n)

	def build_nodes(self, doc):
		nodes = self.file.org
		for n in nodes.children:
			self.build_node(doc, n)

	def build_document(self, doc):
		doc.StartNodes()
		self.build_nodes(doc)
		doc.EndNodes()

	def build_body(self, doc):
		doc.StartDocument(self.file)
		self.build_document(doc)
		doc.EndDocument()
		doc.InsertScripts(self.file)

	def run(self,edit, onDone=None):
		self.file = db.Get().FindInfo(self.view)
		if(None == self.file):
			log.debug("Not an org file? Cannot build reveal document")
			evt.EmitIf(onDone)	
			return
		doc = None
		self.style = GetGlobalOption(self.file,"HTML_STYLE","HtmlStyle","blocky").lower()
		print("STYLE: " + self.style)
		try:
			doc = HtmlDoc(HtmlFilename(self.view), self.file)
			doc.style = self.style
			doc.StartHead()
			self.build_head(doc)
			doc.EndHead()

			doc.StartBody()
			self.build_body(doc)
			doc.EndBody()
		finally:	
			if(None != doc):
				doc.Close()
			evt.EmitIf(onDone)

def sync_up_on_closed():
	notice.Get().BuildToday()


class OrgDownloadHighlighJs(sublime_plugin.TextCommand):
	def run(self,edit):
		log.info("Trying to download highlightjs")
		import OrgExtended.orgutil.webpull as wp
		wp.download_highlightjs()

class OrgExportSubtreeAsOHtmlCommand(sublime_plugin.TextCommand):
	def onDone(self):
		# Remove this item from the DB!
		db.Get().Remove(self.tempView)
		self.tempView.set_scratch(True)
		self.view.window().focus_view(self.tempView)
		self.view.window().run_command("close_file")	
		self.tempView = None
		self.view.window().focus_view(self.view)
		sublime.set_timeout_async(lambda: sync_up_on_closed(), 1000)
		db.Get().RebuildDb()


	def run(self,edit):
		n = db.Get().AtInView(self.view)
		s = self.view.text_point(n.start_row,0)
		e = self.view.line(self.view.text_point(n.end_row,0)).end()
		r = sublime.Region(s,e)
		ct = self.view.substr(r)
		start = ""
		#if "#+TITLE:" not in ct:
		#	start = "#+TITLE: " + os.path.splitext(os.path.basename(self.view.file_name()))[0]
		tempFile = tf.CreateTempFileFromRegion(self.view, r, ".org", start)
		print("temp file: " + str(tempFile))
		self.tempView = self.view.window().open_file(tempFile)
		self.tempView.run_command('org_export_file_oHtml', {"onDone": evt.Make(self.onDone)})

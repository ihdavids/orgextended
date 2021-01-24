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
import yaml
import sys
import subprocess
import html

log = logging.getLogger(__name__)



def ReadTheOrgFilename(view):
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


def mapLanguage(lang):
	if(lang == 'html'):
		return 'language-html'
	elif(lang == 'python'):
		return 'language-python'
	else:
		return lang



class RevealDoc:
	def __init__(self, filename):
		self.fs = open(filename,"w")
		self.fs.write("<!doctype html>\n")
		self.fs.write("<html lang=\"en\" class>\n")
		self.commentName = None

	def AddJs(self,link):
		self.fs.write("    <script type=\"text/javascript\" src=\"" + link + "\"></script>\n")

	def AddStyle(self,link):
		self.fs.write("    <link rel=\"stylesheet\" href=\""+link+"\">\n")

	def StartHead(self):
		self.fs.write("  <head>\n")

	def EndHead(self):
		self.fs.write("  </head>\n")

	def StartPres(self, file):
		# This doesn't work have to do it as a parameter!
		transition      = GetGlobalOption(file,"REVEAL_TRANS","RevealTransition","none").lower()
		transitionSpeed = GetGlobalOption(file,"REVEAL_TRANS_SPEED","RevealTransitionSpeed","default").lower()
		self.fs.write("  <div class=\"reveal slide center has-vertical-slides has-horizontal-slides ready\" role=\"application\" data-transition-speed=\"{tspeed}\" data-background-transition=\"{transition}\">\n".format(
			transition=transition,
			tspeed=transitionSpeed))

	def EndPres(self):
		self.fs.write("  </div>\n")

	def StartSlides(self):
		self.fs.write("    <div class=\"slides\">\n")

	def EndSlides(self):
		self.fs.write("    </div>\n")

	# Per slide properties
	#:PROPERTIES:
	#:reveal_background: images/name-of-image
	#:reveal_background_size: width-of-image
	#:reveal_background_trans: slide
	#:END:
	def StartSlide(self,slide):
		# data-background-trans:        slide
		# data-background-image 		URL of the image to show. GIFs restart when the slide opens.
		# data-background-size 	        cover 	See background-size on MDN.
		# data-background-position 	    center 	See background-position on MDN.
		# data-background-repeat 	    no-repeat 	See background-repeat on MDN.
		# data-background-opacity
		# data-background-color	
		# data-background-video 		A single video source, or a comma separated list of video sources.
		# data-background-video-loop 	false 	Flags if the video should play repeatedly.
		# data-background-video-muted 	false 	Flags if the audio should be muted.
		properties = ""
		for prop in slide.properties:
			if prop in propMappings:
				properties = "{0} {1}=\"{2}\"".format(properties,propMappings[prop],slide.properties[prop])

		self.fs.write("      <section {0}>\n".format(properties))

	def EndSlide(self):
		self.fs.write("      </section>\n")

	def SlideHeading(self,slide):
		heading = html.escape(slide.heading)
		level = slide.level + 1
		self.fs.write("      <h{level}>{heading}</h{level}>\n".format(level=level,heading=heading))


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
		return line

	def SlideBody(self,slide):
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
					self.fs.write("    </code></pre>\n")
					continue
				else:
					if(not skipSrc):
						self.fs.write("     " + l + "\n")
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
				self.fs.write("    <pre><code language=\"{language}\" {attribs}>\n".format(language=mapLanguage(m.group('lang')),attribs=attribs))
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
					self.fs.write("     <ul>\n")
					inUl = True
				data = self.EscAndLinks(m.group('data'))
				self.fs.write("     <li>{content}</li>\n".format(content=data))
				continue
			elif(inUl):
				inUl = False
				self.fs.write("     </ul>\n")
			line = self.EscAndLinks(l)
			self.fs.write("     " + line + "\n")
		if(inUl):
			inUl = False
			self.fs.write("     </ul>\n")

		pass

	def StartBody(self):
		self.fs.write("  <body style=\"transition: -webkit-transform 0.8s ease 0s; transform-origin: 0px 0px;\">\n")

	def EndBody(self):
		self.fs.write("  </body>\n")

	def Progress(self):
		self.fs.write("  <div class=\"progress\" style=\"display: block;\">\n")
		self.fs.write("    <span style=\"width: 265px;\"></span>\n")
		self.fs.write("    ::after\n")
		self.fs.write("  </div>")

	def Dep(self, file, link, last=False):
		location = "https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/"
		location = GetGlobalOption(file,"REVEAL_LOCATION","RevealLocation",location)	
		location = location + "plugin/"
		comma =","
		if(last):
			comma = ""
		self.fs.write("              { src: '"+location+link+"', async: true }"+comma+"\n") 

	def RevealScript(self,file):
		location = "https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/"
		location = GetGlobalOption(file,"REVEAL_LOCATION","RevealLocation",location)	
		self.fs.write("  <script src=\"{location}js/reveal.js\"></script>\n".format(location=location))
		self.fs.write("  <script>\n")
		#self.fs.write("       Reveal.initialize();\n")
		self.fs.write("      Reveal.initialize({\n")
		self.fs.write("          hash: true,\n") # Allow browsing back to this slide.
		transition      = GetGlobalOption(file,"REVEAL_TRANS","RevealTransition","none").lower()
		transitionSpeed = GetGlobalOption(file,"REVEAL_TRANS_SPEED","RevealTransitionSpeed","default").lower()
		# Transition style
		self.fs.write("          transition: '{transition}',\n".format(transition=transition)) # none/fade/slide/convex/concave/zoom
		self.fs.write("          transitionSpeed: '{transitionSpeed}',\n".format(transitionSpeed=transitionSpeed)) # default/fast/slow
		#self.fs.write("          showNotes: false,\n")
		self.fs.write("          dependencies: [\n") 
		self.Dep(file, "markdown/marked.js")
		self.Dep(file, "markdown/markdown.js")
		self.Dep(file, "highlight/highlight.js")
		self.Dep(file, "search/search.js")
		self.Dep(file, "zoom-js/zoom.js")
		self.Dep(file, "notes/notes.js")
		#self.Dep("print-pdf/print-pdf.min.js")
		self.Dep(file, "math/math.js",True)
		self.fs.write("          ]\n") 
		self.fs.write("      });\n")
		self.fs.write("  </script>\n")


	def Close(self):
		self.fs.write("</html>\n")
		self.fs.close()


# Export the entire file using pandoc 
class OrgExportFileReadTheOrgCommand(sublime_plugin.TextCommand):

	def build_head(self, doc):
		# TODO: Make these configurable about where to pull reveal from.
		#doc.AddJs("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/plugin/markdown/markdown.min.js")
		#doc.AddJs("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/plugin/highlight/highlight.min.js")
		#doc.AddJs("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/plugin/search/search.min.js")
		#doc.AddJs("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/plugin/zoom-js/zoom.min.js")
		#doc.AddJs("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/plugin/notes/notes.min.js")
		#doc.AddJs("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/plugin/print-pdf/print-pdf.min.js")
		#doc.AddJs("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/plugin/math/math.min.js")
		#doc.AddJs("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/lib/js/head.min.js")
		#doc.AddJs("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/js/reveal.min.js")

		# TODO: Make these configurable about where to pull reveal from.
		#doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/css/print/pdf.min.css")
		doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/css/reveal.min.css")
		doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/css/reset.min.css")



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
		doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/css/theme/{theme}.min.css".format(theme=theme))
		doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/css/print/paper.min.css")


		highlight      = GetGlobalOption(self.file,"REVEAL_HIGHLIGHT","RevealHighlight","zenburn").lower()
		#doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/lib/css/monokai.min.css")
		#doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/lib/css/zenburn.min.css")
		doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/lib/css/{hl}.min.css".format(hl=highlight))
		#doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/lib/font/league-gothic/league-gothic.min.css")
		#doc.AddStyle("https://cdnjs.cloudflare.com/ajax/libs/reveal.js/3.8.0/lib/font/source-sans-pro/source-sans-pro.min.css")
		self.vlevel = int(GetGlobalOption(self.file,"REVEAL_VLEVEL","RevealVLevel",1))

	def build_slide(self, doc, slide):
		if(slide.num_children > 0 and self.vlevel == slide.level):
			doc.StartSlide(slide)
		doc.StartSlide(slide)
		doc.SlideHeading(slide)
		doc.SlideBody(slide)
		doc.EndSlide()
		for c in slide.children:
			self.build_slide(doc, c)
		if(slide.num_children > 0 and self.vlevel == slide.level):
			doc.EndSlide()

	def build_slides(self, doc):
		nodes = self.file.org
		for slide in nodes.children:
			self.build_slide(doc, slide)

	def build_pres(self, doc):
		doc.StartSlides()
		self.build_slides(doc)
		doc.EndSlides()

	def build_body(self, doc):
		doc.StartPres(self.file)
		self.build_pres(doc)
		doc.EndPres()
		doc.RevealScript(self.file)

	def run(self,edit):
		self.file = db.Get().FindInfo(self.view)
		if(None == self.file):
			log.debug("Not an org file? Cannot build reveal document")
			return
		doc = None
		try:
			doc = RevealDoc(RevealFilename(self.view))
			doc.StartHead()
			self.build_head(doc)
			doc.EndHead()

			doc.StartBody()
			self.build_body(doc)
			doc.EndBody()
		finally:	
			if(None != doc):
				doc.Close()

# pandoc -s -o output.html input.txt

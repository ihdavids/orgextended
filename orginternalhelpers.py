
import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
import fnmatch
import logging
import sys
import traceback
import yaml
import json
#from jsoncomment import JsonComment
import ast
import OrgExtended.orgxmlthemeparser as tp
import glob

varre = re.compile(r'var\((?P<name>[^)]+)\)')
colorre = re.compile(r'#(?P<r>[A-Fa-f0-9][A-Fa-f0-9])(?P<g>[A-Fa-f0-9][A-Fa-f0-9])(?P<b>[A-Fa-f0-9][A-Fa-f0-9])(?P<a>[A-Fa-f0-9][A-Fa-f0-9])?')

template = """
    - match: '{{{{beginsrc}}}}(({match})\s*)'
      captures:
        1: constant.other orgmode.fence.sourceblock
        2: orgmode.fence.sourceblock
        3: keyword orgmode.fence.language
        4: orgmode.fence.sourceblock
      embed: scope:{source}
      escape: '{{{{endsrc}}}}'
      embed_scope: markup.raw.block orgmode.raw.block
      escape_captures:
        1: constant.other orgmode.fence.sourceblock"""


introBlock = """
	// GENERATED: By OrgExtended
	//
	// The generator adds a subset of the orgmode specific scopes.
	// The scopes that it has added tend to play an important role
	// in making an orgmode buffer operational.
	//
	// That said, orgmode offers a wide variety of syntax elements for
	// you to style as needed. Please see blow for more information
	// on some of these scopes.
	//
	// The preamble scope is one of the more important scopes. In the
	// future I hope to produce some ligature fonts that will make the preamble
	// scope a thing of the past. For now, the preamble is the scope that hides
	// leading stars in your buffer. I find those visually disturbing and
	// appreciate working with them being invisible.
	//
	// The preamble used the pre-defined background color of your theme to
	// ensure the stars are invisible.
"""

# TODO Create blocks for each of the relevant blocks of markers
#      Create a set of useful markers with comments about how you can customize them
commentBlock = """
	// GENERATED: By Org Extended
	// 
	// The generator has added a bunch of useful extensions to the color scheme
	// That said there is much more than can be done by you to tweak your scheme
	// to your hearts content. The following comment block is here to give you
	// ideas of what is possible.
	//
	// On a windows box type Ctrl + Alt + Shift + P
	// to get a view of what scopes are in play on the thing you want to style
	// This table can help you tweak what you would like to see change
	//
	//	{
	//		"scope": "orgmode.break",
	//		"foreground": "#ed188a",
	//	},
	//	{
	//		"scope": "orgmode.page",
	//		"foreground": "#f5eebf",
	//	},
	//	{
	//		"scope": "orgmode.headline",
	//		"foreground": "#14adfa",
	//		"background": "#172822",
	//		"font_style": "bold italic",
	//	},
	//	{
	//		"scope": "orgmode.headline2",
	//		"background": "#172822",			
	//		"foreground": "#bb86fc",
	//		"font_style": "bold underline",
	//	},
	//	{
	//		"scope": "orgmode.headline3",
	//		"foreground": "#03dac5",
	//		"font_style": "bold",
	//	},
	//	{
	//		"scope": "orgmode.headline4",
	//		"foreground": "#dfe6a1",
	//		"font_style": "italic",
	//	},
	//	{
	//		"scope": "orgmode.headline5",
	//		"foreground": "#018786",
	//		"font_style": "italic",
	//	},
	//	{
	//		"scope": "orgmode.headline6",
	//		"foreground": "#afe3de",
	//		"font_style": "italic",
	//	},
	//	// Links can target these
	//	{
	//		"scope": "orgmode.target",
	//		"foreground": "#7c004a",
	//		"font_style": "italic",
	//	},
	//	// Links can target these
	//	{
	//		"scope": "orgmode.target.bracket",
	//		"foreground": "#7c004a",
	//		"font_style": "bold",
	//	},
	//	// [[LINK]] This is the entire link block
	//	{
	//		"scope": "orgmode.link",
	//		"foreground": "#3cd7fa",
	//		"font_style": "",
	//	},
	//	{
	//		"scope": "orgmode.link.href",
	//		"foreground": "#9999aa",
	//		"font_style": "italic",
	//	},
	//	{
	//		"scope": "orgmode.link.text",
	//		"foreground": "#4ce7fd",
	//		"font_style": "bold",
	//	},
	//  // Special coloring for email addresses
	//	{
	//		"scope": "orgmode.email",
	//		"foreground": "#a188b3",
	//		"font_style": "italic",
	//	},
	//	{
	//		"scope": "orgmode.deadline",
	//		"foreground": "#d1771d",
	//		"font_style": "italic",
	//	},
	//	{
	//		"scope": "orgmode.scheduled",
	//		"foreground": "#d1771d",
	//		"font_style": "italic",
	//	},
	//	// #+PRIORITIES: A B C
	//	{
	//		"scope": "orgmode.controltag",
	//		"foreground": "#aaaaaa",
	//	},
	//	// controltag.text also exists
	//	{
	//		"scope": "orgmode.controltag.tag",
	//		"foreground": "#aaaaaa",
	//		"font_style": "italic",
	//	},
	//	// < DATETIME >
	//	{
	//		"scope": "orgmode.datetime",
	//		"foreground": "#b0a497",
	//	},
	//	// [ DATETIME ]
	//	{
	//		"scope": "orgmode.unscheddatetime",
	//		"foreground": "#b0a497",
	//	},
	//	// CLOSED: SCHEDULED: DEADLINE:		
	//	{
	//		"scope": "orgmode.statekeyword",
	//		"foreground": "#d1771d",
	//		"font_style": "italic",
	//	},
	//	{
	//		"scope": "orgmode.checkbox",
	//		"foreground": "#c9be7b",
	//	},
	//	{
	//		"scope": "orgmode.checkbox.checked",
	//		"foreground": "#00FF00",
	//	},
	//	{
	//		"scope": "orgmode.checkbox.blocked",
	//		"foreground": "#FF0000",
	//	},
	//	{
	//		"scope": "orgmode.tags",
	//		"foreground": "#ded49b",
	//	},
	//	{
	//		"scope": "orgmode.tags.headline",
	//		"foreground": "#deff9b",
	//	},		
	//	{
	//		"scope": "orgmode.tack",
	//		"foreground": "#c993c4",
	//		"font_style": "bold",
	//	},
	//	{
	//		"scope": "orgmode.numberedlist",
	//		"foreground": "#c993c4",
	//		"font_style": "bold",
	//	},
	//	{
	//		"scope": "orgmode.definition",
	//		"foreground": "#A2E8E4",
	//		"font_style": "bold",
	//	},
	//	{
	//		"scope": "orgmode.definition.marker",
	//		"foreground": "#E1A2E8",
	//		"font_style": "bold",
	//	},
	//	{
	//		"scope": "orgmode.follow_up",
	//		"foreground": "#FF0000",
	//		"font_style": "bold",
	//	},
	//	{
	//		"scope": "orgmode.fence",
	//		"background": "#322830",
	//		"font_style": "bold",
	//	},
	//	{
	//		"scope": "orgmode.fence.language",
	//		"background": "#322830",
	//		"foreground": "#f1bff2",
	//		"font_style": "bold",
	//	},
	//	{
	//		"scope": "orgmode.raw.block",
	//		"background": "#252520",
	//		"font_style": "bold",
	//	},
	//	{
	//		"scope": "orgmode.table.block",
	//		"background": "#272828",
	//	},
	//	{
	//		"scope": "orgmode.bold",
	//		"foreground": "#aaffaa",
	//		"font_style": "bold",
	//	},
	//	{
	//		"scope": "orgmode.italics",
	//		"foreground": "#aaffff",
	//		"font_style": "italic",
	//	},
	//	{
	//		"scope": "orgmode.underline",
	//		"foreground": "#aaaaff",
	//		"font_style": "underline",
	//	},
	//	{
	//		"scope": "orgmode.strikethrough",
	//		"foreground": "#aaaaaa",
	//	},
	//	{
	//		"scope": "orgmode.code",
	//		"foreground": "#ffaaff",
	//	},
	//	{
	//		"scope": "orgmode.verbatim",
	//		"foreground": "#ffaaaa",
	//	},
"""


stateBlock = """
	// GENERATED: By OrgExtended
	//
	// States are the build in state flow. While org
	// allows you to define your own state flows
	// I do not yet have a good way of automatically
	// adding those to the syntax and color scheme.
	// (I hope to one day have a way to do that)
	//
	// For now the pre-defined state flows have automatic
	// highlighting and any new ones you define will have
	// the default. I can of course extend the syntax if desired.
"""

priorityBlock = """
	// GENERATED: By OrgExtended
	//
	// Much like states I do not have a way to extend the syntax with
	// new priorities at this time. I hope to devise a good scheme in
	// the future. 
	//
	// That said there is a default set of priorities A,B,C,D,E that
	// have automatic coloring. These are the color scheme elements that
	// add that coloring.
"""

fenceBlock = """
	// GENERATED: By OrgExtended
	//
	// Code blocks have a heading BEGIN_SRC and an ending END_SRC
	// I find it visually appealing to make these stand out.
	// You may have different preferences. NOTE: I use a luminance
	// shift expression to make the chosen color work with your color scheme.
"""

datePickerBlock = """
	// GENERATED: By OrgExtended
	// ====== DATE PICKER =====
	//
	// The date picker is the calendar view widget for selecting dates
	// this view has its own color scheme. The defaults are reasonable
	// with most color schemes. You may however want to tweak one of these.
	//
	//	{
	//		"scope": "orgdatepicker.weekendheader",
	//		"foreground": "#5b96f5",
	//		"font_style": "bold italic",
	//	},
	//	{
	//		"scope": "orgdatepicker.weekdayheader",
	//		"foreground": "#0762a3",
	//		"font_style": "bold italic",
	//	},
	//	{
	//		"scope": "orgdatepicker.monthheader",
	//		"foreground": "#7e4794",
	//		"font_style": "bold italic",
	//	},
	//	{
	//		"scope": "orgdatepicker.time",
	//		"foreground": "#aaaaaa",
	//		"font_style": "bold italic",
	//	},
"""

agendaIntroBlock = """
	// GENERATED: By OrgExtended
	// ====== AGENDA =====
	//
	// The agenda has a few unique requirements. It builds some of the blocky
	// diagrams using colors that have the same foreground as background.
	//
	// You can change these colors.
"""

agendaHabitBlock = """
	// GENERATED: By OrgExtended
	//
	// Habits are a means of tracking repeated tasks in orgmode. The
	// agena has limited support for habits. The display shows how often
	// you are achieving your habit.
"""

agendaWeekEmptyBlock = """
	// GENERATED: By OrgExtended
	// 
	// The weekly empty scope is how we fill the time blocks
	// that are empty in the weekly view. Usually I fill these with
	// grey blocks per hour. You may choose otherwise.
	// The foreground and background should be the same color
	// to avoid showing the control characters.
"""

agendaWeekColorsBlock = """
	// GENERATED: By OrgExtended
	// 
	// The week view uses these numeric week colors to randomly highlight
	// tasks to make them appear unique. You can change this pallete as desired.
"""

agendaDayColorBlocks = """
	// GENERATED: By OrgExtended
	// 
	// The day color blocks are used in the day view
	// to show how scheduled todos overlap. This is a range
	// of colors that show visually how todos fit into your day.
	// You can choose the color palette although it is best if
	// these colors have the same foreground and background color.
"""

agendaNowBlock = """
	// GENERATED: By OrgExtended
	//
	// orgagenda.now is the cursor. It is not used by the syntax
	// but rather to dynamically insert cursor markers in various
	// locations in the agenda. Color as you see fit.
"""


agendaScopesBlock = """
	// GENERATED: By OrgExtended
	// 
	// There are more colors you can override in the agenda:
	// 
	//	{
	//		"scope": "orgagenda.header",
	//		"foreground": "#5b96f5",
	//		"font_style": "bold italic",
	//	},
	//	{
	//		"scope": "orgagenda.dateheader",
	//		"foreground": "#5b96f5",
	//		"font_style": "bold italic underline",
	//	},
	//	{
	//		"scope": "orgagenda.weekendheader",
	//		"foreground": "#ab96f5",
	//		"font_style": "bold italic underline",
	//	},
	//	{
	//		"scope": "orgagenda.timeseparator",
	//		"foreground": "#7c7c7d",
	//	},
	//	{
	//		"scope": "orgagenda.now",
	//		"foreground": "#a88cd4",
	//		"font_style": "bold italic",
	//	},
	//	{
	//		"scope": "orgagenda.filename",
	//		"foreground": "#76b3ae",
	//	},
	//	{
	//		"scope": "orgagenda.todo",
	//		"foreground": "#a63229",
	//		"font_style": "bold italic",
	//	},
	//	{
	//		"scope": "orgagenda.doing",
	//		"foreground": "#d2a2e0",
	//		"font_style": "bold italic",
	//	},
	//	{
	//		"scope": "orgagenda.blocked",
	//		"foreground": "#FF0000",
	//		"font_style": "bold italic",
	//	},
	//	{
	//		"scope": "orgagenda.waiting",
	//		"foreground": "#ffff00",
	//		"font_style": "bold italic",
	//	},
	//	{
	//		"scope": "orgagenda.cancelled",
	//		"foreground": "#bab9b8",
	//		"font_style": "italic",
	//	},
	//	{
	//		"scope": "orgagenda.inprogress",
	//		"foreground": "#d2a2e0",
	//		"font_style": "bold italic",
	//	},
	//	{
	//		"scope": "orgagenda.next",
	//		"foreground": "#3fd9d7",
	//		"font_style": "bold italic",
	//	},
	//	{   // Hide the week markup in the buffer
	//		"scope": "orgagenda.week",
	//		"foreground": "var(bgcol)",
	//	},
	//	{
	//		"scope": "orgagenda.week.something",
	//		"foreground": "#ffffff",
	//		"background": "#007700",
	//	},
	//	{
	//		"scope": "orgagenda.week.today",
	//		"foreground": "#f89cf4",
	//		"font_style": "bold",
	//	},
	//	{
	//		"scope": "orgagenda.week.active",
	//		"foreground": "#f8fc00",
	//		"font_style": "bold",
	//	},
	//	{
	//		"scope": "orgagenda.week.activetoday",
	//		"foreground": "#f89cf4",
	//		"background": "#485c00",
	//		"font_style": "bold",
	//	},
	//	{
	//		"scope": "orgagenda.projecttitle",
	//		"foreground": "#a87932",
	//		"font_style": "bold italic",
	//	},
	//	{
	//		"scope": "orgagenda.blockseparator",
	//		"foreground": "#4a4a37",
	//		"font_style": "bold italic",
	//	},
	//	{
	//		"scope": "orgagenda.monthheader",
	//		"foreground": "#a87932",
	//		"font_style": "bold italic",
	//	},
"""

class OrgRegenSyntaxTemplateCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		templateFile = os.path.join(sublime.packages_path(),"OrgExtended","OrgExtended.sublime-syntax-template")
		outputFile = os.path.join(sublime.packages_path(),"OrgExtended","OrgExtended.sublime-syntax")
		languageList = os.path.join(sublime.packages_path(),"OrgExtended","languagelist.yaml")
		templates = ""
		with open(languageList) as file:
			documents = yaml.full_load(file)
			for item in documents:
				if 'text' in item:
					item['source'] = "text." + item['text']
				elif not 'source' in item:
					item['source'] = "source." + item['language']
				else:
					item['source'] = "source." + item['source']
				if not 'match' in item:
					item['match'] = item['language']
				templates += template.format(**item)
		templates += "\n"
		with open(templateFile) as tfile:
			with open(outputFile, 'w') as ofile:
				for line in tfile.readlines():
					if("{{INSERT_LANGUAGES_HERE}}" in line):
						ofile.write(templates)
					else:
						ofile.write(line)
			#print(templates)

def findscope(cs, name):
	if(name == None):
		return None
	for i in cs['rules']:
		if 'scope' in i and i['scope'] == name:
			return i
	return None

def replaceVar(cs,val):
	m = varre.match(val)
	while(m):
		name = m.group('name')
		data = cs['variables'][name]
		val = varre.sub(val,data)	
		m = varre.match(val)
	return val

def expandColor(cs, val):
	return replaceVar(cs,val)

def getBackground(cs, scope = None):
	i = findscope(cs, scope)
	if(i):
		if('background' in i):
			return expandColor(cs, i['background'])
	bg = cs['globals']['background']
	if(not bg):
		return expandColor(cs, "#ffffff")
	return expandColor(cs, bg)

class OrgCreateColorSchemeFromActiveCommand(sublime_plugin.TextCommand):

	def addstates(self, cs):
		cs['rules'].append({"COMMENT ORGMODE STATES COMMENT HERE":""})
		self.addscope(cs,"orgmode.state.todo",      "#e6ab4c")
		self.addscope(cs,"orgmode.state.blocked",   "#FF0000")
		self.addscope(cs,"orgmode.state.done",      "#47c94f")
		self.addscope(cs,"orgmode.state.cancelled", "#bab9b8")
		self.addscope(cs,"orgmode.state.meeting",   "#dec7fc")
		self.addscope(cs,"orgmode.state.phone",     "#77ebed")
		self.addscope(cs,"orgmode.state.note",      "#d2a2e0")
		self.addscope(cs,"orgmode.state.doing",     "#9c9c17")
		self.addscope(cs,"orgmode.state.inprogress","#9c9c17")
		self.addscope(cs,"orgmode.state.next",      "#37dae6")
		self.addscope(cs,"orgmode.state.reassigned","#bab9b8")

	def addpriorities(self, cs):
		cs['rules'].append({"COMMENT ORGMODE PRIORITIES COMMENT HERE":""})
		self.addscope(cs,"orgmode.priority","#c27532")
		self.addscope(cs,"orgmode.priority.value","#f5a55f")
		self.addscope(cs,"orgmode.priority.value.a","#e05a7b")
		self.addscope(cs,"orgmode.priority.value.b","#f59a76")
		self.addscope(cs,"orgmode.priority.value.c","#fab978")
		self.addscope(cs,"orgmode.priority.value.d","#f5d976")
		self.addscope(cs,"orgmode.priority.value.e","#bcbfae")
		self.addscope(cs,"orgmode.priority.value.general","#b59eb5")

	def addagenda(self,cs):
		cs['rules'].append({"COMMENT ORGMODE DAYBLOCKS HERE":""})
		self.addscope(cs,"orgagenda.block.1","#623456","#623456")
		self.addscope(cs,"orgagenda.block.2","#007777","#007777")
		self.addscope(cs,"orgagenda.block.3","#999900","#999900")
		self.addscope(cs,"orgagenda.block.4","#007700","#007700")
		self.addscope(cs,"orgagenda.block.5","#aa5522","#aa5522")
		self.addscope(cs,"orgagenda.block.6","#f89cf4","#f89cf4")
		self.addscope(cs,"orgagenda.block.7","#0000ee","#0000ee")
		
		cs['rules'].append({"COMMENT ORGMODE HABITS HERE":""})
		self.addscope(cs,"orgagenda.habit.didit","#ffffff","#007700")
		self.addscope(cs,"orgagenda.habit.scheduled","#333300","#550000")
		self.addscope(cs,"orgagenda.habit.nothing","#000066","#000066")

		bg = getBackground(cs)
		weekEmpty = "color(" + bg + " l(+ 5%))"
		cs['rules'].append({"COMMENT ORGMODE WEEKEMPTY HERE":""})
		self.addscope(cs,"orgagenda.week.empty", weekEmpty, weekEmpty)	

		cs['rules'].append({"COMMENT ORGMODE AGENDA WEEKCOLORS HERE":""})
		self.addscope(cs,"orgagenda.week.done.0","#4f4f4f")
		self.addscope(cs,"orgagenda.week.done.1","#666666")
		self.addscope(cs,"orgagenda.week.0","#550000")
		self.addscope(cs,"orgagenda.week.1","#007700")
		self.addscope(cs,"orgagenda.week.2","#770077")
		self.addscope(cs,"orgagenda.week.3","#0000ff")
		self.addscope(cs,"orgagenda.week.4","#999900")
		self.addscope(cs,"orgagenda.week.5","#007777")
		self.addscope(cs,"orgagenda.week.6","#aa5522")
		self.addscope(cs,"orgagenda.week.7","#cc99cc")
		self.addscope(cs,"orgagenda.week.8","#225522")
		self.addscope(cs,"orgagenda.week.9","#623456")


		self.addscope(cs,"orgmode.deadline.warning","#999900",bg)
		self.addscope(cs,"orgmode.deadline.overdue","#880088",bg)
		self.addscope(cs,"orgmode.deadline.due","#007700",bg)

		now = "#aaaa00"
		if('find_highlight' in cs['globals']):
			now = cs['globals']['find_highlight']
		cs['rules'].append({"COMMENT ORGMODE AGENDA NOW HERE":""})
		self.addscope(cs,"orgagenda.now",now)

		cs['rules'].append({"COMMENT ORGMODE AGENDA SCOPES HERE":""})

	def addfences(self, cs):
		cs['rules'].append({"COMMENT ORGMODE FENCE COMMENT HERE":""})
		bg = getBackground(cs, 'markup.raw.block')
		bg = "color(" + bg + " l(+ 6%))"
		self.addscope(cs,"orgmode.fence",None, bg,"bold")

	def addscope(self, cs, name, fg, bg=None, style=None):
		if(not findscope(cs, name)):
			scope = {"scope": name}
			if(fg):
				scope['foreground'] = fg
			if(bg):
				scope['background'] = bg
			if(style):
				scope['font_style'] = style
			cs['rules'].append(scope)	

	def addpreamble(self, cs):
		if(not findscope(cs, 'orgmode.preamble')):
			bg = cs['globals']['background']
			cs['rules'].append({"scope": "orgmode.preamble","foreground": bg, "background": bg})	

	def run(self, edit):
		self.settings = sublime.load_settings('Preferences.sublime-settings')
		self.origColorScheme = self.settings.get("color_scheme",None)
		if(self.origColorScheme):
			self.colorSchemeData = sublime.load_resource(self.origColorScheme)
			cs = None
			if(".tmTheme" in self.origColorScheme):
				try:
					p = tp.XMLThemeParser(self.colorSchemeData)
					cs = p.cs
				except:
					print("Failed to parse tmTheme file: \n" + traceback.format_exc())
			else:
				cs = ast.literal_eval(self.colorSchemeData)
			if(not cs):
				print("FAILED TO GENERATE NEW COLOR SCHEME COULD NOT PARSE SCHEME")
				return
			path = os.path.join(sublime.packages_path(),"User","OrgColorSchemes")
			if(not os.path.exists(path)):
				os.mkdir(path)

			cs['rules'].append({"COMMENT ORGMODE INTRO HERE":""})

			self.addpreamble(cs)
			self.addstates(cs)
			self.addfences(cs)
			self.addpriorities(cs)


			scheme = os.path.basename(self.origColorScheme)
			scheme = os.path.splitext(scheme)[0]
			schemeName = scheme + "_Org.sublime-color-scheme"
			outputFile = os.path.join(path, schemeName)
			# ===========================================================
			cs['rules'].append({"COMMENT ORGMODE SCOPES HERE":""})
			# ===========================================================
			cs['rules'].append({"COMMENT ORGMODE DATEPICKER SCOPES HERE":""})
			# ===========================================================
			cs['rules'].append({"COMMENT ORGMODE AGENDA INTRO HERE":""})
			
			self.addagenda(cs)

			jsonStr = json.dumps(cs, sort_keys=True, indent=4)


			jsonStr = jsonStr.replace('"COMMENT ORGMODE SCOPES HERE": ""',commentBlock)
			jsonStr = jsonStr.replace('"COMMENT ORGMODE INTRO HERE": ""',introBlock)
			jsonStr = jsonStr.replace('"COMMENT ORGMODE FENCE COMMENT HERE": ""',fenceBlock)
			jsonStr = jsonStr.replace('"COMMENT ORGMODE PRIORITIES COMMENT HERE": ""',priorityBlock)
			jsonStr = jsonStr.replace('"COMMENT ORGMODE STATES COMMENT HERE": ""',stateBlock)
			jsonStr = jsonStr.replace('"COMMENT ORGMODE DATEPICKER SCOPES HERE": ""',datePickerBlock)
			jsonStr = jsonStr.replace('"COMMENT ORGMODE AGENDA INTRO HERE": ""',agendaIntroBlock)
			jsonStr = jsonStr.replace('"COMMENT ORGMODE WEEKEMPTY HERE": ""',agendaWeekEmptyBlock)
			jsonStr = jsonStr.replace('"COMMENT ORGMODE DAYBLOCKS HERE": ""',agendaDayColorBlocks)
			jsonStr = jsonStr.replace('"COMMENT ORGMODE HABITS HERE": ""',agendaHabitBlock)
			jsonStr = jsonStr.replace('"COMMENT ORGMODE AGENDA WEEKCOLORS HERE": ""',agendaWeekColorsBlock)
			jsonStr = jsonStr.replace('"COMMENT ORGMODE AGENDA SCOPES HERE": ""',agendaScopesBlock)
			jsonStr = jsonStr.replace('"COMMENT ORGMODE AGENDA NOW HERE": ""',agendaNowBlock)
			
			with open(outputFile,'w') as ofile:
				ofile.write(jsonStr)
				ofile.flush()
			newColorScheme = "Packages/User/OrgColorSchemes/" + schemeName
			print("CHANGING ORIGINAL COLOR SCHEME: " + self.origColorScheme)
			print("TO COLOR SCHEME: " + newColorScheme)
			# We need some time for that file to hit the disk before we try to
			# load from them. Sublime is fast so give us a little time here.
			sublime.set_timeout(self.setColorSchemes(newColorScheme), 1000)
			

	def setColorSchemes(self, newColorScheme):
		self.mysettings = sublime.load_settings('OrgExtended.sublime-settings')
		self.mysettings.set("color_scheme", newColorScheme)
		sublime.save_settings('OrgExtended.sublime-settings')
		self.mysettings = sublime.load_settings('orgdatepicker.sublime-settings')
		self.mysettings.set("color_scheme", newColorScheme)
		sublime.save_settings('orgdatepicker.sublime-settings')
		self.mysettings = sublime.load_settings('orgagenda.sublime-settings')
		self.mysettings.set("color_scheme", newColorScheme)
		sublime.save_settings('orgagenda.sublime-settings')


class OrgSelectExistingColorSchemeCommand(sublime_plugin.TextCommand):
	def on_done_st4(self, index, modifiers):
		self.on_done(index)
	def on_done(self, index):
		if(index < 0):
			return
		newColorScheme = self.files[index]
		self.mysettings = sublime.load_settings('OrgExtended.sublime-settings')
		self.mysettings.set("color_scheme", newColorScheme)
		sublime.save_settings('OrgExtended.sublime-settings')
		self.mysettings = sublime.load_settings('orgdatepicker.sublime-settings')
		self.mysettings.set("color_scheme", newColorScheme)
		sublime.save_settings('orgdatepicker.sublime-settings')
		self.mysettings = sublime.load_settings('orgagenda.sublime-settings')
		self.mysettings.set("color_scheme", newColorScheme)
		sublime.save_settings('orgagenda.sublime-settings')
	def run(self, edit):
		path = os.path.join(sublime.packages_path(),"User","OrgColorSchemes")
		self.files = glob.glob(os.path.join(path,"*.sublime-color-scheme"))
		temp = []
		for file in self.files:
			file = file.replace(sublime.packages_path(),"")
			file = "Packages" + file.replace("\\","/")
			temp.append(file)
		self.files = temp
		self.files.append("Packages/OrgExtended/OrgExtended.sublime-color-scheme")
		self.files.append("Packages/OrgExtended/OrgExtended-Light.sublime-color-scheme")
		if(int(sublime.version()) >= 4096):
			self.view.window().show_quick_panel(self.files, self.on_done_st4, -1, -1)
		else:
			self.view.window().show_quick_panel(self.files, self.on_done, -1, -1)


class OrgCreateKeymapDocCommand(sublime_plugin.TextCommand):
	def run(self, edit):
		commandsData = sublime.load_resource("Packages/OrgExtended/OrgExtended.sublime-commands")
		commandsData = re.sub(r"//.*\n","\n",commandsData)
		com = ast.literal_eval(commandsData)

		keymapData = sublime.load_resource("Packages/OrgExtended/Default.sublime-keymap")
		keymapData = re.sub(r"//.*\n","",keymapData)
		keymapData = re.sub(r"\n\s*\n","\n",keymapData)
		keymapData = re.sub(r"\r\s*\r","",keymapData)
		keys = json.loads(keymapData)
		coms = {}
		for c in com:
			cmd = c['command']
			cap = c['caption']
			coms[cmd] = {'cap': cap}

		for k in keys:
			kks  = k['keys']	
			cmd  = k['command']
			cntx = "everywhere"
			vi   = False
			if('context' in k):
				for i in k['context']:
					if('key' in i and 'vi_command_mode_aware' == i['key']):
						vi = True
					if('operand' in i):
						if(isinstance(i['operand'],str)):
							cntx = i['operand']
			if(cmd in coms):
				if(not 'keys' in coms[cmd]):
					coms[cmd]['keys'] = {}
				if(vi):
					coms[cmd]['keys']['vi'] = kks
				else:
					coms[cmd]['keys']['norm'] = kks
				coms[cmd]['cntx'] = cntx
				coms[cmd]['vi']   = vi
			else:
				if(vi):
					coms[cmd] = {'keys': {'vi': kks}, 'cntx': cntx}
				else:
					coms[cmd] = {'keys': {'norm': kks}, 'cntx': cntx}
		out = ""
		contexts = {"Date Picker": "orgdateeditor", "Org File":"orgmode", "Org Agenda":"orgagenda", "Unbound":"","Everywhere":"everywhere", "Quick Input": "orginput" }
		for name,con in contexts.items():
			out += "* " + name + "\n"
			out += " |Normal Keys| Vim Keys | Command|Operation| \n"
			out +="|-\n"
			for k,i in coms.items():
				if(not k.startswith("org_")):
					continue
				if(('cntx' in i and con != "" and con in i['cntx']) or ('cntx' not in i and con == "")): 
					if('keys' in i):
						if('norm' in i['keys']):
							out += "|" + str(i['keys']['norm']).replace('[','').replace(']','').replace("'",'')
						else:
							out += "|"
						if('vi' in i['keys']):
							out += "|" + str(i['keys']['vi']).replace('[','').replace(']','').replace("' '","<space>").replace("'",'')
						else:
							out += "|"
					else:
						out += "||"
					if('cap' in i):
						out += "|" + i['cap']
					else:
						out += "|"
					out += "|" + k + "|\n"
			out += "\n\n"
		self.view.insert(edit,0,out)

		pass






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


# TODO Create blocks for each of the relevant blocks of markers
#      Create a set of useful markers with comments about how you can customize them
commentBlock = """
    // This is a comment block and should be ignored
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
    				item['source'] = "text." + item['language']
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
		if i['scope'] == name:
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
		self.addscope(cs,"orgmode.priority","#c27532")
		self.addscope(cs,"orgmode.priority.value","#f5a55f")
		self.addscope(cs,"orgmode.priority.value.a","#e05a7b")
		self.addscope(cs,"orgmode.priority.value.b","#f59a76")
		self.addscope(cs,"orgmode.priority.value.c","#fab978")
		self.addscope(cs,"orgmode.priority.value.d","#f5d976")
		self.addscope(cs,"orgmode.priority.value.e","#bcbfae")
		self.addscope(cs,"orgmode.priority.value.general","#b59eb5")

	def addfences(self, cs):
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
			cs = ast.literal_eval(self.colorSchemeData)
			self.addpreamble(cs)
			self.addstates(cs)
			self.addfences(cs)
			self.addpriorities(cs)

			path = os.path.join(sublime.packages_path(),"User","OrgColorSchemes")
			if(not os.path.exists(path)):
				os.mkdir(path)

			scheme = os.path.basename(self.origColorScheme)
			scheme = os.path.splitext(scheme)[0]
			schemeName = scheme + "_Org.sublime-color-scheme"
			outputFile = os.path.join(path, schemeName)
			cs['rules'].append({"THIS SHOULD BE REPLACED":""})
			jsonStr = json.dumps(cs, sort_keys=True, indent=4)
			jsonStr = jsonStr.replace('"THIS SHOULD BE REPLACED": ""',commentBlock)
			with open(outputFile,'w') as ofile:
				ofile.write(jsonStr)
			newColorScheme = "Packages/User/OrgColorSchemes/" + schemeName
			print("CHANGING ORIGINAL COLOR SCHEME: " + self.origColorScheme)
			print("TO COLOR SCHEME: " + self.origColorScheme)
			self.mysettings = sublime.load_settings('OrgExtended.sublime-settings')
			self.mysettings.set("color_scheme", newColorScheme)




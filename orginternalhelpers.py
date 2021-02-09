
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


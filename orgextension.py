# LOADING Extension modules.
# Dynamic Blocks, Links and the Agenda plan to use this mechanism.
# My extensions can live in subfolder and are loaded dynamically
# YOUR Extensions can live in User and be loaded dynamically.


import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
import fnmatch
import logging
import sys
import OrgExtended.asettings as sets
import importlib

log = logging.getLogger(__name__)


def load_module(basemodule, folder, filename):
	if sys.version_info[0] < 3:
		module_path = folder + '.' + filename.split('.')[0]
		name = filename.split('.')[0]
		module = __import__(module_path, globals(), locals(), name)
		module = reload(module)
	else:
		module_path = basemodule + '.'+ folder +'.' + filename.split('.')[0]
		for m in sys.modules:
			if(module_path in m):
				print("KEY: " + str(m))
		if module_path in sys.modules:
			del sys.modules[module_path]
		module = importlib.import_module(module_path)
	return module

def find_extension_modules(folder):
	importlib.invalidate_caches()
	base = os.path.dirname(os.path.abspath(__file__))
	path = base + '/' + folder
	moduleTable = {}
	# Built in extensions
	for root, dirnames, filenames in os.walk(path):
		for filename in fnmatch.filter(filenames, '*.py'):
			if '__init__' in filename or 'abstract' in filename:
				continue
			module = load_module("OrgExtended", folder, filename)
			moduleTable[filename.split('.')[0]] = module
	# User generated extensions
	path = base + '/../User/' + folder
	for root, dirnames, filenames in os.walk(path):
		for filename in fnmatch.filter(filenames, '*.py'):
			if '__init__' in filename or 'abstract' in filename:
				continue
			module = load_module("OrgExtended", folder, filename)
			moduleTable[filename.split('.')[0]] = module
	return moduleTable



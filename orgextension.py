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

lastModCache = {}

def load_module(basemodule, folder, filename,force = False):
	if sys.version_info[0] < 3:
		module_path = folder + '.' + filename.split('.')[0]
		name = filename.split('.')[0]
		module = __import__(module_path, globals(), locals(), name)
		module = reload(module)
	else:
		module_path = basemodule + '.'+ folder +'.' + filename.split('.')[0]
		#for m in sys.modules:
		#	if(module_path in m):
		#		print("KEY: " + str(m))
		if force and module_path in sys.modules:
			del sys.modules[module_path]
		module = importlib.import_module(module_path)
	return module

def GetUserFolder():
	base = sublime.packages_path()
	#base = os.path.dirname(os.path.abspath(__file__))
	return os.path.join(base,'User')


def find_extension_modules(folder, builtins):
	importlib.invalidate_caches()
	#base = os.path.dirname(os.path.abspath(__file__))
	base = sublime.packages_path()
	path = base + '/' + folder
	moduleTable = {}
	# Built in extensions
	#for root, dirnames, filenames in os.walk(path):
	#	for filename in fnmatch.filter(filenames, '*.py'):
	#		if '__init__' in filename or 'abstract' in filename:
	#			continue
	for filename in builtins:
		filename = filename + ".py"
		force = sets.Get("forceLoadInternalExtensions",False)
		module = load_module("OrgExtended", folder, filename, force)
		moduleTable[filename.split('.')[0]] = module
	# User generated extensions
	path = os.path.join(base,'User',folder)
	for root, dirnames, filenames in os.walk(path):
		for filename in fnmatch.filter(filenames, '*.py'):
			if '__init__' in filename or 'abstract' in filename:
				continue
			# Only reload if the file is newer.
			# NOTE: Due to how import works, it will not
			#       reload the file until sublime reloads
			#       so we have to track that ourselves
			#       in the loadModCache.
			fullfilename = os.path.join(path,filename)
			lastMod = os.path.getmtime(fullfilename)
			force = fullfilename not in lastModCache or lastMod > lastModCache[fullfilename] or sets.Get("forceLoadExternalExtensions",False)
			lastModCache[fullfilename] = lastMod
			module = load_module("User", folder, filename, force)
			moduleTable[filename.split('.')[0]] = module
	return moduleTable


def find_extension_file(folder,name,extension='.py'):
	base = os.path.dirname(os.path.abspath(__file__))
	# User generated extensions
	path = base + '/../User/' + folder
	fname = name + extension
	for root, dirnames, filenames in os.walk(path):
		for filename in fnmatch.filter(filenames, fname):
			return "Packages/User/" + folder + "/" + filename
	# Built in extensions
	path = base + '/' + folder
	for root, dirnames, filenames in os.walk(path):
		for filename in fnmatch.filter(filenames, fname):
			return "Packages/OrgExtended/" + folder + "/" + filename
	return None

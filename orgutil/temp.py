import sublime
import sublime_plugin
import re
from pathlib import Path
import os
import fnmatch
import logging
import sys
import traceback 
import tempfile
from shutil import copyfile

log = logging.getLogger(__name__)

def CreateTempFile(source, suffix=".temp",start=None, end=None):
	filename = None
	tmp = tempfile.NamedTemporaryFile(delete=False,suffix=suffix)
	try:
		if(start):
			tmp.write((start + "\n").encode("utf-8"))
		tmp.write(source.encode('utf-8'))
		if(end):
			tmp.write(("\n" + end).encode("utf-8"))
		filename = tmp.name
		tmp.close()	
	except:
		res = traceback.format_exc()
		log.debug("Failed to create temp file: " + str(tmp.name) + "\n" + str(res))
		pass
	return filename

def CreateTempFileFromRegion(view, region,suffix=".temp",start=None, end=None):
	content = view.substr(region)
	return CreateTempFile(content,suffix,start,end)

def GetViewFileAs(view,extension):
	sourcepath = os.path.dirname(view.file_name())
	return os.path.join(sourcepath,os.path.splitext(os.path.basename(view.file_name()))[0] + extension)

def CopyTempToViewDir(view,tempfile,asfile):
	sourcepath = os.path.dirname(view.file_name())
	destFile   = os.path.join(sourcepath,asfile)
	copyfile(tempfile, destFile)
	return destFile

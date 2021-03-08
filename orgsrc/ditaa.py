


import sublime
import sublime_plugin
import sys
import io
import re
import logging
import subprocess, os
import threading, time, signal
from shutil import copyfile
import OrgExtended.asettings as sets

# Python Babel Mode
def Extension(cmd):
	return ".ditaa"

# Actually do the work, return an array of output.
def Execute(cmd):
	jarfile = sets.Get("ditaa",None)
	if(jarfile == None):
		print("ERROR: cannot find ditaa jar file. Please setup the ditaa key in your settings file")
		return ["ERROR - missing ditaa.jar file"]
	output = "diagram.png"
	if(cmd.params and "file" in cmd.params):
		output = cmd.params["file"]
	outpath     = os.path.dirname(cmd.filename)
	sourcepath = os.path.dirname(cmd.sourcefile)
	#commandLine = [r"java", "-jar", jarfile, mypath, "-o", output]
	commandLine = [r"java", "-jar", jarfile, cmd.filename, "-o"]
	print(str(commandLine))
	#commandLine = [r"java", "-jar", jarfile, "-help"]
	try:
		startupinfo = subprocess.STARTUPINFO()
		startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
	except:
		startupinfo = None
	# cwd=working_dir, env=my_env,
	os.makedirs(outpath, exist_ok=True)
	cwd = os.path.join(sublime.packages_path(),"User") 
	popen = subprocess.Popen(commandLine, universal_newlines=True, cwd=cwd, startupinfo=startupinfo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

	#popen.wait()
	(o,e) = popen.communicate()
	
	convertFile = os.path.join(outpath,os.path.splitext(os.path.basename(cmd.filename))[0] + ".png")
	destFile    = os.path.join(sourcepath,output)
	copyfile(convertFile, destFile)
	#print(str(os.path.basename(cmd.sourcefile)))
	#print(str(os.path.splitext(cmd.filename)))
	#print(str(os.path.splitext(cmd.sourcefile)))
	destFile = os.path.relpath(destFile, sourcepath)
	out = o
	o = "[[file:" + destFile + "]]"
	if("error" in out or "failed" in out or "Failed" in out or "Error" in out or "not" in out):
		o = o +out
	return o.split('\n') + e.split('\n')


# Run after results are in the buffer. We can do whatever
# Is needed to the buffer post execute here.
def PostExecute(cmd):
	pass

# Create one of these and return true if we should show images after a execution.
def GeneratesImages(cmd):
	return True
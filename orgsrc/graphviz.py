
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
import platform

# Python Babel Mode
def Extension(cmd):
	return ".dot"

# Actually do the work, return an array of output.
def Execute(cmd,sets):
	exe = sets.Get("graphviz",None)
	if(exe == None):
		print("ERROR: cannot find graphviz executable file. Please setup the graphviz key in your settings file")
		return ["ERROR - missing graphviz executable file"]
	output = "diagram"
	format = cmd.params.Get('fmt',"png")
	engine = cmd.params.Get('engine',"default")
	output = output + "." + format
	cmd.output = cmd.params.Get('file',output)

	if(engine != "default"):
		if(platform.system() == "Windows"):
			if(not engine.endswith(".exe")):
				engine = engine + ".exe"
		exe = os.path.join(os.path.dirname(exe),engine)
	outpath     = os.path.dirname(cmd.filename)
	sourcepath = os.path.dirname(cmd.sourcefile)
	destFile    = os.path.join(sourcepath,cmd.output)
	commandLine = [exe, "-T" + format, cmd.filename, "-o", destFile]
	#print(str(commandLine))
	#commandLine = [r"java", "-jar", jarfile, "-help"]
	try:
		startupinfo = subprocess.STARTUPINFO()
		startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
	except:
		startupinfo = None
	# cwd=working_dir, env=my_env,
	os.makedirs(os.path.dirname(destFile), exist_ok=True)
	cwd = os.path.join(sublime.packages_path(),"User") 
	popen = subprocess.Popen(commandLine, universal_newlines=True, cwd=cwd, startupinfo=startupinfo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

	#popen.wait()
	(o,e) = popen.communicate()
	
	#convertFile = os.path.join(outpath,os.path.splitext(os.path.basename(cmd.filename))[0] + ".png")
	#copyfile(convertFile, destFile)
	#print(str(os.path.basename(cmd.sourcefile)))
	#print(str(os.path.splitext(cmd.filename)))
	#print(str(os.path.splitext(cmd.sourcefile)))
	#destFile = os.path.relpath(destFile, sourcepath)
	#o = "[[file:" + destFile + "]]" + o
	return o.split('\n') + e.split('\n')


# Run after results are in the buffer. We can do whatever
# Is needed to the buffer post execute here.
def PostExecute(cmd):
	pass

# Create one of these and return true if we should show images after a execution.
def GeneratesImages(cmd):
	return True

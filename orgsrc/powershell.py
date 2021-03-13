import sublime
import sublime_plugin
import sys
import io
import re
import logging
import subprocess, os
import threading, time, signal

# Python Babel Mode
def Extension(cmd):
	return ".ps1"

# Actually do the work, return an array of output.
def Execute(cmd,sets):
	commandLine = [r"C:\\Windows\\SysWOW64\\WindowsPowerShell\\v1.0\\powershell.exe", "-ExecutionPolicy", "Unrestricted", cmd.filename]
	try:
		startupinfo = subprocess.STARTUPINFO()
		startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
	except:
		startupinfo = None
	# cwd=working_dir, env=my_env,
	cwd = os.path.join(sublime.packages_path(),"User") 
	popen = subprocess.Popen(commandLine, universal_newlines=True, cwd=cwd, startupinfo=startupinfo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	#popen.wait()
	(o,e) = popen.communicate()
	return o.split('\n') + e.split('\n')


# Run after results are in the buffer. We can do whatever
# Is needed to the buffer post execute here.
def PostExecute(cmd):
	pass

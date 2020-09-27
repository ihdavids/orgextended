# Download highlight js IF we need it!
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
import OrgExtended.orgextension as ext
import yaml
import sys
import subprocess
import html

log = logging.getLogger(__name__)

def ensure_dir(file_path):
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)

def download_highlightjs():
	users = os.path.join(ext.GetUserFolder(),"highlightjs")
	if(os.path.exists(users)):
		log.error('highlightjs folder exists not downloading')
		return
	import requests
	# We have to get the csrf token out of the document
	# <input type="hidden" name="csrfmiddlewaretoken" value="kn9otxuIzP289hae1RbmrU9fbWoMBgqpWEwctR7pAZL2tq5q6uZKyOmufJ1SWrtA">	
	r = requests.get('https://highlightjs.org/download')
	matcher = re.compile('^[ 	]*<input[ ]+type=\"hidden\"[ ]+name=\"csrfmiddlewaretoken\"[ ]+value=\"([^\"]+)\"')
	cookie = r.headers['Set-Cookie']
	#csrftoken=mm0TFIj3kVfXGORUqThNU1XTocsCPeEPYDnHF2WKl5YR0XM6vw5b1Va8sZ5IapH0
	cookie = cookie[0:cookie.find(';')]
	#print("COOKIE: " + cookie[0:cookie.find(';')])
	#print(r.headers)
	csrftoken = ""
	for l in r.text.split('\n'):
		m = matcher.match(l)
		if(m):
			csrftoken = str(m.groups(1)[0])
	#print("Token: " + csrftoken)
	payload = {
	'csrfmiddlewaretoken': csrftoken,
	'properties.js': 'on',
	'apache.js': 'on',
	'bash.js': 'on',
	'c.js': 'on',
	'csharp.js': 'on',
	'cpp.js': 'on',
	'c-like.js': 'on',
	'css.js': 'on',
	'coffeescript.js': 'on',
	'diff.js': 'on',
	'go.js': 'on',
	'xml.js': 'on',
	'http.js': 'on',
	'json.js': 'on',
	'java.js': 'on',
	'javascript.js': 'on',
	'kotlin.js': 'on',
	'less.js': 'on',
	'lua.js': 'on',
	'makefile.js': 'on',
	'markdown.js': 'on',
	'nginx.js': 'on',
	'objectivec.js': 'on',
	'php.js': 'on',
	'php-template.js': 'on',
	'perl.js': 'on',
	'plaintext.js': 'on',
	'python.js': 'on',
	'python-repl.js': 'on',
	'ruby.js': 'on',
	'rust.js': 'on',
	'scss.js': 'on',
	'sql.js': 'on',
	'shell.js': 'on',
	'swift.js': 'on',
	'ini.js': 'on',
	'typescript.js': 'on',
	'yaml.js': 'on',
	'cmake.js': 'on',
	'lisp.js': 'on',
	'powershell.js': 'on'
	}
	r = requests.post('https://highlightjs.org/download/',data = payload, headers = {'cookie': cookie, 'Referer': 'https://highlightjs.org/download', 'content-type': 'application/x-www-form-urlencoded'})
	if(not 'Content-Type' in r.headers or r.headers['Content-Type'] != 'application/zip'):
		log.error("Cannot finish highligh js download, download was not a zip file")
		log.error(str(r.headers))
		return
	import zipfile
	import io
	os.mkdir(users)	
	othersep = '/'
	if(os.sep == othersep):
		othersep = '\\'
	z = zipfile.ZipFile(io.BytesIO(r.content))
	for info in z.infolist():
		data = z.read(info.filename)   # Reads the data from the file
		fname = info.filename.replace(othersep, os.sep)
		filename = os.path.join(users, fname)
		ensure_dir(filename)
		file = open(filename, "wb")
		file.write(data)
		file.close()	
	z.close() 
	log.debug("Zip file unzipped")

import sublime
import sublime_plugin
import datetime
import os
import logging

log = logging.getLogger(__name__)

defaultTodoStates = ["TODO(!)", "NEXT", "BLOCKED","WAITING","|", "CANCELLED", "DONE","MEETING","PHONE","NOTE"]

class ASettings:
	def __init__(self, settingsName):
		self.settings = sublime.load_settings(settingsName + '.sublime-settings')

	def Get(self, name, defaultVal):
		val = self.settings.get(name)
		if(val == None):
			val = defaultVal
		return val


configFilename    = "orgextended"

def setup_user_settings():
	filename = configFilename + ".sublime-settings"
	user_settings_path = os.path.join(
		sublime.packages_path(),
		"User",
		filename)

	if not os.path.exists(user_settings_path):
		default_settings_path = os.path.join(
			sublime.packages_path(),
			"OrgExtended",
			filename)
		shutil.copyfile(default_settings_path, user_settings_path)

# Singleton access
_sets = None

def Load():
	global configFilename
	global _sets
	_sets          = ASettings(configFilename)

def Get(name, defaultValue):
	global _sets
	if(_sets == None):
		log.warning("SETTINGS IS NULL? IS THIS BEING CALLED BEFORE PLUGIN START?")
		Load()
	return _sets.Get(name, defaultValue)

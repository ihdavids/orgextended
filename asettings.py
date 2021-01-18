import sublime
import sublime_plugin
import datetime
import os
import logging
import shutil
import OrgExtended.orgutil.template as temp


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

def setup_mousemap():
	filename = "Default.sublime-mousemap"
	user_settings_path = os.path.join(
		sublime.packages_path(),
		"User",
		filename)
	mousemap = """
[
    {
        "button": "button1", 
        "count": 1, 
        "modifiers": ["alt"],
        "press_command": "drag_select",
        // In the future we may vector this to a more generic handler
        "command": "org_mouse_handler",
    }
]
	"""	
	if not os.path.exists(user_settings_path):
		with open(user_settings_path,"w") as o:
			o.write(mousemap)
			o.write("\n")

class OrgSetupMouseMapCommand(sublime_plugin.TextCommand):
    def run(self, edit, event=None):
    	setup_mousemap()


# Singleton access
_sets = None

def Load():
	global configFilename
	global _sets
	_sets          = ASettings(configFilename)

def Get(name, defaultValue, formatDictionary = None):
	global _sets
	if(_sets == None):
		log.warning("SETTINGS IS NULL? IS THIS BEING CALLED BEFORE PLUGIN START?")
		Load()
	rv = _sets.Get(name, defaultValue)
	formatDict = {
		"date":     str(datetime.date.today()),
		"time":     datetime.datetime.now().strftime("%H:%M:%S"),
		"datetime": str(datetime.datetime.now().strftime("%Y-%m-%d %a %H:%M")),
	}

	if(formatDictionary != None):
		formatDict.update(formatDictionary)

	if(str == type(rv)):
		formatter = temp.TemplateFormatter()
		rv  = formatter.format(rv, **formatDict)
	if(list == type(rv)):
		formatter = temp.TemplateFormatter()
		rv = [ (formatter.format(r, **formatDict) if str == type(r) else r) for r in rv ]
	return rv

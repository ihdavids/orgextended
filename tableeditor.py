import os
import sublime

PCKGCTRL_SETTINGS = "Package Control.sublime-settings"
TABLE_PACKAGE     = "Table Editor"

def IsInstalled():
	settings = sublime.load_settings(PCKGCTRL_SETTINGS)
	return TABLE_PACKAGE in set(settings.get("installed_packages", []))

def Install():
	print("Installing `{}` ..".format(TABLE_PACKAGE))
	sublime.active_window().run_command("advanced_install_package", {"packages": TABLE_PACKAGE})
	#Hide()

def Hide():
	sublime.active_window().active_view().hide_popup()



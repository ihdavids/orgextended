import os
import sublime

PCKGCTRL_SETTINGS = "Package Control.sublime-settings"
TABLE_PACKAGE     = "Table Editor"
# TODO Make this much more generic!
#      support the languages and grammars we support.
#PS_PACKAGE        = "Powershell"

def IsInstalled():
	settings = sublime.load_settings(PCKGCTRL_SETTINGS)
	return TABLE_PACKAGE in set(settings.get("installed_packages", []))

#def IsPkgInstalled(pkgName):
#	settings = sublime.load_settings(PCKGCTRL_SETTINGS)
#	return pkgName in set(settings.get("installed_packages", []))

def Install():
	print("Installing `{}` ..".format(TABLE_PACKAGE))
	sublime.active_window().run_command("advanced_install_package", {"packages": TABLE_PACKAGE})
	#Hide()

def Hide():
	sublime.active_window().active_view().hide_popup()



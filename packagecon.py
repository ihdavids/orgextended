# Package Control
import os
import sublime

PCKGCTRL_SETTINGS = "Package Control.sublime-settings"
TABLE_PACKAGE     = "Table Editor"
PS_PACKAGE        = "PowerShell"
#      support the languages and grammars we support.

def IsInstalled(pkg):
	settings = sublime.load_settings(PCKGCTRL_SETTINGS)
	return pkg in set(settings.get("installed_packages", []))

#def IsPkgInstalled(pkgName):
#	settings = sublime.load_settings(PCKGCTRL_SETTINGS)
#	return pkgName in set(settings.get("installed_packages", []))

def Install(pkg):
	print("Installing `{}` ..".format(pkg))
	sublime.active_window().run_command("advanced_install_package", {"packages": pkg})
	#Hide()

def Hide():
	sublime.active_window().active_view().hide_popup()




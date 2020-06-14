import string
import sublime
import sublime_plugin
import datetime
import re



cur1 = re.compile('\\$0')

# A really quick and dirty template mechanism.
# Stolen from: https://makina-corpus.com/blog/metier/2016/the-worlds-simplest-python-template-engine
class TemplateFormatter(string.Formatter):
    # {stringVal.upper:call} - make a function call to upper method 
    def format_field(self, value, spec):
        if spec == 'call':
            return value()
        else:
            return super(TemplateFormatter, self).format_field(value, spec)



def ExpandTemplate(view, template):
    # Supported expansions
    formatDict = {
    "date": str(datetime.date.today()),
    "time": datetime.datetime.now().strftime("%H:%M:%S"),
    #"datetime": str(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    "datetime": str(datetime.datetime.now().strftime("%Y-%m-%d %a %H:%M")),
    "file": str(view.file_name()),
    "clipboard": sublime.get_clipboard()
    }

    formatter = TemplateFormatter()
    template  = formatter.format(template, **formatDict)

    global cur1
    mat = cur1.search(template)
    pos = -1
    if(mat != None):
    	pos = mat.start(0)
    	template = cur1.sub('',template)
    return (template, pos)



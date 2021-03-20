import json
import sublime
import sublime_plugin


def sortMessages(x):
    r = x
    xs = x.split('.')
    if(len(xs) <= 1):
        return 0
    m = 1
    c = 0
    for i in range(len(xs)-1,-1,-1):
        x = xs[i]
        c = c+(int(x)*m)
        m *= 100
    return c

# ===================================================================================
class OrgBuildDevDocsCommand(sublime_plugin.TextCommand):
    """Show the current worklog to the user"""
    def run(self, edit):
        view = sublime.active_window().new_file()
        view.set_syntax_file("Packages/OrgExtended/OrgExtended.sublime-syntax")
        messData = sublime.load_resource("Packages/OrgExtended/messages.json")
        msgs = json.loads(messData)
        ks = msgs.keys()
        ks = list(ks)
        ks = sorted(ks, key=sortMessages, reverse=True)
        for n in ks:
            name = n + ".org"
            pdata = None
            try:
                pdata = sublime.load_resource("Packages/OrgExtended/messages/" + name)
            except:
                pass
            if(not pdata):
                continue
            pdata = pdata.replace("\r","")
            view.insert(edit,view.size(),"\n" + pdata + "\n")
        pass

# ===================================================================================
class OrgShowTestfileCommand(sublime_plugin.TextCommand):
    """Show an org testfile to help users get started"""
    def run(self, edit):
        view = sublime.active_window().new_file()
        view.set_syntax_file("Packages/OrgExtended/OrgExtended.sublime-syntax")
        data = sublime.load_resource("Packages/OrgExtended/tests/testfile.org")
        data = data.replace("\r","")
        view.insert(edit,view.size(),"\n" + data + "\n")
        view.run_command("save")

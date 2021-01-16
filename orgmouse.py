import sublime
import sublime_plugin
import OrgExtended.pymitter as evt

class OrgMouseHandlerCommand(sublime_plugin.TextCommand):
    def run(self, edit, event=None):
        pt = 0 if not event else self.view.window_to_text((event["x"], event["y"]))
        evt.Get().emit("orgmouse", pt, self.view, edit)

    def want_event(self):
        return True	

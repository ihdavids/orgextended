
import sublime
import sublime_plugin
import requests
import OrgExtended.orgutil.util as util
import OrgExtended.orgdb as db
from OrgExtended.orgutil.addmethod import *
import OrgExtended.orgparse.node as node
import OrgExtended.orgparse.date as odate
import OrgExtended.asana as asana
import datetime
import dateutil.parser as dp

def CreateUniqueViewNamed(name):
    # Return the view if it exists
    win = sublime.active_window()
    for view in win.views():
        if view.name() == name:
            win.focus_view(view)
            return view
    win.run_command('new_file')
    view = win.active_view()
    view.set_name(name)
    view.set_syntax_file("Packages/OrgExtended/OrgExtended.sublime-syntax")
    return view


@add_method(node.OrgBaseNode)
def asanatag(self, defaultVal = None):
    if(defaultVal == None):
        defaultVal = []
    globalStartup = sets.Get("asana",defaultVal)
    return self.list_comment("ASANA", globalStartup)

class ProgressNotifier():
    """
    Animates an indicator, [=   ]

    :param message:
        The message to display next to the activity indicator

    :param success_message:
        The message to display once the thread is complete
    """

    def __init__(self, message, success_message = ''):
        self.message = message
        self.success_message = success_message
        self.stopped = False
        self.addend = 1
        self.size = 8
        sublime.set_timeout(lambda: self.run(0), 100)

    def run(self, i):
        if self.stopped:
            return

        before = i % self.size
        after = (self.size - 1) - before

        sublime.status_message('%s [%s=%s]' % (self.message, ' ' * before, ' ' * after))

        if not after:
            self.addend = -1
        if not before:
            self.addend = 1
        i += self.addend

        sublime.set_timeout(lambda: self.run(i), 100)

    def stop(self):
        if not self.stopped:
            sublime.status_message(self.success_message)
            self.stopped = True

#{'gid': '148322745070654', 'name': 'Today', 'resource_type': 'project'}, {'gid': '216560229717739', 'name': '50th Cake', 'resource_type': 'project'}, {'gid': '216560229717754', 'name': 'Next Week', 'resource_type': 'project'}, {'gid': '1201249509497674', 'name': 'Basics', 'resource_type': 'project'}, {'gid': '1200875183424699', 'name': 'Bathroom Reno', 'resource_type': 'project'}, {'gid': '1200875298067939', 'name': 'Buffi Todo', 'resource_type': 'project'}, {'gid': '1200875183424693', 'name': 'Kitchen Reno', 'resource_type': 'project'}, {'gid': '1200875183424697', 'name': 'Ian Todo', 'resource_type': 'project'}, {'gid': '1200886573454708', 'name': 'Ian Office Move', 'resource_type': 'project'}, {'gid': '1200886573454803', 'name': 'Trip', 'resource_type': 'project'}, {'gid': '1200886573454832', 'name': 'Reading', 'resource_type': 'project'}]



class AsanaConnection:
    def __init__(self, token):
        self.api = asana.AsanaAPI(token, debug=True)
        # see your workspaces
        #myspaces = asana_api.list_workspaces()  #Result: [{u'id': 123456789, u'name': u'asanapy'}]
        # create a new project
        #asana_api.create_project('test project', myspaces[0]['id'])
        # create a new task
        #asana_api.create_task('yetanotherapitest', myspaces[0]['id'], assignee_status='later', notes='some notes')
        # add a story to task
        #asana_api.add_story(mytask, 'omgwtfbbq')




class OrgAsanaBaseCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        self.SetupDataFromSettings()
        
        if not self.token:
            self.HelpText()
            return

        self.connection = AsanaConnection(self.token)
        self.defer(lambda: self.Work())

    def defer(self, fn):
        self.async(fn, 0)
        
    def async(self, fn, delay):
        progress = ProgressNotifier('Asana: Working')
        sublime.set_timeout_async(lambda: self.call(fn, progress), delay)
        sublime.set_timeout_async(lambda: progress.stop(), 5000)
    
    def call(self, fn, progress):
        fn()
        progress.stop()

    def GetS(self, name, defaultVal):
        val = self.settings.get(name)
        if(val == None):
            val = defaultVal
        return val

    def SetupDataFromSettings(self):
        self.settings = sublime.load_settings("OrgExtended.sublime-settings")
        self.token    = self.GetS("AsanaToken",None)

    def HelpText(self):
        message  = "Sorry for the interruption, in order to use the package please go to:\n%s\nand paste the token in the settings (Preferences -> Package Settings -> Asana -> Settings - User). " % self.TokenUrl()
        self.ShowOutput(message)

    def show_token_expired_help(self, e):
        self.show_output_panel_composing("It seems your token is invalid or has expired, try adding it again.\nToken URL: %s" % self.token_url(), "The error encountered was: '%s'" % e)

    def ShowOutput(self, *args):
        help_text = "\n".join(*args)
        self.output_view = self.view.window().get_output_panel("asanaout")
        self.output_view.set_read_only(False)
        self.output_view.run_command("append", { "characters": text })
        self.output_view.set_read_only(True)
        self.view.window().run_command("show_panel", { "panel": "output.asanaout" })

    def Work(self):
        try:
            self.Boards = self.connection.api.list_projects()
            self.Board = None
            node = db.Get().RootInView(self.view)
            if(node != None):
                asanatag = node.asanatag()
                if(len(asanatag != 0)):
                    pass
            self.WorkImpl(self.connection)
            self.connection = None
        except requests.exceptions.HTTPError as e:
            #self.show_token_expired_help(e)
            self.connection = None
            raise e

    def WorkImpl(self, connection):
        # Override me
        pass


class OrgAsanaSyncBoardCommand(OrgAsanaBaseCommand):
    def WorkImpl(self, connection):


        update = False
        if(self.Board != None):
            update = True
            # Clear current view
            self.view.EraseAll()
            # Rebuild the board in this view.
            self.CreateBoardInView(self.view, board)
        if(not update):
            self.AuthorNewBoard()

    def AuthorNewBoard(self):
        self.BoardsList = []
        print(str(self.Boards))
        for b in self.Boards:
            self.BoardsList.append(b.name)
        self.show_quick_panel(self.BoardsList, self.OnCreateBoardPage)

    def OnCreateBoardPage(self, index):
        if(index >= 0):
            board = self.Boards[index]
            v = CreateUniqueViewNamed("asana_" + board.name + ".org")
            self.CreateBoardInView(v, board)

    # def CreateBoardInView(self, v, board):
    #     print(board.goo())
    #     v.InsertEnd("#+TITLE: Asana - {}\n".format(board.name))
    #     v.InsertEnd("#+ASANA: {}\n".format(board._id))
    #     v.InsertEnd("\n")
    #     for l in board.lists:
    #         v.InsertEnd("* {} {}\n".format("DONE" if l.closed else "TODO",l.name))
    #         v.InsertEnd("  :PROPERTIES:\n")
    #         v.InsertEnd("    :TRELLOID: {}\n".format(l._id))
    #         v.InsertEnd("  :END:\n")
    #         for c in l.cards:
    #             print(c.goo())
    #             v.InsertEnd("** {} {}{}\n".format("DONE" if c.closed else "TODO", c.name.ljust(70), (":" + ":".join([str(x['color']) for x in c.labels]) + ":") if c.labels else ""))
    #             if(c.due != None):
    #                 v.InsertEnd("   SCHEDULED: {}\n".format(odate.OrgDate.format_date(dp.parse(c.due),True)))
    #             v.InsertEnd("   :PROPERTIES:\n")
    #             v.InsertEnd("     :TRELLOID: {}\n".format(c._id))
    #             v.InsertEnd("     :URL: [[{}][Card]]\n".format(c.short_url))
    #             if(len(c.members) > 0):
    #                 v.InsertEnd("     :MEMBERS: {}\n".format(",".join([x.username for x in c.members])))
    #             v.InsertEnd("   :END:\n")
    #             if(c.desc):
    #                 v.InsertEnd("   " + c.desc.replace("\n","\n   ") + "\n")
    #             clists = c.checklists
    #             for clist in clists:
    #                 v.InsertEnd("*** {} [%]\n".format(clist.name))
    #                 for it in clist.checkItems:
    #                     v.InsertEnd("    - [{}] {}\n".format(' ' if it.state == 'incomplete' else 'x',it.name))
    #             comments = c.comments()
    #             for com in comments:
    #                 v.InsertEnd("*** From {}\n".format(com["username"]))
    #                 v.InsertEnd("    {}\n".format(com["text"]))
    #     v.run_command('org_recalc_all_checkbox_summaries')
    #     v.run_command('org_fold_all')


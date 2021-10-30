try:
    import sublime
    import sublime_plugin
    from Trello.trello import TrelloCommand
    import requests
    from Trello.trello import TrelloCommand
    from Trello.trello_cache import TrelloCache
    from Trello.operations import BoardOperation, CardOperation
    import OrgExtended.orgutil.util as util
    import OrgExtended.orgdb as db
    from OrgExtended.orgutil.addmethod import *
    import OrgExtended.orgparse.node as node
    import OrgExtended.orgparse.date as odate
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
    def trellotag(self, defaultVal = None):
        if(defaultVal == None):
            defaultVal = []
        globalStartup = sets.Get("trello",defaultVal)
        return self.list_comment("TRELLO", globalStartup)

    class OrgTrelloBaseCommand(TrelloCommand):
        def work(self, connection):
            try:
                self.Member = connection.me
                # Grab the boards list. We will use thit to try to match up
                # with current document for a board update OR for authoring a new board
                # page interactively.
                self.Boards = self.Member.boards
                self.Board = None
                node = db.Get().RootInView(self.view)
                if(node != None):
                    trellotag = node.trellotag()
                    if(len(trellotag != 0)):
                        # TODO: Edit check?
                        #       I shouldn't do this if you have edits to the
                        #       current buffer
                        self.BoardId = trellotag[0]
                        self.Board   = self.Member.get_board(self.BoardId)
                self.safe_work(connection)
            except requests.exceptions.HTTPError as e:
                self.show_token_expired_help(e)
                raise e
        def safe_work(self, connection):
            # Override me
            pass



    class OrgTrelloSyncBoardCommand(OrgTrelloBaseCommand):
        def safe_work(self, connection):
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
            for b in self.Boards:
                self.BoardsList.append(b.name)
            self.show_quick_panel(self.BoardsList, self.OnCreateBoardPage)

        def OnCreateBoardPage(self, index):
            if(index >= 0):
                board = self.Boards[index]
                v = CreateUniqueViewNamed("trello_" + board.name + ".org")
                self.CreateBoardInView(v, board)

        def CreateBoardInView(self, v, board):
            print(board.goo())
            v.InsertEnd("#+TITLE: Trello - {}\n".format(board.name))
            v.InsertEnd("#+TRELLO: {}\n".format(board._id))
            v.InsertEnd("\n")
            for l in board.lists:
                v.InsertEnd("* {} {}\n".format("DONE" if l.closed else "TODO",l.name))
                v.InsertEnd("  :PROPERTIES:\n")
                v.InsertEnd("    :TRELLOID: {}\n".format(l._id))
                v.InsertEnd("  :END:\n")
                for c in l.cards:
                    print(c.goo())
                    v.InsertEnd("** {} {}{}\n".format("DONE" if c.closed else "TODO", c.name.ljust(70), (":" + ":".join([str(x['color']) for x in c.labels]) + ":") if c.labels else ""))
                    if(c.due != None):
                        v.InsertEnd("   SCHEDULED: {}\n".format(odate.OrgDate.format_date(dp.parse(c.due),True)))
                    v.InsertEnd("   :PROPERTIES:\n")
                    v.InsertEnd("     :TRELLOID: {}\n".format(c._id))
                    v.InsertEnd("     :URL: [[{}][Card]]\n".format(c.short_url))
                    if(len(c.members) > 0):
                        v.InsertEnd("     :MEMBERS: {}\n".format(",".join([x.username for x in c.members])))
                    v.InsertEnd("   :END:\n")
                    if(c.desc):
                        v.InsertEnd("   " + c.desc.replace("\n","\n   ") + "\n")
                    clists = c.checklists
                    for clist in clists:
                        v.InsertEnd("*** {} [%]\n".format(clist.name))
                        for it in clist.checkItems:
                            v.InsertEnd("    - [{}] {}\n".format(' ' if it.state == 'incomplete' else 'x',it.name))
                    comments = c.comments()
                    for com in comments:
                        v.InsertEnd("*** From {}\n".format(com["username"]))
                        v.InsertEnd("    {}\n".format(com["text"]))
            v.run_command('org_recalc_all_checkbox_summaries')
            v.run_command('org_fold_all')


    class OrgTrelloAddCardCommand(OrgTrelloBaseCommand):
        def safe_work(self, connection):
            pass


except ImportError as err:
    print("Install the Trello Package to add trello support to OrgExtended for SublimeText \n  >> " + str(err))


    

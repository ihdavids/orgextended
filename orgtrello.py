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

    class OrgTrelloSyncBoardCommand(TrelloCommand):
        def work(self, connection):
            try:
                self.safe_work(connection)
            except requests.exceptions.HTTPError as e:
                self.show_token_expired_help(e)
                raise e

        def safe_work(self, connection):
            self.Member = connection.me
            # Grab the boards list. We will use thit to try to match up
            # with current document for a board update OR for authoring a new board
            # page interactively.
            self.Boards = self.Member.boards
            node = db.Get().RootInView(self.view)
            update = False
            if(node != None):
                trellotag = node.trellotag()
                if(len(trellotag != 0)):
                    update = True
                    # TODO: Edit check?
                    #       I shouldn't do this if you have edits to the
                    #       current buffer
                    board_id = trellotag[0]
                    board = self.Member.get_board(board_id)
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
            v.InsertEnd("#+TITLE: Trello - {}\n".format(board.name))
            v.InsertEnd("#+TRELLO: {}\n".format(board._id))
            v.InsertEnd("\n")
            for l in board.lists:
                v.InsertEnd("* {} {}\n".format("DONE" if l.closed else "TODO",l.name))
                for c in l.cards:
                    v.InsertEnd("** {} {}                       \n".format("DONE" if c.closed else "TODO", c.name, c.labels if c.labels else ""))
                    if(c.desc):
                        v.InsertEnd("   " + c.desc.replace("\n","\n   "))




except ImportError as err:
    print("Install the Trello Package to add trello support to OrgExtended for SublimeText \n  >> " + str(err))


    

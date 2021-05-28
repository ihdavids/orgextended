import sublime
import sublime_plugin
import datetime


class BeancountNewTransactionCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        ai = sublime.active_window().active_view().settings().get('auto_indent')
        self.view.settings().set('auto_indent',False)
        snipName = "Packages/Beancount/snipets/transaction.sublime-snippet"
        # OTHER VARIABLES:
        # TM_FULLNAME - Users full name
        # TM_FILENAME - File name of the file being edited
        # TM_CURRENT_WORD - Word under cursor when snippet was triggered
        # TM_SELECTED_TEXT - Selected text when snippet was triggered
        # TM_CURRENT_LINE - Line of snippet when snippet was triggered
        # For NeoVintageous Users FORCE insert mode during snippet insertion for ease of use.
        self.view.run_command('_enter_insert_mode', {"count": 1, "mode": "mode_internal_normal"})
        self.view.run_command("insert_snippet", 
            { "name" : snipName
            , "MONTH":         datetime.datetime.now().strftime("%m")
            , "YEAR":          datetime.datetime.now().strftime("%Y")
            , "DAY":           datetime.datetime.now().strftime("%d")
            , "DATE":          str(datetime.date.today())
            , "TIME":          datetime.datetime.now().strftime("%H:%M:%S")
            , "CLIPBOARD":     sublime.get_clipboard()
            , "SELECTION":     self.view.substr(self.view.sel()[0])
            , "FILENAME":      self.view.file_name()
            , "DEFAULT_CURRENCY": "CAD"
            })
        sublime.active_window().active_view().settings().set('auto_indent',ai)


class BeancountNewFileCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        win = sublime.active_window()
        win.run_command('new_file')
        panel = win.active_view()
        panel.set_syntax_file("Packages/OrgExtended/OrgBeancount.sublime-syntax")
        


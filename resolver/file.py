
import re
import os
from fnmatch import fnmatch
import sublime
from .abstract import AbstractLinkResolver
import OrgExtended.orgdb as db

PATTERN_SETTING = 'resolver.local_file.pattern'
PATTERN_DEFAULT = r'^(file:)?(?P<filepath>.+?)(((::(?P<row>\d+))(::(?P<col>\d+))?)|(::\#(?P<cid>[a-zA-Z0-9!$@%&_-]+)))?\s*$'

FORCE_LOAD_SETTING = 'resolver.local_file.force_into_sublime'
FORCE_LOAD_DEFAULT = ['*.txt', '*.org', '*.py', '*.rb',
                      '*.html', '*.css', '*.js', '*.php', '*.c', '*.cpp', '*.h', '*.png', '*.jpg', '*.gif', '*.cs']


class Resolver(AbstractLinkResolver):

    '''
    @todo: If the link is a local org-file open it directly via sublime, otherwise use OPEN_LINK_COMMAND.
    '''

    def __init__(self, view):
        super(Resolver, self).__init__(view)
        get = self.settings.get
        pattern = get(PATTERN_SETTING, PATTERN_DEFAULT)
        self.regex = re.compile(pattern)
        self.force_load_patterns = get(FORCE_LOAD_SETTING, FORCE_LOAD_DEFAULT)

    def file_is_excluded(self, filepath):
        basename = os.path.basename(filepath)
        for pattern in self.force_load_patterns:
            if fnmatch(basename, pattern):
                print('found in force_load_patterns')
                return False
        return True

        folder_exclude_patterns = self.settings.get('folder_exclude_patterns')
        if basename in folder_exclude_patterns:
            print('found in folder_exclude_patterns')
            return True
        file_exclude_patterns = self.settings.get('file_exclude_patterns')
        for pattern in file_exclude_patterns:
            if fnmatch(basename, pattern):
                print('found in file_exclude_patterns')
                return True
        return False

    def expand_path(self, filepath):
        #print("FP: " + filepath)
        if(filepath.startswith("file:")):
            #print("REPLACE")
            filepath = filepath.replace("file:","", 1)
        #print("FP2: " + filepath)
        filepath = os.path.expandvars(filepath)
        filepath = os.path.expanduser(filepath)

        match = self.regex.match(filepath)
        if match:
            filepath, row, col, cid = match.group('filepath'), match.group('row'), match.group('col'), match.group('cid')
        else:
            row = None
            col = None
            cid = None

        # The presence of a custom ID means we jump
        # using a different means
        if(cid):
            print("Found ID trying to jump to: " + cid)
            db.Get().JumpToCustomId(cid)
            return True
        drive, filepath = os.path.splitdrive(filepath)
        if not filepath.startswith('/'):  # If filepath is relative...
            cwd = os.path.dirname(self.view.file_name())
            testfile = os.path.join(cwd, filepath)
            if os.path.exists(testfile):  # See if it exists here...
                filepath = testfile

        filepath = ''.join([drive, filepath]) if drive else filepath
        print('filepath: ' + filepath)
        if not self.file_is_excluded(filepath):
            if row:
                filepath += ':%s' % row
            if col:
                filepath += ':%s' % col
            self.view.window().open_file(filepath, sublime.ENCODED_POSITION)
            return True
        else:
            print('file_is_excluded: ' + filepath)

        return filepath

    def replace(self, content):
        content = self.expand_path(content)
        return content

    def execute(self, content):
        if content is not True:
            print('normal open')
            return super(Resolver, self).execute(content)

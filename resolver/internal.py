import re
import os
from fnmatch import fnmatch
import sublime
from .abstract import AbstractLinkResolver
import OrgExtended.orgdb as db
from OrgExtended.orgutil.util import *

PATTERN_SETTING = 'resolver.local_file.pattern'
PATTERN_DEFAULT = r'^(((::(?P<row>\d+))(::(?P<col>\d+))?)|(::\#(?P<cid>[a-zA-Z0-9!$@%&_-]+))|(::\*(?P<heading>[a-zA-Z0-9!$@%&_-]+)))?\s*$'

FORCE_LOAD_SETTING = 'resolver.local_file.force_into_sublime'
FORCE_LOAD_DEFAULT = ['*.txt', '*.org', '*.py', '*.rb',
                      '*.html', '*.css', '*.js', '*.php', '*.c', '*.cpp', '*.h', '*.png', '*.jpg', '*.gif', '*.cs']


class Resolver(AbstractLinkResolver):
    def __init__(self, view):
        super(Resolver, self).__init__(view)
        self.view = view
        get = self.settings.get
        pattern = get(PATTERN_SETTING, PATTERN_DEFAULT)
        self.regex = re.compile(pattern)
        self.force_load_patterns = get(FORCE_LOAD_SETTING, FORCE_LOAD_DEFAULT)

    def is_internal_link(self, filepath):
    	fp = filepath.strip()
    	# Starts with :: this is DEFINETLY an internal link
    	if(len(fp) > 2 and fp.startswith("::")):
    		return True
    	if('.' in fp):
    		return False
    	if('/' in fp):
    		return False
    	if('\\' in fp):
    		return False
    	# File path for sure?
    	if(':' in fp):
    		return False
    	if(os.path.isfile(fp)):
    		return False
    	# Okay, this PROBABLY is an internal link
    	print('Probably internal link')
    	return True

    def tryMatchHeading(self, heading):
        fpath = self.view.file_name().lower()
        fi = db.Get().FindInfo(fpath)
        if(fi):
            for n in fi.org:
                if not n.is_root() and n.heading == heading:
                    row = n.start_row + 1
                    col = 0
                    break
            filepath = self.view.file_name()
            if row:
                filepath += ':%s' % row
            if col:
                filepath += ':%s' % col
            self.view.window().open_file(filepath, sublime.ENCODED_POSITION)
            return True
        return False

    def tryMatchDirectTarget(self, heading):
        fpath = self.view.file_name().lower()
        fi = db.Get().FindInfo(fpath)
        if(fi):
            return False
            for n in fi.org:
                if not n.is_root() and n.heading == heading:
                    row = n.start_row + 1
                    col = 0
                    break
            filepath = self.view.file_name()
            if row:
                filepath += ':%s' % row
            if col:
                filepath += ':%s' % col
            self.view.window().open_file(filepath, sublime.ENCODED_POSITION)
            return True
        return False

    def tryMatchNamedObject(self, heading):
        fpath = self.view.file_name().lower()
        fi = db.Get().FindInfo(fpath)
        if(fi):
            return False
            for n in fi.org:
                if not n.is_root() and n.heading == heading:
                    row = n.start_row + 1
                    col = 0
                    break
            filepath = self.view.file_name()
            if row:
                filepath += ':%s' % row
            if col:
                filepath += ':%s' % col
            self.view.window().open_file(filepath, sublime.ENCODED_POSITION)
            return True
        return False

    def expand_path(self, filepath):
        filepath = os.path.expandvars(filepath)
        filepath = os.path.expanduser(filepath)
        if(not self.is_internal_link(filepath)):
            print("Not an internal link")
            return False

        # Check for standard internal link
        match = self.regex.match(filepath)
        if match:
            row, col, cid, heading = match.group('row'), match.group('col'), match.group('cid'), match.group('heading')
            # The presence of a custom ID means we jump
            # using a different means
            if(cid):
                print("Found ID trying to jump to: " + cid)
                db.Get().JumpToCustomId(cid)
                return True
            if(heading):
                return self.tryMatchHeading(heading)
            return False
        else:
            # Okay now the fun starts. We got an unidentifed link, this could be a:
            # <<>> target
            # A #+NAME "ed" object somewhere
            # a heading somewhere
            #
            # So we have to get creative and go find that.
            if(self.tryMatchDirectTarget(filepath)):
                return True
            if(self.tryMatchNamedObject(filepath)):
                return True
            if(self.tryMatchHeading(filepath)):
                return True

    def replace(self, content):
        content = self.expand_path(content)
        return content

    def execute(self, content):
        if content is not True:
            return super(Resolver, self).execute(content)

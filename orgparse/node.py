import re
import itertools
import sublime
try:
    from collections.abc import Sequence
except ImportError:
    from collections import Sequence

from .date import OrgDate, OrgDateClock, OrgDateRepeatedTask, parse_sdc
from .inline import to_plain_text
from .utils.py3compat import PY3, unicode
import copy
from .startup import *
import OrgExtended.pymitter as evt
import datetime


RE_TARGETS = re.compile(r'<<(?P<target>[^>]+)>>')

class OffsetIter:
    def __init__(self, lines):
        self._lines = lines
        self._cur   = 0
        self._len   = len(lines)

    def __iter__(self):
        return self

    @property
    def offset(self):
        return self._cur

    def __next__(self):
        self._cur += 1
        if self._cur < self._len:
            return self._lines[self._cur]
        raise StopIteration

def lines_to_chunks(lines):
    chunk = []
    count = 0
    start = 0
    end   = 0
    for l in lines:
        if RE_NODE_HEADER.search(l):
            end = count - 1
            yield (chunk, start, end)
            chunk = []
            start = count
        chunk.append(l.rstrip())
        count += 1
    end = count - 1
    yield (chunk, start, end)

RE_NODE_HEADER    = re.compile(r"^\*+ ")
RE_HEADER_REPLACE = re.compile("^\\*+ ") 
RE_INDENT_REPLACE = re.compile("^[ \t]*")
RE_DRAWER         = re.compile("^\\s*:([a-zA-Z][a-zA-Z0-9_-]*):\\s*$")

def parse_heading_level(heading):
    """
    Get star-stripped heading and its level

    >>> parse_heading_level('* Heading')
    ('Heading', 1)
    >>> parse_heading_level('******** Heading')
    ('Heading', 8)
    >>> parse_heading_level('*') # None since no space after star
    >>> parse_heading_level('*bold*') # None
    >>> parse_heading_level('not heading')  # None

    """
    try:
        match = RE_HEADING_STARS.search(heading)
        if match:
            return (match.group(2), len(match.group(1)))
    except:
        pass
    return (" ", 1)

RE_HEADING_STARS = re.compile(r'^(\*+)\s+(.*?)\s*$')


def parse_heading_tags(heading):
    """
    Get first tags and heading without tags

    >>> parse_heading_tags('HEADING')
    ('HEADING', [])
    >>> parse_heading_tags('HEADING :TAG1:TAG2:')
    ('HEADING', ['TAG1', 'TAG2'])
    >>> parse_heading_tags('HEADING: this is still heading :TAG1:TAG2:')
    ('HEADING: this is still heading', ['TAG1', 'TAG2'])
    >>> parse_heading_tags('HEADING :@tag:_tag_:')
    ('HEADING', ['@tag', '_tag_'])

    Here is the spec of tags from Org Mode manual:

      Tags are normal words containing letters, numbers, ``_``, and
      ``@``.  Tags must be preceded and followed by a single colon,
      e.g., ``:work:``.

      -- (info "(org) Tags")

    """
    match = RE_HEADING_TAGS.search(heading)
    if match:
        heading = match.group(1)
        tagstr = match.group(2)
        tags = tagstr.split(':')
        evt.Get().emit("tagsfound",tags)
    else:
        tags = []
    return (heading, tags)

# Tags are normal words containing letters, numbers, '_', and '@'. https://orgmode.org/manual/Tags.html
RE_HEADING_TAGS = re.compile(r'(.*?)\s*:([\w@:]+):\s*$')


def parse_heading_todos(heading, todo_candidates):
    """
    Get TODO keyword and heading without TODO keyword.

    >>> todos = ['TODO', 'DONE']
    >>> parse_heading_todos('Normal heading', todos)
    ('Normal heading', None)
    >>> parse_heading_todos('TODO Heading', todos)
    ('Heading', 'TODO')

    """
    for todo in todo_candidates:
        todows = '{0} '.format(todo)
        if heading.startswith(todows):
            return (heading[len(todows):], todo)
    return (heading, None)


def parse_heading_priority(heading):
    """
    Get priority and heading without priority field..

    >>> parse_heading_priority('HEADING')
    ('HEADING', None)
    >>> parse_heading_priority('[#A] HEADING')
    ('HEADING', 'A')
    >>> parse_heading_priority('[#0] HEADING')
    ('HEADING', '0')
    >>> parse_heading_priority('[#A]')
    ('', 'A')

    """
    match = RE_HEADING_PRIORITY.search(heading)
    if match:
        return (match.group(2), match.group(1))
    else:
        return (heading, None)

RE_HEADING_PRIORITY = re.compile(r'^\s*\[#([A-Z0-9])\] ?(.*)$')


def parse_property(line):
    """
    Get property from given string.

    >>> parse_property(':Some_property: some value')
    ('Some_property', 'some value')
    >>> parse_property(':Effort: 1:10')
    ('Effort', 70)

    """
    prop_key = None
    prop_val = None
    match = RE_PROP.search(line)
    if match:
        prop_key = match.group(1)
        prop_val = match.group(2)
        if prop_key == 'Effort':
            (h, m) = prop_val.split(":", 2)
            if h.isdigit() and m.isdigit():
                prop_val = int(h) * 60 + int(m)
    return (prop_key, prop_val)

RE_PROP = re.compile(r'^\s*:(.*?):\s*(.*?)\s*$')


def parse_comment(line):
    """
    Parse special comment such as ``#+SEQ_TODO``

    >>> parse_comment('#+SEQ_TODO: TODO | DONE')
    ('SEQ_TODO', 'TODO | DONE')
    >>> parse_comment('# not a special comment')  # None

    """
    if line.startswith('#+'):
        comment = line.lstrip('#+').split(':', 1)
        if len(comment) == 2:
            return (comment[0], comment[1].strip())


def parse_seq_todo(line):
    """
    Parse value part of SEQ_TODO/TODO/TYP_TODO comment.

    >>> parse_seq_todo('TODO | DONE')
    (['TODO'], ['DONE'])
    >>> parse_seq_todo(' Fred  Sara   Lucy Mike  |  DONE  ')
    (['Fred', 'Sara', 'Lucy', 'Mike'], ['DONE'])
    >>> parse_seq_todo('| CANCELED')
    ([], ['CANCELED'])
    >>> parse_seq_todo('REPORT(r) BUG(b) KNOWNCAUSE(k) | FIXED(f)')
    (['REPORT', 'BUG', 'KNOWNCAUSE'], ['FIXED'])

    See also:

    * (info "(org) Per-file keywords")
    * (info "(org) Fast access to TODO states")

    """
    todo_done = line.split('|', 1)
    if len(todo_done) == 2:
        (todos, dones) = todo_done
    else:
        (todos, dones) = (line, '')
    strip_fast_access_key = lambda x: x.split('(', 1)[0]
    return (list(map(strip_fast_access_key, todos.split())),
            list(map(strip_fast_access_key, dones.split())))


class OrgEnv(object):

    """
    Information global to the file (e.g, TODO keywords).
    """

    def __init__(self, todos=[], dones=[],
                 filename='<undefined>'):
        self._todos = list(todos)
        self._dones = list(dones)
        self._todo_not_specified_in_comment = True
        self._filename = filename
        self._nodes = []
        self.properties = []
        self.customids = {}

    @property
    def nodes(self):
        """
        A list of org nodes.

        >>> OrgEnv().nodes   # default is empty (of course)
        []

        >>> from orgparse import loads
        >>> loads('''
        ... * Heading 1
        ... ** Heading 2
        ... *** Heading 3
        ... ''').env.nodes      # doctest: +ELLIPSIS  +NORMALIZE_WHITESPACE
        [<orgparse.node.OrgRootNode object at 0x...>,
         <orgparse.node.OrgNode object at 0x...>,
         <orgparse.node.OrgNode object at 0x...>,
         <orgparse.node.OrgNode object at 0x...>]

        """
        return self._nodes

    def add_todo_keys(self, todos, dones):
        if self._todo_not_specified_in_comment:
            self._todos = []
            self._dones = []
            self._todo_not_specified_in_comment = False
        self._todos.extend(todos)
        self._dones.extend(dones)

    @property
    def todo_keys(self):
        """
        TODO keywords defined for this document (file).

        >>> env = OrgEnv()
        >>> env.todo_keys
        ['TODO']

        """
        return self._todos

    @property
    def done_keys(self):
        """
        DONE keywords defined for this document (file).

        >>> env = OrgEnv()
        >>> env.done_keys
        ['DONE']

        """
        return self._dones

    @property
    def all_todo_keys(self):
        """
        All TODO keywords (including DONEs).

        >>> env = OrgEnv()
        >>> env.all_todo_keys
        ['TODO', 'DONE']

        """
        return self._todos + self._dones

    @property
    def filename(self):
        """
        Return a path to the source file or similar information.

        If the org objects are not loaded from a file, this value
        will be a string of the form ``<SOME_TEXT>``.

        :rtype: str

        """
        return self._filename

    # parser

    def from_chunks(self, chunks):
        yield OrgRootNode.from_chunk(self, next(chunks))
        for chunk in chunks:
            yield OrgNode.from_chunk(self, chunk)


class OrgBaseNode(Sequence):
    """
    Base class for :class:`OrgRootNode` and :class:`OrgNode`

    .. attribute:: env

       An instance of :class:`OrgEnv`.
       All nodes in a same file shares same instance.

    :class:`OrgBaseNode` is an iterable object:

    >>> from orgparse import loads
    >>> root = loads('''
    ... * Heading 1
    ... ** Heading 2
    ... *** Heading 3
    ... * Heading 4
    ... ''')
    >>> for node in root:
    ...     print(node)
    <BLANKLINE>
    * Heading 1
    ** Heading 2
    *** Heading 3
    * Heading 4

    Note that the first blank line is due to the root node, as
    iteration contains the object itself.  To skip that, use
    slice access ``[1:]``:

    >>> for node in root[1:]:
    ...     print(node)
    * Heading 1
    ** Heading 2
    *** Heading 3
    * Heading 4

    It also support sequence protocol.

    >>> print(root[1])
    * Heading 1
    >>> root[0] is root  # index 0 means itself
    True
    >>> len(root)   # remember, sequence contains itself
    5

    Note the difference between ``root[1:]`` and ``root[1]``:

    >>> for node in root[1]:
    ...     print(node)
    * Heading 1
    ** Heading 2
    *** Heading 3

    """
    def find_last_child_index(self):
        level = self.level
        start = self._index
        end = start
        for i in range(start+1, len(self.env._nodes)):
            if(self.env._nodes[i]._level <= level):
                break
            end = i
        return end

    def get_comment(self, key, defaultVal):
        if( key in self._special_comments):
            return self._special_comments[key]
        return defaultVal
    
    def startup(self, defaultVal):
        comment = " ".join(defaultVal)
        val = self.get_comment("STARTUP",[comment])[0].split(" ")
        return val

    def archive(self, defaultVal):
        dval = defaultVal
        if(self.parent):
            dval = self.parent.archive(defaultVal)
        val = self.get_comment("ARCHIVE", [ dval ])
        return val[0]

    def todo_states(self, defaultVal):
        dval = defaultVal
        if(self.parent):
            dval = self.parent.todo_states(defaultVal)
        val = self.get_comment("TODO", [ dval ])
        return val[0]

    def get_last_child(self):
        pos = self.find_last_child_index()
        return self.env._nodes[pos]
    

    def insert_at(self, n, index):
        if(n == None):
            return

        if(type(n) is OrgRootNode):
            n = n.env._nodes[n._index+1] 

        if(index == n.index):
            return

        # IF the location is a child of ME
        # then I have a problem! I need to
        # validate for that.

        global RE_HEADER_REPLACE
        global RE_INDENT_REPLACE

        # I have to copy the node or else
        # I could have problems pulling it out
        # of the remote tree and corrupting that.
        n = copy.copy(n)
        # Keep a reference around so the target env does not go
        # away.
        sourceEnv = n.env

        sibling = self.env._nodes[index]

        level  = sibling.level
        clevel = n.level
        ldif   = level - clevel
        pos    = index
        #pos = self._index
        count = 0
        for cnode in n[0]:
            count += 1
            ccn    = copy.copy(cnode)
            self.env._nodes.insert(pos + count, ccn)
            ccn._level = ccn._level + ldif
            ccn._index = pos + count
            ccn.env    = self.env
            header     = "*" * ccn._level
            indent     = " " * (ccn._level+1)
            ccn._lines[0] = RE_HEADER_REPLACE.sub(header + " ", ccn._lines[0])
            ccn._heading = ccn._lines[0]
            for i in range(1,len(ccn._lines)):
                ccn._lines[i] = RE_INDENT_REPLACE.sub(indent, ccn._lines[i])
        for i in range(pos + count, len(self.env._nodes)):
            self.env._nodes[i]._index += count
        # Now setup my new nodes Env properly
        n.env = self.env
        # Reset the num_children count, we will recount again, just in case
        self._count = -1


    def insert_child(self, n):
        if(n == None):
            return None

        global RE_HEADER_REPLACE
        global RE_INDENT_REPLACE
        if(type(n) is OrgRootNode):
            n = n.env._nodes[n._index+1]
        n = copy.copy(n)
        # Keep a reference around so the target env does not go
        # away.
        sourceEnv = n.env
        level = self.level
        clevel = n.level
        ldif   = level - clevel + 1
        pos = self.find_last_child_index()
        startrow = self._end
        if(len(self.env._nodes) > pos):
            startrow = self.env._nodes[pos]._end + 1
        elif(pos > self._index):
            startrow = self.env._nodes[pos-1]._end + 1
        #pos = self._index
        retNode = None
        count = 0
        for cnode in n[0]:
            count += 1
            ccn = copy.copy(cnode)
            self.env._nodes.insert(pos + count, ccn)
            if(count == 1):
                retNode = ccn
            size = ccn.size()
            # We have to update start end at least
            ccn._start = startrow
            ccn._end   = startrow + size
            # Update property drawer location at least!
            inprops = False
            c = 0
            s = 0
            for line in ccn._lines:
                if(inprops):
                    if(":END:" in line):
                        ccn._property_drawer_location = (ccn._start + s , ccn._start + c)
                        break
                elif(":PROPERTIES:" in line):
                    inprops = True
                    s = c
                c += 1
            # fix property drawer lines
            startrow  += size + 1
            ccn._level = ccn._level + ldif
            ccn._index = pos + count
            ccn.env = self.env
            header = "*" * ccn._level
            indent = " " * (ccn._level+1)
            newHeading = RE_HEADER_REPLACE.sub(header + " ", ccn._lines[0])
            if(len(ccn._lines) > 1):
                ccn._lines = ccn._lines[1:]
                ccn._lines.insert(0, newHeading)
            else:
                ccn._lines = [newHeading]
            ccn._heading = ccn._lines[0]
            for i in range(1,len(ccn._lines)):
                ccn._lines[i] = RE_INDENT_REPLACE.sub(indent, ccn._lines[i])
        for i in range(pos + count, len(self.env._nodes)):
            self.env._nodes[i]._index += count
        # Now setup my new nodes Env properly
        n.env = self.env
        # Reset the num_children count, we will recount again, just in case
        self._count = -1
        return retNode

    # Remove this node, and all its children!
    def remove_node(self):
        pos = self._index
        end = pos
        size = len(self.env._nodes)
        level = self.level
        if(pos < (size-1)):
            for i in range(pos+1,size):
                # < means higher in hierarchy
                if(self.env._nodes[i].level <= level):
                    break
                end = i
        #print("removing "+str(pos)+" to "+str(end) + " in " + str(len(self.env._nodes)))
        for i in range(end,pos-1,-1):
            self.env._nodes.pop(i)
        # Remove the elements.
        #del self.env._nodes[pos:end+1]
        # Now update the indexes!
        size = len(self.env._nodes)
        for i in range(pos,size):
            self.env._nodes[i]._index = i

    # NOTE: This will remove all children!
    def replace_node(self, n):
        if(type(n) is OrgRootNode):
            n = n.env._nodes[n._index+1]
        level = self.level
        clevel = n.level
        ldif   = level - clevel
        pos = self._index
        count = 0
        self.remove_node()
        for cnode in n[0]:
            self.env._nodes.insert(pos + count, cnode)
            cnode._level = cnode._level + ldif
            cnode._index = pos + count
            count += 1
        for i in range(pos + count, len(self.env._nodes)):
            self.env._nodes[i]._index += count

    def __init__(self, env, index=None):
        """
        Create a :class:`OrgBaseNode` object.

        :type env: :class:`OrgEnv`
        :arg  env: This will be set to the :attr:`env` attribute.

        """
        self.env = env

        # content
        self._lines = []
        # Num children, gets cached.
        self._count = -1

        # FIXME: use `index` argument to set index.  (Currently it is
        # done externally in `parse_lines`.)
        if index is not None:
            self._index = index
            """
            Index of `self` in `self.env.nodes`.

            It must satisfy an equality::

                self.env.nodes[self._index] is self

            This value is used for quick access for iterator and
            tree-like traversing.

            """

    def __iter__(self):
        yield self
        level = self.level
        for node in self.env._nodes[self._index + 1:]:
            if node.level > level:
                yield node
            else:
                break

    def __len__(self):
        return sum(1 for _ in self)

    def __nonzero__(self):
        # As self.__len__ returns non-zero value always this is not
        # needed.  This function is only for performance.
        return True

    __bool__ = __nonzero__  # PY3

    def __getitem__(self, key):
        if isinstance(key, slice):
            return itertools.islice(self, key.start, key.stop, key.step)
        elif isinstance(key, int):
            if key < 0:
                key += len(self)
            for (i, node) in enumerate(self):
                if i == key:
                    return node
            raise IndexError("Out of range {0}".format(key))
        else:
            raise TypeError("Inappropriate type {0} for {1}"
                            .format(type(key), type(self)))

    # tree structure

    def _find_same_level(self, iterable):
        for node in iterable:
            if node.level < self.level:
                return
            if node.level == self.level:
                return node

    @property
    def start_row(self):
        return self._start

    def size(self):
        return self._end - self._start

    @property
    def end_row(self):
        end = self._end
        midx = self._index
        idx  = self.find_last_child_index()
        if(midx != idx):
            end = self.env._nodes[idx].end_row
        return end

    @property
    def local_end_row(self):
        return self._end

    def recalc_duration(self):
        self._local_duration = datetime.timedelta(seconds=0)
        for c in self.clock:
            self._local_duration += c.duration
        self._total_duration = copy.copy(self._local_duration)
        for c in self.children:
            self._total_duration += c.duration()

    def duration(self):
        if(not hasattr(self,'_local_duration')):
            self.recalc_duration()
        return self._total_duration

    def local_duration(self):
        if(not hasattr(self,'_local_duration')):
            self.recalc_duration()
        return self._local_duration

    @property
    def end_row(self):
        end = self._end
        midx = self._index
        idx  = self.find_last_child_index()
        if(midx != idx):
            end = self.env._nodes[idx].end_row
        return end

    @property
    def previous_same_level(self):
        """
        Return previous node if exists or None otherwise.

        >>> from orgparse import loads
        >>> root = loads('''
        ... * Node 1
        ... * Node 2
        ... ** Node 3
        ... ''')
        >>> (n1, n2, n3) = list(root[1:])
        >>> n1.previous_same_level is None
        True
        >>> n2.previous_same_level is n1
        True
        >>> n3.previous_same_level is None  # n2 is not at the same level
        True

        """
        return self._find_same_level(reversed(self.env._nodes[:self._index]))

    @property
    def next_same_level(self):
        """
        Return next node if exists or None otherwise.

        >>> from orgparse import loads
        >>> root = loads('''
        ... * Node 1
        ... * Node 2
        ... ** Node 3
        ... ''')
        >>> (n1, n2, n3) = list(root[1:])
        >>> n1.next_same_level is n2
        True
        >>> n2.next_same_level is None  # n3 is not at the same level
        True
        >>> n3.next_same_level is None
        True

        """
        return self._find_same_level(self.env._nodes[self._index + 1:])

    # FIXME: cache parent node
    def _find_parent(self):
        for node in reversed(self.env._nodes[:self._index]):
            if node.level < self.level:
                return node

    def get_parent(self, max_level=None):
        """
        Return a parent node.

        :arg int max_level:
            In the normally structured org file, it is a level
            of the ancestor node to return.  For example,
            ``get_parent(max_level=0)`` returns a root node.

            In general case, it specify a maximum level of the
            desired ancestor node.  If there is no ancestor node
            which level is equal to ``max_level``, this function
            try to find an ancestor node which level is smaller
            than ``max_level``.

        >>> from orgparse import loads
        >>> root = loads('''
        ... * Node 1
        ... ** Node 2
        ... ** Node 3
        ... ''')
        >>> (n1, n2, n3) = list(root[1:])
        >>> n1.get_parent() is root
        True
        >>> n2.get_parent() is n1
        True
        >>> n3.get_parent() is n1
        True

        For simplicity, accessing :attr:`parent` is alias of calling
        :meth:`get_parent` without argument.

        >>> n1.get_parent() is n1.parent
        True
        >>> root.parent is None
        True

        This is a little bit pathological situation -- but works.

        >>> root = loads('''
        ... * Node 1
        ... *** Node 2
        ... ** Node 3
        ... ''')
        >>> (n1, n2, n3) = list(root[1:])
        >>> n1.get_parent() is root
        True
        >>> n2.get_parent() is n1
        True
        >>> n3.get_parent() is n1
        True

        Now let's play with `max_level`.

        >>> root = loads('''
        ... * Node 1 (level 1)
        ... ** Node 2 (level 2)
        ... *** Node 3 (level 3)
        ... ''')
        >>> (n1, n2, n3) = list(root[1:])
        >>> n3.get_parent() is n2
        True
        >>> n3.get_parent(max_level=2) is n2  # same as default
        True
        >>> n3.get_parent(max_level=1) is n1
        True
        >>> n3.get_parent(max_level=0) is root
        True

        """
        if max_level is None:
            max_level = self.level - 1
        parent = self._find_parent()
        while parent.level > max_level:
            parent = parent.get_parent()
        return parent

    @property
    def parent(self):
        """
        Alias of :meth:`get_parent()` (calling without argument).
        """
        return self.get_parent()
    # FIXME: cache children nodes
    def _find_children(self):
        nodeiter = iter(self.env._nodes[self._index + 1:])
        try:
            node = next(nodeiter)
        except StopIteration:
            return
        if node.level <= self.level:
            return
        yield node
        last_child_level = node.level
        for node in nodeiter:
            if node.level <= self.level:
                return
            if node.level <= last_child_level:
                yield node
                last_child_level = node.level

    @property
    def num_children(self):
        if(type(self) == OrgRootNode):
            if(self._count == -1):
                self._count = 0
                for i in range(1, len(self.env._nodes)):
                    if(self.env._nodes[i]._level == 1):
                        self._count += 1
            return self._count

        if(self._count == -1):
            self._count = 0
            idx   = self._index + 1
            level = self._level
            for i in range(self._index + 1, len(self.env._nodes)):
                if(self.env._nodes[i]._level <= level):
                    return self._count
                self._count += 1
        return self._count

    @property
    def children(self):
        """
        A list of child nodes.

        >>> from orgparse import loads
        >>> root = loads('''
        ... * Node 1
        ... ** Node 2
        ... *** Node 3
        ... ** Node 4
        ... ''')
        >>> (n1, n2, n3, n4) = list(root[1:])
        >>> (c1, c2) = n1.children
        >>> c1 is n2
        True
        >>> c2 is n4
        True

        Note the difference to ``n1[1:]``, which returns the Node 3 also.:

        >>> (m1, m2, m3) = list(n1[1:])
        >>> m2 is n3
        True

        """
        return list(self._find_children())

    @property
    def root(self):
        """
        The root node.

        >>> from orgparse import loads
        >>> root = loads('* Node 1')
        >>> n1 = root[1]
        >>> n1.root is root
        True

        """
        root = self
        while True:
            parent = root.get_parent()
            if not parent:
                return root
            root = parent

    # parser

    @classmethod
    def from_chunk(cls, env, chunk):
        lines,start,end = chunk
        self = cls(env)
        self._lines = lines
        self._start = start
        self._end   = end
        self._names = {}
        self._parse_comments()
        return self

    def is_in(self, line):
        return line >= self._start and line <= self._end

    def _parse_comments(self):
        special_comments = {}
        idx = -1
        for line in self._lines:
            idx += 1
            parsed = parse_comment(line)
            if parsed:
                (key, val) = parsed
                if(key == 'NAME' or key == 'name'):
                    # IAN TODO: Latch position, identify duplicates
                    #           and somehow mark the next object as being named this.
                    # Named objects are very important
                    self._names[val] = { 
                    'row': idx + self._start, 
                    'offset': idx 
                    } 
                special_comments.setdefault(key, []).append(val)
        self._special_comments = special_comments
        # parse TODO keys and store in OrgEnv
        for todokey in ['TODO', 'SEQ_TODO', 'TYP_TODO']:
            for val in special_comments.get(todokey, []):
                self.env.add_todo_keys(*parse_seq_todo(val))

    # misc

    @property
    def level(self):
        """
        Level of this node.

        :rtype: int

        """
        raise NotImplemented

    def _get_tags(self, inher=False):
        """
        Return tags

        :arg bool inher:
            Mix with tags of all ancestor nodes if ``True``.

        :rtype: set

        """
        return set()


    @property
    def tags(self):
        """
        Tag of this and parents node.

        >>> from orgparse import loads
        >>> n2 = loads('''
        ... * Node 1    :TAG1:
        ... ** Node 2   :TAG2:
        ... ''')[2]
        >>> n2.tags == set(['TAG1', 'TAG2'])
        True

        """
        return self._get_tags(inher=True)

    @property
    def shallow_tags(self):
        """
        Tags defined for this node (don't look-up parent nodes).

        >>> from orgparse import loads
        >>> n2 = loads('''
        ... * Node 1    :TAG1:
        ... ** Node 2   :TAG2:
        ... ''')[2]
        >>> n2.shallow_tags == set(['TAG2'])
        True

        """
        return self._get_tags(inher=False)

    def is_root(self):
        """
        Return ``True`` when it is a root node.

        >>> from orgparse import loads
        >>> root = loads('* Node 1')
        >>> root.is_root()
        True
        >>> n1 = root[1]
        >>> n1.is_root()
        False

        """
        return False

    #def __unicode__(self):
    #    return unicode("\n").join(self._lines)

    #if PY3:
    #    __str__ = __unicode__
    #else:
    def __str__(self):
        return "\n".join(self._lines) + "\n"


class OrgRootNode(OrgBaseNode):

    """
    Node to represent a file

    See :class:`OrgBaseNode` for other available functions.

    """

    # getter

    @property
    def level(self):
        return 0

    def get_parent(self, max_level=None):
        return None

    # misc

    def is_root(self):
        return True

    def at(self, line):
        for n in self.env._nodes:
            if(n.is_in(line)):
                return n
        return None

    def node_at(self, index):
        if(index >= 0 and index < len(self.env._nodes)):
            return self.env._nodes[index]
        return None

    def getFile(self):
        return self.file

    def setFile(self, file):
        self.file = file


class OrgNode(OrgBaseNode):

    """
    Node to represent normal org node

    See :class:`OrgBaseNode` for other available functions.

    """

    def __init__(self, *args, **kwds):
        super(OrgNode, self).__init__(*args, **kwds)
        self._heading = None
        self._level = None
        self._tags = None
        self._todo = None
        self._priority = None
        self._properties = {}
        self._property_offsets = {}
        self._drawers = None
        self._blocks = None
        self._dynamicblocks = None
        self._property_drawer_location = None
        self._scheduled = OrgDate(None)
        self._deadline = OrgDate(None)
        self._closed = OrgDate(None)
        self._timestamps = []
        self._clocklist = []
        self._body_lines = []
        self._repeated_tasks = []
        self._body_lines_start = None
        self._customid = None

    @property
    def customid(self):
        return self._customid

    @property
    def property_drawer_location(self):
        return self._property_drawer_location

    def set_property_drawer_location(self, value):
        self._property_drawer_location = value

    @property
    def body_lines_start(self):
        return self._body_lines_start

    @property
    def blocks(self):
        return self._blocks

    @property
    def dynamicblocks(self):
        return self._dynamicblocks

    @property
    def drawers(self):
        return self._drawers

    @property
    def full_heading(self):
        return self._lines[0]


    def get_drawer(self,name):
        for i in self.drawers:
            if i['name'] == name:
                return i
        return None
    # parser

    def _parse_pre(self):
        """Call parsers which must be called before tree structuring"""
        self._parse_heading()
        # FIXME: make the following parsers "lazy"
        ilines = OffsetIter(self._lines)
        #try:
        #    next(ilines)            # skip heading
        #except StopIteration:
        #    return
        # This is creative each parser gets a crack at
        # each line. The problem is that we can't
        # tell the offset from the heading
        gen = self._iparse_sdc(ilines)
        gen = self._iparse_clock(gen, ilines)
        gen = self._iparse_properties(gen, ilines)
        gen = self._iparse_drawers(gen, ilines)
        gen = self._iparse_targets(gen, ilines)
        gen = self._iparse_blocks(gen, ilines)
        gen = self._iparse_repeated_tasks(gen, ilines)
        gen = self._iparse_timestamps(gen, ilines)
        if(self._body_lines_start == None):
            self._body_lines_start = self._start + ilines.offset + 1
        self._body_lines = list(gen)

    def _parse_heading(self):
        heading = self._lines[0]
        (heading, self._level) = parse_heading_level(heading)
        (heading, self._tags) = parse_heading_tags(heading)
        (heading, self._todo) = parse_heading_todos(
            heading, self.env.all_todo_keys)
        (heading, self._priority) = parse_heading_priority(heading)
        self._heading = heading

    # The following ``_iparse_*`` methods are simple generator based
    # parser.  See ``_parse_pre`` for how it is used.  The principle
    # is simple: these methods get an iterator and returns an iterator.
    # If the item returned by the input iterator must be dedicated to
    # the parser, do not yield the item or yield it as-is otherwise.

    def _iparse_sdc(self, ilines):
        """
        Parse SCHEDULED, DEADLINE and CLOSED time tamps.

        They are assumed be in the first line.

        """
        try:
            line = next(ilines)
        except StopIteration:
            return

        for i in range(0,3):
            (scheduled, deadline, closed) = parse_sdc(line)

            if not (scheduled or
                    deadline or
                    closed):
                yield line  # when none of them were found
            else:
                if(scheduled):
                    self._scheduled = scheduled
                if(deadline):
                    self._deadline = deadline
                if(closed):
                    self._closed = closed 
                try:
                    line = next(ilines)
                except StopIteration:
                    return

        for line in ilines:
            yield line

    def _iparse_clock(self, ilines, at):
        self._clocklist = clocklist = []
        for line in ilines:
            try:
                cl = OrgDateClock.from_str(line)
            except:
                print("FAILED PARSING CLOCK({0}): {1}".format(at.offset,line))
            if cl:
                clocklist.append(cl)
            else:
                yield line

    def _iparse_timestamps(self, ilines, at):
        self._timestamps = timestamps = []
        timestamps.extend(OrgDate.list_from_str(self._heading))
        for l in ilines:
            timestamps.extend(OrgDate.list_from_str(l))
            yield l

    def _iparse_properties(self, ilines, at):
        self._properties = properties = {}
        self._property_offsets = poff = {}
        in_property_field = False
        start = 0
        end   = 0
        for line in ilines:
            if in_property_field:
                if line.find(":END:") >= 0:
                    end = self._start + at.offset
                    self._property_drawer_location = (start, end)
                    self.env.properties.append(self._property_drawer_location)
                    in_property_field = False
                    break
                else:
                    (key, val) = parse_property(line)
                    if key:
                        properties.update({key: val})
                        if(key.lower() == "custom_id"):
                            self._customid = (val, at.offset)
                            self.env.customids[val] = (at.offset, self._start)
                        poff.update({key: at.offset})
            elif line.find(":PROPERTIES:") >= 0:
                start = self._start + at.offset
                in_property_field = True
            else:
                yield line
        for line in ilines:
            yield line

    def _iparse_drawers(self, ilines, at):
        self._drawers = []
        drawerName = ""
        in_field = False
        start    = 0
        end      = 0
        for line in ilines:
            m = RE_DRAWER.search(line)
            if in_field:
                if line.find(":END:") >= 0:
                    end = self._start + at.offset
                    loc = (start, end)
                    drw = { "name":drawerName, "loc":loc }
                    self._drawers.append(drw)
                    in_field = False
            elif m != None and m.group(1) != "PROPERTIES" and m.group(1) != "END":
                drawerName = m.group(1)
                start      = self._start + at.offset
                in_field   = True
            else:
                yield line
        for line in ilines:
            yield line

    def _iparse_blocks(self, ilines, at):
        self._blocks = []
        self._dynamicblocks = []
        in_block = False
        in_dynamic_block = False
        start = 0
        end   = 0
        for line in ilines:
            if in_block:
                if line.find("#+END_") >= 0 or line.find("#+end_") >= 0:
                    end = self._start + at.offset
                    blk = (start, end)
                    self._blocks.append(blk)
                    in_block = False
            elif in_dynamic_block:
                if line.find("#+END:") >= 0 or line.find("#+end:") >= 0:
                    end = self._start + at.offset
                    blk = (start, end)
                    self._dynamicblocks.append(blk)
                    in_dynamic_block = False
            elif line.find("#+BEGIN_") >= 0 or line.find("#+begin_") >= 0:
                start = self._start + at.offset
                in_block = True
            elif line.find("#+BEGIN:") >= 0 or line.find("#+begin:") >= 0:
                start = self._start + at.offset
                in_dynamic_block = True
            else:
                yield line
        for line in ilines:
            yield line

    def _iparse_targets(self, ilines, at):
        global RE_TARGETS
        if(not hasattr(self.env,'_targets')):
            self.env._targets = {}
        for line in ilines:
            m = RE_TARGETS.search(line)
            if(m):
                name = m.group('target')
                row  = self._start + at.offset
                col  = m.span('target')
                self.env._targets[name] = {'row': row, 'col': col}
            yield line

    def _iparse_repeated_tasks(self, ilines, at):
        self._repeated_tasks = repeated_tasks = []
        for line in ilines:
            match = self._repeated_tasks_re.search(line)
            if match:
                # FIXME: move this parsing to OrgDateRepeatedTask.from_str
                mdict = match.groupdict()
                done_state = mdict['done']
                todo_state = mdict['todo']
                date = OrgDate.from_str(mdict['date'])
                repeated_tasks.append(
                    OrgDateRepeatedTask(date.start, todo_state, done_state))
            else:
                yield line

    _repeated_tasks_re = re.compile(
        r'''
        \s+ - \s+
        State \s+ "(?P<done> [^"]+)" \s+
        from  \s+ "(?P<todo> [^"]+)" \s+
        \[ (?P<date> [^\]]+) \]''',
        re.VERBOSE)

    # getter

    @staticmethod
    def _get_text(text, format='plain'):
        if format == 'plain':
            return to_plain_text(text)
        elif format == 'raw':
            return text
        else:
            raise ValueError('format={0} is not supported.'.format(format))

    def get_heading(self, format='plain'):
        """
        Return a string of head text without tags and TODO keywords.

        >>> from orgparse import loads
        >>> node = loads('* TODO Node 1').children[0]
        >>> node.get_heading()
        'Node 1'

        It strips off inline markup by default (``format='plain'``).
        You can get the original raw string by specifying
        ``format='raw'``.

        >>> node = loads('* [[link][Node 1]]').children[0]
        >>> node.get_heading()
        'Node 1'
        >>> node.get_heading(format='raw')
        '[[link][Node 1]]'

        """
        return self._get_text(self._heading, format)

    def get_body(self, format='plain'):
        """
        Return a string of body text.

        See also: :meth:`get_heading`.

        """
        return self._get_text(
            '\n'.join(self._body_lines), format) if self._lines else ''

    @property
    def heading(self):
        """Alias of ``.get_heading(format='plain')``."""
        return self.get_heading()

    @property
    def body(self):
        """Alias of ``.get_body(format='plain')``."""
        return self.get_body()

    @property
    def level(self):
        return self._level
        """
        Level attribute of this node.  Top level node is level 1.

        >>> from orgparse import loads
        >>> root = loads('''
        ... * Node 1
        ... ** Node 2
        ... ''')
        >>> (n1, n2) = root.children
        >>> root.level
        0
        >>> n1.level
        1
        >>> n2.level
        2

        """

    @property
    def priority(self):
        """
        Priority attribute of this node.  It is None if undefined.

        >>> from orgparse import loads
        >>> (n1, n2) = loads('''
        ... * [#A] Node 1
        ... * Node 2
        ... ''').children
        >>> n1.priority
        'A'
        >>> n2.priority is None
        True

        """
        return self._priority

    def _get_tags(self, inher=False):
        tags = set(self._tags)
        if inher:
            parent = self.get_parent()
            if parent:
                return tags | parent._get_tags(inher=True)
        return tags


    def add_tag(self, tag):
        if(not tag in self._tags):
            self._tags.append(tag)
            head = self._lines[0].strip()
            if(head.endswith(":")):
                self._lines[0] = head + tag.strip() + ":"
            else:
                self._lines[0] = head + "    :" + tag.strip() + ":"

    # Get a unique locator for this heading
    def get_locator(self):
        heading = self.heading
        cur = self
        while(cur.parent and cur.parent.level > 0):
            cur = cur.parent
            heading = cur.heading + ":" + heading
        return heading

    @property
    def todo(self):
        """
        A TODO keyword of this node if exists or None otherwise.

        >>> from orgparse import loads
        >>> root = loads('* TODO Node 1')
        >>> root.children[0].todo
        'TODO'

        """
        return self._todo

    def update_property(self, key, val):
        # Do we have this property already?
        if(not key in self._properties):
            self._properties[key] = val
            # No property drawer, just add one.
            if(not self._property_drawer_location):
                self._property_drawer_location = (self._start + 1, self._start + 2)
                i = 1
                while(len(self._lines) > i and ("SCHEDULED" in self._lines[i] or "DEADLINE" in self._lines[i])):
                    i += 1
                self._lines.insert(i,   "{0} :PROPERTIES:".format(" " * self._level))
                self._lines.insert(i+1, "{0} :END:".format(" " * self._level))
            # Find property drawer and add this property
            offset = self._property_drawer_location[0] - self._start + 1
            self._lines.insert(offset, "{0} {1}: {2}".format(" " * self.level,key,val))
            self._property_drawer_location = (self._property_drawer_location[0], self._property_drawer_location[1] + 1)
        # We have this property, if it has changed
        # Modify it.
        else:
            offset = self._property_offsets[key]
            self._properties[key] = val
            self._lines[offset] = "{0}  {1}:{2}\n".format(" " * self._level,key,val)


    def get_property(self, key, val=None):
        """
        Return property named ``key`` if exists or ``val`` otherwise.

        :arg str key:
            Key of property.

        :arg val:
            Default value to return.

        """
        return self._properties.get(key, val)

    @property
    def properties(self):
        """
        Node properties as a dictionary.

        >>> from orgparse import loads
        >>> root = loads('''
        ... * Node
        ...   :PROPERTIES:
        ...   :SomeProperty: value
        ...   :END:
        ... ''')
        >>> root.children[0].properties['SomeProperty']
        'value'

        """
        return self._properties

    @property
    def scheduled(self):
        """
        Return scheduled timestamp

        :rtype: a subclass of :class:`orgparse.date.OrgDate`

        >>> from orgparse import loads
        >>> root = loads('''
        ... * Node
        ...   SCHEDULED: <2012-02-26 Sun>
        ... ''')
        >>> root.children[0].scheduled
        OrgDateScheduled((2012, 2, 26))

        """
        return self._scheduled

    @property
    def deadline(self):
        """
        Return deadline timestamp.

        :rtype: a subclass of :class:`orgparse.date.OrgDate`

        >>> from orgparse import loads
        >>> root = loads('''
        ... * Node
        ...   DEADLINE: <2012-02-26 Sun>
        ... ''')
        >>> root.children[0].deadline
        OrgDateDeadline((2012, 2, 26))

        """
        return self._deadline

    @property
    def closed(self):
        """
        Return timestamp of closed time.

        :rtype: a subclass of :class:`orgparse.date.OrgDate`

        >>> from orgparse import loads
        >>> root = loads('''
        ... * Node
        ...   CLOSED: [2012-02-26 Sun 21:15]
        ... ''')
        >>> root.children[0].closed
        OrgDateClosed((2012, 2, 26, 21, 15, 0))

        """
        return self._closed

    @property
    def clock(self):
        """
        Return a list of clocked timestamps

        :rtype: a list of a subclass of :class:`orgparse.date.OrgDate`

        >>> from orgparse import loads
        >>> root = loads('''
        ... * Node
        ...   CLOCK: [2012-02-26 Sun 21:10]--[2012-02-26 Sun 21:15] =>  0:05
        ... ''')
        >>> root.children[0].clock
        [OrgDateClock((2012, 2, 26, 21, 10, 0), (2012, 2, 26, 21, 15, 0))]

        """
        return self._clocklist

    def get_timestamps(self, active=False, inactive=False,
                       range=False, point=False):
        """
        Return a list of timestamps in the body text.

        :type   active: bool
        :arg    active: Include active type timestamps.
        :type inactive: bool
        :arg  inactive: Include inactive type timestamps.
        :type    range: bool
        :arg     range: Include timestamps which has end date.
        :type    point: bool
        :arg     point: Include timestamps which has no end date.

        :rtype: list of :class:`orgparse.date.OrgDate` subclasses


        Consider the following org node:

        >>> from orgparse import loads
        >>> node = loads('''
        ... * Node
        ...   CLOSED: [2012-02-26 Sun 21:15] SCHEDULED: <2012-02-26 Sun>
        ...   CLOCK: [2012-02-26 Sun 21:10]--[2012-02-26 Sun 21:15] =>  0:05
        ...   Some inactive timestamp [2012-02-23 Thu] in body text.
        ...   Some active timestamp <2012-02-24 Fri> in body text.
        ...   Some inactive time range [2012-02-25 Sat]--[2012-02-27 Mon].
        ...   Some active time range <2012-02-26 Sun>--<2012-02-28 Tue>.
        ... ''').children[0]

        The default flags are all off, so it does not return anything.

        >>> node.get_timestamps()
        []

        You can fetch appropriate timestamps using keyword arguments.

        >>> node.get_timestamps(inactive=True, point=True)
        [OrgDate((2012, 2, 23), None, False)]
        >>> node.get_timestamps(active=True, point=True)
        [OrgDate((2012, 2, 24))]
        >>> node.get_timestamps(inactive=True, range=True)
        [OrgDate((2012, 2, 25), (2012, 2, 27), False)]
        >>> node.get_timestamps(active=True, range=True)
        [OrgDate((2012, 2, 26), (2012, 2, 28))]

        This is more complex example.  Only active timestamps,
        regardless of range/point type.

        >>> node.get_timestamps(active=True, point=True, range=True)
        [OrgDate((2012, 2, 24)), OrgDate((2012, 2, 26), (2012, 2, 28))]

        """
        return [
            ts for ts in self._timestamps if
            (((active and ts.is_active()) or
              (inactive and not ts.is_active())) and
             ((range and ts.has_end()) or
              (point and not ts.has_end())))]

    @property
    def datelist(self):
        """
        Alias of ``.get_timestamps(active=True, inactive=True, point=True)``.

        :rtype: list of :class:`orgparse.date.OrgDate` subclasses

        >>> from orgparse import loads
        >>> root = loads('''
        ... * Node with point dates <2012-02-25 Sat>
        ...   CLOSED: [2012-02-25 Sat 21:15]
        ...   Some inactive timestamp [2012-02-26 Sun] in body text.
        ...   Some active timestamp <2012-02-27 Mon> in body text.
        ... ''')
        >>> root.children[0].datelist      # doctest: +NORMALIZE_WHITESPACE
        [OrgDate((2012, 2, 25)),
         OrgDate((2012, 2, 26), None, False),
         OrgDate((2012, 2, 27))]

        """
        return self.get_timestamps(active=True, inactive=True, point=True)

    @property
    def rangelist(self):
        """
        Alias of ``.get_timestamps(active=True, inactive=True, range=True)``.

        :rtype: list of :class:`orgparse.date.OrgDate` subclasses

        >>> from orgparse import loads
        >>> root = loads('''
        ... * Node with range dates <2012-02-25 Sat>--<2012-02-28 Tue>
        ...   CLOCK: [2012-02-26 Sun 21:10]--[2012-02-26 Sun 21:15] => 0:05
        ...   Some inactive time range [2012-02-25 Sat]--[2012-02-27 Mon].
        ...   Some active time range <2012-02-26 Sun>--<2012-02-28 Tue>.
        ...   Some time interval <2012-02-27 Mon 11:23-12:10>.
        ... ''')
        >>> root.children[0].rangelist     # doctest: +NORMALIZE_WHITESPACE
        [OrgDate((2012, 2, 25), (2012, 2, 28)),
         OrgDate((2012, 2, 25), (2012, 2, 27), False),
         OrgDate((2012, 2, 26), (2012, 2, 28)),
         OrgDate((2012, 2, 27, 11, 23, 0), (2012, 2, 27, 12, 10, 0))]

        """
        return self.get_timestamps(active=True, inactive=True, range=True)

    def has_date(self):
        """
        Return ``True`` if it has any kind of timestamp
        """
        return (self.scheduled or
                self.deadline or
                self.datelist or
                self.rangelist)

    @property
    def repeated_tasks(self):
        """
        Get repeated tasks marked DONE in a entry having repeater.

        :rtype: list of :class:`orgparse.date.OrgDateRepeatedTask`

        >>> from orgparse import loads
        >>> node = loads('''
        ... * TODO Pay the rent
        ...   DEADLINE: <2005-10-01 Sat +1m>
        ...   - State "DONE"  from "TODO"  [2005-09-01 Thu 16:10]
        ...   - State "DONE"  from "TODO"  [2005-08-01 Mon 19:44]
        ...   - State "DONE"  from "TODO"  [2005-07-01 Fri 17:27]
        ... ''').children[0]
        >>> node.repeated_tasks            # doctest: +NORMALIZE_WHITESPACE
        [OrgDateRepeatedTask((2005, 9, 1, 16, 10, 0), 'TODO', 'DONE'),
         OrgDateRepeatedTask((2005, 8, 1, 19, 44, 0), 'TODO', 'DONE'),
         OrgDateRepeatedTask((2005, 7, 1, 17, 27, 0), 'TODO', 'DONE')]
        >>> node.repeated_tasks[0].before
        'TODO'
        >>> node.repeated_tasks[0].after
        'DONE'

        Repeated tasks in ``:LOGBOOK:`` can be fetched by the same code.

        >>> node = loads('''
        ... * TODO Pay the rent
        ...   DEADLINE: <2005-10-01 Sat +1m>
        ...   :LOGBOOK:
        ...   - State "DONE"  from "TODO"  [2005-09-01 Thu 16:10]
        ...   - State "DONE"  from "TODO"  [2005-08-01 Mon 19:44]
        ...   - State "DONE"  from "TODO"  [2005-07-01 Fri 17:27]
        ...   :END:
        ... ''').children[0]
        >>> node.repeated_tasks            # doctest: +NORMALIZE_WHITESPACE
        [OrgDateRepeatedTask((2005, 9, 1, 16, 10, 0), 'TODO', 'DONE'),
         OrgDateRepeatedTask((2005, 8, 1, 19, 44, 0), 'TODO', 'DONE'),
         OrgDateRepeatedTask((2005, 7, 1, 17, 27, 0), 'TODO', 'DONE')]

        See: `(info "(org) Repeated tasks")
        <http://orgmode.org/manual/Repeated-tasks.html>`_

        """
        return self._repeated_tasks


def parse_lines(lines, filename, todos, dones):
    env = OrgEnv(filename=filename, todos=todos, dones=dones)
    # parse into node of list (environment will be parsed)
    nodelist = list(env.from_chunks(lines_to_chunks(lines)))
    # parse headings (level, TODO, TAGs, and heading)
    nodelist[0]._index = 0
    for (i, node) in enumerate(nodelist[1:], 1):   # nodes except root node
        node._index = i
        node._parse_pre()
    env._nodes = nodelist
    return nodelist[0]  # root


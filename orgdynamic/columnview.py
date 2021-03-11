import sublime
import OrgExtended.orgdb as db
import OrgExtended.orgparse.date as d
import OrgExtended.orgutil.util as util
import re
import os


def get_level(params):
	level = 2
	if('maxlevel' in params):
		level = int(params['maxlevel'])
	if(level < 2):
		level = 2
	return level

def handle_item(params,n,defs,output,depth,maxdepth):
	if(maxdepth > 0 and depth > maxdepth):
		return
	if('hlines' in params):
		v = params['hlines']
		if(v == 't'):
			output.append("|-")
		elif(v != 'nil' and v != ""):
			v = int(v)
			if(depth <= v):
				output.append("|-")
	out = "|"
	for d in defs:
		out += str(d.GetCellValue(n,params)) + "|"
	ok = True
	if('exclude-tags' in params):
		exclude = util.ToList(params['exclude-tags'])
		for e in exclude:
			if(e in n.tags):
				ok = False
				break
	if(ok):
		output.append(out)
	for c in n.children:
		handle_item(params,c,defs,output,depth+1,maxdepth)

def handle_headings(defs,output):
	out = "|"
	for d in defs:
		out += d.Heading() + "|"
	output.append(out)

class ColumnHandler:
	def Setup(self,width,propName,heading,summary):
		self.width = width
		self.name = propName
		if(heading):
			self.heading = heading
		else:
			self.heading = propName
		self.summary = summary

	def Heading(self):
		return self.heading

class ItemHandler(ColumnHandler):
	def GetCellValue(self,n,params):
		indent = ""
		if('indent' in params):
			idt = params['indent']
			if(idt and idt == 't'):
				indent = '..' * (n.level-1)
		return indent + n.heading

class DeadlineHandler(ColumnHandler):
	def GetCellValue(self,n,params):
		return n.deadline.format_datetime_str() if n.deadline else ""

class ClosedHandler(ColumnHandler):
	def GetCellValue(self,n,params):
		return n.closed.format_datetime_str() if n.closed else ""

class ScheduledHandler(ColumnHandler):
	def GetCellValue(self,n,params):
		return n.scheduled.format_datetime_str() if n.scheduled else ""

class TimestampHandler(ColumnHandler):
	def GetCellValue(self,n,params):
		ts = n.get_timestamps(active=True, inactive=False, range=True, point=True)
		if(ts and len(ts) >= 1):
			return ts[0].format_datetime_str()
		return ""

class IATimestampHandler(ColumnHandler):
	def GetCellValue(self,n,params):
		ts = n.get_timestamps(active=False, inactive=True, range=True, point=True)
		if(ts and len(ts) >= 1):
			return ts[0].format_datetime_str()
		return ""

class PriorityHandler(ColumnHandler):
	def GetCellValue(self,n,params):
		return n.priority if n.priority else ""

class TodoHandler(ColumnHandler):
	def GetCellValue(self,n,params):
		return n.todo if n.todo else ""

class AllTagsHandler(ColumnHandler):
	def GetCellValue(self,n,params):
		return ' '.join(n.tags) if n.tags else ""

class TagsHandler(ColumnHandler):
	def GetCellValue(self,n,params):
		return ' '.join(n.shallow_tags) if n.shallow_tags else ""

class FilenameHandler(ColumnHandler):
	def GetCellValue(self,n,params):
		return os.path.basename(n.env.filename)

class PropertyHandler(ColumnHandler):
	def GetCellValue(self,n,params):
		v = n.get_property(self.name,None)
		if(not v):
			v = n.get_property(self.name.upper(),None)
			if(not v):
				v = n.get_property(self.name.lower(),"")
		return v

special_registry = {
    #‘ITEM’	The headline of the entry.
	"ITEM":      ItemHandler,
    #‘PRIORITY’	The priority of the entry, a string with a single letter.
	"PRIORITY":  PriorityHandler,
    #‘CLOSED’	When was this entry closed?
	"CLOSED":    ClosedHandler,
    #‘SCHEDULED’	The scheduling timestamp.
	"SCHEDULED": ScheduledHandler,
    #‘TODO’	The TODO keyword of the entry.
	"TODO":      TodoHandler,
     #‘DEADLINE’	The deadline timestamp.
	"DEADLINE":  DeadlineHandler,
     #‘ALLTAGS’	All tags, including inherited ones.
	"ALLTAGS":   AllTagsHandler,
     #‘FILE’	The filename the entry is located in.
	"FILE":      FilenameHandler,
     #‘TAGS’	The tags defined directly in the headline.
	"TAGS":      TagsHandler,
	 #‘TIMESTAMP’	The first keyword-less timestamp in the entry.
	"TIMESTAMP":    TimestampHandler,
     #‘TIMESTAMP_IA’	The first inactive timestamp in the entry.
	"TIMESTAMP_IA": IATimestampHandler,
}

#‘BLOCKED’	t if task is currently blocked by children or siblings.
#‘CATEGORY’	The category of an entry.
#‘CLOCKSUM’	The sum of CLOCK intervals in the subtree. org-clock-sum
#           must be run first to compute the values in the current buffer.
#‘CLOCKSUM_T’	The sum of CLOCK intervals in the subtree for today.
#               org-clock-sum-today must be run first to compute the
#               values in the current buffer.

#%[WIDTH]PROPERTY[(TITLE)][{SUMMARY-TYPE}]
RE_PARSER = re.compile(r"[%](?P<width>[0-9]+)?(?P<prop>[a-zA-Z][a-zA-Z0-9_-]+)([(](?P<heading>([a-zA-Z0-9 +-]|\s)+)[)])?(?P<summary>[^ ())]+)?")
def get_column_definitions(f):
	columns = f.org.list_comment("COLUMNS",[r"%70ITEM(Task)",r"%17Effort(Effort)"])
	h = []
	for item in columns:
		m = RE_PARSER.search(item)
		if(m):
			width = m.group('width')
			if(width and width != ""):
				width = int(width)
			else:
				width = 0
			prop  = m.group('prop')
			heading = m.group('heading')
			summary = m.group('summary')
			if(prop in special_registry):
				cfactory = special_registry[prop]
			else:
				cfactory = PropertyHandler
			v = cfactory()
			v.Setup(width,prop,heading,summary)
			h.append(v)
	return h

def Execute(view, params):
	maxdepth = 0
	id = "global"
	# How far down the tree do we allow?
	print("MAX: " + str(params))
	if('maxdepth' in params):
		maxdepth = int(params['maxdepth'])
	# This is the most crucial parameter it defines how
	# we will process nodes.
	if('id' in params):
		id = params['id']
	# We accumulate output in here line by line for insertion
	# into the main buffer.
	output = []
	# By default we operate in the current file off the current view
	# Look it up in the DB. This will also reload it if it is dirty.
	file = db.Get().FindInfo(view)
	if(file):
		defs = get_column_definitions(file)
		r = file.org
		# Local we search up till we find the node parent that is not the root
		if(id == 'local'):
			node = db.Get().AtInView(view)
			if(node):
				while(node and node.parent and node.parent.parent):
					node = node.parent
				r = node
		# Operate on all children of the root (default)
		elif(id == 'global'):
			pass
		# Operate on the root of another file in the db
		elif('file:' in id):
			files = id.split(':')
			file = db.Get().FindFileByFilename(files[1].strip())
			r = file.org
			pass
		# Operate on a node marked with an ID or CUSTOM_ID
		# ONLY if found in the DB.
		else:
			r = db.Get().FindNodeByAnyId(id)
			print(str(r))
			pass

		# Output the headings of our table based on the fields and handlers
		# we found in our COLUMNS definition.
		handle_headings(defs,output)
		# If we had a root, run over it and process it's children
		# building up our output array.
		if(r):
			for n in r.children:
				handle_item(params,n,defs,output,1,maxdepth)
	# Did we get some output? return it
	if(len(output) > 0):
		return output
	# Nope add a generic error so we know we failed getting output at all...
	output.append("|NO COLUMNVIEW DATA|")
	return output

def PostExecute(view, params, region):
	# We wrote our data to the buffer, get the TableEditor to
	# align our data for us.
	row,col = view.rowcol(view.sel()[0].begin())
	view.sel().clear()
	view.sel().add(view.text_point(row+1,col))
	view.run_command("table_editor_next_field")

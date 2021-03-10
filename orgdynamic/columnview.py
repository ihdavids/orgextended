import sublime
import OrgExtended.orgdb as db
import OrgExtended.orgparse.date as d
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
		out += str(d.GetCellValue(n)) + "|"
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
	def GetCellValue(self,n):
		return n.heading

class DeadlineHandler(ColumnHandler):
	def GetCellValue(self,n):
		return n.deadline.format_datetime_str() if n.deadline else ""

class ClosedHandler(ColumnHandler):
	def GetCellValue(self,n):
		return n.closed.format_datetime_str() if n.closed else ""

class ScheduledHandler(ColumnHandler):
	def GetCellValue(self,n):
		return n.scheduled.format_datetime_str() if n.scheduled else ""

class TimestampHandler(ColumnHandler):
	def GetCellValue(self,n):
		ts = n.get_timestamps(active=True, inactive=False, range=True, point=True)
		if(ts and len(ts) >= 1):
			return ts[0].format_datetime_str()
		return ""

class IATimestampHandler(ColumnHandler):
	def GetCellValue(self,n):
		ts = n.get_timestamps(active=False, inactive=True, range=True, point=True)
		if(ts and len(ts) >= 1):
			return ts[0].format_datetime_str()
		return ""

class PriorityHandler(ColumnHandler):
	def GetCellValue(self,n):
		return n.priority if n.priority else ""

class TodoHandler(ColumnHandler):
	def GetCellValue(self,n):
		return n.todo if n.todo else ""

class AllTagsHandler(ColumnHandler):
	def GetCellValue(self,n):
		return ' '.join(n.tags) if n.tags else ""

class TagsHandler(ColumnHandler):
	def GetCellValue(self,n):
		return ' '.join(n.shallow_tags) if n.shallow_tags else ""

class FilenameHandler(ColumnHandler):
	def GetCellValue(self,n):
		return os.path.basename(n.env.filename)

class PropertyHandler(ColumnHandler):
	def GetCellValue(self,n):
		v = n.get_property(self.name,None)
		if(not v):
			v = n.get_property(self.name.upper(),None)
			if(not v):
				v = n.get_property(self.name.lower(),"")
		return v

special_registry = {
	"ITEM":      ItemHandler,
	"PRIORITY":  PriorityHandler,
	"CLOSED":    ClosedHandler,
	"SCHEDULED": ScheduledHandler,
	"TODO":      TodoHandler,
	"DEADLINE":  DeadlineHandler,
	"ALLTAGS":   AllTagsHandler,
	"FILE":      FilenameHandler,
	"TAGS":      TagsHandler,
	"TIMESTAMP":    TimestampHandler,
	"TIMESTAMP_IA": IATimestampHandler,
}

#‘ALLTAGS’	All tags, including inherited ones.
#‘BLOCKED’	t if task is currently blocked by children or siblings.
#‘CATEGORY’	The category of an entry.
#‘CLOCKSUM’	The sum of CLOCK intervals in the subtree. org-clock-sum
#must be run first to compute the values in the current buffer.
#‘CLOCKSUM_T’	The sum of CLOCK intervals in the subtree for today.
#org-clock-sum-today must be run first to compute the
#values in the current buffer.
#‘CLOSED’	When was this entry closed?
#‘DEADLINE’	The deadline timestamp.
#‘FILE’	The filename the entry is located in.
#‘ITEM’	The headline of the entry.
#‘PRIORITY’	The priority of the entry, a string with a single letter.
#‘SCHEDULED’	The scheduling timestamp.
#‘TAGS’	The tags defined directly in the headline.
#‘TIMESTAMP’	The first keyword-less timestamp in the entry.
#‘TIMESTAMP_IA’	The first inactive timestamp in the entry.
#‘TODO’	The TODO keyword of the entry.

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
	if('maxdepth' in params):
		maxdepth = int(params['maxdepth'])
	if('id' in params):
		id = params['id']
	print("FILE: " + id)
	output = []
	file = db.Get().FindInfo(view)
	if(file):
		defs = get_column_definitions(file)
		r = file.org
		if(id == 'local'):
			node = db.Get().AtInView(view)
			if(node):
				while(node and node.parent and node.parent.parent):
					node = node.parent
				r = node
		elif(id == 'global'):
			pass
		elif('file:' in id):
			files = id.split(':')
			file = db.Get().FindFileByFilename(files[1].strip())
			r = file.org
			pass
		else:
			r = db.Get().FindNodeByAnyId(id)
			print(str(r))
			pass


		handle_headings(defs,output)	
		if(r):
			for n in r.children:
				handle_item(params,n,defs,output,1,maxdepth)
	if(len(output) > 0):
		return output
	output.append("|NO COLUMNVIEW DATA|")
	return output

def PostExecute(view, params, region):
	row,col = view.rowcol(view.sel()[0].begin())
	view.sel().clear()
	view.sel().add(view.text_point(row+1,col))
	view.run_command("table_editor_next_field")

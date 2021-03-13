import sublime
import OrgExtended.orgdb as db
import OrgExtended.orgparse.date as d

# This is a placeholder clocktable dynamic block
def setup_heading(output,level):
	title = "|Heading|Time|" + ('|' * (level-1))
	output.append(title)
	output.append("|-")

def handle_heading(skip, node, clevel, level):
	#print("H: " + node.heading)
	skipstr = ""
	if(skip > 0):
		skipstr = ("|" * skip)
	clevelskip = ""
	if(clevel > 0):
		clevelskip = "|" * clevel
	difflevel = level - clevel - 1
	difflevelskip = ""
	if(difflevel > 0):
		difflevelskip = "|" * difflevel
	hindent = ""
	if(clevel > 0):
		hindent = r'\_'
	if(clevel > 1):
		hindent = hindent + ('__' * (clevel - 1))
	if(hindent != ""):
		hindent = hindent + " "
	return "{0}|{1}|{2}{3}{4}|".format(skipstr,hindent + node.heading,clevelskip,d.OrgDate.format_duration(node.duration()),difflevelskip)

def handle_subheading(output, skip, view, node, params, clevel, level):
	output.append(handle_heading(skip, node, clevel, level))
	for c in node.children:
		handle_subheading(output, skip, view, c, params, clevel+1, level)


def handle_subtree(view, params, level):
	node = db.Get().AtInView(view)	
	output = []
	setup_heading(output, level)
	output.append(handle_heading(0, node, 0, level))
	for c in node.children:
		handle_subheading(output, 0, view, c, params, 1, level)
	return output

def get_level(params):
	level = params.GetInt('maxlevel',2)
	if(level < 2):
		level = 2
	return level

def Execute(view, params):
	level = get_level(params)
	if(params.Get('scope','subtree') == 'subtree'):
		return handle_subtree(view, params, level)
	else:
		print(params['scope'] + " is not implemented")

	file = db.Get().FindInfo(view)
	if(file):
		r = file.org
		for n in r.children:
			n.duration()	
	output = []
	output.append("|Heading|Time|")
	output.append("|-")
	output.append("|A|B|")
	return output

def PostExecute(view, params, region):
	row,col = view.rowcol(view.sel()[0].begin())
	view.sel().clear()
	view.sel().add(view.text_point(row+1,col))
	view.run_command("table_editor_next_field")
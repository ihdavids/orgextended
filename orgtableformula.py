import sublime
import sublime_plugin
import datetime
import re
from pathlib import Path
import os
import fnmatch
import OrgExtended.orgparse.node as node
import OrgExtended.orgutil.util as util
import logging
import sys
import traceback 
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
import OrgExtended.pymitter as evt
import OrgExtended.orginsertselected as ins
import OrgExtended.simple_eval as simpev
import OrgExtended.orgextension as ext
import math
import random
import ast
import operator as op
import subprocess

random.seed()
RE_PRINTFSTYLE = re.compile(r"(?P<formatter>[%][0-9]*\.[0-9]+f)")
RE_ISCOMMENT = re.compile(r"^\s*[#][+]")
MAX_STRING_LENGTH = 100000
MAX_COMPREHENSION_LENGTH = 10000
MAX_POWER = 4000000  # highest exponent

log = logging.getLogger(__name__)

def isTable(view):
    names = view.scope_name(view.sel()[0].end())
    return 'orgmode.table' in names

def isTableFormula(view):
    names = view.scope_name(view.sel()[0].end())
    return 'orgmode.tblfm' in names

class TableCache:
    def __init__(self):
        self.cachedTables = []
        self.change_count = -1

    def _FindTable(self,row,view):
        if(self.change_count >= view.change_count()):
            for t in self.cachedTables:
                if row >= t[0][0] and row <= t[0][1]:
                    return t[1]
        else:
            self.change_count = view.change_count()
            self.cachedTables = []
        return None

    def GetTable(self,view,at=None):
        row = view.curRow()
        if(at != None):
            row,_ = view.rowcol(at)
        td = self._FindTable(row,view)
        if(not td):
            td = create_table(view,at)
            self.cachedTables.append(((td.start,td.end),td))
        return td

tableCache = TableCache()

def plot_write_table_data_to(table,f,r,c,first=False):
    txt = table.GetCellText(r,c).strip()
    if(first):
        if(r == 1 and (table.StartRow() != 1 or not isNumeric(txt))):
            f.write("#")
    else:
        f.write("\t")
    f.write(txt)

def plot_build_data_file(table,params):
    filename = params['_filename']
    datafile = os.path.join(params['_sourcepath'],os.path.splitext(filename)[0]+".data")
    params['_datafile'] = datafile
    # Maybe skip the first column if it has lables
    startCol = 1
    for r in range(1,table.Height() + 1):
        if(not isNumeric(table.GetCellText(r,1).strip())):
            startCol += 1
            break
    ind = startCol
    if('ind' in params):
        if(startCol > 1):
            ind = int(params['ind'])+1
        else:
            ind = int(params['ind'])
    usingVals = range(startCol, table.Width()+1)
    if('deps' in params):
        deps = params['deps']
        t = deps.replace('(',"").replace(")","")
        ts = re.split(r'\s+',t)
        usingVals = []
        for x in ts:
            if(x.strip() != ""):
                usingVals.append(int(x.strip()))

    with open(datafile,"w") as f:
        for r in range(1,table.Height()+1):
            c = ind
            plot_write_table_data_to(table,f,r,c,first=True)
            # Eventually we will need to do this with a user specified range.
            for c in usingVals:
                if(c != ind):
                    plot_write_table_data_to(table,f,r,c)
            f.write("\n")
    return datafile

def plot_param(p,n,defaultVal):
    v = defaultVal
    if(n in p):
        v = p[n]
    return v

def plot_quote(v):
    if not "\"" in v:
        v = "\"" + v + "\""
    return v

def find_in_using(idx,usings):
    for i in range(0,len(usings)):
        if(usings[i] == idx):
            return i + 2

def plot_build_command_file(table, params):
    filename = params['_filename']
    gpltfile = os.path.join(params['_sourcepath'],os.path.splitext(filename)[0]+".gplt")
    params['_gpltfile'] = gpltfile
    dataFile = params['_datafile']
    filename = params['_filename']
    withstmt = " notitle "
    usingVals = []
    with open(gpltfile,"w") as f:
        title = plot_quote(plot_param(params,'title',"Table Data"))
        f.write('set title ' + title + "\n")
        f.write('set term png \n')
        f.write('set output ' + plot_quote(filename.replace('\\','\\\\')) + "\n")
        if('deps' in params):
            deps = params['deps']
            t = deps.replace('(',"").replace(")","")
            ts = re.split(r'\s+',t)
            for x in ts:
                if(x.strip() != ""):
                    usingVals.append(int(x.strip()))
        ind = 1
        if('set' in params):
            for x in params['set']:
                f.write('set ' + x + '\n')
        for x,y in params.items():
            if(x == "with"):
                if(y == 'histograms'):
                    count = 1
                    first = True
                    for i in usingVals:
                        count = count + 1
                        seriesTitle = table.GetCellText(1,i).strip()
                        if(seriesTitle != ""):
                            seriesTitle = "\"" + seriesTitle + "\""
                        else:
                            seriesTitle = " \"col "+str(i)+"\""
                        if(not first):
                            withstmt += ",\"\" using " + str(count) + " with histograms title " + seriesTitle + " "
                        else:
                            withstmt = " using " + str(count) + " with histograms title " + seriesTitle + " "
                if(y == 'candlesticks'):
                    count = 0
                    for idx in range(0,len(usingVals),4):
                        count = count*4 + ind + 1
                        i = usingVals[idx]
                        seriesTitle = table.GetCellText(1,i).strip()
                        if(seriesTitle != ""):
                            seriesTitle = "\"" + seriesTitle + "\""
                        else:
                            seriesTitle = "\"series"+str(i)+"\""
                        withstmt = " using " + str(ind)+":"+str(count)+":"+str(count+1)+":"+str(count+2)+":"+str(count+3) + " with "+y+" title " + seriesTitle + " "
                else:
                    count = 1
                    first = True
                    for i in usingVals:
                        count = count + 1
                        seriesTitle = table.GetCellText(1,i).strip()
                        if(seriesTitle != ""):
                            seriesTitle = "\"" + seriesTitle + "\""
                        else:
                            seriesTitle = "\"series"+str(i)+"\""
                        if(not first):
                            withstmt += ",\"\" using " + str(ind)+":"+str(count) + " with "+y+" title " + seriesTitle + " "
                        else:
                            withstmt = " using " + str(ind)+":"+str(count) + " with "+y+" title " + seriesTitle + " "
                        first = False
            #elif not x.startswith("_") and x != 'set':
            #    f.write(x + " " + y + "\n")
        f.write('plot ' + plot_quote(dataFile.replace('\\','\\\\')) + withstmt + '\n')
        pass

def plot_get_params(table,view):
    dt = datetime.datetime.now()
    sourcepath = os.path.dirname(view.file_name())
    filename = "plot_" + str(dt.year) + "_" + str(dt.month) + "_" + str(dt.day) + "_" + str(dt.time().hour) + "_" + str(dt.time().minute) + "_" + str(dt.time().second) + ".png"
    params = {}
    params['_filename'] = os.path.join(sourcepath,filename)
    params['_sourcepath'] = sourcepath
    row = view.curRow()
    node = db.Get().At(view, row)
    if(node):
        plot = " " + node.get_comment('PLOT',"")[0]
        #print(plot)
        ps     = re.split(r'\s+[a-zA-Z][a-zA-Z0-9]+[:]',plot) 
        ps = ps[1:]
        keys   = [m.group(0) for m in re.finditer(r'\s+[a-zA-Z][a-zA-Z0-9]+[:]',plot)]
        #keys   = [m.group(0) for m in re.finditer(r'(^|\s+)[^: ]+[:]',plot)]
        for i in range(0,len(keys)):
            k = keys[i].strip()
            if(k.endswith(':')):
                k = k[:-1]
            v = ps[i].strip()
            #print("K: " + str(k))
            #print("V: " + str(v))
            if(k == 'set'):
                if(not 'set' in params):
                    params['set'] = []
                params['set'].append(v.replace("\"",""))
                continue
            if(k == 'output'):
                filename = v
                sourcepath = os.path.dirname(filename)
                if(len(sourcepath) > 2):
                    params['_sourcepath'] = sourcepath
                    params['_filename'] = filename
                else:
                    params['_filename'] = os.path.join(params['_sourcepath'],filename)
                continue
            else:
                params[k] = v
            continue
            for m in RE_FN_MATCH.finditer(item):
                k = m.group(1).strip()
                v = m.group(2).strip()
                print("K: " + str(k))
                print("V: " + str(v))
                if(k == 'set'):
                    if(not 'set' in params):
                        params['set'] = []
                    params['set'].append(v)
                if(k == 'output'):
                    filename = v
                    sourcepath = os.path.dirname(filename)
                    if(len(sourcepath) > 2):
                        params['_sourcepath'] = sourcepath
                        params['_filename'] = filename
                    else:
                        params['_filename'] = os.path.join(params['_sourcepath'],filename)
                else:
                    params[k] = v
                    print("PPP: " + str(params))
            continue
            its = item.split(':')
            if(len(its) == 2):
                if(its[0] == 'set'):
                    if(not 'set' in params):
                        params['set'] = []
                    params['set'].append(its[1])
                if(its[0] == 'output'):
                    filename = its[1]
                    sourcepath = os.path.dirname(filename)
                    if(len(sourcepath) > 2):
                        params['_sourcepath'] = sourcepath
                        params['_filename'] = its[1]
                    else:
                        params['_filename'] = os.path.join(params['_sourcepath'],its[1])
                else:
                    params[its[0]] = its[1]
    print(str(params))
    return params

RE_SRC_BLOCK = re.compile(r"^\s*\#\+(BEGIN_SRC|begin_src)\s+(?P<name>[^: ]+)\s*")
RE_RESULTS = re.compile(r"^\s*\#\+(RESULTS|results)[:]\s*$")
RE_HEADING = re.compile(r"^[*]+\s+")
RE_PROPERTY_DRAWER = re.compile(r"^\s*[:][a-zA-Z0-9]+[:]\s*$")
RE_BLOCK = re.compile(r"^\s*\#\+(BEGIN_|begin_)[a-zA-Z]+\s+")
RE_IS_BLANK_LINE = re.compile(r"^\s*$")
def plot_find_results(table,view):
    row = view.curRow()
    node = db.Get().At(view, row)
    if(node):
        row              = table.end + 1
        fileEndRow,_     = view.rowcol(view.size())
        inResults        = False
        inPropertyDrawer = False
        inBlock          = False
        startResults     = None
        for rw in range(row, fileEndRow):
            line = view.substr(view.line(view.text_point(rw,0)))
            if(not inResults and RE_RESULTS.search(line)):
                startResults = rw
                inResults = True
                continue
            # A new heading ends the results.
            if(RE_HEADING.search(line) or RE_PROPERTY_DRAWER.search(line) or RE_BLOCK.search(line)):
                if(inResults):
                    table.resultsRegion = sublime.Region(view.text_point(startResults,0),view.text_point(rw,0)-1)
                    return True
                else:
                    break
            if(inResults and RE_IS_BLANK_LINE.search(line)):
                table.resultsRegion = sublime.Region(view.text_point(startResults,0),view.text_point(rw,0)-1)
                return True
        # We just hit the end of the file.
        if(inResults):
            table.resultsRegion = sublime.Region(view.text_point(startResults,0),view.text_point(fileEndRow,0))
            return True
        # We hit the end of the file and didn't find a results tag.
        # We need to make one.
        if(not inResults):
            table.resultsRegion = sublime.Region(view.text_point(table.end+1,0),view.text_point(table.end+1,0))
            return True

def plot_table_command(table,view):
    # First get parameters
    ps = plot_get_params(table,view)
    # Next build the data file
    datafile = plot_build_data_file(table,ps)
    # Next build the plot command file
    plot_build_command_file(table,ps)
    # Shell out to gnu plot
    plotcmd = sets.Get("gnuplot",r"C:\Program Files\gnuplot\bin\gnuplot.exe")
    output = ps['_filename']
    outpath    = os.path.dirname(output)
    sourcepath = os.path.dirname(view.file_name())
    commandLine = [plotcmd, "-c", ps['_gpltfile'] ]
    #print(str(commandLine))
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    except:
        startupinfo = None
    cwd = os.path.join(sublime.packages_path(),"User") 
    popen = subprocess.Popen(commandLine, universal_newlines=True, cwd=cwd, startupinfo=startupinfo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (o,e) = popen.communicate()
    print("Plotting data from table:")
    print(str(o))
    print(str(e))
    if(os.path.exists(ps['_datafile'])):
       os.remove(ps['_datafile']) 
    if(os.path.exists(ps['_gpltfile'])):
       os.remove(ps['_gpltfile']) 
    #convertFile = os.path.join(outpath,os.path.splitext(os.path.basename(cmd.filename))[0] + ".png")
    #destFile    = os.path.join(sourcepath,output)
    #copyfile(convertFile, destFile)

    #print(str(os.path.basename(cmd.sourcefile)))
    #print(str(os.path.splitext(cmd.filename)))
    #print(str(os.path.splitext(cmd.sourcefile)))
    #destFile = os.path.relpath(destFile, sourcepath)
    o = "#+RESULTS:\n[[file:" + output.replace("\\","/") + "]]"
    plot_find_results(table,view)
    view.run_command("org_internal_replace", {"start": table.resultsRegion.begin(), "end": table.resultsRegion.end(), "text": o})
    print(o)
    #return o.split('\n') + e.split('\n')



def insert_file_data(indentDepth, data, view, edit, onDone=None, replace=False):
    # figure out what our separator is.
    # replace the separator with |
    indent = (" " * indentDepth) + " "
    lines = data.split('\n')
    separator = ','
    possibles = {",": [], ";": [], "\t": [], " ": []}
    for l in lines:
        if(l.strip() == ""):
            continue
        for k,v in possibles.items():
            v.append(l.count(k))
    vars = {}
    for k,d in possibles.items():
        s = sum(d) 
        mean = s / len(d)
        #print("MEAN: " + str(mean) + " SEP: [" + k + "]")
        if(mean > 0):
            variance = math.sqrt(sum([ (x-mean)*(x-mean) for x in d ]) / len(d))
            vars[k] = variance
    #print(str(vars))
    #print(str(possibles))
    separator = min(vars, key=vars.get) 
    log.info("SEPARATOR CHOSEN: " + separator)
    data = ""
    for l in lines:
        if(l.strip() == ""):
            continue
        data += indent + '|' + l.strip().replace(separator,'|') + '|\n'
    if(replace):
        view.run_command("org_internal_replace", {"start": view.sel()[0].begin(), "end": view.sel()[0].end(), "text": data, "onDone": onDone})
    else:
        view.run_command("org_internal_insert", {"location": view.sel()[0].begin(), "text": data, "onDone": onDone})


class OrgConvertSelectionToTableCommand(sublime_plugin.TextCommand):
    def OnDone(self):
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(self.pos.begin() +1, self.pos.begin()+1))
        self.view.run_command('table_editor_next_field')
        evt.EmitIf(self.onDone)

    def run(self, edit, onDone=None):
        self.edit = edit
        self.onDone = onDone
        self.pos = self.view.sel()[0]
        curNode = db.Get().AtInView(self.view)
        level = 1
        if(None != curNode):
            level = curNode.level
        fileData = self.view.substr(self.view.sel()[0])
        if(len(fileData) > 6):
            insert_file_data(level,fileData,self.view, self.edit, evt.Make(self.OnDone), True)

table_phantoms = []

class OrgHideTableRowsCommand(sublime_plugin.TextCommand):
    def OnDone(self):
        evt.EmitIf(self.onDone)
    def run(self, edit, onDone=None):
        self.onDone = onDone
        for f in table_phantoms:
            self.view.erase_phantoms(f)
        self.OnDone()


class OrgShowTableRowsCommand(sublime_plugin.TextCommand):
    def OnDone(self):
        evt.EmitIf(self.onDone)

    def ToRomanNumeral(self,input):
        if not 0 < input < 4000:
            raise ValueError("Argument must be between 1 and 3999")
        ints = (1000, 900,  500, 400, 100,  90, 50,  40, 10,  9,   5,  4,   1)
        nums = ('M',  'CM', 'D', 'CD','C', 'XC','L','XL','X','IX','V','IV','I')
        result = []
        for i in range(len(ints)):
            count = int(input / ints[i])
            result.append(nums[i] * count)
            input -= ints[i] * count
        return ''.join(result)

    def RowToCellRow(self,r):
        for i in range(1,len(self.td.lineToRow)+1):
            if(self.td.lineToRow[i] == r):
                return str(i)
        count = 0;
        for h in self.td.hlines:
            if h == r:
                return self.ToRomanNumeral(count+1)
            ++count
        return "U"
    def run(self, edit, onDone=None):
        self.onDone = onDone
        self.td = create_table(self.view)
        if(self.td):
            hline = self.td.start-1
            if(self.td.hlines and len(self.td.hlines) > 0):
                hline = self.td.hlines[0]
            line = self.view.line(self.view.text_point(self.td.start,0))
            indent = self.view.substr(line).find("|")
            for r in range(self.td.start,self.td.end+1):
                pt = self.view.text_point(r,indent)
                region = sublime.Region(pt,pt)
                idx = self.RowToCellRow(r)
                body = """
                <body id="table-index-popup">
                <style>
                    div.heading {{
                        color: #880077;
                        padding: 0px;
                        font-weight: bold;
                        }}
                </style>
                <div class="heading">{0}</div>
                </body>
                """.format(idx)
                key = "table_" + str(self.td.start) + "_row_" + str(r)
                table_phantoms.append(key)
                self.view.add_phantom("table_" + str(self.td.start) + "_row_" + str(r),region,body,sublime.LAYOUT_INLINE)
                for c in range(1,self.td.Width()+1):
                    if(not idx.isnumeric()):
                        break
                    #print("II: " + str(idx) + "x" + str(c))
                    reg = self.td.FindCellRegion(int(idx),c)
                    if(not reg):
                        continue
                    row,col = self.view.rowcol(reg.begin())
                    pt1 = self.view.text_point(row,col)
                    pt2 = self.view.text_point(self.td.end,col)
                    region = sublime.Region(pt1,pt1)
                    body = """
                    <body id="table-index-popup">
                    <style>
                        div.heading {{
                            color: #880077;
                            padding: 0px;
                            font-weight: bold;
                            }}
                    </style>
                    <div class="heading">{0}</div>
                    </body>
                    """.format(c)
                    key = "table_" + str(self.td.start) + "_row_"+str(r)+"_col_" + str(c)
                    table_phantoms.append(key)
                    self.view.add_phantom(key,region,body,sublime.LAYOUT_INLINE)
                #p = Phantom(region, content, sublime.LAYOUT_INLINE)
                #phantoms.append(p)
        self.OnDone()

class OrgPlotTableCommand(sublime_plugin.TextCommand):
    def onHidden(self):
        self.view.run_command("org_show_images",{"onDone": evt.Make(self.onShown)})

    def onShown(self):
        self.OnDone()

    def OnDone(self):
        evt.EmitIf(self.onDone)

    def run(self, edit, onDone=None):
        self.td = create_table(self.view)
        plot_table_command(self.td,self.view) 
        self.edit = edit
        self.onDone = onDone
        self.view.run_command("org_hide_images",{"onDone": evt.Make(self.onHidden)})


class OrgImportTableFromCsvCommand(sublime_plugin.TextCommand):
    def OnFile(self, filename=None):
        self.inHan = None
        if(None == filename):
            return
        if(os.path.exists(filename) and os.path.isfile(filename)):
            fileData = ""
            with open(filename,'r') as f:
                fileData = f.read()
            self.pos = self.view.sel()[0]
            curNode = db.Get().AtInView(self.view)
            level = 1
            if(None != curNode):
                level = curNode.level
            insert_file_data(level,fileData,self.view, self.edit, evt.Make(self.OnDone))

    def OnDone(self):
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(self.pos.begin() +1, self.pos.end()+1))
        self.view.run_command('table_editor_next_field')
        evt.EmitIf(self.onDone)

    def run(self, edit, onDone=None):
        self.edit = edit
        self.onDone = onDone
        self.inHan = ins.OrgInput()
        self.inHan.isFileBox = True
        self.inHan.run("CSV", None, evt.Make(self.OnFile))

class OrgInsertBlankTableCommand(sublime_plugin.TextCommand):
    def OnDims(self, text):
        if(text == None):
            return
        dims = text.split('x')
        if(len(dims) != 2):
            log.error("DIMENSIONS ARE NOT RIGHT!")
            return
        w = int(dims[0])
        h = int(dims[1])
        curNode = db.Get().AtInView(self.view)
        level = 1
        if(None != curNode):
            level = curNode.level
        indent = (" " * level) + " "
        data = ""
        for y in range(0,h+1):
            line = indent + "|"
            for x in range(0,w):
                line += "|"
            data += line + '\n'
            if(y == 0):
                data += '|-\n'
        self.pos = self.view.sel()[0]
        self.view.run_command("org_internal_insert", {"location": self.view.sel()[0].begin(), "text": data, "onDone": self.onDone})
        self.OnDone()

    def OnDone(self):
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(self.pos.begin() +1, self.pos.end()+1))
        self.view.run_command('table_editor_next_field')
        evt.EmitIf(self.onDone)

    def run(self, edit, onDone=None):
        self.edit = edit
        self.onDone = onDone
        self.input = ins.OrgInput()
        self.input.run("WxH", None, evt.Make(self.OnDims))

RE_TABLE_LINE = re.compile(r'\s*[|]')
RE_TABLE_HLINE = re.compile(r'\s*[|][-][+-]*[|]')
RE_FMT_LINE = re.compile(r'\s*[#][+](TBLFM|tblfm)[:]\s*(?P<expr>.*)')

RE_TARGET = re.compile(r'\s*(([@](?P<rowonly>[-]?[0-9><]+))|([$](?P<colonly>[-]?[0-9><]+))|([@](?P<row>[-]?[0-9><]+)[$](?P<col>[-]?[0-9><]+)))\s*$')
def formula_rowcol(expr):
    fields = expr.split('=')
    if(len(fields) != 2):
        return (None, None)
    target = fields[0]
    targets = target.split('..')
    if(len(targets)==2):
        r1 = formula_rowcol(targets[0] + "=")
        r2 = formula_rowcol(targets[1] + "=")
        return [r1[0] + r2[0],fields[1]]
    m = RE_TARGET.search(target)
    if(m):
        row = m.group('row')
        col = m.group('col')
        if not row and not col:
            row = m.group('rowonly')
            if(row):
                if(isNumeric(row)):
                    row = int(row)
                col = '*'
                return [[row,col],fields[1]]
            else:
                col = m.group('colonly')
                if(isNumeric(col)):
                    col = int(col)
                row = '*'
                return [[row,col],fields[1]]
        else:
            if(isNumeric(row)):
                row = int(row)
            if(isNumeric(col)):
                col = int(col)
            return [[row,col],fields[1]]
    return (None, None)

def numberCheck(v):
    try:
        float(v)
        return True
    except:
        return False

def isNumeric(v):
    return v.lstrip('-').lstrip('+').isnumeric()

def isFunc(v):
    return 'ridx()' in v or 'cidx()' in v

# TODO: Make funciton cells work!
RE_TARGET_A = re.compile(r'\s*(([@](?P<rowonly>((?P<rosign>[+-])?[0-9><#]+)|(ridx\(\))|(cidx\(\))))|([$](?P<colonly>((?P<cosign>[+-])?[0-9><#]+)|(ridx\(\))|(cidx\(\))))|([@](?P<row>(?P<rsign>[+-])?[0-9><#]+)[$](?P<col>((?P<csign>[+-])?[0-9><#]+)|(ridx\(\))|(cidx\(\)))))(?P<end>[^@$]|$)')
RE_ROW_TOKEN = re.compile(r'[@][#]')
RE_COL_TOKEN = re.compile(r'[$][#]')
RE_SYMBOL_OR_CELL_NAME = re.compile(r'[$](?P<name>[a-zA-Z][a-zA-Z0-9_-]*)')
def replace_cell_references(expr):
    #print("EXPS: " + str(expr))
    while(True):
        expr = RE_ROW_TOKEN.sub('ridx()',expr)
        expr = RE_COL_TOKEN.sub('cidx()',expr)
        m = RE_TARGET_A.search(expr)
        if(m):
            row = m.group('row')
            col = m.group('col')
            rs  = m.group('rsign')
            cs  = m.group('csign')
            end = m.group('end')
            if(not end):
                end = ""
            if not row and not col:
                row = m.group('rowonly')
                if(row):
                    rs = m.group('rosign')
                    rs = '1' if rs else '0'
                    if(isNumeric(row) or isFunc(row)):
                        expr = RE_TARGET_A.sub('getrowcell(' + str(row) + ',' + rs + ')' + end,expr,1)
                    else:
                        expr = RE_TARGET_A.sub('getrowcell(\'' + str(row) + '\''+","+rs+')' + end,expr,1)
                else:
                    col = m.group('colonly')
                    cs = m.group('cosign')
                    cs = '1' if cs else '0'
                    if(isNumeric(col) or isFunc(col)):
                        expr = RE_TARGET_A.sub('getcolcell(' + str(col) + ',' + cs + ')' + end,expr,1)
                    else:
                        expr = RE_TARGET_A.sub('getcolcell(\'' + str(col) + '\'' +","+cs+ ')' + end,expr,1)
            else:
                rowmarkers = '' if not isNumeric(row) or isFunc(row) else '\''
                colmarkers = '' if not isNumeric(col) or isFunc(col) else '\''
                cs = '1' if cs else '0'
                rs = '1' if rs else '0'
                expr = RE_TARGET_A.sub('getcell(' + rowmarkers + str(row) + rowmarkers + "," + rs + "," + colmarkers + str(col) + colmarkers + "," + cs + ")" + end,expr,1)
        else:
            break
    while(True):
        m = RE_SYMBOL_OR_CELL_NAME.search(expr)
        if(m):
            name = m.group('name')
            expr = RE_SYMBOL_OR_CELL_NAME.sub('symorcell(\'' + name + '\')',expr,1)
        else:
            break
    #print("EXP: " + str(expr))
    return expr

def formula_sources(expr):
    ms = RE_TARGET.findall(expr)
    matches = []
    for m in ms:
        row = m.group('row')
        col = m.group('col')
        if not row and not col:
            row = m.group('rowonly')
            if(row):
                row = int(row)
                col = '*'
                matches.append([row,col])
            else:
                col = m.group('colonly')
                col = int(col)
                row = '*'
                matches.append([row,col])
        else:
            row = int(row)
            col = int(col)
            matches.append([row,col])
    return matches

#class EvalNoMethods(simpleeval.SimpleEval):
#    def _eval_call(self, node):
#        if isinstance(node.func, ast.Attribute):
#            raise simpleeval.FeatureNotAvailable("No methods please, we're British")
#        return super(EvalNoMethods, self)._eval_call(node)




class Formula:
    def __init__(self,expr, reg, formatters):
        self.formatters = formatters
        self.printfout = None
        if(self.formatters):
            m = RE_PRINTFSTYLE.search(self.formatters)
            if(m):
                self.printfout = m.group('formatter')
        self.target, self.expr = formula_rowcol(expr)
        # Never allow our expr to be empty. If we failed to parse it our EXPR is current cell value
        if(self.expr == None):
            self.expr = "$0"
        if(self.target == None):
            self.target = "@0$0"
        self.expr = replace_cell_references(self.expr.replace("..","//"))
        self.formula   = expr
        self.reg = reg 
    def EmptyIsZero(self):
        return 'N' in self.formatters

def CellRowIterator(table,start,end):
    c = table.CurCol()
    if(start < table.StartRow()):
        start = table.StartRow()
    for r in range(start,end+1):
        cell = Cell(r,c,table)
        yield cell

def CellColIterator(table,start,end):
    r = table.CurRow()
    for c in range(start,end+1):
        cell = Cell(r,c,table)
        yield cell

def CellBoxIterator(table,a,b):
    sr = a.GetRow()
    er = b.GetRow()
    if(a.GetRow() > b.GetRow()):
        sr = b.GetRow()
        er = a.GetRow()
    sc = a.GetCol()
    ec = b.GetCol()
    if(a.GetCol() > b.GetCol()):
        sc = b.GetCol()
        ec = a.GetCol()
    if(sr < table.StartRow()):
        sr = table.StartRow()
    for r in range(sr,er+1):
        for c in range(sc,ec+1):
            cell = Cell(r,c,table)
            yield cell

def CellIterator(table,cell):
    r = cell.r
    c = cell.c
    if(r == '*'):
        rrange = range(table.StartRow(),table.Height()+1)
    else:
        rrange = range(cell.GetRow(),cell.GetRow()+1)
    if(c == '*'):
        crange = range(table.StartCol(),table.Width()+1)
    else:
        crange = range(cell.GetCol(),cell.GetCol()+1)
    for r in rrange:
        for c in crange:
            cell = Cell(r,c,table)
            yield cell

def RCIterator(table,r,c):
    if(r == '*'):
        rrange = range(table.StartRow(),table.Height()+1)
    else:
        rrange = range(r,r+1)
    if(c == '*'):
        crange = range(table.StartCol(),table.Width()+1)
    else:
        crange = range(c,c+1)
    for r in rrange:
        for c in crange:
            yield [r,c]

# ============================================================
class Cell:
    def __init__(self,r,c,table,rrelative=0,crelative=0):
        self.r = r
        self.c = c
        self.table = table
        self.rrelative = rrelative
        self.crelative = crelative

    def __str__(self):
        return self.GetText()

    def __eq__(self, other):
        if isinstance(other, Cell):
            if self.r == other.r and self.c == other.c:
                return True
            return self.GetText() == other.GetText()
        return NotImplemented

    def rc(self):
        return (self.r,self.c)

    def GetRow(self):
        r = None
        if(isinstance(self.r,str)):
            if(self.r == "*"):
                r = self.table.CurRow()
            elif(self.r.startswith('>')):
                cnt = len(self.r.strip())
                r = self.table.Height() - (cnt-1)
            elif(self.r.startswith("<")):
                cnt = len(self.r.strip())
                r = self.table.StartRow() + (cnt-1)
            else:
                if(numberCheck(self.r)):
                    r = int(self.r)
        elif(self.r < 0 or self.rrelative):
            r = self.table.CurRow() + self.r
        elif(self.r == 0):
            return self.table.CurRow()
        else:
            r = self.r
        if(None == r):
            r = self.table.CurRow()
        if(r < 1):
            r = 1
        if(r > self.table.Height()):
            r = self.table.Height()
        return r

    def GetCol(self):
        c = None
        if(isinstance(self.c,str)):
            if(self.c == "*"):
                c = self.table.CurCol()
            elif(self.c.startswith(">")):
                cnt = len(self.c.strip())
                c = self.table.Width() - (cnt-1)
            elif(self.c.startswith("<")):
                cnt = len(self.c.strip())
                c = self.table.StartCol() + (cnt-1)
            else:
                if(numberCheck(self.c)):
                    c = int(self.c)
        elif(self.c < 0 or self.crelative):
            c = self.table.CurCol() + self.c
        elif(self.c == 0):
            return self.table.CurCol()
        else:
            c = self.c
        if(None == c):
            c = self.table.CurCol()
        if(c < 1):
            c = 1
        if(c > self.table.Width()):
            c = self.table.Width()
        return c

    def GetText(self):
        return self.table.GetCellText(self.GetRow(), self.GetCol())

    def GetInt(self):
        return int(self.GetText())

    def GetFloat(self):
        return float(self.GetText())

    def GetVal(self):
        txt = self.GetText().strip()
        if(numberCheck(txt)):
            if('.' in txt):
                return float(txt)
            return int(txt)
        return txt
    
    def GetNum(self):
        txt = self.GetText().strip()
        if(numberCheck(txt)):
            if('.' in txt):
                return float(txt)
            return int(txt)
        return 0

def GetVal(i):
    if(isinstance(i,Cell)):
        return i.GetVal()
    return i

def GetNum(i):
    if(isinstance(i,Cell)):
        return i.GetNum()
    return i

# ============================================================
#  Functions
# ============================================================

def safe_mult(a, b):  # pylint: disable=invalid-name
    if hasattr(a, '__len__') and b * len(a) > MAX_STRING_LENGTH:
        raise IterableTooLong('Sorry, I will not evalute something that long.')
    if hasattr(b, '__len__') and a * len(b) > MAX_STRING_LENGTH:
        raise IterableTooLong('Sorry, I will not evalute something that long.')
    return GetVal(a) * GetVal(b)

def safe_pow(a, b):  # pylint: disable=invalid-name
    if abs(a) > MAX_POWER or abs(b) > MAX_POWER:
        raise NumberTooHigh("Sorry! I don't want to evaluate {0} ** {1}"
                            .format(a, b))
    return GetVal(a) ** GetVal(b)


def safe_add(a, b):  # pylint: disable=invalid-name
    if hasattr(a, '__len__') and hasattr(b, '__len__'):
        if len(a) + len(b) > MAX_STRING_LENGTH:
            raise IterableTooLong("Sorry, adding those two together would"
                                  " make something too long.")
    return GetVal(a) + GetVal(b)

def tsub(a, b):  # pylint: disable=invalid-name
    return GetVal(a) - GetVal(b)

def tdiv(a, b):  # pylint: disable=invalid-name
    return GetNum(a) / GetNum(b)

def tmod(a, b):  # pylint: disable=invalid-name
    return GetVal(a) % GetVal(b)

def teq(a,b):
    return GetVal(a) == GetVal(b)

def tneq(a,b):
    return GetVal(a) != GetVal(b)

def tgt(a,b):
    return GetVal(a) > GetVal(b)

def tlt(a,b):
    return GetVal(a) < GetVal(b)

def tge(a,b):
    return GetVal(a) >= GetVal(b)

def tle(a,b):
    return GetVal(a) <= GetVal(b)

def tnot(a):
    return not GetVal(a)

def tusub(a):
    return - GetVal(a)

def tuadd(a):
    return + GetVal(a)

def vmean(rng):
    n = 0
    s = 0
    for i in rng:
        num = GetNum(i)
        s += num
        n += 1
    if(n != 0):
        return float(s) / float(n)
    return 0

def vsum(rng):
    s = 0
    for i in rng:
        s += GetNum(i)
    return s

def vmedian(rng):
    data = list(rng)
    dl = len(data)
    v = math.floor(dl/2)
    if(v*2 != dl):
        return GetNum(data[v+1])
    else:
        return (GetNum(data[v]) + GetNum(data[v+1]))/2.0

def vmax(rng):
    m = -999999999
    for i in rng:
        num = GetNum(i)
        if(num > m):
            m = num
    return m

def vmin(rng):
    m = 999999999
    for i in rng:
        num = GetNum(i)
        if(num < m):
            m = num
    return m

def myfloor(num):
    v = GetNum(num)
    if(isinstance(v,float)):
        return math.floor(v)
    return num 

def myceil(num):
    v = GetNum(num)
    if(isinstance(v,float)):
        return math.ceil(v)
    return num 

def myround(num):
    v = GetNum(num)
    if(isinstance(v,float)):
        return round(v,0)
    return num 

def mytrunc(num):
    v = GetNum(num)
    if(isinstance(v,float)):
        return int(v)
    return num 

def mynow():
    return datetime.datetime.now()

def myyear(dt):
    return dt.year

def myday(dt):
    return dt.day

def mymonth(dt):
    return dt.month

def myhour(dt):
    return dt.hour

def myminute(dt):
    return dt.minute

def mysecond(dt):
    return dt.second

def myweekday(dt):
    return dt.date().weekday()

def myyearday(dt):
    return dt.timetuple().tm_yday

def mytime(dt):
    return dt.time()

def mydate(dt):
    return dt.date()

def randomDigit(start, end):
    return random.randint(GetVal(start),GetVal(end))

def randomFloat():
    return random.randint(0,1000000)/1000000.0

def tan(cell):
    return math.tan(GetNum(cell))

def sin(cell):
    return math.sin(GetNum(cell))

def cos(cell):
    return math.cos(GetNum(cell))

def exp(cell):
    return math.exp(GetNum(cell))

def remote(name,cellRef):
    view = sublime.active_window().active_view()
    if(view):
        node = db.Get().AtInView(view)
        if(node):
            names = node.names
            if(names and name in names):
                row = names[name]['row']
                last_row = view.lastRow()
                for r in range(row,last_row):
                    pt = view.text_point(r, 0)
                    line = view.substr(view.line(pt))
                    m = RE_ISCOMMENT.search(line)
                    if(m):
                        continue
                    elif(line.strip() == ""):
                        continue
                    else:
                        row = r
                        break
                td = create_table(view,view.text_point(row,0))
                text = td.GetCellText(cellRef.GetRow(),cellRef.GetCol())
                return text

# ============================================================
class RangeExprOnNonCells(simpev.InvalidExpression):
    """ a name isn't defined. """

    def __init__(self,name,expression):
        self.name = name
        self.message = "both sides of a range expression must be a cell definition"
        self.expression = expression
        # pylint: disable=bad-super-call
        super(RangeExprOnNonCells, self).__init__(self.message)


# ============================================================
class TableDef(simpev.SimpleEval):
    def range_expr(self,a,b):
        if(isinstance(a,Cell) and isinstance(b,Cell)):
            if(a.r == "*" and b.r == "*"):
                return CellColIterator(a.table, a.GetCol(), b.GetCol())
            elif(a.c == "*" and b.c == "*"):
                return CellRowIterator(a.table, a.GetRow(), b.GetRow())
            elif(a.r != '*' and b.r != '*' and a.c != '*' and b.c != '*'):
                return CellBoxIterator(a.table,a,b)
            else:
                raise RangeExprOnNonCells("End cells must be wild of same type", "range expression is invalid")
        else:
            raise RangeExprOnNonCells(str(a), "range expression is invalid")

    def ridx(self):
        return self.CurRow()
    
    def cidx(self):
        return self.CurCol()

    def getrowcell(self,r,relative):
        return Cell(r,'*',self,relative,0)

    def getcolcell(self,c,relative):
        return Cell('*',c,self,0,relative)

    def getcell(self,r,c,rrelative,crelative):
        return Cell(r,c,self,rrelative,crelative)

    def symbolOrCell(self,name):
        # TODO: Look up cell names FIRST
        #       but only once we have the advanced features
        if(name in self.consts):
            v = self.consts[name].strip()
            if(numberCheck(v)):
                if('.' in v):
                    return float(v)
                else:
                    return int(v)
            return v

    def add_cell_names(self,names,start,end,linedef):
        pass
        #for r in range(1,(end+2)-start):
        #    names["r"+str(r)] = Cell(r,'*',self)
        #    for c in range(1,len(linedef)):
        #        names["c"+str(c)] = Cell('*',c,self)
        #        names["r"+str(r)+"c"+str(c)] = Cell(r,c,self)
        #print(str(names))
    def ClearAllRegions(self):
        for r in range(1,(self.end+2)-self.start):
            self.view.erase_regions("cell_"+str(r))
            for c in range(1,len(self.linedef)):
                self.view.erase_regions("cell__"+str(c))
                self.view.erase_regions("cell_"+str(r)+"_"+str(c))
        for i in range(0,self.NumFormulas()):
            self.view.erase_regions("fmla_"+str(i))

    def add_constants(self,n):
        n['pi'] = 3.1415926
    def add_functions(self,f):
        f['vmean'] = vmean
        f['vmedian'] = vmedian
        f['vmax'] = vmax
        f['vmin'] = vmin
        f['vsum'] = vsum
        f['tan'] = tan
        f['cos'] = cos
        f['sin'] = sin
        f['exp'] = exp
        f['floor'] = myfloor
        f['ceil'] = myceil
        f['round'] = myround
        f['trunc'] = mytrunc
        f['ridx'] = self.ridx
        f['cidx'] = self.cidx
        f['randomf'] = randomFloat
        f['random'] = randomDigit
        f['symorcell'] = self.symbolOrCell
        f['getcell'] = self.getcell
        f['getrowcell'] = self.getrowcell
        f['getcolcell'] = self.getcolcell
        f['remote'] = remote
        f['now'] = mynow
        f['year'] = myyear
        f['day'] = myday
        f['month'] = mymonth
        f['hour'] = myhour
        f['minute'] = myminute
        f['second'] = mysecond
        f['time'] = mytime
        f['date'] = mydate
        f['weekday'] = myweekday
        f['yearday'] = myyearday
        # abs
        # now

    def add_dynamic_functions(self,f):
        exts = sets.Get("enableTableExtensions",None)
        if(exts):
            dynamic = ext.find_extension_modules('orgtable', [])
            for k in dynamic.keys():
                if(hasattr(dynamic[k],"Execute")):
                    f[k] = dynamic[k].Execute
                else:
                    log.warning("Dynamic table module does not have method Execute, cannot use: " + k)
    def add_operators(self,o):
        o[ast.Mult] = safe_mult
        o[ast.Add]  = safe_add
        o[ast.Pow]  = safe_pow
        o[ast.Sub] = tsub
        o[ast.Div] = tdiv
        o[ast.Mod] = tmod
        o[ast.Eq] = teq
        o[ast.NotEq] = tneq
        o[ast.Gt] = tgt
        o[ast.Lt] = tlt
        o[ast.GtE] = tge
        o[ast.LtE] = tle
        o[ast.Not] = tnot
        o[ast.USub] = tusub
        o[ast.UAdd] = tuadd

    #                     ast.In: lambda x, y: op.contains(y, x),
    #                     ast.NotIn: lambda x, y: not op.contains(y, x),
    #                     ast.Is: lambda x, y: x is y,
    #                     ast.IsNot: lambda x, y: x is not y,
    #                     }

    def __init__(self,view, start,end,linedef):
        operators = simpev.DEFAULT_OPERATORS.copy()
        operators[ast.FloorDiv] = self.range_expr
        functions = simpev.DEFAULT_FUNCTIONS.copy()
        names = simpev.DEFAULT_NAMES.copy()
        self.add_operators(operators)
        self.add_functions(functions)
        self.add_dynamic_functions(functions)
        self.add_constants(names)
        self.add_cell_names(names,start,end,linedef)
        super(TableDef,self).__init__(operators, functions, names)
        self.curRow = 0
        self.curCol = 0
        self.start = start
        self.end   = end
        self.view  = view
        self.linedef = linedef
        self.cellToFormula = None
        self.accessList = []
        self.consts = {}
        self.emptyiszero = False
        self.startCol = 1

    def RecalculateTableDimensions(self):
        res = recalculate_linedef(self.view,self.start)
        if(res == None):
            log.error("FAILURE TO RECALCULATE LINE DEFINITION FOR TABLE. Something is wrong!")
        else:
            self.linedef = res

    def Width(self):
        if(not self.linedef):
            return 0
        return len(self.linedef) - 1

    def Height(self):
        return self.rowCount

    def StartRow(self):
        return self.startRow

    def StartCol(self):
        return self.startCol

    def SetCurRow(self,r):
        self.curRow = r
    
    def SetCurCol(self,c):
        self.curCol = c

    def CurRow(self):
        return self.curRow

    def CurCol(self):
        return self.curCol

    def GetCellText(self,r,c):
        self.accessList.append([r,c])
        reg = self.FindCellRegion(r,c)
        if(reg):
            text = self.view.substr(reg)
            if(self.emptyiszero and text.strip() == ""):
                return "0"
            return text
        if(self.emptyiszero):
            return "0"
        return ""
    def FindCellRegion(self,r,c):
        if(not r in self.lineToRow):
            return None
        row = self.lineToRow[r]
        #row = self.start + (r-1)       # 1 is zero
        colstart = self.linedef[c-1] 
        colend   = self.linedef[c]
        return sublime.Region(self.view.text_point(row,colstart+1),self.view.text_point(row,colend)) 
    def HighlightCells(self, cells,color):
        for cell in cells:
            it = RCIterator(self,cell[0],cell[1])
            for cc in it:
                reg = self.FindCellRegion(*cc)
                if(reg):
                    style = "orgagenda.week." + str(color)
                    self.view.add_regions("cell_"+str(cc[0])+"_"+str(cc[1]),[reg],style,"",sublime.DRAW_NO_FILL)

    def HighlightFormulaRegion(self,i,color=3):
        style = "orgagenda.week." + str(color)
        if(self.formulas and i >= 0 and i < len(self.formulas)):
            reg = self.formulas[i].reg
            if(reg):
                self.view.add_regions("fmla_"+str(i),[reg],style,"",sublime.DRAW_NO_FILL)

    def NumFormulas(self):
        return len(self.formulas) 

    def CursorToFormula(self):
        fm = self.formulaLine
        row,col = self.view.curRowCol()
        if(row != self.formulaRow):
            return None
        segs = fm.split('::')
        acc = 0
        for idx in range(0,len(segs)):
            if(col >= acc and col < acc+len(segs[idx])):
                return idx
            acc += len(segs[idx]) + 2
        return None

    def ReplaceFormula(self,i,formula):
        fmla = self.formulas[i]
        self.view.run_command("org_internal_replace", {"start": fmla.reg.begin(), "end": fmla.reg.end(), "text": formula})

    def AddNewFormula(self, formula):
        pt = None
        if(self.NumFormulas() > 0):
            pt = self.formulas[self.NumFormulas()-1].reg.end()
            formula = "::" + formula
        else:
            pt = self.view.text_point(self.end,0)
            ll = self.view.line(pt)
            line = self.view.substr(ll)
            indentCount = 0
            while(indentCount < 20 and line[indentCount] == ' ' or line[indentCount] == '\t'):
                indentCount += 1
            indent = ' ' * indentCount
            formula = "\n" + indent + "#+TBLFM:" + formula
            pt = ll.end()
        self.view.run_command("org_internal_insert", {"location": pt, "text": formula})

    def RowToCellRow(self,r):
        for i in range(1,len(self.lineToRow)+1):
            if(i in self.lineToRow and self.lineToRow[i] == r):
                return i
        return 1

    def FindCellColFromCol(self,c):
        for i in range(0,len(self.linedef)-1):
            if(c >= self.linedef[i] and c < self.linedef[i+1]):
                return i+1
        if(not self.linedef or (len(self.linedef) > 1 and c < self.linedef[0])):
            return 1
        return len(self.linedef)-1

    def CursorToCell(self):
        row,col = self.view.curRowCol()
        r = self.RowToCellRow(row)
        c = self.FindCellColFromCol(col)
        return [r,c]

    def CellToFormula(self, cell):
        r,c = cell
        if(self.cellToFormula):
            if(r in self.cellToFormula and c in self.cellToFormula[r]):
                return self.cellToFormula[r][c]
        return None

    def HighlightFormula(self, i):
        it = SingleFormulaIterator(self,i)
        for n in it:
            r,c,val,reg = n
            # This is important, the cell COULD return a cell
            # until we convert it to a string that cell will not
            # necessarily be touched so the accessList will not be
            # correct.
            valStr = str(val)
            self.HighlightCells(self.accessList,1)
            self.HighlightCells([[r,c]],2)
        self.HighlightFormulaRegion(i)

    def GetFormula(self,i):
        return self.formulas[i]

    def FormulaTarget(self, i):
        dm = self.formulas[i]
        return dm.target

    def ValidateFormulaCells(self,i):
        if("INVALID" in self.formulas[i].formula):
            sublime.status_message("ORG Table WARNING: Formula {0} is targetting an invalid cell!".format(i))

    def FormulaTargetCellIterator(self, i):
        target = self.FormulaTarget(i)
        self.ValidateFormulaCells(i)
        if(len(target) == 4):
            cellStart = Cell(target[0],target[1],self)
            cellEnd = Cell(target[2],target[3],self)
            cellIterator = CellBoxIterator(self,cellStart,cellEnd)
        else:
            cell = Cell(target[0],target[1],self)
            cellIterator = CellIterator(self,cell)
        return cellIterator

    def IsSingleTargetFormula(self,i):
        target = self.FormulaTarget(i)
        if(len(target) == 2 and isinstance(target[0],int) and isinstance(target[1],int)):
            return True
        return False 

    def AddCellToFormulaMap(self,cell,i):
        r,c = 1,1
        if(isinstance(cell,Cell)):
            r = cell.r
            c = cell.c
        else:
            r,c = cell
        if(not r in self.cellToFormula):
            self.cellToFormula[r] = {}
        self.cellToFormula[r][c] = i

    def BuildCellToFormulaMap(self):
        self.cellToFormula = {}
        for i in range(0,self.NumFormulas()):
            if(not self.IsSingleTargetFormula(i)):
                it = self.FormulaTargetCellIterator(i)
                if(it):
                    for c in it:
                        self.AddCellToFormulaMap(c,i)
        for i in range(0,self.NumFormulas()):
            if(self.IsSingleTargetFormula(i)):
                it = self.FormulaTargetCellIterator(i)
                if(it):
                    for c in it:
                        self.AddCellToFormulaMap(c,i)

    def Execute(self, i):
        self.accessList = []
        try:
            self.emptyiszero = self.formulas[i].EmptyIsZero()
            val = self.eval(self.formulas[i].expr)
            if(val and isinstance(val,Cell)):
                val = val.GetVal()
            return val
        except:
            log.error("TABLE ERROR: %s",traceback.format_exc())
            return "<ERR>"

    def GetFormulaAt(self):
        cell = self.CursorToCell()
        if(cell):
            formulaIdx = self.CellToFormula(cell)
            return formulaIdx
        return None
    def FormulaFormatter(self,i):
        dm = self.formulas[i]
        return dm.printfout


def findOccurrences(s, ch):
    return [i for i, letter in enumerate(s) if letter == ch]

def find_formula(view):
    row = view.curRow()
    last_row = view.lastRow()
    for r in range(row,last_row):
        pt = view.text_point(r, 0)
        line = view.substr(view.line(pt))
        m = RE_FMT_LINE.search(line)
        if(m):
            return m.group('expr').split('::')
        elif(RE_TABLE_LINE.search(line)):
            continue
        else:
            return None
def recalculate_linedef(view,row):
    pt = view.text_point(row, 0)
    line = view.substr(view.line(pt))
    linedef = None
    if(not RE_TABLE_HLINE.search(line) and RE_TABLE_LINE.search(line)):
        linedef = findOccurrences(line,'|')
    return linedef

# ====================================================================
# CREATE TABLE
# ====================================================================
RE_AUTOCOMPUTE = re.compile(r"^\s*[|]\s*(?P<a>[#_$^*!/])\s*[|]")
def create_table(view, at=None):
    row = view.curRow()
    if(at != None):
        row,_ = view.rowcol(at)
    start_row = row
    last_row = view.lastRow()
    end = last_row
    start = row
    linedef = None
    formula = None
    hlines = []
    lineToRow = {}
    endHeader = 1
    formulaRow = None
    formulaLine = None
    for r in range(row-1,0,-1):
        pt = view.text_point(r, 0)
        line = view.substr(view.line(pt))
        if(RE_TABLE_LINE.search(line) or RE_TABLE_HLINE.search(line)):
            continue
        row = r+1
        break
    start = row
    rowNum = 0
    lastRow = 0
    spacesRow = 0
    isAdvanced = False
    autoCompute = []
    namesRowsAbove = []
    namesRowsBelow = []
    colNames       = []
    parameters     = []
    ignore = []
    for r in range(row,last_row+1):
        rowNum += 1
        pt = view.text_point(r, 0)
        line = view.substr(view.line(pt))
        m = RE_FMT_LINE.search(line)
        # Found a table hline. These don't get counted
        if(RE_TABLE_HLINE.search(line)):
            hlines.append(r)
            rowNum -= 1
            if(endHeader == 1):
                endHeader = (r - start) + 1
            continue
        # Found a table line match and continue
        elif(RE_TABLE_LINE.search(line)):
            if(None == linedef):
                linedef = findOccurrences(line,'|')
            # Is this an advanced table? If so we have to handle things
            # in a special way!
            mm = RE_AUTOCOMPUTE.search(line) 
            if(mm):
                isAdvanced = True
                char = mm.group('a')
                # Name row
                if(char == '!'):
                    ignore.append((rowNum,r))
                    colNames.append((rowNum,r))
                    pass
                # Auto compute row
                elif(char == "#"):
                    autoCompute.append(rowNum)
                # compute row
                elif(char == "*"):
                    pass
                # Skip row
                elif(char == "/"):
                    ignore.append((rowNum,r))
                    pass
                # Name below
                elif(char == "_"):
                    namesRowsBelow.append((rowNum,r))
                    ignore.append((rowNum,r))
                    pass
                # Name above
                elif(char == "^"):
                    namesRowsAbove.append((rowNum,r))
                    ignore.append((rowNum,r))
                    pass
                elif(char == "$"):
                    parameters.append((rowNum,r))
                    ignore.append((rowNum,r))
                else:
                    ignore.append((rowNum,r))
                    pass
                lineToRow[rowNum] = r
            else:
                lineToRow[rowNum] = r
            continue
        # Found a formula break!
        elif(m):
            end = r-1
            formula = m.group('expr').split('::')
            formulaRow = r
            formulaLine = line
            lastRow = rowNum - 1
            break
        else:
            # We keep going for blank lines allowing #TBLFM lines with spaces to
            # be okay.
            if(line.strip() == ""):
                if(lastRow == 0):
                    spacesRow = r
                    end = r-1
                    lastRow = rowNum - 1
                continue
            else:
                if(lastRow == 0):
                    end = r-1
                    lastRow = rowNum - 1
            break
    for r in range(row,0,-1):
        pt = view.text_point(r, 0)
        line = view.substr(view.line(pt))
        if(RE_TABLE_LINE.search(line)):
            continue
        else:
            start = r+1
            break
    td = TableDef(view, start, end, linedef)
    td.hlines = hlines
    td.startRow = endHeader
    td.spacesRow = spacesRow
    #td.linedef = linedef
    td.formulas = []
    td.formulaRow    = formulaRow
    td.formulaLine   = formulaLine
    td.lineToRow     = lineToRow
    td.rowCount      = lastRow
    td.autoCompute   = autoCompute
    td.nameRowsAbove = namesRowsAbove
    td.nameRowsBelow = namesRowsBelow
    td.colNames      = colNames
    td.ignore        = ignore
    if(isAdvanced):
        td.startCol = 2
    if(formula):
        sre = re.compile(r'\s*[#][+]((TBLFM)|(tblfm))[:]')
        first = sre.match(formulaLine)
        if(first):
            lastend = len(first.group(0))
            xline = sre.sub('',formulaLine)
            las = xline.split('::')
            index = 0
            for fm in formula:
                formatters = fm.split(';')
                if(len(formatters) > 1):
                    fm = formatters[0]
                    formatters = formatters[1]
                else:
                    formatters = ""
                fend = lastend+len(las[index])
                td.formulas.append(Formula(fm, sublime.Region(view.text_point(formulaRow,lastend),view.text_point(formulaRow,fend)),formatters))
                index += 1
                lastend = fend + 2
        td.BuildCellToFormulaMap()
    # 
    if(td):
        node = db.Get().At(view, start_row)
        if(node):
            constants = node.list_comment('CONSTANTS',[])
            consts = {}
            if(constants and len(constants) > 0):
                for con in constants:
                    cs = con.split('=')
                    if(len(cs) == 2):
                        name = cs[0].strip()
                        val  = cs[1].strip()
                        consts[name] = val
            props = node.properties
            if(props and len(props) > 0):
                for k,v in props.items():
                    consts['PROP_'+k] = v
            td.consts = consts
        if(parameters and len(parameters) > 0):
            for prow in parameters:
                for c in range(2,td.Width()):
                    txt = td.GetCellText(prow[0],c).strip()
                    if('=' in txt):
                        ps = txt.split(' ')
                        if(len(ps) < 1):
                            continue
                        for p in ps:
                            pp = p.split('=')
                            if(len(pp) == 2):
                                td.consts[pp[0].strip()] = pp[1].strip()
    return td


def SingleFormulaIterator(table,i):
    cellIterator = table.FormulaTargetCellIterator(i) 
    for cell in cellIterator:
        r,c = cell.rc()
        table.SetCurRow(r)
        table.SetCurCol(c)
        val = table.Execute(i)
        yield [r,c,val,table.FindCellRegion(r,c)]

def FormulaIterator(table):
    for i in range(0,table.NumFormulas()):
        cellIterator = table.FormulaTargetCellIterator(i) 
        for cell in cellIterator:
            r,c = cell.rc()
            table.SetCurRow(r)
            table.SetCurCol(c)
            val = table.Execute(i)
            yield (r,c,val,table.FindCellRegion(r,c),table.FormulaFormatter(i))
    return None

# ================================================================================
class OrgExecuteTableCommand(sublime_plugin.TextCommand):
    def on_reformat(self):
        self.td.RecalculateTableDimensions()
        self.process_next()

    def on_done_cell(self):
        self.view.sel().clear()
        self.view.sel().add(self.result[3])
        #self.view.run_command('table_editor_next_field')
        self.view.run_command('table_editor_align')
        sublime.set_timeout(self.on_reformat,1)

    def process_next(self):
        self.result = next(self.it,None)
        if(None == self.result):
            self.on_done()
            return
        r,c,val,reg,fmt = self.result
        if(val and isinstance(val,float) and fmt and "%" in fmt):
            val = fmt % val
        #print("REPLACING WITH: " + str(val))
        self.view.run_command("org_internal_replace", {"start": reg.begin(), "end": reg.end(), "text": str(val), "onDone": evt.Make(self.on_done_cell)})

    def on_done(self):
        evt.EmitIf(self.onDone)

    def on_formula_copy_done(self):
        # Working on formula handling
        self.td = create_table(self.view)
        self.td.ClearAllRegions()
        self.it = FormulaIterator(self.td)
        self.process_next()

    def run(self, edit,onDone=None,skipFormula=None):
        self.onDone = onDone
        if(skipFormula):
            self.on_formula_copy_done()
        else:
            self.view.run_command('org_fill_in_formula_from_cell',{"onDone": evt.Make(self.on_formula_copy_done)})
        #td.HighlightFormula(i)

# ================================================================================
class OrgClearTableRegionsCommand(sublime_plugin.TextCommand):
    def run(self,edit,at=None):
        global tableCache
        self.td = tableCache.GetTable(self.view,at)
        if(self.td):
            self.td.ClearAllRegions()

# ================================================================================
class OrgHighlightFormulaCommand(sublime_plugin.TextCommand):
    def run(self,edit):
        global tableCache
        td = tableCache.GetTable(self.view)
        if(td):
            td.ClearAllRegions()
            i = td.CursorToFormula()
            if(None != i):
                td.HighlightFormula(i)

# ================================================================================
class OrgHighlightFormulaFromCellCommand(sublime_plugin.TextCommand):
    def run(self,edit):
        global tableCache
        td = tableCache.GetTable(self.view)
        if(td):
            td.ClearAllRegions()
            formulaIdx = td.GetFormulaAt()
            if(None != formulaIdx):
                td.HighlightFormula(formulaIdx)

# ================================================================================
class OrgFillInFormulaFromCellCommand(sublime_plugin.TextCommand):
    def on_reformat(self):
        td = create_table(self.view)
        cell = td.CursorToCell()
        if(cell):
            r,c = cell
            txt = td.GetCellText(r,c).strip()
            formula = None
            rangeFml = False
            # Direct targeted formula
            if(txt.startswith(":=")):
                formula = "@" + str(r) + "$" + str(c) + txt[1:]
            # Row targeted formula
            if(txt.startswith(">=")):
                formula = "@" + str(r) + txt[1:]
            # Column formula
            if(txt.startswith("=")):
                formula = "$" + str(c) + txt
                rangeFml = True
            if(formula):
                formulaIdx = td.CellToFormula(cell)
                if(None != formulaIdx):
                    td.ReplaceFormula(formulaIdx,formula)
                else:
                    td.AddNewFormula(formula)
        if(self.onDone):
            evt.EmitIf(self.onDone)
        else:
            self.view.run_command('org_execute_table',{'skipFormula': True})

    def run(self,edit,onDone=None):
        self.onDone = onDone
        self.view.run_command('table_editor_align')
        sublime.set_timeout(self.on_reformat,1)


# ================================================================================
class TableEventListener(sublime_plugin.ViewEventListener):

    @classmethod
    def is_applicable(cls, settings):
        # 4095 seems to crash when querying settings
        if(int(sublime.version()) != 4095):
            try:
                return not "not here" in settings.get("orgDirs","not here")
            except:
                return False
        else:
            return False

    def __init__(self, view):
        super(TableEventListener, self).__init__(view)
        self.showing = False
        self.at = None
        self.lastpt = None
        global tableCache
        self.tableCache = tableCache
  
    def GetTable(self):
        if(isTable(self.view)):
            return tableCache.GetTable(self.view)
        return None

    def on_selection_modified(self):
        if(self.lastpt and self.lastpt == self.view.sel()[0].begin()):
            return
        self.lastpt = self.view.sel()[0].begin()
        if(isTableFormula(self.view)):
            self.view.run_command("org_highlight_formula")
            self.at = self.view.sel()[0].begin()
            self.showing = True
        elif(isTable(self.view)):
            self.view.run_command("org_highlight_formula_from_cell")
            if(not self.at):
                self.at = self.view.sel()[0].begin()
            self.showing = True
        elif(self.showing):
            self.view.run_command("org_clear_table_regions", {'at': self.at})
            self.showing = False

    def wasFirstRow(self):
        return self.preCell[0] <= 1
    
    def wasLastRow(self,td):
        rc = self.preCell[0] >= td.Height()
        return rc

    def wasFirstCol(self):
        return self.preCell[1] <= 1
    
    def wasLastCol(self,td):
        return self.preCell[1] >= td.Width()

    def wasPostToHLine(self):
        r = self.preRow
        prior = r-1
        return (prior in self.hlines)
    
    def wasPreToHLine(self):
        r = self.preRow
        pre = r+1
        rc = (pre in self.hlines)
        return rc

    def wasHLine(self):
        r = self.preRow
        rc = (r in self.hlines)
        return rc

    def on_text_command(self, command_name, args=None):
        if('table_editor' in command_name):
            td = self.GetTable()
            self.preCell = None
            self.preRow,col = self.view.curRowCol()
            if(td):
                self.preCell = td.CursorToCell()
                self.hlines  = td.hlines
    def on_post_text_command(self, command_name, args= None):
        if(hasattr(self,'preCell') and self.preCell != None):
            if('table_editor_move_row_up' == command_name):
                # Also if pre was an hline
                if(self.wasFirstRow() or self.wasHLine() or self.wasPostToHLine()):
                    return
                # 2 rows flipped
                td = self.GetTable()
                RE_ROW = re.compile("[@](?P<num>[0-9]+)")
                line = td.formulaLine
                out = ""
                last = 0
                for m in RE_ROW.finditer(line):
                    s = m.span()
                    num = int(m.group('num'))
                    if(num == self.preCell[0]):
                        newNum = num - 1
                        out += line[last:s[0]] + "@" + str(newNum)
                        last = s[1]
                    elif(num == (self.preCell[0]-1)):
                        newNum = num + 1
                        out += line[last:s[0]] + "@" + str(newNum)
                        last = s[1]
                    else:
                        out += line[last:s[1]]
                        last = s[1]
                out += line[last:]
                lineReg = self.view.line(self.view.text_point(td.formulaRow,0))
                self.view.run_command("org_internal_replace", {"start": lineReg.begin(), "end": lineReg.end(), "text": out})
            elif('table_editor_move_row_down' == command_name):
                # Also if pre was an hline
                td = self.GetTable()
                if(self.wasLastRow(td) or self.wasHLine() or self.wasPreToHLine()):
                    return
                # 2 rows flipped
                RE_ROW = re.compile("[@](?P<num>[0-9]+)")
                line = td.formulaLine
                out = ""
                last = 0
                for m in RE_ROW.finditer(line):
                    s = m.span()
                    num = int(m.group('num'))
                    if(num == self.preCell[0]):
                        newNum = num + 1
                        out += line[last:s[0]] + "@" + str(newNum)
                        last = s[1]
                    elif(num == (self.preCell[0]+1)):
                        newNum = num - 1
                        out += line[last:s[0]] + "@" + str(newNum)
                        last = s[1]
                    else:
                        out += line[last:s[1]]
                        last = s[1]
                out += line[last:]
                lineReg = self.view.line(self.view.text_point(td.formulaRow,0))
                self.view.run_command("org_internal_replace", {"start": lineReg.begin(), "end": lineReg.end(), "text": out})
            elif('table_editor_move_column_left' == command_name):
                if(self.wasFirstCol()):
                    return
                # 2 cols flipped
                td = self.GetTable()
                RE_ROW = re.compile("[$](?P<num>[0-9]+)")
                line = td.formulaLine
                out = ""
                last = 0
                for m in RE_ROW.finditer(line):
                    s = m.span()
                    num = int(m.group('num'))
                    if(num == self.preCell[1]):
                        newNum = num - 1
                        out += line[last:s[0]] + "$" + str(newNum)
                        last = s[1]
                    elif(num == (self.preCell[1]-1)):
                        newNum = num + 1
                        out += line[last:s[0]] + "$" + str(newNum)
                        last = s[1]
                    else:
                        out += line[last:s[1]]
                        last = s[1]
                out += line[last:]
                lineReg = self.view.line(self.view.text_point(td.formulaRow,0))
                self.view.run_command("org_internal_replace", {"start": lineReg.begin(), "end": lineReg.end(), "text": out})
            elif('table_editor_move_column_right' == command_name):
                td = self.GetTable()
                if(self.wasLastCol(td)):
                    return
                # 2 cols flipped
                RE_ROW = re.compile("[$](?P<num>[0-9]+)")
                line = td.formulaLine
                out = ""
                last = 0
                for m in RE_ROW.finditer(line):
                    s = m.span()
                    num = int(m.group('num'))
                    if(num == self.preCell[1]):
                        newNum = num + 1
                        out += line[last:s[0]] + "$" + str(newNum)
                        last = s[1]
                    elif(num == (self.preCell[1]+1)):
                        newNum = num - 1
                        out += line[last:s[0]] + "$" + str(newNum)
                        last = s[1]
                    else:
                        out += line[last:s[1]]
                        last = s[1]
                out += line[last:]
                lineReg = self.view.line(self.view.text_point(td.formulaRow,0))
                self.view.run_command("org_internal_replace", {"start": lineReg.begin(), "end": lineReg.end(), "text": out})
            elif('table_editor_kill_row' == command_name):
                # This has a problem! It doesn't move the formula up!
                # I am going to have to find the formula and delete the blank lines so it gets moved!
                td = self.GetTable()
                RE_ROW = re.compile("[@](?P<num>[0-9]+)")
                line = td.formulaLine
                out = ""
                last = 0
                for m in RE_ROW.finditer(line):
                    s = m.span()
                    num = int(m.group('num'))
                    if(num > self.preCell[0]):
                        newNum = num - 1
                        out += line[last:s[0]] + "@" + str(newNum)
                        last = s[1]
                    if(num == self.preCell[0]):
                        out += line[last:s[0]] + "@INVALID"
                        last = s[1]
                    else:
                        out += line[last:s[1]]
                        last = s[1]
                out += line[last:]
                lineReg = self.view.line(self.view.text_point(td.formulaRow,0))
                spacesReg = lineReg
                if(td.spacesRow > 0):
                    spacesReg = self.view.line(self.view.text_point(td.spacesRow,0))
                self.view.run_command("org_internal_replace", {"start": spacesReg.begin(), "end": lineReg.end(), "text": out})
            elif('table_editor_insert_row' == command_name):
                td = self.GetTable()
                RE_ROW = re.compile("[@](?P<num>[0-9]+)")
                line = td.formulaLine
                out = ""
                last = 0
                for m in RE_ROW.finditer(line):
                    s = m.span()
                    num = int(m.group('num'))
                    if(num >= self.preCell[0]):
                        newNum = num + 1
                        out += line[last:s[0]] + "@" + str(newNum)
                        last = s[1]
                    else:
                        out += line[last:s[1]]
                        last = s[1]
                out += line[last:]
                lineReg = self.view.line(self.view.text_point(td.formulaRow,0))
                self.view.run_command("org_internal_replace", {"start": lineReg.begin(), "end": lineReg.end(), "text": out})
            elif('table_editor_delete_column' == command_name):
                td = self.GetTable()
                RE_ROW = re.compile("[$](?P<num>[0-9]+)")
                line = td.formulaLine
                out = ""
                last = 0
                for m in RE_ROW.finditer(line):
                    s = m.span()
                    num = int(m.group('num'))
                    if(num > self.preCell[1]):
                        newNum = num - 1
                        out += line[last:s[0]] + "$" + str(newNum)
                        last = s[1]
                    if(num == self.preCell[1]):
                        out += line[last:s[0]] + "$INVALID"
                        last = s[1]
                    else:
                        out += line[last:s[1]]
                        last = s[1]
                out += line[last:]
                lineReg = self.view.line(self.view.text_point(td.formulaRow,0))
                self.view.run_command("org_internal_replace", {"start": lineReg.begin(), "end": lineReg.end(), "text": out})
            elif('table_editor_insert_column' == command_name):
                td = self.GetTable()
                RE_ROW = re.compile("[$](?P<num>[0-9]+)")
                line = td.formulaLine
                out = ""
                last = 0
                for m in RE_ROW.finditer(line):
                    s = m.span()
                    num = int(m.group('num'))
                    if(num >= self.preCell[1]):
                        newNum = num + 1
                        out += line[last:s[0]] + "$" + str(newNum)
                        last = s[1]
                    else:
                        out += line[last:s[1]]
                        last = s[1]
                out += line[last:]
                lineReg = self.view.line(self.view.text_point(td.formulaRow,0))
                self.view.run_command("org_internal_replace", {"start": lineReg.begin(), "end": lineReg.end(), "text": out})



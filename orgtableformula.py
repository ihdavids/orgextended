import sublime
import sublime_plugin
import datetime
import re
#from pathlib import Path
import os
#import fnmatch
#import OrgExtended.orgparse.node as node
import OrgExtended.orgutil.util as util
import logging
#import sys
import traceback 
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
import OrgExtended.pymitter as evt
import OrgExtended.orginsertselected as ins
import OrgExtended.simple_eval as simpev
import OrgExtended.orgextension as ext
import OrgExtended.orgparse.date as orgdate
import OrgExtended.orgduration as orgduration
import OrgExtended.orgtableplot as orgplot
import OrgExtended.orglinks as olinks
import math
import random
import ast
import operator as op
import subprocess
import platform
import time
import json
import ast

random.seed()
RE_TABLE_LINE   = re.compile(r'\s*[|]')
RE_PRINTFSTYLE = re.compile(r"(?P<formatter>[%][0-9]*\.[0-9]+f)")
RE_ISCOMMENT = re.compile(r"^\s*[#][+]")
RE_AUTOLINE = re.compile(r"^\s*[|]\s*[#]\s*[|]")
RE_AUTOCOMPUTE = re.compile(r"^\s*[|]\s*(?P<a>[#_$^*!/ ])\s*[|]")
RE_END_BLOCK   = re.compile(r'^\s*[#][+](END|end)[:]\s*')
MAX_STRING_LENGTH = 100000
MAX_COMPREHENSION_LENGTH = 10000
MAX_POWER = 4000000  # highest exponent

highlightEnabled = True

log = logging.getLogger(__name__)


def isTable(view,at=None):
    if(at == None):
        at = view.sel()[0].end()
    names = view.scope_name(at)
    return 'orgmode.table' in names

def isTableFormula(view):
    names = view.scope_name(view.sel()[0].end())
    return 'orgmode.tblfm' in names

def isTableLine(line):
    return RE_TABLE_LINE.search(line)

def isAutoComputeRow(view):
    return None != RE_AUTOLINE.search(view.curLineText())

opsTable = None
def GetOps():
    global opsTable
    if(opsTable == None):
        o = simpev.DEFAULT_OPERATORS.copy()
        o[ast.Mult]  = safe_mult
        o[ast.Add]   = safe_add
        o[ast.Pow]   = safe_pow
        o[ast.Sub]   = tsub
        o[ast.Div]   = tdiv
        o[ast.Mod]   = tmod
        o[ast.Eq]    = teq
        o[ast.NotEq] = tneq
        o[ast.Gt]    = tgt
        o[ast.Lt]    = tlt
        o[ast.GtE]   = tge
        o[ast.LtE]   = tle
        o[ast.Not]   = tnot
        o[ast.USub]  = tusub
        o[ast.UAdd]  = tuadd
        opsTable     = o
    return opsTable

def add_dynamic_symbols(s):
    exts = sets.Get("enableTableExtensions",None)
    if(exts):
        dynamic = ext.find_extension_modules('orgtable', [])
        for k in dynamic.keys():
            if(hasattr(dynamic[k],"AddSymbols")):
                try:
                    dynamic[k].AddSymbols(s)
                except:
                    log.error("Failed to add symbols from: " + str(k) + "\n" + traceback.format_exc())
            else:
                if(not hasattr(dynamic[k],"Execute")):
                    log.warning("Dynamic table module does not have method AddSymbols, cannot use: " + k)
constsTable = None
def GetConsts():
    global constsTable
    reloadExtensions = sets.Get("forceLoadExternalExtensions",False)
    if(constsTable == None or reloadExtensions):
        n = simpev.DEFAULT_NAMES.copy()
        n['pi']     = 3.1415926535897932385
        n['t']      = True
        n['true']   = True
        n['True']   = True
        n['false']  = False
        n['False']  = False
        n['nil']    = None
        n['None']   = None
        add_dynamic_symbols(n)
        constsTable = n
    return constsTable

# These are table extensions you would like to add
# for performance reasons we only reload them when you start sublime
# you can however turn on forceLoadExternalExtensions to reload the
# extension dynamically ALL THE TIME. do not leave that one though!
def add_dynamic_functions(f):
    exts = sets.Get("enableTableExtensions",None)
    if(exts):
        dynamic = ext.find_extension_modules('orgtable', [])
        for k in dynamic.keys():
            if(hasattr(dynamic[k],"Execute")):
                f[k] = dynamic[k].Execute
            else:
                if(not hasattr(dynamic[k],"AddSymbols")):
                    log.warning("Dynamic table module does not have method Execute, cannot use: " + k)


functionsTable = None
def GetFunctions():
    global functionsTable
    reloadExtensions = sets.Get("forceLoadExternalExtensions",False)
    if(functionsTable == None or reloadExtensions):
        f = simpev.DEFAULT_FUNCTIONS.copy()
        f['vmean'] = vmean
        f['vmedian'] = vmedian
        f['vmax'] = vmax
        f['vmin'] = vmin
        f['vsum'] = vsum
        f['tan'] = tan
        f['cos'] = cos
        f['sin'] = sin
        f['atan'] = atan
        f['acos'] = acos
        f['asin'] = asin
        f['tanh'] = tanh
        f['cosh'] = cosh
        f['sinh'] = sinh
        f['atanh'] = atanh
        f['acosh'] = acosh
        f['asinh'] = asinh
        f['degrees'] = degrees
        f['radians'] = radians
        f['exp'] = exp
        f['sqrt'] = sqrt
        f['pow'] = pow
        f['log'] = mylog
        f['log10'] = mylog10
        f['log2'] = mylog2
        f['floor'] = myfloor
        f['ceil'] = myceil
        f['round'] = myround
        f['trunc'] = mytrunc
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
        f['duration'] = myduration
        f['randomf'] = randomFloat
        f['random'] = randomDigit
        f['abs'] = myabs
        f['bool'] = mybool
        f['int'] = myint
        f['float'] = myfloat
        f['highlight'] = myhighlight
        f['filename'] = mylocalfile
        add_dynamic_functions(f)
        functionsTable = f
    return functionsTable

class TableCache:
    def __init__(self):
        self.cachedTables = {}
        self.change_count = -1

    def _ViewName(self,view):
        name = view.file_name()
        if(not name):
            name = "view_" + view.id()
        return name

    def _FindTable(self,row,view):
        name = self._ViewName(view)
        if(not name in self.cachedTables):
            self.cachedTables[name] = []
        cache = self.cachedTables[name]
        if(self.change_count >= view.change_count()):
            for t in cache:
                if row >= t[0][0] and row <= t[0][1]:
                    return t[1]
        else:
            self.change_count = view.change_count()
            self.cachedTables[name] = []
        return None

    def GetTable(self,view,at=None):
        row = view.curRow()
        if(at != None):
            row,_ = view.rowcol(at)
        td = self._FindTable(row,view)
        if(not td):
            td = create_table(view,at)
            name = self._ViewName(view)
            self.cachedTables[name].append(((td.start,td.end),td))
        return td

tableCache = TableCache()

def TableConversion(indentDepth,data):
    # figure out what our separator is.
    # replace the separator with |
    indent = ""
    if(indentDepth > 0):
        indent = (" " * indentDepth) + " "
    try:
        # Try AST and see if we can parse it that way.
        # This if for things like: [[a,b,c],[1,2,3],[4,5,6]]
        l = ast.literal_eval(data)
        d = ""
        if(isinstance(l,list)):
            for r in l:
                if (isinstance(r,list)):
                    d += indent + "|"
                    for c in r:
                        d += str(c) + "|"
                else:
                    d += "|" + str(r) + "|"
                d += "\n"
            return (d, True)
    except:
        # It is okay if we fail.
        pass
    # Nope use the heuristic processing way.
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
        if(mean > 0):
            variance = math.sqrt(sum([ (x-mean)*(x-mean) for x in d ]) / len(d))
            vars[k] = variance
    #print(str(vars))
    separator = min(vars, key=vars.get) 
    # We prefer comma if the variance is the same for the min and comma.
    if(separator != ',' and ',' in vars and vars[','] == vars[separator]):
        separator = ','
    log.info("SEPARATOR CHOSEN: " + separator)
    data = ""
    for l in lines:
        if(l.strip() == ""):
            continue
        data += indent + '|' + l.strip().replace(separator,'|') + '|\n'
    return (data, True)


def insert_file_data(indentDepth, data, view, edit, onDone=None, replace=False):
    data,_ = TableConversion(indentDepth, data)
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
    def OnDone(self):
        if(None != self.origCur):
            self.view.sel().clear()
            self.view.sel().add(self.origCur)
        evt.EmitIf(self.onDone)

    def run(self, edit, onDone=None):
        self.onDone = onDone
        if(self.view.sel()):
            self.origCur = self.view.sel()[0]
        row = self.view.curRow()
        line = self.view.getLine(row)
        if("#+PLOT:" in line):
            pt = self.view.text_point(row,0)
            while(not isTable(self.view,pt)):
                row += 1
                pt = self.view.text_point(row,0)
            self.origCur = pt
            self.view.sel().clear()
            self.view.sel().add(self.origCur)
        self.td = create_table(self.view)
        orgplot.plot_table_command(self.td,self.view) 
        self.edit = edit
        self.view.run_command("org_cycle_images",{"onDone": evt.Make(self.OnDone)})

# Grab the function table and dump a table of all the functions and their doc strings.
# Build a table of that information.
class OrgDocTableCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        td = create_table(self.view)
        out = ""
        keys = list(td.functions.keys())
        keys.sort()
        for k in keys:
            v = td.functions[k]
            if(k == "ridx" or k == "cidx" or k == "symorcell" or k == "getcell" or k == "getcolcell" or k == "getrowcell"):
                continue
            if(not v.__doc__):
                out += "  - " + k + " :: " +  "Not Yet Documented \n"
            else:
                out += "  - " + k + " :: " + str(v.__doc__).replace("\n","\n      ") + "\n"
        out += "----------------------NAMES--------------------------------\n"
        for k,v in td.names.items():
            out += "  - " + k + " :: " +  str(v) + " \n"
        self.view.insert(edit,self.view.line(self.view.size()).begin(),out)


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

RE_TABLE_HLINE  = re.compile(r'\s*[|][-][+-]*[|]')
RE_FMT_LINE     = re.compile(r'\s*[#][+](TBLFM|tblfm)[:]\s*(?P<expr>.*)')
RE_TARGET       = re.compile(r'\s*(([@](?P<rowonly>[-]?[0-9><]+))|([$](?P<colonly>[-]?[0-9><]+))|([@](?P<row>[-]?[0-9><]+)[$](?P<col>[-]?[0-9><]+)))\s*$')
RE_NAMED_TARGET = re.compile(r'\s*[$](?P<name>[a-zA-Z][a-zA-Z0-9]+)')
def formula_rowcol(expr,table):
    fields = expr.split('=')
    if(len(fields) < 2):
        return (None, None, None)
    target = fields[0]
    formula = "=".join(fields[1:]) if len(fields[1:]) > 1 else fields[1]
    targets = target.split('..')
    if(len(targets)==2):
        r1 = formula_rowcol(targets[0] + "=",table)
        r2 = formula_rowcol(targets[1] + "=",table)
        return [r1[0] + r2[0],formula,None]
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
                return [[row,col],formula,None]
            else:
                col = m.group('colonly')
                if(isNumeric(col)):
                    col = int(col)
                row = '*'
                return [[row,col],formula,None]
        else:
            if(isNumeric(row)):
                row = int(row)
            if(isNumeric(col)):
                col = int(col)
            return [[row,col],formula,None]
    else:
        mn = RE_NAMED_TARGET.search(target)
        if(mn):
            cell = table.symbolOrCell(mn.group('name').strip())
            if(isinstance(cell,Cell)):
                return [[cell.r,cell.c],formula,cell.rowFilter]
    return (None, None, None)

def isNumeric(v):
    return v.strip().lstrip('-').lstrip('+').isnumeric()

def isFunc(v):
    return 'ridx()' in v or 'cidx()' in v

RE_TARGET_A  = re.compile(r'\s*(([@](?P<row>(?P<rsign>[+-])?([0-9]+)|([>]+)|([<]+)|[#])[$](?P<col>((?P<csign>[+-])?([0-9]+)|([>]+)|([<]+)|[#])|(ridx\(\))|(cidx\(\))))|([@](?P<rowonly>((?P<rosign>[+-])?([0-9]+)|([>]+)|([<]+)|[#])|(ridx\(\))|(cidx\(\))))|([$](?P<colonly>((?P<cosign>[+-])?([0-9]+)|([>]+)|([<]+)|[#])|(ridx\(\))|(cidx\(\)))))(?P<end>[^@$]|$)')
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
                        expr = RE_TARGET_A.sub(' getrowcell(' + str(row) + ',' + rs + ') ' + end,expr,1)
                    else:
                        expr = RE_TARGET_A.sub(' getrowcell(\'' + str(row) + '\''+","+rs+') ' + end,expr,1)
                else:
                    col = m.group('colonly')
                    cs = m.group('cosign')
                    cs = '1' if cs else '0'
                    if(isNumeric(col) or isFunc(col)):
                        expr = RE_TARGET_A.sub(' getcolcell(' + str(col) + ',' + cs + ') ' + end,expr,1)
                    else:
                        expr = RE_TARGET_A.sub(' getcolcell(\'' + str(col) + '\'' +","+cs+ ') ' + end,expr,1)
            else:
                rowmarkers = '' if isNumeric(row) or isFunc(row) else '\''
                colmarkers = '' if isNumeric(col) or isFunc(col) else '\''
                cs = '1' if cs else '0'
                rs = '1' if rs else '0'
                expr = RE_TARGET_A.sub(' getcell(' + rowmarkers + str(row) + rowmarkers + "," + rs + "," + colmarkers + str(col) + colmarkers + "," + cs + ") " + end,expr,1)
        else:
            break
    while(True):
        m = RE_SYMBOL_OR_CELL_NAME.search(expr)
        if(m):
            name = m.group('name')
            expr = RE_SYMBOL_OR_CELL_NAME.sub(' symorcell(\'' + name + '\') ',expr,1)
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

# ============================================================
class Formula:
    def __init__(self,raw, expr, reg, formatters, table):
        self.raw = raw
        self.table = table
        self.formatters = formatters
        self.printfout = None
        if(self.formatters):
            m = RE_PRINTFSTYLE.search(self.formatters)
            if(m):
                self.printfout = m.group('formatter')
        self.target, self.expr, self.rowFilter = formula_rowcol(expr,table)
        # print("TARGET: " + str(self.target) + " -> " + str(expr))
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

def CellRowIterator(table,start,end, arit=None, brit=None):
    c = table.CurCol()
    if not arit:
        arit = NullFilter()
    if not brit:
        brit = NullFilter()
    if(start < table.StartRow()):
        start = table.StartRow()
    for r in range(start,end+1):
        if(table.ShouldIgnoreRow(r) or arit.filter(r) or brit.filter(r)):
            continue
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
        if(table.ShouldIgnoreRow(r) or a.ShouldIgnoreRow(r) or b.ShouldIgnoreRow(r)):
            continue
        for c in range(sc,ec+1):
            cell = Cell(r,c,table)
            yield cell

def CellIterator(table,cell):
    r = cell.r
    c = cell.c
    filter = cell.rowFilter
    if(None == filter):
        filter = NullFilter()
    if(r == '*'):
        rrange = range(table.StartRow(),table.Height()+1)
    else:
        rrange = range(cell.GetRow(),cell.GetRow()+1)
    if(c == '*'):
        crange = range(table.StartCol(),table.Width()+1)
    else:
        crange = range(cell.GetCol(),cell.GetCol()+1)
    for r in rrange:
        if(table.ShouldIgnoreRow(r) or filter.filter(r)):
            continue
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
        if(table.ShouldIgnoreRow(r)):
            continue
        for c in crange:
            yield [r,c]

# ============================================================
# This represents a cell REFERENCE in the table.
# It has a reference to the table itself and looks
# up the actual data dynamically WHEN ASKED TO!
# That is important since the current target changes
# and many cell references are RELATIVE to the current
# target.
class Cell:
    def __init__(self,r,c,table,rrelative=0,crelative=0,rowFilter=None):
        self.r = r
        self.c = c
        self.table = table
        self.rrelative = rrelative
        self.crelative = crelative
        self.rowFilter = rowFilter

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

    def ShouldIgnoreRow(self, r):
        if(self.rowFilter):
            rv = self.rowFilter.filter(r)
            return rv
        return False

    def GetRow(self,height=None):
        r = None
        # We have to allow someone to pass in the height
        # because remote tables don't like to be truncated
        # to a local tables height!
        if(height == None):
            height = self.table.Height()
        if(isinstance(self.r,str)):
            if(self.r == "*"):
                r = self.table.CurRow()
            elif(self.r.startswith('>')):
                cnt = len(self.r.strip())
                r = height - (cnt-1)
            elif(self.r.startswith("<")):
                cnt = len(self.r.strip())
                r = self.table.StartRow() + (cnt-1)
            else:
                if(util.numberCheck(self.r)):
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
        if(r > height):
            r = height
        return r

    def GetCol(self,width=None):
        c = None
        # We have to allow someone to pass in the width
        # because remote tables don't like to be truncated
        # to a local tables width!
        if(width==None):
            width = self.table.Width()
        if(isinstance(self.c,str)):
            if(self.c == "*"):
                c = self.table.CurCol()
            elif(self.c.startswith(">")):
                cnt = len(self.c.strip())
                c = width - (cnt-1)
            elif(self.c.startswith("<")):
                cnt = len(self.c.strip())
                c = self.table.StartCol() + (cnt-1)
            else:
                if(util.numberCheck(self.c)):
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
        if(c > width):
            c = width
        return c

    def GetText(self):
        return self.table.GetCellText(self.GetRow(), self.GetCol())

    def GetInt(self):
        return int(self.GetText())

    def GetFloat(self):
        return float(self.GetText())

    def GetVal(self):
        txt = self.GetText().strip()
        if(util.numberCheck(txt)):
            if('.' in txt):
                return float(txt)
            return int(txt)
        if(txt.endswith("%")):
            t = txt[:-1]
            if(util.numberCheck(t)):
                f = float(t)
                f = (f / 100.0)
                return f
        l = txt.lower()
        if(l == "true" or l == "t"):
            return True
        if(l == "false"):
            return False
        return txt
    
    def GetNum(self):
        txt = self.GetText().strip()
        if(util.numberCheck(txt)):
            if('.' in txt):
                return float(txt)
            return int(txt)
        if(txt.endswith("%")):
            t = txt[:-1]
            if(util.numberCheck(t)):
                f = float(t)
                f = (f / 100.0)
                return f
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

RE_END = re.compile(r"^\s*\#\+(END_SRC|end_src)")
RE_SRC_BLOCK = re.compile(r"^\s*\#\+(BEGIN_SRC|begin_src)\s+(?P<name>[^: ]+)\s*")
def IsSourceFence(view,row):
    #line = view.getLine(view.curRow())
    line = view.getLine(row)
    return RE_SRC_BLOCK.search(line) or RE_END.search(line)

RE_ISCOMMENT = re.compile(r"^\s*[#][+]")
def LookupNamedSourceBlockInFile(name):
    view = sublime.active_window().active_view()
    if(view):
        node = db.Get().AtInView(view)
        if(node):
            # Look for named objects in the file.
            names = node.names
            if(names and name in names):
                row = names[name]['row']
                last_row = view.lastRow()
                for r in range(row,last_row):
                    if(IsSourceFence(view,r)):
                        row = r
                        break
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
                pt = view.text_point(row,0)
                reg = view.line(pt)
                line = view.substr(reg)
                if(IsSourceFence(view,row)):
                    return pt
    return None

# This class lets us run an arbitrary source block
# and place the result of that into a cell.
class SourceBlockExecute:
    def __init__(self,cell):
        self.cell = cell
        self.r = cell.GetRow()
        self.c = cell.GetCol()
        self.i = cell.table.GetActiveFormula()
        self.gotVal = False
        self.val = None

    def OnDoneFunction(self,otherParams=None):
        print("ON DONE FNCT")
        if('preFormat' in otherParams):
            data = otherParams['preFormat']
            print("PRE FORMAT: " + str(data))
            table = self.cell.table
            reg = table.FindCellRegion(self.r,self.c)
            fmt = table.FormulaFormatter(self.i)
            if(data and isinstance(data,float) and fmt and "%" in fmt):
                data = fmt % data
            print("REPLACING WITH: " + str(data))
            self.val = str(data)
            if(self.gotVal):
                sublime.active_window().active_view().run_command("org_internal_replace", {"start": reg.begin(), "end": reg.end(), "text": str(data)})

    def __getitem__(self,index):
        if(self.val):
            try:
                l = ast.literal_eval(self.val)
                rv = l[index]
                self.gotVal = True
                return rv
            except:
                pass
        return "<SBE>"

    def __str__(self):
        self.gotVal = True
        if(self.val):
            return str(self.val)
        else:
            return "<SBE>"

    def AdjustParams(self,otherParams=None):
        if('cmd' in otherParams):
            cmd = otherParams['cmd']
            self.cmd = cmd
            # We hack the results to be raw and silent with no formatting
            # output or value is not something we want to overwrite
            res = cmd.params.Get('results',None)
            if(res):
                if('value' in res):
                    cmd.params.Replace('results',['raw','silent','value'])
                else:
                    cmd.params.Replace('results',['raw','silent','output'])
            else:
                cmd.params.Replace('results',['raw', 'silent'])
            var = cmd.params.Get('var',None)
            if(var):
                for k in self.params:
                    var[k] = self.params[k]

    def run(self, name, kwargs):
        self.params = kwargs
        self.sourcefns = {}
        pt = LookupNamedSourceBlockInFile(name)
        if(None != pt):
            if(not name in self.sourcefns):
                self.sourcefns[name] = {'at': pt, 'name': name}
                sublime.active_window().active_view().run_command('org_execute_source_block',{'at':pt, 'onDoneResultsPos': evt.Make(self.OnDoneFunction), 'onDoneFnName': name, 'onAdjustParams': evt.Make(self.AdjustParams), 'silent': True, 'skipSaveWarning': True})



def myabs(a):
    """Convert value to a positive value"""
    return abs(GetVal(a))

def safe_mult(a, b):  # pylint: disable=invalid-name
    if hasattr(a, '__len__') and b * len(a) > MAX_STRING_LENGTH:
        raise IterableTooLong('Sorry, I will not evalute something that long.')
    if hasattr(b, '__len__') and a * len(b) > MAX_STRING_LENGTH:
        raise IterableTooLong('Sorry, I will not evalute something that long.')
    a = GetVal(a)
    b = GetVal(b)
    if(isinstance(a,float) or isinstance(b,float)):
        if(isinstance(a,str) or isinstance(b,str)):
            return 0
    return a * b

def safe_pow(a, b):  # pylint: disable=invalid-name
    a = GetVal(a)
    b = GetVal(b)
    if abs(a) > MAX_POWER or abs(b) > MAX_POWER:
        raise NumberTooHigh("Sorry! I don't want to evaluate {0} ** {1}"
                            .format(a, b))
    return a ** b


def safe_add(a, b):  # pylint: disable=invalid-name
    if hasattr(a, '__len__') and hasattr(b, '__len__'):
        if len(a) + len(b) > MAX_STRING_LENGTH:
            raise IterableTooLong("Sorry, adding those two together would"
                                  " make something too long.")
    a = GetVal(a)
    b = GetVal(b)
    return a + b

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
    """Computes the average value of a column or row. Takes a range of cells"""
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
    """Computes the sum of a range of cells"""
    s = 0
    for i in rng:
        s += GetNum(i)
    return s

def vmedian(rng):
    """Computes the median (middle) value of a sorted range of cells"""
    data = list(rng)
    for i in range(0,len(data)):
        data[i] = GetVal(data[i])
    data.sort()
    dl = len(data)
    v = math.floor(dl/2)
    if(dl == 1):
        return data[0]
    if(v*2 != dl):
        return data[v]
    else:
        if(v <= 0):
            return data[0]
        return (GetNum(data[v-1]) + GetNum(data[v]))/2.0

def vmax(rng):
    """Computes the max value of a range of cells"""
    m = -999999999
    for i in rng:
        num = GetNum(i)
        if(num > m):
            m = num
    return m

def vmin(rng):
    """Computes the minimum value of a range of cells"""
    m = 999999999
    for i in rng:
        num = GetNum(i)
        if(num < m):
            m = num
    return m

def mybool(num):
    """Explicitly convert value to a boolean value if possible"""
    v = GetVal(num)
    if(isinstance(v,str)):
        l = v.lower()
        if(l == "true" or l == "t"):
            return True
    if(v):
        return True
    return False

def myint(num):
    """Force a value to an integer"""
    v = GetVal(num)
    try:
        return int(v)
    except:
        return 0

def myfloat(num):
    """Force a value to a float"""
    v = GetVal(num)
    try:
        return float(v)
    except:
        return 0.0

def ClearAllOldCellHighlights():
    colors = ["green","red","orang","whit","black","purpl","yellow","cyan","blu"]
    for color in colors:
        hname = "myhighlight_" + color
        if color == "whit":
            style = "region.foreground"
        style = "region." + color + "ish"
        sublime.active_window().active_view().add_regions(hname,[],style,"",sublime.DRAW_NO_OUTLINE)
def ClearRegionFromOldHighlights(table,reg,newcolor):
    colors = ["green","red","orang","whit","black","purpl","yellow","cyan","blu"]
    for color in colors:
        if(color == newcolor):
            continue
        hname = "myhighlight_" + color
        regs = sublime.active_window().active_view().get_regions(hname)
        if(reg in regs):
            regs.remove(reg)
            style = "region." + color + "ish"
            if color == "whit":
                style = "region.foreground"
            sublime.active_window().active_view().add_regions(hname,regs,style,"",sublime.DRAW_NO_OUTLINE)

def postedithighlight(table,r,c,color,value):
    color = color.strip()
    if color.endswith("e"):
        color = color[:-1]
    style = "region." + color + "ish"
    if color == "whit":
        style = "region.foreground"
    reg = table.FindCellRegion(r,c)
    hname = "myhighlight_" + color
    regs = sublime.active_window().active_view().get_regions(hname)
    if(not reg in regs):
        regs.append(reg)
        ClearRegionFromOldHighlights(table,reg,color)
    sublime.active_window().active_view().add_regions(hname,regs,style,"",sublime.DRAW_NO_OUTLINE)
def myhighlight(cell,color,value=""):
    """highlight(cell,color,text) highlights a cell to one of: green,red,orange,white,black,purple,yellow,cyan and returns the text specified"""
    #sublime.active_window().active_view().add_regions("myhighlight",[],"","",sublime.DRAW_SOLID_UNDERLINE)
    a = cell.GetRow()
    b = cell.GetCol()
    cell.table.SetPostExecuteHook(lambda table,x=cell.GetRow(),y=cell.GetCol(),c=color,v=value: postedithighlight(table,x,y,c,v))
    return value


def myfloor(num):
    """Force a value to the previous integer"""
    v = GetNum(num)
    if(isinstance(v,float)):
        return math.floor(v)
    return num 

def myceil(num):
    """Force a value to the next integer"""
    v = GetNum(num)
    if(isinstance(v,float)):
        return math.ceil(v)
    return num 

def myround(num):
    """Round to the nearest integer"""
    v = GetNum(num)
    if(isinstance(v,float)):
        return round(v,0)
    return num 

def mytrunc(num):
    """Round down to the nearest int"""
    v = GetNum(num)
    if(isinstance(v,float)):
        return int(v)
    return num 

def GetTime(dt):
    if(isinstance(dt,Cell)):
        dt = mydate(dt)
    if(isinstance(dt,list) and len(dt) > 0):
        dt = dt[0]
    if(isinstance(dt,orgdate.OrgDate)):
        dt = dt.start
    return dt

def mynow():
    """Returns the current date time"""
    return orgdate.OrgDate(datetime.datetime.now())

def myyear(dt):
    """Get the year value from a datetime  - datetime.time().year"""
    dt = GetTime(dt)
    return dt.year

def myday(dt):
    """Get the day value from a datetime  - datetime.time().day"""
    dt = GetTime(dt)
    return dt.day

def mymonth(dt):
    """Get the month value from a datetime - datetime.time().month"""
    dt = GetTime(dt)
    return dt.month

def myhour(dt):
    """Get the hours value from a datetime - datetime.time().hour"""
    dt = GetTime(dt)
    return dt.hour

def myminute(dt):
    """Get the minutes value from a datetime - datetime.time().minute"""
    dt = GetTime(dt)
    return dt.minute

def mysecond(dt):
    """Get the seconds value from a datetime - datetime.time().second"""
    dt = GetTime(dt)
    return dt.second

def myweekday(dt):
    """Get an index for the day of the week where monday is 0"""
    dt = GetTime(dt)
    return dt.date().weekday()

def myyearday(dt):
    """Get the numerical day of the year where jan 1 is 1"""
    dt = GetTime(dt)
    return dt.timetuple().tm_yday

def mytime(dt):
    """Return the current time from a datetime object time(datetime)"""
    dt = GetTime(dt)
    return dt.time()

LINK_RE = re.compile(r'^\s*\[\[(file:)?(?P<filepath>.+?)(((::(?P<row>\d+))(::(?P<col>\d+))?)|(::\#(?P<cid>[a-zA-Z0-9!$@%&_-]+))|(::\*(?P<heading>[a-zA-Z0-9!$@%&_-]+))|(::(?P<textmatch>[a-zA-Z0-9!$@%&_-]+)))?\s*\]\s*(\]|\s*\[.*\])')
def mylocalfile(obj):
    """Convert a local filename or link into an absolute filename"""
    txt = GetVal(obj)
    m = LINK_RE.search(txt)
    if(m):
        txt = m.group('filepath')
    txt = txt.strip()
    # We assume this is an abs path
    if(txt.startswith('/') or (len(txt) > 3 and txt[2] == ':' and (txt[3] == '\\' or txt[3] == '/'))):
        return txt
    else:
        p = sublime.active_window().active_view().file_name()
        if(p):
            p = os.path.dirname(p)
            txt = os.path.normpath(os.path.join(p,txt))
    return txt

# Not currently used, the python if is forced on us due to the use
# of the AST backend. I could convert from this to that with an RE
# but I am not yet sure that's a good idea.
def myif(test,a,b=None):
    v = GetVal(test)
    if(isinstance(v,str)):
        if(v.strip() != ""):
            return a
        else:
            return b
    elif(isinstance(v,int)):
        if(v):
            return a
        else:
            return b
    else:
        if(test):
            return a
        return b

def myduration(dt):
    """Convert to a timespan value"""
    if(isinstance(dt,Cell)):
        return orgduration.OrgDuration.Parse(dt.GetText())
    if(isinstance(dt,str)):
        return orgduration.OrgDuration.Parse(dt)
    return dt

def mydate(dt):
    """Convert string to a date value"""
    if(isinstance(dt,Cell)):
        rc = orgdate.OrgDate.list_from_str(dt.GetText())
        if(len(rc) == 0):
            log.debug("ERROR: date function failed to parse date? " + str(dt.GetText()))
            traceback.print_stack()
        if(len(rc) == 1):
            return rc[0]
        return rc
    if(isinstance(dt,str)):
        rc = orgdate.OrgDate.list_from_str(dt)
        if(len(rc) == 1):
            return rc[0]
        return rc
    elif(isinstance(dt,datetime.datetime)):
        return dt.date()
    elif(isinstance(dt,datetime.date)):
        return dt
    return None

def randomDigit(start, end):
    """Returns a random value in a range specified start..end"""
    return random.randint(GetVal(start),GetVal(end))

def randomFloat():
    """Returns a random value from 0..1"""
    return random.randint(0,1000000)/1000000.0

def degrees(cell):
    """Convert from radians to degress"""
    return math.degrees(GetNum(cell))

def radians(cell):
    """Convert from degrees to radians"""
    return math.radians(GetNum(cell))

def tan(cell):
    """Return the tangent of x radians."""
    return math.tan(GetNum(cell))

def sin(cell):
    """Return the sine of x radians."""
    return math.sin(GetNum(cell))

def cos(cell):
    """Return the cosine of x radians."""
    return math.cos(GetNum(cell))

def atan(cell):
    """Return the arc tangent of x radians."""
    return math.atan(GetNum(cell))

def asin(cell):
    """Return the arc sine of x radians."""
    return math.asin(GetNum(cell))

def acos(cell):
    """Return the arc cosine of x radians."""
    return math.acos(GetNum(cell))

def tanh(cell):
    """Return the hyperbolic tangent of x."""
    return math.tanh(GetNum(cell))

def sinh(cell):
    """Return the hyperbolic sine of x."""
    return math.sinh(GetNum(cell))

def cosh(cell):
    """Return the hyperbolic cosine of x."""
    return math.cosh(GetNum(cell))

def atanh(cell):
    """Return the inverse hyperbolic tangent of x."""
    return math.atanh(GetNum(cell))

def asinh(cell):
    """Return the inverse hyperbolic sine of x."""
    return math.asinh(GetNum(cell))

def acosh(cell):
    """Return the inverse hyperbolic cosine of x."""
    return math.acosh(GetNum(cell))

def exp(cell):
    """Return e raised to the power x, where e = 2.718281"""
    return math.exp(GetNum(cell))

def pow(x,y):
    """Return x raised to the power y"""
    return math.pow(GetNum(x),GetNum(y))

def mylog(x):
    """Return the natural logarithm of x (to base e)."""
    return math.log(x)

def mylog10(x):
    """Return the base-10 logarithm of x."""
    return math.log10(x)

def mylog2(x):
    """Return the base-2 logarithm of x."""
    return math.log2(x)

def sqrt(x):
    """Return the square root of x."""
    return math.sqrt(x)

def LookupNamedTableInFile(name):
    td = None
    view = sublime.active_window().active_view()
    if(view):
        node = db.Get().AtInView(view)
        if(node):
            # Look for named objects in the file.
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
                pt = view.text_point(row,0)
                if(isTable(view, pt)):
                    td = create_table(view,pt)
    return td

def LookupTableFromId(name):
    td = None
    file, row = db.Get().FindByAnyId(name)
    if(file):
        node = file.At(row)
        if(node and node.table):
            td = create_table_from_node(node, node.table['nodeoff'][0])
    return td

def LookupTableFromNamedObject(name):
    # First search for a named table from the ID
    td = LookupNamedTableInFile(name)
    if(not td):
        # Okay use the custom ID rule to try to get the
        # table.
        td = LookupTableFromId(name)
    return td

def remote(name,cellRef):
    """remote('table-name OR custom-id-value',cellRef) returns a cell from a remote table.
       table-name only works local to a file while custom-id or id will look up the first table
       in a heading marked with that id.
    """
    td = LookupTableFromNamedObject(name)
    if(td):
        text = td.GetCellText(cellRef.GetRow(td.Height()),cellRef.GetCol(td.Width()))
        return text
    return "<UNK REF>"

# ============================================================
class RangeExprOnNonCells(simpev.InvalidExpression):
    def __init__(self,name,expression):
        self.name = name
        self.message = "both sides of a range expression must be a cell definition"
        self.expression = expression
        # pylint: disable=bad-super-call
        super(RangeExprOnNonCells, self).__init__(self.message)

# These filters are used for naming cells above or below a certain point.
# The symbolOrCell system uses this when iterating to filter out cells that
# do not belong.
class NullFilter:
    def filter(self,x):
        return False
class AboveFilter:
    def __init__(self,r):
        self.r = r
    def filter(self,x):
        return x >= self.r
class BelowFilter:
    def __init__(self,r):
        self.r = r
    def filter(self,x):
        return x <= self.r

def checkPassed(txt):
    txt = GetVal(txt)
    if(isinstance(txt,str)):
        txt = txt.strip()
        return txt != "<ERR>" and txt != "<UNK REF>"
    return txt

# ============================================================
class TableDef(simpev.SimpleEval):
    def range_expr(self,a,b):
        if(isinstance(a,Cell) and isinstance(b,Cell)):
            if(a.r == "*" and b.r == "*"):
                return CellColIterator(a.table, a.GetCol(), b.GetCol())
            elif(a.c == "*" and b.c == "*"):
                return CellRowIterator(a.table, a.GetRow(), b.GetRow(), a.rowFilter, b.rowFilter)
            elif(a.r != '*' and b.r != '*' and a.c != '*' and b.c != '*'):
                return CellBoxIterator(a.table,a,b)
            else:
                raise RangeExprOnNonCells("End cells must be wild of same type", "range expression is invalid")
        else:
            raise RangeExprOnNonCells(str(a), "range expression is invalid")

    def mysbe(table, name,**kwargs):
        view = sublime.active_window().active_view()
        cell = Cell(table.CurRow(),table.CurCol(),table)
        sbe = SourceBlockExecute(cell)
        sbe.run(name,kwargs)
        print(name)
        print(str(kwargs))
        return sbe

    def mypassed(table,test,cell=None):
        if(not cell):
            cell = Cell(table.CurRow(),table.CurCol(),table)
        if(checkPassed(test)):
            return myhighlight(cell,"green","PASSED")
        else:
            return myhighlight(cell,"red","FAILED")

    def SetPostExecuteHook(self,fun):
        self.postExecute.append(fun)

    def ForEachRow(self):
        return range(1,self.Height() + 1)
    
    def ForEachCol(self):
        return range(1,self.Width() + 1)

    def ShouldIgnoreRow(self,row):
        return row in self.ignoreRows

    def ridx(self):
        return self.CurRow()
    
    def cidx(self):
        return self.CurCol()

    def getrowcell(self,r,relative):
        return Cell(r,'*',self,relative,0)

    def getcolcell(self,c,relative):
        return Cell('*',c,self,0,relative)

    def getcell(self,r,rrelative,c,crelative):
        return Cell(r,c,self,rrelative,crelative)

    def symbolOrCell(self,name):
        if name in self.nameToCell:
            return self.nameToCell[name]
        if(name in self.consts):
            v = self.consts[name].strip()
            if(util.numberCheck(v)):
                if('.' in v):
                    return float(v)
                else:
                    return int(v)
            return v

    def ClearAllRegions(self):
        for r in range(1,(self.end+2)-self.start):
            self.view.erase_regions("cell_"+str(r))
            if(not self.linedef):
                continue
            for c in range(1,len(self.linedef)):
                self.view.erase_regions("cell__"+str(c))
                self.view.erase_regions("cell_"+str(r)+"_"+str(c))
        for i in range(0,self.NumFormulas()):
            self.view.erase_regions("fmla_"+str(i))


    def add_functions(self,f):
        f['ridx']       = self.ridx
        f['cidx']       = self.cidx
        f['symorcell']  = self.symbolOrCell
        f['getcell']    = self.getcell
        f['getrowcell'] = self.getrowcell
        f['getcolcell'] = self.getcolcell
        f['passed']     = self.mypassed
        f['sbe']        = self.mysbe


    def __init__(self,view, start,end,linedef):
        self.names     = GetConsts().copy()
        self.operators = GetOps().copy()
        self.operators[ast.FloorDiv] = self.range_expr
        self.functions = GetFunctions().copy()
        self.add_functions(self.functions)
        super(TableDef,self).__init__(self.operators, self.functions, self.names)
        self.curRow  = 0
        self.curCol  = 0
        self.start   = start
        self.end     = end
        self.view    = view
        self.linedef = linedef
        self.cellToFormula = None
        self.accessList    = []
        self.consts        = {}
        self.emptyiszero   = False
        self.startCol      = 1

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

    def GetActiveFormula(self):
        return self.activeFormula

    def SetActiveFormula(self,i):
        self.activeFormula = i

    def GetCellText(self,r,c):
        self.accessList.append([r,c])
        if(isinstance(self.view,sublime.View)):
            reg = self.FindCellRegion(r,c)
            if(reg):
                text = self.view.substr(reg)
                if(self.emptyiszero and text.strip() == ""):
                    return "0"
                return text
            if(self.emptyiszero):
                return "0"
        else:
            row,cs,ce = self.FindCellNodeRegion(r,c)
            text = self.view._lines[row]
            cell = text[cs+1:ce].strip()
            if(self.emptyiszero and cell == ""):
                return "0"
            return cell
        return ""
    def FindCellRegion(self,r,c):
        if(not r in self.lineToRow):
            return None
        row = self.lineToRow[r]
        #row = self.start + (r-1)       # 1 is zero
        colstart = self.linedef[c-1] 
        colend   = self.linedef[c]
        return sublime.Region(self.view.text_point(row,colstart+1),self.view.text_point(row,colend)) 
    def FindCellNodeRegion(self,r,c):
        if(not r in self.lineToRow):
            return None
        row = self.lineToRow[r]
        #row = self.start + (r-1)       # 1 is zero
        colstart = self.linedef[c-1] 
        colend   = self.linedef[c]
        return (row,colstart,colend)
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
        rc = self.view.curRowCol()
        if(not rc): 
            return None
        row,col = rc
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
        rc = self.view.curRowCol()
        if(rc):
            row,col = rc
            r = self.RowToCellRow(row)
            c = self.FindCellColFromCol(col)
            return [r,c]
        return None

    def CellToFormula(self, cell):
        r,c = cell
        if(self.cellToFormula):
            if(r in self.cellToFormula and c in self.cellToFormula[r]):
                return self.cellToFormula[r][c]
        return None

    def HighlightFormula(self, i):
        self.PreExecute()
        if(not hasattr(self,'highlight') or self.highlight):
            it = SingleFormulaIterator(self,i)
            for n in it:
                r,c,val,reg,_ = n
                # This is important, the cell COULD return a cell
                # until we convert it to a string that cell will not
                # necessarily be touched so the accessList will not be
                # correct.
                valStr = str(val)
                self.HighlightCells(self.accessList,1)
                self.HighlightCells([[r,c]],2)
        self.HighlightFormulaRegion(i)
        self.PostExecute()

    def GetFormula(self,i):
        return self.formulas[i]

    def FormulaTarget(self, i):
        dm = self.formulas[i]
        return dm.target

    def FormulaTargetRowFilter(self, i):
        dm = self.formulas[i]
        return dm.rowFilter

    def ValidateFormulaCells(self,i):
        if("INVALID" in self.formulas[i].formula):
            sublime.status_message("ORG Table WARNING: Formula {0} is targetting an invalid cell!".format(i))

    def FormulaTargetCellIterator(self, i):
        target = self.FormulaTarget(i)
        rowFilter = self.FormulaTargetRowFilter(i)
        self.ValidateFormulaCells(i)
        if(len(target) == 4):
            cellStart = Cell(target[0],target[1],self,rowFilter = rowFilter)
            cellEnd = Cell(target[2],target[3],self,rowFilter = rowFilter)
            cellIterator = CellBoxIterator(self,cellStart,cellEnd)
        else:
            cell = Cell(target[0],target[1],self,rowFilter=rowFilter)
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
    
    def BuildNameMap(self):
        self.nameToCell = {}
        for r,row in self.colNames:
            for c in range(1,self.Width()+1):
                txt = self.GetCellText(r,c).strip()
                if(not txt == "" and txt[0].isalpha()):
                    self.nameToCell[txt] = Cell('*', c, self)
        for r,row in self.nameRowsAbove:
            for c in range(1,self.Width()+1):
                txt = self.GetCellText(r,c).strip()
                if(not txt == "" and txt[0].isalpha()):
                    f = AboveFilter(r)
                    self.nameToCell[txt] = Cell('*', c, self, rowFilter = f)
        for r,row in self.nameRowsBelow:
            for c in range(1,self.Width()+1):
                txt = self.GetCellText(r,c).strip()
                if(not txt == "" and txt[0].isalpha()):
                    f = BelowFilter(r)
                    self.nameToCell[txt] = Cell('*', c, self, rowFilter = f)

    def PreExecute(self):
        self.postExecute = []

    def PostExecute(self):
        for fun in self.postExecute:
            fun(self)

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
    if(isinstance(view,sublime.View)):
        pt = view.text_point(row, 0)
        line = view.substr(view.line(pt))
        linedef = None
        if(not RE_TABLE_HLINE.search(line) and RE_TABLE_LINE.search(line)):
            linedef = findOccurrences(line,'|')
        return linedef
    else:
        line = view._lines[row]
        linedef = None
        if(not RE_TABLE_HLINE.search(line) and RE_TABLE_LINE.search(line)):
            linedef = findOccurrences(line,'|')
        return linedef

# ====================================================================
# CREATE TABLE
# ====================================================================
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
        if(RE_TABLE_LINE.search(line) or RE_TABLE_HLINE.search(line) or RE_END_BLOCK.search(line)):
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
    ignoreRows = {}
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
                char = mm.group('a')
                if(char != ' '):
                    isAdvanced = True
                # Name row
                if(char == '!'):
                    ignoreRows[rowNum] = r
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
                    ignoreRows[rowNum] = r
                    ignore.append((rowNum,r))
                    pass
                # Name below
                elif(char == "_"):
                    ignoreRows[rowNum] = r
                    namesRowsBelow.append((rowNum,r))
                    ignore.append((rowNum,r))
                    pass
                # Name above
                elif(char == "^"):
                    ignoreRows[rowNum] = r
                    namesRowsAbove.append((rowNum,r))
                    ignore.append((rowNum,r))
                    pass
                elif(char == "$"):
                    ignoreRows[rowNum] = r
                    parameters.append((rowNum,r))
                    ignore.append((rowNum,r))
                else:
                    ignoreRows[rowNum] = r
                    ignore.append((rowNum,r))
                    pass
                lineToRow[rowNum] = r
            else:
                lineToRow[rowNum] = r
            continue
        # Found a formula break!
        elif(m):
            formula = m.group('expr').split('::')
            formulaRow = r
            formulaLine = line
            if(lastRow == 0):
                end = r-1
                lastRow = rowNum - 1
            break
        else:
            endb = RE_END_BLOCK.search(line)
            # We keep going for blank lines allowing #TBLFM lines with spaces to
            # be okay OR tables inside dynamic blocks (RE above)
            if(line.strip() == "" or endb):
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
    td.highlight     = True
    if(isAdvanced):
        td.ignore        = ignore
        td.ignoreRows    = ignoreRows
    else:
        td.ignore     = []
        td.ignoreRows = {}
    if(isAdvanced):
        td.startCol = 2
        td.BuildNameMap()
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
            if(hasattr(node,'properties')):
                props = node.properties
                if('NoTableHighlight' in props):
                    td.highlight = False
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
    if(formula):
        sre = re.compile(r'\s*[#][+]((TBLFM)|(tblfm))[:]')
        first = sre.match(formulaLine)
        if(first):
            lastend = len(first.group(0))
            xline = sre.sub('',formulaLine)
            las = xline.split('::')
            index = 0
            for fm in formula:
                raw = fm.strip()
                formatters = fm.split(';')
                if(len(formatters) > 1):
                    fm = formatters[0]
                    formatters = formatters[1]
                else:
                    formatters = ""
                fend = lastend+len(las[index])
                td.formulas.append(Formula(raw,fm, sublime.Region(view.text_point(formulaRow,lastend),view.text_point(formulaRow,fend)),formatters,td))
                index += 1
                lastend = fend + 2
        td.BuildCellToFormulaMap()
    # 
    return td

# CREATE TABLE FROM NODE
# Figure out a way to get rid of this duplication!
# ====================================================================
def create_table_from_node(node, row):
    start_row = row
    lineData = node._lines
    last_row  = len(lineData)
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
        line = lineData[r]
        if(RE_TABLE_LINE.search(line) or RE_TABLE_HLINE.search(line) or RE_END_BLOCK.search(line)):
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
    ignoreRows = {}
    for r in range(row,last_row):
        rowNum += 1
        line = lineData[r]
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
                char = mm.group('a')
                if(char != ' '):
                    isAdvanced = True
                # Name row
                if(char == '!'):
                    ignoreRows[rowNum] = r
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
                    ignoreRows[rowNum] = r
                    ignore.append((rowNum,r))
                    pass
                # Name below
                elif(char == "_"):
                    ignoreRows[rowNum] = r
                    namesRowsBelow.append((rowNum,r))
                    ignore.append((rowNum,r))
                    pass
                # Name above
                elif(char == "^"):
                    ignoreRows[rowNum] = r
                    namesRowsAbove.append((rowNum,r))
                    ignore.append((rowNum,r))
                    pass
                elif(char == "$"):
                    ignoreRows[rowNum] = r
                    parameters.append((rowNum,r))
                    ignore.append((rowNum,r))
                else:
                    ignoreRows[rowNum] = r
                    ignore.append((rowNum,r))
                    pass
                lineToRow[rowNum] = r
            else:
                lineToRow[rowNum] = r
            continue
        # Found a formula break!
        elif(m):
            formula = m.group('expr').split('::')
            formulaRow = r
            formulaLine = line
            if(lastRow == 0):
                end = r-1
                lastRow = rowNum - 1
            break
        else:
            endb = RE_END_BLOCK.search(line)
            # We keep going for blank lines allowing #TBLFM lines with spaces to
            # be okay OR tables inside dynamic blocks (RE above)
            if(line.strip() == "" or endb):
                if(lastRow == 0):
                    spacesRow = r
                    if(lastRow == 0):
                        end = r-1
                        lastRow = rowNum - 1
                continue
            else:
                if(lastRow == 0):
                    end = r-1
                    lastRow = rowNum - 1
            break
    for r in range(row,0,-1):
        line = lineData[r]
        if(RE_TABLE_LINE.search(line)):
            continue
        else:
            start = r+1
            break
    td = TableDef(node, start, end, linedef)
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
    if(isAdvanced):
        td.ignore        = ignore
        td.ignoreRows    = ignoreRows
    else:
        td.ignore     = []
        td.ignoreRows = {}
    if(isAdvanced):
        td.startCol = 2
        td.BuildNameMap()
    if(td):
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
            if(hasattr(node,'properties')):
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
    if(formula):
        sre = re.compile(r'\s*[#][+]((TBLFM)|(tblfm))[:]')
        first = sre.match(formulaLine)
        if(first):
            lastend = len(first.group(0))
            xline = sre.sub('',formulaLine)
            las = xline.split('::')
            index = 0
            for fm in formula:
                raw = fm.strip()
                formatters = fm.split(';')
                if(len(formatters) > 1):
                    fm = formatters[0]
                    formatters = formatters[1]
                else:
                    formatters = ""
                fend = lastend+len(las[index])
                td.formulas.append(Formula(raw,fm, None,formatters,td))
                index += 1
                lastend = fend + 2
        td.BuildCellToFormulaMap()
    # 
    return td

def SingleFormulaIterator(table,i):
    table.SetActiveFormula(i)
    cellIterator = table.FormulaTargetCellIterator(i) 
    for cell in cellIterator:
        r,c = cell.rc()
        table.SetCurRow(r)
        table.SetCurCol(c)
        val = table.Execute(i)
        yield [r,c,val,table.FindCellRegion(r,c),table.FormulaFormatter(i)]

def FormulaIterator(table):
    for i in range(0,table.NumFormulas()):
        table.SetActiveFormula(i)
        cellIterator = table.FormulaTargetCellIterator(i) 
        for cell in cellIterator:
            r,c = cell.rc()
            table.SetCurRow(r)
            table.SetCurCol(c)
            val = table.Execute(i)
            yield (r,c,val,table.FindCellRegion(r,c),table.FormulaFormatter(i))
    return None

# ================================================================================
class OrgExecuteFormulaCommand(sublime_plugin.TextCommand):
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
        global highlightEnabled
        highlightEnabled = True
        self.td.PostExecute()
        if(None != self.origCur):
            self.view.sel().clear()
            self.view.sel().add(self.origCur)
        evt.EmitIf(self.onDone)

    def on_formula_copy_done(self):
        if(None != self.at):
            self.view.sel().clear()
            self.view.sel().add(self.at)
        # Working on formula handling
        self.td = create_table(self.view)
        self.td.ClearAllRegions()
        self.td.PreExecute()
        formulaIdx = self.td.GetFormulaAt()
        self.it = SingleFormulaIterator(self.td,formulaIdx)
        self.process_next()

    def run(self, edit,onDone=None,skipFormula=None,at=None,clearHighlights=True):
        global highlightEnabled
        highlightEnabled = False
        self.at = at
        if(self.view.sel()):
            self.origCur = self.view.sel()[0]
        if(clearHighlights):
            ClearAllOldCellHighlights()
        self.onDone = onDone
        if(skipFormula):
            self.on_formula_copy_done()
        else:
            self.view.run_command('org_fill_in_formula_from_cell',{"onDone": evt.Make(self.on_formula_copy_done), "at": at,"clearHighlights":clearHighlights})
        #td.HighlightFormula(i)
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
        global highlightEnabled
        highlightEnabled = True
        self.td.PostExecute()
        if(None != self.origCur):
            self.view.sel().clear()
            self.view.sel().add(self.origCur)
        evt.EmitIf(self.onDone)

    def on_formula_copy_done(self):
        if(None != self.at):
            self.view.sel().clear()
            self.view.sel().add(self.at)
        # Working on formula handling
        self.td = create_table(self.view)
        self.td.ClearAllRegions()
        self.td.PreExecute()
        self.it = FormulaIterator(self.td)
        self.process_next()

    def run(self, edit,onDone=None,skipFormula=None,at=None,clearHighlights=True):
        global highlightEnabled
        highlightEnabled = False
        self.at = at
        if(self.view.sel()):
            self.origCur = self.view.sel()[0]
        if(clearHighlights):
            ClearAllOldCellHighlights()
        self.onDone = onDone
        if(skipFormula):
            self.on_formula_copy_done()
        else:
            self.view.run_command('org_fill_in_formula_from_cell',{"onDone": evt.Make(self.on_formula_copy_done), "at": at,"clearHighlights":clearHighlights})
        #td.HighlightFormula(i)


# ================================================================================
class OrgExecuteAllTablesCommand(sublime_plugin.TextCommand):

    def continueRun(self):
        for r in range(self.cur,self.last_row):
            self.cur = r
            pt = self.view.text_point(r,1)
            if(not self.inTable and isTable(self.view,pt)):
                self.view.run_command('org_execute_table',{"at":pt,"onDone":evt.Make(self.continueRun),"clearHighlights":False})
                self.inTable = True
                break
            elif(self.inTable and not isTable(self.view,pt)):
                self.inTable = False

    def run(self,edit,at=None):
        global tableCache
        self.last_row = self.view.endRow()
        self.cur = 0
        self.inTable = False
        self.continueRun()


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
class OrgEditFormulaForCellCommand(sublime_plugin.TextCommand):
    def run(self,edit,onDone=None):
        global tableCache
        td = tableCache.GetTable(self.view)
        if(td):
            td.ClearAllRegions()
            formulaIdx = td.GetFormulaAt()
            if(None != formulaIdx):
                r,c = td.CursorToCell()
                fml = td.GetFormula(formulaIdx)
                reg = td.FindCellRegion(r,c)
                self.view.run_command("org_internal_replace", {"start": reg.begin(), "end": reg.end(), "text": str(fml.raw), "onDone": onDone})

# ================================================================================
class OrgClearCellCommand(sublime_plugin.TextCommand):
    def on_done(self):
        self.view.run_command('table_editor_align')
        evt.EmitIf(self.onDone)
    def run(self,edit,onDone=None):
        global tableCache
        self.onDone = onDone
        td = tableCache.GetTable(self.view)
        if(td):
            td.ClearAllRegions()
            r,c = td.CursorToCell()
            reg = td.FindCellRegion(r,c)
            self.view.run_command("org_internal_replace", {"start": reg.begin(), "end": reg.end(), "text": "", "onDone": evt.Make(self.on_done)})
            
# ================================================================================
class OrgTableAutoComputeCommand(sublime_plugin.TextCommand):
    def on_reformat(self):
        self.on_done()

    def on_done_cell(self):
        self.view.sel().clear()
        self.view.sel().add(self.result[3])
        self.view.run_command('table_editor_align')
        sublime.set_timeout(self.on_reformat,1)

    def on_done(self):
        global highlightEnabled
        highlightEnabled = True
        evt.EmitIf(self.onDone)

    def run(self,edit,onDone = None):
        global highlightEnabled
        highlightEnabled = False
        self.onDone = onDone
        global tableCache
        td = tableCache.GetTable(self.view)
        if(td):
            cell = td.CursorToCell()
            formulaIdx = td.GetFormulaAt()
            if(None != formulaIdx):
                it = SingleFormulaIterator(td,formulaIdx)
                for n in it:
                    r,c,val,reg,_ = n
                    if(r == cell[0] and c == cell[1]):
                        self.result = n
                        fmt = td.FormulaFormatter(formulaIdx)
                        if(val and isinstance(val,float) and fmt and "%" in fmt):
                            val = fmt % val
                        self.view.run_command("org_internal_replace", {"start": reg.begin(), "end": reg.end(), "text": str(val), "onDone": evt.Make(self.on_done_cell)})

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
            if(None != self.origCur):
                self.view.sel().clear()
                self.view.sel().add(self.origCur)
            evt.EmitIf(self.onDone)
        else:
            self.view.run_command('org_execute_table',{'skipFormula': True,'at': self.at})

    def run(self,edit,onDone=None,at=None,clearHighlights=True):
        self.onDone = onDone
        self.origCur = None
        self.at = at
        if(self.view.sel()):
            self.origCur = self.view.sel()[0]
        if(None != at):
            self.view.sel().clear()
            self.view.sel().add(at)
        if(clearHighlights):
            ClearAllOldCellHighlights()
        if(isTable(self.view)):
            while(not isTable(self.view) or isTableFormula(self.view)):
                # Cannot align on the table formula line
                row = self.view.curRow()
                pt = self.view.text_point(row-1,0)
                self.view.sel().clear()
                self.view.sel().add(pt)
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
        self.updating = None
  
    def GetTable(self):
        if(isTable(self.view)):
            return tableCache.GetTable(self.view)
        return None

    def on_query_completions(self, prefix, locations):
        if not self.view.match_selector(locations[0], "text.orgmode"):
            return []
        self.files = []
        if(self.view.match_selector(locations[0],"orgmode.link")):
            line = self.view.substr(self.view.line(locations[0]))
            lastsq = len(line)-1
            pp = None
            for i in range(len(line)-1,0,-1):
                if(line[i] == ']'):
                    lastsq = i
                if(line[i] == '[' and i > 0 and line[i-1] == '['):
                    pp = line[i+1:lastsq]
                    break
            if(None == pp):
                return []
            for i in range(0,len(db.Get().Files)):
                filename = db.Get().Files[i].filename
                if(re.search(".*"+pp+".*",filename)):
                    self.files.append([os.path.basename(filename),"file:"+self.view.MakeRelativeToMe(filename)+"][$0"])
        if(int(sublime.version()) <= 4096):
            return (self.files,sublime.INHIBIT_EXPLICIT_COMPLETIONS|sublime.INHIBIT_WORD_COMPLETIONS)
        else:
            return (self.files,sublime.INHIBIT_EXPLICIT_COMPLETIONS|sublime.INHIBIT_WORD_COMPLETIONS|sublime.DYNAMIC_COMPLETIONS)

        

    def on_selection_modified(self):
        global highlightEnabled
        if(not highlightEnabled):
            return
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

    def on_activated(self):
        if(not self.updating and util.isPotentialOrgFile(self.view.file_name()) and sets.Get("backlinksUpdate",True)):
            # We do this to avoid recursive update on refocus
            self.updating = True
            olinks.UpdateBacklinksForDisplay(self.view)
            self.updating = False

    def on_text_command(self, command_name, args=None):
        if('table_editor' in command_name):
            td = self.GetTable()
            self.preCell = None
            self.preRow,col = self.view.curRowCol()
            if(td):
                self.preCell = td.CursorToCell()
                self.hlines  = td.hlines
                if(isAutoComputeRow(self.view)):
                    self.view.run_command("org_table_auto_compute")
    def on_post_text_command(self, command_name, args= None):
        global highlightEnabled
        if(not highlightEnabled):
            return
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



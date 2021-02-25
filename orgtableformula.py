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
import math
import ast
import operator as op


log = logging.getLogger(__name__)

def isTable(view):
    names = view.scope_name(view.sel()[0].end())
    return 'orgmode.table' in names


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

RE_TARGET = re.compile(r'\s*([@](?P<row>[0-9]+))?([$](?P<col>[0-9]+))?([@](?P<row2>[0-9]+))?\s*')
def formula_rowcol(expr):
    fields = expr.split('=')
    if(len(fields) != 2):
        return (None, None)
    target = fields[0]
    print(target)
    m = RE_TARGET.search(target)
    if(m):
        row = m.group('row')
        col = m.group('col')
        if(not row):
            row = m.group('row2')
        else:
            row = int(row)
        if not row:
            row = '*'
        else:
            row = int(row)
        if not col:
            col = '*'
        else:
            col = int(col)
        return ([row, col], fields[1])
        pass
    return (None, None)


#class EvalNoMethods(simpleeval.SimpleEval):
#    def _eval_call(self, node):
#        if isinstance(node.func, ast.Attribute):
#            raise simpleeval.FeatureNotAvailable("No methods please, we're British")
#        return super(EvalNoMethods, self)._eval_call(node)




class Formula:
    def __init__(self,expr):
        self.target, self.expr = formula_rowcol(expr)
        self.expr = self.expr.replace("@","r").replace("$","c").replace("..","//")
        self.formula   = expr

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
    sr = a.r
    er = b.r
    if(a.r > b.r):
        sr = b.r
        er = a.r
    sc = a.c
    ec = b.c
    if(a.c > b.c):
        sc = b.c
        ec = a.c
    if(sr < table.StartRow()):
        sr = table.StartRow()
    for r in range(sr,er+1):
        for c in range(sc,ec+1):
            cell = Cell(r,c,table)
            yield cell

def CellIterator(table,cell):
    r = cell.r
    c = cell.c
    print("START ROW: " + str(table.StartRow()))
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
    def __init__(self,r,c,table):
        self.r = r
        self.c = c
        self.table = table

    def __str__(self):
        return self.GetText()

    def __eq__(self, other):
        if isinstance(other, Cell):
            if self.r == other.r and self.c == other.c:
                return True
            return self.GetText() == other.GetText()
        return NotImplemented 

    def GetRow(self):
        if(self.r == "*"):
            return self.table.CurRow()
        return self.r

    def GetCol(self):
        if(self.c == "*"):
            return self.table.CurCol()
        return self.c

    def GetText(self):
        return self.table.GetCellText(self.GetRow(), self.GetCol())

    def GetInt(self):
        return int(self.GetText())

    def GetFloat(self):
        return float(self.GetText())

    def GetVal(self):
        txt = self.GetText().strip()
        if(txt.isnumeric()):
            if('.' in txt):
                return float(txt)
            return int(txt)
        return txt
    
    def GetNum(self):
        txt = self.GetText().strip()
        if(txt.isnumeric()):
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
    return GetVal(a) / GetVal(b)

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

def tan(cell):
    return math.tan(GetNum(cell))

def sin(cell):
    return math.sin(GetNum(cell))

def cos(cell):
    return math.cos(GetNum(cell))

def exp(cell):
    return math.exp(GetNum(cell))

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
                return CellColIterator(a.table, a.c, b.c)
            elif(a.c == "*" and b.c == "*"):
                return CellRowIterator(a.table, a.r, b.r)
            elif(a.r != '*' and b.r != '*' and a.c != '*' and b.c != '*'):
                return CellBoxIterator(a.table,a,b)
            else:
                raise RangeExprOnNonCells("End cells must be wild of same type", "range expression is invalid")
        else:
            raise RangeExprOnNonCells(str(a), "range expression is invalid")
    def add_cell_names(self,names,start,end,linedef):
        for r in range(1,(end+2)-start):
            names["r"+str(r)] = lambda: Cell(r,'*',self)
            for c in range(1,len(linedef)):
                names["c"+str(c)] = Cell('*',c,self)
                names["r"+str(r)+"c"+str(c)] = Cell(r,c,self)
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
        self.add_constants(names)
        self.add_cell_names(names,start,end,linedef)
        super(TableDef,self).__init__(operators, functions, names)
        self.curRow = 0
        self.curCol = 0
        self.start = start
        self.end   = end
        self.view  = view
        self.linedef = linedef

    def RecalculateTableDimensions(self):
        res = recalculate_linedef(self.view,self.start)
        if(res == None):
            log.error("FAILURE TO RECALCULATE LINE DEFINITION FOR TABLE. Something is wrong!")
        else:
            self.linedef = res

    def Width(self):
        return len(self.linedef)

    def Height(self):
        return (self.end-self.start) + 1

    def StartRow(self):
        return self.startRow

    def StartCol(self):
        return 1

    def SetCurRow(self,r):
        self.curRow = r
    
    def SetCurCol(self,c):
        self.curCol = c

    def CurRow(self):
        return self.curRow

    def CurCol(self):
        return self.curCol

    def GetCellText(self,r,c):
        reg = self.FindCellRegion(r,c)
        if(reg):
            text = self.view.substr(reg)
            return text
        return ""
    def FindCellRegion(self,r,c):
        row = self.start + (r-1)       # 1 is zero
        colstart = self.linedef[c-1] 
        colend   = self.linedef[c]
        return sublime.Region(self.view.text_point(row,colstart+1),self.view.text_point(row,colend)) 
    def HighlightCells(self, cells):
        for cell in cells:
            reg = self.FindCellRegion(*cell)
            style = "orgdatepicker.monthheader"
            self.view.add_regions("cell_"+str(cell[0])+"_"+str(cell[1]),[reg],style,"",sublime.DRAW_NO_OUTLINE)
    def NumFormulas(self):
        return len(self.formulas) 

    def HighlightFormula(self, i):
        dm = self.formulas[i]
        self.HighlightCells([dm.target])

    def FormulaTarget(self, i):
        dm = self.formulas[i]
        return dm.target

    def Execute(self, i):
        return self.eval(self.formulas[i].expr)

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

def create_table(view):
    row = view.curRow()
    last_row = view.lastRow()
    end = last_row
    start = row
    linedef = None
    formula = None
    hlines = []
    endHeader = 1
    for r in range(row,0,-1):
        pt = view.text_point(r, 0)
        line = view.substr(view.line(pt))
        if(RE_TABLE_LINE.search(line) or RE_TABLE_HLINE.search(line)):
            continue
        row = r+1
        break
    start = row
    for r in range(row,last_row):
        pt = view.text_point(r, 0)
        line = view.substr(view.line(pt))
        m = RE_FMT_LINE.search(line)
        if(RE_TABLE_HLINE.search(line)):
            hlines.append(row)
            if(endHeader == 1):
                endHeader = (r - start) + 2
            continue
        elif(RE_TABLE_LINE.search(line)):
            if(None == linedef):
                linedef = findOccurrences(line,'|')
            continue
        elif(m):
            end = r-1
            formula = m.group('expr').split('::')
            break
        else:
            end = r-1
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
    #td.linedef = linedef
    td.formulas = []
    for fm in formula:
        td.formulas.append(Formula(fm))
    return td

def FormulaIterator(table):
    for i in range(0,table.NumFormulas()):
        target = table.FormulaTarget(i)
        cell = Cell(target[0],target[1],table)
        cellIterator = CellIterator(table,cell)
        for r,c in cellIterator:
            table.SetCurRow(r)
            table.SetCurCol(c)
            val = table.Execute(i)
            yield (r,c,val,table.FindCellRegion(r,c))
    return None

class OrgExecuteTableCommand(sublime_plugin.TextCommand):
    def on_reformat(self):
        print("RECALC DIMENSIONS")
        self.td.RecalculateTableDimensions()
        self.process_next()

    def on_done_cell(self):
        print("ON DONE CELL")
        self.view.sel().clear()
        self.view.sel().add(self.result[3])
        #self.view.run_command('table_editor_next_field')
        self.view.run_command('table_editor_align')
        sublime.set_timeout(self.on_reformat,1)

    def process_next(self):
        print("PROCESS NEXT")
        self.result = next(self.it,None)
        if(None == self.result):
            print("NONE EXITING")
            self.on_done()
            return
        r,c,val,reg = self.result
        print("REPLACING WITH: " + str(val))
        self.view.run_command("org_internal_replace", {"start": reg.begin(), "end": reg.end(), "text": str(val), "onDone": evt.Make(self.on_done_cell)})

    def on_done(self):
        print("DONE")
        pass

    def run(self, edit):
        # Working on formula handling
        self.td = create_table(self.view)
        self.it = FormulaIterator(self.td)
        self.process_next()
        #td.HighlightFormula(i)
        pass
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

def isTableFormula(view):
    names = view.scope_name(view.sel()[0].end())
    return 'orgmode.tblfm' in names

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

RE_TARGET = re.compile(r'\s*(([@](?P<rowonly>[-]?[0-9><]+))|([$](?P<colonly>[-]?[0-9><]+))|([@](?P<row>[-]?[0-9><]+)[$](?P<col>[-]?[0-9><]+)))\s*$')
def formula_rowcol(expr):
    fields = expr.split('=')
    if(len(fields) != 2):
        return (None, None)
    target = fields[0]
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

def isNumeric(v):
    return v.lstrip('-').isnumeric()

def isFunc(v):
    return 'ridx()' in v or 'cidx()' in v

# TODO: Make funciton cells work!
RE_TARGET_A = re.compile(r'\s*(([@](?P<rowonly>([-]?[0-9><#]+)|(ridx\(\))|(cidx\(\))))|([$](?P<colonly>([-]?[0-9><#]+)|(ridx\(\))|(cidx\(\))))|([@](?P<row>[-]?[0-9><#]+)[$](?P<col>([-]?[0-9><#]+)|(ridx\(\))|(cidx\(\)))))(?P<end>[^@$]|$)')
RE_ROW_TOKEN = re.compile(r'[@][#]')
RE_COL_TOKEN = re.compile(r'[$][#]')
def replace_cell_references(expr):
    print("EXPS: " + str(expr))
    while(True):
        expr = RE_ROW_TOKEN.sub('ridx()',expr)
        expr = RE_COL_TOKEN.sub('cidx()',expr)
        m = RE_TARGET_A.search(expr)
        if(m):
            row = m.group('row')
            col = m.group('col')
            end = m.group('end')
            if(not end):
                end = ""
            if not row and not col:
                row = m.group('rowonly')
                if(row):
                    if(isNumeric(row) or isFunc(row)):
                        expr = RE_TARGET_A.sub('getrowcell(' + str(row) + ')' + end,expr,1)
                    else:
                        expr = RE_TARGET_A.sub('getrowcell(\'' + str(row) + '\')' + end,expr,1)
                else:
                    col = m.group('colonly')
                    if(isNumeric(col) or isFunc(col)):
                        expr = RE_TARGET_A.sub('getcolcell(' + str(col) + ')' + end,expr,1)
                    else:
                        expr = RE_TARGET_A.sub('getcolcell(\'' + str(col) + '\')' + end,expr,1)
            else:
                rowmarkers = '' if not isNumeric(row) or isFunc(row) else '\''
                colmarkers = '' if not isNumeric(col) or isFunc(col) else '\''
                expr = RE_TARGET_A.sub('getcell(' + rowmarkers + str(row) + rowmarkers + "," + colmarkers + str(col) + colmarkers + ")" + end,expr,1)
        else:
            break
    print("EXP: " + str(expr))
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
    def __init__(self,expr, reg):
        self.target, self.expr = formula_rowcol(expr)
        # Never allow our expr to be empty. If we failed to parse it our EXPR is current cell value
        if(self.expr == None):
            self.expr = "$0"
        if(self.target == None):
            self.target = "@0$0"
        self.expr = replace_cell_references(self.expr.replace("..","//"))
        self.formula   = expr
        self.reg = reg 

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
            yield [r,c]

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
        elif(self.r < 0):
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
        elif(self.c < 0):
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

    def ridx(self):
        return self.CurRow()
    
    def cidx(self):
        return self.CurCol()

    def getrowcell(self,r):
        return Cell(r,'*',self)

    def getcolcell(self,c):
        return Cell('*',c,self)

    def getcell(self,r,c):
        return Cell(r,c,self)

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
        f['ridx'] = self.ridx
        f['cidx'] = self.cidx
        f['getcell'] = self.getcell
        f['getrowcell'] = self.getrowcell
        f['getcolcell'] = self.getcolcell

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
        self.cellToFormula = None
        self.accessList = []

    def RecalculateTableDimensions(self):
        res = recalculate_linedef(self.view,self.start)
        if(res == None):
            log.error("FAILURE TO RECALCULATE LINE DEFINITION FOR TABLE. Something is wrong!")
        else:
            self.linedef = res

    def Width(self):
        return len(self.linedef) - 1

    def Height(self):
        return self.rowCount

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
        self.accessList.append([r,c])
        reg = self.FindCellRegion(r,c)
        if(reg):
            text = self.view.substr(reg)
            return text
        return ""
    def FindCellRegion(self,r,c):
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
            if(self.lineToRow[i] == r):
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

    def FormulaTarget(self, i):
        dm = self.formulas[i]
        return dm.target

    def FormulaTargetCellIterator(self, i):
        target = self.FormulaTarget(i)
        cell = Cell(target[0],target[1],self)
        cellIterator = CellIterator(self,cell)
        return cellIterator

    def IsSingleTargetFormula(self,i):
        target = self.FormulaTarget(i)
        if(isinstance(target[0],int) and isinstance(target[1],int)):
            return True
        return False 

    def AddCellToFormulaMap(self,cell,i):
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
            val = self.eval(self.formulas[i].expr)
            return val
        except:
            return "<ERR>"

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

def create_table(view, at=None):
    row = view.curRow()
    if(at != None):
        row,_ = view.rowcol(at)
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
    for r in range(row,last_row):
        rowNum += 1
        pt = view.text_point(r, 0)
        line = view.substr(view.line(pt))
        m = RE_FMT_LINE.search(line)
        if(RE_TABLE_HLINE.search(line)):
            hlines.append(row)
            rowNum -= 1
            if(endHeader == 1):
                endHeader = (r - start) + 1
            continue
        elif(RE_TABLE_LINE.search(line)):
            if(None == linedef):
                linedef = findOccurrences(line,'|')
            lineToRow[rowNum] = r
            continue
        elif(m):
            end = r-1
            formula = m.group('expr').split('::')
            formulaRow = r
            formulaLine = line
            lastRow = rowNum - 1
            break
        else:
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
    #td.linedef = linedef
    td.formulas = []
    td.formulaRow = formulaRow
    td.formulaLine = formulaLine
    td.lineToRow   = lineToRow
    td.rowCount = lastRow
    if(formula):
        sre = re.compile(r'\s*[#][+]((TBLFM)|(tblfm))[:]')
        first = sre.match(formulaLine)
        lastend = len(first.group(0))
        xline = sre.sub('',formulaLine)
        las = xline.split('::')
        index = 0
        for fm in formula:
            fend = lastend+len(las[index])
            td.formulas.append(Formula(fm, sublime.Region(view.text_point(formulaRow,lastend),view.text_point(formulaRow,fend))))
            index += 1
            lastend = fend + 2
        td.BuildCellToFormulaMap()
    return td


def SingleFormulaIterator(table,i):
    target = table.FormulaTarget(i)
    cell = Cell(target[0],target[1],table)
    cellIterator = CellIterator(table,cell)
    for r,c in cellIterator:
        table.SetCurRow(r)
        table.SetCurCol(c)
        val = table.Execute(i)
        yield [r,c,val,table.FindCellRegion(r,c)]

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
        r,c,val,reg = self.result
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
        self.td = create_table(self.view, at)
        self.td.ClearAllRegions()

# ================================================================================
class OrgHighlightFormulaCommand(sublime_plugin.TextCommand):
    def run(self,edit):
        td = create_table(self.view)
        td.ClearAllRegions()
        i = td.CursorToFormula()
        if(None != i):
            td.HighlightFormula(i)

# ================================================================================
class OrgHighlightFormulaFromCellCommand(sublime_plugin.TextCommand):
    def run(self,edit):
        td = create_table(self.view)
        td.ClearAllRegions()
        cell = td.CursorToCell()
        if(cell):
            formulaIdx = td.CellToFormula(cell)
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




    

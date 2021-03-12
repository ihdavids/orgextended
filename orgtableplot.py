
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
import OrgExtended.orgparse.date as orgdate
import OrgExtended.orgduration as orgduration
import math
import random
import ast
import operator as op
import subprocess
import platform
import time


def plot_write_table_data_to(params,table,f,r,c,first=False):
    txt = table.GetCellText(r,c).strip()
    if(first):
        if((r == 1 and table.StartRow() != 1) and not ("include" in params and "header" in params["include"])):
            f.write("#")
    else:
        f.write("\t")
    if(not util.numberCheck(txt) and " " in txt or "\t" in txt):
        f.write("\""+ txt + "\"")
    else:
        f.write(txt)

def plot_build_data_file(table,params):
    filename = params['_filename']
    datafile = os.path.join(params['_sourcepath'],os.path.splitext(filename)[0]+".data")
    params['_datafile'] = datafile
    # Maybe skip the first column if it has lables
    startCol = 1
    #for r in range(1,table.Height() + 1):
    #    if(not isNumeric(table.GetCellText(r,1).strip())):
    #        startCol += 1
    #        break
    ind = startCol
    if('ind' in params):
        if(startCol > 1):
            ind = int(params['ind'])+1
        else:
            ind = int(params['ind'])
    usingVals = range(startCol, table.Width()+1)
    if('deps' in params):
        deps = params['deps']
        usingVals = util.ToIntList(deps)

    with open(datafile,"w") as f:
        for r in range(1,table.Height()+1):
            c = ind
            plot_write_table_data_to(params,table,f,r,c,first=True)
            # Eventually we will need to do this with a user specified range.
            for c in usingVals:
                if(c != ind):
                    plot_write_table_data_to(params,table,f,r,c)
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
        ff,ext = os.path.splitext(filename)
        if(ext == '.png'):
            f.write('set term png \n')
        if(ext == '.jpg' or ext == '.jpeg'):
            f.write('set term jpeg \n')
        if(ext == '.gif'):
            f.write('set term gif \n')
        if(ext == '.html'):
            f.write('set term canvas \n')
        if(ext == '.txt'):
            f.write('set term dumb \n')
        if(ext == '.svg'):
            f.write('set term svg \n')
        if(ext == '.ps'):
            f.write('set term postscript \n')

        if(filename != "viewer"):
            f.write('set output ' + plot_quote(filename.replace('\\','\\\\')) + "\n")
        if('deps' in params):
            deps = params['deps']
            t = deps.replace('(',"").replace(")","")
            ts = re.split(r'\s+',t)
            for x in ts:
                if(x.strip() != ""):
                    usingVals.append(int(x.strip()))
        ind = 1
        if('unset' in params):
            for x in params['unset']:
                f.write('unset ' + x + '\n')
        if('set' in params):
            for x in params['set']:
                f.write('set ' + x + '\n')
        for x,y in params.items():
            if(isinstance(y,str)):
                y = y.strip()
            if(x == "using"):
                withstmt = " " + y.replace("\"","") + " "
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
                            seriesTitle = "\"col "+str(i)+"\""
                        if(not first):
                            withstmt += ",\"\" using " + str(count) + " with histograms title " + seriesTitle + " "
                        else:
                            withstmt = " using " + str(count) + " with histograms title " + seriesTitle + " "
                    continue
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
                    continue
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
        ps     = re.split(r'\s+[a-zA-Z][a-zA-Z0-9]+[:]',plot) 
        ps = ps[1:]
        keys   = [m.group(0) for m in re.finditer(r'\s+[a-zA-Z][a-zA-Z0-9]+[:]',plot)]
        #keys   = [m.group(0) for m in re.finditer(r'(^|\s+)[^: ]+[:]',plot)]
        for i in range(0,len(keys)):
            k = keys[i].strip()
            if(k.endswith(':')):
                k = k[:-1]
            v = ps[i].strip()
            if(k == 'set'):
                if(not 'set' in params):
                    params['set'] = []
                params['set'].append(v.replace("\"",""))
                continue
            if(k == 'unset'):
                if(not 'unset' in params):
                    params['unset'] = []
                params['unset'].append(v.replace("\"",""))
                continue
            if(k == 'file'):
                filename = v
                if(filename == "viewer"):
                    params["_filename"] = "viewer"
                    continue
                sourcepath = os.path.dirname(filename)
                if(len(sourcepath) > 2):
                    params['_sourcepath'] = sourcepath
                    params['_filename'] = filename
                else:
                    params['_filename'] = os.path.join(params['_sourcepath'],filename)
                continue
            else:
                params[k] = v
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
            table.resultsRegion = sublime.Region(view.text_point(startResults,0),view.line(view.text_point(fileEndRow,0)).end())
            return True
        # We hit the end of the file and didn't find a results tag.
        # We need to make one.
        if(not inResults):
            table.resultsRegion = sublime.Region(view.text_point(table.end+2,0),view.text_point(table.end+2,0))
            return False
ppp = None
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
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    except:
        startupinfo = None
    cwd = os.path.join(sublime.packages_path(),"User") 
    if(output == "viewer" and platform.system() == "Windows"):
        global ppp
        ppp = subprocess.Popen(commandLine, universal_newlines=True, cwd=cwd, startupinfo=startupinfo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        o = ""
        e = ""
    else:
        popen = subprocess.Popen(commandLine, universal_newlines=True, cwd=cwd, startupinfo=startupinfo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (o,e) = popen.communicate()
    print("Attempting to plot data from table:")
    print("STDOUT: \n" + str(o))
    print("STDERR: \n" + str(e))
    cullTempFiles = True
    if(cullTempFiles):
        if(os.path.exists(ps['_datafile'])):
            os.remove(ps['_datafile']) 
        if(os.path.exists(ps['_gpltfile'])):
            os.remove(ps['_gpltfile']) 
    row = view.curRow()
    node = db.Get().At(view, row)
    level = 1
    indent = " "
    if(node):
        level = node.level
        indent = " " * level + " "
    o = indent + "#+RESULTS:\n"+indent+"[[file:" + output.replace("\\","/") + "]]"
    if(output != "viewer"):
        have = plot_find_results(table,view)
        if(not have):
            o = "\n" + o
        view.run_command("org_internal_replace", {"start": table.resultsRegion.begin(), "end": table.resultsRegion.end(), "text": o})
    print(o)
    #return o.split('\n') + e.split('\n')

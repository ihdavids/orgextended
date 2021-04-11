import sublime
import sublime_plugin
import sys
import io
import re
import logging
import subprocess, os
import threading, time, signal
import OrgExtended.orgtableformula as fml
import OrgExtended.orgsourceblock as src
import OrgExtended.orgparse.date as odate
import OrgExtended.orgutil.util as util
import OrgExtended.orglist as lst

# Cmd Babel Mode

def FormatText(txt):
    if(isinstance(txt,str)):
        txt = txt.strip()
        return "'" + txt + "'"
    return txt


def HandleValue(cmd):
    if(cmd.CheckResultsFor('value')):
        out = "function OrgExtendedPowershellWrapperFunction {\n"
        outs = cmd.source.split('\n')
        for o in outs:
            out += " " + o + "\n"
        out += '}\n'
        out += "$orgExtendedWrapperVar = OrgExtendedPowershellWrapperFunction\nWrite-Host RETURNVALUESTART\nWrite-Host $orgExtendedWrapperVar\nWrite-Host RETURNVALUEEND\n"
        cmd.source = out

def PreProcessSourceFile(cmd):
    HandleValue(cmd)
    var = cmd.params.Get('var',None)
    if(var):
        out = ""
        for k in var:
            v = var[k]
            if(isinstance(v,src.TableData)):
                out += "set " + str(k) + "_width=" + str(v.Width()) + "\n"
                out += "set " + str(k) + "_height=" + str(v.Height()) + "\n"
                for r in v.ForEachRow():
                    for c in v.ForEachCol():
                        txt = v.GetCell(r,c)
                        out += "set " + str(k) + "[" + str(r) + "," + str(c) + "]=" + str(FormatText(txt)) + "\n"
            elif(isinstance(v,lst.ListData)):
                out += "set " + str(k) + "_len=" + str(v.Length()) + "\n"
                out += "set " + str(k) + "=[" 
                first = True
                for txt in v:
                    out += (',' if not first else "") + str(FormatText(txt))
                    first = False
                out += "]\n"
            elif(isinstance(v,int) or isinstance(v,float) or (isinstance(v,str) and util.numberCheck(v))):
                out += "set /A " + str(k) + "=" + str(v) + "\n"
            elif(isinstance(v,str)):
                out += "set " + str(k) + "=" + str(v) + "\n"
        cmd.source = out + cmd.source
        print(str(cmd.source))


def Extension(cmd):
    return ".bat"

def LineCommentPrefix():
    return "REM"
    
# Actually do the work, return an array of output.
def Execute(cmd,sets):
    commandLine = [r"C:\\Windows\\system32\\cmd.exe","/Q", "/C", cmd.filename]
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    except:
        startupinfo = None
    # cwd=working_dir, env=my_env,
    cwd = os.path.join(sublime.packages_path(),"User") 
    popen = subprocess.Popen(commandLine, universal_newlines=True, cwd=cwd, startupinfo=startupinfo, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    #popen.wait()
    (o,e) = popen.communicate()
    if(cmd.CheckResultsFor('value')):
        out = []
        outs = o.split('\n')
        seenStart = False
        for oo in outs:
            if(oo.strip() == "RETURNVALUESTART"):
                seenStart = True
                continue
            if(oo.strip() == "RETURNVALUEEND"):
                seenStart = False
                continue
            if(seenStart):
                out.append(oo)
        return out + e.split('\n')

    return o.split('\n') + e.split('\n')


# Run after results are in the buffer. We can do whatever
# Is needed to the buffer post execute here.
def PostExecute(cmd):
    pass

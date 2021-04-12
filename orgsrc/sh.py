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

# Bash Babel Mode

def FormatText(txt):
    if(isinstance(txt,str)):
        txt = txt.strip()
        #return "'" + txt + "'"
    return txt


def HandleValue(cmd):
    if(cmd.CheckResultsFor('value')):
        out = "OrgExtendedBashWrapperFunction () {\n"
        outs = cmd.source.split('\n')
        for o in outs:
            out += " " + o + "\n"
        out += '}\n'
        out += "OrgExtendedBashWrapperFunction\norgExtendedWrapperVar=$?\necho RETURNVALUESTART\necho ${orgExtendedWrapperVar}\necho RETURNVALUEEND\n"
        cmd.source = out

def PreProcessSourceFile(cmd):
    HandleValue(cmd)
    var = cmd.params.Get('var',None)
    if(var):
        out = ""
        for k in var:
            v = var[k]
            if(isinstance(v,src.TableData)):
                out += str(k) + "=$(cat <<'END_HERE_DOC'\n"
                for r in v.ForEachRow():
                    first = True
                    for c in v.ForEachCol():
                        txt = v.GetCell(r,c)
                        out += ('\t' if not first else "") + str(FormatText(txt))
                        first = False
                    out += '\n'
                out += "END_HERE_DOC\n)\n"
            elif(isinstance(v,lst.ListData)):
                out += str(k) + "=("
                first = True
                for txt in v:
                    out += (' ' if not first else "") + str(FormatText(txt))
                    first = False
                out += ")\n"
            elif(isinstance(v,int) or isinstance(v,float) or (isinstance(v,str) and util.numberCheck(v))):
                out += str(k) + "=" + str(v) + "\n"
            elif(isinstance(v,str)):
                out += str(k) + "=\'" + str(v) + "\'\n"
        cmd.source = out + cmd.source


def Extension(cmd):
    return ".sh"

def LineCommentPrefix():
    return "#"

def GetCommandLine(cmd,sets):
    filename = cmd.filename
    if(sublime.platform() == 'windows'):
        bashLocation = sets.Get("bashPath",r"C:\\Windows\\System32\\wsl.exe")
        filename = filename.replace("C:\\","/mnt/c/").replace("c:\\","/mnt/c/").replace("\\","/")
    else:
        bashLocation = sets.Get("bashPath",r"/bin/bash")
    commandLine = [bashLocation, filename]
    return commandLine

    
# Actually do the work, return an array of output.
def Execute(cmd,sets):
    commandLine = GetCommandLine(cmd,sets)
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

import sublime
import sublime_plugin
import sys
import io
import re
import OrgExtended.orgtableformula as fml
import OrgExtended.orgsourceblock as src
import OrgExtended.orglist as lst
import OrgExtended.orgparse.date as odate
import OrgExtended.orgutil.util as util

# Python Babel Mode
def FormatText(txt):
    if(isinstance(txt,str)):
        txt = txt.strip()
        return "'" + txt + "'"
    return txt

def HandleValue(cmd):
    if(cmd.CheckResultsFor('value')):
        out = "def OrgExtendedPythonWrapperFunction():\n"
        outs = cmd.source.split('\n')
        leadingIndent = ""
        if(len(outs) > 0):
            leadingIndent = re.match(r"\s*", outs[0]).group()
        for vaDefs in cmd.varsDefs:
            out += "    " + leadingIndent + vaDefs + "\n"
        for o in outs:
            out += "    " + o + "\n"
        out += "\n\norgExtendedPythonReturnVar = OrgExtendedPythonWrapperFunction()\n"
        cmd.source = out

def PreProcessSourceFile(cmd):
    var = cmd.params.Get('var',None)
    cmd.varsDefs = []
    out = ""
    if(var):
        for k in var:
            v = var[k]
            if(isinstance(v,src.TableData)):
                out += str(k) + " = [\n"
                cmd.varsDefs.append("global " + str(k))
                fr = True
                for r in v.ForEachRow():
                    first = True
                    out += '[' if fr else ",["
                    fr = False
                    for c in v.ForEachCol():
                        txt = v.GetCell(r,c)
                        out += (',' if not first else "") + str(FormatText(txt))
                        first = False
                    out += ']'
                out += "]\n"
            if(isinstance(v,fml.TableDef)):
                out += str(k) + " = [\n"
                cmd.varsDefs.append("global " + str(k))
                fr = True
                for r in v.ForEachRow():
                    first = True
                    out += '[' if fr else ",["
                    fr = False
                    for c in v.ForEachCol():
                        txt = fml.Cell(r,c,v).GetVal()
                        out += (',' if not first else "") + str(FormatText(txt))
                        first = False
                    out += ']'
                out += "]\n"
            elif(isinstance(v,lst.ListData)):
                out += str(k) + " = [\n"
                cmd.varsDefs.append("global " + str(k))
                first = True
                for txt in v:
                    out += (',' if not first else "") + str(FormatText(txt))
                    first = False
                out += "]\n"
            elif(isinstance(v,int) or isinstance(v,float) or (isinstance(v,str) and util.numberCheck(v))):
                out += str(k) + " = " + str(v) + "\n"
                cmd.varsDefs.append("global " + str(k))
            elif(isinstance(v,str)):
                out += str(k) + " = \'" + str(v) + "\'\n"
                cmd.varsDefs.append("global " + str(k))
    HandleValue(cmd)
    if(out != ""):
        cmd.source = out + cmd.source


# Actually do the work, return an array of output.
def Execute(cmd, sets):
    # create file-like string to capture output
    codeOut = io.StringIO()
    codeErr = io.StringIO()
    code    = cmd.source
    # capture output and errors
    oldOut     = sys.stdout
    oldErr     = sys.stderr
    sys.stdout = codeOut
    sys.stderr = codeErr
    ret = None
    loc = {}
    loc['orgExtendedPythonReturnVar'] = None
    loc['view'] = sublime.active_window().active_view()
    loc['window'] = sublime.active_window()
    globs = globals()
    try:
        if(not cmd.CheckResultsFor('value')):
            code = re.sub(r"^(\s+)(.*)$",
                    lambda m: re.sub("^" + " "*len(m.group(1)),"",m.group(2),flags=re.MULTILINE)
                    ,code,flags=re.MULTILINE|re.DOTALL)
        exec(code,globs,loc)
    except Exception as ex:
        # If we throw during the run we need to catch it
        # and try to handle it here.
        print("EXCEPTION DURING RUN:")
        print(type(ex))
        print(ex.args)

    # restore stdout and stderr
    #sys.stdout = sys.__stdout__
    #sys.stderr = sys.__stderr__
    sys.stdout = oldOut
    sys.stderr = oldErr

    e = codeErr.getvalue()
    #print("error:\n%s\n" % e)
    o = codeOut.getvalue()
    #print("output:\n%s" % o)
    codeOut.close()
    codeErr.close()
    if(cmd.CheckResultsFor('value')):
        if(loc['orgExtendedPythonReturnVar'] == None):
            if(e.strip()+o.strip() != ""):
                return o.split('\n') + e.split('\n')
        return [ str(loc['orgExtendedPythonReturnVar']) ]
        #return [ str(globs) ]
    else:
        return o.split('\n') + e.split('\n')


# Run after results are in the buffer. We can do whatever
# Is needed to the buffer post execute here.
def PostExecute(cmd):
    pass

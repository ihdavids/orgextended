import sublime
import sublime_plugin
import sys
import io
import re
import OrgExtended.orgtableformula as fml
import OrgExtended.orgparse.date as odate

# Python Babel Mode
def FormatText(txt):
    if(isinstance(txt,str)):
        txt = txt.strip()
        return "'" + txt + "'"
    return txt

def PreProcessSourceFile(cmd):
    var = cmd.params.Get('var',None)
    if(var):
        out = ""
        for k in var:
            v = var[k]
            if(isinstance(v,fml.TableDef)):
                out += str(k) + " = [\n"
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
    try:
        code = re.sub(r"^(\s+)(.*)$",
            lambda m: re.sub("^" + " "*len(m.group(1)),"",m.group(2),flags=re.MULTILINE)
            ,code,flags=re.MULTILINE|re.DOTALL)
        exec(code)
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

    #print("DONE EXECUTING")
    e = codeErr.getvalue()
    #print("error:\n%s\n" % e)
    o = codeOut.getvalue()
    #print("output:\n%s" % o)
    codeOut.close()
    codeErr.close()
    return o.split('\n') + e.split('\n')


# Run after results are in the buffer. We can do whatever
# Is needed to the buffer post execute here.
def PostExecute(cmd):
    pass

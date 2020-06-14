import sublime
import sublime_plugin
import sys
import io
import re

# Python Babel Mode


# Actually do the work, return an array of output.
def Execute(cmd):
	print("EXECUTE STARTED")
	# create file-like string to capture output
	codeOut = io.StringIO()
	codeErr = io.StringIO()
	code    = cmd.source
	print("TRYING TO EXECUTE 2")
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

	print("DONE EXECUTING")
	e = codeErr.getvalue()
	print("error:\n%s\n" % e)
	o = codeOut.getvalue()
	print("output:\n%s" % o)
	codeOut.close()
	codeErr.close()
	return o.split('\n') + e.split('\n')


# Run after results are in the buffer. We can do whatever
# Is needed to the buffer post execute here.
def PostExecute(cmd):
	pass

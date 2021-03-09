import sublime
import datetime

def Execute(view, params):
	return [str(datetime.datetime.now())]
import sublime
import datetime
import re
import math
import sublime_plugin

# This library provides tools to manipulate durations.  A duration
# can have multiple formats:
#
#   - 3:12
#   - 1:23:45
#   - 1y 3d 3h 4min
#   - 1d3h5min
#   - 3d 13:35
#   - 2.35h
#
# More accurately, it consists of numbers and units, as defined in
# variable `org-duration-units', possibly separated with white
# spaces, and an optional "H:MM" or "H:MM:SS" part, which always
# comes last.  White spaces are tolerated between the number and its
# relative unit.  Variable `org-duration-format' controls durations
# default representation.
#
# The library provides functions allowing to convert a duration to,
# and from, a number of minutes: `org-duration-to-minutes' and
# `org-duration-from-minutes'.  It also provides two lesser tools:
# `org-duration-p', and `org-duration-h:mm-only-p'.
#
# Users can set the number of minutes per unit, or define new units,
# in `org-duration-units'.  The library also supports canonical
# duration, i.e., a duration that doesn't depend on user's settings,
# through optional arguments. 

RE_DURATION_PARSER = re.compile(r'\s*((?P<years>[0-9.]+)y)?\s*((?P<days>[0-9.]+)d)?\s*((?P<hours>[0-9.]+)h)?\s*((?P<mins>[0-9.]+)min)?\s*((?P<thours>[0-9]+)[:](?P<tmins>[0-9]+)([:](?P<tsecs>[0-9]+))?)?')
class OrgDuration:
    def __init__(self,minutes):
        self.mins = minutes

    def __str__(self):
        r = ""
        y = int(self.mins / 525600.0)
        if(y > 0):
            r += str(y) + "y "
        days = math.fmod(self.mins,525600.0)
        d = int(days / 1440.0)
        if(d > 0):
            r += str(d) + "d "
        hours = math.fmod(days,1440.0)
        h = int(hours/60.0)
        if(h > 0):
            r += str(h) + "h "
        mins = int(math.fmod(hours,60))
        if(mins > 0):
            r += str(mins) + "mins"
        return r.strip()
    
    def __sub__(self,o):
        print("SUB")
        if(isinstance(o,int)):
            d = OrgDuration.ParseInt(o)
            mins = self.mins - d.mins
            d.mins = mins
            return d
        if(isinstance(o,float)):
            d = OrgDuration.ParseFloat(o)
            mins = self.mins - d.mins
            d.mins = mins
            return d
        if(isinstance(o,OrgDuration)):
            d = OrgDuration.ParseInt(1)
            d.mins = self.mins - o.mins
            return d
        return self 
    
    def __add__(self,o):
        if(isinstance(o,int)):
            d = OrgDuration.ParseInt(o)
            mins = self.mins + d.mins
            d.mins = mins
            return d
        if(isinstance(o,float)):
            d = OrgDuration.ParseFloat(o)
            mins = self.mins + d.mins
            d.mins = mins
            return d
        if(isinstance(o,OrgDuration)):
            d = OrgDuration.ParseInt(1)
            d.mins = self.mins + o.mins
            return d
        return self 

    def timedelta(self):
        y     = int(self.mins / 525600.0)
        days  = math.fmod(self.mins,525600.0)
        d     = int(days / 1440.0)
        hours = math.fmod(days,1440.0)
        h     = int(hours/60.0)
        mins  = int(math.fmod(hours,60))
        td = datetime.timedelta(days=d+(y*365),hours=h,minutes=mins)
        return td

    @staticmethod
    def FromTimedelta(td: datetime.timedelta):
        return OrgDuration(td.days*1440 + (td.seconds/60.0))

    @staticmethod
    def Parse(txt: str):
        m = RE_DURATION_PARSER.search(txt)
        if(m):
            mtot = 0.0
            y = m.group('years')
            if(y):
                mtot += float(y)*525600.0
            d = m.group('days')
            if(d):
                mtot += float(d)*1440
            h = m.group('hours')
            if(h):
                mtot += float(h)*60
            mins = m.group('mins')
            if(mins):
                mtot += float(mins)
            h = m.group('thours')
            if(h):
                mtot += float(h)*60
            mins = m.group('tmins')
            if(mins):
                mtot += float(mins)
            secs = m.group('tsecs')
            if(secs):
                mtot += float(secs)*0.01666667
            return OrgDuration(mtot)
        return None


    @staticmethod
    def ParseInt(d: int):
        # Let the user determine default meaning d is the default
        mtot = float(d)*1440
        return OrgDuration(mtot)
    
    @staticmethod
    def ParseFloat(d: float):
        # Let the user determine default meaning d is the default
        mtot = float(d)*1440
        return OrgDuration(mtot)


# ================================================================================
class OrgTestDurationCommand(sublime_plugin.TextCommand):
    def run(self, edit, onDone=None):
        d = OrgDuration.Parse("2y3d5h6min")
        print(str(d))
        d = OrgDuration.Parse("1y")
        print(str(d))
        d = OrgDuration.Parse("2d")
        print(str(d))
        d = OrgDuration.Parse("3h")
        print(str(d))
        d = OrgDuration.Parse("4min")
        print(str(d))
        d = OrgDuration.Parse("1d 3:44")
        print(str(d))
        d = OrgDuration.Parse("1d 4:55:55")
        print(str(d))

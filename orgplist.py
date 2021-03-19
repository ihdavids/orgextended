import sublime
import sublime_plugin
import os
import base64
import urllib.request
import OrgExtended.asettings as sets 
import uuid
import re
import logging

from OrgExtended.orgutil.addmethod import *

log = logging.getLogger(__name__)


RE_FN_MATCH = re.compile(r"\s+[:]([a-zA-Z][a-zA-Z0-9-_]*)\s+(([a-zA-Z][a-zA-Z0-9]*\s*[=]\s*[\"][^\"]+[\"])|([^ ()\"]+)|([(][^)]+[)])|([\"][^\"]+[\"]))")
class PList:
    def __init__(self,plist):
        self.params = plist

    def Get(self, name, defaultValue):
        if(name in self.params and self.params[name]):
            v = self.params[name]
            if(isinstance(v,str)):
                v = v.strip()
                if(v.startswith("\"")):
                    v = v[1:]
                if(v.endswith("\"")):
                    v = v[:-1]
            return v
        return defaultValue

    def FormatData(self,x):
    	if(x.startswith("\"")):
    		x = x[1:]
    	if(x.endswith("\"")):
    		x = x[:-1]
    	return x

    def GetInt(self,name,defaultValue):
        v = self.Get(name,defaultValue)
        try:
            return int(v)
        except:
            return defaultValue

    def GetFloat(self,name,defaultValue):
        v = self.Get(name,defaultValue)
        try:
            return float(v)
        except:
            return defaultValue

    def GetList(self,name,defaultValue):
        v = self.Get(name,defaultValue)
        if(not isinstance(v,list)):
            return ToList(v) 
        return v

    def GetIntList(self,name,defaultValue):
        v = self.Get(name,defaultValue)
        if(not isinstance(v,list)):
            return ToIntList(v) 
        return v

    def GetDict(self,name,defaultValue):
        out = {}
        v = self.Get(name,defaultValue)
        if(isinstance(v,str)):
            vs = v.split('=')
            if(len(vs) == 2):
                out[vs[0].strip()] = self.FormatData(vs[1].strip())
                return out
        if(isinstance(v,list)):
            for i in v:
                vs = i.split('=')
                if(len(vs) == 2):
                    out[vs[0].strip()] = self.FormatData(vs[1].strip())
            if(len(out) > 0):
                return out
        return defaultValue

    def Add(self,key,val):
        PList.addToParam(self.params,key,val)

    def Has(self,key):
        return key in self.params
    
    def Replace(self,key,val):
        self.params[key] = val

    def AddFromPList(self,strData):
        if(None == strData):
            return
        d = PList.plistParse(strData)
        for k in d:
            self.addToParam(self.params,k,d[k])

    @staticmethod
    def addToParam(params,key,val):
        val = val.strip()
        if(val.startswith("\"")):
            val = val[1:]
        if(val.endswith("\"")):
            val = val[:-1]
        if(key in params):
            v = params[key]
            if(isinstance(v,str)):
                params[key] = []
                params[key].append(v)
            params[key].append(val)
        else:
            params[key] = val

    @staticmethod
    def plistParse(data):
        if(isinstance(data,list)):
            data = " ".join(data)
        paramstr = " " + data
        params = {}
        for m in RE_FN_MATCH.finditer(paramstr):
            key = m.group(1)
            val = m.group(2)
            PList.addToParam(params,key,val)
        return params

    @staticmethod
    def createPList(data):
        params = PList.plistParse(data)
        return PList(params)

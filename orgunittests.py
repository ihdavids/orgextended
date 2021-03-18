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
from   OrgExtended.orgplist import *
import math
import random
import ast
import operator as op
import subprocess
import platform
import time


class OrgPlistTestCommand(sublime_plugin.TextCommand):
    def run(self,edit):
    	# Test the plist parsing utilities 
        p = PList.createPList(":width 10 :height 20")
        util.TEST("plist int1",p.GetInt('width',-1),10,"Width did not come back propperly")
        util.TEST("plist int2",p.GetInt('height',-1),20,"Height did not come back propperly")

        util.TEST("plist intstr1",p.Get('width',-1),"10","Width did not come back propperly")
        util.TEST("plist intstr2",p.Get('height',-1),"20","Height did not come back propperly")

        p = PList.createPList(":width 10.5 :height 20.2")
        util.TEST("plist float1",p.GetFloat('width',-1),10.5,"Width did not come back propperly")
        util.TEST("plist float2",p.GetFloat('height',-1),20.2,"Height did not come back propperly")

        p = PList.createPList(":param (1 2 3 4) :param2 ( 5 6) :param3 (7 8 )")
        util.TEST("plist list1",p.Get('param',None),"(1 2 3 4)","List test")
        util.TEST("plist list2",p.Get('param2',None),"( 5 6)","List param 2 test")
        util.TEST("plist list3",p.Get('param3',None),"(7 8 )","List param 3 test")

        util.TEST("plist intlist1",p.GetIntList('param',None),[1,2,3,4],"List test")
        util.TEST("plist intlist2",p.GetIntList('param2',None),[5,6],"List param 2 test")
        util.TEST("plist intlist3",p.GetIntList('param3',None),[7,8],"List param 3 test")

        util.TEST("plist liststr1",p.GetList('param',None),['1','2','3','4'],"List test")
        util.TEST("plist liststr2",p.GetList('param2',None),['5','6'],"List param 2 test")
        util.TEST("plist liststr3",p.GetList('param3',None),['7','8'],"List param 3 test")

        p = PList.createPList(":param \"Hello World\" :param2 \"Yet Again\"")
        util.TEST("plist string1",p.Get('param',None),"Hello World","List string 1 test")
        util.TEST("plist string1",p.Get('param2',None),"Yet Again","List string 1 test")

        p = PList.createPList(":var a=b :var c=d :var e=f :other hello")
        util.TEST("plist list dict",p.Get('var',None),['a=b','c=d','e=f'],"List dict test 1")
        util.TEST("plist dict",p.GetDict('var',None),{'a':'b','c':'d','e':'f'},"Dict test 1")
        util.TEST("plist dict other",p.Get('other',None),"hello","Dict other test 1")


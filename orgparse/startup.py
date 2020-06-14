from .enum import Enum


Startup = Enum(["overview", "content", "showall", "showeverything", "fold", "nofold", "noinlineimages", "inlineimages", "logdone", "lognotedone"])

#+STARTUP: overview
#+STARTUP: content
#+STARTUP: showall
#+STARTUP: showeverything
#+STARTUP: lognotedone logdone - for closing a task

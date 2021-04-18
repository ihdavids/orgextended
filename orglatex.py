import sublime
import sublime_plugin
import datetime
import re
import regex
from pathlib import Path
import os
import fnmatch
import OrgExtended.orgparse.node as node
from   OrgExtended.orgparse.sublimenode import * 
import OrgExtended.orgutil.util as util
import OrgExtended.orgutil.navigation as nav
import OrgExtended.orgutil.template as templateEngine
import logging
import sys
import traceback 
import OrgExtended.orgfolding as folding
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
import OrgExtended.orgcapture as capture
import OrgExtended.orgproperties as props
import OrgExtended.orgutil.temp as tf
import OrgExtended.pymitter as evt
import OrgExtended.orgnotifications as notice
import OrgExtended.orgextension as ext
import OrgExtended.orgsourceblock as src
import OrgExtended.orgexporter as exp
import yaml
import sys
import subprocess
import html

log = logging.getLogger(__name__)

langMap = {
    "cpp": "C++",
    "python": "Python",
    "C": "C",
    "perl": "Perl",
    "bash": "bash",
    "sh": "sh",
    "lua": "[5.0]Lua",
    "java": "Java",
    "php": "PHP",
    "xml": "XML",
    "lisp": "Lisp",
    "sql": "SQL",
    "r": "R",
    "html": "HTML",
    "go": "Go",
    "make": "make",
    "pascal": "Pascal",
    "ruby": "Ruby",
    "xsl": "XSLT",
    "scala": "Scala",
    "erlang": "erlang",
    "gnuplot": "Gnuplot",
}

# overriding it by users settings
langMap.update(sets.Get("latexListingPackageLang",langMap))

def haveLang(lang):
    return lang in langMap

def mapLanguage(lang):
    if(lang in langMap):
        return langMap[lang]
    return lang

RE_ATTR = regex.compile(r"^\s*[#][+]ATTR_HTML[:](?P<params>\s+[:](?P<name>[a-zA-Z0-9._-]+)\s+(?P<value>([^:]|((?<! )[:]))+))+$")
RE_ATTR_ORG = regex.compile(r"^\s*[#][+]ATTR_ORG[:] ")
RE_LINK = re.compile(r"\[\[(?P<link>[^\]]+)\](\[(?P<desc>[^\]]+)\])?\]")
RE_UL   = re.compile(r"^(?P<indent>\s*)(-|[+])\s+(?P<data>.+)")
RE_FN_MATCH = re.compile(r"\s*[:]([a-zA-Z0-9-_]+)\s+([^: ]+)?\s*")
RE_STARTSRC = re.compile(r"^\s*#\+(BEGIN_SRC|begin_src)\s+(?P<lang>[a-zA-Z0-9]+)")
RE_STARTDYN = re.compile(r"^\s*#\+(BEGIN:|begin:)\s+(?P<lang>[a-zA-Z0-9]+)")
RE_ENDSRC = re.compile(r"^\s*#\+(END_SRC|end_src)")
RE_ENDDYN = re.compile(r"^\s*#\+(end:|END:)")
RE_RESULTS = re.compile(r"^\s*#\+RESULTS.*")
RE_TABLE_SEPARATOR = re.compile(r"^\s*[|][-]")
RE_CHECKBOX         = re.compile(r"^\[ \] ")
RE_CHECKED_CHECKBOX = re.compile(r"^\[[xX]\] ")
RE_PARTIAL_CHECKBOX = re.compile(r"^\[[-]\] ")
RE_EMPTY_LINE = re.compile(r"^\s*$")


# <!-- multiple_stores height="50%" width="50%" --> 
RE_COMMENT_TAG = re.compile(r"^\s*[<][!][-][-]\s+(?P<name>[a-zA-Z0-9_-]+)\s+(?P<props>.*)\s+[-][-][>]")

#\documentclass{article}
# PREAMBLE
#\begin{document}
#Hello, \LaTeX\ world.
#\end{document}

sectionTypes = [
r"\chapter{{{heading}}}",
r"\section{{{heading}}}",
r"\subsection{{{heading}}}",
r"\subsubsection{{{heading}}}",
r"\paragraph{{{heading}}}",
r"\subparagraph{{{heading}}}"
]


class LatexSourceBlockState(exp.SourceBlockState):
    def __init__(self,doc):
        super(LatexSourceBlockState,self).__init__(doc)
        self.skipSrc = False

    def HandleEntering(self, m, l, orgnode):
        self.skipSrc = False
        language = m.group('lang')
        paramstr = l[len(m.group(0)):]
        p = type('', (), {})() 
        src.BuildFullParamList(p,language,paramstr,orgnode)
        exp = p.params.Get("exports",None)
        if(isinstance(exp,list) and len(exp) > 0):
            exp = exp[0]
        if(exp == 'results' or exp == 'none'):
            self.skipSrc = True
            return
        # Some languages we skip source by default
        skipLangs = sets.Get("latexDefaultSkipSrc",[])
        if(exp == None and language == skipLangs):
            self.skipSrc = True
            return
        attribs = ""
        if(haveLang(language)):
            self.e.doc.append(r"  \begin{{lstlisting}}[language={{{lang}}}]".format(lang=mapLanguage(language)))
        else:
            self.e.doc.append(r"  \begin{lstlisting}")

    def HandleExiting(self, m, l , orgnode):
        if(not self.skipSrc):
            self.e.doc.append(r"  \end{lstlisting}")
        skipSrc = False

    def HandleIn(self,l, orgnode):
        if(not self.skipSrc):
            self.e.doc.append(l)

# Skips over contents not intended for a latex buffer
class LatexExportBlockState(exp.ExportBlockState):
    def __init__(self,doc):
        super(LatexExportBlockState,self).__init__(doc)
        self.skipExport = False

    def HandleEntering(self, m, l, orgnode):
        self.skipExport = False
        language = m.group('lang').strip().lower()
        if(language != "latex"):
            self.skipExport = True
            return
        # We will probably need this in the future.
        #paramstr = l[len(m.group(0)):]
        #p = type('', (), {})() 
        #src.BuildFullParamList(p,language,paramstr,orgnode)

    def HandleExiting(self, m, l , orgnode):
        self.skipExport = False

    def HandleIn(self,l, orgnode):
        if(not self.skipExport):
            self.e.doc.append(l)


class LatexDynamicBlockState(exp.DynamicBlockState):
    def __init__(self,doc):
        super(LatexDynamicBlockState,self).__init__(doc)
        self.skip = False
    def HandleEntering(self,m,l,orgnode):
        self.skip = False
        language = m.group('lang')
        paramstr = l[len(m.group(0)):]
        p = type('', (), {})() 
        src.BuildFullParamList(p,language,paramstr,orgnode)
        exp = p.params.Get("exports",None)
        if(isinstance(exp,list) and len(exp) > 0):
            exp = exp[0]
        if(exp == 'results' or exp == 'none'):
            self.skip = True
            return
        self.e.doc.append(r"  \begin{verbatim}")
    def HandleExiting(self, m, l , orgnode):
        if(not self.skip):
            self.e.doc.append(r"  \end{verbatim}")
        self.skip = False
    def HandleIn(self,l, orgnode):
        if(not self.skip):
            self.e.doc.append(l)

class LatexQuoteBlockState(exp.QuoteBlockState):
    def __init__(self,doc):
        super(LatexQuoteBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        self.e.doc.append(r"  \begin{displayquote}")
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"  \end{displayquote}")
    def HandleIn(self,l, orgnode):
        self.e.doc.append(l)

class LatexExampleBlockState(exp.ExampleBlockState):
    def __init__(self,doc):
        super(LatexExampleBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        self.e.doc.append(r"  \begin{verbatim}")
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"  \end{verbatim}")
    def HandleIn(self,l, orgnode):
        self.e.doc.append(l)

class LatexGenericBlockState(exp.GenericBlockState):
    def __init__(self,doc):
        super(LatexGenericBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        self.data = m.group('data').strip().lower()
        self.e.doc.append(r"  \begin{{{data}}}".format(data=self.data))
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"  \end{{{data}}}".format(data=self.data))
    def HandleIn(self,l, orgnode):
        self.e.doc.append(l)


class LatexUnorderedListBlockState(exp.UnorderedListBlockState):
    def __init__(self,doc):
        super(LatexUnorderedListBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        self.e.doc.append(r"    \begin{itemize}")
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"     \end{itemize}")
    def HandleItem(self,m,l, orgnode):
        data = self.e.Escape(m.group('data'))
        self.e.doc.append(r"     \item {content}".format(content=data))

class LatexOrderedListBlockState(exp.OrderedListBlockState):
    def __init__(self,doc):
        super(LatexOrderedListBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        self.e.doc.append(r"    \begin{enumerate}")
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"     \end{enumerate}")
    def HandleItem(self,m,l, orgnode):
        data = self.e.Escape(m.group('data'))
        self.e.doc.append(r"     \item {content}".format(content=data))

class LatexCheckboxListBlockState(exp.CheckboxListBlockState):
    def __init__(self,doc):
        super(LatexCheckboxListBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        self.e.doc.append(r"    \begin{todolist}")
    def HandleExiting(self, m, l , orgnode):
        self.e.doc.append(r"     \end{todolist}")
    def HandleItem(self,m,l, orgnode):
        data = self.e.Escape(m.group('data'))
        state = m.group('state')
        if(state == 'x'):
            self.e.doc.append(r"     \item[\wontfix] {content}".format(content=data))
        elif(state == '-'):
            self.e.doc.append(r"     \item {content}".format(content=data))
            #self.e.doc.append(r"     \item[\inp] {content}".format(content=data))
        else:
            self.e.doc.append(r"     \item {content}".format(content=data))

class LatexTableBlockState(exp.TableBlockState):
    def __init__(self,doc):
        super(LatexTableBlockState,self).__init__(doc)
    def HandleEntering(self,m,l,orgnode):
        tabledef = ""
        tds = None
        if(not RE_TABLE_SEPARATOR.search(l)):
            tds = l.split('|')
            if(len(tds) > 1):
                tabledef = ("|c" * (len(tds)-2)) + "|"
        self.e.doc.append(r"    \begin{table}[!htp]")
        if(self.e.GetAttrib('caption')):
            self.e.doc.append(r"    \caption{{{caption}}}".format(caption=self.e.GetAttrib('caption')))
            #self.fs.write("    <caption class=\"t-above\"><span class=\"table-number\">Table {index}:</span>{caption}</caption>".format(index=self.tableIndex,caption=self.caption))
            #self.tableIndex += 1
            self.e.ClearAttrib()
        self.e.doc.append(r"    \centering\renewcommand{\arraystretch}{1.2}")
        self.e.doc.append(r"    \begin{{tabular}}{{{tabledef}}}".format(tabledef=tabledef))
        self.e.doc.append(r"    \hline") 
        if(tds):
            self.HandleData(tds,True)
    def HandleExiting(self, m, l , orgnode):
        print("EXIT")
        self.e.doc.append(r"    \hline")
        self.e.doc.append(r"    \end{tabular}")
        self.e.doc.append(r"    \end{table}")

    def HandleData(self,tds,head=False): 
        if(len(tds) > 3):
            # An actual table row, build a row
            first = True
            line = "    "
            for td in tds[1:-1]:
                if(not first):
                    line += " & "
                first = False
                if(head):
                    line += r"\textbf{{{data}}}".format(data=self.e.Escape(td))
                else:
                    line += self.e.Escape(td)
            line += " \\\\"
            self.e.doc.append(line)
            haveTableHeader = True

    def HandleIn(self,l, orgnode):
        print("IN")
        if(RE_TABLE_SEPARATOR.search(l)):
            self.e.doc.append(r'    \hline')
        else:
            tds = l.split('|')
            self.HandleData(tds)

class LatexHrParser(exp.HrParser):
    def __init__(self,doc):
        super(LatexHrParser,self).__init__(doc)
    def HandleLine(self,m,l,n):
        self.e.doc.append(r"\newline\noindent\rule{\textwidth}{0.5pt}")

class LatexEmptyParser(exp.EmptyParser):
    def __init__(self,doc):
        super(LatexEmptyParser,self).__init__(doc)
    def HandleLine(self,m,l,n):
        self.e.doc.append(r"\newline")

class LatexActiveDateParser(exp.EmptyParser):
    def __init__(self,doc):
        super(LatexActiveDateParser,self).__init__(doc)
    def HandleLine(self,m,l,n):
        self.e.doc.append(r"\textit{{{date}}}".format(date=m.group()))

class LatexBoldParser(exp.BoldParser):
    def __init__(self,doc):
        super(LatexBoldParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(self.sre.sub(r"\\textbf{\g<data>}",m.group()))

class LatexItalicsParser(exp.ItalicsParser):
    def __init__(self,doc):
        super(LatexItalicsParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(self.sre.sub(r"\\textit{\g<data>}",m.group()))

class LatexUnderlineParser(exp.UnderlineParser):
    def __init__(self,doc):
        super(LatexUnderlineParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(self.sre.sub(r"\\underline{\g<data>}",m.group()))

class LatexStrikethroughParser(exp.StrikethroughParser):
    def __init__(self,doc):
        super(LatexStrikethroughParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(self.sre.sub(r"\\sout{\g<data>}",m.group()))

class LatexCodeParser(exp.CodeParser):
    def __init__(self,doc):
        super(LatexCodeParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(self.sre.sub(r"\\texttt{\g<data>}",m.group()))

class LatexVerbatimParser(exp.VerbatimParser):
    def __init__(self,doc):
        super(LatexVerbatimParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(self.sre.sub(r"\\texttt{\g<data>}",m.group()))

# Simple links are easy. The hard part is images, includes and results
class LatexLinkParser(exp.LinkParser):
    def __init__(self,doc):
        super(LatexLinkParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        link = m.group('link').strip()
        desc = m.group('desc')
        if(desc):
            desc = self.e.Escape(desc.strip())
        if(link.startswith("file:")):
            link = re.sub(r'^file:','',link)  
        link = re.sub(r"[:][:][^/].*","",link)
        link = link.replace("\\","/")
        text = m.group()
        if(desc):
            self.e.doc.append(r"\href{{{link}}}{{{desc}}}".format(link=link,desc=desc))
        else:
            self.e.doc.append(r"\href{{{link}}}{{{desc}}}".format(link=link,desc=self.e.Escape(link)))

# <<TARGET>>
class LatexTargetParser(exp.TargetParser):
    def __init__(self,doc):
        super(LatexTargetParser,self).__init__(doc)
    def HandleSegment(self,m,l,n):
        self.e.doc.append(r"\label{{{data}}}".format(data=m.group('data')))

class LatexDoc(exp.OrgExporter):
    def __init__(self,filename,file,**kwargs):
        super(LatexDoc, self).__init__(filename, file, **kwargs)
        self.documentclass = r'\documentclass{article}'
        self.pre      = []
        self.doc      = []
        self.attribs  = {}
        self.amInBlock = False
        # TODO: Make this configurable
        self.pre.append(r"\usepackage[utf8]{inputenc}")
        self.pre.append(r"\usepackage{listings}")
        self.pre.append(r"\usepackage{hyperref}")
        self.pre.append(r"\usepackage{csquotes}")
        self.pre.append(r"\usepackage{makecell, caption}")
        self.pre.append(r"\usepackage[T1]{fontenc}")
        self.pre.append(r"\usepackage[greek,english]{babel}")
        self.pre.append(r"\usepackage{CJKutf8}")
        self.pre.append(r"\usepackage{graphicx}")
        self.pre.append(r"\usepackage{grffile}")
        self.pre.append(r"\usepackage{longtable}")
        self.pre.append(r"\usepackage{wrapfig}")
        self.pre.append(r"\usepackage{rotating}")
        self.pre.append(r"\usepackage{textcomp}")
        self.pre.append(r"\usepackage{capt-of}")
        # Needed for strikethrough
        self.pre.append(r"\usepackage[normalem]{ulem}")
        # Checkbox Setup
        self.pre.append(r"\usepackage{enumitem,amssymb}")
        self.pre.append(r"\newlist{todolist}{itemize}{2}")
        self.pre.append(r"\setlist[todolist]{label=$\square$}")
        self.pre.append(r"\usepackage{pifont}")
        self.pre.append(r"\newcommand{\cmark}{\ding{51}}%")
        self.pre.append(r"\newcommand{\xmark}{\ding{55}}%")
        self.pre.append(r"\newcommand{\tridot}{\ding{213}}%")
        self.pre.append(r"\newcommand{\inp}{\rlap{$\square$}{\large\hspace{1pt}\tridot}}")
        self.pre.append(r"\newcommand{\done}{\rlap{$\square$}{\raisebox{2pt}{\large\hspace{1pt}\cmark}}%")
        self.pre.append(r"\hspace{-2.5pt}}")
        self.pre.append(r"\newcommand{\wontfix}{\rlap{$\square$}{\large\hspace{1pt}\xmark}}")
        #self.pre.append(r"\usepackage{flafter}") 
        self.nodeParsers = [
        exp.CaptionAttributeParser(self),
        LatexTableBlockState(self),
        LatexSourceBlockState(self),
        LatexDynamicBlockState(self),
        LatexQuoteBlockState(self),
        LatexExampleBlockState(self),
        LatexCheckboxListBlockState(self),
        LatexUnorderedListBlockState(self),
        LatexOrderedListBlockState(self),
        LatexExportBlockState(self),
        LatexGenericBlockState(self),
        exp.DrawerBlockState(self),
        exp.SchedulingStripper(self),
        exp.TblFmStripper(self),
        LatexLinkParser(self),
        LatexHrParser(self),
        #LatexEmptyParser(self),
        LatexActiveDateParser(self),
        LatexBoldParser(self),
        LatexItalicsParser(self),
        LatexUnderlineParser(self),
        LatexStrikethroughParser(self),
        LatexCodeParser(self),
        LatexVerbatimParser(self),
        LatexTargetParser(self)
        ]

    def SetAmInBlock(self,inBlock):
        self.amInBlock = inBlock

    def AmInBlock(self):
        return self.amInBlock

    def AddAttrib(self,name,val):
        self.attribs[name] = val.strip()
    
    def GetAttrib(self,name):
        if(name in self.attribs):
            return self.attribs[name]
        return None

    def ClearAttrib(self):
        self.attribs.clear()

    def setClass(self,className):
        self.documentclass = r'\documentclass{{{docclass}}}'.format(docclass=className)

    def BuildDoc(self):
        out = self.documentclass + '\n' + '\n'.join(self.pre) + '\n' + r'\begin{document}' + '\n' + '\n'.join(self.doc) + '\n' + r'\end{document}' + '\n'
        return out

    # Document header metadata should go in here
    def AddExportMetaCustom(self):
        if(self.author):
            self.pre.append(r"\author{{{data}}}".format(data=self.author))
        if(self.title):
            self.pre.append(r"\title{{{data}}}".format(data=self.title))
        pass

    # Setup to start the export of a node
    def StartNode(self, n):
        pass 

    def Escape(self,str):
        str,cnt = self.SingleLineReplacements(str)
        if(0 == cnt):
            return self.TexFullEscape(str)
        elif(1 == cnt):
            return self.TexCommandEscape(str)
        else:
            return str

    def TexFullEscape(self,text):
        conv = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
        '\\': r'\textbackslash{}',
        '<': r'\textless{}',
        '>': r'\textgreater{}',
        }



        cleanre = re.compile(r'([^\\])(\%|\&|\$|\#|\_|\{|\}|\~|\^|\\|\>|\<)')
        #print("AAA: " + '|'.join(re.escape(str(key)) for key in sorted(conv.keys(), key = lambda item: - len(item))))

        #cleanre = re.compile('(.)(' + '|'.join(re.escape(str(key)) for key in sorted(conv.keys(), key = lambda item: - len(item))) + ")")
        result = cleanre.sub(lambda match: (match.group(1) if match.group(1) else "") + conv[match.group(2)] if (match.group(1) and match.group(1) != "\\") else match.group(), text)        
        return result

    
    def TexCommandEscape(self,text):
        conv = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
        '<': r'\textless{}',
        '>': r'\textgreater{}',
        }
        cleanre = re.compile(r'([^\\])(\%|\&|\$|\#|\_|\~|\^|\>|\<)')
        result = cleanre.sub(lambda match: (match.group(1) if match.group(1) else "") + conv[match.group(2)] if (match.group(1) and match.group(1) != "\\") else match.group(), text)        
        return result
        #return cleanre.sub(lambda match: conv[match.group()], text)        

    def SingleLineReplace(self,reg,rep,text,ok):
        nt = reg.sub(rep,text)
        ok = ok or nt != text
        return (nt,ok)

    def SingleLineReplacements(self,text):
        didRep = 0
        text = exp.RE_TITLE.sub("",text)
        text = exp.RE_AUTHOR.sub("",text)
        text = exp.RE_LANGUAGE.sub("",text)
        text = exp.RE_EMAIL.sub("",text)
        text = exp.RE_DATE.sub("",text)
        m = RE_LINK.search(text)
        if(m):
            link = m.group('link').strip()
            desc = m.group('desc')
            if(desc):
                desc = self.TexFullEscape(desc.strip())
            if(False and (link.endswith(".png") or link.endswith(".jpg") or link.endswith(".jpeg") or link.endswith(".gif"))):
                if(link.startswith("file:")):
                    link = re.sub(r'^file:','',link)  
                extradata = ""  
                if(self.commentName and self.commentName in link):
                    extradata =  " " + self.commentData
                    self.commentName = None
                if(hasattr(self,'attrs')):
                    for key in self.attrs:
                        extradata += " " + str(key) + "=\"" + str(self.attrs[key]) + "\""
                preamble = ""
                postamble = ""
                if(hasattr(self,'caption') and self.caption):
                    pass
                    #preamble = "<div class=\"figure\"><p>"
                    #postamble = "</p><p><span class=\"figure-number\">Figure {index}: </span>{caption}</p></div>".format(index=self.figureIndex,caption=self.caption)
                    self.figureIndex += 1
                #text = RE_LINK.sub("{preamble}<img src=\"{link}\" alt=\"{desc}\"{extradata}>{postamble}".format(preamble=preamble,link=link,desc=desc,extradata=extradata,postamble=postamble),line)
                didRep = True
                #self.ClearAttributes()
                return (text,2)
            else:
                if(link.startswith("file:")):
                    link = re.sub(r'^file:','',link)  
                link = re.sub(r"[:][:][^/].*","",link)
                #link = self.TexFullEscape(link)
                link = link.replace("\\","/")
                if(desc):
                    text = RE_LINK.sub(r"\\ref{{{link}}}{{{desc}}}".format(link=link,desc=desc),text)
                else:
                    text = RE_LINK.sub(r"\\ref{{{link}}}".format(link=link),text)
                didRep = 2
                #self.ClearAttributes()
                return (text,2)

        text,didRep = self.SingleLineReplace(exp.RE_NAME,r"\label{\g<data>}",text,didRep)
        text,didRep = self.SingleLineReplace(exp.RE_BOLD,r"\\textbf{\g<data>}",text,didRep)
        text,didRep = self.SingleLineReplace(exp.RE_ITALICS,r"\\textit{\g<data>}",text,didRep)
        text,didRep = self.SingleLineReplace(exp.RE_UNDERLINE,r"\underline{\g<data>}",text,didRep)
        text,didRep = self.SingleLineReplace(exp.RE_CODE,r"\\texttt{\g<data>}",text,didRep)
        text,didRep = self.SingleLineReplace(exp.RE_VERBATIM,r"\\texttt{\g<data>}",text,didRep)
        text,didRep = self.SingleLineReplace(exp.RE_HR,r"\hrulefill",text,didRep)
        return (text,1 if didRep else 0)

    # Export the heading of this node
    def NodeHeading(self,n):
        heading = self.Escape(n.heading)
        level = n.level
        if(level >= len(sectionTypes)):
            level = len(sectionTypes)-1
        self.doc.append(sectionTypes[level].format(heading=heading))

    # We are about to start exporting the nodes body
    def StartNodeBody(self,n):
        pass

    def AttributesGather(self, l):
        return False


    def NodeBody(self,n):
        ilines = n._lines[1:]
        for parser in self.nodeParsers:
            ilines = parser.Handle(ilines,n)
        for line in ilines:
            self.doc.append(self.TexFullEscape(line))


    # Actually buid the node body in the document
    def OldNodeBody(self,slide):
        inDrawer = False
        inResults= False
        inUl     = 0
        ulIndent = 0
        inTable  = False
        haveTableHeader = False
        inSrc    = False
        skipSrc  = False
        inDynSrc    = False
        skipDynSrc  = False
        exp      = None

        blockParsers = [LatexSourceBlockState(self.doc)]
        for l in slide._lines[1:]:
          if(self.AttributesGather(l)):
            continue
          if(inResults):
            if(l.strip() == ""):
              inResults = False
            elif(RE_ENDSRC.search(l) or RE_END_DRAWER_LINE.search(l)):
              inResults = False
              continue
            if(inResults):
              if(exp == 'code' or exp == 'none'):
                continue
              else:
                line = self.Escape(l)
                self.doc.append(line)
                continue
          if(inDrawer):
            if(RE_END_DRAWER_LINE.search(l)):
              inDrawer = False
            continue
          if(inTable):
            if(RE_TABLE_ROW.search(l)):
              if(RE_TABLE_SEPARATOR.search(l)):
                continue
              else:
                tds = l.split('|')
                if(len(tds) > 3):
                  # An actual table row, build a row
                  first = True
                  line = "    "
                  for td in tds[1:-1]:
                    if(not first):
                        line += " & "
                    first = False
                    line += self.Escape(td)
                  line += " \\\\"
                  self.doc.append(line)
                  haveTableHeader = True
                  continue
            else:
              self.doc.append(r"    \hline")
              self.doc.append(r"    \end{tabular}")
              self.doc.append(r"    \end{table}")
              inTable         = False
              haveTableHeader = False
          if(inDynSrc):
            if(RE_ENDDYN.search(l)):
              inDynSrc = False
              if(skipDynSrc):
                skipDynSrc = False
                continue
              self.doc.append(r"  \end{verbatim}")
              continue
            else:
              if(not skipDynSrc):
                self.doc.append(l)
              continue
          if(inSrc):
            if(RE_ENDSRC.search(l)):
              inSrc = False
              if(skipSrc):
                skipSrc = False
                continue
              self.doc.append(r"  \end{lstlisting}")
              continue
            else:
              if(not skipSrc):
                self.doc.append(l)
              continue
          m = RE_STARTDYN.search(l)
          if(m):
            inDynSrc = True
            language = m.group('lang')
            paramstr = l[len(m.group(0)):]
            p = type('', (), {})() 
            src.BuildFullParamList(p,language,paramstr,slide)
            exp = p.params.Get("exports",None)
            if(isinstance(exp,list) and len(exp) > 0):
              exp = exp[0]
            if(exp == 'results' or exp == 'none'):
              skipDynSrc = True
              continue
            self.doc.append(r"  \begin{verbatim}")
          # src block
          m = RE_STARTSRC.search(l)
          if(m):
            inSrc = True
            language = m.group('lang')
            paramstr = l[len(m.group(0)):]
            p = type('', (), {})() 
            src.BuildFullParamList(p,language,paramstr,slide)
            exp = p.params.Get("exports",None)
            if(isinstance(exp,list) and len(exp) > 0):
              exp = exp[0]
            if(exp == 'results' or exp == 'none'):
              skipSrc = True
              continue
            # Some languages we skip source by default
            skipLangs = sets.Get("htmlDefaultSkipSrc",[])
            if(exp == None and language == skipLangs):
              skipSrc = True
              continue
            #params = {}
            #for ps in RE_FN_MATCH.finditer(paramstr):
            # params[ps.group(1)] = ps.group(2)
            attribs = ""
            # This is left over from reveal.
            if(p.params.Get("data-line-numbers",None)):
              attribs += " data-line-numbers=\"{nums}\"".format(nums=p.params.Get("data-line-numbers",""))
            if(haveLang(language)):
                self.doc.append(r"  \begin{{lstlisting}}[language={lang}]".format(lang=mapLanguage(language)))
            else:
                self.doc.append(r"  \begin{lstlisting}")
            continue
          # property drawer
          if(RE_DRAWER_LINE.search(l)):
            inDrawer = True
            continue
          # scheduling
          if(RE_SCHEDULING_LINE.search(l)):
            continue
          if(RE_RESULTS.search(l)):
            inResults = True
            continue
          m = RE_COMMENT_TAG.search(l)
          if(m):
            self.commentData = m.group('props')
            self.commentName = m.group('name')
            continue
    
          m = RE_TABLE_ROW.search(l)
          if(m):
            tabledef = ""
            tds = None
            if(not RE_TABLE_SEPARATOR.search(l)):
              tds = l.split('|')
              if(len(tds) > 1):
                tabledef = ("|c" * (len(tds)-2)) + "|"
            self.doc.append(r"    \begin{table}")
            self.doc.append(r"    \centering")
            self.doc.append(r"    \begin{{tabular}}{{{tabledef}}}".format(tabledef=tabledef))
            self.doc.append(r"    \hline") 
            if(hasattr(self,'caption') and self.caption):
                self.doc.append(r"    \caption{{{caption}}}".format(caption=self.caption))
                #self.fs.write("    <caption class=\"t-above\"><span class=\"table-number\">Table {index}:</span>{caption}</caption>".format(index=self.tableIndex,caption=self.caption))
                self.tableIndex += 1
                self.ClearAttributes()
            if(tds):
                first = True
                line = "    "
                for td in tds[1:-1]:
                    if(not first):
                        line += " & "
                    first = False
                    line += self.Escape(td)
                line += " \\\\"
                self.doc.append(line)
                haveTableHeader = True
            inTable = True
            continue
          m = RE_UL.search(l)
          if(m):
            thisIndent = len(m.group('indent'))
            if(not inUl):
              ulIndent = thisIndent
              self.doc.append(r"    \begin{itemize}")
              inUl += 1
            elif(thisIndent > ulIndent):
              ulIndent = thisIndent
              self.doc.append(r"     \begin{itemize}")
              inUl += 1
            elif(thisIndent < ulIndent and inUl > 1):
              inUl -= 1
              self.doc.append(r"     \end{itemize}")
            data = self.Escape(m.group('data'))
            self.doc.append(r"     \item {content}".format(content=data))
            continue
          elif(inUl):
            while(inUl > 0):
              inUl -= 1
              self.doc.append(r"     \end{itemize}")
          if(RE_EMPTY_LINE.search(l)):
            self.doc.append(r"   \smallskip")
          # Normal Write
          line = self.Escape(l)
          self.doc.append(line)
        if(inUl):
          inUl -= 1
          self.doc.append(r"     \end{itemize}")

    # We are done exporting the nodes body so finish it off
    def EndNodeBody(self,n):
        pass

    # We are now done the node itself so finish that off
    def EndNode(self,n):
        pass

    # def about to start exporting nodes
    def StartNodes(self):
        pass

    # done exporting nodes
    def EndNodes(self):
        pass

    def StartDocument(self, file):
        pass

    def EndDocument(self):
        pass

    def InsertScripts(self,file):
        pass

    def StartHead(self):
        pass

    def EndHead(self):
        pass

    def StartBody(self):
        pass

    def EndBody(self):
        pass

    def FinishDocCustom(self):
        self.fs.write(self.BuildDoc())

    def Execute(self):
        cmdStr = sets.Get("latex2Pdf","C:\\texlive\\2021\\bin\\win32\\pdflatex.exe")
        commandLine = [cmdStr, self.outputFilename]
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
        log.debug(o)
        log.debug(e)
        #log.debug(o.split('\n') + e.split('\n'))

# ============================================================
class OrgExportFileAsLatexCommand(sublime_plugin.TextCommand):

    def OnDoneSourceBlockExecution(self):
        # Reload if necessary
        self.file = db.Get().FindInfo(self.view)
        self.doc  = None
        self.docClass = exp.GetGlobalOption(self.file,"LATEX_CLASS","latexClass","article").lower()
        try:
            outputFilename = exp.ExportFilename(self.view,".tex",self.suffix)
            self.doc       = LatexDoc(outputFilename,self.file)
            self.doc.setClass(self.docClass)
            self.helper    = exp.OrgExportHelper(self.view,self.index)
            self.helper.Run(outputFilename, self.doc)
            self.doc.Execute()
        finally:    
            evt.EmitIf(self.onDone)


    def run(self,edit, onDone=None, index=None, suffix=""):
        self.file = db.Get().FindInfo(self.view)
        self.onDone = onDone
        self.suffix = suffix
        if(index != None):
            self.index = index
        else:
            self.index = None
        if(None == self.file):
            log.error("Not an org file? Cannot build reveal document")
            evt.EmitIf(onDone)  
            return
        if(sets.Get("latexExecuteSourceOnExport",False)):
            self.view.run_command('org_execute_all_source_blocks',{"onDone":evt.Make(self.OnDoneSourceBlockExecution),"amExporting": True})
        else:
            self.OnDoneSourceBlockExecution()


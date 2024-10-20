import sublime
import sublime_plugin
import requests
import logging
import traceback
import OrgExtended.asettings as sets
import OrgExtended.pymitter as evt

log = logging.getLogger(__name__)

def getOrgs() -> str:
    url = sets.Get("orgsUrl", None)
    return url

def haveOrgs() -> bool:
    return getCon() is not None

CONTENT_TYPE = 'Content-Type'
CTYPE_JSON     = 'application/json'
CTYPE_TEXT     = 'text/plain; charset=utf-8'

class NodeTarget:
    def __init__(self, fname, id, type):
        self.filename = fname
        self.id = id
        self.type = type

    def __repr__(self):
        return f"Tgt (id: {self.id}, type: {self.type}, fn: {self.filename})"

    def ToDict(self):
       return {
        "Filename": target.filename,
        "Id": target.id,
        "Type": target.type
        }

class OrgS:
    def __init__(self):
        pass

    def post(self, body):
        url = getOrgs()
        if url is None:
            # TODO: Is this what we should return?
            return None
        data = json.dumps(body)
        response = requests.post(url, data=data)
        if not response.ok:
            log.error(f"ORGS POST ERROR: {response}")
        if(not CONTENT_TYPE in response.headers or response.headers[CONTENT_TYPE] != CTYPE_JSON):
            log.warning(f"WARNING: Invalid response type from orgs? {response.headers[CONTENT_TYPE]}")
        return response.json()
        # TODO Handle creds

    def get(self, url, params=None):
        headers = {
            CONTENT_TYPE: CTYPE_JSON,
            'Accept': CTYPE_JSON
        }
        base = getOrgs()
        if base is None:
            log.error("ORGS: Base url is none")
            return None
        url = base + url
        response = requests.get(url, headers=headers)
        if not response.ok:
            log.error(f"ORGS GET ERROR: {response}")
        if(not CONTENT_TYPE in response.headers or response.headers[CONTENT_TYPE] != CTYPE_JSON):
            log.warning(f"WARNING: Invalid response type from orgs? {response.headers[CONTENT_TYPE]}")
        return response.json()
        # TODO Handle creds

    # TODO: Need event based mechanism here this has to be
    #.      async. Can I do closures or something better
    #.      in this python version?
    def RefileTargets(self):
        return self.get('/refilefiles')

    def AgendaRest(self):
        now = datetime.dateime.now()
        params = None
        #url.searchParams.append('query',`!IsProject() && !IsArchived() && IsTodo() && OnDate("${now.getFullYear()} ${pad2(now.getDate())} ${pad2(now.getMonth()+1)}")`);
        return self.get("/search", params=params)

    def Query(self, query: str):
        qry = "!IsArchived() && IsTodo()"
        if query and query != "":
            qry = query
        params = {
            "query": qry
        }
        return self.get(f"/search", params=params)

    # Conversion queries
    # Based on a query string return the selected nodes
    # converted to another format
    def FileQuery(self, name: str, query: str=None):
        qry = "!IsArchived() && IsTodo()"
        if query and query != "":
            qry = query
        params = {
            "query": qry
        }
        return self.get(f"/file/{name}", params=params)

    def Gantt(self, query: str = None):
        return self.FileQuery("mermaid", query)

    def MindMap(self, query: str = None):
        return self.FileQuery("mindmap", query)

    def Html(self, query: str = None):
        return self.FileQuery("html", query)

    def Latex(self, query: str = None):
        return self.FileQuery("latex", query)

    def RevealJs(self, query: str = None):
        return self.FileQuery("revealjs", query)

    def RevealJs(self, query: str = None):
        return self.FileQuery("impressjs", query)

    def LookupHash(self, file:str, pos):
        params = {
            "pos": pos,
            "filename": file
        }
        return self.get("/lookuphash", params=params)

    def _getFilename(self, fileOrView):
        if(util.isView(fileOrView)):
            id = fileOrView.file_name()
            return id
        else:
            return fileOrView

    def GetFullFile(self, fileOrView):
        id = self._getFilename()
        if id:
            params = {
                "filename": file
            }
            return self.get("/orgfile", params=params)

    def FindInfoSource(self, fileOrView):
        if (not fileOrView):
            return None
        fname = self._getFilename(fileOrView)
        if fname:
            return self.GetFullFile(fname)
        return None

    def LookupCurrentHash(self, view):
        if (util.isView(view)):
            row, col = view.rowcol()
            fname = view.file_name()
            return self.LookupHash(fname, row)
        return None

    def GetHashTarget(self, view):
        if (util.isView(view)):
            row, col = view.rowcol()
            t = NodeTarget(view.file_name(), self.LookupHash(view.file_name(), row), 'hash')
            return t
        return None

    def DayPage(self,tm=None):
        if tm is None:
            tm = datetime.datetime.now()
        url = f"/daypage/{tm.year}-{tm.day}-{tm.month+1}/"
        return self.get(url)

    # For compatibility with VSCode API, really should fix that.
    def GetDayPage(self, tm):
        return self.DayPage(tm)

    def GetDayPageIncrement(self):
        return self.get("/daypage/increment/")

    def CreateDayPage(self):
        self.post("/daypage", {})

    def Capture(self, name: str, headline: str, content: str, tags=[], props={}, priority:str=""):
        return self.post("/capture", {
            "Template": name, 
            "NewNode": {
                "Headline": headline,
                "Content": content,
                "Tags": tags,
                "Props": props,
                "Priority": priority
                },
            })

    def Delete(self,target: NodeTarget):
        return self.post("/delete", target.ToDict())

    def Refile(self, src: NodeTarget, dest: NodeTarget):
        return self.post("/refile", {
            "FromId": src.ToDict(),
            "ToId": dest.ToDict()
            })

    def Archive(self, src: NodeTarget):
        return self.post("/archive", src.ToDict())


    def CaptureTemplates(self):
        return self.get("/capture/templates")


    def SetProperty(self, hash: str, name: str, value: str):
        return self.post("/property", {"Hash": hash, "Name": name, "Value": value})

    def ReFormat(self, filename: str):
        return self.post("/reformat", [filename])


    def SetMarker(self, src: NodeTarget, marker: str):
        return self.post("/setexclusivemarker", {
            "ToId": src.ToDict(),
            "Name": marker
            })

    def GetMarker(self, marker: str):
        return self.get("/exclusivemarker", params={
                "name": marker
            })

    def CreateJira(self, src: NodeTarget):
        return self.post("/update", {
            "Target": src.ToDict(),
            "Name": "jira"
            })

    def ClockIn(self, src: NodeTarget):
        return self.post("/clockin", src.ToDict())

    def ClockOut(self):
        return self.post("/clockout",{})

    def ClockActive(self):
        return self.get("/clock")


    def ExecBlock(self, src: NodeTarget, row):
        return self.post("/execb", {
            "Target": src.ToDict(),
            "Row": row
            })

    def ExecTable(self, src: NodeTarget, row):
        return self.post("/exectable", {
            "Target": src.ToDict(),
            "Row": row
            })

    def ExecAllTable(self, fname: str):
        return self.post("/execalltables", fname)


    def FormulaDetails(self, src: NodeTarget, row):
        return self.post("/tableformulainfo", {
            "Target": src.ToDict(),
            "Row": row
            })

# GLOBAL Singleton - Orgs is a replacement for the sublime DB
#                    this is an external go based org mode sever
#                    that all running instances of sublime will share.
#                    The orgs server gets the "org mode" aspect
#                    out of sublime text itself and into a sharable
#                    form that can be used in other editors, web apps
#                    command line tools and other things.
#
#                    It can be running while sublime is down
#                    and can be accessed remotely if desired.
orgsInstance = OrgS()
def Get() -> OrgS:
    global orgsInstance
    return orgsInstance

class OrgTestOrgsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        Get().RefileTargets()

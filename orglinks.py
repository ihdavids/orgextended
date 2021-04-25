import sublime
import sublime_plugin
import re
import os
from   OrgExtended.orgparse.sublimenode import * 
import OrgExtended.orgutil.util as util
from OrgExtended.orgutil.util import *
import logging
import OrgExtended.orgdb as db
import OrgExtended.asettings as sets
import OrgExtended.orgextension as ext
from collections import defaultdict
import struct
import imghdr
import urllib.request
import yaml
import OrgExtended.orgneovi as nvi
import OrgExtended.pymitter as evt
from   OrgExtended.orgplist import *
import OrgExtended.orguniqueview as uview

try:
    import importlib
except ImportError:
    pass

log = logging.getLogger(__name__)

# This is entirely copied from the wonderful OrgMode plugin
# found on package control. The orgmode plugin has a great base
# resolver system. I have copied it and will be extending it
# somewhat. OrgExtended is not compatible with orgmode
# so I have had to consume it here rather than just recommend
# you use it.


def find_all_links(view):
    links = view.find_by_selector("orgmode.link")
    return links

def extract_link(view):
    pt    = view.sel()[0].begin()
    links = find_all_links(view)
    for link in links:
        if(link.contains(pt)):
            return link
    return None


DEFAULT_LINK_RESOLVERS = [
    'internal',
    'http',
    'https',
    'prompt',
    'jira',
    'email',
    'file',
]

available_resolvers = ext.find_extension_modules('orgresolver', DEFAULT_LINK_RESOLVERS)
linkre              = re.compile(r"\[\[([^\[\]]+)\]\s*(\[[^\[\]]*\])?\]")

# Returns the url from the full link
def extract_link_url(str):
    m = linkre.search(str)
    return m.group(1)

def extract_link_url_from_region(view, region):
    return extract_link_url(view.substr(region))

def is_region_link(view, region):
    return 'orgmode.link' in view.scope_name(region.end())

def get_link_region_at(view):
    if(is_region_link(view, view.sel()[0])):
        return extract_link(view)
    return None

def find_image_file(view, url):
    # ABS
    if(os.path.isabs(url)):
        return url
    # Relative
    if(view != None):
        curDir = os.path.dirname(view.file_name())
        filename = os.path.join(curDir, url)
        if(os.path.isfile(filename)):
            return filename
    # In search path
    searchHere = sets.Get("imageSearchPath",[])
    for direc in searchHere:
        filename = os.path.join(direc, url)
        if(os.path.isfile(filename)):
            return filename

    searchHere = sets.Get("orgDirs",[])
    for direc in searchHere:
        filename = os.path.join(direc, "images", url) 
        if(os.path.isfile(filename)):
            return filename

RE_TARGET = re.compile(r'<<(?P<target>[^>]+)>>')
RE_NAMED = re.compile(r'[#][+]NAME[:]\s*(?P<target>.+)')
def CreateLink(view):
    fn = view.file_name()
    # Org Files have a LOT more potential for making links!
    if(util.isPotentialOrgFile(fn)):
        r = view.curRow()
        line = view.getLine(r)
        linet = RE_TARGET.match(line)
        namet = RE_NAMED.match(line)
        link = None
        # have target on this line?
        if(linet):
           link = "[[file:{0}::{1}][{1}]]".format(view.file_name(),linet.group('target'))
        # have named object on this line?
        if(link == None and namet):
           link = "[[file:{0}::{1}][{1}]]".format(view.file_name(),namet.group('target'))
        n = db.Get().AtInView(view)
        if(link == None and n and not n.is_root()):
            p  = n.get_property("ID")
            cp = n.get_property("CUSTOM_ID")
            if(p):
               link = "[[file:{0}::#{1}][{2}]]".format(view.file_name(),p,n.heading)
            # Have custom id?
            elif(cp):
               link = "[[file:{0}::#{1}][{2}]]".format(view.file_name(),cp,n.heading)
            # Am near a heading?
            else:
               link = "[[file:{0}::*{1}][{1}]]".format(view.file_name(),n.heading)
        # okay then just use row,col
        if(link == None):
            r,c = view.curRowCol()
            link = "[[file:{0}::{1},{2}][{3}]]".format(view.file_name(),r,c,os.path.basename(view.file_name()))
        return link
    else:
        # Other file types only have line and column
        r,c = view.curRowCol()
        link = "[[{0}::{1}::{2}][{3}]]".format(fn,r,c,os.path.basename(fn))
        return link

class OrgOpenLinkCommand(sublime_plugin.TextCommand):
    def resolve(self, content):
        for resolver in self.resolvers:
            result = resolver.resolve(content)
            if result is not None:
                return resolver, result
        return None, None

    def is_valid_scope(self, region):
        return is_region_link(self.view, region)

    def extract_content(self, region):
        return extract_link_url_from_region(self.view, region)

    def run(self, edit):
        # reload our resolvers if they are not loaded.
        #if(not hasattr(self, "resolvers")):
        wanted_resolvers = sets.Get("linkResolvers", DEFAULT_LINK_RESOLVERS)
        self.resolvers   = [available_resolvers[name].Resolver(self.view) for name in wanted_resolvers]

        # This is goofy. File loads get resolve called that calls extract.
        # extact may launch the file into sublime. IF we return a path
        # sublime will call start on the file.
        view = self.view
        for sel in view.sel():
            if not self.is_valid_scope(sel):
                continue
            region = extract_link(view) #view.extract_scope(sel.end())
            content = self.extract_content(region)
            resolver, newcontent = self.resolve(content)
            if newcontent is None:
                log.error(" Could not resolve link:\n%s" % content)
                sublime.error_message('Could not resolve link:\n%s' % content)
                continue
            resolver.execute(newcontent)

class OrgCreateLinkCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        link = CreateLink(self.view)
        sublime.set_clipboard(link)
        nvi.TestAndSetClip(self.view, link)



# global magic
VIEWS_WITH_IMAGES = set()

# Stolen from:
# https://github.com/renerocksai/sublime_zk/blob/master/sublime_zk.py
# The excellent work in that system showed a way of using
# Phantoms to show images inline. This gives us a part of one of Org Modes
# Most powerful features which is babel modes ability to make diagrams in
# documents.
class ImageHandler:
    Phantoms = defaultdict(set)
    Cache    = {}

    @staticmethod
    def save_cache():
       user_settings_path = os.path.join(sublime.packages_path(), "User","OrgExtended_image_cache.yaml")
       f = open(user_settings_path,"w")
       data = yaml.dump(ImageHandler.Cache, f)
       f.close() 

    @staticmethod
    def load_cache():
        user_settings_path = os.path.join(sublime.packages_path(), "User","OrgExtended_image_cache.yaml")
        if(os.path.isfile(user_settings_path)):
            stream = open(user_settings_path, 'r')
            ImageHandler.Cache = yaml.load(stream, Loader=yaml.SafeLoader)
            stream.close()

    @staticmethod
    def show_image(region, view, max_width=1024):
        width = -1
        height = -1
        node = db.Get().AtRegion(view,region)
        if(node):
            attr = node.get_comment("ORG_ATTR",None)
            if(attr):
                params = PList.createPList(attr)
                try:
                    width = int(params.Get('width',-1))
                    height = int(params.Get('height',-1))
                except:
                    log.error("Could not extract width and height from plist / ORG_ATTR comment")
        # If we already have this image then exit out
        if view.id() in ImageHandler.Phantoms and str(region) in ImageHandler.Phantoms[view.id()]:
            return
        url    = extract_link_url_from_region(view, region)
        # We can only handle links to images this way.
        if not util.is_image(url):
            return
        level  = db.Get().GetIndentForRegion(view, region)
        indent = "&nbsp;" * (level * 2)
        if url.startswith('http') or url.startswith('https'):
            img = url
            local_filename = None
            if(url in ImageHandler.Cache and os.path.isfile(ImageHandler.Cache[url])):
                local_filename = ImageHandler.Cache[url]
                log.debug("Loaded from cache: " + url)
            else:
                log.debug("Downloaded: " + url)
                local_filename, headers = urllib.request.urlretrieve(url)
                ImageHandler.Cache[url] = local_filename
                ImageHandler.save_cache()
            size = ImageHandler.get_image_size(local_filename)
            ttype = None
            if None != size:
                w, h, ttype = size
                if ttype and ttype == 'svg':
                    view.erase_phantoms(str(region))
                    html_img = util.get_as_string(img)
                    print(html_img)
                    view.add_phantom(str(region), region, html_img, sublime.LAYOUT_BLOCK)
                    ImageHandler.Phantoms[view.id()].add(str(region))
                    return
                FMT = u'''
                    {}<img src="data:image/{}" class="centerImage" {}>
                '''
            img = ttype + ";base64," + util.get_as_base64(img)
        elif url.startswith("file:"):
            url = url.replace("file:","")
            log.debug("FILE: " + url)
            FMT = '''
                {}<img src="file://{}" class="centerImage" {}>
            '''
            img  = find_image_file(view, url)
            if(img):
                size = ImageHandler.get_image_size(img)
                if(width > 0):
                    size = [width, size[1], size[2]]
                if(height > 0):
                    size = [size[0], height, size[2]]
            else:
                size = (100,100,"png")
        else:
            log.debug("local file: " + url)
            FMT = '''
                {}<img src="file://{}" class="centerImage" {}>
            '''
            img  = find_image_file(view, url)
            log.debug("local file2: " + url)
            size = ImageHandler.get_image_size(img)
            if(width > 0):
                size = [width, size[1], size[2]]
            if(height > 0):
                size = [size[0], height, size[2]]
        if not size:
            return
        w, h, t = size
        line_region = view.line(region)
        imgattr = ImageHandler.check_imgattr(view, line_region, region)
        if not imgattr:
            if w > max_width:
                m = max_width / w
                h *= m
                w = max_width
            imgattr = 'width="{}" height="{}"'.format(w, h)

        view.erase_phantoms(str(region))
        html_img = FMT.format(indent, img, imgattr)
        view.add_phantom(str(region), region, html_img, sublime.LAYOUT_BLOCK)
        ImageHandler.Phantoms[view.id()].add(str(region))

    @staticmethod
    def hide_image(region, view):
        try:
            view.erase_phantoms(str(region))
            ImageHandler.Phantoms[view.id()].remove(str(region))
        except:
            pass

    @staticmethod
    def show_image_at(view, max_width=1024):
        reg = get_link_region_at(view)
        if(reg):
            ImageHandler.show_image(reg, view)

    @staticmethod
    def hide_image_at(view, max_width=1024):
        reg = get_link_region_at(view)
        if(reg):
            ImageHandler.hide_image(reg, view)

    @staticmethod
    def show_images(view, max_width=1024):
        global VIEWS_WITH_IMAGES
        skip = 0

        while True:
            imageRegions = view.find_by_selector('orgmode.link')[skip:]
            skip += 1
            if not imageRegions:
                break
            region = imageRegions[0]
            ImageHandler.show_image(region, view, max_width)
        VIEWS_WITH_IMAGES.add(view.id())

    @staticmethod
    def check_imgattr(view, line_region, link_region=None):
        # find attrs for this link
        full_line = view.substr(line_region)
        link_till_eol = full_line[link_region.a - line_region.a:]
        # find attr if present
        m = re.match(r'.*\)\{(.*)\}', link_till_eol)
        if m:
            return m.groups()[0]

    @staticmethod
    def hide_images(view, edit):
        for rel_p in ImageHandler.Phantoms[view.id()]:
            view.erase_phantoms(rel_p)
        del ImageHandler.Phantoms[view.id()]
        skip = 0
        while True:
            img_regs = view.find_by_selector('orgmode.link.href')[skip:]
            skip += 1
            if not img_regs:
                break
            region = img_regs[0]
            rel_p = view.substr(region)
            if(util.is_image(rel_p)):
                pass
                #line_region = view.line(region)
                #line_str = view.substr(line_region)
                #view.replace(edit, line_region, line_str.strip())
        VIEWS_WITH_IMAGES.discard(view.id())

    @staticmethod
    def get_image_size(img):
        """
        Determine the image type of img and return its size.
        """
        #print("IMG: " + img)
        try:
            with open(img, 'rb') as f:
                head = f.read(24)
                ttype = None

                if b'<svg' in head:
                    ttype = 'svg'
                    width, height = (100,100)
                    return width, height, ttype
                if len(head) != 24:
                    return
                if imghdr.what(img) == 'png':
                    ttype = "png"
                    check = struct.unpack('>i', head[4:8])[0]
                    if check != 0x0d0a1a0a:
                        return
                    width, height = struct.unpack('>ii', head[16:24])
                elif imghdr.what(img) == 'gif':
                    ttype = "gif"
                    width, height = struct.unpack('<HH', head[6:10])
                elif imghdr.what(img) == 'jpeg':
                    ttype = "jpeg"
                    try:
                        f.seek(0)  # Read 0xff next
                        size = 2
                        ftype = 0
                        while not 0xc0 <= ftype <= 0xcf:
                            f.seek(size, 1)
                            byte = f.read(1)
                            while ord(byte) == 0xff:
                                byte = f.read(1)
                            ftype = ord(byte)
                            size = struct.unpack('>H', f.read(2))[0] - 2
                        # SOFn block
                        f.seek(1, 1)  # skip precision byte.
                        height, width = struct.unpack('>HH', f.read(4))
                    except Exception:
                        return
                else:
                    return
                return width, height, ttype
        except:
            return 100,100,'png'

class OrgCycleImagesCommand(sublime_plugin.TextCommand):
    def OnDone(self):
        self.view.sel().clear()
        self.view.sel().add(self.cursor)
        evt.EmitIf(self.onDone)

    def OnShown(self):
        self.OnDone()

    def OnHidden(self):
        self.view.run_command("org_show_images",{"onDone": evt.Make(self.OnShown)})

    def run(self, edit, onDone=None):
        self.onDone = onDone
        self.cursor = self.view.sel()[0]
        self.view.run_command("org_hide_images",{"onDone": evt.Make(self.OnHidden)})

class OrgShowImagesCommand(sublime_plugin.TextCommand):
    def run(self, edit,onDone=None):
        ImageHandler.show_images(self.view)
        evt.EmitIf(onDone)

class OrgHideImagesCommand(sublime_plugin.TextCommand):
    def run(self, edit,onDone=None):
        ImageHandler.hide_images(self.view, edit)
        evt.EmitIf(onDone)

class OrgShowImageCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        ImageHandler.show_image_at(self.view)

class OrgHideImageCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        ImageHandler.hide_image_at(self.view)

# ON LOAD HANDLER: if startup is set we show or hide the images.
#+STARTUP: inlineimages
#+STARTUP: noinlineimages
def get_show_images_default():
    return sets.Get("startup",["noinlineimages"])

def get_image_startup(node):
    startupDefault = get_show_images_default()
    return node.startup(startupDefault)

def onShutdown():
    ImageHandler.save_cache()

def onLoad(view):
    ImageHandler.load_cache()
    file = db.Get().FindInfo(view)
    if(file):
        startup = get_image_startup(file.org[0])
        if(Startup.inlineimages in startup):
            ImageHandler.show_images(view)


class OrgLinkToFileCommand(sublime_plugin.TextCommand):
    def on_done(self, index, modifiers=None):
        if(index >= 0):
            f = self.files[index]
            link = self.view.MakeRelativeToMe(f[0])
            desc = os.path.basename(link)
            if(len(f) > 1):
                desc = f[1]
                includeRoamTag = sets.Get("insertRoamTagToFileLink", True)
                if includeRoamTag is False:
                    log.error(self.rawTitles[f[0]])
                    desc = self.rawTitles[f[0]]
            indent = ""
            node = db.Get().AtInView(self.view)
            if(node):
                indent = node.indent()
            data = r"{indent}[[file:{link}][{desc}]]".format(indent=indent, link=link, desc=desc)
            self.view.run_command("org_internal_insert", {"location": self.view.sel()[0].begin(), "text": data})

    def run(self, edit):
        self.files = []
        self.rawTitles = {}
        for i in range(0, len(db.Get().Files)):
            filename = db.Get().Files[i].filename
            title = " ".join(db.Get().Files[i].org.get_comment("TITLE", "")).strip()
            self.rawTitles[filename] = title
            useRoamTags = sets.Get("linkFindUseRoamTags", True)
            if(useRoamTags):
                tags = " ".join(db.Get().Files[i].org.get_comment("ROAM_TAGS", "")).strip()
                if(tags != ""):
                    title = "(" + tags + ") " + title
            if(title != ""):
                self.files.append([filename, title])
            else:
                self.files.append([filename])
        self.view.window().show_quick_panel(self.files, self.on_done, -1, -1)

class OrgJumpToBacklinksCommand(sublime_plugin.TextCommand):
    def on_done(self, index, modifiers=None):
        if(index >= 0):
            f = self.links[index]
            fname = f.fromFile.filename + ":" + str(f.row)
            self.view.window().open_file(fname, sublime.ENCODED_POSITION)

    def run(self, edit):
        self.files = []
        bl = db.Get().GetBacklinks(self.view)
        if(bl):
            self.links = bl
            for l in bl:
                title = l.fromFile.org.get_comment("TITLE",[""])[0]
                desc = l.desc if l.desc else ""
                if(title.strip() != ""):
                    desc = title + ": " + desc
                self.files.append([desc, l.link])
            self.view.window().show_quick_panel(self.files, self.on_done, -1, -1)
            return
        log.debug("NO BACKLINKS")


def BuildBacklinksDisplay(view):
    bl = db.Get().GetBacklinks(view)
    if(bl):
        out = str(len(bl)) + " Backlinks\n"
        files = {}
        for l in bl:
            title = l.fromFile.org.get_comment("TITLE",[""])[0]
            if(title.strip() == ""):
                title = l.desc
                if(not title):
                    title = l.link
            if(not title in files):
                files[title] = []
            files[title].append(l)
        keys = list(files.keys())
        keys.sort()
        for k in keys:
            out += "\n"
            flist = files[k]
            flist = sorted(flist,key=lambda x: x.row)
            f = flist[0] 
            fn = f.fromFile.filename
            out += "* {}\n".format(k)
            for f in flist:
                desc = f.desc
                if(not desc):
                    desc = f.link
                out += "  - [[file:{}::{}][{}]]\n".format(fn,f.row,desc)
                if(f.linktext != f.text and (len(f.linktext)+5) < len(f.text)):
                    out += "    " + f.text.strip() + "\n"
        return out
    return "0 Backlinks"

def UpdateBacklinksForDisplay(view):
    if(uview.UniqueView.IsShowing("Backlinks")):
        out = BuildBacklinksDisplay(view)
        uv = uview.UniqueView.Get("Backlinks",curview=view)
        uv.view.set_read_only(False)
        uv.view.run_command("org_internal_replace", {"start": 0, "end": uv.view.size(), "text": out + "\n"})
        uv.view.set_read_only(True)
        uv.view.run_command("org_fold_all_links")

class OrgShowBacklinksCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        out = BuildBacklinksDisplay(self.view)
        #bl = db.Get().GetBacklinks(self.view)
        self.uv = uview.UniqueView.Get("Backlinks",curview=self.view)
        self.uv.view.set_read_only(False)
        self.uv.view.run_command("org_internal_replace", {"start": 0, "end": self.uv.view.size(), "text": out + "\n"})
        self.uv.view.set_read_only(True)
        self.uv.view.run_command("org_fold_all_links")
        

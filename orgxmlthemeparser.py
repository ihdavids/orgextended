import os
from xml.etree import ElementTree
from collections import OrderedDict

import sublime


STYLE_TEMPLATE = """
 <dict>
    <key>name</key>
    <string>{name}</string>
    <key>scope</key>
    <string>{scope}</string>
    <key>settings</key>
    <dict>
{properties}
    </dict>
</dict>
"""

PROPERTY_TEMPLATE = """
        <key>{key}</key>
        <string>{value}</string>
"""

class XMLThemeParser:
    def __init__(self, themeText):
        self.cs = {}
        self.plist = ElementTree.XML(themeText)
        styles = self.plist.find("./dict/array")
        assert styles
        self.styles = styles
        globalsVals = self.styles[0]
        gv = {}
        k = None
        for p in globalsVals:
            if p.tag == "dict":
                for v in p:
                    if v.tag == "key":
                        k = v.text
                    if v.tag == "string":
                        gv[k] = v.text
        self.cs['globals'] = gv
        rules = []
        for d in self.styles[1:]:
            r = {}
            for p in d:
                if p.tag == "key":
                    k = p.text
                if p.tag == "string":
                    if k == "name" or k == 'scope':
                        r[k] = p.text
                if p.tag == "dict" and k == "settings":
                    dk = None
                    for c in p:
                        if c.tag == "key":
                            k = c.text
                        if c.tag == "string":
                            if k == 'fontStyle':
                                k = "font_style"
                            r[k] = c.text
            rules.append(r)
        self.cs['rules'] = rules


    # def _add_scoped_style(self, name, scope, **kwargs):
    #     properties = "".join(PROPERTY_TEMPLATE.format(key=k, value=v) for k, v in kwargs.items())
    #     new_style = STYLE_TEMPLATE.format(name=name, scope=scope, properties=properties)
    #     self.styles.append(ElementTree.XML(new_style))

    # def write_new_theme(self, name):
    #     full_path = os.path.join(sublime.packages_path(), self.get_theme_path(name))

    #     with file.safe_open(full_path, "wb", buffering=0) as out_f:
    #         out_f.write(STYLES_HEADER.encode("utf-8"))
    #         out_f.write(ElementTree.tostring(self.plist, encoding="utf-8"))
import sublime
import sublime_plugin
import OrgExtended.orgparse.node as node
import OrgExtended.orgutil.util as util


def navigate_up(view):
    (curRow,curCol) = view.curRowCol()
    while(curRow >= 0):
        curRow -= 1
        linePos = view.text_point(curRow,0)
        pos = view.line(linePos)
        lineText = view.substr(pos)
        if node.RE_NODE_HEADER.search(lineText): 
            view.show_at_center(linePos)
            view.sel().clear()
            view.sel().add(linePos)
            break

def navigate_down(view):
    (curRow,curCol) = view.curRowCol()
    max = view.line_count()
    while(curRow < max):
        curRow += 1
        linePos = view.text_point(curRow,curCol)
        pos = view.line(linePos)
        lineText = view.substr(pos)
        if node.RE_NODE_HEADER.search(lineText): 
            view.show_at_center(linePos)
            view.sel().clear()
            view.sel().add(linePos)
            break
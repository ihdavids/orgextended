#-*- coding: utf-8 -*-
#-----------------------------------------------------------------------
# Author: delimitry
#         https://github.com/delimitry/ascii_clock
#-----------------------------------------------------------------------

import os
import time
import math
import datetime

class AsciiCanvas(object):
    """
    ASCII canvas for drawing in console using ASCII chars
    """

    def __init__(self, cols, lines, fill_char=' '):
        """
        Initialize ASCII canvas
        """
        if cols < 1 or cols > 1000 or lines < 1 or lines > 1000:
            raise Exception('Canvas cols/lines must be in range [1..1000]')
        self.cols = cols
        self.lines = lines
        if not fill_char:
            fill_char = ' '
        elif len(fill_char) > 1:
            fill_char = fill_char[0]
        self.fill_char = fill_char
        self.canvas = [[fill_char] * (cols) for _ in range(lines)]

    def clear(self):
        """
        Fill canvas with empty chars
        """
        self.canvas = [[self.fill_char] * (self.cols) for _ in range(self.lines)]

    def print_out(self):
        """
        Print out canvas to console
        """
        print(self.get_canvas_as_str())

    def add_line(self, x0, y0, x1, y1, fill_char='o'):
        """
        Add ASCII line (x0, y0 -> x1, y1) to the canvas, fill line with `fill_char`
        """
        if not fill_char:
            fill_char = 'o'
        elif len(fill_char) > 1:
            fill_char = fill_char[0]
        if x0 > x1:
            # swap A and B
            x1, x0 = x0, x1
            y1, y0 = y0, y1
        # get delta x, y
        dx = x1 - x0
        dy = y1 - y0
        # if a length of line is zero just add point
        if dx == 0 and dy == 0:
            if self.check_coord_in_range(x0, y0):
                self.canvas[y0][x0] = fill_char
            return
        # when dx >= dy use fill by x-axis, and use fill by y-axis otherwise
        if abs(dx) >= abs(dy):
            for x in range(x0, x1 + 1):
                y = y0 if dx == 0 else y0 + int(round((x - x0) * dy / float((dx))))
                if self.check_coord_in_range(x, y):
                    self.canvas[y][x] = fill_char
        else:
            if y0 < y1:
                for y in range(y0, y1 + 1):
                    x = x0 if dy == 0 else x0 + int(round((y - y0) * dx / float((dy))))
                    if self.check_coord_in_range(x, y):
                        self.canvas[y][x] = fill_char
            else:
                for y in range(y1, y0 + 1):
                    x = x0 if dy == 0 else x1 + int(round((y - y1) * dx / float((dy))))
                    if self.check_coord_in_range(x, y):
                        self.canvas[y][x] = fill_char

    def add_text(self, x, y, text):
        """
        Add text to canvas at position (x, y)
        """
        for i, c in enumerate(text):
            if self.check_coord_in_range(x + i, y):
                self.canvas[y][x + i] = c

    def add_rect(self, x, y, w, h, fill_char=' ', outline_char='o'):
        """
        Add rectangle filled with `fill_char` and outline with `outline_char`
        """
        if not fill_char:
            fill_char = ' '
        elif len(fill_char) > 1:
            fill_char = fill_char[0]
        if not outline_char:
            outline_char = 'o'
        elif len(outline_char) > 1:
            outline_char = outline_char[0]
        for px in range(x, x + w):
            for py in range(y, y + h):
                if self.check_coord_in_range(px, py):
                    if px == x or px == x + w - 1 or py == y or py == y + h - 1:
                        self.canvas[py][px] = outline_char
                    else:
                        self.canvas[py][px] = fill_char

    def add_nine_patch_rect(self, x, y, w, h, outline_3x3_chars=None):
        """
        Add nine-patch rectangle
        """
        default_outline_3x3_chars = (
            '.', '-', '.', 
            '|', ' ', '|', 
            '`', '-', "'"
        )
        if not outline_3x3_chars:
            outline_3x3_chars = default_outline_3x3_chars
        # filter chars
        filtered_outline_3x3_chars = []
        for index, char in enumerate(outline_3x3_chars[0:9]):
            if not char:
                char = default_outline_3x3_chars[index]
            elif len(char) > 1:
                char = char[0]
            filtered_outline_3x3_chars.append(char)
        for px in range(x, x + w):
            for py in range(y, y + h):
                if self.check_coord_in_range(px, py):
                    if px == x and py == y:
                        self.canvas[py][px] = filtered_outline_3x3_chars[0]
                    elif px == x and y < py < y + h - 1:
                        self.canvas[py][px] = filtered_outline_3x3_chars[3]
                    elif px == x and py == y + h - 1:
                        self.canvas[py][px] = filtered_outline_3x3_chars[6]
                    elif x < px < x + w - 1 and py == y:
                        self.canvas[py][px] = filtered_outline_3x3_chars[1]
                    elif x < px < x + w - 1 and py == y + h - 1:
                        self.canvas[py][px] = filtered_outline_3x3_chars[7]
                    elif px == x + w - 1 and py == y:
                        self.canvas[py][px] = filtered_outline_3x3_chars[2]
                    elif px == x + w - 1 and y < py < y + h - 1:
                        self.canvas[py][px] = filtered_outline_3x3_chars[5]
                    elif px == x + w - 1 and py == y + h - 1:
                        self.canvas[py][px] = filtered_outline_3x3_chars[8]
                    else:
                        self.canvas[py][px] = filtered_outline_3x3_chars[4]

    def check_coord_in_range(self, x, y):
        """
        Check that coordinate (x, y) is in range, to prevent out of range error
        """
        return 0 <= x < self.cols and 0 <= y < self.lines

    def get_canvas_as_str(self):
        """
        Return canvas as a string
        """
        return '\n'.join([''.join(col) for col in self.canvas])

    def __str__(self):
        """
        Return canvas as a string
        """
        return self.get_canvas_as_str()

    def get_row(self, i):
    	rows = [''.join(col) for col in self.canvas]
    	if(i > 0 and i < len(rows)):
    		return rows[i]
    	return ''

x_scale_ratio = 1.75


def draw_second_hand(ascii_canvas, seconds, length, fill_char):
    """
    Draw second hand
    """
    x0 = int(math.ceil(ascii_canvas.cols / 2.0))
    y0 = int(math.ceil(ascii_canvas.lines / 2.0))
    x1 = x0 + int(math.cos((seconds + 45) * 6 * math.pi / 180) * length * x_scale_ratio)
    y1 = y0 + int(math.sin((seconds + 45) * 6 * math.pi / 180) * length)
    ascii_canvas.add_line(int(x0), int(y0), int(x1), int(y1), fill_char=fill_char)


def draw_minute_hand(ascii_canvas, minutes, length, fill_char):
    """
    Draw minute hand
    """
    x0 = int(math.ceil(ascii_canvas.cols / 2.0))
    y0 = int(math.ceil(ascii_canvas.lines / 2.0))
    x1 = x0 + int(math.cos((minutes + 45) * 6 * math.pi / 180) * length * x_scale_ratio)
    y1 = y0 + int(math.sin((minutes + 45) * 6 * math.pi / 180) * length)
    ascii_canvas.add_line(int(x0), int(y0), int(x1), int(y1), fill_char=fill_char)


def draw_hour_hand(ascii_canvas, hours, minutes, length, fill_char):
    """
    Draw hour hand
    """
    x0 = int(math.ceil(ascii_canvas.cols / 2.0))
    y0 = int(math.ceil(ascii_canvas.lines / 2.0))
    total_hours = hours + minutes / 60.0
    x1 = x0 + int(math.cos((total_hours + 45) * 30 * math.pi / 180) * length * x_scale_ratio)
    y1 = y0 + int(math.sin((total_hours + 45) * 30 * math.pi / 180) * length)
    ascii_canvas.add_line(int(x0), int(y0), int(x1), int(y1), fill_char=fill_char)


def draw_clock_face(ascii_canvas, radius, mark_char):
    """
    Draw clock face with hour and minute marks
    """
    x0 = ascii_canvas.cols // 2
    y0 = ascii_canvas.lines // 2
    # draw marks first
    for mark in range(1, 12 * 5 + 1):
        x1 = x0 + int(math.cos((mark + 45) * 6 * math.pi / 180) * radius * x_scale_ratio)
        y1 = y0 + int(math.sin((mark + 45) * 6 * math.pi / 180) * radius)
        if mark % 5 != 0:
            ascii_canvas.add_text(x1, y1, mark_char)
    # start from 1 because at 0 index - 12 hour
    for mark in range(1, 12 + 1):
        x1 = x0 + int(math.cos((mark + 45) * 30 * math.pi / 180) * radius * x_scale_ratio)
        y1 = y0 + int(math.sin((mark + 45) * 30 * math.pi / 180) * radius)
        ascii_canvas.add_text(x1, y1, '%s' % mark)


def draw_clock(now, cols, lines):
    """
    Draw clock
    """
    if cols < 25 or lines < 25:
        print('Too little columns/lines for print out the clock!')
        return None
    # Yes we want just plain date not
    # datetime here to match.
    if type(now) == datetime.date:
        return None
    # prepare chars
    single_line_border_chars = ('.', '-', '.', '|', ' ', '|', '`', '-', "'")
    second_hand_char = '.'
    minute_hand_char = 'o'
    hour_hand_char = 'O'
    mark_char = '`'
    if os.name == 'nt':
        single_line_border_chars = ('.', '-', '.', '|', ' ', '|', '`', '-', "'")  # ('\xDA', '\xC4', '\xBF', '\xB3', '\x20', '\xB3', '\xC0', '\xC4', '\xD9')
        second_hand_char = '.'  # '\xFA'
        minute_hand_char = 'o'  # '\xF9'
        hour_hand_char = 'O'  # 'o'
        mark_char = '`'  # '\xF9'
    # create ascii canvas for clock and eval vars
    ascii_canvas = AsciiCanvas(cols, lines)
    center_x = int(math.ceil(cols / 2.0))
    center_y = int(math.ceil(lines / 2.0))
    radius = center_y - 5
    second_hand_length = int(radius / 1.17)
    minute_hand_length = int(radius / 1.25)
    hour_hand_length = int(radius / 1.95)
    # add clock region and clock face
    #ascii_canvas.add_rect(5, 3, int(math.floor(cols / 2.0)) * 2 - 9, int(math.floor(lines / 2.0)) * 2 - 5)
    draw_clock_face(ascii_canvas, radius, mark_char)
    #now = datetime.datetime.now()
    # add regions with weekday and day if possible
    if center_x > 25:
        left_pos = int(radius * x_scale_ratio) / 2 - 4
        ascii_canvas.add_nine_patch_rect(int(center_x + left_pos), int(center_y - 1), 5, 3, single_line_border_chars)
        ascii_canvas.add_text(int(center_x + left_pos + 1), int(center_y), now.strftime('%a'))
        ascii_canvas.add_nine_patch_rect(int(center_x + left_pos + 5), int(center_y - 1), 4, 3, single_line_border_chars)
        ascii_canvas.add_text(int(center_x + left_pos + 1 + 5), int(center_y), now.strftime('%d'))
    # add clock hands
    draw_second_hand(ascii_canvas, now.second, second_hand_length, fill_char=second_hand_char)
    draw_minute_hand(ascii_canvas, now.minute, minute_hand_length, fill_char=minute_hand_char)
    draw_hour_hand(ascii_canvas, now.hour, now.minute, hour_hand_length, fill_char=hour_hand_char)
    # print out canvas
    return ascii_canvas
    #ascii_canvas.print_out()


# def main():
#     lines = 40
#     cols = int(lines * x_scale_ratio)
#     # set console window size and screen buffer size
#     if os.name == 'nt':
#         os.system('mode con: cols=%s lines=%s' % (cols + 1, lines + 1))
#     while True:
#        os.system('cls' if os.name == 'nt' else 'clear')
#        draw_clock(cols, lines)
#        time.sleep(0.2)


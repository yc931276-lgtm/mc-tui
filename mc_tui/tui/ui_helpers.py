"""UI Helper functions and widgets for Curses TUI."""
from __future__ import annotations

import curses
import unicodedata
from typing import List, Optional, Tuple

from mc_tui.i18n import t
from mc_tui.theme import Colors, apply_theme


def init_colors(config=None) -> None:
    """Apply the configured color theme (kept as the UI helper entry point)."""
    apply_theme(config)


def char_width(ch: str) -> int:
    """Return visual display column width of a single character."""
    if not ch:
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


def str_width(s: str) -> int:
    """Return visual display column width of string, handling wide CJK characters."""
    return sum(char_width(ch) for ch in s)


def truncate_str(s: str, max_width: int) -> str:
    """Truncate string so its visual width does not exceed max_width."""
    cur_w = 0
    res: List[str] = []
    for ch in s:
        w = char_width(ch)
        if cur_w + w > max_width:
            break
        res.append(ch)
        cur_w += w
    return "".join(res)


def pad_str(s: str, width: int, align: str = "left") -> str:
    """Pad string with spaces taking visual display width into account."""
    w = str_width(s)
    if w >= width:
        return truncate_str(s, width)
    pad = " " * (width - w)
    if align == "right":
        return pad + s
    elif align == "center":
        left_len = (width - w) // 2
        right_len = width - w - left_len
        return (" " * left_len) + s + (" " * right_len)
    return s + pad


def safe_addstr(win: curses.window, y: int, x: int, text: str, attr: int = 0) -> None:
    """Safely write string to window without crashing on boundary overflow."""
    max_y, max_x = win.getmaxyx()
    if y < 0 or y >= max_y or x < 0 or x >= max_x:
        return
    available = max_x - x
    if available <= 0:
        return
    to_write = truncate_str(text, available)
    try:
        win.addstr(y, x, to_write, attr)
    except curses.error:
        pass


def draw_box(win: curses.window, y: int, x: int, h: int, w: int, title: str = "", attr: int = 0) -> None:
    """Draw a box frame with an optional title."""
    max_y, max_x = win.getmaxyx()
    if y >= max_y or x >= max_x or h <= 1 or w <= 1:
        return

    h = min(h, max_y - y)
    w = min(w, max_x - x)

    # Corners and lines
    try:
        win.attron(attr)
        # Top line
        safe_addstr(win, y, x, "┌" + "─" * (w - 2) + "┐", attr)
        # Sides
        for row in range(y + 1, y + h - 1):
            safe_addstr(win, row, x, "│", attr)
            safe_addstr(win, row, x + w - 1, "│", attr)
        # Bottom line
        safe_addstr(win, y + h - 1, x, "└" + "─" * (w - 2) + "┘", attr)

        if title:
            title_text = f" {title} "
            if str_width(title_text) < w - 4:
                safe_addstr(win, y, x + 2, title_text, attr | curses.A_BOLD)
    finally:
        win.attroff(attr)


def prompt_input(
    stdscr: curses.window, prompt: str, initial_text: str = "", max_len: int = 60
) -> Optional[str]:
    """Display an input modal and return user string, or None if cancelled."""
    max_y, max_x = stdscr.getmaxyx()
    pw = str_width(prompt)
    box_w = min(max(pw + 10, max_len + 8), max_x - 4)
    box_h = 7
    start_y = max(1, (max_y - box_h) // 2)
    start_x = max(1, (max_x - box_w) // 2)

    buf = list(initial_text)
    cursor_idx = len(buf)

    curses.curs_set(1)

    while True:
        # Draw modal box
        box_win = curses.newwin(box_h, box_w, start_y, start_x)
        box_win.bkgd(" ", curses.color_pair(Colors.NORMAL))
        box_win.box()
        safe_addstr(box_win, 0, 2, f" {prompt} ", curses.color_pair(Colors.ACCENT) | curses.A_BOLD)
        safe_addstr(box_win, box_h - 2, 2, t("confirm_cancel_hint"), curses.color_pair(Colors.MUTED))

        # Input field
        visible_str = "".join(buf)
        field_w = box_w - 6
        disp_str = visible_str[-field_w:] if len(visible_str) > field_w else visible_str
        safe_addstr(box_win, 2, 3, "[" + pad_str(disp_str, field_w) + "]", curses.color_pair(Colors.NORMAL))

        # Position cursor
        rel_pos = min(cursor_idx, field_w)
        box_win.move(2, 4 + rel_pos)
        box_win.refresh()

        ch = stdscr.getch()

        if ch in (27,):  # ESC
            curses.curs_set(0)
            return None
        elif ch in (curses.KEY_ENTER, 10, 13):
            curses.curs_set(0)
            return "".join(buf)
        elif ch == 21:  # Ctrl+U: clear the input line
            buf.clear()
            cursor_idx = 0
        elif ch in (curses.KEY_BACKSPACE, 127, 8):
            if cursor_idx > 0:
                buf.pop(cursor_idx - 1)
                cursor_idx -= 1
        elif ch in (curses.KEY_DC,):  # Delete key
            if cursor_idx < len(buf):
                buf.pop(cursor_idx)
        elif ch == curses.KEY_LEFT:
            if cursor_idx > 0:
                cursor_idx -= 1
        elif ch == curses.KEY_RIGHT:
            if cursor_idx < len(buf):
                cursor_idx += 1
        elif ch >= 32 and ch <= 126:
            if len(buf) < max_len:
                buf.insert(cursor_idx, chr(ch))
                cursor_idx += 1


def show_message_modal(stdscr: curses.window, title: str, lines: List[str]) -> None:
    """Show a scrollable message or alert dialog."""
    max_y, max_x = stdscr.getmaxyx()
    max_content_w = max(str_width(l) for l in lines + [title]) if (lines or title) else 30
    box_w = min(max_x - 6, max_content_w + 8)
    box_w = max(box_w, 40)
    box_h = min(max_y - 4, len(lines) + 6)
    start_y = max(1, (max_y - box_h) // 2)
    start_x = max(1, (max_x - box_w) // 2)

    offset = 0
    content_h = box_h - 4

    curses.curs_set(0)

    while True:
        win = curses.newwin(box_h, box_w, start_y, start_x)
        win.box()
        safe_addstr(win, 0, 2, f" {title} ", curses.color_pair(Colors.ACCENT) | curses.A_BOLD)
        safe_addstr(win, box_h - 1, 2, " [Esc / Enter] Close  [↑/↓] Scroll ", curses.color_pair(Colors.MUTED))

        for idx in range(content_h):
            line_idx = offset + idx
            if line_idx < len(lines):
                safe_addstr(win, 2 + idx, 3, lines[line_idx], curses.color_pair(Colors.NORMAL))

        win.refresh()

        ch = stdscr.getch()
        if ch in (curses.KEY_UP, ord("k")):
            if offset > 0:
                offset -= 1
        elif ch in (curses.KEY_DOWN, ord("j")):
            if offset + content_h < len(lines):
                offset += 1
        elif ch in (curses.KEY_ENTER, 10, 13, 27, ord("q"), ord("Q"), ord(" ")):
            break

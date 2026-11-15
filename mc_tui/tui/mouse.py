"""Pure hit-testing helpers for mouse support in the TUI.

Coordinates are screen columns/rows as returned by ``curses.getmouse()``.
These helpers mirror the layout calculations in ``views.py`` so mouse clicks
select the same rows that are drawn on screen.
"""
from __future__ import annotations

from typing import Optional, Sequence

from mc_tui.tui.ui_helpers import str_width


def tab_index_at(x: int, tabs: Sequence[str]) -> Optional[int]:
    """Return the tab index at column ``x`` on the header tab row."""
    tab_x = 2
    for index, title in enumerate(tabs):
        width = str_width(title) + 4  # " [title] " / "  title  "
        if tab_x <= x < tab_x + width:
            return index
        tab_x += width + 1
    return None


def version_index_at(
    y: int,
    x: int,
    max_x: int,
    top_y: int,
    bottom_y: int,
    has_filter: bool,
    total: int,
    selected: int,
) -> Optional[int]:
    """Map a click in the Versions tab's left list to a version index."""
    height = bottom_y - top_y
    if height < 4 or max_x < 30:
        return None

    split_x = int(max_x * 0.58)
    if x >= split_x:
        return None

    content_y_start = top_y + (2 if has_filter else 1)
    visible_rows = height - (3 if has_filter else 2)
    if not (content_y_start <= y < content_y_start + visible_rows):
        return None

    scroll_start = selected - visible_rows + 1 if selected >= visible_rows else 0
    index = scroll_start + (y - content_y_start)
    return index if 0 <= index < total else None


def settings_index_at(
    y: int,
    top_y: int,
    bottom_y: int,
    total: int,
    selected: int,
) -> Optional[int]:
    """Map a click in the Settings tab to a settings-field index."""
    if total <= 0:
        return None

    start_y = top_y + 2
    per_page = max(1, ((bottom_y - 2) - start_y) // 2)
    offset = 0
    if selected >= per_page:
        offset = min(selected - per_page + 1, max(0, total - per_page))

    if y < start_y:
        return None
    row = (y - start_y) // 2
    if row >= per_page:
        return None

    index = offset + row
    return index if index < total else None


def download_index_at(
    y: int,
    x: int,
    max_x: int,
    top_y: int,
    bottom_y: int,
    total: int,
    selected: int,
) -> Optional[int]:
    """Map a click in the Download tab's left list to a remote-version index."""
    height = bottom_y - top_y
    if height < 4 or max_x < 30:
        return None

    split_x = int(max_x * 0.58)
    if x >= split_x:
        return None

    content_y_start = top_y + 2
    visible_rows = height - 3
    if not (content_y_start <= y < content_y_start + visible_rows):
        return None

    scroll_start = selected - visible_rows + 1 if selected >= visible_rows else 0
    index = scroll_start + (y - content_y_start)
    return index if 0 <= index < total else None


def dir_index_at(
    y: int,
    top_y: int,
    bottom_y: int,
    total: int,
) -> Optional[int]:
    """Map a click in the Game Dir tab's candidate list to an index."""
    start_y = top_y + 6
    index = y - start_y
    if 0 <= index < total and y < bottom_y - 2:
        return index
    return None


def button_hit(x: int, y: int, row_y: int, start_x: int, label: str) -> bool:
    """Return True when ``(x, y)`` is inside a single-line button label."""
    return y == row_y and start_x <= x < start_x + str_width(label)

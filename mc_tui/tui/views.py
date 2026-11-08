"""View renderers for MC-TUI screens."""
from __future__ import annotations

import curses
from pathlib import Path
from typing import Any, List, Optional, Tuple

from mc_tui.config import Config
from mc_tui.java_detector import find_best_java
from mc_tui.launcher import Launcher
from mc_tui.tui.ui_helpers import Colors, draw_box, safe_addstr
from mc_tui.version_parser import VersionMeta


TABS = ["1: Versions", "2: Settings", "3: Console Logs", "4: Game Dir"]


def render_header(
    win: curses.window,
    active_tab: int,
    config: Config,
    launcher: Launcher,
) -> None:
    """Render top header bar with branding, tabs, and status."""
    max_y, max_x = win.getmaxyx()

    # Title row
    title = " MC-TUI: Local Minecraft Launcher "
    safe_addstr(win, 0, 0, title.center(max_x), curses.color_pair(Colors.HEADER) | curses.A_BOLD)

    # Tabs row
    tab_x = 2
    for i, tab_title in enumerate(TABS):
        if i == active_tab:
            attr = curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD
            tab_str = f" [{tab_title}] "
        else:
            attr = curses.color_pair(Colors.ACCENT)
            tab_str = f"  {tab_title}  "

        safe_addstr(win, 1, tab_x, tab_str, attr)
        tab_x += len(tab_str) + 1

    # Status indicators on right side of row 1
    status_text = ""
    status_attr = curses.color_pair(Colors.NORMAL)
    if launcher.current_process:
        if launcher.current_process.is_running:
            status_text = "● Minecraft Running"
            status_attr = curses.color_pair(Colors.SUCCESS) | curses.A_BOLD
        else:
            code = launcher.current_process.exit_code
            status_text = f"○ Stopped ({code})"
            status_attr = curses.color_pair(Colors.MUTED)
    else:
        status_text = "○ Idle"
        status_attr = curses.color_pair(Colors.MUTED)

    status_x = max(tab_x + 2, max_x - len(status_text) - 4)
    safe_addstr(win, 1, status_x, status_text, status_attr)

    # Info row 2: Current directory, user, java
    game_dir_str = str(config.game_dir)
    if len(game_dir_str) > 35:
        game_dir_str = "..." + game_dir_str[-32:]

    java_info = find_best_java(configured_path=config.java_path)
    java_label = f"Java {java_info.major_version}" if java_info else "Java ??"

    info_str = f"Dir: {game_dir_str}  │  User: {config.username}  │  {java_label}"
    safe_addstr(win, 2, 2, info_str, curses.color_pair(Colors.MUTED))
    win.hline(3, 0, curses.ACS_HLINE, max_x)


def render_footer(win: curses.window, active_tab: int) -> None:
    """Render footer shortcuts."""
    max_y, max_x = win.getmaxyx()
    y = max_y - 1

    shortcuts = {
        0: "[1-4] Tabs  [↑/↓] Select  [Enter] Launch  [p] Preview Cmd  [/] Filter  [r] Refresh  [q] Quit",
        1: "[1-4] Tabs  [↑/↓] Field   [Enter] Edit    [s] Save Config  [r] Reset Defaults  [q] Quit",
        2: "[1-4] Tabs  [↑/↓/PgUp/PgDn] Scroll  [Space] Auto-scroll  [k] Kill MC  [c] Clear  [q] Quit",
        3: "[1-4] Tabs  [↑/↓] Choose Common Dir  [Enter] Select  [e] Custom Path  [q] Quit",
    }

    text = shortcuts.get(active_tab, "[1-4] Switch Tabs  [q] Quit")
    safe_addstr(win, y, 0, f" {text} ".ljust(max_x), curses.color_pair(Colors.HEADER))


def render_versions_view(
    win: curses.window,
    versions: List[VersionMeta],
    selected_idx: int,
    filter_text: str,
    config: Config,
    top_y: int,
    bottom_y: int,
) -> None:
    """Render version selector view."""
    max_y, max_x = win.getmaxyx()
    h = bottom_y - top_y
    if h < 4 or max_x < 30:
        return

    # Split screen: Left = List (60%), Right = Details (40%)
    split_x = int(max_x * 0.58)

    # 1. Left Pane: Versions list
    box_w = split_x
    draw_box(win, top_y, 0, h, box_w, f"Installed Versions ({len(versions)})", curses.color_pair(Colors.ACCENT))

    if filter_text:
        safe_addstr(win, top_y + 1, 2, f"Filter: {filter_text}", curses.color_pair(Colors.WARNING))
        content_y_start = top_y + 2
        visible_rows = h - 3
    else:
        content_y_start = top_y + 1
        visible_rows = h - 2

    if not versions:
        safe_addstr(win, content_y_start + 1, 2, "No Minecraft versions found in:", curses.color_pair(Colors.MUTED))
        safe_addstr(win, content_y_start + 2, 2, str(config.game_dir), curses.color_pair(Colors.WARNING))
        safe_addstr(win, content_y_start + 4, 2, "Press [4] to switch or select Game Dir.", curses.color_pair(Colors.ACCENT))
        safe_addstr(win, content_y_start + 5, 2, "Press [r] to refresh.", curses.color_pair(Colors.MUTED))
    else:
        # Calculate scroll window
        scroll_start = 0
        if selected_idx >= visible_rows:
            scroll_start = selected_idx - visible_rows + 1

        for i in range(visible_rows):
            v_idx = scroll_start + i
            if v_idx >= len(versions):
                break

            v = versions[v_idx]
            is_selected = (v_idx == selected_idx)
            row_y = content_y_start + i

            # Format version row: [Badge] Version ID (Release date)
            badge = f"[{v.display_type}]"
            vid_w = box_w - len(badge) - 15
            vid_disp = v.id[:vid_w] if len(v.id) > vid_w else v.id

            line_str = f" {badge:<9} {vid_disp}"
            if v.release_time:
                date_str = f"({v.release_time})"
                line_str = f"{line_str:<{box_w - len(date_str) - 3}} {date_str}"

            if is_selected:
                safe_addstr(win, row_y, 1, line_str.ljust(box_w - 2), curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD)
            else:
                attr = curses.color_pair(Colors.NORMAL)
                if v.display_type in ("Fabric", "Forge", "Quilt"):
                    attr = curses.color_pair(Colors.ACCENT)
                safe_addstr(win, row_y, 1, line_str.ljust(box_w - 2), attr)

    # 2. Right Pane: Version Details
    det_w = max_x - split_x
    draw_box(win, top_y, split_x, h, det_w, "Version Details", curses.color_pair(Colors.ACCENT))

    if versions and 0 <= selected_idx < len(versions):
        cur = versions[selected_idx]
        dy = top_y + 2
        dx = split_x + 2

        safe_addstr(win, dy, dx, "Version ID:", curses.color_pair(Colors.MUTED))
        safe_addstr(win, dy + 1, dx + 2, cur.id, curses.color_pair(Colors.NORMAL) | curses.A_BOLD)

        safe_addstr(win, dy + 3, dx, "Type:", curses.color_pair(Colors.MUTED))
        safe_addstr(win, dy + 3, dx + 12, cur.display_type, curses.color_pair(Colors.ACCENT))

        safe_addstr(win, dy + 4, dx, "Release Date:", curses.color_pair(Colors.MUTED))
        safe_addstr(win, dy + 4, dx + 15, cur.release_time or "Unknown", curses.color_pair(Colors.NORMAL))

        java_req = f"Java {cur.java_major_version}+" if cur.java_major_version else "Any (Default)"
        safe_addstr(win, dy + 5, dx, "Java Version:", curses.color_pair(Colors.MUTED))
        safe_addstr(win, dy + 5, dx + 15, java_req, curses.color_pair(Colors.NORMAL))

        if cur.inherits_from:
            safe_addstr(win, dy + 6, dx, "Inherits From:", curses.color_pair(Colors.MUTED))
            safe_addstr(win, dy + 6, dx + 16, cur.inherits_from, curses.color_pair(Colors.NORMAL))

        safe_addstr(win, dy + 8, dx, "Main Class:", curses.color_pair(Colors.MUTED))
        mc_name = cur.main_class or "(Default Launcher Main)"
        safe_addstr(win, dy + 9, dx + 2, mc_name[:det_w - 6], curses.color_pair(Colors.MUTED))

        # Launch quick button
        launch_btn = " ▶ LAUNCH VERSION (Press Enter) "
        safe_addstr(win, top_y + h - 3, dx + 2, launch_btn, curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD)
    else:
        safe_addstr(win, top_y + 2, split_x + 3, "Select a version to view info.", curses.color_pair(Colors.MUTED))


def render_settings_view(
    win: curses.window,
    config: Config,
    selected_idx: int,
    top_y: int,
    bottom_y: int,
) -> None:
    """Render interactive settings form."""
    max_y, max_x = win.getmaxyx()
    h = bottom_y - top_y

    draw_box(win, top_y, 0, h, max_x, "Launcher Settings & Profile", curses.color_pair(Colors.ACCENT))

    fields = [
        ("Player Username", config.username, "Offline player nickname and UUID generator"),
        ("Minimum RAM (-Xms)", config.min_ram, "Initial heap allocation (e.g. 512M, 1G)"),
        ("Maximum RAM (-Xmx)", config.max_ram, "Maximum heap allocation (e.g. 2G, 4G, 8G)"),
        ("Java Executable Path", config.java_path or "[Auto-Detect Best Java]", "Path to java binary or auto-detect"),
        ("Game Directory", str(config.game_dir), "Root directory for versions, libraries, and assets"),
        ("Custom JVM Flags", config.custom_jvm_args or "(none)", "Extra arguments passed to Java JVM"),
        ("Window Width", str(config.get("window_width", 854)), "Default initial Minecraft window width"),
        ("Window Height", str(config.get("window_height", 480)), "Default initial Minecraft window height"),
    ]

    start_y = top_y + 2
    for i, (label, val, desc) in enumerate(fields):
        row_y = start_y + (i * 2)
        if row_y >= bottom_y - 2:
            break

        is_sel = (i == selected_idx)
        cursor_prefix = "► " if is_sel else "  "

        label_col = 4
        val_col = 32

        if is_sel:
            safe_addstr(win, row_y, label_col - 2, cursor_prefix + f"{label}:", curses.color_pair(Colors.ACCENT) | curses.A_BOLD)
            val_disp = f" {val} "
            safe_addstr(win, row_y, val_col, val_disp.ljust(max_x - val_col - 4), curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD)
            safe_addstr(win, row_y + 1, val_col, f"↳ {desc}", curses.color_pair(Colors.MUTED))
        else:
            safe_addstr(win, row_y, label_col, f"{label}:", curses.color_pair(Colors.NORMAL))
            safe_addstr(win, row_y, val_col, str(val)[:max_x - val_col - 4], curses.color_pair(Colors.NORMAL))


def render_console_view(
    win: curses.window,
    log_buffer: List[str],
    is_running: bool,
    exit_code: Optional[int],
    auto_scroll: bool,
    scroll_offset: int,
    top_y: int,
    bottom_y: int,
) -> None:
    """Render real-time Minecraft process output logs."""
    max_y, max_x = win.getmaxyx()
    h = bottom_y - top_y

    status_str = "RUNNING" if is_running else f"STOPPED (exit: {exit_code})"
    scroll_str = "Auto-scroll: ON" if auto_scroll else f"Scroll: {scroll_offset}"
    title = f"Minecraft Console Output [{status_str}]  ({scroll_str})"

    draw_box(win, top_y, 0, h, max_x, title, curses.color_pair(Colors.ACCENT))

    content_h = h - 2
    total_lines = len(log_buffer)

    if total_lines == 0:
        safe_addstr(win, top_y + 2, 3, "No logs yet. Launch a version to see console logs here.", curses.color_pair(Colors.MUTED))
        return

    # Calculate starting line
    if auto_scroll:
        start_line = max(0, total_lines - content_h)
    else:
        start_line = max(0, min(scroll_offset, max(0, total_lines - content_h)))

    for i in range(content_h):
        line_idx = start_line + i
        if line_idx >= total_lines:
            break

        line = log_buffer[line_idx]
        attr = curses.color_pair(Colors.NORMAL)
        if "ERROR" in line or "Exception" in line or "FATAL" in line:
            attr = curses.color_pair(Colors.DANGER) | curses.A_BOLD
        elif "WARN" in line:
            attr = curses.color_pair(Colors.WARNING)
        elif "INFO" in line:
            attr = curses.color_pair(Colors.NORMAL)

        safe_addstr(win, top_y + 1 + i, 2, line[:max_x - 4], attr)


def render_dir_picker_view(
    win: curses.window,
    current_dir: Path,
    candidates: List[Tuple[str, Path, int]],
    selected_idx: int,
    top_y: int,
    bottom_y: int,
) -> None:
    """Render game directory selector."""
    max_y, max_x = win.getmaxyx()
    h = bottom_y - top_y

    draw_box(win, top_y, 0, h, max_x, "Select Game Directory (.minecraft)", curses.color_pair(Colors.ACCENT))

    safe_addstr(win, top_y + 2, 3, f"Current Game Directory: {current_dir}", curses.color_pair(Colors.NORMAL) | curses.A_BOLD)
    safe_addstr(win, top_y + 4, 3, "Discovered or Common Directories:", curses.color_pair(Colors.ACCENT))

    start_y = top_y + 6
    for i, (name, path, v_count) in enumerate(candidates):
        row_y = start_y + i
        if row_y >= bottom_y - 2:
            break

        is_sel = (i == selected_idx)
        is_cur = (str(path.resolve()) == str(current_dir.resolve()))

        cur_marker = " [CURRENT] " if is_cur else ""
        count_str = f"({v_count} versions found)" if v_count > 0 else "(0 versions)"

        line = f" {name:<22} {str(path):<40} {count_str:<18}{cur_marker}"

        if is_sel:
            safe_addstr(win, row_y, 2, line.ljust(max_x - 4), curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD)
        else:
            attr = curses.color_pair(Colors.SUCCESS if is_cur else Colors.NORMAL)
            safe_addstr(win, row_y, 2, line.ljust(max_x - 4), attr)

    safe_addstr(win, bottom_y - 3, 3, "Press [e] to enter a custom path directly, or [Enter] to choose highlighted.", curses.color_pair(Colors.MUTED))

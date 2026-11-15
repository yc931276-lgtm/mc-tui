"""View renderers for MC-TUI screens with internationalization."""
from __future__ import annotations

import curses
import platform
import socket
import sys
from pathlib import Path
from typing import Any, List, Optional, Set, Tuple

from mc_tui.config import Config
from mc_tui.downloader import DownloadProgress, RemoteVersion
from mc_tui.i18n import t
from mc_tui.java_detector import find_best_java
from mc_tui.jre_manager import JRE_VERSIONS, installed_majors
from mc_tui.launcher import Launcher
from mc_tui.theme import (
    accent_label,
    get_accent_choice,
    get_header_style,
    get_selection_style,
    get_theme_name,
    header_style_label,
    selection_style_label,
    theme_label,
)
from mc_tui.tui.ui_helpers import (
    Colors,
    draw_box,
    pad_str,
    safe_addstr,
    str_width,
    truncate_str,
)
from mc_tui.version_parser import VersionMeta


def get_tabs() -> List[str]:
    return [
        t("tab_versions"),
        t("tab_settings"),
        t("tab_console"),
        t("tab_dir"),
        t("tab_download"),
        t("tab_about"),
    ]


def render_header(
    win: curses.window,
    active_tab: int,
    config: Config,
    launcher: Launcher,
) -> None:
    """Render top header bar with branding, tabs, and status."""
    max_y, max_x = win.getmaxyx()
    tabs = get_tabs()

    # Title row
    title = t("title")
    safe_addstr(win, 0, 0, pad_str(title, max_x, align="center"), curses.color_pair(Colors.HEADER) | curses.A_BOLD)

    # Tabs row
    tab_x = 2
    for i, tab_title in enumerate(tabs):
        if i == active_tab:
            attr = curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD
            tab_str = f" [{tab_title}] "
        else:
            attr = curses.color_pair(Colors.ACCENT)
            tab_str = f"  {tab_title}  "

        safe_addstr(win, 1, tab_x, tab_str, attr)
        tab_x += str_width(tab_str) + 1

    # Status indicators on right side of row 1
    if launcher.current_process:
        if launcher.current_process.is_running:
            status_text = t("status_running")
            status_attr = curses.color_pair(Colors.SUCCESS) | curses.A_BOLD
        else:
            code = launcher.current_process.exit_code
            status_text = t("status_stopped", code=code)
            status_attr = curses.color_pair(Colors.MUTED)
    else:
        status_text = t("status_idle")
        status_attr = curses.color_pair(Colors.MUTED)

    status_x = max(tab_x + 2, max_x - str_width(status_text) - 4)
    safe_addstr(win, 1, status_x, status_text, status_attr)

    # Info row 2: Current directory, user, java
    game_dir_str = str(config.game_dir)
    if str_width(game_dir_str) > 35:
        game_dir_str = "..." + game_dir_str[-32:]

    java_info = find_best_java(configured_path=config.java_path)
    java_label = f"Java {java_info.major_version}" if java_info else "Java ??"

    info_str = t("info_bar", dir=game_dir_str, user=config.username, java=java_label)
    safe_addstr(win, 2, 2, info_str, curses.color_pair(Colors.MUTED))
    win.hline(3, 0, curses.ACS_HLINE, max_x)


def render_footer(win: curses.window, active_tab: int) -> None:
    """Render footer shortcuts."""
    max_y, max_x = win.getmaxyx()
    y = max_y - 1

    shortcuts = {
        0: t("footer_0"),
        1: t("footer_1"),
        2: t("footer_2"),
        3: t("footer_3"),
        4: t("footer_4"),
        5: t("footer_5"),
    }

    text = shortcuts.get(active_tab, t("footer_default"))
    safe_addstr(win, y, 0, pad_str(f" {text} ", max_x), curses.color_pair(Colors.HEADER))


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

    split_x = int(max_x * 0.58)

    # 1. Left Pane: Versions list
    box_w = split_x
    draw_box(win, top_y, 0, h, box_w, t("box_installed_versions", count=len(versions)), curses.color_pair(Colors.ACCENT))

    if filter_text:
        safe_addstr(win, top_y + 1, 2, t("filter_prefix", filter=filter_text), curses.color_pair(Colors.WARNING))
        content_y_start = top_y + 2
        visible_rows = h - 3
    else:
        content_y_start = top_y + 1
        visible_rows = h - 2

    if not versions:
        safe_addstr(win, content_y_start + 1, 2, t("no_versions_found"), curses.color_pair(Colors.MUTED))
        safe_addstr(win, content_y_start + 2, 2, str(config.game_dir), curses.color_pair(Colors.WARNING))
        safe_addstr(win, content_y_start + 4, 2, t("press_d_to_download"), curses.color_pair(Colors.SUCCESS) | curses.A_BOLD)
        safe_addstr(win, content_y_start + 5, 2, t("press_4_to_switch_dir"), curses.color_pair(Colors.ACCENT))
        safe_addstr(win, content_y_start + 6, 2, t("press_r_to_refresh"), curses.color_pair(Colors.MUTED))
    else:
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

            badge = f"[{v.display_type}]"
            vid_w = max(10, box_w - str_width(badge) - 16)
            vid_disp = truncate_str(v.id, vid_w)

            line_str = f" {badge} {vid_disp}"
            date_str = f"({v.release_time})" if v.release_time else ""
            if date_str:
                remaining_w = box_w - 2 - str_width(line_str) - str_width(date_str)
                if remaining_w > 0:
                    line_str = line_str + (" " * remaining_w) + date_str
            line_str = pad_str(line_str, box_w - 2)

            if is_selected:
                safe_addstr(win, row_y, 1, line_str, curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD)
            else:
                attr = curses.color_pair(Colors.NORMAL)
                if v.display_type in ("Fabric", "Forge", "Quilt"):
                    attr = curses.color_pair(Colors.ACCENT)
                safe_addstr(win, row_y, 1, line_str, attr)

    # 2. Right Pane: Version Details
    det_w = max_x - split_x
    draw_box(win, top_y, split_x, h, det_w, t("box_version_details"), curses.color_pair(Colors.ACCENT))

    if versions and 0 <= selected_idx < len(versions):
        cur = versions[selected_idx]
        dy = top_y + 2
        dx = split_x + 2

        safe_addstr(win, dy, dx, t("version_id"), curses.color_pair(Colors.MUTED))
        safe_addstr(win, dy + 1, dx + 2, cur.id, curses.color_pair(Colors.NORMAL) | curses.A_BOLD)

        safe_addstr(win, dy + 3, dx, t("version_type"), curses.color_pair(Colors.MUTED))
        safe_addstr(win, dy + 3, dx + 15, cur.display_type, curses.color_pair(Colors.ACCENT))

        safe_addstr(win, dy + 4, dx, t("release_date"), curses.color_pair(Colors.MUTED))
        safe_addstr(win, dy + 4, dx + 15, cur.release_time or "Unknown", curses.color_pair(Colors.NORMAL))

        java_req = f"Java {cur.java_major_version}+" if cur.java_major_version else "Any (Default)"
        safe_addstr(win, dy + 5, dx, t("java_version"), curses.color_pair(Colors.MUTED))
        safe_addstr(win, dy + 5, dx + 15, java_req, curses.color_pair(Colors.NORMAL))

        if cur.inherits_from:
            safe_addstr(win, dy + 6, dx, t("inherits_from"), curses.color_pair(Colors.MUTED))
            safe_addstr(win, dy + 6, dx + 16, cur.inherits_from, curses.color_pair(Colors.NORMAL))

        safe_addstr(win, dy + 8, dx, t("main_class"), curses.color_pair(Colors.MUTED))
        mc_name = cur.main_class or "(Default Launcher Main)"
        safe_addstr(win, dy + 9, dx + 2, truncate_str(mc_name, det_w - 6), curses.color_pair(Colors.MUTED))

        # Launch quick button
        launch_btn = t("btn_launch")
        safe_addstr(win, top_y + h - 3, dx + 2, launch_btn, curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD)
    else:
        safe_addstr(win, top_y + 2, split_x + 3, t("select_version_hint"), curses.color_pair(Colors.MUTED))


def build_settings_fields(config: Config) -> List[Tuple[str, str, str, str]]:
    """Return the ordered (action, label, value, description) rows of Settings."""
    detected = set(installed_majors())
    jre_fields = [
        (
            f"jre:{version}",
            t("field_install_jre", version=version),
            t("jre_installed") if version in detected else t("jre_install_value"),
            t("desc_install_jre", version=version),
        )
        for version in JRE_VERSIONS
    ]

    return [
        ("username", t("field_username"), config.username, t("desc_username")),
        ("theme", t("field_theme"), theme_label(get_theme_name(config)), t("desc_theme")),
        ("accent_color", t("field_accent_color"), accent_label(get_accent_choice(config)), t("desc_accent_color")),
        ("header_style", t("field_header_style"), header_style_label(get_header_style(config)), t("desc_header_style")),
        ("selection_style", t("field_selection_style"), selection_style_label(get_selection_style(config)), t("desc_selection_style")),
        ("min_ram", t("field_min_ram"), config.min_ram, t("desc_min_ram")),
        ("max_ram", t("field_max_ram"), config.max_ram, t("desc_max_ram")),
        ("java_path", t("field_java_path"), config.java_path or "[Auto-Detect Best Java]", t("desc_java_path")),
        *jre_fields,
        ("game_dir", t("field_game_dir"), str(config.game_dir), t("desc_game_dir")),
        ("jvm_flags", t("field_jvm_flags"), config.custom_jvm_args or "(none)", t("desc_jvm_flags")),
        ("win_w", t("field_win_w"), str(config.get("window_width", 854)), t("desc_win_w")),
        ("win_h", t("field_win_h"), str(config.get("window_height", 480)), t("desc_win_h")),
        ("mirror", t("field_mirror"), config.download_mirror, t("desc_mirror")),
        ("assets", t("field_assets"), "Enabled" if config.download_assets else "Disabled", t("desc_assets")),
        ("threads", t("field_threads"), str(config.download_threads), t("desc_threads")),
        ("language", t("field_language"), config.language, t("desc_language")),
    ]


def render_settings_view(
    win: curses.window,
    config: Config,
    selected_idx: int,
    top_y: int,
    bottom_y: int,
) -> None:
    """Render interactive settings form with scrolling for long field lists."""
    max_y, max_x = win.getmaxyx()
    h = bottom_y - top_y

    fields = build_settings_fields(config)

    start_y = top_y + 2
    available_rows = max(1, (bottom_y - 2) - start_y)
    per_page = max(1, available_rows // 2)
    total = len(fields)
    selected = min(max(0, selected_idx), total - 1)

    offset = 0
    if selected >= per_page:
        offset = min(selected - per_page + 1, max(0, total - per_page))

    title = t("box_settings")
    if total > per_page:
        title += f"  [{offset + 1}-{min(offset + per_page, total)}/{total}]"

    draw_box(win, top_y, 0, h, max_x, title, curses.color_pair(Colors.ACCENT))

    for i in range(offset, min(offset + per_page, total)):
        _action, label, val, desc = fields[i]
        row_y = start_y + ((i - offset) * 2)

        is_sel = (i == selected)
        cursor_prefix = "► " if is_sel else "  "

        label_col = 4
        val_col = 32

        if is_sel:
            safe_addstr(win, row_y, label_col - 2, cursor_prefix + f"{label}:", curses.color_pair(Colors.ACCENT) | curses.A_BOLD)
            val_disp = f" {val} "
            safe_addstr(win, row_y, val_col, pad_str(val_disp, max_x - val_col - 4), curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD)
            safe_addstr(win, row_y + 1, val_col, f"↳ {desc}", curses.color_pair(Colors.MUTED))
        else:
            safe_addstr(win, row_y, label_col, f"{label}:", curses.color_pair(Colors.NORMAL))
            safe_addstr(win, row_y, val_col, truncate_str(str(val), max_x - val_col - 4), curses.color_pair(Colors.NORMAL))


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

    status_str = t("console_running") if is_running else t("console_stopped", code=exit_code)
    scroll_str = t("auto_scroll_on") if auto_scroll else t("scroll_offset", offset=scroll_offset)
    title = t("box_console", status=status_str, scroll=scroll_str)

    draw_box(win, top_y, 0, h, max_x, title, curses.color_pair(Colors.ACCENT))

    content_h = h - 2
    total_lines = len(log_buffer)

    if total_lines == 0:
        safe_addstr(win, top_y + 2, 3, t("no_logs_yet"), curses.color_pair(Colors.MUTED))
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

        safe_addstr(win, top_y + 1 + i, 2, truncate_str(line, max_x - 4), attr)


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

    draw_box(win, top_y, 0, h, max_x, t("box_dir_picker"), curses.color_pair(Colors.ACCENT))

    safe_addstr(win, top_y + 2, 3, t("current_game_dir", dir=current_dir), curses.color_pair(Colors.NORMAL) | curses.A_BOLD)
    safe_addstr(win, top_y + 4, 3, t("discovered_dirs"), curses.color_pair(Colors.ACCENT))

    start_y = top_y + 6
    for i, (name, path, v_count) in enumerate(candidates):
        row_y = start_y + i
        if row_y >= bottom_y - 2:
            break

        is_sel = (i == selected_idx)
        is_cur = (str(path.resolve()) == str(current_dir.resolve()))

        cur_marker = t("current_marker") if is_cur else ""
        count_str = t("versions_count", count=v_count) if v_count > 0 else t("zero_versions")

        line = f" {pad_str(name, 22)} {pad_str(str(path), 38)} {pad_str(count_str, 18)}{cur_marker}"
        line = pad_str(line, max_x - 4)

        if is_sel:
            safe_addstr(win, row_y, 2, line, curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD)
        else:
            attr = curses.color_pair(Colors.SUCCESS if is_cur else Colors.NORMAL)
            safe_addstr(win, row_y, 2, line, attr)

    safe_addstr(win, bottom_y - 3, 3, t("dir_picker_hint"), curses.color_pair(Colors.MUTED))


def render_download_view(
    win: curses.window,
    remote_versions: List[RemoteVersion],
    selected_idx: int,
    filter_text: str,
    show_snapshots: bool,
    config: Config,
    installed_ids: Set[str],
    is_loading: bool,
    load_error: str,
    top_y: int,
    bottom_y: int,
) -> None:
    """Render official Mojang vanilla version downloader view."""
    max_y, max_x = win.getmaxyx()
    h = bottom_y - top_y
    if h < 4 or max_x < 30:
        return

    split_x = int(max_x * 0.58)

    # 1. Left Pane: Available versions list
    box_w = split_x
    snap_str = t("mode_all") if show_snapshots else t("mode_releases")
    left_title = t("box_remote_versions", count=len(remote_versions))
    draw_box(win, top_y, 0, h, box_w, left_title, curses.color_pair(Colors.ACCENT))

    if is_loading:
        safe_addstr(win, top_y + 2, 3, t("connecting_mojang"), curses.color_pair(Colors.WARNING) | curses.A_BOLD)
        safe_addstr(win, top_y + 3, 3, t("fetching_manifest"), curses.color_pair(Colors.MUTED))
        return

    if load_error:
        safe_addstr(win, top_y + 2, 3, t("failed_manifest"), curses.color_pair(Colors.DANGER) | curses.A_BOLD)
        safe_addstr(win, top_y + 3, 3, truncate_str(load_error, box_w - 6), curses.color_pair(Colors.MUTED))
        safe_addstr(win, top_y + 5, 3, t("press_r_retry"), curses.color_pair(Colors.ACCENT))
        return

    # Filter / mode line
    if filter_text:
        header_line = t("filter_mode_header", filter=filter_text, mode=snap_str)
    else:
        header_line = t("mode_header", mode=snap_str)
    safe_addstr(win, top_y + 1, 2, truncate_str(header_line, box_w - 4), curses.color_pair(Colors.WARNING))

    content_y_start = top_y + 2
    visible_rows = h - 3

    if not remote_versions:
        safe_addstr(win, content_y_start + 1, 2, t("no_remote_found"), curses.color_pair(Colors.MUTED))
        safe_addstr(win, content_y_start + 3, 2, t("clear_filter_hint"), curses.color_pair(Colors.ACCENT))
    else:
        scroll_start = 0
        if selected_idx >= visible_rows:
            scroll_start = selected_idx - visible_rows + 1

        for i in range(visible_rows):
            v_idx = scroll_start + i
            if v_idx >= len(remote_versions):
                break

            v = remote_versions[v_idx]
            is_selected = (v_idx == selected_idx)
            is_installed = v.id in installed_ids
            row_y = content_y_start + i

            badge = f"[{v.display_type}]"
            vid_w = max(10, box_w - str_width(badge) - 22)
            vid_disp = truncate_str(v.id, vid_w)

            installed_badge = t("badge_installed") if is_installed else ""
            date_str = f"({v.release_time})" if v.release_time else ""

            line_str = f" {badge} {vid_disp}"
            right_part = f"{date_str} {installed_badge}".strip()
            if right_part:
                rem_w = box_w - 2 - str_width(line_str) - str_width(right_part)
                if rem_w > 0:
                    line_str = line_str + (" " * rem_w) + right_part
            line_str = pad_str(line_str, box_w - 2)

            if is_selected:
                safe_addstr(win, row_y, 1, line_str, curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD)
            else:
                attr = curses.color_pair(Colors.SUCCESS if is_installed else Colors.NORMAL)
                if not v.is_release:
                    attr = curses.color_pair(Colors.MUTED)
                safe_addstr(win, row_y, 1, line_str, attr)

    # 2. Right Pane: Details & Download action
    det_w = max_x - split_x
    draw_box(win, top_y, split_x, h, det_w, t("box_download_details"), curses.color_pair(Colors.ACCENT))

    if remote_versions and 0 <= selected_idx < len(remote_versions):
        cur = remote_versions[selected_idx]
        is_installed = cur.id in installed_ids
        dy = top_y + 2
        dx = split_x + 2

        safe_addstr(win, dy, dx, t("version_id"), curses.color_pair(Colors.MUTED))
        safe_addstr(win, dy + 1, dx + 2, cur.id, curses.color_pair(Colors.NORMAL) | curses.A_BOLD)

        safe_addstr(win, dy + 3, dx, t("version_type"), curses.color_pair(Colors.MUTED))
        safe_addstr(win, dy + 3, dx + 14, cur.display_type, curses.color_pair(Colors.ACCENT))

        safe_addstr(win, dy + 4, dx, t("release_date"), curses.color_pair(Colors.MUTED))
        safe_addstr(win, dy + 4, dx + 14, cur.release_time or "Unknown", curses.color_pair(Colors.NORMAL))

        safe_addstr(win, dy + 5, dx, t("download_options"), curses.color_pair(Colors.MUTED))
        if is_installed:
            safe_addstr(win, dy + 5, dx + 14, t("status_installed"), curses.color_pair(Colors.SUCCESS) | curses.A_BOLD)
        else:
            safe_addstr(win, dy + 5, dx + 14, t("status_not_installed"), curses.color_pair(Colors.WARNING))

        safe_addstr(win, dy + 7, dx, t("download_options"), curses.color_pair(Colors.ACCENT) | curses.A_BOLD)

        assets_flag = t("assets_yes") if config.download_assets else t("assets_no")
        safe_addstr(win, dy + 8, dx + 2, t("include_assets_opt", opt=assets_flag), curses.color_pair(Colors.NORMAL))
        safe_addstr(win, dy + 9, dx + 2, t("mirror_opt", mirror=config.download_mirror.capitalize()), curses.color_pair(Colors.MUTED))
        safe_addstr(win, dy + 10, dx + 2, t("threads_opt", threads=config.download_threads), curses.color_pair(Colors.MUTED))
        dest_str = str(config.game_dir / "versions" / cur.id)
        if str_width(dest_str) > det_w - 6:
            dest_str = "..." + dest_str[-(det_w - 9):]
        safe_addstr(win, dy + 11, dx + 2, t("dest_opt", dest=dest_str), curses.color_pair(Colors.MUTED))

        # Action button
        btn_label = t("btn_redownload") if is_installed else t("btn_download")
        safe_addstr(win, top_y + h - 4, dx + 2, btn_label, curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD)

        # Quick hint
        safe_addstr(win, top_y + h - 2, dx + 2, t("download_bottom_hint"), curses.color_pair(Colors.MUTED))
    else:
        safe_addstr(win, top_y + 2, split_x + 3, t("select_download_hint"), curses.color_pair(Colors.MUTED))

def render_about_view(
    win: curses.window,
    top_y: int,
    bottom_y: int,
) -> None:
    """Render the About page with version, build time, and OS information."""
    import platform
    import socket
    import sys

    from mc_tui import __version__, __build_time__

    max_y, max_x = win.getmaxyx()
    h = bottom_y - top_y

    draw_box(win, top_y, 0, h, max_x, t("box_about"), curses.color_pair(Colors.ACCENT))

    dy = top_y + 2
    dx = 4
    val_col = 28

    def row(label: str, value: str, color: int = Colors.NORMAL, label_color: int = Colors.MUTED) -> None:
        nonlocal dy
        if dy >= bottom_y - 1:
            return
        safe_addstr(win, dy, dx, label, curses.color_pair(label_color))
        safe_addstr(win, dy, dx + val_col, truncate_str(value, max_x - dx - val_col - 2), curses.color_pair(color) | curses.A_BOLD)
        dy += 1

    def blank() -> None:
        nonlocal dy
        dy += 1

    # --- MC-TUI Version Info ---
    safe_addstr(win, dy, dx, "MC-TUI", curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD)
    dy += 1
    row(t("about_version_label"), __version__, Colors.SUCCESS)
    row(t("about_build_label"), __build_time__ or t("about_build_dev"), Colors.NORMAL)
    blank()

    # --- OS Info ---
    safe_addstr(win, dy, dx, t("about_os_label"), curses.color_pair(Colors.ACCENT) | curses.A_BOLD)
    dy += 1

    uname = platform.uname()
    row(t("about_os_name_label"), uname.system or "Unknown")
    row(t("about_os_release_label"), uname.release or "Unknown")
    row(t("about_os_version_label"), truncate_str(uname.version or "Unknown", max_x - dx - val_col - 4))
    row(t("about_os_machine_label"), uname.machine or "Unknown")

    # Processor info (may be empty on some systems)
    proc_info = uname.processor or platform.processor() or "Unknown"
    row(t("about_os_processor_label"), truncate_str(proc_info, max_x - dx - val_col - 4))
    blank()

    # --- Python & Runtime ---
    py_ver = sys.version.replace("\n", " ")
    row(t("about_python_label"), py_ver, Colors.MUTED)

    # Hostname
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "Unknown"
    row(t("about_hostname_label"), hostname, Colors.MUTED)
    blank()

    # --- Description & Links ---
    if dy < bottom_y - 2:
        safe_addstr(win, dy, dx, t("about_desc"), curses.color_pair(Colors.NORMAL))
        dy += 1
    if dy < bottom_y - 2:
        safe_addstr(win, dy, dx, t("about_github"), curses.color_pair(Colors.MUTED))
        dy += 1
    if dy < bottom_y - 2:
        safe_addstr(win, dy, dx, t("about_license"), curses.color_pair(Colors.MUTED))


def render_download_progress_modal(
    win: curses.window,
    progress: Optional[DownloadProgress],
    version_id: str,
) -> None:
    """Render modal progress box during active download directly on main window without flicker."""
    max_y, max_x = win.getmaxyx()
    box_w = min(max_x - 6, 68)
    box_h = 10
    start_y = max(1, (max_y - box_h) // 2)
    start_x = max(1, (max_x - box_w) // 2)

    # 1. Blank out modal background area so underlying text does not bleed through
    for r in range(start_y, start_y + box_h):
        safe_addstr(win, r, start_x, " " * box_w, curses.color_pair(Colors.NORMAL))

    # 2. Draw outer border
    title = t("modal_downloading", version=version_id)
    draw_box(win, start_y, start_x, box_h, box_w, title, curses.color_pair(Colors.ACCENT))

    if not progress:
        safe_addstr(win, start_y + 3, start_x + 4, t("preparing_download"), curses.color_pair(Colors.MUTED))
        return

    # 3. Stage / Message
    msg = progress.message or f"Stage: {progress.stage}"
    safe_addstr(win, start_y + 2, start_x + 4, truncate_str(msg, box_w - 8), curses.color_pair(Colors.NORMAL) | curses.A_BOLD)

    # 4. Current file
    if progress.current_file:
        file_text = t("file_prefix", file=progress.current_file)
        safe_addstr(win, start_y + 3, start_x + 4, truncate_str(file_text, box_w - 8), curses.color_pair(Colors.MUTED))

    # 5. Progress bar
    bar_w = box_w - 18
    pct = progress.percent
    filled = int(bar_w * (pct / 100.0))
    bar_str = "█" * filled + "░" * (bar_w - filled)
    bar_display = f"[{bar_str}] {pct:5.1f}%"
    safe_addstr(win, start_y + 5, start_x + 4, bar_display, curses.color_pair(Colors.HIGHLIGHT) | curses.A_BOLD)

    # 6. Speed & Bytes
    info_parts = []
    if progress.total_bytes > 0 or progress.bytes_downloaded > 0:
        info_parts.append(progress.formatted_bytes)
    if progress.speed > 0:
        info_parts.append(progress.formatted_speed)
    if info_parts:
        safe_addstr(win, start_y + 6, start_x + 4, "  │  ".join(info_parts), curses.color_pair(Colors.MUTED))

    # 7. Cancel prompt
    cancel_hint = t("cancel_download_hint")
    safe_addstr(win, start_y + box_h - 2, start_x + 4, cancel_hint, curses.color_pair(Colors.DANGER))

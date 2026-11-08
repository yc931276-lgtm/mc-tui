"""Main TUI application event loop and state management."""
from __future__ import annotations

import curses
import os
import shlex
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from mc_tui.config import Config, DEFAULT_CONFIG
from mc_tui.launcher import Launcher, MinecraftProcess
from mc_tui.tui.ui_helpers import (
    Colors,
    init_colors,
    prompt_input,
    show_message_modal,
)
from mc_tui.tui.views import (
    render_console_view,
    render_dir_picker_view,
    render_footer,
    render_header,
    render_settings_view,
    render_versions_view,
)
from mc_tui.version_parser import VersionMeta, VersionScanner


class MCTuiApp:
    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()
        self.launcher = Launcher(self.config)
        self.active_tab = 0  # 0: Versions, 1: Settings, 2: Console, 3: Dir Picker

        # Versions tab state
        self.all_versions: List[VersionMeta] = []
        self.filtered_versions: List[VersionMeta] = []
        self.selected_version_idx = 0
        self.filter_text = ""

        # Settings tab state
        self.selected_setting_idx = 0

        # Console tab state
        self.auto_scroll = True
        self.scroll_offset = 0

        # Dir picker state
        self.dir_candidates: List[Tuple[str, Path, int]] = []
        self.selected_dir_idx = 0

        # Scan initial state
        self.refresh_versions()
        self.refresh_dir_candidates()

    def refresh_versions(self) -> None:
        """Scan current game directory for versions."""
        scanner = VersionScanner(self.config.game_dir)
        self.all_versions = scanner.list_versions()
        self.apply_filter()

    def apply_filter(self) -> None:
        if not self.filter_text:
            self.filtered_versions = list(self.all_versions)
        else:
            q = self.filter_text.lower()
            self.filtered_versions = [
                v for v in self.all_versions
                if q in v.id.lower() or q in v.display_type.lower()
            ]

        # Select last played or clamp index
        if self.config.get("last_version"):
            for idx, v in enumerate(self.filtered_versions):
                if v.id == self.config.get("last_version"):
                    self.selected_version_idx = idx
                    return

        if self.selected_version_idx >= len(self.filtered_versions):
            self.selected_version_idx = max(0, len(self.filtered_versions) - 1)

    def refresh_dir_candidates(self) -> None:
        """Scan common local paths for Minecraft installations."""
        home = Path.home()
        common = [
            ("Default Minecraft", home / ".minecraft"),
            ("Prism Launcher", home / ".local" / "share" / "PrismLauncher"),
            ("Flatpak Minecraft", home / ".var" / "app" / "com.mojang.Minecraft" / ".minecraft"),
            ("Home Games Folder", home / "Games" / "minecraft"),
            ("Home Directory", home / "minecraft"),
        ]

        candidates: List[Tuple[str, Path, int]] = []
        # Add current directory first if not already in list
        cur = self.config.game_dir
        cur_scanner = VersionScanner(cur)
        candidates.append(("Current Active Dir", cur, len(cur_scanner.list_versions())))

        for name, p in common:
            if p.exists() and p.resolve() != cur.resolve():
                count = len(VersionScanner(p).list_versions())
                candidates.append((name, p, count))

        self.dir_candidates = candidates

    def run(self, stdscr: curses.window) -> None:
        """Curses main loop."""
        curses.curs_set(0)
        stdscr.timeout(100)  # Non-blocking input timeout (100ms) for live logs
        init_colors()

        while True:
            stdscr.erase()
            max_y, max_x = stdscr.getmaxyx()

            if max_y < 12 or max_x < 40:
                stdscr.addstr(0, 0, "Terminal window too small! Please resize.", curses.A_BOLD)
                stdscr.refresh()
                ch = stdscr.getch()
                if ch in (ord("q"), ord("Q")):
                    break
                continue

            # Render top and bottom chrome
            render_header(stdscr, self.active_tab, self.config, self.launcher)
            render_footer(stdscr, self.active_tab)

            top_y = 4
            bottom_y = max_y - 1

            # Render tab content
            if self.active_tab == 0:
                render_versions_view(
                    stdscr,
                    self.filtered_versions,
                    self.selected_version_idx,
                    self.filter_text,
                    self.config,
                    top_y,
                    bottom_y,
                )
            elif self.active_tab == 1:
                render_settings_view(
                    stdscr,
                    self.config,
                    self.selected_setting_idx,
                    top_y,
                    bottom_y,
                )
            elif self.active_tab == 2:
                proc = self.launcher.current_process
                logs = list(proc.log_buffer) if proc else []
                is_running = proc.is_running if proc else False
                exit_code = proc.exit_code if proc else None
                render_console_view(
                    stdscr,
                    logs,
                    is_running,
                    exit_code,
                    self.auto_scroll,
                    self.scroll_offset,
                    top_y,
                    bottom_y,
                )
            elif self.active_tab == 3:
                render_dir_picker_view(
                    stdscr,
                    self.config.game_dir,
                    self.dir_candidates,
                    self.selected_dir_idx,
                    top_y,
                    bottom_y,
                )

            stdscr.refresh()

            # Handle user keystroke
            ch = stdscr.getch()
            if ch == -1:
                continue

            # Global keys
            if ch in (ord("q"), ord("Q")):
                # If game is running, confirm quit
                if self.launcher.current_process and self.launcher.current_process.is_running:
                    ans = prompt_input(stdscr, "Minecraft is running! Quit launcher? (y/n)", "n", 2)
                    if ans and ans.lower().startswith("y"):
                        break
                else:
                    break
            elif ch == ord("1"):
                self.active_tab = 0
            elif ch == ord("2"):
                self.active_tab = 1
            elif ch == ord("3"):
                self.active_tab = 2
            elif ch == ord("4"):
                self.active_tab = 3
            elif ch in (ord("\t"),):  # Tab key cycles tabs
                self.active_tab = (self.active_tab + 1) % 4
            elif self.active_tab == 0:
                self._handle_versions_input(stdscr, ch)
            elif self.active_tab == 1:
                self._handle_settings_input(stdscr, ch)
            elif self.active_tab == 2:
                self._handle_console_input(stdscr, ch)
            elif self.active_tab == 3:
                self._handle_dir_input(stdscr, ch)

    def _handle_versions_input(self, stdscr: curses.window, ch: int) -> None:
        count = len(self.filtered_versions)
        if ch in (curses.KEY_UP, ord("k")):
            if count > 0:
                self.selected_version_idx = (self.selected_version_idx - 1) % count
        elif ch in (curses.KEY_DOWN, ord("j")):
            if count > 0:
                self.selected_version_idx = (self.selected_version_idx + 1) % count
        elif ch in (curses.KEY_PPAGE,):  # Page Up
            self.selected_version_idx = max(0, self.selected_version_idx - 10)
        elif ch in (curses.KEY_NPAGE,):  # Page Down
            if count > 0:
                self.selected_version_idx = min(count - 1, self.selected_version_idx + 10)
        elif ch == ord("/"):
            query = prompt_input(stdscr, "Filter versions by name:", self.filter_text)
            if query is not None:
                self.filter_text = query
                self.apply_filter()
        elif ch in (ord("r"), ord("R")):
            self.refresh_versions()
            show_message_modal(stdscr, "Refresh Complete", [f"Found {len(self.all_versions)} version(s)."])
        elif ch in (curses.KEY_ENTER, 10, 13):
            self._launch_selected_version(stdscr)
        elif ch in (ord("p"), ord("P")):
            self._preview_command(stdscr)

    def _launch_selected_version(self, stdscr: curses.window) -> None:
        if not self.filtered_versions:
            show_message_modal(stdscr, "No Version Selected", ["No Minecraft version is currently selected."])
            return

        cur_v = self.filtered_versions[self.selected_version_idx]

        try:
            self.launcher.launch(cur_v)
            # Switch to console view
            self.active_tab = 2
            self.auto_scroll = True
        except Exception as e:
            show_message_modal(stdscr, "Launch Error", [f"Failed to launch {cur_v.id}:", "", str(e)])

    def _preview_command(self, stdscr: curses.window) -> None:
        if not self.filtered_versions:
            return
        cur_v = self.filtered_versions[self.selected_version_idx]
        try:
            plan = self.launcher.build_launch_plan(cur_v)
            cmd_lines = [
                f"Version ID: {cur_v.id}",
                f"Working Dir: {plan.cwd}",
                f"Java Path: {plan.java_bin}",
                "",
                "Command Arguments:",
            ]
            for arg in [plan.java_bin] + plan.args:
                cmd_lines.append(f"  {arg}")
            show_message_modal(stdscr, f"Launch Command: {cur_v.id}", cmd_lines)
        except Exception as e:
            show_message_modal(stdscr, "Preview Error", [str(e)])

    def _handle_settings_input(self, stdscr: curses.window, ch: int) -> None:
        total_fields = 8
        if ch in (curses.KEY_UP, ord("k")):
            self.selected_setting_idx = (self.selected_setting_idx - 1) % total_fields
        elif ch in (curses.KEY_DOWN, ord("j")):
            self.selected_setting_idx = (self.selected_setting_idx + 1) % total_fields
        elif ch in (curses.KEY_ENTER, 10, 13):
            self._edit_setting_field(stdscr, self.selected_setting_idx)
        elif ch in (ord("s"), ord("S")):
            self.config.save()
            show_message_modal(stdscr, "Config Saved", ["Configuration successfully saved to disk!"])
        elif ch in (ord("r"), ord("R")):
            ans = prompt_input(stdscr, "Reset all settings to defaults? (y/n)", "n", 2)
            if ans and ans.lower().startswith("y"):
                self.config.data = dict(DEFAULT_CONFIG)
                self.config.save()
                self.refresh_versions()
                show_message_modal(stdscr, "Reset", ["Settings restored to defaults."])

    def _edit_setting_field(self, stdscr: curses.window, idx: int) -> None:
        if idx == 0:
            val = prompt_input(stdscr, "Enter Player Username:", self.config.username, 32)
            if val is not None and val.strip():
                self.config.username = val.strip()
        elif idx == 1:
            val = prompt_input(stdscr, "Enter Minimum RAM (-Xms, e.g. 512M, 1G):", self.config.min_ram, 10)
            if val is not None and val.strip():
                self.config.min_ram = val.strip()
        elif idx == 2:
            val = prompt_input(stdscr, "Enter Maximum RAM (-Xmx, e.g. 2G, 4G, 8G):", self.config.max_ram, 10)
            if val is not None and val.strip():
                self.config.max_ram = val.strip()
        elif idx == 3:
            val = prompt_input(stdscr, "Enter Java Executable Path (blank for auto-detect):", self.config.java_path, 80)
            if val is not None:
                self.config.java_path = val.strip()
        elif idx == 4:
            val = prompt_input(stdscr, "Enter Game Directory Path:", str(self.config.game_dir), 80)
            if val is not None and val.strip():
                self.config.game_dir = val.strip()
                self.refresh_versions()
                self.refresh_dir_candidates()
        elif idx == 5:
            val = prompt_input(stdscr, "Enter Custom JVM Flags:", self.config.custom_jvm_args, 80)
            if val is not None:
                self.config.custom_jvm_args = val.strip()
        elif idx == 6:
            val = prompt_input(stdscr, "Enter Initial Window Width:", str(self.config.get("window_width", 854)), 8)
            if val is not None and val.isdigit():
                self.config.set("window_width", int(val))
        elif idx == 7:
            val = prompt_input(stdscr, "Enter Initial Window Height:", str(self.config.get("window_height", 480)), 8)
            if val is not None and val.isdigit():
                self.config.set("window_height", int(val))

    def _handle_console_input(self, stdscr: curses.window, ch: int) -> None:
        proc = self.launcher.current_process
        total_logs = len(proc.log_buffer) if proc else 0

        if ch in (curses.KEY_UP, ord("k")):
            self.auto_scroll = False
            self.scroll_offset = max(0, self.scroll_offset - 1)
        elif ch in (curses.KEY_DOWN, ord("j")):
            self.scroll_offset = min(total_logs, self.scroll_offset + 1)
        elif ch in (curses.KEY_PPAGE,):  # Page Up
            self.auto_scroll = False
            self.scroll_offset = max(0, self.scroll_offset - 15)
        elif ch in (curses.KEY_NPAGE,):  # Page Down
            self.scroll_offset = min(total_logs, self.scroll_offset + 15)
        elif ch == ord(" "):  # Space toggles auto-scroll
            self.auto_scroll = not self.auto_scroll
            if self.auto_scroll:
                self.scroll_offset = max(0, total_logs - 20)
        elif ch in (ord("k"), ord("K")):  # Kill Minecraft
            if proc and proc.is_running:
                ans = prompt_input(stdscr, "Terminate Minecraft process? (y/n)", "n", 2)
                if ans and ans.lower().startswith("y"):
                    proc.stop()
                    show_message_modal(stdscr, "Process Stopped", ["Minecraft process terminated."])
        elif ch in (ord("c"), ord("C")):  # Clear logs
            if proc:
                proc.log_buffer.clear()

    def _handle_dir_input(self, stdscr: curses.window, ch: int) -> None:
        count = len(self.dir_candidates)
        if ch in (curses.KEY_UP, ord("k")):
            if count > 0:
                self.selected_dir_idx = (self.selected_dir_idx - 1) % count
        elif ch in (curses.KEY_DOWN, ord("j")):
            if count > 0:
                self.selected_dir_idx = (self.selected_dir_idx + 1) % count
        elif ch in (curses.KEY_ENTER, 10, 13):
            if self.dir_candidates:
                _, chosen_path, _ = self.dir_candidates[self.selected_dir_idx]
                self.config.game_dir = chosen_path
                self.refresh_versions()
                self.refresh_dir_candidates()
                show_message_modal(stdscr, "Game Dir Changed", [f"Game directory set to:", str(chosen_path)])
                self.active_tab = 0  # switch back to versions
        elif ch in (ord("e"), ord("E")):
            new_path = prompt_input(stdscr, "Enter custom directory path:", str(self.config.game_dir), 80)
            if new_path and new_path.strip():
                p = Path(os.path.expanduser(new_path.strip()))
                self.config.game_dir = p
                self.refresh_versions()
                self.refresh_dir_candidates()
                show_message_modal(stdscr, "Game Dir Changed", [f"Game directory set to:", str(p)])
                self.active_tab = 0


def main() -> None:
    app = MCTuiApp()
    try:
        curses.wrapper(app.run)
    except KeyboardInterrupt:
        pass

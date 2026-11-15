"""Main TUI application event loop and state management."""
from __future__ import annotations

import curses
import os
import shlex
import sys
import threading
from pathlib import Path
from typing import List, Optional, Set, Tuple

from mc_tui.config import Config, DEFAULT_CONFIG
from mc_tui.downloader import (
    Downloader,
    DownloadProgress,
    RemoteVersion,
)
from mc_tui.i18n import set_language, t
from mc_tui.jre_manager import (
    format_command,
    get_install_command,
    install_jre,
    refresh_detection,
)
from mc_tui.launcher import Launcher, MinecraftProcess
from mc_tui.theme import (
    ACCENT_CHOICES,
    HEADER_STYLES,
    SELECTION_STYLES,
    THEME_NAMES,
    get_accent_choice,
    get_header_style,
    get_selection_style,
    get_theme_name,
    next_choice,
)
from mc_tui.tui.ui_helpers import (
    Colors,
    init_colors,
    prompt_input,
    show_message_modal,
)
from mc_tui.tui.version_filter import best_match_index, filter_versions
from mc_tui.tui.views import (
    build_settings_fields,
    render_about_view,
    render_console_view,
    render_dir_picker_view,
    render_download_progress_modal,
    render_download_view,
    render_footer,
    render_header,
    render_settings_view,
    render_versions_view,
)
from mc_tui.version_parser import VersionMeta, VersionScanner


class MCTuiApp:
    def __init__(self, config: Optional[Config] = None) -> None:
        self.config = config or Config()
        set_language(self.config.language)
        self.launcher = Launcher(self.config)
        self.active_tab = 0  # 0: Versions, 1: Settings, 2: Console, 3: Dir Picker, 4: Download

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

        # Downloader tab state
        self.downloader = Downloader(self.config.game_dir, mirror=self.config.download_mirror)
        self.remote_versions: List[RemoteVersion] = []
        self.filtered_remote_versions: List[RemoteVersion] = []
        self.selected_remote_idx = 0
        self.remote_filter_text = ""
        self.show_snapshots = False
        self.manifest_loaded = False
        self.manifest_loading = False
        self.manifest_error = ""

        # Active download state
        self.is_downloading = False
        self.download_progress: Optional[DownloadProgress] = None
        self.cancel_download_token: Optional[threading.Event] = None
        self.download_thread: Optional[threading.Thread] = None
        self.download_success: Optional[bool] = None
        self.download_error_msg: str = ""
        self.last_downloaded_version: str = ""

        # Scan initial state
        self.refresh_versions()
        self.refresh_dir_candidates()

        # Preload manifest in background
        self.load_manifest_async()

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

    def load_manifest_async(self, force_refresh: bool = False) -> None:
        """Fetch remote versions from Mojang in background thread."""
        if self.manifest_loading:
            return
        self.manifest_loading = True
        self.manifest_error = ""

        def task() -> None:
            try:
                self.downloader.game_dir = self.config.game_dir
                self.downloader.mirror = self.config.download_mirror
                versions = self.downloader.fetch_manifest(force_refresh=force_refresh)
                self.remote_versions = versions
                self.manifest_loaded = True
                self.manifest_error = ""
                self.apply_remote_filter()
            except Exception as e:
                self.manifest_error = str(e)
            finally:
                self.manifest_loading = False

        threading.Thread(target=task, daemon=True).start()

    def apply_remote_filter(self, select_best: bool = False) -> None:
        """Filter remote versions and keep a sensible selected row."""
        previous_id = ""
        if 0 <= self.selected_remote_idx < len(self.filtered_remote_versions):
            previous_id = self.filtered_remote_versions[self.selected_remote_idx].id

        self.filtered_remote_versions = filter_versions(
            self.remote_versions,
            self.remote_filter_text,
            self.show_snapshots,
        )

        if select_best:
            self.selected_remote_idx = best_match_index(
                self.filtered_remote_versions,
                self.remote_filter_text,
            )
        elif previous_id:
            for index, version in enumerate(self.filtered_remote_versions):
                if version.id == previous_id:
                    self.selected_remote_idx = index
                    break
            else:
                self.selected_remote_idx = 0
        else:
            self.selected_remote_idx = 0

        if self.filtered_remote_versions:
            self.selected_remote_idx = min(
                self.selected_remote_idx,
                len(self.filtered_remote_versions) - 1,
            )
        else:
            self.selected_remote_idx = 0

    def _on_download_progress(self, prog: DownloadProgress) -> None:
        self.download_progress = prog

    def start_download_selected(self, stdscr: curses.window) -> None:
        if not self.filtered_remote_versions:
            return
        ver = self.filtered_remote_versions[self.selected_remote_idx]

        # Check if already installed
        local_ids = {v.id for v in self.all_versions}
        if ver.id in local_ids:
            ans = prompt_input(stdscr, t("already_installed_prompt", version=ver.id), "n", 2)
            if not ans or not ans.lower().startswith("y"):
                return

        self.is_downloading = True
        self.download_progress = None
        self.cancel_download_token = threading.Event()
        self.download_success = None
        self.download_error_msg = ""
        self.last_downloaded_version = ver.id

        def task() -> None:
            try:
                self.downloader.game_dir = self.config.game_dir
                self.downloader.mirror = self.config.download_mirror
                ok = self.downloader.download_version(
                    version_id=ver.id,
                    include_assets=self.config.download_assets,
                    progress_callback=self._on_download_progress,
                    cancel_token=self.cancel_download_token,
                    max_workers=self.config.download_threads,
                )
                self.download_success = ok
            except Exception as e:
                self.download_success = False
                self.download_error_msg = str(e)
            finally:
                self.is_downloading = False

        self.download_thread = threading.Thread(target=task, daemon=True)
        self.download_thread.start()

    def run(self, stdscr: curses.window) -> None:
        """Curses main loop."""
        curses.curs_set(0)
        stdscr.keypad(True)
        stdscr.timeout(100)  # Non-blocking input timeout (100ms) for live logs & progress
        init_colors(self.config)

        while True:
            # Check if background download just finished
            if not self.is_downloading and self.download_success is not None:
                success = self.download_success
                ver_id = self.last_downloaded_version
                self.download_success = None
                self.refresh_versions()

                if success:
                    ans = prompt_input(
                        stdscr,
                        t("download_done_prompt", version=ver_id),
                        "y",
                        2,
                    )
                    if ans and ans.lower().startswith("y"):
                        self.active_tab = 0
                        for idx, v in enumerate(self.filtered_versions):
                            if v.id == ver_id:
                                self.selected_version_idx = idx
                                break
                elif self.cancel_download_token and self.cancel_download_token.is_set():
                    show_message_modal(stdscr, t("download_cancelled"), [t("download_cancelled_desc")])
                else:
                    err_msg = self.download_error_msg or "Unknown error"
                    show_message_modal(
                        stdscr,
                        t("download_failed_title"),
                        [t("download_failed_desc", version=ver_id), "", err_msg],
                    )

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
            elif self.active_tab == 4:
                installed_ids = {v.id for v in self.all_versions}
                render_download_view(
                    stdscr,
                    self.filtered_remote_versions,
                    self.selected_remote_idx,
                    self.remote_filter_text,
                    self.show_snapshots,
                    self.config,
                    installed_ids,
                    self.manifest_loading,
                    self.manifest_error,
                    top_y,
                    bottom_y,
                )
            elif self.active_tab == 5:
                render_about_view(stdscr, top_y, bottom_y)

            # Overlay active download progress modal
            if self.is_downloading:
                render_download_progress_modal(
                    stdscr,
                    self.download_progress,
                    self.last_downloaded_version,
                )

            stdscr.refresh()

            # Handle user keystroke
            ch = stdscr.getch()
            if ch == -1:
                continue

            # If downloading, only allow cancelling with Esc or 'q'
            if self.is_downloading:
                if ch in (27, ord("q"), ord("Q")):
                    if self.cancel_download_token:
                        self.cancel_download_token.set()
                continue

            # Global keys
            if ch in (ord("q"), ord("Q")):
                # If game is running, confirm quit
                if self.launcher.current_process and self.launcher.current_process.is_running:
                    ans = prompt_input(stdscr, t("mc_running_quit"), "n", 2)
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
            elif ch == ord("5"):
                self.active_tab = 4
                if not self.manifest_loaded:
                    self.load_manifest_async()
            elif ch == ord("6"):
                self.active_tab = 5
            elif ch in (ord("\t"),):  # Tab key cycles tabs
                self.active_tab = (self.active_tab + 1) % 6
                if self.active_tab == 4 and not self.manifest_loaded:
                    self.load_manifest_async()
            elif self.active_tab == 0:
                if ch in (ord("d"), ord("D")):
                    self.active_tab = 4
                    if not self.manifest_loaded:
                        self.load_manifest_async()
                else:
                    self._handle_versions_input(stdscr, ch)
            elif self.active_tab == 1:
                self._handle_settings_input(stdscr, ch)
            elif self.active_tab == 2:
                self._handle_console_input(stdscr, ch)
            elif self.active_tab == 3:
                self._handle_dir_input(stdscr, ch)
            elif self.active_tab == 4:
                self._handle_download_input(stdscr, ch)

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
            query = prompt_input(stdscr, t("filter_prompt"), self.filter_text)
            if query is not None:
                self.filter_text = query
                self.apply_filter()
        elif ch in (ord("r"), ord("R")):
            self.refresh_versions()
            show_message_modal(stdscr, t("refresh_complete"), [t("refresh_found", count=len(self.all_versions))])
        elif ch in (curses.KEY_ENTER, 10, 13):
            self._launch_selected_version(stdscr)
        elif ch in (ord("p"), ord("P")):
            self._preview_command(stdscr)

    def _launch_selected_version(self, stdscr: curses.window) -> None:
        if not self.filtered_versions:
            show_message_modal(stdscr, t("no_version_sel"), [t("no_version_sel_desc")])
            return

        cur_v = self.filtered_versions[self.selected_version_idx]

        try:
            self.launcher.launch(cur_v)
            # Switch to console view
            self.active_tab = 2
            self.auto_scroll = True
        except Exception as e:
            show_message_modal(stdscr, t("launch_error"), [t("launch_failed", version=cur_v.id), "", str(e)])

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
            show_message_modal(stdscr, t("preview_cmd_title", version=cur_v.id), cmd_lines)
        except Exception as e:
            show_message_modal(stdscr, t("preview_error"), [str(e)])

    def _handle_settings_input(self, stdscr: curses.window, ch: int) -> None:
        total_fields = len(build_settings_fields(self.config))
        if ch in (curses.KEY_UP, ord("k")):
            self.selected_setting_idx = (self.selected_setting_idx - 1) % total_fields
        elif ch in (curses.KEY_DOWN, ord("j")):
            self.selected_setting_idx = (self.selected_setting_idx + 1) % total_fields
        elif ch == curses.KEY_PPAGE:
            self.selected_setting_idx = max(0, self.selected_setting_idx - 5)
        elif ch == curses.KEY_NPAGE:
            self.selected_setting_idx = min(total_fields - 1, self.selected_setting_idx + 5)
        elif ch in (curses.KEY_ENTER, 10, 13):
            self._edit_setting_field(stdscr, self.selected_setting_idx)
        elif ch in (ord("s"), ord("S")):
            self.config.save()
            show_message_modal(stdscr, t("config_saved"), [t("config_saved_desc")])
        elif ch in (ord("r"), ord("R")):
            ans = prompt_input(stdscr, t("reset_defaults_prompt"), "n", 2)
            if ans and ans.lower().startswith("y"):
                self.config.data = dict(DEFAULT_CONFIG)
                self.config.save()
                set_language(self.config.language)
                init_colors(self.config)
                self.refresh_versions()
                show_message_modal(stdscr, t("reset_complete"), [t("reset_complete_desc")])

    def _edit_setting_field(self, stdscr: curses.window, idx: int) -> None:
        fields = build_settings_fields(self.config)
        if idx < 0 or idx >= len(fields):
            return
        action = fields[idx][0]

        if action.startswith("jre:"):
            try:
                major = int(action.split(":", 1)[1])
            except ValueError:
                return
            self._install_jre(stdscr, major)
        elif action == "username":
            val = prompt_input(stdscr, t("prompt_username"), self.config.username, 32)
            if val is not None and val.strip():
                self.config.username = val.strip()
        elif action == "min_ram":
            val = prompt_input(stdscr, t("prompt_min_ram"), self.config.min_ram, 10)
            if val is not None and val.strip():
                self.config.min_ram = val.strip()
        elif action == "max_ram":
            val = prompt_input(stdscr, t("prompt_max_ram"), self.config.max_ram, 10)
            if val is not None and val.strip():
                self.config.max_ram = val.strip()
        elif action == "java_path":
            val = prompt_input(stdscr, t("prompt_java_path"), self.config.java_path, 80)
            if val is not None:
                self.config.java_path = val.strip()
        elif action == "game_dir":
            val = prompt_input(stdscr, t("prompt_game_dir"), str(self.config.game_dir), 80)
            if val is not None and val.strip():
                self.config.game_dir = val.strip()
                self.downloader.game_dir = self.config.game_dir
                self.refresh_versions()
                self.refresh_dir_candidates()
        elif action == "jvm_flags":
            val = prompt_input(stdscr, t("prompt_jvm_flags"), self.config.custom_jvm_args, 80)
            if val is not None:
                self.config.custom_jvm_args = val.strip()
        elif action == "win_w":
            val = prompt_input(stdscr, t("prompt_win_w"), str(self.config.get("window_width", 854)), 8)
            if val is not None and val.isdigit():
                self.config.set("window_width", int(val))
        elif action == "win_h":
            val = prompt_input(stdscr, t("prompt_win_h"), str(self.config.get("window_height", 480)), 8)
            if val is not None and val.isdigit():
                self.config.set("window_height", int(val))
        elif action == "mirror":
            curr = self.config.download_mirror
            suggested = "bmclapi" if curr == "official" else "official"
            val = prompt_input(stdscr, t("prompt_mirror"), suggested, 20)
            if val is not None and val.strip():
                choice = val.strip().lower()
                if choice in ("official", "bmclapi"):
                    self.config.download_mirror = choice
                    self.downloader.mirror = choice
                    self.load_manifest_async(force_refresh=True)
        elif action == "assets":
            self.config.download_assets = not self.config.download_assets
        elif action == "threads":
            val = prompt_input(stdscr, t("prompt_threads"), str(self.config.download_threads), 4)
            if val is not None and val.strip().isdigit():
                self.config.download_threads = int(val.strip())
        elif action == "language":
            curr = self.config.language
            suggested = "zh_CN" if curr == "en" else ("en" if curr == "zh_CN" else "zh_CN")
            val = prompt_input(stdscr, t("prompt_language"), suggested, 15)
            if val is not None and val.strip():
                choice = val.strip()
                if choice in ("auto", "zh_CN", "en"):
                    self.config.language = choice
                    set_language(choice)
        elif action == "theme":
            self.config.set("theme", next_choice(THEME_NAMES, get_theme_name(self.config)))
            init_colors(self.config)
        elif action == "accent_color":
            self.config.set("accent_color", next_choice(ACCENT_CHOICES, get_accent_choice(self.config)))
            init_colors(self.config)
        elif action == "header_style":
            self.config.set("header_style", next_choice(HEADER_STYLES, get_header_style(self.config)))
            init_colors(self.config)
        elif action == "selection_style":
            self.config.set("selection_style", next_choice(SELECTION_STYLES, get_selection_style(self.config)))
            init_colors(self.config)

    def _install_jre(self, stdscr: curses.window, major: int) -> None:
        """Install a JRE through apt, temporarily suspending the curses UI."""
        answer = prompt_input(stdscr, t("jre_confirm_prompt", version=major), "", 2)
        if not answer or not answer.strip().lower().startswith("y"):
            return

        command = get_install_command(major)
        if command is None:
            show_message_modal(stdscr, t("jre_install_title"), [t("jre_unavailable")])
            return

        ok = False
        code = -1
        curses.def_prog_mode()
        curses.endwin()
        try:
            print()
            print(t("jre_installing", cmd=format_command(command)))
            print(t("jre_install_hint"))
            print()
            ok, code = install_jre(major)
            print()
            if ok:
                print(t("jre_install_success", version=major))
            else:
                print(t("jre_install_failed", code=code))
                print(t("jre_install_retry_hint"))
            print(t("jre_install_done"))
            try:
                input()
            except (EOFError, KeyboardInterrupt):
                pass
        except Exception as exc:  # keep the TUI alive if apt/terminal handling fails
            print(t("jre_install_failed", code=code))
            print(str(exc))
        finally:
            curses.reset_prog_mode()
            stdscr.erase()
            stdscr.refresh()

        if ok:
            refresh_detection()
            show_message_modal(
                stdscr,
                t("jre_install_title"),
                [t("jre_install_success", version=major)],
            )
        else:
            show_message_modal(
                stdscr,
                t("jre_install_title"),
                [t("jre_install_failed", code=code), "", t("jre_install_retry_hint")],
            )

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
                ans = prompt_input(stdscr, t("terminate_prompt"), "n", 2)
                if ans and ans.lower().startswith("y"):
                    proc.stop()
                    show_message_modal(stdscr, t("proc_stopped"), [t("proc_stopped_desc")])
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
                self.downloader.game_dir = chosen_path
                self.refresh_versions()
                self.refresh_dir_candidates()
                show_message_modal(stdscr, t("dir_changed"), [t("dir_set_to"), str(chosen_path)])
                self.active_tab = 0  # switch back to versions
        elif ch in (ord("e"), ord("E")):
            new_path = prompt_input(stdscr, t("prompt_custom_dir"), str(self.config.game_dir), 80)
            if new_path and new_path.strip():
                p = Path(os.path.expanduser(new_path.strip()))
                self.config.game_dir = p
                self.downloader.game_dir = p
                self.refresh_versions()
                self.refresh_dir_candidates()
                show_message_modal(stdscr, t("dir_changed"), [t("dir_set_to"), str(p)])
                self.active_tab = 0

    def _handle_download_input(self, stdscr: curses.window, ch: int) -> None:
        count = len(self.filtered_remote_versions)
        if ch in (curses.KEY_UP, ord("k")):
            if count > 0:
                self.selected_remote_idx = (self.selected_remote_idx - 1) % count
        elif ch in (curses.KEY_DOWN, ord("j")):
            if count > 0:
                self.selected_remote_idx = (self.selected_remote_idx + 1) % count
        elif ch in (curses.KEY_PPAGE,):  # Page Up
            self.selected_remote_idx = max(0, self.selected_remote_idx - 10)
        elif ch in (curses.KEY_NPAGE,):  # Page Down
            if count > 0:
                self.selected_remote_idx = min(count - 1, self.selected_remote_idx + 10)
        elif ch == ord("/"):
            query = prompt_input(stdscr, t("prompt_remote_filter"), self.remote_filter_text, 40)
            if query is not None:
                self.remote_filter_text = query
                self.apply_remote_filter(select_best=True)
        elif ch == 27:  # Esc clears the search
            if self.remote_filter_text:
                self.remote_filter_text = ""
                self.apply_remote_filter()
        elif ch in (ord("s"), ord("S")):
            self.show_snapshots = not self.show_snapshots
            self.apply_remote_filter()
        elif ch in (ord("a"), ord("A")):
            self.config.download_assets = not self.config.download_assets
        elif ch in (ord("r"), ord("R")):
            self.load_manifest_async(force_refresh=True)
            show_message_modal(stdscr, t("refreshing_manifest_title"), [t("refreshing_manifest_desc")])
        elif ch in (curses.KEY_ENTER, 10, 13):
            self.start_download_selected(stdscr)


def main() -> None:
    app = MCTuiApp()
    try:
        curses.wrapper(app.run)
    except KeyboardInterrupt:
        pass

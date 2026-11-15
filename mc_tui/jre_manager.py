"""Install Minecraft-friendly OpenJDK runtimes through apt.

The launcher itself only requires Python.  Java runtimes are an optional
runtime dependency: when none is installed the user can trigger an apt
installation from the Settings tab.  We deliberately do not depend on any
specific JRE package at the packaging level.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from typing import List, Optional, Tuple

# Java versions commonly required by Minecraft releases / mod loaders.
JRE_VERSIONS: Tuple[int, ...] = (8, 17, 21, 25)


def package_name(major: int) -> str:
    """Return the Debian/Ubuntu package that provides the given Java major."""
    return f"openjdk-{major}-jre"


def get_install_command(major: int) -> Optional[List[str]]:
    """Build the apt-get command used to install a JRE.

    Returns ``None`` when apt-get is unavailable, or when the process is not
    root and neither sudo nor pkexec can escalate privileges.
    """
    if shutil.which("apt-get") is None:
        return None

    command = ["apt-get", "install", "-y", package_name(major)]

    try:
        if os.geteuid() == 0:
            return command
    except AttributeError:  # pragma: no cover - Windows
        pass

    if shutil.which("sudo"):
        return ["sudo", *command]
    if shutil.which("pkexec"):
        return ["pkexec", *command]
    return None


def format_command(command: List[str]) -> str:
    """Return a shell-like display string for a command argument list."""
    return " ".join(command)


def install_jre(major: int) -> Tuple[bool, int]:
    """Run apt-get for ``major`` and return ``(succeeded, exit_code)``.

    The caller must suspend curses first so that the package manager can use
    the terminal (sudo password prompt, apt output).  A user cancellation is
    reported as ``(False, -1)``.
    """
    command = get_install_command(major)
    if command is None:
        return False, -1

    try:
        code = subprocess.call(command)
    except KeyboardInterrupt:
        return False, -1
    except OSError:
        return False, -1
    return code == 0, code


@lru_cache(maxsize=1)
def installed_majors() -> Tuple[int, ...]:
    """Detected Java major versions, cached until :func:`refresh_detection`."""
    from mc_tui.java_detector import detect_all_javas

    try:
        return tuple(sorted({info.major_version for info in detect_all_javas()}))
    except Exception:
        return ()


def refresh_detection() -> None:
    """Forget cached Java detection results (e.g. after installing a JRE)."""
    installed_majors.cache_clear()

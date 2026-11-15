"""Theme presets and configurable colors for the curses UI.

The launcher keeps a small number of logical color pairs (accent, success,
warning, ...).  A theme maps those roles to terminal colors; the user can pick
a preset in Settings and optionally override the main accent color, the header
bar style and the selection style.
"""
from __future__ import annotations

import curses
from typing import Any, Dict, Optional, Tuple

from mc_tui.i18n import t


class Colors:
    NORMAL = 1
    ACCENT = 2
    SUCCESS = 3
    WARNING = 4
    DANGER = 5
    MUTED = 6
    HIGHLIGHT = 7
    HEADER = 8


THEME_NAMES: Tuple[str, ...] = ("classic", "ocean", "forest", "sunset", "mono", "neon", "paper")

ACCENT_CHOICES: Tuple[str, ...] = (
    "auto",
    "black",
    "red",
    "green",
    "yellow",
    "blue",
    "magenta",
    "cyan",
    "white",
)

HEADER_STYLES: Tuple[str, ...] = ("auto", "accent", "plain")
SELECTION_STYLES: Tuple[str, ...] = ("solid", "bold")

# Roles: normal, accent, success, warning, danger, muted, header_fg, header_bg.
THEME_PRESETS: Dict[str, Dict[str, str]] = {
    "classic": {
        "normal": "white",
        "accent": "cyan",
        "success": "green",
        "warning": "yellow",
        "danger": "red",
        "muted": "gray",
        "header_fg": "black",
        "header_bg": "white",
    },
    "ocean": {
        "normal": "white",
        "accent": "blue",
        "success": "cyan",
        "warning": "yellow",
        "danger": "red",
        "muted": "gray",
        "header_fg": "white",
        "header_bg": "blue",
    },
    "forest": {
        "normal": "white",
        "accent": "green",
        "success": "green",
        "warning": "yellow",
        "danger": "red",
        "muted": "gray",
        "header_fg": "black",
        "header_bg": "green",
    },
    "sunset": {
        "normal": "white",
        "accent": "magenta",
        "success": "green",
        "warning": "yellow",
        "danger": "red",
        "muted": "gray",
        "header_fg": "black",
        "header_bg": "magenta",
    },
    "mono": {
        "normal": "white",
        "accent": "white",
        "success": "white",
        "warning": "white",
        "danger": "white",
        "muted": "gray",
        "header_fg": "black",
        "header_bg": "white",
    },
    "neon": {
        "normal": "white",
        "accent": "magenta",
        "success": "green",
        "warning": "yellow",
        "danger": "red",
        "muted": "gray",
        "header_fg": "black",
        "header_bg": "cyan",
    },
    "paper": {
        # For terminals with a light background.
        "normal": "black",
        "accent": "blue",
        "success": "green",
        "warning": "magenta",
        "danger": "red",
        "muted": "gray",
        "header_fg": "white",
        "header_bg": "blue",
    },
}

COLOR_NAMES: Dict[str, int] = {
    "black": curses.COLOR_BLACK,
    "red": curses.COLOR_RED,
    "green": curses.COLOR_GREEN,
    "yellow": curses.COLOR_YELLOW,
    "blue": curses.COLOR_BLUE,
    "magenta": curses.COLOR_MAGENTA,
    "cyan": curses.COLOR_CYAN,
    "white": curses.COLOR_WHITE,
}

# Background colors that need dark text for readability.
_LIGHT_BACKGROUNDS = {
    curses.COLOR_BLACK,
    curses.COLOR_CYAN,
    curses.COLOR_GREEN,
    curses.COLOR_YELLOW,
    curses.COLOR_WHITE,
}


def _config_get(config: Any, key: str, default: str) -> str:
    if config is None:
        return default
    try:
        value = config.get(key, default)
    except TypeError:
        value = config.get(key)
    except Exception:
        return default
    return default if value is None else str(value)


def _choice(value: str, options: Tuple[str, ...], default: str) -> str:
    return value if value in options else default


def get_theme_name(config: Any = None) -> str:
    return _choice(_config_get(config, "theme", "classic"), THEME_NAMES, "classic")


def get_accent_choice(config: Any = None) -> str:
    return _choice(_config_get(config, "accent_color", "auto"), ACCENT_CHOICES, "auto")


def get_header_style(config: Any = None) -> str:
    return _choice(_config_get(config, "header_style", "auto"), HEADER_STYLES, "auto")


def get_selection_style(config: Any = None) -> str:
    return _choice(_config_get(config, "selection_style", "solid"), SELECTION_STYLES, "solid")


def _label(prefix: str, value: str) -> str:
    key = f"{prefix}_{value}"
    text = t(key)
    return value if text == key else text


def theme_label(value: str) -> str:
    return _label("theme", _choice(value, THEME_NAMES, "classic"))


def accent_label(value: str) -> str:
    return _label("color", _choice(value, ACCENT_CHOICES, "auto"))


def header_style_label(value: str) -> str:
    return _label("header", _choice(value, HEADER_STYLES, "auto"))


def selection_style_label(value: str) -> str:
    return _label("selection", _choice(value, SELECTION_STYLES, "solid"))


def next_choice(options: Tuple[str, ...], current: str) -> str:
    """Return the option after ``current``, wrapping around."""
    try:
        index = options.index(current)
    except ValueError:
        index = -1
    return options[(index + 1) % len(options)]


def _resolve(name: str, color_count: int) -> int:
    if name == "gray":
        return curses.COLOR_BLACK + 8 if color_count >= 16 else curses.COLOR_WHITE
    return COLOR_NAMES.get(name, curses.COLOR_WHITE)


def _contrast(color: int) -> int:
    return curses.COLOR_BLACK if color in _LIGHT_BACKGROUNDS else curses.COLOR_WHITE


def build_pairs(
    config: Any = None,
    color_count: Optional[int] = None,
) -> Dict[int, Tuple[int, Optional[int]]]:
    """Build logical color pair specs from config.

    Returns ``{pair_id: (foreground, background)}`` where ``background=None``
    means the terminal's default background.
    """
    count = color_count if color_count is not None else getattr(curses, "COLORS", 8) or 8
    preset = THEME_PRESETS[get_theme_name(config)]

    accent_choice = get_accent_choice(config)
    accent_name = preset["accent"] if accent_choice == "auto" else accent_choice
    accent = _resolve(accent_name, count)

    header_style = get_header_style(config)
    if header_style == "accent":
        header = (_contrast(accent), accent)
    elif header_style == "plain":
        header = (_resolve(preset["normal"], count), None)
    else:
        header = (
            _resolve(preset["header_fg"], count),
            _resolve(preset["header_bg"], count),
        )

    if get_selection_style(config) == "bold":
        highlight = (accent, None)
    else:
        highlight = (_contrast(accent), accent)

    return {
        Colors.NORMAL: (_resolve(preset["normal"], count), None),
        Colors.ACCENT: (accent, None),
        Colors.SUCCESS: (_resolve(preset["success"], count), None),
        Colors.WARNING: (_resolve(preset["warning"], count), None),
        Colors.DANGER: (_resolve(preset["danger"], count), None),
        Colors.MUTED: (_resolve(preset["muted"], count), None),
        Colors.HIGHLIGHT: highlight,
        Colors.HEADER: header,
    }


def apply_theme(config: Any = None) -> None:
    """(Re)initialize curses color pairs for the configured theme."""
    if not curses.has_colors():
        return

    try:
        curses.start_color()
    except curses.error:
        pass

    default_background = False
    try:
        curses.use_default_colors()
        default_background = True
    except curses.error:
        pass

    for pair, (foreground, background) in build_pairs(config, curses.COLORS).items():
        if background is None:
            background = -1 if default_background else curses.COLOR_BLACK
        try:
            curses.init_pair(pair, foreground, background)
        except curses.error:
            # Keep the terminal default (pair 0) if this color is unsupported.
            pass

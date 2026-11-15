"""Tests for theme preset and color-pair resolution."""
from __future__ import annotations

import curses
import unittest

from mc_tui import i18n, theme
from mc_tui.theme import Colors, build_pairs, next_choice


class TestThemeResolution(unittest.TestCase):
    def pairs(self, config):
        return build_pairs(config, color_count=16)

    def test_classic_defaults(self):
        pairs = self.pairs({"theme": "classic"})
        self.assertEqual(pairs[Colors.NORMAL], (curses.COLOR_WHITE, None))
        self.assertEqual(pairs[Colors.ACCENT], (curses.COLOR_CYAN, None))
        self.assertEqual(pairs[Colors.HIGHLIGHT], (curses.COLOR_BLACK, curses.COLOR_CYAN))
        self.assertEqual(pairs[Colors.HEADER], (curses.COLOR_BLACK, curses.COLOR_WHITE))
        self.assertEqual(pairs[Colors.MUTED], (curses.COLOR_BLACK + 8, None))

    def test_ocean_preset(self):
        pairs = self.pairs({"theme": "ocean"})
        self.assertEqual(pairs[Colors.ACCENT], (curses.COLOR_BLUE, None))
        self.assertEqual(pairs[Colors.HIGHLIGHT], (curses.COLOR_WHITE, curses.COLOR_BLUE))
        self.assertEqual(pairs[Colors.HEADER], (curses.COLOR_WHITE, curses.COLOR_BLUE))

    def test_paper_preset_for_light_terminals(self):
        pairs = self.pairs({"theme": "paper"})
        self.assertEqual(pairs[Colors.NORMAL], (curses.COLOR_BLACK, None))
        self.assertEqual(pairs[Colors.ACCENT], (curses.COLOR_BLUE, None))
        self.assertEqual(pairs[Colors.HEADER], (curses.COLOR_WHITE, curses.COLOR_BLUE))

    def test_accent_override_updates_selection(self):
        pairs = self.pairs({"theme": "classic", "accent_color": "red"})
        self.assertEqual(pairs[Colors.ACCENT], (curses.COLOR_RED, None))
        self.assertEqual(pairs[Colors.HIGHLIGHT], (curses.COLOR_WHITE, curses.COLOR_RED))

    def test_header_accent_style(self):
        pairs = self.pairs({"theme": "classic", "accent_color": "green", "header_style": "accent"})
        self.assertEqual(pairs[Colors.HEADER], (curses.COLOR_BLACK, curses.COLOR_GREEN))

    def test_header_plain_style(self):
        pairs = self.pairs({"theme": "ocean", "header_style": "plain"})
        self.assertEqual(pairs[Colors.HEADER], (curses.COLOR_WHITE, None))

    def test_bold_selection_style(self):
        pairs = self.pairs({"theme": "classic", "accent_color": "yellow", "selection_style": "bold"})
        self.assertEqual(pairs[Colors.HIGHLIGHT], (curses.COLOR_YELLOW, None))

    def test_invalid_values_fall_back(self):
        self.assertEqual(theme.get_theme_name({"theme": "does-not-exist"}), "classic")
        self.assertEqual(theme.get_accent_choice({"accent_color": "nope"}), "auto")
        self.assertEqual(theme.get_header_style({"header_style": "nope"}), "auto")
        self.assertEqual(theme.get_selection_style({"selection_style": "nope"}), "solid")
        pairs = self.pairs({"theme": "does-not-exist", "accent_color": "nope"})
        self.assertEqual(pairs[Colors.ACCENT], (curses.COLOR_CYAN, None))

    def test_next_choice_wraps(self):
        self.assertEqual(next_choice(theme.THEME_NAMES, "classic"), "ocean")
        self.assertEqual(next_choice(theme.THEME_NAMES, theme.THEME_NAMES[-1]), "classic")
        self.assertEqual(next_choice(theme.THEME_NAMES, "unknown"), "classic")

    def test_labels_follow_language(self):
        previous = i18n.get_language()
        try:
            i18n.set_language("en")
            self.assertEqual(theme.theme_label("ocean"), "Ocean")
            self.assertEqual(theme.accent_label("auto"), "Auto (theme)")
            i18n.set_language("zh_CN")
            self.assertEqual(theme.theme_label("ocean"), "海洋")
            self.assertEqual(theme.accent_label("cyan"), "青色")
        finally:
            i18n.set_language(previous)


if __name__ == "__main__":
    unittest.main()

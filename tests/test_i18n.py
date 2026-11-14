"""Unit tests for internationalization and wide character handling."""
from __future__ import annotations

import unittest
from mc_tui.i18n import get_language, set_language, t
from mc_tui.tui.ui_helpers import char_width, pad_str, str_width, truncate_str


class TestI18n(unittest.TestCase):
    def setUp(self) -> None:
        self.orig_lang = get_language()

    def tearDown(self) -> None:
        set_language(self.orig_lang)

    def test_set_and_get_language(self) -> None:
        set_language("zh_CN")
        self.assertEqual(get_language(), "zh_CN")
        self.assertEqual(t("tab_versions"), "1: 版本列表")

        set_language("en")
        self.assertEqual(get_language(), "en")
        self.assertEqual(t("tab_versions"), "1: Versions")

    def test_translations_fallback(self) -> None:
        set_language("en")
        val_en = t("title")
        self.assertIn("MC-TUI", val_en)

        set_language("zh_CN")
        val_zh = t("title")
        self.assertIn("MC-TUI", val_zh)
        self.assertIn("启动器", val_zh)

    def test_string_formatting(self) -> None:
        set_language("zh_CN")
        res = t("box_installed_versions", count=5)
        self.assertEqual(res, "已安装版本 (5)")

        set_language("en")
        res_en = t("box_installed_versions", count=5)
        self.assertEqual(res_en, "Installed Versions (5)")

    def test_cjk_char_and_str_width(self) -> None:
        self.assertEqual(char_width("a"), 1)
        self.assertEqual(char_width("中"), 2)
        self.assertEqual(char_width("文"), 2)

        self.assertEqual(str_width("Hello"), 5)
        self.assertEqual(str_width("你好世界"), 8)
        self.assertEqual(str_width("Hello 世界"), 10)

    def test_cjk_truncate_and_pad(self) -> None:
        text = "你好世界"
        # max_width 5 should take '你好' (4 cols) and stop before '世' (which would make it 6)
        self.assertEqual(truncate_str(text, 5), "你好")
        self.assertEqual(str_width(truncate_str(text, 5)), 4)

        padded = pad_str("中文", 10)
        self.assertEqual(str_width(padded), 10)
        self.assertTrue(padded.startswith("中文"))

        centered = pad_str("中文", 10, align="center")
        self.assertEqual(str_width(centered), 10)


if __name__ == "__main__":
    unittest.main()

"""Tests for mouse hit-testing helpers."""
import unittest

from mc_tui.tui.mouse import (
    button_hit,
    dir_index_at,
    download_index_at,
    settings_index_at,
    tab_index_at,
    version_index_at,
)


class TestMouseHitTesting(unittest.TestCase):
    def test_tab_index(self):
        tabs = ["1: Versions", "2: Settings"]
        self.assertEqual(tab_index_at(2, tabs), 0)
        self.assertEqual(tab_index_at(16, tabs), 0)
        self.assertIsNone(tab_index_at(17, tabs))
        self.assertEqual(tab_index_at(18, tabs), 1)
        self.assertIsNone(tab_index_at(33, tabs))

    def test_version_rows(self):
        self.assertEqual(
            version_index_at(5, 5, 100, 4, 31, False, 100, 0),
            0,
        )
        self.assertEqual(
            version_index_at(29, 5, 100, 4, 31, False, 100, 0),
            24,
        )
        self.assertIsNone(version_index_at(30, 5, 100, 4, 31, False, 100, 0))

        # Scrolled list: selected row 30 puts row 6 at the top.
        self.assertEqual(
            version_index_at(5, 5, 100, 4, 31, False, 100, 30),
            6,
        )
        self.assertEqual(
            version_index_at(29, 5, 100, 4, 31, False, 100, 30),
            30,
        )

        # Filter mode shifts the list down one row.
        self.assertEqual(
            version_index_at(6, 5, 100, 4, 31, True, 100, 0),
            0,
        )
        self.assertIsNone(version_index_at(5, 5, 100, 4, 31, True, 100, 0))

    def test_version_requires_left_pane(self):
        self.assertIsNone(version_index_at(5, 60, 100, 4, 31, False, 100, 0))
        self.assertIsNone(version_index_at(5, 5, 20, 4, 31, False, 100, 0))

    def test_settings_rows(self):
        self.assertEqual(settings_index_at(6, 4, 31, 20, 0), 0)
        self.assertEqual(settings_index_at(7, 4, 31, 20, 0), 0)  # description line
        self.assertEqual(settings_index_at(26, 4, 31, 20, 0), 10)
        self.assertIsNone(settings_index_at(28, 4, 31, 20, 0))
        self.assertIsNone(settings_index_at(5, 4, 31, 20, 0))
        self.assertIsNone(settings_index_at(6, 4, 31, 0, 0))

        # Scrolled to the last page.
        self.assertEqual(settings_index_at(6, 4, 31, 20, 15), 5)
        self.assertEqual(settings_index_at(26, 4, 31, 20, 15), 15)

    def test_download_rows(self):
        self.assertEqual(download_index_at(6, 5, 100, 4, 31, 923, 0), 0)
        self.assertEqual(download_index_at(29, 5, 100, 4, 31, 923, 0), 23)
        self.assertIsNone(download_index_at(30, 5, 100, 4, 31, 923, 0))
        self.assertEqual(download_index_at(6, 5, 100, 4, 31, 923, 30), 7)
        self.assertIsNone(download_index_at(6, 60, 100, 4, 31, 923, 0))

    def test_dir_rows(self):
        self.assertEqual(dir_index_at(10, 4, 31, 20), 0)
        self.assertEqual(dir_index_at(28, 4, 31, 20), 18)
        self.assertIsNone(dir_index_at(29, 4, 31, 20))
        self.assertIsNone(dir_index_at(9, 4, 31, 20))

    def test_button_hit(self):
        label = " LAUNCH "
        self.assertTrue(button_hit(60, 20, 20, 60, label))
        self.assertTrue(button_hit(60 + len(label) - 1, 20, 20, 60, label))
        self.assertFalse(button_hit(60 + len(label), 20, 20, 60, label))
        self.assertFalse(button_hit(60, 21, 20, 60, label))


if __name__ == "__main__":
    unittest.main()

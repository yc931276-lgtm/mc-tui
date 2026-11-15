"""Tests for download-page version search helpers."""
from __future__ import annotations

import unittest

from mc_tui.downloader import RemoteVersion
from mc_tui.tui.version_filter import (
    best_match_index,
    filter_versions,
    normalize_query,
)


def _version(version_id: str, version_type: str = "release") -> RemoteVersion:
    return RemoteVersion(id=version_id, type=version_type, url="")


VERSIONS = [
    _version("1.21.4"),
    _version("1.20.6"),
    _version("1.20.5"),
    _version("1.20.4"),
    _version("1.20.4-rc1", "snapshot"),
    _version("24w14a", "snapshot"),
    _version("b1.8.1", "old_beta"),
]


class TestVersionFilter(unittest.TestCase):
    def test_normalize_query(self):
        self.assertEqual(normalize_query("  V1.20.4 "), "1.20.4")
        self.assertEqual(normalize_query(None), "")
        self.assertEqual(normalize_query("1.20.4"), "1.20.4")

    def test_release_only_filter(self):
        result = filter_versions(VERSIONS, "", include_snapshots=False)
        self.assertEqual([v.id for v in result], ["1.21.4", "1.20.6", "1.20.5", "1.20.4"])

    def test_search_by_version_id(self):
        result = filter_versions(VERSIONS, "1.20", include_snapshots=False)
        self.assertEqual([v.id for v in result], ["1.20.6", "1.20.5", "1.20.4"])

        result = filter_versions(VERSIONS, "V1.20.4", include_snapshots=False)
        self.assertEqual([v.id for v in result], ["1.20.4"])

        result = filter_versions(VERSIONS, "24w", include_snapshots=True)
        self.assertEqual([v.id for v in result], ["24w14a"])

    def test_snapshots_excluded_by_default(self):
        result = filter_versions(VERSIONS, "24w", include_snapshots=False)
        self.assertEqual(result, [])

    def test_best_match_prefers_exact_id(self):
        releases = filter_versions(VERSIONS, "1.20", include_snapshots=False)
        self.assertEqual(releases[best_match_index(releases, "1.20")].id, "1.20.6")

        all_versions = filter_versions(VERSIONS, "", include_snapshots=True)
        self.assertEqual(
            all_versions[best_match_index(all_versions, "1.20.4")].id,
            "1.20.4",
        )
        self.assertEqual(
            all_versions[best_match_index(all_versions, "v1.20.4-rc1")].id,
            "1.20.4-rc1",
        )

    def test_best_match_fallback(self):
        all_versions = filter_versions(VERSIONS, "", include_snapshots=True)
        self.assertEqual(all_versions[best_match_index(all_versions, "20.4")].id, "1.20.4")
        self.assertEqual(best_match_index(all_versions, "does-not-exist"), 0)
        self.assertEqual(best_match_index([], "1.20.4"), 0)


if __name__ == "__main__":
    unittest.main()

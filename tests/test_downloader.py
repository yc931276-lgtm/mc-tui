"""Unit tests for Minecraft vanilla downloader."""
from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from mc_tui.downloader import (
    Downloader,
    DownloadItem,
    DownloadProgress,
    RemoteVersion,
    apply_mirror,
    download_single_file,
    verify_sha1,
)


class TestDownloader(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.game_dir = Path(self.temp_dir.name) / "minecraft"
        self.cache_dir = Path(self.temp_dir.name) / "cache"
        self.downloader = Downloader(self.game_dir, cache_dir=self.cache_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_verify_sha1(self) -> None:
        test_file = self.game_dir / "sample.txt"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        content = b"Hello Minecraft World!"
        test_file.write_bytes(content)
        expected = hashlib.sha1(content).hexdigest()

        self.assertTrue(verify_sha1(test_file, expected))
        self.assertTrue(verify_sha1(test_file, expected.upper()))
        self.assertFalse(verify_sha1(test_file, "wrong_hash"))
        self.assertFalse(verify_sha1(self.game_dir / "nonexistent.txt", expected))

    def test_apply_mirror(self) -> None:
        official_url = "https://piston-meta.mojang.com/v1/packages/123/1.20.4.json"
        self.assertEqual(apply_mirror(official_url, "official"), official_url)

        bmclapi_url = apply_mirror(official_url, "bmclapi")
        self.assertIn("bmclapi2.bangbang93.com", bmclapi_url)
        self.assertNotIn("piston-meta.mojang.com", bmclapi_url)

        lib_url = "https://libraries.minecraft.net/com/mojang/patchy/1.3.9/patchy-1.3.9.jar"
        bmclapi_lib = apply_mirror(lib_url, "bmclapi")
        self.assertEqual(bmclapi_lib, "https://bmclapi2.bangbang93.com/maven/com/mojang/patchy/1.3.9/patchy-1.3.9.jar")

        asset_url = "https://resources.download.minecraft.net/b6/b62ca8ec10d07e6bf5ac8dae0c8c1d2e6a1e3356"
        bmclapi_asset = apply_mirror(asset_url, "bmclapi")
        self.assertEqual(bmclapi_asset, "https://bmclapi2.bangbang93.com/assets/b6/b62ca8ec10d07e6bf5ac8dae0c8c1d2e6a1e3356")

    def test_parse_manifest_data(self) -> None:
        data = {
            "latest": {"release": "1.20.4", "snapshot": "24w14a"},
            "versions": [
                {
                    "id": "1.20.4",
                    "type": "release",
                    "url": "https://piston-meta.mojang.com/1.20.4.json",
                    "releaseTime": "2023-12-07T12:56:20+00:00",
                    "sha1": "abc12345",
                },
                {
                    "id": "24w14a",
                    "type": "snapshot",
                    "url": "https://piston-meta.mojang.com/24w14a.json",
                    "releaseTime": "2024-04-03T14:00:00+00:00",
                    "sha1": "def67890",
                },
                {
                    "id": "b1.8.1",
                    "type": "old_beta",
                    "url": "https://piston-meta.mojang.com/b1.8.1.json",
                    "releaseTime": "2011-09-19T00:00:00+00:00",
                },
            ],
        }

        versions = self.downloader._parse_manifest_data(data)
        self.assertEqual(len(versions), 3)
        self.assertEqual(self.downloader._latest_release, "1.20.4")
        self.assertEqual(self.downloader._latest_snapshot, "24w14a")

        v0 = versions[0]
        self.assertEqual(v0.id, "1.20.4")
        self.assertTrue(v0.is_release)
        self.assertEqual(v0.display_type, "Release")
        self.assertEqual(v0.release_time, "2023-12-07")

        v1 = versions[1]
        self.assertEqual(v1.id, "24w14a")
        self.assertFalse(v1.is_release)
        self.assertEqual(v1.display_type, "Snapshot")

        v2 = versions[2]
        self.assertEqual(v2.display_type, "Old Beta")

    def test_collect_libraries_to_download(self) -> None:
        v_data = {
            "libraries": [
                {
                    "name": "com.mojang:patchy:1.3.9",
                    "downloads": {
                        "artifact": {
                            "path": "com/mojang/patchy/1.3.9/patchy-1.3.9.jar",
                            "sha1": "abcdef123456",
                            "size": 1234,
                            "url": "https://libraries.minecraft.net/com/mojang/patchy/1.3.9/patchy-1.3.9.jar",
                        }
                    },
                },
                {
                    # Windows-only lib (should be skipped on linux)
                    "name": "net.java.jinput:jinput-platform:2.0.5:natives-windows",
                    "rules": [{"action": "allow", "os": {"name": "windows"}}],
                    "downloads": {
                        "artifact": {
                            "path": "net/java/jinput/jinput-platform/2.0.5/jinput-platform-2.0.5-natives-windows.jar",
                            "url": "https://example.com/win.jar",
                        }
                    },
                },
                {
                    # Linux-only lib (should be included on linux)
                    "name": "org.lwjgl:lwjgl:3.3.2:natives-linux",
                    "rules": [{"action": "allow", "os": {"name": "linux"}}],
                    "downloads": {
                        "artifact": {
                            "path": "org/lwjgl/lwjgl/3.3.2/lwjgl-3.3.2-natives-linux.jar",
                            "sha1": "9876543210",
                            "size": 5678,
                            "url": "https://libraries.minecraft.net/org/lwjgl/lwjgl/3.3.2/lwjgl-3.3.2-natives-linux.jar",
                        }
                    },
                },
                {
                    # Legacy natives classifier dict
                    "name": "org.lwjgl.lwjgl:lwjgl-platform:2.9.4",
                    "natives": {"linux": "natives-linux", "windows": "natives-windows"},
                    "downloads": {
                        "classifiers": {
                            "natives-linux": {
                                "path": "org/lwjgl/lwjgl/lwjgl-platform/2.9.4/lwjgl-platform-2.9.4-natives-linux.jar",
                                "sha1": "linuxnat123",
                                "size": 9000,
                                "url": "https://libraries.minecraft.net/nat-linux.jar",
                            },
                            "natives-windows": {
                                "path": "org/lwjgl/lwjgl/lwjgl-platform/2.9.4/lwjgl-platform-2.9.4-natives-windows.jar",
                                "sha1": "winnat123",
                                "size": 9000,
                                "url": "https://libraries.minecraft.net/nat-win.jar",
                            },
                        }
                    },
                },
            ]
        }

        items = self.downloader.collect_libraries_to_download(v_data, current_os="linux", current_arch="x86_64")
        item_paths = [str(it.target_path.relative_to(self.game_dir / "libraries")) for it in items]

        self.assertIn("com/mojang/patchy/1.3.9/patchy-1.3.9.jar", item_paths)
        self.assertIn("org/lwjgl/lwjgl/3.3.2/lwjgl-3.3.2-natives-linux.jar", item_paths)
        self.assertIn("org/lwjgl/lwjgl/lwjgl-platform/2.9.4/lwjgl-platform-2.9.4-natives-linux.jar", item_paths)
        self.assertNotIn("net/java/jinput/jinput-platform/2.0.5/jinput-platform-2.0.5-natives-windows.jar", item_paths)

    def test_collect_assets_to_download(self) -> None:
        index_data = {
            "objects": {
                "icons/icon_16x16.png": {"hash": "b62ca8ec10d07e6bf5ac8dae0c8c1d2e6a1e3356", "size": 9101},
                "minecraft/sounds/ambient/cave/cave1.ogg": {"hash": "5ff04807c356f1beed0b86ccf659b44b9983e3fa", "size": 781},
            }
        }

        items = self.downloader.collect_assets_to_download(index_data)
        self.assertEqual(len(items), 2)

        it0 = next(it for it in items if "icon_16x16.png" in it.name)
        self.assertEqual(it0.expected_sha1, "b62ca8ec10d07e6bf5ac8dae0c8c1d2e6a1e3356")
        self.assertEqual(it0.expected_size, 9101)
        expected_path = self.game_dir / "assets" / "objects" / "b6" / "b62ca8ec10d07e6bf5ac8dae0c8c1d2e6a1e3356"
        self.assertEqual(it0.target_path, expected_path)
        self.assertIn("/b6/b62ca8ec10d07e6bf5ac8dae0c8c1d2e6a1e3356", it0.url)

    def test_download_single_file_verified_skip(self) -> None:
        dest = self.game_dir / "test.jar"
        dest.parent.mkdir(parents=True, exist_ok=True)
        content = b"Mock client content"
        dest.write_bytes(content)
        sha1 = hashlib.sha1(content).hexdigest()

        # Should skip network request when SHA-1 matches
        res = download_single_file(
            url="http://invalid-url-should-not-be-called.mock",
            dest_path=dest,
            expected_sha1=sha1,
            expected_size=len(content),
        )
        self.assertTrue(res)

    def test_download_single_file_cancellation(self) -> None:
        dest = self.game_dir / "cancel.jar"
        cancel_token = threading.Event()
        cancel_token.set()  # Cancelled before start

        res = download_single_file(
            url="https://example.com/dummy.jar",
            dest_path=dest,
            cancel_token=cancel_token,
        )
        self.assertFalse(res)
        self.assertFalse(dest.exists())

    @patch("mc_tui.downloader.download_single_file")
    def test_download_version_flow(self, mock_download: MagicMock) -> None:
        mock_download.return_value = True

        r_ver = RemoteVersion(
            id="1.20.4",
            type="release",
            url="https://example.com/1.20.4.json",
            sha1="",
        )

        mock_v_json = {
            "id": "1.20.4",
            "type": "release",
            "downloads": {
                "client": {
                    "url": "https://example.com/client.jar",
                    "sha1": "client_sha1",
                    "size": 1000,
                }
            },
            "libraries": [
                {
                    "name": "com.mojang:patchy:1.3.9",
                    "downloads": {
                        "artifact": {
                            "path": "com/mojang/patchy/1.3.9/patchy-1.3.9.jar",
                            "sha1": "lib_sha1",
                            "size": 500,
                            "url": "https://example.com/patchy.jar",
                        }
                    },
                }
            ],
            "assetIndex": {
                "id": "12",
                "sha1": "ai_sha1",
                "size": 200,
                "url": "https://example.com/12.json",
            },
        }

        # Mock methods on downloader
        self.downloader.get_remote_version = MagicMock(return_value=r_ver)
        self.downloader.fetch_version_json = MagicMock(return_value=mock_v_json)

        # Mock asset index read
        def fake_download_single_file(url, dest_path, **kwargs):
            if "12.json" in str(dest_path):
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                dest_path.write_text(json.dumps({"objects": {}}))
            return True

        mock_download.side_effect = fake_download_single_file

        progress_events: list[DownloadProgress] = []
        ok = self.downloader.download_version(
            version_id="1.20.4",
            include_assets=True,
            progress_callback=lambda p: progress_events.append(p),
        )

        self.assertTrue(ok)
        self.assertTrue(any(p.stage == "client_jar" for p in progress_events))
        self.assertTrue(any(p.stage == "libraries" for p in progress_events))
        self.assertTrue(any(p.stage == "complete" for p in progress_events))

        # Check version JSON was written
        json_file = self.game_dir / "versions" / "1.20.4" / "1.20.4.json"
        self.assertTrue(json_file.is_file())


if __name__ == "__main__":
    unittest.main()

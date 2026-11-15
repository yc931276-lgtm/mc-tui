"""Tests for resumable transfers and batched (multi-threaded) downloads."""
from __future__ import annotations

import hashlib
import http.server
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List
from unittest.mock import patch

from mc_tui.downloader import Downloader, DownloadItem, download_single_file

PAYLOAD = bytes(range(256)) * 400  # 102_400 bytes
PAYLOAD_SHA1 = hashlib.sha1(PAYLOAD).hexdigest()


class RangeRequestHandler(http.server.BaseHTTPRequestHandler):
    payload = b""
    support_range = True
    ranges: List[str] = []
    delay = 0.0

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        data = type(self).payload
        if type(self).delay:
            import time

            time.sleep(type(self).delay)

        range_header = self.headers.get("Range")
        type(self).ranges.append(range_header or "")

        if range_header and type(self).support_range and range_header.startswith("bytes="):
            start = int(range_header.split("=", 1)[1].split("-", 1)[0])
            if start >= len(data):
                self.send_response(416)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = data[start:]
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{len(data) - 1}/{len(data)}")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args) -> None:  # silence test output
        pass


class HttpDownloadTest(unittest.TestCase):
    def setUp(self) -> None:
        RangeRequestHandler.payload = PAYLOAD
        RangeRequestHandler.support_range = True
        RangeRequestHandler.ranges = []
        RangeRequestHandler.delay = 0.0
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), RangeRequestHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/file.bin"
        self.tmp = TemporaryDirectory()
        self.dest = Path(self.tmp.name) / "file.bin"
        self.part = self.dest.with_name(self.dest.name + ".part")

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.server_thread.join(timeout=2)
        self.tmp.cleanup()

    def test_complete_partial_is_promoted_without_network(self) -> None:
        self.part.write_bytes(PAYLOAD)
        ok = download_single_file(
            self.url,
            self.dest,
            expected_sha1=PAYLOAD_SHA1,
            expected_size=len(PAYLOAD),
            timeout=5,
        )
        self.assertTrue(ok)
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)
        self.assertFalse(self.part.exists())
        self.assertEqual(RangeRequestHandler.ranges, [])

    def test_resume_sends_range_and_appends(self) -> None:
        prefix = 12345
        self.part.write_bytes(PAYLOAD[:prefix])

        ok = download_single_file(
            self.url,
            self.dest,
            expected_sha1=PAYLOAD_SHA1,
            expected_size=len(PAYLOAD),
            timeout=5,
        )

        self.assertTrue(ok)
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)
        self.assertFalse(self.part.exists())
        self.assertEqual(RangeRequestHandler.ranges, [f"bytes={prefix}-"])

    def test_server_ignoring_range_restarts_cleanly(self) -> None:
        RangeRequestHandler.support_range = False
        self.part.write_bytes(PAYLOAD[:12345])

        ok = download_single_file(
            self.url,
            self.dest,
            expected_sha1=PAYLOAD_SHA1,
            expected_size=len(PAYLOAD),
            timeout=5,
        )

        self.assertTrue(ok)
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)
        self.assertFalse(self.part.exists())

    def test_hash_mismatch_discards_partial(self) -> None:
        ok = download_single_file(
            self.url,
            self.dest,
            expected_sha1="0" * 40,
            expected_size=len(PAYLOAD),
            retries=1,
            timeout=5,
        )
        self.assertFalse(ok)
        self.assertFalse(self.dest.exists())
        self.assertFalse(self.part.exists())

    def test_verify_existing_rejects_same_size_corruption(self) -> None:
        self.dest.write_bytes(b"\x00" * len(PAYLOAD))

        ok = download_single_file(
            self.url,
            self.dest,
            expected_sha1=PAYLOAD_SHA1,
            expected_size=len(PAYLOAD),
            verify_existing=True,
            timeout=5,
        )

        self.assertTrue(ok)
        self.assertEqual(self.dest.read_bytes(), PAYLOAD)

    def test_cancel_keeps_partial_for_next_run(self) -> None:
        self.part.write_bytes(PAYLOAD[:500])
        token = threading.Event()
        token.set()

        ok = download_single_file(
            self.url,
            self.dest,
            expected_sha1=PAYLOAD_SHA1,
            expected_size=len(PAYLOAD),
            cancel_token=token,
            timeout=5,
        )

        self.assertFalse(ok)
        self.assertTrue(self.part.is_file())
        self.assertFalse(self.dest.exists())


class BatchDownloadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.downloader = Downloader(self.root / "minecraft", cache_dir=self.root / "cache")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _item(self, name: str, size: int = 10) -> DownloadItem:
        return DownloadItem(
            url=f"http://example.invalid/{name}",
            target_path=self.root / "files" / name,
            expected_size=size,
            expected_sha1=hashlib.sha1(b"0123456789"[:size]).hexdigest(),
            name=name,
        )

    def test_same_target_is_downloaded_once(self) -> None:
        target = self.root / "files" / "shared.bin"
        items = [
            DownloadItem("http://example.invalid/a", target, expected_size=10, name="a"),
            DownloadItem("http://example.invalid/b", target, expected_size=10, name="b"),
        ]
        calls: List[str] = []

        def fake(url: str, dest_path: Path, **kwargs) -> bool:
            calls.append(url)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(b"0123456789")
            return True

        with patch("mc_tui.downloader.download_single_file", side_effect=fake):
            ok, failed = self.downloader._download_batch(items, "assets", None, None, max_workers=4)

        self.assertTrue(ok)
        self.assertEqual(failed, [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(target.read_bytes(), b"0123456789")

    def test_progress_bytes_are_not_double_counted(self) -> None:
        items = [self._item(f"file{i}.bin") for i in range(3)]
        events = []

        def fake(url: str, dest_path: Path, **kwargs) -> bool:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(b"0123456789")
            return True

        with patch("mc_tui.downloader.download_single_file", side_effect=fake):
            ok, failed = self.downloader._download_batch(
                items, "libraries", events.append, None, max_workers=3
            )

        self.assertTrue(ok)
        self.assertEqual(failed, [])
        self.assertEqual(events[-1].current, 3)
        self.assertEqual(events[-1].bytes_downloaded, 30)
        self.assertTrue(all(e.bytes_downloaded <= 30 for e in events))

    def test_failed_items_are_reported(self) -> None:
        good = self._item("good.bin")
        bad = self._item("bad.bin")

        def fake(url: str, dest_path: Path, **kwargs) -> bool:
            if url.endswith("bad.bin"):
                return False
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(b"0123456789")
            return True

        with patch("mc_tui.downloader.download_single_file", side_effect=fake):
            ok, failed = self.downloader._download_batch(
                [good, bad], "libraries", None, None, max_workers=2
            )

        self.assertFalse(ok)
        self.assertEqual([item.name for item in failed], ["bad.bin"])

    def test_cancel_before_batch_starts(self) -> None:
        token = threading.Event()
        token.set()
        items = [self._item("file.bin")]

        with patch("mc_tui.downloader.download_single_file") as mock_download:
            ok, failed = self.downloader._download_batch(items, "libraries", None, token)

        self.assertFalse(ok)
        self.assertEqual(failed, [])
        mock_download.assert_not_called()


if __name__ == "__main__":
    unittest.main()

"""Minecraft Java Edition (Vanilla) downloader for MC-TUI.

Downloads official Mojang vanilla versions including:
- Version JSON metadata
- Client JAR
- OS-specific and architecture-specific libraries and natives
- Asset indexes and resource objects
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import platform
import shutil
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from mc_tui.config import CONFIG_DIR
from mc_tui.version_parser import (
    evaluate_rules,
    get_current_arch,
    get_current_os,
    maven_to_path,
)

MOJANG_MANIFEST_V2 = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
MOJANG_MANIFEST_FALLBACK = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
BMCLAPI_MANIFEST = "https://bmclapi2.bangbang93.com/mc/game/version_manifest_v2.json"


def apply_mirror(url: str, mirror: str = "official") -> str:
    """Rewrite official Mojang URLs to mirror URLs if mirror is specified."""
    if not url:
        return url
    if mirror == "bmclapi":
        url = url.replace("https://launchermeta.mojang.com", "https://bmclapi2.bangbang93.com")
        url = url.replace("https://piston-meta.mojang.com", "https://bmclapi2.bangbang93.com")
        url = url.replace("https://piston-data.mojang.com", "https://bmclapi2.bangbang93.com")
        url = url.replace("https://libraries.minecraft.net", "https://bmclapi2.bangbang93.com/maven")
        url = url.replace("https://resources.download.minecraft.net", "https://bmclapi2.bangbang93.com/assets")
    return url


def verify_sha1(file_path: Path, expected_sha1: str) -> bool:
    """Verify whether file matches expected SHA-1 hash."""
    if not file_path.is_file():
        return False
    hasher = hashlib.sha1()
    try:
        with open(file_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest().lower() == expected_sha1.lower()
    except Exception:
        return False


@dataclass
class RemoteVersion:
    id: str
    type: str  # 'release', 'snapshot', 'old_beta', 'old_alpha'
    url: str
    time: str = ""
    release_time: str = ""
    sha1: str = ""
    compliance_level: int = 0

    @property
    def is_release(self) -> bool:
        return self.type == "release"

    @property
    def display_type(self) -> str:
        if self.type == "release":
            return "Release"
        elif self.type == "snapshot":
            return "Snapshot"
        elif self.type == "old_beta":
            return "Old Beta"
        elif self.type == "old_alpha":
            return "Old Alpha"
        return self.type.capitalize()


@dataclass
class DownloadProgress:
    stage: str  # 'manifest', 'version_json', 'client_jar', 'libraries', 'assets', 'complete', 'error', 'cancelled'
    message: str = ""
    current: int = 0
    total: int = 0
    bytes_downloaded: int = 0
    total_bytes: int = 0
    current_file: str = ""
    speed: float = 0.0  # bytes / sec
    is_done: bool = False
    error: Optional[str] = None

    @property
    def percent(self) -> float:
        if self.total > 0:
            return min(100.0, (self.current / self.total) * 100.0)
        return 0.0

    @property
    def formatted_bytes(self) -> str:
        cur_str = self._format_size(self.bytes_downloaded)
        if self.total_bytes > 0:
            return f"{cur_str} / {self._format_size(self.total_bytes)}"
        return cur_str

    @property
    def formatted_speed(self) -> str:
        return f"{self._format_size(self.speed)}/s"

    @staticmethod
    def _format_size(num_bytes: float) -> str:
        if num_bytes < 1024:
            return f"{num_bytes:.0f} B"
        elif num_bytes < 1024 * 1024:
            return f"{num_bytes / 1024:.1f} KB"
        elif num_bytes < 1024 * 1024 * 1024:
            return f"{num_bytes / (1024 * 1024):.1f} MB"
        return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


@dataclass
class DownloadItem:
    url: str
    target_path: Path
    expected_sha1: Optional[str] = None
    expected_size: Optional[int] = None
    name: str = ""


def download_single_file(
    url: str,
    dest_path: Path,
    expected_sha1: Optional[str] = None,
    expected_size: Optional[int] = None,
    cancel_token: Optional[threading.Event] = None,
    timeout: float = 15.0,
    retries: int = 3,
    bytes_callback: Optional[Callable[[int], None]] = None,
) -> bool:
    """Download a single file to dest_path with SHA-1 check, temp-file atomic rename, and retries."""
    if cancel_token and cancel_token.is_set():
        return False

    # Check if existing file is already valid
    if dest_path.is_file():
        if expected_size is not None and dest_path.stat().st_size != expected_size:
            pass  # Size mismatch, re-download
        elif expected_sha1:
            if verify_sha1(dest_path, expected_sha1):
                return True
        elif expected_size is not None and dest_path.stat().st_size == expected_size:
            return True

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = dest_path.with_name(dest_path.name + f".tmp.{os.getpid()}")

    for attempt in range(retries):
        if cancel_token and cancel_token.is_set():
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return False

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "mc-tui/1.0"})
            hasher = hashlib.sha1() if expected_sha1 else None
            downloaded = 0

            with urllib.request.urlopen(req, timeout=timeout) as resp, open(tmp_path, "wb") as out_f:
                while True:
                    if cancel_token and cancel_token.is_set():
                        out_f.close()
                        tmp_path.unlink(missing_ok=True)
                        return False

                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    out_f.write(chunk)
                    downloaded += len(chunk)
                    if hasher:
                        hasher.update(chunk)
                    if bytes_callback:
                        bytes_callback(len(chunk))

            # Verify size if expected
            if expected_size is not None and downloaded != expected_size:
                tmp_path.unlink(missing_ok=True)
                continue

            # Verify SHA-1 if expected
            if hasher and hasher.hexdigest().lower() != expected_sha1.lower():
                tmp_path.unlink(missing_ok=True)
                continue

            # Success: atomic move
            os.replace(tmp_path, dest_path)
            return True

        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))

    return False


class Downloader:
    def __init__(
        self,
        game_dir: Path | str,
        cache_dir: Optional[Path | str] = None,
        mirror: str = "official",
    ) -> None:
        self.game_dir = Path(game_dir)
        self.cache_dir = Path(cache_dir) if cache_dir else CONFIG_DIR / "cache"
        self.mirror = mirror
        self._manifest_cache: Optional[List[RemoteVersion]] = None
        self._latest_release: str = ""
        self._latest_snapshot: str = ""

    def fetch_manifest(self, force_refresh: bool = False) -> List[RemoteVersion]:
        """Fetch remote version manifest from Mojang or cache."""
        if not force_refresh and self._manifest_cache is not None:
            return self._manifest_cache

        cache_file = self.cache_dir / "version_manifest.json"

        # Check local cache file freshness (1 hour)
        if not force_refresh and cache_file.is_file():
            try:
                mtime = cache_file.stat().st_mtime
                if (time.time() - mtime) < 3600:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    versions = self._parse_manifest_data(data)
                    if versions:
                        self._manifest_cache = versions
                        return versions
            except Exception:
                pass

        # Fetch from network
        urls_to_try = [
            apply_mirror(MOJANG_MANIFEST_V2, self.mirror),
            MOJANG_MANIFEST_V2,
            MOJANG_MANIFEST_FALLBACK,
        ]

        last_err: Optional[Exception] = None
        manifest_data: Optional[Dict[str, Any]] = None

        for url in urls_to_try:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "mc-tui/1.0"})
                with urllib.request.urlopen(req, timeout=12) as resp:
                    manifest_data = json.loads(resp.read().decode("utf-8"))
                    break
            except Exception as e:
                last_err = e

        if manifest_data is None:
            # Fallback to existing cache file if available
            if cache_file.is_file():
                try:
                    with open(cache_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    versions = self._parse_manifest_data(data)
                    if versions:
                        self._manifest_cache = versions
                        return versions
                except Exception:
                    pass
            raise RuntimeError(f"Failed to fetch Mojang version manifest: {last_err}")

        # Save to disk cache
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, indent=2)
        except Exception:
            pass

        versions = self._parse_manifest_data(manifest_data)
        self._manifest_cache = versions
        return versions

    def _parse_manifest_data(self, data: Dict[str, Any]) -> List[RemoteVersion]:
        latest = data.get("latest", {})
        self._latest_release = latest.get("release", "")
        self._latest_snapshot = latest.get("snapshot", "")

        versions: List[RemoteVersion] = []
        for v in data.get("versions", []):
            vid = v.get("id")
            if not vid:
                continue
            v_type = v.get("type", "release")
            url = v.get("url", "")
            r_time = v.get("releaseTime", v.get("time", ""))
            sha1 = v.get("sha1", "")
            comp = v.get("complianceLevel", 0)
            versions.append(
                RemoteVersion(
                    id=vid,
                    type=v_type,
                    url=url,
                    time=v.get("time", ""),
                    release_time=r_time[:10] if r_time else "",
                    sha1=sha1,
                    compliance_level=comp,
                )
            )
        return versions

    def get_remote_version(self, version_id: str) -> Optional[RemoteVersion]:
        manifest = self.fetch_manifest()
        return next((v for v in manifest if v.id == version_id), None)

    def fetch_version_json(self, remote_version: RemoteVersion) -> Dict[str, Any]:
        """Fetch and return version package JSON."""
        url = apply_mirror(remote_version.url, self.mirror)
        req = urllib.request.Request(url, headers={"User-Agent": "mc-tui/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read()

        if remote_version.sha1:
            computed = hashlib.sha1(content).hexdigest().lower()
            if computed != remote_version.sha1.lower():
                raise ValueError(f"Version JSON SHA-1 mismatch for {remote_version.id}")

        return json.loads(content.decode("utf-8"))

    def collect_libraries_to_download(
        self,
        version_data: Dict[str, Any],
        current_os: str = "",
        current_arch: str = "",
    ) -> List[DownloadItem]:
        """Collect all required library jar files matching OS and architecture."""
        if not current_os:
            current_os = get_current_os()
        if not current_arch:
            current_arch = get_current_arch()

        libs_dir = self.game_dir / "libraries"
        libraries = version_data.get("libraries", [])
        items: List[DownloadItem] = []
        seen_targets: Set[Path] = set()

        for lib in libraries:
            # Check rules
            if not evaluate_rules(lib.get("rules"), current_os, current_arch):
                continue

            downloads = lib.get("downloads", {})
            artifact = downloads.get("artifact")

            # Standard artifact
            if artifact and "path" in artifact and "url" in artifact:
                rel_path = artifact["path"]
                target = libs_dir / rel_path
                if target not in seen_targets:
                    seen_targets.add(target)
                    items.append(
                        DownloadItem(
                            url=apply_mirror(artifact["url"], self.mirror),
                            target_path=target,
                            expected_sha1=artifact.get("sha1"),
                            expected_size=artifact.get("size"),
                            name=Path(rel_path).name,
                        )
                    )
            elif "name" in lib:
                rel_path = maven_to_path(lib["name"])
                if rel_path:
                    target = libs_dir / rel_path
                    if target not in seen_targets:
                        seen_targets.add(target)
                        default_url = f"https://libraries.minecraft.net/{rel_path}"
                        items.append(
                            DownloadItem(
                                url=apply_mirror(default_url, self.mirror),
                                target_path=target,
                                expected_sha1=None,
                                expected_size=None,
                                name=Path(rel_path).name,
                            )
                        )

            # Native classifiers
            natives_dict = lib.get("natives", {})
            classifier_key = natives_dict.get(current_os)
            if classifier_key:
                classifier_key = classifier_key.replace("${arch}", "64" if current_arch == "x86_64" else "32")
                classifiers = downloads.get("classifiers", {})
                nat_artifact = classifiers.get(classifier_key)

                if nat_artifact and "path" in nat_artifact and "url" in nat_artifact:
                    rel_path = nat_artifact["path"]
                    target = libs_dir / rel_path
                    if target not in seen_targets:
                        seen_targets.add(target)
                        items.append(
                            DownloadItem(
                                url=apply_mirror(nat_artifact["url"], self.mirror),
                                target_path=target,
                                expected_sha1=nat_artifact.get("sha1"),
                                expected_size=nat_artifact.get("size"),
                                name=Path(rel_path).name,
                            )
                        )
                elif "name" in lib:
                    coords = lib["name"].split(":")
                    if len(coords) >= 3:
                        coord_with_cls = f"{coords[0]}:{coords[1]}:{coords[2]}:{classifier_key}"
                        rel_path = maven_to_path(coord_with_cls)
                        if rel_path:
                            target = libs_dir / rel_path
                            if target not in seen_targets:
                                seen_targets.add(target)
                                default_url = f"https://libraries.minecraft.net/{rel_path}"
                                items.append(
                                    DownloadItem(
                                        url=apply_mirror(default_url, self.mirror),
                                        target_path=target,
                                        expected_sha1=None,
                                        expected_size=None,
                                        name=Path(rel_path).name,
                                    )
                                )

        return items

    def collect_assets_to_download(self, index_data: Dict[str, Any]) -> List[DownloadItem]:
        """Collect all asset objects specified in asset index."""
        objects = index_data.get("objects", {})
        items: List[DownloadItem] = []
        assets_dir = self.game_dir / "assets" / "objects"

        for obj_name, obj_meta in objects.items():
            h = obj_meta.get("hash")
            sz = obj_meta.get("size")
            if not h or len(h) < 2:
                continue
            sub_dir = h[:2]
            target = assets_dir / sub_dir / h
            url = f"https://resources.download.minecraft.net/{sub_dir}/{h}"
            items.append(
                DownloadItem(
                    url=apply_mirror(url, self.mirror),
                    target_path=target,
                    expected_sha1=h,
                    expected_size=sz,
                    name=obj_name,
                )
            )

        return items

    def _download_batch(
        self,
        items: List[DownloadItem],
        stage_name: str,
        progress_cb: Optional[Callable[[DownloadProgress], None]],
        cancel_token: Optional[threading.Event],
        max_workers: int = 12,
    ) -> bool:
        """Download a batch of DownloadItems concurrently."""
        total_items = len(items)
        if total_items == 0:
            return True

        # Quick pre-filter: check if already exists on disk
        verified_items: List[DownloadItem] = []
        to_download: List[DownloadItem] = []

        for it in items:
            if it.target_path.is_file():
                if it.expected_size is not None and it.target_path.stat().st_size == it.expected_size:
                    verified_items.append(it)
                    continue
                elif it.expected_sha1 and verify_sha1(it.target_path, it.expected_sha1):
                    verified_items.append(it)
                    continue
            to_download.append(it)

        completed_count = len(verified_items)
        bytes_downloaded = sum(it.expected_size or 0 for it in verified_items)
        total_bytes = sum(it.expected_size or 0 for it in items)

        # Notify initial state
        if progress_cb:
            progress_cb(
                DownloadProgress(
                    stage=stage_name,
                    message=f"Verifying {stage_name}: {completed_count}/{total_items} ready",
                    current=completed_count,
                    total=total_items,
                    bytes_downloaded=bytes_downloaded,
                    total_bytes=total_bytes,
                )
            )

        if not to_download:
            return True

        lock = threading.Lock()
        start_time = time.time()
        failed: List[DownloadItem] = []

        def worker(item: DownloadItem) -> bool:
            if cancel_token and cancel_token.is_set():
                return False

            def chunk_cb(chunk_len: int) -> None:
                nonlocal bytes_downloaded
                with lock:
                    bytes_downloaded += chunk_len

            ok = download_single_file(
                url=item.url,
                dest_path=item.target_path,
                expected_sha1=item.expected_sha1,
                expected_size=item.expected_size,
                cancel_token=cancel_token,
                bytes_callback=chunk_cb,
            )

            with lock:
                nonlocal completed_count
                if ok:
                    completed_count += 1
                else:
                    failed.append(item)

                if progress_cb and not (cancel_token and cancel_token.is_set()):
                    elapsed = max(0.1, time.time() - start_time)
                    speed = (bytes_downloaded - sum(it.expected_size or 0 for it in verified_items)) / elapsed
                    progress_cb(
                        DownloadProgress(
                            stage=stage_name,
                            message=f"Downloading {stage_name} ({completed_count}/{total_items})",
                            current=completed_count,
                            total=total_items,
                            bytes_downloaded=bytes_downloaded,
                            total_bytes=total_bytes,
                            current_file=item.name,
                            speed=max(0.0, speed),
                        )
                    )

            return ok

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(worker, item) for item in to_download]
            for f in concurrent.futures.as_completed(futures):
                if cancel_token and cancel_token.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    return False
                try:
                    f.result()
                except Exception:
                    pass

        if cancel_token and cancel_token.is_set():
            return False

        return len(failed) == 0

    def download_version(
        self,
        version_id: str,
        include_assets: bool = True,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
        cancel_token: Optional[threading.Event] = None,
        max_workers: int = 12,
    ) -> bool:
        """
        Download complete vanilla Minecraft version.
        Returns True on success, False if cancelled or failed.
        """
        cancel_token = cancel_token or threading.Event()

        def notify(prog: DownloadProgress) -> None:
            if progress_callback:
                progress_callback(prog)

        try:
            # 1. Fetch manifest & find target version
            notify(
                DownloadProgress(
                    stage="manifest",
                    message=f"Fetching version manifest...",
                    current=0,
                    total=100,
                )
            )
            r_ver = self.get_remote_version(version_id)
            if not r_ver:
                raise ValueError(f"Version '{version_id}' not found in official Mojang manifest.")

            if cancel_token.is_set():
                notify(DownloadProgress(stage="cancelled", message="Download cancelled.", is_done=True))
                return False

            # 2. Fetch and save version JSON
            notify(
                DownloadProgress(
                    stage="version_json",
                    message=f"Fetching version JSON for {version_id}...",
                    current=1,
                    total=100,
                )
            )
            v_data = self.fetch_version_json(r_ver)

            version_dir = self.game_dir / "versions" / version_id
            version_dir.mkdir(parents=True, exist_ok=True)
            v_json_file = version_dir / f"{version_id}.json"

            with open(v_json_file, "w", encoding="utf-8") as f:
                json.dump(v_data, f, indent=2)

            if cancel_token.is_set():
                notify(DownloadProgress(stage="cancelled", message="Download cancelled.", is_done=True))
                return False

            # 3. Download Client JAR
            downloads = v_data.get("downloads", {})
            client_info = downloads.get("client")
            if not client_info or "url" not in client_info:
                raise ValueError(f"Version JSON for {version_id} does not contain client download URL.")

            client_url = apply_mirror(client_info["url"], self.mirror)
            client_jar_file = version_dir / f"{version_id}.jar"
            client_sha1 = client_info.get("sha1")
            client_size = client_info.get("size", 0)

            notify(
                DownloadProgress(
                    stage="client_jar",
                    message=f"Downloading {version_id}.jar ({DownloadProgress._format_size(client_size)})...",
                    current=0,
                    total=1,
                    total_bytes=client_size,
                    current_file=f"{version_id}.jar",
                )
            )

            client_downloaded_bytes = 0
            start_client = time.time()

            def client_chunk_cb(n: int) -> None:
                nonlocal client_downloaded_bytes
                client_downloaded_bytes += n
                elapsed = max(0.1, time.time() - start_client)
                notify(
                    DownloadProgress(
                        stage="client_jar",
                        message=f"Downloading {version_id}.jar ({DownloadProgress._format_size(client_downloaded_bytes)}/{DownloadProgress._format_size(client_size)})",
                        current=0,
                        total=1,
                        bytes_downloaded=client_downloaded_bytes,
                        total_bytes=client_size,
                        current_file=f"{version_id}.jar",
                        speed=client_downloaded_bytes / elapsed,
                    )
                )

            ok_client = download_single_file(
                url=client_url,
                dest_path=client_jar_file,
                expected_sha1=client_sha1,
                expected_size=client_size,
                cancel_token=cancel_token,
                bytes_callback=client_chunk_cb,
            )
            if not ok_client:
                if cancel_token.is_set():
                    notify(DownloadProgress(stage="cancelled", message="Download cancelled.", is_done=True))
                    return False
                raise RuntimeError(f"Failed to download client jar: {client_url}")

            notify(
                DownloadProgress(
                    stage="client_jar",
                    message=f"{version_id}.jar downloaded and verified.",
                    current=1,
                    total=1,
                    bytes_downloaded=client_size,
                    total_bytes=client_size,
                )
            )

            # 4. Download Libraries
            lib_items = self.collect_libraries_to_download(v_data)
            notify(
                DownloadProgress(
                    stage="libraries",
                    message=f"Resolving {len(lib_items)} required libraries...",
                    current=0,
                    total=len(lib_items),
                )
            )

            ok_libs = self._download_batch(
                items=lib_items,
                stage_name="libraries",
                progress_cb=notify,
                cancel_token=cancel_token,
                max_workers=max_workers,
            )
            if not ok_libs:
                if cancel_token.is_set():
                    notify(DownloadProgress(stage="cancelled", message="Download cancelled.", is_done=True))
                    return False
                raise RuntimeError("One or more libraries failed to download.")

            # 5. Download Assets (if requested)
            if include_assets and "assetIndex" in v_data:
                ai = v_data["assetIndex"]
                ai_id = ai.get("id", version_id)
                ai_url = apply_mirror(ai.get("url", ""), self.mirror)
                ai_sha1 = ai.get("sha1")
                ai_size = ai.get("size")

                notify(
                    DownloadProgress(
                        stage="assets",
                        message=f"Fetching asset index ({ai_id})...",
                        current=0,
                        total=100,
                    )
                )

                indexes_dir = self.game_dir / "assets" / "indexes"
                indexes_dir.mkdir(parents=True, exist_ok=True)
                ai_file = indexes_dir / f"{ai_id}.json"

                ok_ai = download_single_file(
                    url=ai_url,
                    dest_path=ai_file,
                    expected_sha1=ai_sha1,
                    expected_size=ai_size,
                    cancel_token=cancel_token,
                )
                if not ok_ai:
                    if cancel_token.is_set():
                        notify(DownloadProgress(stage="cancelled", message="Download cancelled.", is_done=True))
                        return False
                    raise RuntimeError(f"Failed to download asset index from {ai_url}")

                with open(ai_file, "r", encoding="utf-8") as f:
                    index_data = json.load(f)

                asset_items = self.collect_assets_to_download(index_data)
                notify(
                    DownloadProgress(
                        stage="assets",
                        message=f"Resolving {len(asset_items)} asset files...",
                        current=0,
                        total=len(asset_items),
                    )
                )

                ok_assets = self._download_batch(
                    items=asset_items,
                    stage_name="assets",
                    progress_cb=notify,
                    cancel_token=cancel_token,
                    max_workers=max_workers,
                )
                if not ok_assets:
                    if cancel_token.is_set():
                        notify(DownloadProgress(stage="cancelled", message="Download cancelled.", is_done=True))
                        return False
                    # Note: We do not fail the entire install if minor non-critical assets failed
                    pass

                # Virtual and map_to_resources asset handling
                is_virtual = index_data.get("virtual", False)
                map_resources = index_data.get("map_to_resources", False)

                if is_virtual or map_resources:
                    objects = index_data.get("objects", {})
                    for obj_path, meta in objects.items():
                        h = meta.get("hash")
                        if not h:
                            continue
                        src = self.game_dir / "assets" / "objects" / h[:2] / h
                        if not src.is_file():
                            continue

                        targets: List[Path] = []
                        if is_virtual:
                            targets.append(self.game_dir / "assets" / "virtual" / "legacy" / obj_path)
                        if map_resources:
                            targets.append(self.game_dir / "resources" / obj_path)

                        for target in targets:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            if not target.exists():
                                try:
                                    os.link(src, target)
                                except Exception:
                                    try:
                                        shutil.copyfile(src, target)
                                    except Exception:
                                        pass

            notify(
                DownloadProgress(
                    stage="complete",
                    message=f"Successfully downloaded Minecraft {version_id}!",
                    current=100,
                    total=100,
                    is_done=True,
                )
            )
            return True

        except Exception as e:
            notify(
                DownloadProgress(
                    stage="error",
                    message=f"Error downloading {version_id}: {e}",
                    error=str(e),
                    is_done=True,
                )
            )
            return False

"""Minecraft version parser and resolution logic."""
from __future__ import annotations

import json
import os
import platform
import re
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


def get_current_os() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "osx"
    elif system == "windows":
        return "windows"
    return "linux"


def get_current_arch() -> str:
    arch = platform.machine().lower()
    if arch in ("x86_64", "amd64"):
        return "x86_64"
    elif arch in ("i386", "i686", "x86"):
        return "x86"
    elif arch in ("aarch64", "arm64"):
        return "arm64"
    return arch


def get_offline_uuid(username: str) -> str:
    """Generate Mojang standard offline UUID for player username."""
    # Java: UUID.nameUUIDFromBytes(("OfflinePlayer:" + name).getBytes(StandardCharsets.UTF_8))
    # Python: uuid.uuid3 with NAMESPACE_DNS / MD5 produces the exact same RFC 4122 v3 UUID
    ns = uuid.UUID("00000000-0000-0000-0000-000000000000")
    # Actually Java's UUID.nameUUIDFromBytes calculates MD5 hash, sets version=3 and variant=2
    # uuid.uuid3 uses standard namespace hashing, but let's do the exact byte mapping:
    import hashlib
    data = f"OfflinePlayer:{username}".encode("utf-8")
    md5_hash = bytearray(hashlib.md5(data).digest())
    md5_hash[6] = (md5_hash[6] & 0x0F) | 0x30  # set version to 3
    md5_hash[8] = (md5_hash[8] & 0x3F) | 0x80  # set variant to IETF
    return str(uuid.UUID(bytes=bytes(md5_hash)))


def maven_to_path(coordinate: str) -> str:
    """Convert maven coordinate to relative jar file path."""
    # Format: package:name:version[:classifier][@extension]
    ext = "jar"
    if "@" in coordinate:
        coordinate, ext = coordinate.split("@", 1)

    parts = coordinate.split(":")
    if len(parts) < 3:
        return ""

    pkg, name, version = parts[0], parts[1], parts[2]
    classifier = parts[3] if len(parts) > 3 else ""

    pkg_path = pkg.replace(".", "/")
    filename = f"{name}-{version}"
    if classifier:
        filename += f"-{classifier}"
    filename += f".{ext}"

    return f"{pkg_path}/{name}/{version}/{filename}"


def evaluate_rules(
    rules: Optional[List[Dict[str, Any]]],
    current_os: str = "",
    current_arch: str = "",
    features: Optional[Dict[str, bool]] = None,
) -> bool:
    """Evaluate Mojang rule array. Returns True if allowed, False otherwise."""
    if not rules:
        return True

    if not current_os:
        current_os = get_current_os()
    if not current_arch:
        current_arch = get_current_arch()
    if features is None:
        features = {}

    allowed = False
    for rule in rules:
        action = rule.get("action")
        applies = True

        # OS check
        if "os" in rule:
            os_rule = rule["os"]
            if "name" in os_rule:
                if os_rule["name"] != current_os:
                    applies = False
            if "arch" in os_rule and applies:
                if os_rule["arch"] != current_arch:
                    applies = False
            if "version" in os_rule and applies:
                try:
                    if not re.match(os_rule["version"], platform.release()):
                        applies = False
                except Exception:
                    pass

        # Features check
        if "features" in rule and applies:
            for feat_name, feat_val in rule["features"].items():
                if features.get(feat_name) != feat_val:
                    applies = False
                    break

        if applies:
            allowed = (action == "allow")

    return allowed


@dataclass
class VersionMeta:
    id: str
    type: str  # release, snapshot, modified, forge, fabric, standalone
    main_class: str
    release_time: str
    java_major_version: int
    inherits_from: Optional[str]
    jar_path: Optional[Path]
    json_path: Optional[Path]
    is_standalone_jar: bool = False
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def display_type(self) -> str:
        if self.is_standalone_jar:
            return "JAR"
        vid = self.id.lower()
        if "fabric" in vid:
            return "Fabric"
        if "forge" in vid or "neoforge" in vid:
            return "Forge"
        if "quilt" in vid:
            return "Quilt"
        if "optifine" in vid:
            return "OptiFine"
        return self.type.capitalize() if self.type else "Custom"


class VersionScanner:
    def __init__(self, game_dir: Path | str) -> None:
        self.game_dir = Path(game_dir)

    def list_versions(self) -> List[VersionMeta]:
        """Scan game directory and return all detected versions."""
        versions: List[VersionMeta] = []
        versions_dir = self.game_dir / "versions"

        # 1. Scan versions directory
        if versions_dir.exists() and versions_dir.is_dir():
            try:
                for entry in sorted(versions_dir.iterdir()):
                    if entry.is_dir():
                        v_json = entry / f"{entry.name}.json"
                        if v_json.is_file():
                            meta = self.load_version_meta(v_json)
                            if meta:
                                versions.append(meta)
            except Exception:
                pass

        # 2. Check for standalone .jar files in root game_dir or versions_dir
        for search_dir in (self.game_dir, versions_dir):
            if search_dir.exists() and search_dir.is_dir():
                try:
                    for entry in search_dir.glob("*.jar"):
                        if entry.is_file() and not entry.name.endswith("-sources.jar"):
                            # Avoid duplicates if version folder already matched
                            name = entry.stem
                            if not any(v.id == name for v in versions):
                                versions.append(
                                    VersionMeta(
                                        id=name,
                                        type="standalone",
                                        main_class="",
                                        release_time="",
                                        java_major_version=0,
                                        inherits_from=None,
                                        jar_path=entry,
                                        json_path=None,
                                        is_standalone_jar=True,
                                    )
                                )
                except Exception:
                    pass

        return versions

    def load_version_meta(self, json_path: Path) -> Optional[VersionMeta]:
        """Read version json and return basic metadata."""
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            vid = data.get("id", json_path.parent.name)
            v_type = data.get("type", "release")
            main_class = data.get("mainClass", "")
            release_time = data.get("releaseTime", data.get("time", ""))

            # Java version
            java_major = 0
            java_ver_data = data.get("javaVersion")
            if isinstance(java_ver_data, dict):
                java_major = int(java_ver_data.get("majorVersion", 0))

            inherits_from = data.get("inheritsFrom")

            # Version jar
            # Check if jar attribute overrides
            jar_name = data.get("jar", vid)
            possible_jar = json_path.parent / f"{jar_name}.jar"
            jar_path = possible_jar if possible_jar.is_file() else None

            return VersionMeta(
                id=vid,
                type=v_type,
                main_class=main_class,
                release_time=release_time[:10] if release_time else "",
                java_major_version=java_major,
                inherits_from=inherits_from,
                jar_path=jar_path,
                json_path=json_path,
                raw_data=data,
            )
        except Exception:
            return None

    def resolve_version_tree(self, version_id: str) -> Dict[str, Any]:
        """
        Recursively load and merge a version with its parents (inheritsFrom).
        Returns fully merged version dictionary.
        """
        versions_dir = self.game_dir / "versions"
        v_json = versions_dir / version_id / f"{version_id}.json"
        if not v_json.is_file():
            raise FileNotFoundError(f"Version JSON not found: {v_json}")

        with open(v_json, "r", encoding="utf-8") as f:
            child = json.load(f)

        parent_id = child.get("inheritsFrom")
        if not parent_id:
            return child

        # Load parent recursively
        parent = self.resolve_version_tree(parent_id)

        # Merge parent and child:
        merged = dict(parent)
        merged.update({k: v for k, v in child.items() if v is not None})

        # Libraries: child libraries often prepend or append to parent libraries
        # Deduplicate libraries by name prefix (package:name)
        child_libs = child.get("libraries", [])
        parent_libs = parent.get("libraries", [])

        def lib_id(lib: dict) -> str:
            name = lib.get("name", "")
            parts = name.split(":")
            if len(parts) >= 2:
                return f"{parts[0]}:{parts[1]}"
            return name

        merged_libs: List[dict] = []
        seen_lib_ids: Set[str] = set()

        for lib in child_libs:
            lid = lib_id(lib)
            if lid:
                seen_lib_ids.add(lid)
            merged_libs.append(lib)

        for lib in parent_libs:
            lid = lib_id(lib)
            if not lid or lid not in seen_lib_ids:
                merged_libs.append(lib)

        merged["libraries"] = merged_libs

        # Arguments:
        child_args = child.get("arguments")
        parent_args = parent.get("arguments")

        if isinstance(child_args, dict) or isinstance(parent_args, dict):
            c_args = child_args if isinstance(child_args, dict) else {}
            p_args = parent_args if isinstance(parent_args, dict) else {}

            merged_jvm = list(p_args.get("jvm", [])) + list(c_args.get("jvm", []))
            merged_game = list(p_args.get("game", [])) + list(c_args.get("game", []))
            merged["arguments"] = {
                "jvm": merged_jvm,
                "game": merged_game,
            }
        elif "minecraftArguments" in child:
            merged["minecraftArguments"] = child["minecraftArguments"]

        # Ensure jar fallback
        if "jar" not in child:
            # If child version folder doesn't have child_id.jar, use parent_id
            c_jar = versions_dir / version_id / f"{version_id}.jar"
            if not c_jar.is_file():
                merged["jar"] = parent.get("jar", parent_id)

        # Retain child's primary ID
        merged["id"] = child.get("id", version_id)
        return merged

"""Java runtime detection and version matching."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class JavaInfo:
    path: str
    version_string: str
    major_version: int
    is_valid: bool = True

    def __str__(self) -> str:
        return f"Java {self.major_version} ({self.version_string}) -> {self.path}"


def parse_java_version(output: str) -> tuple[str, int]:
    """Parse Java version string and major version number from java -version output."""
    # Examples:
    # openjdk version "25.0.4.1" 2026-08-18
    # java version "1.8.0_351"
    # openjdk version "17.0.8" 2023-07-18
    match = re.search(r'(?:java|openjdk) version "([^"]+)"', output)
    if not match:
        # Fallback to general pattern
        match = re.search(r'version "([^"]+)"', output)

    if not match:
        return ("unknown", 0)

    ver_str = match.group(1)
    # Parse major version
    # Legacy: 1.8.0_... -> 8
    # Modern: 17.0.1 -> 17, 21.0.2 -> 21, 25.0.4 -> 25
    parts = ver_str.split(".")
    try:
        if parts[0] == "1" and len(parts) > 1:
            major = int(parts[1])
        else:
            major = int(parts[0])
    except ValueError:
        major = 0

    return (ver_str, major)


def get_java_info(java_path: str | Path) -> Optional[JavaInfo]:
    """Inspect a Java executable and return its JavaInfo."""
    path_str = str(java_path)
    if not os.path.isfile(path_str) or not os.access(path_str, os.X_OK):
        return None

    try:
        proc = subprocess.run(
            [path_str, "-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3,
        )
        # java -version usually writes to stderr
        combined = (proc.stderr or "") + (proc.stdout or "")
        ver_str, major = parse_java_version(combined)
        return JavaInfo(path=os.path.realpath(path_str), version_string=ver_str, major_version=major)
    except Exception:
        return None


def detect_all_javas() -> List[JavaInfo]:
    """Discover all installed Java runtimes on the system."""
    candidates: set[str] = set()

    # 1. From PATH
    which_java = shutil.which("java")
    if which_java:
        candidates.add(which_java)

    # 2. Check JAVA_HOME
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        jh_bin = Path(java_home) / "bin" / "java"
        if jh_bin.is_file():
            candidates.add(str(jh_bin))

    # 3. Check common Linux JVM directories
    jvm_dirs = [
        Path("/usr/lib/jvm"),
        Path("/usr/java"),
        Path("/opt/jdk"),
        Path("/opt/java"),
        Path.home() / ".jdks",
        Path.home() / ".sdkman" / "candidates" / "java",
    ]

    for root_dir in jvm_dirs:
        if root_dir.exists() and root_dir.is_dir():
            try:
                for entry in root_dir.iterdir():
                    bin_java = entry / "bin" / "java"
                    if bin_java.is_file():
                        candidates.add(str(bin_java))
            except Exception:
                pass

    # Inspect all candidates and deduplicate by canonical path
    results: List[JavaInfo] = []
    seen_paths: set[str] = set()

    for cand in candidates:
        info = get_java_info(cand)
        if info and info.path not in seen_paths:
            seen_paths.add(info.path)
            results.append(info)

    # Sort by major version descending
    results.sort(key=lambda j: j.major_version, reverse=True)
    return results


def find_best_java(required_major: Optional[int] = None, configured_path: str = "") -> Optional[JavaInfo]:
    """Find the most appropriate Java runtime."""
    if configured_path:
        custom_info = get_java_info(configured_path)
        if custom_info:
            return custom_info

    all_javas = detect_all_javas()
    if not all_javas:
        return None

    if not required_major:
        return all_javas[0]

    # Exact match first
    for j in all_javas:
        if j.major_version == required_major:
            return j

    # Compatible match:
    # If required_major <= 8, prefer 8, then lowest >= 8
    # If required_major >= 17, prefer >= required_major
    compatible = [j for j in all_javas if j.major_version >= required_major]
    if compatible:
        # Pick lowest version that satisfies the requirement
        return sorted(compatible, key=lambda j: j.major_version)[0]

    # Fallback to highest available
    return all_javas[0]

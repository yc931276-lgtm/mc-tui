#!/usr/bin/env python3
"""Update MC-TUI's version across the source tree and Debian packaging files.

Usage:
    python3 bump_version.py 1.2.0          # Debian revision defaults to 1
    python3 bump_version.py 1.2.0 2
    python3 bump_version.py 1.2.0 -m "Add new feature" --dry-run
"""
from __future__ import annotations

import argparse
import email.utils
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INIT_FILE = ROOT / "mc_tui" / "__init__.py"
CONTROL_FILE = ROOT / "debian" / "control"
CHANGELOG_FILE = ROOT / "debian" / "changelog"
MAN_FILE = ROOT / "debian" / "mc-tui.1"
README_FILE = ROOT / "README.md"

UPSTREAM_RE = re.compile(r"^\d+(?:\.\d+){1,3}(?:[-+~][0-9A-Za-z.+~]+)?$")
REVISION_RE = re.compile(r"^[0-9][0-9A-Za-z.+~]*$")


def _replace(pattern: str, replacement: str, text: str, *, count: int = 1) -> str:
    new_text, changed = re.subn(pattern, replacement, text, count=count, flags=re.M)
    return new_text if changed else text


def _changelog_entry(version: str, revision: str, maintainer: str, messages: list[str]) -> str:
    bullets = messages or [f"New upstream release {version}."]
    lines = [f"mc-tui ({version}-{revision}) unstable; urgency=medium", ""]
    lines.extend(f"  * {message}" for message in bullets)
    lines.append("")
    lines.append(f" -- {maintainer}  {email.utils.formatdate(localtime=True)}")
    return "\n".join(lines) + "\n\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump the MC-TUI version everywhere.")
    parser.add_argument("version", help="upstream version, e.g. 1.2.0")
    parser.add_argument(
        "revision",
        nargs="?",
        default="1",
        help="Debian revision (default: 1)",
    )
    parser.add_argument(
        "--message",
        "-m",
        action="append",
        default=[],
        help="changelog bullet; may be repeated",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="show what would change without writing files",
    )
    args = parser.parse_args()

    version = args.version.strip()
    revision = args.revision.strip()
    if not UPSTREAM_RE.match(version):
        parser.error(f"invalid upstream version: {version!r} (expected e.g. 1.2.0)")
    if not REVISION_RE.match(revision):
        parser.error(f"invalid Debian revision: {revision!r} (expected e.g. 1 or 2)")

    deb_version = f"{version}-{revision}"

    control_text = CONTROL_FILE.read_text(encoding="utf-8")
    init_text = INIT_FILE.read_text(encoding="utf-8")
    changelog_text = CHANGELOG_FILE.read_text(encoding="utf-8")
    man_text = MAN_FILE.read_text(encoding="utf-8")
    readme_text = README_FILE.read_text(encoding="utf-8")

    maintainer_match = re.search(r"^Maintainer:\s*(.+)$", control_text, flags=re.M)
    maintainer = maintainer_match.group(1).strip() if maintainer_match else "heaway <heaway@localhost>"

    new_control = _replace(r"^Version:.*$", f"Version: {deb_version}", control_text)
    new_init = _replace(r'^__version__ = "[^"]*"', f'__version__ = "{version}"', init_text)

    month_year = datetime.now().strftime("%B %Y")
    new_man = _replace(
        r'^\.TH MC-TUI 1 "[^"]*" "mc-tui [^"]*" "User Commands"$',
        f'.TH MC-TUI 1 "{month_year}" "mc-tui {version}" "User Commands"',
        man_text,
    )
    new_readme = re.sub(
        r"mc-tui_[0-9][0-9A-Za-z.+~-]*_all\.deb",
        f"mc-tui_{deb_version}_all.deb",
        readme_text,
    )

    if changelog_text.startswith(f"mc-tui ({deb_version})"):
        new_changelog = changelog_text
    else:
        new_changelog = _changelog_entry(version, revision, maintainer, args.message) + changelog_text

    updates = {
        INIT_FILE: new_init,
        CONTROL_FILE: new_control,
        MAN_FILE: new_man,
        CHANGELOG_FILE: new_changelog,
        README_FILE: new_readme,
    }

    for path, content in updates.items():
        old = path.read_text(encoding="utf-8")
        status = "updated" if content != old else "unchanged"
        print(f"{status:9} {path.relative_to(ROOT)}")
        if content != old and not args.dry_run:
            path.write_text(content, encoding="utf-8")

    print(f"\nVersion: {version}  |  Debian: {deb_version}")
    if args.dry_run:
        print("Dry run: no files were written.")
    else:
        print("Next: ./build_deb.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())

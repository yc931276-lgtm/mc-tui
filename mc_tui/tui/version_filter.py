"""Search and selection helpers for the vanilla download view."""
from __future__ import annotations

from typing import List, Optional, Sequence

from mc_tui.downloader import RemoteVersion


def normalize_query(query: Optional[str]) -> str:
    """Normalize a version search term (trim, lowercase, drop a leading ``v``)."""
    text = (query or "").strip().lower()
    if len(text) > 1 and text[0] == "v" and text[1].isdigit():
        text = text[1:]
    return text


def filter_versions(
    versions: Sequence[RemoteVersion],
    query: Optional[str],
    include_snapshots: bool,
) -> List[RemoteVersion]:
    """Return versions matching the release-mode and search filters."""
    text = normalize_query(query)
    result: List[RemoteVersion] = []
    for version in versions:
        if not include_snapshots and not version.is_release:
            continue
        if text:
            version_id = version.id.lower()
            if text not in version_id and text not in version.display_type.lower():
                continue
        result.append(version)
    return result


def best_match_index(versions: Sequence[RemoteVersion], query: Optional[str]) -> int:
    """Index of the best match for ``query``: exact ID, prefix, then substring."""
    text = normalize_query(query)
    if not versions or not text:
        return 0

    for index, version in enumerate(versions):
        if version.id.lower() == text:
            return index
    for index, version in enumerate(versions):
        if version.id.lower().startswith(text):
            return index
    for index, version in enumerate(versions):
        if text in version.id.lower():
            return index
    return 0

"""MC-TUI: A lightweight Terminal UI Minecraft Launcher for local files."""
__version__ = "1.1.0"

# Filled in by build_deb.sh for packaged builds; empty in the source tree.
try:
    from mc_tui.build_info import BUILD_TIME as __build_time__
except Exception:  # pragma: no cover - defensive for partial installs
    __build_time__ = ""

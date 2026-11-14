#!/usr/bin/env python3
"""MC-TUI Entry Point."""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mc_tui.cli import cli

if __name__ == "__main__":
    cli()

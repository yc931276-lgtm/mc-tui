#!/usr/bin/env python3
"""MC-TUI Entry Point."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from mc_tui.config import Config
from mc_tui.launcher import Launcher
from mc_tui.tui.app import MCTuiApp, main
from mc_tui.version_parser import VersionScanner


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="MC-TUI: Fast and lightweight Terminal UI Minecraft Launcher for local files."
    )
    parser.add_argument(
        "--game-dir",
        type=str,
        default=None,
        help="Specify Minecraft root directory (default: ~/.minecraft or config)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all locally installed Minecraft versions and exit",
    )
    parser.add_argument(
        "--launch",
        type=str,
        metavar="VERSION_ID",
        help="Directly launch a specified version without opening TUI",
    )
    parser.add_argument(
        "--username",
        type=str,
        default=None,
        help="Override player username for launch",
    )
    parser.add_argument(
        "--ram",
        type=str,
        default=None,
        help="Override maximum RAM (e.g. 4G, 8G)",
    )
    parser.add_argument(
        "--preview",
        type=str,
        metavar="VERSION_ID",
        help="Print the generated Java launch command for VERSION_ID and exit",
    )

    args = parser.parse_args()
    config = Config()

    if args.game_dir:
        config.game_dir = args.game_dir
    if args.username:
        config.username = args.username
    if args.ram:
        config.max_ram = args.ram

    # Handle --list
    if args.list:
        scanner = VersionScanner(config.game_dir)
        versions = scanner.list_versions()
        print(f"\nMinecraft Game Directory: {config.game_dir}")
        print(f"Found {len(versions)} local version(s):\n")
        if not versions:
            print("  (No versions found. Check game directory path)")
        else:
            print(f"  {'TYPE':<12} {'VERSION ID':<35} {'RELEASE DATE':<15} {'JAVA'}")
            print("  " + "─" * 70)
            for v in versions:
                j_str = f"Java {v.java_major_version}" if v.java_major_version else "Default"
                print(f"  {v.display_type:<12} {v.id:<35} {v.release_time:<15} {j_str}")
        print()
        sys.exit(0)

    # Handle --preview
    if args.preview:
        scanner = VersionScanner(config.game_dir)
        versions = scanner.list_versions()
        target = next((v for v in versions if v.id == args.preview), None)
        if not target:
            print(f"Error: Version '{args.preview}' not found in {config.game_dir}/versions", file=sys.stderr)
            sys.exit(1)
        launcher = Launcher(config)
        plan = launcher.build_launch_plan(target)
        print(f"\n--- Launch Plan for {target.id} ---")
        print(f"Java: {plan.java_bin}")
        print(f"Working Dir: {plan.cwd}")
        print(f"Natives Dir: {plan.natives_dir}")
        print("\nFull Command:")
        print(f"{plan.java_bin} \\\n  " + " \\\n  ".join(plan.args))
        print()
        sys.exit(0)

    # Handle --launch
    if args.launch:
        scanner = VersionScanner(config.game_dir)
        versions = scanner.list_versions()
        target = next((v for v in versions if v.id == args.launch), None)
        if not target:
            print(f"Error: Version '{args.launch}' not found in {config.game_dir}/versions", file=sys.stderr)
            sys.exit(1)

        print(f"Launching {target.id} (Player: {config.username}, RAM: {config.max_ram})...")
        launcher = Launcher(config)
        proc = launcher.launch(target, log_callback=lambda line: print(line))
        try:
            if proc._thread:
                proc._thread.join()
        except KeyboardInterrupt:
            print("\nStopping Minecraft...")
            proc.stop()
        sys.exit(proc.exit_code or 0)

    # Launch interactive TUI
    import curses
    app = MCTuiApp(config)
    curses.wrapper(app.run)


if __name__ == "__main__":
    cli()

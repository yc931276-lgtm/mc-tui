"""Command line interface and argument parsing for MC-TUI."""
from __future__ import annotations

import argparse
import curses
import sys

from mc_tui.config import Config
from mc_tui.downloader import Downloader, DownloadProgress
from mc_tui.launcher import Launcher
from mc_tui.tui.app import MCTuiApp
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
    parser.add_argument(
        "--download-list",
        action="store_true",
        help="List official Minecraft versions available for download from Mojang",
    )
    parser.add_argument(
        "--download",
        type=str,
        metavar="VERSION_ID",
        help="Download vanilla Minecraft VERSION_ID (client jar, libraries, and assets)",
    )
    parser.add_argument(
        "--snapshots",
        action="store_true",
        help="Include snapshots and pre-releases with --download-list",
    )
    parser.add_argument(
        "--no-assets",
        action="store_true",
        help="Skip downloading asset files (sounds, music, textures) with --download",
    )
    parser.add_argument(
        "--mirror",
        type=str,
        choices=["official", "bmclapi"],
        default=None,
        help="Select download mirror ('official' or 'bmclapi')",
    )

    args = parser.parse_args()
    config = Config()

    if args.game_dir:
        config.game_dir = args.game_dir
    if args.username:
        config.username = args.username
    if args.ram:
        config.max_ram = args.ram
    if args.mirror:
        config.download_mirror = args.mirror

    # Handle --download-list
    if args.download_list:
        mirror = args.mirror or config.download_mirror
        downloader = Downloader(config.game_dir, mirror=mirror)
        print(f"\nFetching official Minecraft version manifest (Mirror: {mirror})...")
        try:
            versions = downloader.fetch_manifest()
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        installed_ids = {v.id for v in VersionScanner(config.game_dir).list_versions()}
        displayed = [v for v in versions if v.is_release] if not args.snapshots else versions

        print(f"Found {len(displayed)} available version(s)" + (" (Releases only)" if not args.snapshots else "") + ":\n")
        print(f"  {'TYPE':<10} {'VERSION ID':<30} {'RELEASE DATE':<14} {'STATUS'}")
        print("  " + "─" * 68)
        for v in displayed:
            status = "✔ Installed" if v.id in installed_ids else ""
            print(f"  {v.display_type:<10} {v.id:<30} {v.release_time:<14} {status}")
        print()
        sys.exit(0)

    # Handle --download
    if args.download:
        ver_id = args.download
        mirror = args.mirror or config.download_mirror
        include_assets = not args.no_assets
        downloader = Downloader(config.game_dir, mirror=mirror)

        print(f"\nPreparing to download Minecraft {ver_id} (Vanilla)...")
        print(f"Target Directory: {config.game_dir}")
        print(f"Include Assets:   {'Yes' if include_assets else 'No (Quick)'}")
        print(f"Download Mirror:  {mirror}\n")

        last_stage = ""

        def cli_progress(p: DownloadProgress) -> None:
            nonlocal last_stage
            if p.stage != last_stage:
                if last_stage in ("libraries", "assets", "client_jar"):
                    sys.stdout.write("\n")
                last_stage = p.stage
                if p.message and p.stage not in ("libraries", "assets"):
                    print(f"==> {p.message}")

            if p.stage in ("libraries", "assets"):
                bar_len = 25
                pct = p.percent
                filled = int(bar_len * (pct / 100.0))
                bar_str = "=" * filled + "-" * (bar_len - filled)
                speed_str = f"({p.formatted_speed})" if p.speed > 0 else ""
                sys.stdout.write(
                    f"\r  [{p.stage.capitalize()}] [{bar_str}] {pct:5.1f}% ({p.current}/{p.total}) {p.formatted_bytes} {speed_str}   "
                )
                sys.stdout.flush()

        try:
            ok = downloader.download_version(
                version_id=ver_id,
                include_assets=include_assets,
                progress_callback=cli_progress,
            )
        except KeyboardInterrupt:
            print("\nDownload aborted by user.")
            sys.exit(130)

        sys.stdout.write("\n")
        if ok:
            print(f"\n✔ Successfully downloaded Minecraft {ver_id} to {config.game_dir}/versions/{ver_id}!")
            print(f"  Launch with: ./run.py --launch {ver_id}\n")
            sys.exit(0)
        else:
            print(f"\n✖ Download failed for Minecraft {ver_id}.", file=sys.stderr)
            sys.exit(1)

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
    app = MCTuiApp(config)
    curses.wrapper(app.run)

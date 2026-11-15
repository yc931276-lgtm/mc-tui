# MC-TUI: Terminal User Interface Minecraft Launcher

A lightweight, zero-dependency **Terminal User Interface (TUI) Minecraft launcher** designed specifically for discovering and launching **local Minecraft files**.

Built strictly with Python's standard library (`curses`, `subprocess`, `json`, `uuid`, etc.), requiring **no external pip packages** or compilers.

---

## ✨ Features

- **Local & Offline Focus**:
  - No Microsoft login or external accounts required.
  - Automatically generates standard Mojang offline UUIDs for custom player usernames.
  - 100% offline launch — does not make unneeded network requests or telemetry calls.
- **Built-in Vanilla Minecraft Downloader**:
  - Download official Mojang releases, snapshots, and legacy versions directly.
  - Downloads version JSON, client `.jar`, platform-specific libraries/natives, and asset indexes/objects.
  - Multi-threaded concurrent downloading with SHA-1 integrity verification, HTTP Range resume (`.part` files), and duplicate-target de-duplication.
  - Optional mirror support (`official` Mojang or `bmclapi`).
- **Universal Local Version Compatibility**:
  - Supports **Vanilla**, **Fabric**, **Forge**, **NeoForge**, **Quilt**, and **OptiFine**.
  - Also launches standalone server or client `.jar` files directly.
  - Resolves recursive version inheritance (`inheritsFrom`) for mod loaders.
- **Comprehensive Launch Engine**:
  - Supports both **modern** `arguments` JSON format (1.13+) and **legacy** `minecraftArguments` format (1.7 – 1.12.2).
  - Evaluates Mojang OS and architecture rules (`linux`, `x86_64`, `arm64`, etc.).
  - Resolves Maven library coordinates into local jar paths.
  - Automatically extracts native shared libraries (`.so`) into native directories for older releases.
- **Smart Java Runtime Detection**:
  - Discovers installed Java environments across `/usr/lib/jvm`, `PATH`, `$JAVA_HOME`, and SDK managers.
  - Parses major versions (Java 8, 11, 17, 21, 25) and selects the appropriate runtime for the target Minecraft version.
  - Installs missing OpenJDK 8/17/21/25 runtimes from the **Settings** tab via `apt` (sudo password prompt).
- **Interactive TUI & Full Internationalization**:
  - **Simplified Chinese (简体中文) & English**: Automatically detects system locale with manual override in settings.
  - **Versions View**: Filter and search versions (`/`), view metadata, release dates, required Java version, and launch with `[Enter]`.
  - **Settings View**: Interactively configure username, RAM (`-Xms`, `-Xmx`), JVM flags, mirrors, language, custom Java/game paths, JRE installation, and appearance.
  - **Themes & Appearance**: Seven color presets (Classic, Ocean, Forest, Sunset, Mono, Neon, Paper), accent-color override, header-bar style, and selection style with live preview.
  - **Console Logs View**: Real-time Minecraft process output viewer with colorized logs, auto-scroll, and process termination.
  - **Game Directory Selector**: Easily switch between `~/.minecraft`, Prism Launcher instances, Flatpak directories, or custom folders.
  - **Vanilla Downloader**: Browse official releases/snapshots, search by version ID (e.g. `1.20.4`), preview details, and download directly within the TUI.
- **CLI Companion**:
  - Use headless or in scripts via `--list`, `--launch`, and `--preview`.

---

## 🚀 Quick Start

### 1. Launch Interactive TUI
```bash
# Direct run
python3 run.py

# Or via wrapper executable
mc-tui
```

### 2. CLI Modes

**List available official vanilla versions from Mojang:**
```bash
./run.py --download-list
# Or include snapshots and pre-releases
./run.py --download-list --snapshots
```

**Download official Minecraft vanilla version:**
```bash
# Complete download (client jar + libraries + sounds & textures assets)
./run.py --download 1.20.4

# Quick download (client jar + libraries only, skipping optional assets)
./run.py --download 1.20.4 --no-assets

# Download using BMCLAPI mirror
./run.py --download 1.20.4 --mirror bmclapi
```

**List locally installed versions:**
```bash
./run.py --list
# Or specify a custom game directory
./run.py --game-dir ~/Games/minecraft --list
```

**Preview the assembled Java command without launching:**
```bash
./run.py --preview 1.20.4
```

**Directly launch a version from terminal with streaming logs:**
```bash
./run.py --launch 1.20.4 --username Steve --ram 4G
```

---

## ⌨️ TUI Keyboard Shortcuts

| Shortcut | Description |
|---|---|
| `[1]` `[2]` `[3]` `[4]` `[5]` | Switch between **Versions**, **Settings**, **Console**, **Game Dir**, **Download** |
| `[Tab]` | Cycle to next tab |
| `[↑]` / `[↓]` or `[k]` / `[j]` | Navigate lists or fields |
| `[Enter]` | Launch selected version / start download / edit setting |
| `[d]` | Quick jump to **Download** tab (from Versions view) |
| `[a]` | Toggle assets download on/off (Download view) |
| `[s]` | Toggle snapshots on/off (Download view) / Save settings (Settings view) |
| `[p]` | Preview full Java command and arguments |
| `[/]` | Search versions by ID (e.g. `1.20.4`; exact match auto-selected in Download) |
| `[r]` | Refresh versions list / manifest / Reset settings to defaults |
| `[Space]` | Toggle log auto-scroll (Console view) |
| `[k]` | Stop / Kill running Minecraft process (Console view) |
| `[c]` | Clear console logs |
| `[e]` | Enter custom path (Game Dir view) |
| `[q]` | Quit launcher / Cancel active download |

---

## 📁 Project Structure

```
mc-tui/
├── bump_version.py         # Update version across source and Debian packaging
├── mc_tui/
│   ├── __init__.py
│   ├── config.py           # Configuration management (~/.config/mc-tui/config.json)
│   ├── downloader.py       # Mojang vanilla version, library, and asset downloader
│   ├── i18n.py             # Internationalization & Simplified Chinese translations
│   ├── java_detector.py    # Multi-version Java scanner and version matcher
│   ├── version_parser.py   # Version JSON parsing, inheritsFrom merger, maven resolver
│   ├── launcher.py         # Launch plan builder, native extractor, process controller
│   ├── theme.py            # Color themes and appearance settings
│   └── tui/
│       ├── __init__.py
│       ├── app.py          # Main curses event loop & controller
│       ├── ui_helpers.py   # Modals, color pairs, safe rendering, text prompts
│       ├── version_filter.py # Download-page version search and best-match selection
│       └── views.py        # Tab views: versions, settings, console, directory picker, download
├── tests/
│   ├── test_config.py
│   ├── test_downloader.py
│   ├── test_i18n.py
│   ├── test_java_detector.py
│   ├── test_parser.py
│   ├── test_launcher.py
│   └── test_execution.py
├── run.py                  # CLI and TUI launcher entrypoint
├── mc-tui                  # Executable wrapper symlink
└── README.md
```

---

## 🧪 Running Tests

```bash
cd /home/heaway/Dev/mc-tui
python3 -m unittest discover -s tests
```

---

## 📦 Debian Package (.deb)

### Bump Version
Version strings live in `mc_tui/__init__.py`, `debian/control`, `debian/changelog`, the man page and README package filenames. Update all of them at once:
```bash
python3 bump_version.py 1.2.0          # Debian revision defaults to 1
python3 bump_version.py 1.2.0 2        # packaging-only revision 2
python3 bump_version.py 1.2.0 --dry-run
```
The launcher's `${launcher_version}` / `-Dminecraft.launcher.version` now come from `mc_tui.__version__`, so no separate edit is needed there.

### Build Package
To build the `.deb` package on Debian/Ubuntu systems:
```bash
./build_deb.sh
```
The resulting package will be generated at `dist/mc-tui_1.1.0-1_all.deb`. Only this canonically named file is produced; no convenience copies are created. The build script also stamps the package build time shown on the About page; source-tree runs display "development run" instead.

### Install Package
Using `apt` installs the launcher itself; the only required dependency is Python 3. Java runtimes are optional and are no longer pulled in automatically — install the versions you need from the **Settings** tab inside the TUI (`Install JRE 8/17/21/25`), or manually with `sudo apt install openjdk-17-jre`:
```bash
sudo apt install ./dist/mc-tui_1.1.0-1_all.deb
```
Or via `dpkg`:
```bash
sudo dpkg -i dist/mc-tui_1.1.0-1_all.deb
# Resolve any missing dependencies if using dpkg:
sudo apt-get install -f
```

Once installed, `mc-tui` can be launched from anywhere via `mc-tui` in your terminal or from your desktop applications menu.

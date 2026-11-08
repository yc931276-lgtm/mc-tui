# MC-TUI: Terminal User Interface Minecraft Launcher

A lightweight, zero-dependency **Terminal User Interface (TUI) Minecraft launcher** designed specifically for discovering and launching **local Minecraft files**.

Built strictly with Python's standard library (`curses`, `subprocess`, `json`, `uuid`, etc.), requiring **no external pip packages** or compilers.

---

## ✨ Features

- **Local & Offline Focus**:
  - No Microsoft login or external accounts required.
  - Automatically generates standard Mojang offline UUIDs for custom player usernames.
  - 100% offline — does not make unneeded network requests or telemetry calls.
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
- **Interactive TUI**:
  - **Versions View**: Filter and search versions (`/`), view metadata, release dates, required Java version, and launch with `[Enter]`.
  - **Settings View**: Interactively configure username, RAM (`-Xms`, `-Xmx`), JVM flags, and custom Java/game paths.
  - **Console Logs View**: Real-time Minecraft process output viewer with colorized logs, auto-scroll, and process termination.
  - **Game Directory Selector**: Easily switch between `~/.minecraft`, Prism Launcher instances, Flatpak directories, or custom folders.
- **CLI Companion**:
  - Use headless or in scripts via `--list`, `--launch`, and `--preview`.

---

## 🚀 Quick Start

### 1. Launch Interactive TUI
```bash
# Direct run
python3 /home/heaway/Dev/mc-tui/run.py

# Or via wrapper executable
/home/heaway/Dev/mc-tui/mc-tui
```

### 2. CLI Modes

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
| `[1]` `[2]` `[3]` `[4]` | Switch between **Versions**, **Settings**, **Console**, **Game Dir** |
| `[Tab]` | Cycle to next tab |
| `[↑]` / `[↓]` or `[k]` / `[j]` | Navigate lists or fields |
| `[Enter]` | Launch selected version / edit setting field |
| `[p]` | Preview full Java command and arguments |
| `[/]` | Filter versions by name |
| `[r]` | Refresh versions list / Reset settings to defaults |
| `[s]` | Save settings |
| `[Space]` | Toggle log auto-scroll (Console view) |
| `[k]` | Stop / Kill running Minecraft process (Console view) |
| `[c]` | Clear console logs |
| `[e]` | Enter custom path (Game Dir view) |
| `[q]` | Quit launcher |

---

## 📁 Project Structure

```
/home/heaway/Dev/mc-tui/
├── mc_tui/
│   ├── __init__.py
│   ├── config.py           # Configuration management (~/.config/mc-tui/config.json)
│   ├── java_detector.py    # Multi-version Java scanner and version matcher
│   ├── version_parser.py   # Version JSON parsing, inheritsFrom merger, maven resolver
│   ├── launcher.py         # Launch plan builder, native extractor, process controller
│   └── tui/
│       ├── __init__.py
│       ├── app.py          # Main curses event loop & controller
│       ├── ui_helpers.py   # Modals, color pairs, safe rendering, text prompts
│       └── views.py        # Tab views: versions, settings, console, directory picker
├── tests/
│   ├── test_config.py
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

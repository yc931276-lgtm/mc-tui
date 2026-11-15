"""Minecraft launch command builder and process controller."""
from __future__ import annotations

import collections
import os
import shlex
import subprocess
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from mc_tui import __version__ as MC_TUI_VERSION
from mc_tui.config import LOGS_DIR, Config
from mc_tui.java_detector import find_best_java
from mc_tui.version_parser import (
    VersionMeta,
    VersionScanner,
    evaluate_rules,
    get_current_arch,
    get_current_os,
    get_offline_uuid,
    maven_to_path,
)


@dataclass
class LaunchPlan:
    java_bin: str
    args: List[str]
    cwd: Path
    natives_dir: Path
    classpath: List[Path]
    main_class: str


class MinecraftProcess:
    def __init__(self, plan: LaunchPlan, log_callback: Optional[Callable[[str], None]] = None) -> None:
        self.plan = plan
        self.log_callback = log_callback
        self.process: Optional[subprocess.Popen] = None
        self.log_buffer: collections.deque[str] = collections.deque(maxlen=2000)
        self.is_running = False
        self.exit_code: Optional[int] = None
        self._thread: Optional[threading.Thread] = None
        self.log_file = LOGS_DIR / "latest.log"

    def start(self) -> None:
        """Launch the Minecraft process in a background thread and stream logs."""
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_fh = open(self.log_file, "w", encoding="utf-8")

        # Command
        cmd = [self.plan.java_bin] + self.plan.args
        self.process = subprocess.Popen(
            cmd,
            cwd=str(self.plan.cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        self.is_running = True

        def monitor() -> None:
            assert self.process is not None and self.process.stdout is not None
            try:
                for line in iter(self.process.stdout.readline, ""):
                    if not line:
                        break
                    line_clean = line.rstrip("\r\n")
                    self.log_buffer.append(line_clean)
                    log_fh.write(line_clean + "\n")
                    log_fh.flush()
                    if self.log_callback:
                        try:
                            self.log_callback(line_clean)
                        except Exception:
                            pass
            finally:
                self.process.stdout.close()
                self.exit_code = self.process.wait()
                self.is_running = False
                log_fh.close()

        self._thread = threading.Thread(target=monitor, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Terminate the running Minecraft process."""
        if self.process and self.is_running:
            try:
                self.process.terminate()
                # Wait briefly, then kill if not exited
                time.sleep(1)
                if self.process.poll() is None:
                    self.process.kill()
            except Exception:
                pass
            self.is_running = False


class Launcher:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.current_process: Optional[MinecraftProcess] = None

    def build_launch_plan(self, version_meta: VersionMeta) -> LaunchPlan:
        """Construct the launch plan for a given Minecraft version."""
        game_dir = self.config.game_dir
        if not game_dir.exists():
            raise FileNotFoundError(f"Game directory does not exist: {game_dir}")

        # If standalone JAR mode
        if version_meta.is_standalone_jar and version_meta.jar_path:
            return self._build_standalone_plan(version_meta.jar_path)

        scanner = VersionScanner(game_dir)
        v_data = scanner.resolve_version_tree(version_meta.id)

        # 1. Resolve Java runtime
        java_major = version_meta.java_major_version
        if not java_major and "javaVersion" in v_data:
            java_major = int(v_data["javaVersion"].get("majorVersion", 0))

        java_info = find_best_java(
            required_major=java_major if java_major > 0 else None,
            configured_path=self.config.java_path,
        )
        if not java_info:
            raise RuntimeError(
                f"No suitable Java found on system for Java major version {java_major}. "
                "Please configure a valid Java path in Settings, or install a JRE from the Settings tab."
            )
        java_bin = java_info.path

        # 2. Extract and resolve Natives directory
        version_id = v_data.get("id", version_meta.id)
        natives_dir = game_dir / "versions" / version_id / f"{version_id}-natives"
        natives_dir.mkdir(parents=True, exist_ok=True)

        # 3. Resolve Libraries and Classpath
        classpath_files: List[Path] = []
        libraries = v_data.get("libraries", [])
        libs_dir = game_dir / "libraries"
        current_os = get_current_os()
        current_arch = get_current_arch()

        for lib in libraries:
            # Check rules
            if not evaluate_rules(lib.get("rules"), current_os, current_arch):
                continue

            # Standard artifact
            lib_path: Optional[Path] = None
            downloads = lib.get("downloads", {})
            artifact = downloads.get("artifact")

            if artifact and "path" in artifact:
                lib_path = libs_dir / artifact["path"]
            elif "name" in lib:
                rel = maven_to_path(lib["name"])
                if rel:
                    lib_path = libs_dir / rel

            if lib_path and lib_path.is_file():
                if lib_path not in classpath_files:
                    classpath_files.append(lib_path)

            # Native classifiers
            natives_dict = lib.get("natives", {})
            classifier_key = natives_dict.get(current_os)
            if classifier_key:
                # May contain ${arch} placeholder
                classifier_key = classifier_key.replace("${arch}", "64" if current_arch == "x86_64" else "32")
                classifiers = downloads.get("classifiers", {})
                nat_artifact = classifiers.get(classifier_key)
                nat_path: Optional[Path] = None
                if nat_artifact and "path" in nat_artifact:
                    nat_path = libs_dir / nat_artifact["path"]
                elif "name" in lib:
                    # Append classifier to maven coordinate
                    coords = lib["name"].split(":")
                    if len(coords) >= 3:
                        coord_with_cls = f"{coords[0]}:{coords[1]}:{coords[2]}:{classifier_key}"
                        rel = maven_to_path(coord_with_cls)
                        if rel:
                            nat_path = libs_dir / rel

                if nat_path and nat_path.is_file():
                    # Extract native if needed
                    self._extract_natives(nat_path, natives_dir)
                    if nat_path not in classpath_files:
                        classpath_files.append(nat_path)

        # 4. Add Minecraft Version Client JAR
        jar_name = v_data.get("jar", version_id)
        version_jar = game_dir / "versions" / jar_name / f"{jar_name}.jar"
        if not version_jar.is_file():
            # Check in child version folder
            version_jar = game_dir / "versions" / version_id / f"{version_id}.jar"

        if version_jar.is_file():
            classpath_files.append(version_jar)

        # Classpath string
        cp_separator = ":" if current_os != "windows" else ";"
        classpath_str = cp_separator.join(str(p) for p in classpath_files)

        # 5. Template placeholders
        username = self.config.username.strip() or "Player"
        offline_uuid = get_offline_uuid(username)
        assets_dir = game_dir / "assets"
        asset_index = v_data.get("assetIndex", {}).get("id", v_data.get("assets", version_id))
        version_type = v_data.get("type", "release")

        tokens: Dict[str, str] = {
            "${auth_player_name}": username,
            "${version_name}": version_id,
            "${game_directory}": str(game_dir),
            "${assets_root}": str(assets_dir),
            "${assets_index_name}": str(asset_index),
            "${auth_uuid}": offline_uuid,
            "${auth_access_token}": "00000000000000000000000000000000",
            "${user_type}": "mojang",
            "${version_type}": str(version_type),
            "${natives_directory}": str(natives_dir),
            "${launcher_name}": "mc-tui",
            "${launcher_version}": MC_TUI_VERSION,
            "${classpath}": classpath_str,
            "${classpath_separator}": cp_separator,
            "${library_directory}": str(libs_dir),
            "${resolution_width}": str(self.config.get("window_width", 854)),
            "${resolution_height}": str(self.config.get("window_height", 480)),
            "${user_properties}": "{}",
        }

        # 6. Assemble JVM arguments
        jvm_args: List[str] = [
            f"-Xms{self.config.min_ram}",
            f"-Xmx{self.config.max_ram}",
        ]

        # Add custom JVM flags from user config
        custom_jvm = self.config.custom_jvm_args.strip()
        if custom_jvm:
            jvm_args.extend(shlex.split(custom_jvm))

        main_class = v_data.get("mainClass", "net.minecraft.client.main.Main")
        arguments = v_data.get("arguments")

        game_args: List[str] = []

        if isinstance(arguments, dict):
            # Modern arguments format
            # Process arguments.jvm
            for item in arguments.get("jvm", []):
                val_list = self._eval_arg_item(item, current_os, current_arch)
                for val in val_list:
                    jvm_args.append(self._substitute_tokens(val, tokens))

            # Process arguments.game
            for item in arguments.get("game", []):
                val_list = self._eval_arg_item(item, current_os, current_arch)
                for val in val_list:
                    game_args.append(self._substitute_tokens(val, tokens))

            # Ensure -cp is present in modern JVM arguments if not generated
            if not any(a == "-cp" or a == "-classpath" or a.startswith("-Djava.class.path") for a in jvm_args):
                jvm_args.extend(["-cp", classpath_str])

        elif "minecraftArguments" in v_data:
            # Legacy arguments format
            jvm_args.append(f"-Djava.library.path={natives_dir}")
            jvm_args.append("-Dminecraft.launcher.brand=mc-tui")
            jvm_args.append(f"-Dminecraft.launcher.version={MC_TUI_VERSION}")
            jvm_args.extend(["-cp", classpath_str])

            legacy_arg_str = v_data["minecraftArguments"]
            # Split and replace tokens
            for part in shlex.split(legacy_arg_str):
                game_args.append(self._substitute_tokens(part, tokens))

            # Add resolution if not specified
            width = str(self.config.get("window_width", 854))
            height = str(self.config.get("window_height", 480))
            if "--width" not in game_args:
                game_args.extend(["--width", width, "--height", height])
        else:
            # Fallback simple launch
            jvm_args.append(f"-Djava.library.path={natives_dir}")
            jvm_args.extend(["-cp", classpath_str])

        # Full argument list: [jvm_args, main_class, game_args]
        full_args = jvm_args + [main_class] + game_args

        return LaunchPlan(
            java_bin=java_bin,
            args=full_args,
            cwd=game_dir,
            natives_dir=natives_dir,
            classpath=classpath_files,
            main_class=main_class,
        )

    def _build_standalone_plan(self, jar_path: Path) -> LaunchPlan:
        """Construct launch plan for a standalone .jar file."""
        java_info = find_best_java(configured_path=self.config.java_path)
        if not java_info:
            raise RuntimeError("No Java runtime found on system.")

        jvm_args = [
            f"-Xms{self.config.min_ram}",
            f"-Xmx{self.config.max_ram}",
        ]
        custom_jvm = self.config.custom_jvm_args.strip()
        if custom_jvm:
            jvm_args.extend(shlex.split(custom_jvm))

        full_args = jvm_args + ["-jar", str(jar_path)]
        return LaunchPlan(
            java_bin=java_info.path,
            args=full_args,
            cwd=jar_path.parent,
            natives_dir=jar_path.parent,
            classpath=[jar_path],
            main_class="",
        )

    def _eval_arg_item(self, item: Any, current_os: str, current_arch: str) -> List[str]:
        """Process argument item which can be a string or a dict with rules and value."""
        if isinstance(item, str):
            return [item]
        elif isinstance(item, dict):
            rules = item.get("rules")
            if evaluate_rules(rules, current_os, current_arch):
                val = item.get("value", [])
                if isinstance(val, str):
                    return [val]
                elif isinstance(val, list):
                    return [str(v) for v in val]
        return []

    def _substitute_tokens(self, text: str, tokens: Dict[str, str]) -> str:
        for placeholder, replacement in tokens.items():
            if placeholder in text:
                text = text.replace(placeholder, replacement)
        return text

    def _extract_natives(self, zip_path: Path, target_dir: Path) -> None:
        """Extract shared libraries (.so, .dylib, .dll) from native jar into target directory."""
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    name = member.filename
                    if name.startswith("META-INF/") or member.is_dir():
                        continue
                    ext = os.path.splitext(name)[1].lower()
                    if ext in (".so", ".dylib", ".dll"):
                        dest = target_dir / Path(name).name
                        if not dest.exists():
                            with zf.open(member) as src, open(dest, "wb") as dst:
                                dst.write(src.read())
        except Exception:
            pass

    def launch(
        self,
        version_meta: VersionMeta,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> MinecraftProcess:
        """Build plan, start Minecraft process, and return handle."""
        plan = self.build_launch_plan(version_meta)
        proc = MinecraftProcess(plan, log_callback=log_callback)
        proc.start()
        self.current_process = proc
        self.config.set("last_version", version_meta.id)
        return proc

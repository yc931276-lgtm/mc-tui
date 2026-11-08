"""Configuration manager for MC-TUI."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

CONFIG_DIR = Path.home() / ".config" / "mc-tui"
CONFIG_FILE = CONFIG_DIR / "config.json"
LOGS_DIR = CONFIG_DIR / "logs"

DEFAULT_CONFIG: Dict[str, Any] = {
    "game_dir": str(Path.home() / ".minecraft"),
    "username": "Player",
    "min_ram": "1G",
    "max_ram": "4G",
    "java_path": "",
    "custom_jvm_args": "-XX:+UseG1GC",
    "window_width": 854,
    "window_height": 480,
    "last_version": "",
    "auto_detect_java": True,
}


class Config:
    def __init__(self, config_path: Path | str | None = None) -> None:
        self.config_path = Path(config_path) if config_path else CONFIG_FILE
        self.data: Dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        """Load configuration from disk if exists, otherwise save defaults."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    user_data = json.load(f)
                    if isinstance(user_data, dict):
                        self.data.update(user_data)
            except Exception:
                # Fallback to defaults on read error
                pass
        else:
            self.save()

    def save(self) -> None:
        """Save configuration to disk."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Warning: Failed to save config: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default if default is not None else DEFAULT_CONFIG.get(key))

    def set(self, key: str, value: Any, auto_save: bool = True) -> None:
        self.data[key] = value
        if auto_save:
            self.save()

    @property
    def game_dir(self) -> Path:
        return Path(os.path.expanduser(self.get("game_dir")))

    @game_dir.setter
    def game_dir(self, val: str | Path) -> None:
        self.set("game_dir", str(val))

    @property
    def username(self) -> str:
        return str(self.get("username", "Player"))

    @username.setter
    def username(self, val: str) -> None:
        self.set("username", val)

    @property
    def min_ram(self) -> str:
        return str(self.get("min_ram", "1G"))

    @min_ram.setter
    def min_ram(self, val: str) -> None:
        self.set("min_ram", val)

    @property
    def max_ram(self) -> str:
        return str(self.get("max_ram", "4G"))

    @max_ram.setter
    def max_ram(self, val: str) -> None:
        self.set("max_ram", val)

    @property
    def java_path(self) -> str:
        return str(self.get("java_path", ""))

    @java_path.setter
    def java_path(self, val: str) -> None:
        self.set("java_path", val)

    @property
    def custom_jvm_args(self) -> str:
        return str(self.get("custom_jvm_args", ""))

    @custom_jvm_args.setter
    def custom_jvm_args(self, val: str) -> None:
        self.set("custom_jvm_args", val)

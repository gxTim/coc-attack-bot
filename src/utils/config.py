"""
Config - Configuration management for the COC Attack Bot
"""

import json
import os
from typing import Any, Optional


class Config:
    """Configuration management with JSON file persistence"""

    DEFAULT_CONFIG_PATH = "config.json"

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self._data: dict = {}
        self._load_config()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_config(self) -> None:
        """Load configuration from file, or create defaults if missing."""
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}
        else:
            self._data = {}

    def _resolve(self, key: str) -> tuple:
        """
        Resolve a dotted key to (parent_dict, leaf_key).
        Creates intermediate dicts as needed.
        """
        parts = key.split(".")
        current = self._data
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        return current, parts[-1]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value using dot-notation keys."""
        parts = key.split(".")
        current = self._data
        for part in parts:
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value using dot-notation keys."""
        parent, leaf = self._resolve(key)
        parent[leaf] = value

    def set_and_save(self, key: str, value: Any) -> None:
        """Set a configuration value and immediately persist it to disk.

        Use this for critical settings that must survive an unexpected crash.
        """
        self.set(key, value)
        self.save_config()

    def save_config(self) -> None:
        """Persist current configuration to file."""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4, ensure_ascii=False)
        except OSError as e:
            # Non-fatal – config changes are held in memory for the session.
            print(f"[WARNING] Could not save config to {self.config_path}: {e}")

    # ------------------------------------------------------------------
    # Convenience accessors (used by example_usage.py and other modules)
    # ------------------------------------------------------------------

    def get_click_delay(self) -> float:
        """Return the configured click delay in seconds."""
        return float(self.get("bot.click_delay", 0.1))

    def get_playback_speed(self) -> float:
        """Return the playback speed multiplier."""
        return float(self.get("bot.playback_speed", 1.0))

    def is_failsafe_enabled(self) -> bool:
        """Return whether the pyautogui failsafe is enabled."""
        return bool(self.get("bot.failsafe", True))

    def get_hotkey(self, section: str, name: str) -> Optional[str]:
        """Return a hotkey string for the given section and name."""
        return self.get(f"hotkeys.{section}.{name}")

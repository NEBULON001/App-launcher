"""settings.py – Persistent user settings for AppLauncher.

Stores a small JSON file (``settings.json``) next to ``config.json``.
Reads merge with built-in defaults so newly added fields keep working on
old files that lack them.  All access is guarded by a lock so the
background update-checker thread and the UI thread can safely share a
single :class:`SettingsManager` instance.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

from paths import SETTINGS_FILE

_DEFAULT_SETTINGS: dict[str, Any] = {
    "auto_check_update": True,
    "show_splash": True,        # 是否显示开屏动画
    "glass_alpha": 0.62,        # 毛玻璃蒙版透明度 0.3-0.9
    "glass_blur_radius": 24,    # 毛玻璃模糊半径 5-50
}


# ---------------------------------------------------------------------------
# SettingsManager
# ---------------------------------------------------------------------------

class SettingsManager:
    """Thread-safe wrapper around the user settings JSON file.

    A single shared instance is exposed as :data:`settings` for convenience;
    both the UI thread and the updater background thread should use it.

    Reads merge with :data:`_DEFAULT_SETTINGS` so that keys missing from an
    older settings file fall back to their default values.  All read/write
    errors are swallowed – settings never crash the app.
    """

    def __init__(self, path: str = SETTINGS_FILE) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._data: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence (private)
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load the JSON file, merging defaults.  Silently ignores errors."""
        with self._lock:
            data: dict[str, Any] = dict(_DEFAULT_SETTINGS)
            try:
                if os.path.exists(self._path):
                    with open(self._path, "r", encoding="utf-8") as fh:
                        loaded = json.load(fh)
                    if isinstance(loaded, dict):
                        # Overlay stored values onto the defaults so that
                        # keys absent from an old file keep their defaults.
                        for key, value in loaded.items():
                            data[key] = value
            except Exception:
                # Corrupt / unreadable → fall back to defaults.
                data = dict(_DEFAULT_SETTINGS)
            self._data = data

    def save(self) -> None:
        """Persist the current settings to disk.  Silently ignores errors."""
        with self._lock:
            try:
                with open(self._path, "w", encoding="utf-8") as fh:
                    json.dump(self._data, fh, ensure_ascii=False, indent=2)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Return the setting *key*, or *default* if it is absent."""
        with self._lock:
            if key in self._data:
                return self._data[key]
            return default

    def set(self, key: str, value: Any) -> None:
        """Set *key* to *value* in memory.

        Call :meth:`save` afterwards to persist the change to disk.
        """
        with self._lock:
            self._data[key] = value


# Shared singleton instance used across the app.
settings = SettingsManager()

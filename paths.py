"""paths.py – Centralised data paths & cross-version persistence for AppLauncher.

All persistent data (config.json, settings.json, backups, version marker) lives
under a stable user data directory (``%APPDATA%\\AppLauncher\\``) so that it
survives PyInstaller onefile temporary directories and exe replacements.

Importing this module is side-effect safe and idempotent: it ensures the data
directory exists and migrates any legacy data files found next to the source /
executable.  Every operation is wrapped in try/except so the data layer can
never crash the main application.
"""

from __future__ import annotations

import datetime
import os
import shutil
import sys

# ---------------------------------------------------------------------------
# Constants – stable user data directory
# ---------------------------------------------------------------------------

APP_NAME = "AppLauncher"
DATA_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME
)
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
VERSION_FILE = os.path.join(DATA_DIR, "version.txt")  # 记录上次运行版本

# Files that participate in migration / snapshot / backup / restore.
_PERSISTED_FILES = ("config.json", "settings.json")


# ---------------------------------------------------------------------------
# Bundled resource paths (icons etc.)
# ---------------------------------------------------------------------------

def resource_path(relative_path: str) -> str:
    """Absolute path to a bundled resource (icon, image, ...).

    - Source run: relative to this module's directory (the launcher folder).
    - Frozen (PyInstaller onefile): relative to ``sys._MEIPASS`` -- the
      extracted temp dir where ``--add-data`` files are unpacked.

    Never raises; returns the joined path even if the file does not exist,
    so callers can decide how to handle a missing resource.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS  # type: ignore[union-attr]
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)


# Launcher icon shipped under icons/, bundled into the exe via --add-data.
ICON_FILE = resource_path("icons/app_launcher.ico")

# Opening-animation frame sequence shipped under assets/splash/.
SPLASH_FRAMES_DIR = resource_path("assets/splash")


# ---------------------------------------------------------------------------
# Directory bootstrap
# ---------------------------------------------------------------------------

def ensure_data_dir() -> None:
    """Create :data:`DATA_DIR` if missing.  Silently ignores errors."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Legacy data discovery & migration
# ---------------------------------------------------------------------------

def _legacy_dirs() -> list[str]:
    """Return candidate legacy data directories (next to source / executable).

    - Source run: the folder containing this module (the launcher folder).
    - Frozen (PyInstaller) run: also the folder containing the .exe, since
      ``__file__`` points at the ephemeral ``_MEIxxxxx`` temp dir.
    """
    dirs: list[str] = []
    try:
        dirs.append(os.path.dirname(os.path.abspath(__file__)))
    except Exception:  # noqa: BLE001
        pass
    if getattr(sys, "frozen", False):
        try:
            dirs.append(os.path.dirname(sys.executable))
        except Exception:  # noqa: BLE001
            pass
    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[str] = []
    for d in dirs:
        if d and d not in seen:
            seen.add(d)
            unique.append(d)
    return unique


def migrate_legacy_data() -> None:
    """Copy legacy config/settings into :data:`DATA_DIR` when missing.

    Only files whose destination does *not* already exist are copied – never
    overwriting current data.  Fully idempotent and silent on any error.
    """
    try:
        ensure_data_dir()
        for legacy_dir in _legacy_dirs():
            for fname in _PERSISTED_FILES:
                src = os.path.join(legacy_dir, fname)
                dst = os.path.join(DATA_DIR, fname)
                if os.path.exists(src) and not os.path.exists(dst):
                    shutil.copy2(src, dst)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Version tracking & snapshot-on-change
# ---------------------------------------------------------------------------

def get_last_version() -> str | None:
    """Return the version recorded at last run, or ``None`` if unknown."""
    try:
        if os.path.exists(VERSION_FILE):
            with open(VERSION_FILE, "r", encoding="utf-8") as fh:
                v = fh.read().strip()
                return v or None
    except Exception:  # noqa: BLE001
        pass
    return None


def set_last_version(v: str) -> None:
    """Persist *v* as the last-run version.  Silently ignores errors."""
    try:
        ensure_data_dir()
        with open(VERSION_FILE, "w", encoding="utf-8") as fh:
            fh.write(v)
    except Exception:  # noqa: BLE001
        pass


def snapshot_on_version_change(current_version: str) -> None:
    """Snapshot current data when the running version differs from last run.

    - First run (no recorded version): just record the version, no snapshot.
    - Version unchanged: no snapshot, no rewrite needed.
    - Version changed: copy the *current* config/settings into
      ``BACKUP_DIR/v{last}_{timestamp}/`` (skipping files that don't exist),
      then record the new version.

    All errors are swallowed.
    """
    try:
        last = get_last_version()
        if last is not None and last != current_version:
            ensure_data_dir()
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            subdir = os.path.join(BACKUP_DIR, f"v{last}_{timestamp}")
            os.makedirs(subdir, exist_ok=True)
            for fname in _PERSISTED_FILES:
                src = os.path.join(DATA_DIR, fname)
                if os.path.exists(src):
                    shutil.copy2(src, os.path.join(subdir, fname))
        set_last_version(current_version)
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Manual backup / restore
# ---------------------------------------------------------------------------

def backup_now(label: str | None = None) -> str | None:
    """Back up current config/settings into a labelled timestamped folder.

    Returns the backup folder name (basename), or ``None`` on failure.  If a
    config/settings file is absent it is skipped, but the backup folder is
    still created.
    """
    try:
        ensure_data_dir()
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"{label if label else 'manual'}_{timestamp}"
        subdir = os.path.join(BACKUP_DIR, name)
        os.makedirs(subdir, exist_ok=True)
        for fname in _PERSISTED_FILES:
            src = os.path.join(DATA_DIR, fname)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(subdir, fname))
        return name
    except Exception:  # noqa: BLE001
        return None


def list_backups() -> list[str]:
    """Return backup folder names under :data:`BACKUP_DIR`, newest first.

    Returns an empty list when the backup directory does not exist.
    """
    try:
        if not os.path.isdir(BACKUP_DIR):
            return []
        entries = [
            e for e in os.listdir(BACKUP_DIR)
            if os.path.isdir(os.path.join(BACKUP_DIR, e))
        ]
        entries.sort(
            key=lambda e: os.path.getmtime(os.path.join(BACKUP_DIR, e)),
            reverse=True,
        )
        return entries
    except Exception:  # noqa: BLE001
        return []


def restore_backup(name: str) -> bool:
    """Restore config/settings from ``BACKUP_DIR/{name}/`` into :data:`DATA_DIR`.

    Returns ``True`` if at least one file was restored.  Any error yields
    ``False``.  Existing files in :data:`DATA_DIR` are overwritten (the UI is
    responsible for user confirmation before calling this).
    """
    try:
        src_dir = os.path.join(BACKUP_DIR, name)
        if not os.path.isdir(src_dir):
            return False
        ensure_data_dir()
        restored = 0
        for fname in _PERSISTED_FILES:
            src = os.path.join(src_dir, fname)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(DATA_DIR, fname))
                restored += 1
        return restored > 0
    except Exception:  # noqa: BLE001
        return False


def open_data_dir() -> None:
    """Open the data directory in Windows Explorer.  Silently ignores errors."""
    try:
        os.startfile(DATA_DIR)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
# Module bootstrap – run once on import so any importer is migrated & ready.
# ---------------------------------------------------------------------------

ensure_data_dir()
migrate_legacy_data()

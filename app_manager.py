"""app_manager.py – Manages the list of registered applications.

Responsibilities:
- Load / save config.json (list of {name, path, icon}).
- Add an application from a path (resolves .lnk shortcuts via win32com).
- Remove an application by index.
- Launch one or all registered applications via subprocess.Popen.
"""

from __future__ import annotations

import json
import os
import subprocess
from typing import TypedDict

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

class AppEntry(TypedDict):
    name: str
    path: str  # resolved (real) executable path
    icon: str  # reserved for future use; empty string if unknown


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

from paths import CONFIG_FILE


# ---------------------------------------------------------------------------
# Helper – resolve .lnk shortcut
# ---------------------------------------------------------------------------

def _resolve_lnk(lnk_path: str) -> str:
    """Return the target path of a Windows .lnk shortcut.

    Falls back to the original path if resolution fails (e.g. win32com not
    available or the shortcut is broken).

    Args:
        lnk_path: Absolute path to the .lnk file.

    Returns:
        Resolved target path, or *lnk_path* on failure.
    """
    try:
        import pythoncom  # type: ignore[import]
        from win32com.client import Dispatch  # type: ignore[import]

        pythoncom.CoInitialize()
        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(lnk_path)
        target: str = shortcut.Targetpath
        if target and os.path.exists(target):
            return target
    except Exception:
        pass
    return lnk_path


# ---------------------------------------------------------------------------
# AppManager
# ---------------------------------------------------------------------------

class AppManager:
    """Manages a list of launchable applications backed by *config.json*.

    Typical usage::

        mgr = AppManager()
        mgr.add_app("C:/path/to/app.exe")
        mgr.launch_all()
    """

    def __init__(self) -> None:
        self._apps: list[AppEntry] = []
        self._lnk_cache: dict[str, str] = {}  # norm exe path → lnk display name
        self._lnk_cache_built: bool = False
        self._load()

    # ------------------------------------------------------------------
    # Public API – read
    # ------------------------------------------------------------------

    @property
    def apps(self) -> list[AppEntry]:
        """Return a *copy* of the current app list (read-only snapshot)."""
        return list(self._apps)

    # ------------------------------------------------------------------
    # Public API – write
    # ------------------------------------------------------------------

    def add_app(self, raw_path: str) -> AppEntry:
        """Register a new application.

        If *raw_path* points to a ``.lnk`` shortcut, the real target is
        resolved automatically.

        Args:
            raw_path: Path selected by the user (may be ``.exe`` or ``.lnk``).

        Returns:
            The newly created :class:`AppEntry`.

        Raises:
            FileNotFoundError: If the resolved path does not exist.
            ValueError: If the application is already registered.
        """
        ext = os.path.splitext(raw_path)[1].lower()
        resolved_path: str = _resolve_lnk(raw_path) if ext == ".lnk" else raw_path

        if not os.path.exists(resolved_path):
            raise FileNotFoundError(
                f"Cannot find executable: {resolved_path!r}"
            )

        # Prevent duplicates (compare by resolved path, case-insensitive on Windows)
        normalized = resolved_path.lower()
        for existing in self._apps:
            if existing["path"].lower() == normalized:
                raise ValueError(
                    f"Application already registered: {resolved_path!r}"
                )

        # Determine display name: prefer the shortcut's file name over the
        # executable's file name (e.g. "微信.lnk" → "微信", not "WeChat").
        if ext == ".lnk":
            # User selected a shortcut → use the shortcut's file name (drop .lnk).
            name: str = os.path.splitext(os.path.basename(raw_path))[0]
        else:
            # User selected the executable → look for a matching .lnk shortcut
            # in common locations; fall back to the exe file name if none matches.
            lnk_name = self._find_lnk_name_for_exe(resolved_path)
            name = lnk_name if lnk_name else os.path.splitext(
                os.path.basename(resolved_path)
            )[0]
        entry: AppEntry = {"name": name, "path": resolved_path, "icon": ""}
        self._apps.append(entry)
        self._save()
        return entry

    def remove_app(self, index: int) -> None:
        """Remove the application at *index*.

        Args:
            index: Zero-based index into :attr:`apps`.

        Raises:
            IndexError: If *index* is out of range.
        """
        if index < 0 or index >= len(self._apps):
            raise IndexError(f"App index out of range: {index}")
        del self._apps[index]
        self._save()

    def move_app(self, from_index: int, to_index: int) -> None:
        """Move the app at *from_index* so that it ends up at position *to_index*.

        *to_index* is the desired final position (0-based, i.e. insert before
        that position).  Indices are clamped to valid ranges; a no-op when
        *from_index == to_index* or out of range.
        """
        n = len(self._apps)
        if from_index < 0 or from_index >= n or from_index == to_index:
            return
        item = self._apps.pop(from_index)
        # After popping, if we removed an element before the target, the target
        # shifts down by one.
        if from_index < to_index:
            to_index -= 1
        to_index = max(0, min(to_index, len(self._apps)))
        self._apps.insert(to_index, item)
        self._save()

    # ------------------------------------------------------------------
    # Public API – launch
    # ------------------------------------------------------------------

    def launch_app(self, index: int) -> None:
        """Launch the application at *index*.

        The process is started with its containing directory as *cwd* so that
        apps that load resources relative to their own location work correctly.

        Args:
            index: Zero-based index into :attr:`apps`.

        Raises:
            IndexError: If *index* is out of range.
            FileNotFoundError: If the executable no longer exists on disk.
        """
        if index < 0 or index >= len(self._apps):
            raise IndexError(f"App index out of range: {index}")
        entry = self._apps[index]
        path = entry["path"]
        if not os.path.exists(path):
            raise FileNotFoundError(f"Executable not found: {path!r}")
        cwd = os.path.dirname(path)
        subprocess.Popen([path], cwd=cwd)  # noqa: S603

    def launch_all(self) -> list[tuple[int, Exception]]:
        """Launch every registered application.

        Returns:
            A list of ``(index, exception)`` pairs for apps that failed to
            start.  An empty list means full success.
        """
        errors: list[tuple[int, Exception]] = []
        for i in range(len(self._apps)):
            try:
                self.launch_app(i)
            except Exception as exc:  # noqa: BLE001
                errors.append((i, exc))
        return errors

    # ------------------------------------------------------------------
    # Persistence (private)
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load *config.json* from disk; silently start with an empty list on failure."""
        if not os.path.exists(CONFIG_FILE):
            self._apps = []
            return
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, list):
                self._apps = [
                    AppEntry(
                        name=str(item.get("name", "")),
                        path=str(item.get("path", "")),
                        icon=str(item.get("icon", "")),
                    )
                    for item in data
                    if isinstance(item, dict)
                ]
            else:
                self._apps = []
        except Exception:  # noqa: BLE001
            self._apps = []

    def _save(self) -> None:
        """Persist the current app list to *config.json*."""
        with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
            json.dump(self._apps, fh, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Private helpers – shortcut name lookup
    # ------------------------------------------------------------------

    def _find_lnk_name_for_exe(self, exe_path: str) -> str | None:
        """Return the display name of a .lnk whose target matches *exe_path*.

        Scans the user's desktop, public desktop, and both Start Menu
        ``Programs`` folders for ``.lnk`` files.  Each shortcut's target is
        resolved via :func:`_resolve_lnk` and compared (case-insensitive,
        after :func:`os.path.realpath`) to *exe_path*.

        Results are cached on the instance: the first call performs the full
        scan, subsequent calls are dictionary lookups.

        Args:
            exe_path: Absolute path to the real executable.

        Returns:
            The shortcut's display name (``.lnk`` extension removed) when a
            matching shortcut is found, otherwise ``None``.
        """
        key = os.path.normcase(os.path.realpath(exe_path))
        if not self._lnk_cache_built:
            self._populate_lnk_cache()
            self._lnk_cache_built = True
        return self._lnk_cache.get(key)

    def _populate_lnk_cache(self) -> None:
        """Scan common shortcut locations and fill ``self._lnk_cache``.

        Searches (recursively) the user desktop, public desktop, system Start
        Menu and user Start Menu.  Broken shortcuts and missing directories
        are silently skipped.
        """
        search_dirs = [
            os.path.join(os.path.expanduser("~"), "Desktop"),
            os.path.join(
                os.environ.get("PUBLIC", "C:\\Users\\Public"), "Desktop"
            ),
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
            os.path.join(
                os.environ.get("APPDATA", ""),
                "Microsoft",
                "Windows",
                "Start Menu",
                "Programs",
            ),
        ]
        for directory in search_dirs:
            if not os.path.isdir(directory):
                continue
            for root, _dirs, files in os.walk(directory):
                for fname in files:
                    if not fname.lower().endswith(".lnk"):
                        continue
                    lnk_path = os.path.join(root, fname)
                    target = _resolve_lnk(lnk_path)
                    if not target or target == lnk_path:
                        # Resolution failed (broken shortcut) → skip.
                        continue
                    norm_target = os.path.normcase(os.path.realpath(target))
                    display_name = os.path.splitext(fname)[0]
                    # First match wins; don't overwrite existing entries.
                    if norm_target not in self._lnk_cache:
                        self._lnk_cache[norm_target] = display_name

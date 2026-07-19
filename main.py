"""main.py – Entry point for AppLauncher.

Single-instance enforcement via a Windows named mutex:
  Only one AppLauncher process is allowed per user session.
  If a second instance is launched it finds the existing window,
  brings it to the foreground, and exits immediately.

Start-up sequence:
1. Try to create the named mutex.
   - If *fail* (already exists) → find & raise existing window → exit.
   - If *ok*   → we are the master instance.
2. Create the hidden root Tk window.
3. Show the splash animation (non-blocking).
4. Build the main UI (:class:`~ui.LauncherApp`).
5. Enter the Tk event loop.
"""

from __future__ import annotations

import ctypes
import os
import sys
import tkinter as tk

# ---------------------------------------------------------------------------
# Single-instance lock: Windows named mutex
# ---------------------------------------------------------------------------

_MUTEX_NAME = "Global\\AppLauncher_SingleInstance"


def _try_become_master() -> bool:
    """Create the named mutex.  Return True if we are the first instance."""
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)
    if not handle:
        return False
    # ERROR_ALREADY_EXISTS == 183
    return ctypes.windll.kernel32.GetLastError() != 183  # type: ignore[attr-defined]


def _find_and_raise_window() -> None:
    """Find the existing AppLauncher window and bring it to the foreground."""
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    # Search by window title; class name is unreliable with Tk.
    hwnd = user32.FindWindowW(None, "AppLauncher")
    if not hwnd:
        # Fallback: enumerate top-level windows looking for the title
        def _enum_proc(h, _extra):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(h, buf, 256)
            if buf.value == "AppLauncher":
                nonlocal hwnd
                hwnd = h
                return False  # stop enumeration
            return True

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(EnumWindowsProc(_enum_proc), 0)

    if hwnd:
        try:
            # Always restore/show: SW_RESTORE both un-minimizes and reveals a
            # withdrawn (root.withdraw) window; safe for already-visible windows.
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            # Bring to front
            user32.SetForegroundWindow(hwnd)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Application entry point."""
    # 1. Single-instance check
    if not _try_become_master():
        # Another instance is running – wake it up and exit
        _find_and_raise_window()
        sys.exit(0)

    # Version snapshot: record version, snapshot current data on version change.
    # Must run before show_splash, which imports settings and triggers the
    # singleton load.  Legacy migration already happened when paths was imported.
    from paths import snapshot_on_version_change  # noqa: PLC0415
    from updater import CURRENT_VERSION  # noqa: PLC0415
    snapshot_on_version_change(CURRENT_VERSION)

    # 2. We are the master instance – build the app
    root = tk.Tk()
    root.withdraw()  # hide until UI is ready

    # Set the app icon on the root window as early as possible: the splash,
    # main window, and every child Toplevel (settings / launch-all /
    # update dialog) all inherit the root icon.  A missing icon file must
    # never block startup -- fall back to the Tk default silently.
    try:
        from paths import ICON_FILE  # noqa: PLC0415
        if os.path.exists(ICON_FILE):
            root.iconbitmap(ICON_FILE)
    except Exception:  # noqa: BLE001
        pass

    # 3. Show splash (non-blocking – uses root.after() callbacks).
    def _on_splash_done() -> None:
        """Build the main UI after the splash animation ends."""
        from ui import LauncherApp  # noqa: PLC0415
        LauncherApp(root)
        try:
            root.deiconify()
            root.lift()
            root.focus_force()
            root.attributes("-topmost", True)
            root.after(100, lambda: root.attributes("-topmost", False))
        except Exception:  # noqa: BLE001
            pass

    try:
        from splash_animation import show_splash  # noqa: PLC0415
        show_splash(root, callback=_on_splash_done)
    except Exception:  # noqa: BLE001
        # Splash failed – build UI directly as fallback
        _on_splash_done()

    root.mainloop()


if __name__ == "__main__":
    main()

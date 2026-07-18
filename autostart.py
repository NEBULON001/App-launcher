"""autostart.py – Register / deregister the launcher in Windows autostart.

Uses the registry key:
    HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run

The presence of the value ``AppLauncher`` under that key makes Windows launch
the application on user log-in.
"""

from __future__ import annotations

import os
import sys

# Registry constants live in winreg (stdlib on Windows).
try:
    import winreg  # type: ignore[import]
except ImportError:
    winreg = None  # type: ignore[assignment]  # non-Windows fallback

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_REG_KEY_PATH: str = r"Software\Microsoft\Windows\CurrentVersion\Run"
_VALUE_NAME: str = "AppLauncher"


def _get_launch_command() -> str:
    """Return the command line that should be stored in the registry.

    We store ``<python_exe> <script_path>`` so the launcher starts with the
    current interpreter.
    """
    python_exe: str = sys.executable
    # Use the main.py entry point located in the same directory as this file.
    script_path: str = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "main.py"
    )
    return f'"{python_exe}" "{script_path}"'


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_autostart_enabled() -> bool:
    """Return *True* if ``AppLauncher`` is registered for autostart.

    Returns:
        *True* when the registry value exists, *False* otherwise (including on
        non-Windows systems where *winreg* is unavailable).
    """
    if winreg is None:
        return False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _REG_KEY_PATH, 0, winreg.KEY_READ
        ) as key:
            winreg.QueryValueEx(key, _VALUE_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable_autostart() -> None:
    """Write the autostart registry entry.

    Raises:
        OSError: If the registry key cannot be opened or written.
        RuntimeError: If *winreg* is not available (non-Windows).
    """
    if winreg is None:
        raise RuntimeError("winreg is not available on this platform.")
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        _REG_KEY_PATH,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        winreg.SetValueEx(key, _VALUE_NAME, 0, winreg.REG_SZ, _get_launch_command())


def disable_autostart() -> None:
    """Remove the autostart registry entry (no-op if it does not exist).

    Raises:
        OSError: If the registry key cannot be opened.
        RuntimeError: If *winreg* is not available (non-Windows).
    """
    if winreg is None:
        raise RuntimeError("winreg is not available on this platform.")
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _REG_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, _VALUE_NAME)
    except FileNotFoundError:
        pass  # Value did not exist – that is fine.


def set_autostart(enabled: bool) -> None:
    """Convenience wrapper: enable or disable autostart in one call.

    Args:
        enabled: Pass *True* to register, *False* to deregister.
    """
    if enabled:
        enable_autostart()
    else:
        disable_autostart()

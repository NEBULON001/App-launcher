"""tray.py – System-tray integration using pystray + Pillow.

Provides a single :func:`setup_tray` function that creates the tray icon,
runs it in a background thread, and wires up the menu / double-click handlers.
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from typing import Callable

from PIL import Image, ImageDraw

from paths import ICON_FILE


# ---------------------------------------------------------------------------
# Tray icon image (programmatically generated – no external file needed)
# ---------------------------------------------------------------------------

def _make_icon_image(size: int = 64) -> Image.Image:
    """Create a simple rocket/launcher icon as a PIL Image.

    Args:
        size: Width/height of the square icon in pixels.

    Returns:
        A PIL :class:`~PIL.Image.Image` in RGBA mode.
    """
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Background circle
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=(30, 30, 46, 255),   # #1e1e2e
    )

    # Lightning-bolt / "A" letter as a simple triangle rocket shape
    cx = size // 2
    # Rocket body (filled rounded rectangle approximation via polygon)
    rocket_pts = [
        (cx, margin + 6),            # nose
        (cx + 10, size - margin - 10),  # bottom-right
        (cx, size - margin - 4),     # tail centre
        (cx - 10, size - margin - 10),  # bottom-left
    ]
    draw.polygon(rocket_pts, fill=(137, 180, 250, 255))  # #89b4fa (blue)

    # Exhaust flame
    flame_pts = [
        (cx - 5, size - margin - 10),
        (cx + 5, size - margin - 10),
        (cx, size - margin + 4),
    ]
    draw.polygon(flame_pts, fill=(250, 179, 135, 255))  # #fab387 (orange)

    return img


def _load_tray_icon() -> Image.Image:
    """Load the bundled app icon for the tray; fall back if unavailable.

    Tries to open the shipped ``icons/app_launcher.ico``.  If the file is
    missing or unreadable (e.g. not bundled correctly), falls back to the
    programmatically generated icon so the tray always has *something*.
    """
    try:
        if ICON_FILE and os.path.exists(ICON_FILE):
            return Image.open(ICON_FILE)
    except Exception:  # noqa: BLE001
        pass
    return _make_icon_image()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def setup_tray(
    root: tk.Tk,
    on_show: Callable[[], None],
    on_quit: Callable[[], None],
) -> None:
    """Create and start the system-tray icon in a daemon thread.

    Args:
        root:     The main Tkinter window (used to schedule ``on_show`` /
                  ``on_quit`` on the Tk thread via ``root.after``).
        on_show:  Callback invoked when the user double-clicks the tray icon
                  or selects "显示" from the context menu.
        on_quit:  Callback invoked when the user selects "退出" from the
                  context menu.
    """
    import pystray  # type: ignore[import]

    icon_image = _load_tray_icon()

    def _on_show_action(icon: pystray.Icon, item: pystray.MenuItem) -> None:  # noqa: ARG001
        root.after(0, on_show)

    def _on_quit_action(icon: pystray.Icon, item: pystray.MenuItem) -> None:  # noqa: ARG001
        icon.stop()
        root.after(0, on_quit)

    # Build context menu
    menu = pystray.Menu(
        pystray.MenuItem("显示", _on_show_action, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", _on_quit_action),
    )

    icon = pystray.Icon(
        name="AppLauncher",
        icon=icon_image,
        title="AppLauncher",
        menu=menu,
    )

    # pystray.Icon.run() blocks; run it in a daemon thread so it doesn't
    # prevent the process from exiting when Tkinter closes.
    thread = threading.Thread(target=icon.run, daemon=True, name="tray-thread")
    thread.start()

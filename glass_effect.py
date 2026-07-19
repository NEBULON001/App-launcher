"""glass_effect.py – Frosted-glass (Acrylic / blur-behind) effect helper.

Three-level degradation strategy (Windows):

  Level 1 – Win11 22H2+ (DwmSetWindowAttribute DWMWA_SYSTEMBACKDROP_TYPE=2):
      Native Mica/Acrylic compositor effect; truly transparent backdrop.
      Works only on Windows 11 Build 22621+ with DWM.

  Level 2 – Win10 / older Win11 (SetWindowCompositionAttribute + AccentPolicy):
      ACCENT_ENABLE_ACRYLICBLURBEHIND (state=4) with tint color + opacity.
      Applies a coloured acrylic blur via the undocumented WCA API.

  Level 3 – Software fallback (PIL screenshot + Gaussian blur):
      Grabs the area behind the window with PIL ImageGrab, applies a Gaussian
      blur and a dark semi-transparent tint, then renders the result onto a
      tk.Label that fills the window background.
      Re-captures automatically when the window moves.

Public API
----------
apply_glass(
    window,
    tint_color="#0d0d1a",
    tint_alpha=0.62,
    blur_radius=24,
) -> None
    Apply the best available glass effect to *window* (a tk.Tk or tk.Toplevel).
    Must be called after the window is shown and positioned.

remove_glass(widget) -> None
    Remove any applied glass effect and restore a solid background.

show_in_taskbar(widget) -> None
    Ensure a borderless (``overrideredirect(True)``) window gets a taskbar
    button by setting ``WS_EX_APPWINDOW`` (and clearing ``WS_EX_TOOLWINDOW``)
    on the extended window style, then forcing a frame change so the shell
    picks it up.  Safe to call before the window is first shown.  Never raises.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
import tkinter as tk
from typing import Optional

# ---------------------------------------------------------------------------
# DWM / Win32 library handles (lazily initialised, never crash on import)
# ---------------------------------------------------------------------------

_dwm: Optional[ctypes.WinDLL] = None
_user32: Optional[ctypes.WinDLL] = None


def _get_dwm() -> Optional[ctypes.WinDLL]:
    global _dwm
    if _dwm is None:
        try:
            _dwm = ctypes.windll.dwmapi  # type: ignore[attr-defined]
        except Exception:
            _dwm = None
    return _dwm


def _get_user32() -> Optional[ctypes.WinDLL]:
    global _user32
    if _user32 is None:
        try:
            _user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        except Exception:
            _user32 = None
    return _user32


def _hwnd(widget: tk.Widget) -> int:
    """Return the Win32 HWND for *widget*.

    On some Tk builds the widget's own id is a child; GetParent gives the
    top-level frame handle that DWM APIs expect.
    """
    try:
        parent = ctypes.windll.user32.GetParent(widget.winfo_id())  # type: ignore[attr-defined]
        return int(parent) if parent else int(widget.winfo_id())
    except Exception:
        return int(widget.winfo_id())


# ---------------------------------------------------------------------------
# Level 1 – Win11 22H2+ native Acrylic / Mica
# ---------------------------------------------------------------------------

# DwmSetWindowAttribute attribute constants
DWMWA_USE_IMMERSIVE_DARK_MODE: int = 20
DWMWA_SYSTEMBACKDROP_TYPE: int = 38      # Win11 22H2+ (Build 22621+)
DWMWA_MICA_EFFECT: int = 1029            # Older Win11 insider builds

# DWMSBT_* values for DWMWA_SYSTEMBACKDROP_TYPE
DWMSBT_DISABLE: int = 1
DWMSBT_MAINWINDOW: int = 2          # Mica – suited to main windows
DWMSBT_TRANSIENTWINDOW: int = 3     # Acrylic – suited to transient/pop-up
DWMSBT_TABBEDWINDOW: int = 4        # Tabbed Mica


def _try_win11_acrylic(hwnd: int) -> bool:
    """Attempt Win11 22H2+ DWMWA_SYSTEMBACKDROP_TYPE = DWMSBT_TRANSIENTWINDOW.

    Returns True on success, False on any failure.
    """
    dwm = _get_dwm()
    if dwm is None:
        return False
    try:
        value = ctypes.c_int(DWMSBT_TRANSIENTWINDOW)
        result: int = dwm.DwmSetWindowAttribute(
            hwnd,
            DWMWA_SYSTEMBACKDROP_TYPE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        return result == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Level 2 – Win10 / older Win11: SetWindowCompositionAttribute + AccentPolicy
# ---------------------------------------------------------------------------

# AccentState values
ACCENT_DISABLED: int = 0
ACCENT_ENABLE_GRADIENT: int = 1
ACCENT_ENABLE_TRANSPARENTGRADIENT: int = 2
ACCENT_ENABLE_BLURBEHIND: int = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND: int = 4   # Win10 1803+ Acrylic
ACCENT_INVALID_STATE: int = 5

# SetWindowCompositionAttribute attribute id
WCA_ACCENT_POLICY: int = 19


class _ACCENTPOLICY(ctypes.Structure):  # noqa: N801
    """Accent policy structure for SetWindowCompositionAttribute."""

    _fields_ = [
        ("AccentState", ctypes.c_uint),
        ("AccentFlags", ctypes.c_uint),
        ("GradientColor", ctypes.c_uint),   # ABGR packed colour + alpha
        ("AnimationId", ctypes.c_uint),
    ]


class _WINCOMPATTRDATA(ctypes.Structure):  # noqa: N801
    """Data envelope for SetWindowCompositionAttribute."""

    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.POINTER(ctypes.c_int)),
        ("SizeOfData", ctypes.c_size_t),
    ]


def _try_accent_acrylic(hwnd: int, tint_hex: str, tint_alpha: float) -> bool:
    """Use SetWindowCompositionAttribute to apply ACCENT_ENABLE_ACRYLICBLURBEHIND.

    The GradientColor field carries a packed ABGR value that controls the tint
    colour and its opacity.  We derive the alpha byte from *tint_alpha*.

    Args:
        hwnd:       Win32 window handle.
        tint_hex:   Tint colour as ``"#rrggbb"`` string.
        tint_alpha: Tint opacity in [0.0, 1.0]; used as alpha byte.

    Returns:
        True on success, False on any failure.
    """
    try:
        user32 = _get_user32()
        if user32 is None:
            return False

        # Decode hex colour to R, G, B
        h = tint_hex.lstrip("#")
        r: int = int(h[0:2], 16)
        g: int = int(h[2:4], 16)
        b: int = int(h[4:6], 16)
        a: int = int(tint_alpha * 255)

        # Pack as 0xAABBGGRR (little-endian ABGR)
        gradient_color: int = (a << 24) | (b << 16) | (g << 8) | r

        policy = _ACCENTPOLICY()
        policy.AccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND
        policy.AccentFlags = 0
        policy.GradientColor = gradient_color
        policy.AnimationId = 0

        data = _WINCOMPATTRDATA()
        data.Attribute = WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.byref(policy), ctypes.POINTER(ctypes.c_int))
        data.SizeOfData = ctypes.sizeof(policy)

        result: int = user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data))
        return bool(result)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Level 3 – Software blur (PIL screenshot + Gaussian blur + tint)
# ---------------------------------------------------------------------------

_PIL_AVAILABLE: bool = False
try:
    from PIL import Image, ImageFilter, ImageGrab, ImageTk  # type: ignore[import]
    _PIL_AVAILABLE = True
except ImportError:
    pass


def _hex_to_rgba(hex_color: str, alpha: int) -> tuple:
    """Convert ``"#rrggbb"`` hex string to an ``(r, g, b, alpha)`` tuple."""
    h = hex_color.lstrip("#")
    r: int = int(h[0:2], 16)
    g: int = int(h[2:4], 16)
    b: int = int(h[4:6], 16)
    return (r, g, b, alpha)


def _capture_blurred_photo(
    x: int,
    y: int,
    w: int,
    h: int,
    tint_color: str,
    tint_alpha: float,
    blur_radius: int,
) -> Optional[object]:
    """Grab the screen region (x, y, w, h), blur it, apply tint.

    Returns an ``ImageTk.PhotoImage`` object or ``None`` on failure.
    The caller must keep the returned object alive (store as attribute) to
    prevent garbage collection.
    """
    if not _PIL_AVAILABLE:
        return None
    try:
        from PIL import Image, ImageFilter, ImageGrab, ImageTk  # type: ignore[import]

        screenshot = ImageGrab.grab(bbox=(x, y, x + w, y + h))
        if screenshot is None:
            return None

        # Apply Gaussian blur
        blurred = screenshot.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        # Composite dark tint overlay
        tint_img = Image.new(
            "RGBA",
            (w, h),
            _hex_to_rgba(tint_color, int(tint_alpha * 255)),
        )
        base = blurred.convert("RGBA")
        base.alpha_composite(tint_img)
        final = base.convert("RGB")

        return ImageTk.PhotoImage(final)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Per-widget state registry
# ---------------------------------------------------------------------------

class _GlassState:
    """Tracks runtime state for a single glass-effect window."""

    __slots__ = (
        "level",           # int: 1, 2, or 3
        "bg_label",        # Optional[tk.Label]: Level 3 background label
        "photo",           # Optional[ImageTk.PhotoImage]: kept alive
        "tint_color",      # str
        "tint_alpha",      # float
        "blur_radius",     # int
        "move_bind_id",    # Optional[str]: <Configure> bind id for auto-update
    )

    def __init__(
        self,
        level: int,
        tint_color: str,
        tint_alpha: float,
        blur_radius: int,
    ) -> None:
        self.level: int = level
        self.bg_label: Optional[tk.Label] = None
        self.photo: Optional[object] = None
        self.tint_color: str = tint_color
        self.tint_alpha: float = tint_alpha
        self.blur_radius: int = blur_radius
        self.move_bind_id: Optional[str] = None


# Map widget id() → _GlassState
_registry: dict[int, _GlassState] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def show_in_taskbar(widget: tk.Widget) -> None:
    """Ensure *widget*'s top-level window shows a taskbar button.

    Borderless (``overrideredirect(True)``) windows are ``WS_POPUP`` and have
    no taskbar button by default, so a running launcher is invisible on the
    taskbar.  This clears ``WS_EX_TOOLWINDOW`` and sets ``WS_EX_APPWINDOW`` on
    the extended style, then forces a frame change (``SWP_FRAMECHANGED``) so
    the shell refreshes its taskbar entry.  Safe to call before the window is
    first shown.  Never raises — styling failures must not crash the launcher.
    """
    try:
        user32 = _get_user32()
        if user32 is None:
            return
        hwnd = _hwnd(widget)

        # 64-bit-safe prototypes: c_long truncates pointers on x64.
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [
            ctypes.wintypes.HWND,
            ctypes.c_int,
            ctypes.c_ssize_t,
        ]

        GWL_EXSTYLE = -20
        WS_EX_APPWINDOW = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080

        ex = user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
        ex = (ex & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
        user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex)

        # Force the taskbar/shell to notice the style change.
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        SWP_NOACTIVATE = 0x0010
        SWP_FRAMECHANGED = 0x0020
        flags = (
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
        )
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, flags)
    except Exception:
        pass


def apply_glass(
    window: tk.Widget,
    tint_color: str = "#0d0d1a",
    tint_alpha: float = 0.62,
    blur_radius: int = 24,
) -> None:
    """Apply the best available frosted-glass effect to *window*.

    Tries three strategies in order:

    1. Win11 22H2+ ``DwmSetWindowAttribute`` with
       ``DWMWA_SYSTEMBACKDROP_TYPE = DWMSBT_TRANSIENTWINDOW``.
    2. Win10 / older Win11 ``SetWindowCompositionAttribute`` +
       ``AccentPolicy(ACCENT_ENABLE_ACRYLICBLURBEHIND)``.
    3. Software PIL screenshot + Gaussian blur + tint ``tk.Label``,
       with automatic update on window move.

    All ``ctypes`` calls are wrapped in ``try/except``; the function will
    never raise.

    Args:
        window:      The ``tk.Tk`` or ``tk.Toplevel`` to style.
        tint_color:  Hex colour for the dark tint overlay (e.g. ``"#0d0d1a"``).
        tint_alpha:  Opacity of the tint overlay in [0.0, 1.0].
        blur_radius: Blur radius for the Level-3 software fallback (pixels).
    """
    wid: int = id(window)

    # Remove any previously applied effect before re-applying
    if wid in _registry:
        remove_glass(window)

    state = _GlassState(
        level=0,
        tint_color=tint_color,
        tint_alpha=tint_alpha,
        blur_radius=blur_radius,
    )
    _registry[wid] = state

    # Ensure geometry is resolved
    window.update_idletasks()

    # Set window background to near-black; DWM will composite over it
    try:
        window.configure(bg="#000000")
    except Exception:
        pass

    hwnd: int = _hwnd(window)

    # --- Level 1: Win11 22H2+ native Acrylic ---
    if _try_win11_acrylic(hwnd):
        state.level = 1
        return

    # --- Level 2: Win10 SetWindowCompositionAttribute Acrylic ---
    if _try_accent_acrylic(hwnd, tint_color, tint_alpha):
        state.level = 2
        return

    # --- Level 3: Software blur ---
    state.level = 3
    _apply_software_blur(window, state)

    # Bind <Configure> to auto-update blur on window move / resize
    try:
        bind_id: str = window.bind("<Configure>", lambda e, w=window, s=state: _on_window_move(w, s))
        state.move_bind_id = bind_id
    except Exception:
        pass


def _apply_software_blur(window: tk.Widget, state: _GlassState) -> None:
    """Capture, blur, tint, and set as background Label for *window*."""
    if not _PIL_AVAILABLE:
        # Absolute last resort: solid semi-transparent colour
        try:
            window.configure(bg=state.tint_color)
            window.attributes("-alpha", max(0.4, 1.0 - state.tint_alpha * 0.5))  # type: ignore[arg-type]
        except Exception:
            pass
        return

    try:
        window.update_idletasks()
        x: int = window.winfo_x()
        y: int = window.winfo_y()
        w: int = window.winfo_width()
        h: int = window.winfo_height()

        if w < 10 or h < 10:
            return

        photo = _capture_blurred_photo(
            x, y, w, h, state.tint_color, state.tint_alpha, state.blur_radius
        )
        if photo is None:
            return

        # Destroy previous bg label if one exists (for re-capture after move)
        if state.bg_label is not None:
            try:
                state.bg_label.destroy()
            except Exception:
                pass
            state.bg_label = None

        bg_label = tk.Label(window, image=photo, bd=0)  # type: ignore[arg-type]
        bg_label.image = photo  # type: ignore[attr-defined]  # keep reference alive
        bg_label.place(x=0, y=0, relwidth=1, relheight=1)
        bg_label.lower()   # push below all other children

        state.bg_label = bg_label
        state.photo = photo   # keep PhotoImage alive via state
    except Exception:
        pass


# Debounce: skip rapid consecutive <Configure> events (e.g. dragging)
_pending_update: dict[int, str] = {}   # widget id → after-job id


def _on_window_move(window: tk.Widget, state: _GlassState) -> None:
    """Debounced callback: re-capture blur after window settles."""
    wid: int = id(window)
    # Cancel any already-scheduled update
    if wid in _pending_update:
        try:
            window.after_cancel(_pending_update[wid])
        except Exception:
            pass
    # Schedule a new capture ~120 ms after the last <Configure> event
    try:
        job: str = window.after(120, lambda: _apply_software_blur(window, state))
        _pending_update[wid] = job
    except Exception:
        pass


def remove_glass(widget: tk.Widget) -> None:
    """Remove any applied glass effect from *widget*.

    Destroys the Level-3 background label (if any), unbinds the move
    handler, and restores the window to a solid dark background.
    """
    wid: int = id(widget)
    state: Optional[_GlassState] = _registry.pop(wid, None)

    if state is not None:
        # Cancel any pending re-capture
        if wid in _pending_update:
            try:
                widget.after_cancel(_pending_update.pop(wid))
            except Exception:
                pass

        # Unbind <Configure> move handler
        if state.move_bind_id is not None:
            try:
                widget.unbind("<Configure>", state.move_bind_id)
            except Exception:
                pass

        # Destroy background label
        if state.bg_label is not None:
            try:
                state.bg_label.destroy()
            except Exception:
                pass

    # Restore defaults
    try:
        widget.configure(bg="#1a1a2e")
        widget.attributes("-alpha", 1.0)  # type: ignore[arg-type]
    except Exception:
        pass

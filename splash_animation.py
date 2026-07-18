"""splash_animation.py – Splash screen module (modular / replaceable).

Public interface (stable):

    show_splash(root: tk.Tk, callback: Callable[[], None] | None = None) -> None

Current implementation:
    Frosted-glass Toplevel (Acrylic / blur-behind via glass_effect),
    centred on screen, with an animated glowing title and a progress bar.
    Fades in → holds → fades out → fires callback.
"""

from __future__ import annotations

import math
import tkinter as tk
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# Timing constants
# ---------------------------------------------------------------------------
_FADE_STEPS: int = 24
_FADE_MS: int = 25           # ms per fade step (~600ms total fade)
_HOLD_MS: int = 1400         # ms at full opacity
_PROGRESS_MS: int = 20       # ms per progress-bar tick
_GLOW_STEPS: int = 40        # glow pulse cycle steps
_GLOW_MS: int = 35           # ms per glow step

# Design
_W, _H = 480, 260
_BG = "#0d0d1a"              # near-black (used when glass fails)
_GLASS_TINT = "#0d0d1a"
_TEXT_MAIN = "#e0e8ff"
_TEXT_SUB = "#5a6080"
_ACCENT = "#89b4fa"          # blue
_BAR_BG = "#1e2040"
_BAR_FG = "#89b4fa"


def show_splash(
    root: tk.Tk,
    callback: Optional[Callable[[], None]] = None,
) -> None:
    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.attributes("-topmost", True)
    splash.withdraw()

    # Position: centre screen
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    x, y = (sw - _W) // 2, (sh - _H) // 2
    splash.geometry(f"{_W}x{_H}+{x}+{y}")
    splash.configure(bg=_BG)
    splash.attributes("-alpha", 0.0)

    # ---- Glass effect ----
    # Deiconify first so the window has a real HWND before DWM calls
    splash.deiconify()
    splash.update_idletasks()
    _canvas_bg: str = "#0d0d2a"   # default: opaque dark (Level-3 or no PIL)
    try:
        from glass_effect import apply_glass  # noqa: PLC0415
        apply_glass(splash, tint_color=_GLASS_TINT, tint_alpha=0.62, blur_radius=24)
        # With DWM-level glass the window bg is "#000000"; canvas must be
        # transparent.  tk.Canvas doesn't support true transparency, but
        # setting bg to the same solid black keeps visual coherence.
        splash.configure(bg="#000000")
        _canvas_bg = "#000000"
    except Exception:
        splash.configure(bg=_BG)

    # ---- Canvas ----
    canvas = tk.Canvas(splash, width=_W, height=_H, bg=_canvas_bg,
                       highlightthickness=0)
    canvas.place(x=0, y=0)

    # Rounded rect border (cosmetic)
    _round_rect(canvas, 2, 2, _W - 2, _H - 2, r=18,
                outline=_ACCENT, fill="", width=1)

    # Thin top accent line
    canvas.create_line(40, 2, _W - 40, 2, fill=_ACCENT, width=2)

    # Logo text (will be re-drawn for glow animation)
    logo_id = canvas.create_text(
        _W // 2, _H // 2 - 28,
        text="AppLauncher",
        fill=_TEXT_MAIN,
        font=("Segoe UI", 34, "bold"),
    )
    sub_id = canvas.create_text(
        _W // 2, _H // 2 + 18,
        text="Quick Launch  ·  Stay Productive",
        fill=_TEXT_SUB,
        font=("Segoe UI", 11),
    )

    # Progress bar
    bar_y = _H - 36
    bar_x0, bar_x1 = 48, _W - 48
    bar_w = bar_x1 - bar_x0
    canvas.create_rectangle(bar_x0, bar_y, bar_x1, bar_y + 4,
                             fill=_BAR_BG, outline="", width=0)
    prog_bar = canvas.create_rectangle(bar_x0, bar_y, bar_x0, bar_y + 4,
                                       fill=_BAR_FG, outline="", width=0)
    pct_text = canvas.create_text(
        _W // 2, bar_y - 10,
        text="0%",
        fill=_TEXT_SUB,
        font=("Segoe UI", 8),
    )

    # ---- Animation state ----
    state = {"prog": 0.0, "done": False}

    # Progress bar fill
    _total_ticks = int((_HOLD_MS + _FADE_STEPS * _FADE_MS * 2) / _PROGRESS_MS)

    def _tick_progress(tick: int = 0) -> None:
        if state["done"]:
            return
        p = min(1.0, tick / _total_ticks)
        state["prog"] = p
        cur_x = bar_x0 + int(bar_w * p)
        try:
            canvas.coords(prog_bar, bar_x0, bar_y, cur_x, bar_y + 4)
            canvas.itemconfig(pct_text, text=f"{int(p * 100)}%")
        except tk.TclError:
            return
        if tick < _total_ticks:
            splash.after(_PROGRESS_MS, _tick_progress, tick + 1)

    # Glow pulse on logo
    _glow_colors = _make_glow_palette(_TEXT_MAIN, _ACCENT, _GLOW_STEPS)

    def _tick_glow(step: int = 0) -> None:
        if state["done"]:
            return
        try:
            canvas.itemconfig(logo_id, fill=_glow_colors[step % _GLOW_STEPS])
        except tk.TclError:
            return
        splash.after(_GLOW_MS, _tick_glow, step + 1)

    # Fade in
    def _fade_in(step: int = 0) -> None:
        alpha = step / _FADE_STEPS
        try:
            splash.attributes("-alpha", alpha)
        except tk.TclError:
            return
        if step < _FADE_STEPS:
            splash.after(_FADE_MS, _fade_in, step + 1)
        else:
            splash.after(_HOLD_MS, _fade_out, _FADE_STEPS)

    def _fade_out(step: int) -> None:
        alpha = step / _FADE_STEPS
        try:
            splash.attributes("-alpha", alpha)
        except tk.TclError:
            return
        if step > 0:
            splash.after(_FADE_MS, _fade_out, step - 1)
        else:
            state["done"] = True
            if callback is not None:
                root.after(0, callback)
            try:
                splash.destroy()
            except tk.TclError:
                pass

    # Kick everything off
    _tick_progress()
    _tick_glow()
    _fade_in()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _round_rect(
    canvas: tk.Canvas,
    x0: int, y0: int, x1: int, y1: int,
    r: int = 12,
    **kwargs,
) -> None:
    """Draw a rounded rectangle on *canvas*."""
    canvas.create_arc(x0, y0, x0 + 2*r, y0 + 2*r, start=90,  extent=90, style="arc", **kwargs)
    canvas.create_arc(x1 - 2*r, y0, x1, y0 + 2*r, start=0,   extent=90, style="arc", **kwargs)
    canvas.create_arc(x1 - 2*r, y1 - 2*r, x1, y1, start=270, extent=90, style="arc", **kwargs)
    canvas.create_arc(x0, y1 - 2*r, x0 + 2*r, y1, start=180, extent=90, style="arc", **kwargs)
    canvas.create_line(x0 + r, y0, x1 - r, y0, **kwargs)
    canvas.create_line(x1, y0 + r, x1, y1 - r, **kwargs)
    canvas.create_line(x1 - r, y1, x0 + r, y1, **kwargs)
    canvas.create_line(x0, y1 - r, x0, y0 + r, **kwargs)


def _lerp_color(c1: str, c2: str, t: float) -> str:
    """Linear interpolate between two hex colors."""
    r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
    r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def _make_glow_palette(base: str, accent: str, steps: int) -> list[str]:
    """Generate a glow pulse palette (base → accent → base)."""
    half = steps // 2
    palette = []
    for i in range(half):
        t = math.sin(math.pi * i / half) ** 2
        palette.append(_lerp_color(base, accent, t * 0.7))
    for i in range(steps - half):
        t = math.sin(math.pi * i / (steps - half)) ** 2
        palette.append(_lerp_color(base, accent, t * 0.7))
    return palette

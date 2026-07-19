"""splash_animation.py – Splash screen module (modular / replaceable).

Public interface (stable):

    show_splash(root: tk.Tk, callback: Callable[[], None] | None = None) -> None

Current implementation:
    Plays a bundled JPEG frame sequence (assets/splash/frame_*.jpg) full-screen
    on a borderless topmost Toplevel.  The frame rate is fixed at ~30 fps and
    the animation duration is determined entirely by the video itself, so there
    is no longer a "splash duration" setting.  Frames are scaled to fit the
    screen while preserving the native 4:3 aspect ratio and centred on a black
    background.

    Robustness contract: ``callback`` is *never* blocked.  If the splash is
    disabled, the frame directory is missing/empty, or any error occurs while
    building the window or decoding a frame, the callback is fired immediately
    so the launcher can continue starting up.
"""

from __future__ import annotations

import glob
import os
import tkinter as tk
from typing import Callable, Optional

from paths import SPLASH_FRAMES_DIR
from settings import settings


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_FRAME_MS: int = 33               # ms per frame (~30 fps, int(1000/30))
_FADE_STEPS: int = 6              # alpha fade-out steps
_FADE_MS: int = 20                # ms per fade-out step
_NATIVE_W, _NATIVE_H = 960, 720   # native frame size (4:3)


def show_splash(
    root: tk.Tk,
    callback: Optional[Callable[[], None]] = None,
) -> None:
    state = {"done": False, "photo": None}

    def _finish() -> None:
        """Fade the splash out, destroy it, then fire the callback.

        Idempotent – safe to call repeatedly; only the first call proceeds.
        """
        if state["done"]:
            return
        state["done"] = True

        def _fade_and_destroy(step: int = _FADE_STEPS) -> None:
            alpha = step / _FADE_STEPS
            try:
                splash.attributes("-alpha", alpha)
            except tk.TclError:
                pass
            if step > 0:
                try:
                    splash.after(_FADE_MS, _fade_and_destroy, step - 1)
                    return
                except tk.TclError:
                    # Window gone – fall straight through to cleanup.
                    pass
            # Destroy (failure is fine) then always invoke the callback.
            try:
                splash.destroy()
            except tk.TclError:
                pass
            if callback is not None:
                try:
                    root.after(0, callback)
                except Exception:
                    try:
                        callback()
                    except Exception:
                        pass

        _fade_and_destroy()

    # ---- Read the on/off setting (silent fallback on any error) ----
    try:
        show = bool(settings.get("show_splash", True))
    except Exception:
        show = True
    if not show:
        # Splash disabled – fire the callback immediately and bail out.
        if callback is not None:
            try:
                callback()
            except Exception:
                pass
        return

    # ---- Discover the frame sequence ----
    try:
        frames = sorted(
            glob.glob(os.path.join(SPLASH_FRAMES_DIR, "frame_*.jpg"))
        )
    except Exception:
        frames = []
    if not frames:
        # No frames bundled / unreadable – never block startup.
        if callback is not None:
            try:
                callback()
            except Exception:
                pass
        return

    # ---- Build the fullscreen borderless Toplevel ----
    splash = None
    try:
        splash = tk.Toplevel(root)
        splash.overrideredirect(True)
        splash.attributes("-topmost", True)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        splash.geometry(f"{sw}x{sh}+0+0")
        splash.configure(bg="#000000")
        splash.deiconify()
        splash.update_idletasks()

        # 4:3 fit-to-screen + centring
        scale = min(sw / _NATIVE_W, sh / _NATIVE_H)
        disp_w = int(_NATIVE_W * scale)
        disp_h = int(_NATIVE_H * scale)
        cx, cy = (sw - disp_w) // 2, (sh - disp_h) // 2

        canvas = tk.Canvas(
            splash, bg="#000000", highlightthickness=0,
        )
        canvas.place(x=0, y=0, relwidth=1, relheight=1)
        img_obj = canvas.create_image(
            cx + disp_w // 2, cy + disp_h // 2, anchor="center",
        )

        # ---- Per-frame playback ----
        from PIL import Image, ImageTk  # noqa: PLC0415

        def _play(i: int) -> None:
            if state["done"]:
                return
            if i >= len(frames):
                _finish()
                return
            try:
                img = Image.open(frames[i])
                img = img.resize((disp_w, disp_h), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                canvas.itemconfig(img_obj, image=photo)
                state["photo"] = photo  # prevent GC
            except Exception:
                # Decode / draw failure – finish gracefully.
                _finish()
                return
            try:
                splash.after(_FRAME_MS, _play, i + 1)
            except tk.TclError:
                _finish()

        _play(0)
    except Exception:
        # Splash construction failed – clean up & fire the callback so the
        # launcher can still start (main.py also has a fallback, but we stay
        # self-sufficient).
        if splash is not None:
            try:
                splash.destroy()
            except Exception:
                pass
        if callback is not None:
            try:
                callback()
            except Exception:
                pass

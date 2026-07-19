"""ui.py – Main application window.

Provides the :class:`LauncherApp` class which builds and manages the entire
Tkinter UI: toolbar, scrollable software list, and system-tray integration.

Color palette (dark theme):
    Background      #1e1e2e
    Surface         #313244
    Overlay         #45475a
    Text            #cdd6f4
    Subtext         #a6adc8
    Blue accent     #89b4fa
    Red accent      #f38ba8
    Green accent    #a6e3a1
"""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from app_manager import AppManager
from autostart import disable_autostart, enable_autostart, is_autostart_enabled
from tray import setup_tray
from glass_effect import apply_glass, show_in_taskbar
from paths import backup_now, list_backups, open_data_dir, restore_backup
from settings import settings
from updater import CURRENT_VERSION, UpdateInfo, check_for_update

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Color / font constants
# ---------------------------------------------------------------------------

C_BG = "#000000"          # 透明底（配合毛玻璃）
C_SURFACE = "#1a1a2e"    # 半透明深蓝面板
C_OVERLAY = "#252540"    # hover 高亮
C_TEXT = "#e0e8ff"
C_SUBTEXT = "#6070a0"
C_BLUE = "#89b4fa"
C_RED = "#f38ba8"
C_GREEN = "#a6e3a1"

FONT_TITLE = ("Segoe UI", 16, "bold")
FONT_LABEL = ("Segoe UI", 10)
FONT_LABEL_BOLD = ("Segoe UI", 10, "bold")
FONT_SMALL = ("Segoe UI", 9)

WINDOW_WIDTH = 600
WINDOW_HEIGHT = 500


# ---------------------------------------------------------------------------
# Helper widgets
# ---------------------------------------------------------------------------

def _styled_button(
    parent: tk.Widget,
    text: str,
    command: "Callable[[], None]",  # noqa: F821
    bg: str = C_BLUE,
    fg: str = C_BG,
) -> tk.Button:
    """Return a flat, styled :class:`tk.Button`."""
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        font=FONT_LABEL_BOLD,
        relief="flat",
        padx=10,
        pady=4,
        cursor="hand2",
        activebackground=C_OVERLAY,
        activeforeground=C_TEXT,
        bd=0,
    )
    return btn


# ---------------------------------------------------------------------------
# Main application class
# ---------------------------------------------------------------------------

class LauncherApp:
    """Root application controller.

    Manages the main :class:`tk.Tk` window, delegates data operations to
    :class:`~app_manager.AppManager`, and wires up the system tray.

    Args:
        root: The Tkinter root window (already created by *main.py*).
    """

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._manager = AppManager()
        self._autostart_var = tk.BooleanVar(value=is_autostart_enabled())

        # Drag-and-drop reorder state
        self._row_widgets: list[tk.Frame] = []
        self._drag_index: int | None = None
        self._drag_row: tk.Frame | None = None
        self._drop_index: int | None = None
        self._indicator: tk.Frame | None = None

        self._build_window()
        self._build_toolbar()
        self._build_list_area()
        self._refresh_list()
        self._setup_tray()

        # Delayed automatic update check (silent, background thread).
        # Waits 2 s so it does not interfere with the splash animation.
        self._root.after(2000, self._auto_check_update)

    # ------------------------------------------------------------------
    # Window setup
    # ------------------------------------------------------------------

    def _build_window(self) -> None:
        """Configure the root window: borderless, fullscreen, frosted-glass."""
        root = self._root
        root.title("AppLauncher")
        root.configure(bg="#000000")

        # Borderless fullscreen
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        sw = root.winfo_screenwidth()
        sh = root.winfo_screenheight()
        root.geometry(f"{sw}x{sh}+0+0")

        # Escape key exits
        root.bind("<Escape>", lambda e: self._quit_app())

        # Apply frosted glass effect (parameters from user settings)
        root.update_idletasks()
        show_in_taskbar(root)
        try:
            apply_glass(
                root,
                tint_color="#0d0d1a",
                tint_alpha=float(settings.get("glass_alpha", 0.62)),
                blur_radius=int(settings.get("glass_blur_radius", 24)),
            )
        except Exception:
            root.configure(bg=C_BG)

        # ttk theme
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure(
            "Vertical.TScrollbar",
            background=C_OVERLAY,
            troughcolor="#00000040",
            arrowcolor=C_TEXT,
            bordercolor="#00000000",
        )

    def _refresh_glass(self) -> None:
        """Re-apply the glass effect to the main window using current settings.

        Used for live preview when the user tweaks the glass sliders in the
        settings window.  Wrapped in try/except so it can never crash the app.
        """
        try:
            apply_glass(
                self._root,
                tint_color="#0d0d1a",
                tint_alpha=float(settings.get("glass_alpha", 0.62)),
                blur_radius=int(settings.get("glass_blur_radius", 24)),
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> None:
        """Build the top toolbar row."""
        toolbar = tk.Frame(self._root, bg=C_SURFACE, pady=8, padx=12)
        toolbar.pack(side="top", fill="x")

        # App title
        tk.Label(
            toolbar,
            text="🚀 AppLauncher",
            font=FONT_TITLE,
            bg=C_SURFACE,
            fg=C_TEXT,
        ).pack(side="left", padx=(0, 16))

        # Exit button (right-most, for borderless window)
        _styled_button(
            toolbar,
            text="✕ 退出",
            command=self._quit_app,
            bg=C_RED,
            fg=C_BG,
        ).pack(side="right", padx=4)

        # Settings button (immediately to the left of Exit)
        _styled_button(
            toolbar,
            text="⚙ 设置",
            command=self._show_settings,
            bg=C_OVERLAY,
            fg=C_TEXT,
        ).pack(side="right", padx=4)

        # Minimize to tray button
        _styled_button(
            toolbar,
            text="— 最小化",
            command=self._hide_to_tray,
            bg=C_OVERLAY,
            fg=C_TEXT,
        ).pack(side="right", padx=4)

        # Autostart checkbox
        autostart_cb = tk.Checkbutton(
            toolbar,
            text="开机自启",
            variable=self._autostart_var,
            command=self._toggle_autostart,
            bg=C_SURFACE,
            fg=C_SUBTEXT,
            selectcolor=C_SURFACE,
            activebackground=C_SURFACE,
            activeforeground=C_TEXT,
            font=FONT_SMALL,
            cursor="hand2",
        )
        autostart_cb.pack(side="right", padx=4)

        # Add button
        _styled_button(
            toolbar,
            text="＋ 添加软件",
            command=self._on_add_app,
            bg=C_GREEN,
            fg=C_BG,
        ).pack(side="right", padx=4)

        # Launch all button
        _styled_button(
            toolbar,
            text="▶ 全部启动",
            command=self._on_launch_all,
            bg=C_BLUE,
            fg=C_BG,
        ).pack(side="right", padx=4)

    # ------------------------------------------------------------------
    # Software list area
    # ------------------------------------------------------------------

    def _build_list_area(self) -> None:
        """Build the scrollable software list container."""
        outer = tk.Frame(self._root, bg=C_BG)
        outer.pack(side="top", fill="both", expand=True, padx=12, pady=(8, 12))

        # Canvas + scrollbar for a scrollable inner frame
        self._canvas = tk.Canvas(outer, bg=C_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            outer, orient="vertical", command=self._canvas.yview
        )
        self._canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        # The inner frame is embedded into the canvas
        self._list_frame = tk.Frame(self._canvas, bg=C_BG)
        self._canvas_window = self._canvas.create_window(
            (0, 0), window=self._list_frame, anchor="nw"
        )

        # Keep canvas scroll region in sync
        self._list_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        # Mouse-wheel scrolling
        self._canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_frame_configure(self, event: tk.Event) -> None:  # noqa: ARG002
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._canvas.itemconfig(self._canvas_window, width=event.width)

    def _on_mousewheel(self, event: tk.Event) -> None:
        self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ------------------------------------------------------------------
    # List rendering
    # ------------------------------------------------------------------

    def _refresh_list(self) -> None:
        """Clear and re-render the software list."""
        for widget in self._list_frame.winfo_children():
            widget.destroy()
        self._row_widgets = []
        # Any indicator line was a child of _list_frame and is now destroyed.
        self._indicator = None

        apps = self._manager.apps
        if not apps:
            tk.Label(
                self._list_frame,
                text="暂无软件，点击「添加软件」开始添加",
                font=FONT_LABEL,
                bg=C_BG,
                fg=C_SUBTEXT,
            ).pack(pady=40)
            return

        for idx, app in enumerate(apps):
            self._render_app_row(idx, app)

    def _render_app_row(self, index: int, app: "AppEntry") -> None:  # noqa: F821
        """Render a single app row in the list.

        Args:
            index: Position in the manager's app list.
            app:   The :class:`~app_manager.AppEntry` dict for this app.
        """
        # Row container
        row = tk.Frame(self._list_frame, bg=C_SURFACE, pady=6, padx=10)
        row.pack(fill="x", pady=3)
        self._row_widgets.append(row)

        # Drag handle (left-most)
        handle = tk.Label(
            row,
            text="⠿",
            font=("Segoe UI Symbol", 16),
            bg=C_SURFACE,
            fg=C_SUBTEXT,
            cursor="fleur",
        )
        handle.pack(side="left", padx=(0, 8))
        handle.bind("<Button-1>", lambda e, i=index: self._on_drag_start(e, i))
        handle.bind("<B1-Motion>", self._on_drag_motion)
        handle.bind("<ButtonRelease-1>", self._on_drag_end)

        # Hover highlight
        def _on_enter(e: tk.Event, r: tk.Frame = row) -> None:  # noqa: ARG001
            r.configure(bg=C_OVERLAY)
            for child in r.winfo_children():
                if isinstance(child, (tk.Label, tk.Frame)):
                    child.configure(bg=C_OVERLAY)

        def _on_leave(e: tk.Event, r: tk.Frame = row) -> None:  # noqa: ARG001
            r.configure(bg=C_SURFACE)
            for child in r.winfo_children():
                if isinstance(child, (tk.Label, tk.Frame)):
                    child.configure(bg=C_SURFACE)

        row.bind("<Enter>", _on_enter)
        row.bind("<Leave>", _on_leave)

        # Left info block
        info_frame = tk.Frame(row, bg=C_SURFACE)
        info_frame.pack(side="left", fill="both", expand=True)

        tk.Label(
            info_frame,
            text=app["name"],
            font=FONT_LABEL_BOLD,
            bg=C_SURFACE,
            fg=C_TEXT,
            anchor="w",
        ).pack(fill="x")

        tk.Label(
            info_frame,
            text=app["path"],
            font=FONT_SMALL,
            bg=C_SURFACE,
            fg=C_SUBTEXT,
            anchor="w",
            wraplength=380,
            justify="left",
        ).pack(fill="x")

        # Bind hover to sub-labels too
        for child in info_frame.winfo_children():
            child.bind("<Enter>", _on_enter)
            child.bind("<Leave>", _on_leave)

        # Right button group
        btn_frame = tk.Frame(row, bg=C_SURFACE)
        btn_frame.pack(side="right", padx=(8, 0))

        _styled_button(
            btn_frame,
            text="▶",
            command=lambda i=index: self._on_launch_single(i),
            bg=C_BLUE,
            fg=C_BG,
        ).pack(side="left", padx=2)

        _styled_button(
            btn_frame,
            text="✕",
            command=lambda i=index: self._on_delete_app(i),
            bg=C_RED,
            fg=C_BG,
        ).pack(side="left", padx=2)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_drag_start(self, event: tk.Event, index: int) -> None:  # noqa: ARG002
        """Begin dragging the row at *index*.

        Highlights the dragged row and (lazily) creates the 2 px indicator
        line that will track the drop target.  Any failure is swallowed so a
        stray drag can never freeze the UI.
        """
        try:
            self._drag_index = index
            if 0 <= index < len(self._row_widgets):
                self._drag_row = self._row_widgets[index]
                self._drag_row.configure(bg=C_OVERLAY)
                for child in self._drag_row.winfo_children():
                    if isinstance(child, (tk.Label, tk.Frame)):
                        child.configure(bg=C_OVERLAY)
            if self._indicator is None:
                self._indicator = tk.Frame(
                    self._list_frame, bg=C_BLUE, height=2
                )
        except Exception:  # noqa: BLE001
            pass

    def _on_drag_motion(self, event: tk.Event) -> None:
        """Track the pointer and move the indicator line to the drop target.

        The drop index is computed from the pointer's Y relative to each row:
        upper half → insert before that row, lower half → insert after it.
        """
        if self._drag_index is None:
            return
        try:
            rel_y = event.y_root - self._list_frame.winfo_rooty()
            drop_index = len(self._row_widgets)
            for i, row in enumerate(self._row_widgets):
                if rel_y < row.winfo_y() + row.winfo_height() // 2:
                    drop_index = i
                    break
            self._drop_index = drop_index
            if self._indicator is not None:
                self._indicator.pack_forget()
                if 0 <= drop_index < len(self._row_widgets):
                    self._indicator.pack(
                        before=self._row_widgets[drop_index], fill="x"
                    )
                else:
                    # Append at the very bottom of the list.
                    self._indicator.pack(fill="x")
        except Exception:  # noqa: BLE001
            pass

    def _on_drag_end(self, event: tk.Event) -> None:  # noqa: ARG002
        """Finalize the drag: persist the new order via *move_app* and refresh.

        Cleans up the indicator line and row highlight unconditionally, then
        applies the reorder (if valid) and re-renders the list.
        """
        if self._drag_index is None:
            return
        from_idx = self._drag_index
        to_idx = self._drop_index
        try:
            if self._indicator is not None:
                self._indicator.pack_forget()
                self._indicator = None
            if self._drag_row is not None:
                self._drag_row.configure(bg=C_SURFACE)
                for child in self._drag_row.winfo_children():
                    if isinstance(child, (tk.Label, tk.Frame)):
                        child.configure(bg=C_SURFACE)
            if (
                from_idx is not None
                and to_idx is not None
                and from_idx != to_idx
            ):
                self._manager.move_app(from_idx, to_idx)
                self._refresh_list()
        except Exception:  # noqa: BLE001
            pass
        finally:
            self._drag_index = None
            self._drop_index = None
            self._drag_row = None

    def _on_add_app(self) -> None:
        """Open a file dialog and register the selected application."""
        path = filedialog.askopenfilename(
            parent=self._root,
            title="选择软件",
            filetypes=[
                ("可执行文件 / 快捷方式", "*.exe;*.lnk"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return
        try:
            self._manager.add_app(path)
            self._refresh_list()
        except FileNotFoundError as exc:
            messagebox.showerror("找不到文件", str(exc), parent=self._root)
        except ValueError as exc:
            messagebox.showwarning("重复添加", str(exc), parent=self._root)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("添加失败", str(exc), parent=self._root)

    def _on_delete_app(self, index: int) -> None:
        """Delete the app at *index* after user confirmation."""
        apps = self._manager.apps
        if index >= len(apps):
            return
        name = apps[index]["name"]
        if not messagebox.askyesno(
            "确认删除",
            f"是否从列表中移除「{name}」？",
            parent=self._root,
        ):
            return
        try:
            self._manager.remove_app(index)
            self._refresh_list()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("删除失败", str(exc), parent=self._root)

    def _on_launch_single(self, index: int) -> None:
        """Launch the app at *index*."""
        try:
            self._manager.launch_app(index)
        except FileNotFoundError as exc:
            messagebox.showerror("启动失败", str(exc), parent=self._root)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("启动失败", str(exc), parent=self._root)

    def _on_launch_all(self) -> None:
        """Launch all registered apps with a live progress window.

        Each app is started in turn via :meth:`AppManager.launch_app`; the
        progress window shows the current target, a progress bar, and a
        running success/failure tally.  An empty list shows a hint instead.
        """
        apps = self._manager.apps
        if not apps:
            messagebox.showinfo("提示", "还没有添加软件", parent=self._root)
            return

        n = len(apps)
        win = tk.Toplevel(self._root)
        win.title("正在启动软件")
        win.configure(bg=C_BG)
        win.resizable(False, False)
        self._center_window(win, 420, 280)
        win.transient(self._root)
        try:
            win.grab_set()
        except tk.TclError:
            pass

        # Frosted-glass styling (parameters from user settings)
        try:
            apply_glass(
                win,
                tint_color="#0d0d1a",
                tint_alpha=float(settings.get("glass_alpha", 0.62)),
                blur_radius=int(settings.get("glass_blur_radius", 24)),
            )
        except Exception:
            win.configure(bg=C_BG)

        tk.Label(
            win, text="正在启动软件...", font=FONT_TITLE, bg=C_BG, fg=C_TEXT
        ).pack(pady=(24, 10))

        status_label = tk.Label(
            win,
            text=f"正在启动：{apps[0]['name']}（1/{n}）",
            font=FONT_LABEL_BOLD,
            bg=C_BG,
            fg=C_SUBTEXT,
        )
        status_label.pack(pady=4, padx=24)

        progress = ttk.Progressbar(win, length=340, maximum=n, value=0)
        progress.pack(pady=12)

        # Launch state
        state = {
            "i": 0,
            "success": 0,
            "failed": [],
            "cancelled": False,
            "done": False,
        }

        def _safe_destroy(w: tk.Toplevel = win) -> None:
            try:
                w.destroy()
            except tk.TclError:
                pass

        def _finish() -> None:
            if state["done"]:
                return
            state["done"] = True
            success = state["success"]
            failed_count = len(state["failed"])
            try:
                progress.configure(value=n)
                if state["cancelled"]:
                    msg = f"已取消（成功 {success} / 失败 {failed_count}）"
                else:
                    msg = f"启动完成（成功 {success} / 失败 {failed_count}）"
                status_label.configure(text=msg)
                cancel_btn.configure(text="关闭", command=_safe_destroy)
            except tk.TclError:
                pass
            # Auto-close 2 s after completion
            self._root.after(2000, _safe_destroy)

        def _step() -> None:
            if state["done"]:
                return
            if state["cancelled"]:
                _finish()
                return
            i = state["i"]
            if i >= n:
                _finish()
                return
            app = apps[i]
            try:
                status_label.configure(
                    text=f"正在启动：{app['name']}（{i + 1}/{n}）"
                )
            except tk.TclError:
                pass
            try:
                self._manager.launch_app(i)
                state["success"] += 1
            except Exception as exc:  # noqa: BLE001
                state["failed"].append((i, exc))
            state["i"] = i + 1
            try:
                progress.configure(value=state["i"])
            except tk.TclError:
                pass
            # Yield to the Tk event loop so the window repaints between launches
            self._root.after(50, _step)

        def _on_cancel() -> None:
            state["cancelled"] = True

        def _on_close() -> None:
            # Closing the window also stops further launches.
            state["cancelled"] = True
            state["done"] = True
            _safe_destroy()

        win.protocol("WM_DELETE_WINDOW", _on_close)

        cancel_btn = _styled_button(
            win, text="取消", command=_on_cancel, bg=C_OVERLAY, fg=C_TEXT,
        )
        cancel_btn.pack(side="bottom", pady=16)

        # Kick off the first step on the event loop
        self._root.after(50, _step)

    def _toggle_autostart(self) -> None:
        """Called when the autostart checkbox is toggled."""
        enabled = self._autostart_var.get()
        try:
            if enabled:
                enable_autostart()
            else:
                disable_autostart()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror(
                "操作失败",
                f"无法修改开机自启设置：{exc}",
                parent=self._root,
            )
            # Revert checkbox state
            self._autostart_var.set(not enabled)

    # ------------------------------------------------------------------
    # Settings & update checking
    # ------------------------------------------------------------------

    def _center_window(self, win: tk.Toplevel, w: int, h: int) -> None:
        """Center *win* on screen using the given size."""
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")

    def _show_settings(self) -> None:
        """Open the settings window (dark, frosted-glass, modal)."""
        win = tk.Toplevel(self._root)
        win.title("设置")
        win.configure(bg=C_BG)
        win.resizable(False, False)
        self._center_window(win, 420, 660)
        win.transient(self._root)
        try:
            win.grab_set()
        except tk.TclError:
            pass

        # Frosted-glass styling (parameters from user settings)
        try:
            apply_glass(
                win,
                tint_color="#0d0d1a",
                tint_alpha=float(settings.get("glass_alpha", 0.62)),
                blur_radius=int(settings.get("glass_blur_radius", 24)),
            )
        except Exception:
            win.configure(bg=C_BG)

        tk.Label(
            win, text="⚙ 设置", font=FONT_TITLE, bg=C_BG, fg=C_TEXT
        ).pack(pady=(18, 10))

        # --- Auto-check-update checkbox ---
        auto_var = tk.BooleanVar(
            value=bool(settings.get("auto_check_update", True))
        )

        def _on_toggle_auto() -> None:
            settings.set("auto_check_update", auto_var.get())
            settings.save()

        tk.Checkbutton(
            win,
            text="自动检查更新",
            variable=auto_var,
            command=_on_toggle_auto,
            bg=C_BG,
            fg=C_TEXT,
            selectcolor=C_SURFACE,
            activebackground=C_BG,
            activeforeground=C_TEXT,
            font=FONT_LABEL,
            cursor="hand2",
            bd=0,
        ).pack(pady=6, anchor="w", padx=48)

        # --- Show-splash checkbox ---
        splash_var = tk.BooleanVar(
            value=bool(settings.get("show_splash", True))
        )

        def _on_toggle_splash() -> None:
            settings.set("show_splash", splash_var.get())
            settings.save()

        tk.Checkbutton(
            win,
            text="显示开屏动画",
            variable=splash_var,
            command=_on_toggle_splash,
            bg=C_BG,
            fg=C_TEXT,
            selectcolor=C_SURFACE,
            activebackground=C_BG,
            activeforeground=C_TEXT,
            font=FONT_LABEL,
            cursor="hand2",
            bd=0,
        ).pack(pady=6, anchor="w", padx=48)

        # --- Glass alpha scale ---
        alpha_var = tk.DoubleVar(
            value=float(settings.get("glass_alpha", 0.62))
        )

        def _on_alpha_change(val: str) -> None:
            v = round(float(val), 2)
            settings.set("glass_alpha", v)
            settings.save()
            try:
                alpha_val_label.configure(text=f"{v:.2f}")
            except tk.TclError:
                pass
            self._refresh_glass()

        tk.Label(
            win, text="毛玻璃透明度", font=FONT_LABEL, bg=C_BG, fg=C_SUBTEXT
        ).pack(anchor="w", padx=48, pady=(10, 0))
        alpha_row = tk.Frame(win, bg=C_BG)
        alpha_row.pack(fill="x", padx=48)
        alpha_val_label = tk.Label(
            alpha_row, text=f"{alpha_var.get():.2f}",
            font=FONT_SMALL, bg=C_BG, fg=C_BLUE, width=8, anchor="e",
        )
        alpha_val_label.pack(side="right")
        tk.Scale(
            alpha_row,
            from_=0.3, to=0.9, resolution=0.05, orient="horizontal",
            variable=alpha_var, command=_on_alpha_change,
            bg=C_BG, fg=C_TEXT, troughcolor=C_SURFACE,
            highlightthickness=0, sliderrelief="flat",
            font=FONT_SMALL, cursor="hand2",
        ).pack(side="left", fill="x", expand=True)

        # --- Glass blur radius scale ---
        blur_var = tk.IntVar(
            value=int(settings.get("glass_blur_radius", 24))
        )

        def _on_blur_change(val: str) -> None:
            v = int(float(val))
            settings.set("glass_blur_radius", v)
            settings.save()
            try:
                blur_val_label.configure(text=str(v))
            except tk.TclError:
                pass
            self._refresh_glass()

        tk.Label(
            win, text="毛玻璃模糊度", font=FONT_LABEL, bg=C_BG, fg=C_SUBTEXT
        ).pack(anchor="w", padx=48, pady=(10, 0))
        blur_row = tk.Frame(win, bg=C_BG)
        blur_row.pack(fill="x", padx=48)
        blur_val_label = tk.Label(
            blur_row, text=str(blur_var.get()),
            font=FONT_SMALL, bg=C_BG, fg=C_BLUE, width=8, anchor="e",
        )
        blur_val_label.pack(side="right")
        tk.Scale(
            blur_row,
            from_=5, to=50, resolution=1, orient="horizontal",
            variable=blur_var, command=_on_blur_change,
            bg=C_BG, fg=C_TEXT, troughcolor=C_SURFACE,
            highlightthickness=0, sliderrelief="flat",
            font=FONT_SMALL, cursor="hand2",
        ).pack(side="left", fill="x", expand=True)

        # --- Data backup & restore section ---
        tk.Frame(win, bg=C_OVERLAY, height=1).pack(
            fill="x", padx=32, pady=(14, 6)
        )
        tk.Label(
            win, text="数据备份与恢复", font=FONT_LABEL_BOLD, bg=C_BG, fg=C_TEXT
        ).pack(anchor="w", padx=48, pady=(0, 6))

        backup_row = tk.Frame(win, bg=C_BG)
        backup_row.pack(fill="x", padx=48, pady=(0, 6))

        def _on_backup_now() -> None:
            name = backup_now()
            if name:
                messagebox.showinfo("已备份", f"已备份至：{name}", parent=win)
            else:
                messagebox.showerror("备份失败", "无法完成备份。", parent=win)

        def _on_restore_data() -> None:
            backups = list_backups()
            if not backups:
                messagebox.showinfo(
                    "暂无备份", "当前没有可恢复的备份。", parent=win
                )
                return
            dlg = tk.Toplevel(win)
            dlg.title("恢复数据")
            dlg.configure(bg=C_BG)
            dlg.resizable(False, False)
            self._center_window(dlg, 320, 360)
            dlg.transient(win)
            try:
                dlg.grab_set()
            except tk.TclError:
                pass
            tk.Label(
                dlg, text="选择要恢复的备份", font=FONT_LABEL_BOLD,
                bg=C_BG, fg=C_TEXT,
            ).pack(pady=(12, 6))
            lb = tk.Listbox(
                dlg, bg=C_SURFACE, fg=C_TEXT, selectbackground=C_BLUE,
                selectforeground=C_BG, font=FONT_SMALL, bd=0,
                highlightthickness=0, height=12,
            )
            for b in backups:
                lb.insert(tk.END, b)
            lb.pack(fill="both", expand=True, padx=16, pady=4)

            def _do_restore() -> None:
                sel = lb.curselection()
                if not sel:
                    return
                name = lb.get(sel[0])
                if restore_backup(name):
                    messagebox.showinfo(
                        "已恢复", "已恢复，重启生效。", parent=dlg
                    )
                    dlg.destroy()
                else:
                    messagebox.showerror(
                        "恢复失败", "无法从该备份恢复。", parent=dlg
                    )

            _styled_button(
                dlg, text="恢复", command=_do_restore, bg=C_BLUE, fg=C_BG,
            ).pack(side="bottom", pady=12)

        def _on_open_data_dir() -> None:
            open_data_dir()

        _styled_button(
            backup_row, text="立即备份", command=_on_backup_now,
            bg=C_BLUE, fg=C_BG,
        ).pack(side="left", padx=(0, 6))
        _styled_button(
            backup_row, text="恢复数据", command=_on_restore_data,
            bg=C_OVERLAY, fg=C_TEXT,
        ).pack(side="left", padx=6)
        _styled_button(
            backup_row, text="打开数据目录", command=_on_open_data_dir,
            bg=C_GREEN, fg=C_BG,
        ).pack(side="left", padx=6)

        # --- Check-now button ---
        check_btn = _styled_button(
            win,
            text="立即检查更新",
            command=lambda: self._on_check_now(check_btn, win),
            bg=C_BLUE,
            fg=C_BG,
        )
        check_btn.pack(pady=(14, 8))

        # --- Close button ---
        _styled_button(
            win,
            text="关闭",
            command=win.destroy,
            bg=C_OVERLAY,
            fg=C_TEXT,
        ).pack(side="bottom", pady=16)

    def _on_check_now(self, btn: tk.Button, win: tk.Toplevel) -> None:
        """Manual update check: runs in a background thread, shows a dialog."""
        btn.configure(text="检查中...", state="disabled")

        def worker() -> None:
            info = check_for_update()
            # Marshal result back to the Tk main thread.
            self._root.after(
                0, lambda: self._on_manual_check_done(info, btn, win)
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_manual_check_done(
        self, info: UpdateInfo | None, btn: tk.Button, win: tk.Toplevel
    ) -> None:
        """Callback (main thread) for the manual update check."""
        # Restore the button; the settings window may already be closed.
        try:
            btn.configure(text="立即检查更新", state="normal")
        except tk.TclError:
            pass
        if info is None:
            # No newer version (or request failed) – prompt the user.
            try:
                messagebox.showinfo(
                    "检查更新", "已是最新版本。", parent=win
                )
            except tk.TclError:
                pass
        else:
            self._show_update_dialog(info, win)

    def _auto_check_update(self) -> None:
        """Silent background update check on startup.

        Reads the ``auto_check_update`` setting; when enabled it queries
        GitHub off the main thread and only surfaces a result when a newer
        version exists.  Any failure is completely silent.
        """
        if not bool(settings.get("auto_check_update", True)):
            return

        def worker() -> None:
            info = check_for_update()
            if info is not None:
                # Only pop a dialog when an update is actually available.
                self._root.after(
                    0, lambda: self._show_update_dialog(info, self._root)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _show_update_dialog(self, info: UpdateInfo, parent: tk.Misc) -> None:
        """Show the 'new version available' dialog with a download button."""
        dlg = tk.Toplevel(parent)
        dlg.title("发现新版本")
        dlg.configure(bg=C_BG)
        dlg.resizable(False, False)
        self._center_window(dlg, 480, 440)
        dlg.transient(parent)
        try:
            dlg.grab_set()
        except tk.TclError:
            pass

        try:
            apply_glass(dlg, tint_color="#0d0d1a", tint_alpha=0.62, blur_radius=24)
        except Exception:
            dlg.configure(bg=C_BG)

        tk.Label(
            dlg, text="🚀 发现新版本", font=FONT_TITLE, bg=C_BG, fg=C_GREEN
        ).pack(pady=(18, 6))

        tk.Label(
            dlg,
            text=f"当前版本：{CURRENT_VERSION}\n最新版本：{info.latest_version}",
            font=FONT_LABEL_BOLD,
            bg=C_BG,
            fg=C_TEXT,
            justify="left",
        ).pack(pady=4, padx=24, anchor="w")

        tk.Label(
            dlg, text="更新内容：", font=FONT_LABEL_BOLD, bg=C_BG, fg=C_SUBTEXT
        ).pack(pady=(10, 2), padx=24, anchor="w")

        notes = info.release_notes.strip() or "（暂无说明）"
        notes_box = tk.Text(
            dlg,
            height=10,
            wrap="word",
            bg=C_SURFACE,
            fg=C_TEXT,
            insertbackground=C_TEXT,
            relief="flat",
            bd=0,
            font=FONT_SMALL,
            padx=8,
            pady=6,
        )
        notes_box.insert("1.0", notes)
        notes_box.configure(state="disabled")
        notes_box.pack(fill="x", padx=24, pady=2)

        tk.Label(
            dlg,
            text=info.download_url,
            font=FONT_SMALL,
            bg=C_BG,
            fg=C_BLUE,
            wraplength=430,
            justify="left",
        ).pack(pady=(6, 4), padx=24, anchor="w")

        btn_frame = tk.Frame(dlg, bg=C_BG)
        btn_frame.pack(side="bottom", pady=16)
        _styled_button(
            btn_frame,
            text="前往下载",
            command=lambda: webbrowser.open(info.download_url),
            bg=C_BLUE,
            fg=C_BG,
        ).pack(side="left", padx=6)
        _styled_button(
            btn_frame,
            text="关闭",
            command=dlg.destroy,
            bg=C_OVERLAY,
            fg=C_TEXT,
        ).pack(side="left", padx=6)

    # ------------------------------------------------------------------
    # Tray / window visibility
    # ------------------------------------------------------------------

    def _setup_tray(self) -> None:
        """Initialise the system-tray icon."""
        setup_tray(
            root=self._root,
            on_show=self._show_window,
            on_quit=self._quit_app,
        )

    def _hide_to_tray(self) -> None:
        """Hide the main window (minimise to tray)."""
        self._root.withdraw()

    def _show_window(self) -> None:
        """Restore and focus the main window from the tray."""
        self._root.deiconify()
        self._root.lift()
        self._root.focus_force()

    def _quit_app(self) -> None:
        """Fully exit the application."""
        try:
            self._root.destroy()
        except tk.TclError:
            pass

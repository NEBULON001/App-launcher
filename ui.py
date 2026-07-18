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

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING

from app_manager import AppManager
from autostart import disable_autostart, enable_autostart, is_autostart_enabled
from tray import setup_tray
from glass_effect import apply_glass

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

        self._build_window()
        self._build_toolbar()
        self._build_list_area()
        self._refresh_list()
        self._setup_tray()

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

        # Apply frosted glass effect
        root.update_idletasks()
        try:
            apply_glass(root, tint_color="#0d0d1a", tint_alpha=0.62, blur_radius=24)
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
        """Launch all registered apps; report failures via a dialog."""
        errors = self._manager.launch_all()
        if errors:
            apps = self._manager.apps
            lines = [
                f"• {apps[i]['name']}: {exc}" for i, exc in errors
            ]
            messagebox.showerror(
                "部分启动失败",
                "以下软件未能启动：\n" + "\n".join(lines),
                parent=self._root,
            )

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

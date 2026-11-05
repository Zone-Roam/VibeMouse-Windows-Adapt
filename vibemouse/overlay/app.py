from __future__ import annotations

import ctypes
import json
import os
import sys
from pathlib import Path
import tkinter as tk

from vibemouse.overlay.state import OverlayState
from vibemouse.overlay.theme import OverlayTheme, OverlayThemeSpec
from vibemouse.overlay.themes import get_theme_spec


STATE_POLL_MS = 70
MOTION_POLL_MS = 16
CURSOR_OFFSET_PX = 22
EDGE_MARGIN_PX = 12

if sys.platform == "win32":
    user32 = ctypes.windll.user32
    MONITOR_DEFAULTTONEAREST = 2
    WS_EX_TRANSPARENT = 0x20
    WS_EX_TOOLWINDOW = 0x80
    GWL_EXSTYLE = -20

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        ]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("rcMonitor", RECT),
            ("rcWork", RECT),
            ("dwFlags", ctypes.c_ulong),
        ]
else:
    user32 = None


class MicOverlay:
    def __init__(
        self,
        root: tk.Tk,
        status_file: Path,
        *,
        theme_name: str = "voice_orb",
    ) -> None:
        self.root = root
        self.status_file = status_file
        self.state = OverlayState()
        self._last_x = 0
        self._last_y = 0
        self._has_last_pos = False
        self._theme_spec = _resolve_theme_spec(theme_name)

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", self._theme_spec.window_alpha)
        self.root.configure(bg="black")
        try:
            self.root.wm_attributes("-transparentcolor", "black")
        except tk.TclError:
            pass
        self.root.geometry(
            f"{self._theme_spec.width}x{self._theme_spec.height}+120+120"
        )

        self.canvas = tk.Canvas(
            self.root,
            width=self._theme_spec.width,
            height=self._theme_spec.height,
            bg="black",
            highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.theme: OverlayTheme = self._theme_spec.create(self.canvas)

        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self._enable_click_through()
        self.root.withdraw()
        self._schedule_state_tick()
        self._schedule_motion_tick()

    def _schedule_state_tick(self) -> None:
        self._refresh_state()
        self.root.after(STATE_POLL_MS, self._schedule_state_tick)

    def _schedule_motion_tick(self) -> None:
        self._refresh_motion()
        self.root.after(MOTION_POLL_MS, self._schedule_motion_tick)

    def _refresh_state(self) -> None:
        self.state = self._read_state()
        if not self.state.visible:
            self._has_last_pos = False
            self.root.withdraw()
            return
        self.root.deiconify()

    def _refresh_motion(self) -> None:
        if not self.state.visible:
            return
        self._reposition_to_cursor()
        self.theme.render(self.state)

    def _read_state(self) -> OverlayState:
        if not self.status_file.exists():
            return OverlayState()
        try:
            payload = json.loads(self.status_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return OverlayState()
        return OverlayState.from_payload(payload)

    def _enable_click_through(self) -> None:
        if user32 is None:
            return
        hwnd = self.root.winfo_id()
        try:
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style |= WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        except Exception:
            return

    def _reposition_to_cursor(self) -> None:
        cursor_x, cursor_y = self._get_cursor_pos()
        left, top, right, bottom = self._get_cursor_monitor_work_area(cursor_x, cursor_y)
        width = self._theme_spec.width
        height = self._theme_spec.height

        x = cursor_x + CURSOR_OFFSET_PX
        y = cursor_y + CURSOR_OFFSET_PX
        if x + width + EDGE_MARGIN_PX > right:
            x = cursor_x - width - CURSOR_OFFSET_PX
        if y + height + EDGE_MARGIN_PX > bottom:
            y = cursor_y - height - CURSOR_OFFSET_PX

        x = max(left + EDGE_MARGIN_PX, min(x, right - width - EDGE_MARGIN_PX))
        y = max(top + EDGE_MARGIN_PX, min(y, bottom - height - EDGE_MARGIN_PX))
        if self._has_last_pos and self._last_x == x and self._last_y == y:
            return
        self._last_x = x
        self._last_y = y
        self._has_last_pos = True
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _get_cursor_pos(self) -> tuple[int, int]:
        if user32 is None:
            pointer_x, pointer_y = self.root.winfo_pointerxy()
            return int(pointer_x), int(pointer_y)
        point = POINT()
        if bool(user32.GetCursorPos(ctypes.byref(point))):
            return int(point.x), int(point.y)
        return 0, 0

    def _get_cursor_monitor_work_area(
        self, cursor_x: int, cursor_y: int
    ) -> tuple[int, int, int, int]:
        if user32 is None:
            return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        try:
            monitor = user32.MonitorFromPoint(
                POINT(cursor_x, cursor_y), MONITOR_DEFAULTTONEAREST
            )
            if not monitor:
                raise RuntimeError("monitor not found")
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            if not bool(user32.GetMonitorInfoW(monitor, ctypes.byref(info))):
                raise RuntimeError("GetMonitorInfoW failed")
            return (
                int(info.rcWork.left),
                int(info.rcWork.top),
                int(info.rcWork.right),
                int(info.rcWork.bottom),
            )
        except Exception:
            return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()


def _resolve_theme_spec(theme_name: str) -> OverlayThemeSpec:
    try:
        return get_theme_spec(theme_name)
    except ValueError as error:
        print(f"Overlay theme fallback: {error}")
        return get_theme_spec("voice_orb")


def _resolve_status_file(argv: list[str]) -> Path:
    if len(argv) >= 2:
        return Path(argv[1])
    project_root = Path(__file__).resolve().parents[2]
    return project_root / ".runtime" / "vibemouse-status.json"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv
    status_file = _resolve_status_file(args)
    theme_name = os.getenv("VIBEMOUSE_OVERLAY_THEME", "voice_orb")
    if user32 is not None:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
    root = tk.Tk()
    _ = MicOverlay(root, status_file=status_file, theme_name=theme_name)
    root.mainloop()
    return 0

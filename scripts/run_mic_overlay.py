from __future__ import annotations

import ctypes
import json
import math
import sys
from pathlib import Path
import tkinter as tk


STATE_POLL_MS = 70
MOTION_POLL_MS = 16
OVERLAY_SIZE = 92
CURSOR_OFFSET_PX = 22
EDGE_MARGIN_PX = 12
WAVE_BAR_COUNT = 9
WAVE_BAR_SPACING = 6
WAVE_BAR_WIDTH = 4
WINDOW_ALPHA = 0.78

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
    def __init__(self, root: tk.Tk, status_file: Path) -> None:
        self.root = root
        self.status_file = status_file
        self.activity = 0.0
        self.recording = False
        self._phase = 0.0
        self._last_x = 0
        self._last_y = 0
        self._has_last_pos = False

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", WINDOW_ALPHA)
        self.root.configure(bg="black")
        try:
            self.root.wm_attributes("-transparentcolor", "black")
        except tk.TclError:
            pass
        self.root.geometry(f"{OVERLAY_SIZE}x{OVERLAY_SIZE}+120+120")

        self.canvas = tk.Canvas(
            self.root,
            width=OVERLAY_SIZE,
            height=OVERLAY_SIZE,
            bg="black",
            highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        center = OVERLAY_SIZE // 2
        self.outer_glow_id = self.canvas.create_oval(
            2,
            2,
            OVERLAY_SIZE - 2,
            OVERLAY_SIZE - 2,
            fill="#16090C",
            outline="",
        )
        self.mid_glow_id = self.canvas.create_oval(
            7,
            7,
            OVERLAY_SIZE - 7,
            OVERLAY_SIZE - 7,
            fill="#33131B",
            outline="",
        )
        self.core_id = self.canvas.create_oval(
            13,
            13,
            OVERLAY_SIZE - 13,
            OVERLAY_SIZE - 13,
            fill="#8E3245",
            outline="",
        )
        self.pulse_id = self.canvas.create_oval(
            center - 16,
            center - 16,
            center + 16,
            center + 16,
            fill="#FFDDE4",
            outline="",
        )
        self.wave_ids: list[int] = []
        start_x = center - ((WAVE_BAR_COUNT - 1) * WAVE_BAR_SPACING) // 2
        for idx in range(WAVE_BAR_COUNT):
            x = start_x + idx * WAVE_BAR_SPACING
            bar_id = self.canvas.create_line(
                x,
                center - 8,
                x,
                center + 8,
                fill="#FFF8FA",
                width=WAVE_BAR_WIDTH,
                capstyle=tk.ROUND,
            )
            self.wave_ids.append(bar_id)

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
        recording, level = self._read_state()
        self.recording = recording
        if self.recording:
            now = self._normalize_activity(level)
            self.activity = max(now, self.activity * 0.7)
        else:
            self.activity = 0.0

        if not self.recording:
            self._has_last_pos = False
            self.root.withdraw()
            return

        self.root.deiconify()

    def _refresh_motion(self) -> None:
        if not self.recording:
            return
        self._reposition_to_cursor()
        self._draw()

    def _read_state(self) -> tuple[bool, float]:
        if not self.status_file.exists():
            return False, 0.0
        try:
            payload = json.loads(self.status_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False, 0.0

        recording = bool(payload.get("recording", False))
        level_raw = payload.get("audio_level", 0.0)
        try:
            level = float(level_raw)
        except (TypeError, ValueError):
            level = 0.0
        return recording, max(0.0, min(1.0, level))

    @staticmethod
    def _normalize_activity(raw_level: float) -> float:
        noise_floor = 0.0012
        speech_peak = 0.018
        if raw_level <= noise_floor:
            return 0.0
        return min(1.0, (raw_level - noise_floor) / (speech_peak - noise_floor))

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

        # Prefer lower-right of cursor; if near edge, flip to the other side.
        x = cursor_x + CURSOR_OFFSET_PX
        y = cursor_y + CURSOR_OFFSET_PX
        if x + OVERLAY_SIZE + EDGE_MARGIN_PX > right:
            x = cursor_x - OVERLAY_SIZE - CURSOR_OFFSET_PX
        if y + OVERLAY_SIZE + EDGE_MARGIN_PX > bottom:
            y = cursor_y - OVERLAY_SIZE - CURSOR_OFFSET_PX

        min_x = left + EDGE_MARGIN_PX
        min_y = top + EDGE_MARGIN_PX
        max_x = right - OVERLAY_SIZE - EDGE_MARGIN_PX
        max_y = bottom - OVERLAY_SIZE - EDGE_MARGIN_PX
        x = max(min_x, min(x, max_x))
        y = max(min_y, min(y, max_y))

        if self._has_last_pos and self._last_x == x and self._last_y == y:
            return
        self._last_x = x
        self._last_y = y
        self._has_last_pos = True
        self.root.geometry(f"{OVERLAY_SIZE}x{OVERLAY_SIZE}+{x}+{y}")

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
            monitor = user32.MonitorFromPoint(POINT(cursor_x, cursor_y), MONITOR_DEFAULTTONEAREST)
            if not monitor:
                raise RuntimeError("monitor not found")
            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            ok = bool(user32.GetMonitorInfoW(monitor, ctypes.byref(info)))
            if not ok:
                raise RuntimeError("GetMonitorInfoW failed")
            return (
                int(info.rcWork.left),
                int(info.rcWork.top),
                int(info.rcWork.right),
                int(info.rcWork.bottom),
            )
        except Exception:
            return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _draw(self) -> None:
        center = OVERLAY_SIZE // 2
        self._phase += 0.32
        if self._phase > 10_000:
            self._phase = 0.0

        # Outer halo pulse
        pulse = 10 + int(self.activity * 18)
        self.canvas.coords(
            self.pulse_id,
            center - pulse,
            center - pulse,
            center + pulse,
            center + pulse,
        )
        if self.activity < 0.3:
            outer_color = "#14080B"
            mid_color = "#2C1018"
            core_color = "#7A2B3D"
            halo_color = "#FFE8EE"
            wave_color = "#FFF7F9"
        elif self.activity < 0.7:
            outer_color = "#1A0A0E"
            mid_color = "#34131C"
            core_color = "#96374B"
            halo_color = "#FFE2E9"
            wave_color = "#FFF4F7"
        else:
            outer_color = "#220D12"
            mid_color = "#3D1620"
            core_color = "#AB3E55"
            halo_color = "#FFD9E3"
            wave_color = "#FFF0F4"
        self.canvas.itemconfig(self.outer_glow_id, fill=outer_color)
        self.canvas.itemconfig(self.mid_glow_id, fill=mid_color)
        self.canvas.itemconfig(self.core_id, fill=core_color)
        self.canvas.itemconfig(self.pulse_id, fill=halo_color)

        # Voiceprint bars
        mid = (WAVE_BAR_COUNT - 1) / 2.0
        for idx, bar_id in enumerate(self.wave_ids):
            distance = abs(idx - mid)
            focus = 1.0 - (distance / (mid + 0.5))
            focus = max(0.2, focus)
            osc = 0.5 + 0.5 * math.sin(self._phase + idx * 0.72)
            bar_half = 4.0 + (2.0 + self.activity * 20.0) * focus * osc
            x = center - ((WAVE_BAR_COUNT - 1) * WAVE_BAR_SPACING) / 2.0 + idx * WAVE_BAR_SPACING
            self.canvas.coords(
                bar_id,
                x,
                center - bar_half,
                x,
                center + bar_half,
            )
            self.canvas.itemconfig(bar_id, fill=wave_color)


def _resolve_status_file(argv: list[str]) -> Path:
    if len(argv) >= 2:
        return Path(argv[1])
    project_root = Path(__file__).resolve().parent.parent
    return project_root / ".runtime" / "vibemouse-status.json"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv
    status_file = _resolve_status_file(args)
    if user32 is not None:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                user32.SetProcessDPIAware()
            except Exception:
                pass
    root = tk.Tk()
    _ = MicOverlay(root, status_file=status_file)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

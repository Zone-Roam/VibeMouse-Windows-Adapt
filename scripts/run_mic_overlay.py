from __future__ import annotations

import json
import sys
from pathlib import Path
import tkinter as tk


POLL_MS = 80
OVERLAY_SIZE = 92


class MicOverlay:
    def __init__(self, root: tk.Tk, status_file: Path) -> None:
        self.root = root
        self.status_file = status_file
        self.activity = 0.0
        self.recording = False

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.configure(bg="black")
        try:
            self.root.wm_attributes("-transparentcolor", "black")
        except tk.TclError:
            pass

        screen_width = self.root.winfo_screenwidth()
        self.root.geometry(
            f"{OVERLAY_SIZE}x{OVERLAY_SIZE}+{screen_width - OVERLAY_SIZE - 28}+88"
        )

        self.canvas = tk.Canvas(
            self.root,
            width=OVERLAY_SIZE,
            height=OVERLAY_SIZE,
            bg="black",
            highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.root.bind("<Escape>", lambda _event: self.root.destroy())
        self.root.withdraw()
        self._schedule_tick()

    def _schedule_tick(self) -> None:
        self._refresh()
        self.root.after(POLL_MS, self._schedule_tick)

    def _refresh(self) -> None:
        recording, level = self._read_state()
        self.recording = recording
        if self.recording:
            now = self._normalize_activity(level)
            self.activity = max(now, self.activity * 0.7)
        else:
            self.activity = 0.0

        if not self.recording:
            self.root.withdraw()
            return

        self.root.deiconify()
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

    def _draw(self) -> None:
        self.canvas.delete("all")
        center = OVERLAY_SIZE // 2

        self.canvas.create_oval(
            12,
            12,
            OVERLAY_SIZE - 12,
            OVERLAY_SIZE - 12,
            fill="#DC3545",
            outline="#FFFFFF",
            width=2,
        )

        pulse = 10 + int(self.activity * 18)
        self.canvas.create_oval(
            center - pulse,
            center - pulse,
            center + pulse,
            center + pulse,
            fill="#FFF1F1",
            outline="",
        )


def _resolve_status_file(argv: list[str]) -> Path:
    if len(argv) >= 2:
        return Path(argv[1])
    project_root = Path(__file__).resolve().parent.parent
    return project_root / ".runtime" / "vibemouse-status.json"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv
    status_file = _resolve_status_file(args)
    root = tk.Tk()
    _ = MicOverlay(root, status_file=status_file)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

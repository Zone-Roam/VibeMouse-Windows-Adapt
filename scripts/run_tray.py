from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw
import pystray


State = Literal["stopped", "idle", "recording"]


class VibeMouseTrayApp:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.venv_python = project_root / ".venv" / "Scripts" / "python.exe"
        self.runtime_dir = project_root / ".runtime"
        self.status_file = self.runtime_dir / "vibemouse-status.json"
        self.log_file = self.runtime_dir / "vibemouse-tray.log"

        self.process: subprocess.Popen[str] | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.reader_thread: threading.Thread | None = None
        self.monitor_thread: threading.Thread | None = None
        self.running = True

        self.openclaw_route_enabled = False
        self.recording = False
        self.state: State = "stopped"

        self.icon = pystray.Icon(
            "vibemouse",
            self._render_icon("stopped"),
            "VibeMouse: stopped",
            menu=pystray.Menu(
                pystray.MenuItem(lambda _item: self._status_text(), None, enabled=False),
                pystray.MenuItem(
                    lambda _item: self._route_text(),
                    None,
                    enabled=False,
                ),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(
                    "Start",
                    self.on_start_click,
                    enabled=lambda _item: self.process is None,
                ),
                pystray.MenuItem(
                    "Stop",
                    self.on_stop_click,
                    enabled=lambda _item: self.process is not None,
                ),
                pystray.MenuItem("Open Log", self.on_open_log_click),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Exit", self.on_exit_click),
            ),
        )

    def build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

        env["VIBEMOUSE_BACKEND"] = "funasr_onnx"
        env["VIBEMOUSE_MODEL"] = "iic/SenseVoiceSmall"
        env["VIBEMOUSE_DEVICE"] = "cpu"
        env["VIBEMOUSE_LANGUAGE"] = "auto"
        env["VIBEMOUSE_USE_ITN"] = "true"
        env["VIBEMOUSE_AUTO_PASTE"] = "true"
        env["VIBEMOUSE_FRONT_BUTTON"] = "x2"
        env["VIBEMOUSE_REAR_BUTTON"] = "x1"
        env["VIBEMOUSE_OPENCLAW_ROUTE_MODE"] = "toggle"
        env["VIBEMOUSE_OPENCLAW_TOGGLE_INITIAL"] = "false"
        env["VIBEMOUSE_OPENCLAW_TOGGLE_HOTKEY"] = "f8"
        env["VIBEMOUSE_OPENCLAW_COMMAND"] = "wsl -d Ubuntu -- openclaw"
        env["VIBEMOUSE_STATUS_FILE"] = str(self.status_file)
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def run(self) -> int:
        if not self.venv_python.exists():
            print(f"[ERROR] Missing venv python: {self.venv_python}")
            return 1

        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.icon.run()
        return 0

    def on_start_click(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.start_service()

    def on_stop_click(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.stop_service()

    def on_open_log_click(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self.log_file.write_text("", encoding="utf-8")
        try:
            subprocess.Popen(["notepad.exe", str(self.log_file)])
        except OSError:
            pass

    def on_exit_click(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.running = False
        self.stop_service()
        self.icon.stop()

    def start_service(self) -> None:
        if self.process is not None:
            return

        env = self.build_env()
        self.openclaw_route_enabled = False
        self._append_log("[INFO] Starting VibeMouse process...")
        creationflags = 0
        if os.name == "nt":
            creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            self.process = subprocess.Popen(
                [str(self.venv_python), "-u", "-m", "vibemouse.main", "run"],
                cwd=str(self.project_root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
        except OSError as error:
            self._append_log(f"[ERROR] Failed to start process: {error}")
            self.process = None
            return

        self.reader_thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.reader_thread.start()
        self._refresh_visual_state(force=True)
        self.icon.notify("VibeMouse started. Use side buttons to record.")

    def stop_service(self) -> None:
        proc = self.process
        if proc is None:
            return
        self._append_log("[INFO] Stopping VibeMouse process...")
        try:
            proc.terminate()
            proc.wait(timeout=4.0)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        self.process = None
        self.recording = False
        self._refresh_visual_state(force=True)

    def _reader_loop(self) -> None:
        proc = self.process
        if proc is None or proc.stdout is None:
            return
        for raw_line in proc.stdout:
            self.log_queue.put(raw_line.rstrip("\n"))
        exit_code = proc.wait()
        self.log_queue.put(f"[INFO] Process exited with code {exit_code}")

    def _monitor_loop(self) -> None:
        while self.running:
            self._drain_logs()
            self._refresh_visual_state(force=False)
            time.sleep(0.25)

    def _drain_logs(self) -> None:
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                return
            self._append_log(line)
            lower = line.lower()
            if "openclaw routing: on" in lower:
                self.openclaw_route_enabled = True
            elif "openclaw routing: off" in lower:
                self.openclaw_route_enabled = False
            elif "openclaw_route=true" in lower:
                self.openclaw_route_enabled = True
            elif "openclaw_route=false" in lower:
                self.openclaw_route_enabled = False

    def _read_recording_state(self) -> bool:
        if not self.status_file.exists():
            return False
        try:
            payload = json.loads(self.status_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        return bool(payload.get("recording", False))

    def _refresh_visual_state(self, *, force: bool) -> None:
        old_state = self.state
        old_recording = self.recording

        self.recording = self._read_recording_state()
        if self.process is None:
            self.state = "stopped"
        elif self.recording:
            self.state = "recording"
        else:
            self.state = "idle"

        if not force and old_state == self.state and old_recording == self.recording:
            return

        self.icon.icon = self._render_icon(self.state)
        self.icon.title = self._status_text()
        self.icon.update_menu()

    def _status_text(self) -> str:
        if self.state == "stopped":
            return "Status: stopped"
        if self.state == "recording":
            return "Status: recording"
        return "Status: idle"

    def _route_text(self) -> str:
        mode = "ON" if self.openclaw_route_enabled else "OFF"
        return f"OpenClaw route: {mode} (toggle F8)"

    @staticmethod
    def _render_icon(state: State) -> Image.Image:
        if state == "recording":
            color = (220, 53, 69, 255)
        elif state == "idle":
            color = (40, 167, 69, 255)
        else:
            color = (108, 117, 125, 255)

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 56, 56), fill=color)
        draw.ellipse((12, 12, 52, 52), outline=(255, 255, 255, 220), width=2)
        return image

    def _append_log(self, line: str) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    app = VibeMouseTrayApp(project_root)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())

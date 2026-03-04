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


State = Literal["stopped", "starting", "idle", "recording"]


class VibeMouseTrayApp:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.venv_python = project_root / ".venv" / "Scripts" / "python.exe"
        self.runtime_dir = project_root / ".runtime"
        self.status_file = self.runtime_dir / "vibemouse-status.json"
        self.control_file = self.runtime_dir / "vibemouse-control.json"
        self.log_file = self.runtime_dir / "vibemouse-tray.log"

        self.process: subprocess.Popen[str] | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.reader_thread: threading.Thread | None = None
        self.monitor_thread: threading.Thread | None = None
        self.running = True
        self.starting_until_monotonic = 0.0
        self.startup_grace_s = 90.0

        self.openclaw_route_enabled = False
        self.translation_route_enabled = False
        self.translation_enabled_for_start = self._read_env_bool(
            "VIBEMOUSE_TRANSLATION_TOGGLE_INITIAL",
            False,
        )
        self.recording = False
        self.audio_level = 0.0
        self.audio_activity = 0.0
        self.overlay_enabled = self._read_env_bool(
            "VIBEMOUSE_TRAY_MIC_OVERLAY",
            False,
        )
        self.overlay_process: subprocess.Popen[str] | None = None
        self.state: State = "stopped"

        self.icon = pystray.Icon(
            "vibemouse",
            self._render_icon("stopped", audio_level=0.0),
            "VibeMouse: stopped",
            menu=pystray.Menu(
                pystray.MenuItem(lambda _item: self._status_text(), None, enabled=False),
                pystray.MenuItem(
                    lambda _item: self._route_text(),
                    None,
                    enabled=False,
                ),
                pystray.MenuItem(
                    lambda _item: self._translation_text(),
                    None,
                    enabled=False,
                ),
                pystray.MenuItem(
                    "Enable ZH->EN Translation",
                    self.on_toggle_translation_click,
                    checked=lambda _item: self.translation_enabled_for_start,
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

        env.setdefault("VIBEMOUSE_BACKEND", "funasr_onnx")
        env.setdefault("VIBEMOUSE_MODEL", "iic/SenseVoiceSmall")
        env.setdefault("VIBEMOUSE_DEVICE", "cpu")
        env.setdefault("VIBEMOUSE_LANGUAGE", "auto")
        env.setdefault("VIBEMOUSE_USE_ITN", "true")
        env.setdefault("VIBEMOUSE_AUTO_PASTE", "true")
        env.setdefault("VIBEMOUSE_INPUT_MODE", "mouse")
        env.setdefault("VIBEMOUSE_FRONT_BUTTON", "x2")
        env.setdefault("VIBEMOUSE_REAR_BUTTON", "x1")
        env.setdefault("VIBEMOUSE_FRONT_HOTKEY", "<ctrl>+<alt>+<shift>+f9")
        env.setdefault("VIBEMOUSE_REAR_HOTKEY", "<ctrl>+<alt>+<shift>+f10")
        env.setdefault("VIBEMOUSE_OPENCLAW_ROUTE_MODE", "toggle")
        env.setdefault("VIBEMOUSE_OPENCLAW_TOGGLE_INITIAL", "false")
        env.setdefault("VIBEMOUSE_OPENCLAW_TOGGLE_HOTKEY", "f8")
        env.setdefault("VIBEMOUSE_OPENCLAW_COMMAND", "wsl -d Ubuntu -- openclaw")
        env.setdefault("VIBEMOUSE_TRANSLATION_TOGGLE_INITIAL", "false")
        env["VIBEMOUSE_TRANSLATION_TOGGLE_INITIAL"] = (
            "true" if self.translation_enabled_for_start else "false"
        )
        env.setdefault("VIBEMOUSE_TRANSLATION_TOGGLE_HOTKEY", "none")
        env.setdefault("VIBEMOUSE_TRANSLATION_PROVIDER", "openai_compatible")
        env.setdefault("VIBEMOUSE_TRANSLATION_API_BASE", "https://api.deepseek.com/v1")
        env.setdefault("VIBEMOUSE_TRANSLATION_MODEL", "deepseek-chat")
        env.setdefault("VIBEMOUSE_TRANSLATION_TIMEOUT_S", "12.0")
        env.setdefault("VIBEMOUSE_TRANSLATION_RETRIES", "1")
        env.setdefault("VIBEMOUSE_TRANSLATION_ONLY_IF_CHINESE", "true")
        env.setdefault("VIBEMOUSE_TRANSLATION_APPLY_TO_OPENCLAW", "false")
        env.setdefault("VIBEMOUSE_STATUS_FILE", str(self.status_file))
        env.setdefault("VIBEMOUSE_CONTROL_FILE", str(self.control_file))
        env.setdefault("PYTHONUNBUFFERED", "1")
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

    def on_toggle_translation_click(
        self, _icon: pystray.Icon, _item: pystray.MenuItem
    ) -> None:
        self.translation_enabled_for_start = not self.translation_enabled_for_start
        enabled_text = "ON" if self.translation_enabled_for_start else "OFF"
        was_running = self.process is not None
        if was_running:
            if self._write_translation_control(self.translation_enabled_for_start):
                self.translation_route_enabled = self.translation_enabled_for_start
                self.icon.notify(f"Translate ZH->EN set to {enabled_text}. Applied live.")
            else:
                self.icon.notify(
                    "Translate ZH->EN toggle failed to apply live. "
                    + "Try restarting the service once."
                )
        else:
            self.icon.notify(
                f"Translate ZH->EN set to {enabled_text}. Will apply on next start."
            )
        self.icon.update_menu()

    def on_exit_click(self, _icon: pystray.Icon, _item: pystray.MenuItem) -> None:
        self.running = False
        self.stop_service()
        self._stop_overlay()
        self.icon.stop()

    def start_service(self) -> None:
        if self.process is not None:
            return

        env = self.build_env()
        _ = self._write_translation_control(self.translation_enabled_for_start)
        self.openclaw_route_enabled = False
        self.translation_route_enabled = self.translation_enabled_for_start
        self.starting_until_monotonic = time.monotonic() + self.startup_grace_s
        self._append_log("[INFO] Starting VibeMouse process...")
        self._append_log(
            "[INFO] Initializing model/transcriber, first start may take 1-3 minutes."
        )
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
        self._ensure_overlay_started()
        self._refresh_visual_state(force=True)
        self.icon.notify("VibeMouse starting. First cold start may take 1-3 minutes.")

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
        self.starting_until_monotonic = 0.0
        self.audio_level = 0.0
        self.audio_activity = 0.0
        self._stop_overlay()
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
            elif "translation routing (zh->en): on" in lower:
                self.translation_route_enabled = True
            elif "translation routing (zh->en): off" in lower:
                self.translation_route_enabled = False
            elif "openclaw_route=true" in lower:
                self.openclaw_route_enabled = True
            elif "openclaw_route=false" in lower:
                self.openclaw_route_enabled = False
            elif "translation_route=true" in lower:
                self.translation_route_enabled = True
            elif "translation_route=false" in lower:
                self.translation_route_enabled = False
            elif "vibemouse ready." in lower:
                self.starting_until_monotonic = 0.0
            elif "transcriber prewarm complete" in lower:
                self.starting_until_monotonic = 0.0

    def _read_status_state(self) -> tuple[bool, float]:
        if not self.status_file.exists():
            return False, 0.0
        try:
            payload = json.loads(self.status_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False, 0.0
        recording = bool(payload.get("recording", False))
        level_raw = payload.get("audio_level", 0.0)
        try:
            audio_level = float(level_raw)
        except (TypeError, ValueError):
            audio_level = 0.0
        audio_level = min(1.0, max(0.0, audio_level))
        return recording, audio_level

    def _refresh_visual_state(self, *, force: bool) -> None:
        old_state = self.state
        old_recording = self.recording
        old_audio_bucket = self._audio_bucket(self.audio_activity)

        self.recording, self.audio_level = self._read_status_state()
        if self.process is None:
            self.state = "stopped"
            self.audio_activity = 0.0
        elif time.monotonic() < self.starting_until_monotonic and not self.recording:
            self.state = "starting"
            self.audio_activity = 0.0
        elif self.recording:
            self.state = "recording"
            activity_now = self._normalize_audio_activity(self.audio_level)
            self.audio_activity = max(activity_now, self.audio_activity * 0.72)
        else:
            self.state = "idle"
            self.audio_level = 0.0
            self.audio_activity = 0.0

        new_audio_bucket = self._audio_bucket(self.audio_activity)

        if (
            not force
            and old_state == self.state
            and old_recording == self.recording
            and old_audio_bucket == new_audio_bucket
        ):
            return

        self.icon.icon = self._render_icon(
            self.state, audio_level=self.audio_activity
        )
        self.icon.title = self._status_text()
        self.icon.update_menu()

    def _status_text(self) -> str:
        if self.state == "stopped":
            return "Status: stopped"
        if self.state == "starting":
            return "Status: starting (warming up...)"
        if self.state == "recording":
            return f"Status: recording (mic {int(self.audio_activity * 100)}%)"
        return "Status: idle"

    def _route_text(self) -> str:
        mode = "ON" if self.openclaw_route_enabled else "OFF"
        return f"OpenClaw route: {mode} (toggle F8)"

    def _translation_text(self) -> str:
        mode = "ON" if self.translation_route_enabled else "OFF"
        startup = "ON" if self.translation_enabled_for_start else "OFF"
        return f"Translate ZH->EN: runtime={mode}, startup={startup} (tray menu)"

    @staticmethod
    def _render_icon(state: State, *, audio_level: float) -> Image.Image:
        if state == "recording":
            color = (220, 53, 69, 255)
        elif state == "starting":
            color = (255, 193, 7, 255)
        elif state == "idle":
            color = (40, 167, 69, 255)
        else:
            color = (108, 117, 125, 255)

        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((8, 8, 56, 56), fill=color)
        draw.ellipse((12, 12, 52, 52), outline=(255, 255, 255, 220), width=2)
        if state == "recording":
            activity = max(0.0, audio_level - 0.03) / 0.22
            activity = min(1.0, activity)
            radius = 8 + int(12 * activity)
            alpha = 120 + int(110 * activity)
            draw.ellipse(
                (32 - radius, 32 - radius, 32 + radius, 32 + radius),
                fill=(255, 245, 245, alpha),
            )
        return image

    @staticmethod
    def _audio_bucket(audio_level: float) -> int:
        return int(max(0.0, min(1.0, audio_level)) * 20)

    @staticmethod
    def _normalize_audio_activity(raw_level: float) -> float:
        level = max(0.0, float(raw_level))
        noise_floor = 0.0012
        speech_peak = 0.018
        if level <= noise_floor:
            return 0.0
        return min(1.0, (level - noise_floor) / (speech_peak - noise_floor))

    @staticmethod
    def _read_env_bool(name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _ensure_overlay_started(self) -> None:
        if not self.overlay_enabled:
            return
        proc = self.overlay_process
        if proc is not None and proc.poll() is None:
            return

        script = self.project_root / "scripts" / "run_mic_overlay.py"
        if not script.exists():
            self._append_log(f"[WARN] Mic overlay script missing: {script}")
            return

        pythonw_path = self.venv_python.with_name("pythonw.exe")
        python_exec = pythonw_path if pythonw_path.exists() else self.venv_python
        creationflags = 0
        if os.name == "nt":
            creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
        try:
            self.overlay_process = subprocess.Popen(
                [str(python_exec), str(script), str(self.status_file)],
                cwd=str(self.project_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
        except OSError as error:
            self.overlay_process = None
            self._append_log(f"[WARN] Failed to start mic overlay: {error}")

    def _stop_overlay(self) -> None:
        proc = self.overlay_process
        self.overlay_process = None
        if proc is None:
            return
        try:
            proc.terminate()
            proc.wait(timeout=1.5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                return

    def _append_log(self, line: str) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    def _write_translation_control(self, enabled: bool) -> bool:
        payload = {
            "translation_enabled": bool(enabled),
            "ts_unix": time.time(),
        }
        tmp_file = self.control_file.with_suffix(self.control_file.suffix + ".tmp")
        try:
            self.control_file.parent.mkdir(parents=True, exist_ok=True)
            _ = tmp_file.write_text(json.dumps(payload), encoding="utf-8")
            _ = tmp_file.replace(self.control_file)
            return True
        except Exception:
            return False


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    app = VibeMouseTrayApp(project_root)
    return app.run()


if __name__ == "__main__":
    raise SystemExit(main())

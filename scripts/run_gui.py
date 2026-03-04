from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, scrolledtext


POLL_MS = 250
SPINNER_FRAMES = ["REC", "REC.", "REC..", "REC..."]


class VibeMouseGui:
    def __init__(self, root: tk.Tk, project_root: Path) -> None:
        self.root = root
        self.project_root = project_root
        self.venv_python = project_root / ".venv" / "Scripts" / "python.exe"
        self.runtime_dir = project_root / ".runtime"
        self.status_file = self.runtime_dir / "vibemouse-status.json"

        self.process: subprocess.Popen[str] | None = None
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.read_thread: threading.Thread | None = None
        self.spinner_index = 0

        self.root.title("VibeMouse Launcher")
        self.root.geometry("760x520")

        self.service_var = tk.StringVar(value="Service: stopped")
        self.record_var = tk.StringVar(value="State: idle")
        self.hotkey_var = tk.StringVar(value="OpenClaw toggle: F8 | Translate ZH->EN: tray menu")

        self._build_ui()
        self._schedule_poll()

    def _build_ui(self) -> None:
        top = tk.Frame(self.root)
        top.pack(fill=tk.X, padx=12, pady=8)

        tk.Label(top, textvariable=self.service_var, font=("Segoe UI", 11, "bold")).pack(
            anchor="w"
        )
        tk.Label(top, textvariable=self.record_var, font=("Segoe UI", 11)).pack(anchor="w")
        tk.Label(top, textvariable=self.hotkey_var, font=("Segoe UI", 10)).pack(anchor="w")

        btn_row = tk.Frame(self.root)
        btn_row.pack(fill=tk.X, padx=12, pady=8)

        self.start_btn = tk.Button(btn_row, text="Start", width=12, command=self.start_service)
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = tk.Button(
            btn_row,
            text="Stop",
            width=12,
            command=self.stop_service,
            state=tk.DISABLED,
        )
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        tips = (
            "Mouse mapping:\n"
            "- Front side button: start/stop recording\n"
            "- Rear side button (idle): send Enter\n"
            "- Rear side button (recording): normal output or OpenClaw (toggle by F8)\n"
            "- Translation route (ZH->EN): use tray right-click menu (requires API key)"
        )
        tk.Label(self.root, text=tips, justify=tk.LEFT).pack(anchor="w", padx=12, pady=(0, 6))

        self.log_view = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, height=18)
        self.log_view.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))
        self.log_view.configure(state=tk.DISABLED)

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
        env.setdefault("PYTHONUNBUFFERED", "1")

        env.setdefault("VIBEMOUSE_OPENCLAW_ROUTE_MODE", "toggle")
        env.setdefault("VIBEMOUSE_OPENCLAW_TOGGLE_INITIAL", "false")
        env.setdefault("VIBEMOUSE_OPENCLAW_TOGGLE_HOTKEY", "f8")
        env.setdefault("VIBEMOUSE_OPENCLAW_COMMAND", "wsl -d Ubuntu -- openclaw")
        env.setdefault("VIBEMOUSE_TRANSLATION_TOGGLE_INITIAL", "false")
        env.setdefault("VIBEMOUSE_TRANSLATION_TOGGLE_HOTKEY", "none")
        env.setdefault("VIBEMOUSE_TRANSLATION_PROVIDER", "openai_compatible")
        env.setdefault("VIBEMOUSE_TRANSLATION_API_BASE", "https://api.deepseek.com/v1")
        env.setdefault("VIBEMOUSE_TRANSLATION_MODEL", "deepseek-chat")
        env.setdefault("VIBEMOUSE_TRANSLATION_TIMEOUT_S", "12.0")
        env.setdefault("VIBEMOUSE_TRANSLATION_RETRIES", "1")
        env.setdefault("VIBEMOUSE_TRANSLATION_ONLY_IF_CHINESE", "true")
        env.setdefault("VIBEMOUSE_TRANSLATION_APPLY_TO_OPENCLAW", "false")

        env["VIBEMOUSE_STATUS_FILE"] = str(self.status_file)
        return env

    def start_service(self) -> None:
        if self.process is not None:
            return
        if not self.venv_python.exists():
            messagebox.showerror(
                "Missing .venv",
                f"Cannot find Python at:\n{self.venv_python}\n\nRun setup first.",
            )
            return

        env = self.build_env()
        self.log("[INFO] Starting VibeMouse process...")
        self.log("[INFO] Initializing model/transcriber, first start may take 1-3 minutes.")
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
        )
        self.service_var.set(f"Service: running (pid={self.process.pid})")
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)

        self.read_thread = threading.Thread(target=self._read_output, daemon=True)
        self.read_thread.start()

    def stop_service(self) -> None:
        if self.process is None:
            return
        self.log("[INFO] Stopping VibeMouse...")
        self.process.terminate()
        self.process = None
        self.service_var.set("Service: stopped")
        self.record_var.set("State: idle")
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)

    def _read_output(self) -> None:
        proc = self.process
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            self.log_queue.put(line.rstrip("\n"))
        code = proc.wait()
        self.log_queue.put(f"[INFO] Process exited with code {code}")

    def _schedule_poll(self) -> None:
        self._drain_logs()
        self._refresh_state()
        self.root.after(POLL_MS, self._schedule_poll)

    def _drain_logs(self) -> None:
        while True:
            try:
                line = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self.log(line)

    def _refresh_state(self) -> None:
        if self.process is not None and self.process.poll() is not None:
            self.process = None
            self.service_var.set("Service: stopped")
            self.start_btn.configure(state=tk.NORMAL)
            self.stop_btn.configure(state=tk.DISABLED)

        if not self.status_file.exists():
            return
        try:
            payload = json.loads(self.status_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        recording = bool(payload.get("recording", False))
        if recording:
            frame = SPINNER_FRAMES[self.spinner_index % len(SPINNER_FRAMES)]
            self.spinner_index += 1
            self.record_var.set(f"State: {frame}")
        else:
            self.spinner_index = 0
            self.record_var.set("State: idle")

    def log(self, text: str) -> None:
        self.log_view.configure(state=tk.NORMAL)
        self.log_view.insert(tk.END, text + "\n")
        self.log_view.see(tk.END)
        self.log_view.configure(state=tk.DISABLED)


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    root = tk.Tk()
    app = VibeMouseGui(root, project_root)

    def _on_close() -> None:
        if app.process is not None and app.process.poll() is None:
            if not messagebox.askyesno("Exit", "VibeMouse is still running. Stop and exit?"):
                return
            app.stop_service()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

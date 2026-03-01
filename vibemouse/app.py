from __future__ import annotations

import threading
from pathlib import Path

from vibemouse.audio import AudioRecorder, AudioRecording
from vibemouse.config import AppConfig
from vibemouse.mouse_listener import SideButtonListener
from vibemouse.output import TextOutput
from vibemouse.transcriber import SenseVoiceTranscriber


class VoiceMouseApp:
    def __init__(self, config: AppConfig) -> None:
        if config.front_button == config.rear_button:
            raise ValueError("Front and rear side buttons must be different")

        self._config: AppConfig = config
        self._recorder: AudioRecorder = AudioRecorder(
            sample_rate=config.sample_rate,
            channels=config.channels,
            dtype=config.dtype,
            temp_dir=config.temp_dir,
        )
        self._transcriber: SenseVoiceTranscriber = SenseVoiceTranscriber(config)
        self._output: TextOutput = TextOutput()
        self._listener: SideButtonListener = SideButtonListener(
            on_front_press=self._on_front_press,
            on_rear_press=self._on_rear_press,
            front_button=config.front_button,
            rear_button=config.rear_button,
            debounce_s=config.button_debounce_ms / 1000.0,
        )
        self._stop_event: threading.Event = threading.Event()
        self._transcribe_lock: threading.Lock = threading.Lock()
        self._workers_lock: threading.Lock = threading.Lock()
        self._workers: set[threading.Thread] = set()

    def run(self) -> None:
        self._listener.start()
        print(
            "VibeMouse ready. "
            + f"Model={self._config.model_name}, preferred_device={self._config.device}, "
            + f"backend={self._config.transcriber_backend}, auto_paste={self._config.auto_paste}, "
            + f"enter_mode={self._config.enter_mode}, debounce_ms={self._config.button_debounce_ms}, "
            + f"front_button={self._config.front_button}, rear_button={self._config.rear_button}. "
            + "Press side-front to start/stop recording, side-rear to send Enter."
        )
        try:
            _ = self._stop_event.wait()
        except KeyboardInterrupt:
            self._stop_event.set()
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        self._listener.stop()
        self._recorder.cancel()
        with self._workers_lock:
            workers = list(self._workers)
        still_running: list[threading.Thread] = []
        for worker in workers:
            worker.join(timeout=5)
            if worker.is_alive():
                still_running.append(worker)
        if still_running:
            print(
                f"Shutdown warning: {len(still_running)} transcription worker(s) are still running"
            )

    def _on_front_press(self) -> None:
        if not self._recorder.is_recording:
            try:
                self._recorder.start()
                print("Recording started")
            except Exception as error:
                print(f"Failed to start recording: {error}")
            return

        recording = self._recorder.stop_and_save()
        if recording is None:
            print("Recording was empty and has been discarded")
            return

        self._start_transcription_worker(recording)

    def _on_rear_press(self) -> None:
        try:
            self._output.send_enter(mode=self._config.enter_mode)
            if self._config.enter_mode == "none":
                print("Enter key handling disabled (enter_mode=none)")
            else:
                print("Enter key sent")
        except Exception as error:
            print(f"Failed to send Enter: {error}")

    def _start_transcription_worker(self, recording: AudioRecording) -> None:
        worker = threading.Thread(
            target=self._transcribe_and_output,
            args=(recording,),
            daemon=True,
        )
        with self._workers_lock:
            self._workers.add(worker)
        worker.start()

    def _transcribe_and_output(self, recording: AudioRecording) -> None:
        current = threading.current_thread()
        try:
            print(f"Recording stopped ({recording.duration_s:.1f}s), transcribing...")
            with self._transcribe_lock:
                text = self._transcriber.transcribe(recording.path)

            if not text:
                print("No speech recognized")
                return

            route = self._output.inject_or_clipboard(
                text,
                auto_paste=self._config.auto_paste,
            )
            device = self._transcriber.device_in_use
            backend = self._transcriber.backend_in_use
            if route == "typed":
                print(
                    f"Transcribed with {backend} on {device}, typed into focused input"
                )
            elif route == "pasted":
                print(
                    f"Transcribed with {backend} on {device}, pasted via system shortcut"
                )
            elif route == "clipboard":
                print(f"Transcribed with {backend} on {device}, copied to clipboard")
            else:
                print(f"Transcribed with {backend} on {device}, but output was empty")
        except Exception as error:
            print(f"Transcription failed: {error}")
        finally:
            self._safe_unlink(recording.path)
            with self._workers_lock:
                self._workers.discard(current)

    def _safe_unlink(self, path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except Exception as error:
            print(f"Failed to remove temp audio file {path}: {error}")

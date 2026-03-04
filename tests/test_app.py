from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from vibemouse.app import VoiceMouseApp


class VoiceMouseAppWorkspaceTests(unittest.TestCase):
    @staticmethod
    def _make_subject() -> VoiceMouseApp:
        return object.__new__(VoiceMouseApp)

    def test_switch_workspace_left_uses_expected_dispatcher(self) -> None:
        subject = self._make_subject()
        switch = cast(Callable[[str], bool], getattr(subject, "_switch_workspace"))

        with patch(
            "vibemouse.app.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="ok\n"),
        ) as run_mock:
            ok = switch("left")

        self.assertTrue(ok)
        self.assertEqual(
            run_mock.call_args.args[0],
            ["hyprctl", "dispatch", "workspace", "e-1"],
        )

    def test_switch_workspace_right_uses_expected_dispatcher(self) -> None:
        subject = self._make_subject()
        switch = cast(Callable[[str], bool], getattr(subject, "_switch_workspace"))

        with patch(
            "vibemouse.app.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="ok\n"),
        ) as run_mock:
            ok = switch("right")

        self.assertTrue(ok)
        self.assertEqual(
            run_mock.call_args.args[0],
            ["hyprctl", "dispatch", "workspace", "e+1"],
        )

    def test_switch_workspace_returns_false_when_process_errors(self) -> None:
        subject = self._make_subject()
        switch = cast(Callable[[str], bool], getattr(subject, "_switch_workspace"))

        with patch(
            "vibemouse.app.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd=["hyprctl"], timeout=1.0),
        ):
            ok = switch("left")

        self.assertFalse(ok)

    def test_set_recording_status_writes_recording_payload(self) -> None:
        subject = self._make_subject()
        with tempfile.TemporaryDirectory(prefix="vibemouse-status-") as tmp:
            status_file = Path(tmp) / "status.json"
            setattr(subject, "_config", SimpleNamespace(status_file=status_file))

            set_status = cast(
                Callable[[bool], None],
                getattr(subject, "_set_recording_status"),
            )
            set_status(True)

            payload = cast(
                dict[str, object],
                json.loads(status_file.read_text(encoding="utf-8")),
            )
            self.assertEqual(
                payload,
                {"recording": True, "state": "recording", "audio_level": 0.0},
            )

    def test_set_recording_status_writes_idle_payload(self) -> None:
        subject = self._make_subject()
        with tempfile.TemporaryDirectory(prefix="vibemouse-status-") as tmp:
            status_file = Path(tmp) / "status.json"
            setattr(subject, "_config", SimpleNamespace(status_file=status_file))

            set_status = cast(
                Callable[[bool], None],
                getattr(subject, "_set_recording_status"),
            )
            set_status(False)

            payload = cast(
                dict[str, object],
                json.loads(status_file.read_text(encoding="utf-8")),
            )
            self.assertEqual(
                payload,
                {"recording": False, "state": "idle", "audio_level": 0.0},
            )


class VoiceMouseAppButtonBehaviorTests(unittest.TestCase):
    @staticmethod
    def _make_subject() -> VoiceMouseApp:
        return object.__new__(VoiceMouseApp)

    def test_front_press_stops_recording_with_default_output_target(self) -> None:
        subject = self._make_subject()
        recording = SimpleNamespace(duration_s=1.1, path=Path("/tmp/voice.wav"))
        setattr(
            subject,
            "_recorder",
            SimpleNamespace(is_recording=True, stop_and_save=lambda: recording),
        )

        status_values: list[bool] = []
        worker_calls: list[tuple[object, str]] = []
        setattr(
            subject, "_set_recording_status", lambda value: status_values.append(value)
        )
        setattr(
            subject,
            "_start_transcription_worker",
            lambda rec, *, output_target: worker_calls.append((rec, output_target)),
        )

        on_front = cast(Callable[[], None], getattr(subject, "_on_front_press"))
        on_front()

        self.assertEqual(status_values, [False])
        self.assertEqual(worker_calls, [(recording, "default")])

    def test_rear_press_stops_recording_and_routes_to_openclaw(self) -> None:
        subject = self._make_subject()
        recording = SimpleNamespace(duration_s=1.2, path=Path("/tmp/voice.wav"))
        setattr(
            subject,
            "_recorder",
            SimpleNamespace(is_recording=True, stop_and_save=lambda: recording),
        )

        status_values: list[bool] = []
        worker_calls: list[tuple[object, str]] = []
        send_enter_calls: list[str] = []
        setattr(
            subject, "_set_recording_status", lambda value: status_values.append(value)
        )
        setattr(
            subject,
            "_start_transcription_worker",
            lambda rec, *, output_target: worker_calls.append((rec, output_target)),
        )
        setattr(
            subject,
            "_output",
            SimpleNamespace(send_enter=lambda mode: send_enter_calls.append(mode)),
        )
        setattr(
            subject,
            "_config",
            SimpleNamespace(
                enter_mode="enter",
                openclaw_route_mode="always",
            ),
        )
        setattr(subject, "_openclaw_route_lock", threading.Lock())
        setattr(subject, "_openclaw_route_enabled", False)

        on_rear = cast(Callable[[], None], getattr(subject, "_on_rear_press"))
        on_rear()

        self.assertEqual(status_values, [False])
        self.assertEqual(worker_calls, [(recording, "openclaw")])
        self.assertEqual(send_enter_calls, [])

    def test_rear_press_sends_enter_when_idle(self) -> None:
        subject = self._make_subject()
        setattr(subject, "_recorder", SimpleNamespace(is_recording=False))
        send_enter_calls: list[str] = []
        setattr(
            subject,
            "_output",
            SimpleNamespace(send_enter=lambda mode: send_enter_calls.append(mode)),
        )
        setattr(subject, "_config", SimpleNamespace(enter_mode="ctrl_enter"))

        on_rear = cast(Callable[[], None], getattr(subject, "_on_rear_press"))
        on_rear()

        self.assertEqual(send_enter_calls, ["ctrl_enter"])

    def test_rear_button_state_matrix(self) -> None:
        for is_recording in (True, False):
            with self.subTest(is_recording=is_recording):
                subject = self._make_subject()
                recording = SimpleNamespace(
                    duration_s=0.8, path=Path("/tmp/matrix.wav")
                )
                setattr(
                    subject,
                    "_recorder",
                    SimpleNamespace(
                        is_recording=is_recording,
                        stop_and_save=lambda: recording,
                    ),
                )
                setattr(subject, "_set_recording_status", lambda value: None)

                worker_calls: list[tuple[object, str]] = []
                send_enter_calls: list[str] = []
                setattr(
                    subject,
                    "_start_transcription_worker",
                    lambda rec, *, output_target: worker_calls.append(
                        (rec, output_target)
                    ),
                )
                setattr(
                    subject,
                    "_output",
                    SimpleNamespace(
                        send_enter=lambda mode: send_enter_calls.append(mode)
                    ),
                )
                setattr(
                    subject,
                    "_config",
                    SimpleNamespace(enter_mode="enter", openclaw_route_mode="always"),
                )
                setattr(subject, "_openclaw_route_lock", threading.Lock())
                setattr(subject, "_openclaw_route_enabled", False)

                on_rear = cast(Callable[[], None], getattr(subject, "_on_rear_press"))
                on_rear()

                if is_recording:
                    self.assertEqual(worker_calls, [(recording, "openclaw")])
                    self.assertEqual(send_enter_calls, [])
                else:
                    self.assertEqual(worker_calls, [])
                    self.assertEqual(send_enter_calls, ["enter"])

    def test_transcribe_and_output_openclaw_uses_openclaw_sender(self) -> None:
        subject = self._make_subject()
        recording = SimpleNamespace(duration_s=1.0, path=Path("/tmp/transcribe.wav"))
        setattr(
            subject,
            "_transcriber",
            SimpleNamespace(
                transcribe=lambda path: "hello world",
                device_in_use="cpu",
                backend_in_use="funasr",
            ),
        )

        openclaw_calls: list[str] = []
        inject_calls: list[tuple[str, bool]] = []
        setattr(
            subject,
            "_output",
            SimpleNamespace(
                send_to_openclaw_result=lambda text: openclaw_calls.append(text)
                or SimpleNamespace(route="openclaw", reason="dispatched"),
                inject_or_clipboard=lambda text, auto_paste: inject_calls.append(
                    (text, auto_paste)
                )
                or "typed",
            ),
        )
        setattr(subject, "_config", SimpleNamespace(auto_paste=True))
        setattr(subject, "_transcribe_lock", threading.Lock())
        setattr(subject, "_workers_lock", threading.Lock())
        setattr(subject, "_workers", set())

        removed_paths: list[Path] = []
        setattr(subject, "_safe_unlink", lambda path: removed_paths.append(path))

        transcribe_and_output = cast(
            Callable[[object, str], None],
            getattr(subject, "_transcribe_and_output"),
        )
        transcribe_and_output(recording, "openclaw")

        self.assertEqual(openclaw_calls, ["hello world"])
        self.assertEqual(inject_calls, [])
        self.assertEqual(removed_paths, [Path("/tmp/transcribe.wav")])

    def test_rear_press_routes_to_default_when_toggle_mode_is_off(self) -> None:
        subject = self._make_subject()
        recording = SimpleNamespace(duration_s=1.2, path=Path("/tmp/voice.wav"))
        setattr(
            subject,
            "_recorder",
            SimpleNamespace(is_recording=True, stop_and_save=lambda: recording),
        )

        worker_calls: list[tuple[object, str]] = []
        setattr(subject, "_set_recording_status", lambda value: None)
        setattr(
            subject,
            "_start_transcription_worker",
            lambda rec, *, output_target: worker_calls.append((rec, output_target)),
        )
        setattr(
            subject,
            "_config",
            SimpleNamespace(
                enter_mode="enter",
                openclaw_route_mode="toggle",
            ),
        )
        setattr(subject, "_openclaw_route_lock", threading.Lock())
        setattr(subject, "_openclaw_route_enabled", False)

        on_rear = cast(Callable[[], None], getattr(subject, "_on_rear_press"))
        on_rear()

        self.assertEqual(worker_calls, [(recording, "default")])

    def test_rear_press_routes_to_openclaw_when_toggle_mode_is_on(self) -> None:
        subject = self._make_subject()
        recording = SimpleNamespace(duration_s=1.2, path=Path("/tmp/voice.wav"))
        setattr(
            subject,
            "_recorder",
            SimpleNamespace(is_recording=True, stop_and_save=lambda: recording),
        )

        worker_calls: list[tuple[object, str]] = []
        setattr(subject, "_set_recording_status", lambda value: None)
        setattr(
            subject,
            "_start_transcription_worker",
            lambda rec, *, output_target: worker_calls.append((rec, output_target)),
        )
        setattr(
            subject,
            "_config",
            SimpleNamespace(
                enter_mode="enter",
                openclaw_route_mode="toggle",
            ),
        )
        setattr(subject, "_openclaw_route_lock", threading.Lock())
        setattr(subject, "_openclaw_route_enabled", True)

        on_rear = cast(Callable[[], None], getattr(subject, "_on_rear_press"))
        on_rear()

        self.assertEqual(worker_calls, [(recording, "openclaw")])


class VoiceMouseAppInitTests(unittest.TestCase):
    @staticmethod
    def _make_config(input_mode: str) -> SimpleNamespace:
        return SimpleNamespace(
            sample_rate=16000,
            channels=1,
            dtype="float32",
            model_name="iic/SenseVoiceSmall",
            device="cpu",
            transcriber_backend="funasr_onnx",
            auto_paste=True,
            enter_mode="enter",
            button_debounce_ms=150,
            gestures_enabled=False,
            gesture_trigger_button="rear",
            gesture_threshold_px=120,
            gesture_freeze_pointer=True,
            gesture_restore_cursor=True,
            prewarm_on_start=False,
            openclaw_command="openclaw",
            openclaw_agent="main",
            openclaw_timeout_s=20.0,
            openclaw_retries=0,
            openclaw_route_mode="toggle",
            openclaw_toggle_initial=False,
            openclaw_toggle_hotkey="f8",
            translation_toggle_initial=False,
            translation_toggle_hotkey="f7",
            translation_provider="openai_compatible",
            translation_api_base="https://api.openai.com/v1",
            translation_api_key="",
            translation_model="gpt-4o-mini",
            translation_timeout_s=12.0,
            translation_retries=1,
            translation_only_if_chinese=True,
            translation_apply_to_openclaw=False,
            user_dictionary_file=Path("D:/tmp/user_dictionary.json"),
            text_history_file=Path("D:/tmp/transcript-history.jsonl"),
            text_history_enabled=True,
            strip_emoji=True,
            front_button="x2",
            rear_button="x1",
            front_hotkey="<ctrl>+<alt>+<shift>+f9",
            rear_hotkey="<ctrl>+<alt>+<shift>+f10",
            input_mode=input_mode,
            status_file=Path("D:/tmp/vibemouse-status.json"),
            control_file=Path("D:/tmp/vibemouse-control.json"),
            temp_dir=Path("D:/tmp"),
        )

    def test_init_uses_mouse_listener_when_input_mode_mouse(self) -> None:
        config = self._make_config("mouse")
        with (
            patch("vibemouse.app.create_system_integration"),
            patch("vibemouse.app.AudioRecorder"),
            patch("vibemouse.app.SenseVoiceTranscriber"),
            patch("vibemouse.app.TextOutput"),
            patch("vibemouse.app.SideButtonListener") as side_listener,
            patch("vibemouse.app.HotkeyListener") as hotkey_listener,
        ):
            _ = VoiceMouseApp(config)

        self.assertEqual(side_listener.call_count, 1)
        self.assertEqual(hotkey_listener.call_count, 0)

    def test_init_uses_hotkey_listener_when_input_mode_hotkey(self) -> None:
        config = self._make_config("hotkey")
        with (
            patch("vibemouse.app.create_system_integration"),
            patch("vibemouse.app.AudioRecorder"),
            patch("vibemouse.app.SenseVoiceTranscriber"),
            patch("vibemouse.app.TextOutput"),
            patch("vibemouse.app.SideButtonListener") as side_listener,
            patch("vibemouse.app.HotkeyListener") as hotkey_listener,
        ):
            _ = VoiceMouseApp(config)

        self.assertEqual(side_listener.call_count, 0)
        self.assertEqual(hotkey_listener.call_count, 1)

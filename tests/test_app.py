from __future__ import annotations

import json
import subprocess
import tempfile
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
            self.assertEqual(payload, {"recording": True, "state": "recording"})

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
            self.assertEqual(payload, {"recording": False, "state": "idle"})

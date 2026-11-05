from __future__ import annotations

import unittest

from vibemouse.overlay.state import OverlayState
from vibemouse.overlay.themes import available_theme_names, get_theme_spec


class OverlayStateTests(unittest.TestCase):
    def test_schema_v1_recording_payload_is_supported(self) -> None:
        state = OverlayState.from_payload(
            {"recording": True, "state": "recording", "audio_level": 0.42}
        )

        self.assertTrue(state.recording)
        self.assertTrue(state.visible)
        self.assertAlmostEqual(state.audio_level, 0.42)

    def test_schema_v2_job_payload_is_supported(self) -> None:
        state = OverlayState.from_payload(
            {
                "schema_version": 2,
                "revision": 7,
                "service": {"state": "ready"},
                "capture": {"state": "idle", "audio_level": 0.0},
                "job": {
                    "id": "job-7",
                    "stage": "transcribing",
                    "target": "default",
                    "partial_text": "实时字幕",
                },
                "last_result": {
                    "outcome": "clipboard_fallback",
                    "error_code": "focus_changed",
                },
            }
        )

        self.assertFalse(state.recording)
        self.assertTrue(state.has_active_job)
        self.assertTrue(state.visible)
        self.assertEqual(state.job_id, "job-7")
        self.assertEqual(state.partial_text, "实时字幕")
        self.assertEqual(state.last_outcome, "clipboard_fallback")
        self.assertEqual(state.error_code, "focus_changed")

    def test_audio_level_is_clamped(self) -> None:
        self.assertEqual(OverlayState.from_payload({"audio_level": -2}).audio_level, 0.0)
        self.assertEqual(OverlayState.from_payload({"audio_level": 3}).audio_level, 1.0)


class OverlayThemeRegistryTests(unittest.TestCase):
    def test_voice_orb_is_the_default_registered_theme(self) -> None:
        self.assertIn("voice_orb", available_theme_names())
        self.assertEqual(get_theme_spec("voice-orb").name, "voice_orb")

    def test_unknown_theme_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown overlay theme"):
            _ = get_theme_spec("missing")


if __name__ == "__main__":
    unittest.main()

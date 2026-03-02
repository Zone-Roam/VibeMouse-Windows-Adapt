from __future__ import annotations

import unittest
from collections.abc import Callable
from typing import cast
from unittest.mock import patch

from vibemouse.mouse_listener import SideButtonListener


def _noop_button() -> None:
    return


class SideButtonListenerGestureTests(unittest.TestCase):
    @staticmethod
    def _classify(dx: int, dy: int, threshold_px: int) -> str | None:
        classify = cast(
            Callable[[int, int, int], str | None],
            getattr(SideButtonListener, "_classify_gesture"),
        )
        return classify(dx, dy, threshold_px)

    def test_classify_returns_none_when_movement_is_small(self) -> None:
        self.assertIsNone(self._classify(20, 10, 120))

    def test_classify_returns_right_for_positive_dx(self) -> None:
        self.assertEqual(self._classify(200, 30, 120), "right")

    def test_classify_returns_left_for_negative_dx(self) -> None:
        self.assertEqual(self._classify(-220, 10, 120), "left")

    def test_classify_returns_up_for_negative_dy(self) -> None:
        self.assertEqual(self._classify(20, -250, 120), "up")

    def test_classify_returns_down_for_positive_dy(self) -> None:
        self.assertEqual(self._classify(30, 240, 120), "down")

    def test_constructor_rejects_invalid_trigger_button(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "gesture_trigger_button must be one of: front, rear, right",
        ):
            _ = SideButtonListener(
                on_front_press=_noop_button,
                on_rear_press=_noop_button,
                front_button="x1",
                rear_button="x2",
                gesture_trigger_button="middle",
            )

    def test_constructor_accepts_right_trigger_button(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gesture_trigger_button="right",
        )

        self.assertIsNotNone(listener)

    def test_dispatch_gesture_calls_callback_when_present(self) -> None:
        seen: list[str] = []

        def on_gesture(direction: str) -> None:
            seen.append(direction)

        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            on_gesture=on_gesture,
        )

        dispatch_gesture = cast(
            Callable[[str], None],
            getattr(listener, "_dispatch_gesture"),
        )
        dispatch_gesture("up")
        self.assertEqual(seen, ["up"])

    def test_finish_gesture_restores_cursor_after_direction_action(self) -> None:
        seen: list[str] = []
        restored: list[tuple[int, int]] = []

        def on_gesture(direction: str) -> None:
            seen.append(direction)

        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            on_gesture=on_gesture,
            gestures_enabled=True,
            gesture_trigger_button="right",
        )

        with patch.object(listener, "_read_cursor_position", return_value=(100, 200)):
            start_capture = cast(
                Callable[..., None],
                getattr(listener, "_start_gesture_capture"),
            )
            start_capture(initial_position=(0, 0))

        accumulate = cast(
            Callable[..., None],
            getattr(listener, "_accumulate_gesture_delta"),
        )
        accumulate(dx=300, dy=0)

        def capture_restore(position: tuple[int, int]) -> None:
            restored.append(position)

        with patch.object(
            listener, "_restore_cursor_position", side_effect=capture_restore
        ):
            finish_capture = cast(
                Callable[[str], None],
                getattr(listener, "_finish_gesture_capture"),
            )
            finish_capture("right")

        self.assertEqual(seen, ["right"])
        self.assertEqual(restored, [(100, 200)])

    def test_finish_small_movement_does_not_restore_cursor(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x1",
            rear_button="x2",
            gestures_enabled=True,
            gesture_trigger_button="right",
        )

        with patch.object(listener, "_read_cursor_position", return_value=(50, 60)):
            start_capture = cast(
                Callable[..., None],
                getattr(listener, "_start_gesture_capture"),
            )
            start_capture(initial_position=(0, 0))

        with patch.object(listener, "_restore_cursor_position") as restore_mock:
            finish_capture = cast(
                Callable[[str], None],
                getattr(listener, "_finish_gesture_capture"),
            )
            finish_capture("right")

        self.assertEqual(restore_mock.call_count, 0)

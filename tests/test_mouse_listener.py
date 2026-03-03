from __future__ import annotations

from types import SimpleNamespace
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

    def test_windows_side_button_suppression_for_xbutton_messages(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x2",
            rear_button="x1",
        )
        blocked = cast(
            Callable[[], set[int]],
            getattr(listener, "_blocked_windows_side_buttons"),
        )()

        should_suppress = cast(
            Callable[..., bool],
            getattr(listener, "_should_suppress_windows_side_button"),
        )

        self.assertTrue(
            should_suppress(
                msg=0x020B,
                data=SimpleNamespace(mouseData=(1 << 16)),
                blocked_buttons=blocked,
            )
        )
        self.assertTrue(
            should_suppress(
                msg=0x020C,
                data=SimpleNamespace(mouseData=(2 << 16)),
                blocked_buttons=blocked,
            )
        )
        self.assertFalse(
            should_suppress(
                msg=0x0200,
                data=SimpleNamespace(mouseData=(1 << 16)),
                blocked_buttons=blocked,
            )
        )

    def test_extract_windows_xbutton_handles_invalid_payload(self) -> None:
        extractor = cast(
            Callable[[object], int | None],
            getattr(SideButtonListener, "_extract_windows_xbutton"),
        )
        self.assertIsNone(extractor(SimpleNamespace()))
        self.assertIsNone(extractor(SimpleNamespace(mouseData="bad")))

    def test_suppress_windows_side_button_calls_listener_suppress_event(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x2",
            rear_button="x1",
        )
        called: list[str] = []
        listener_holder = {
            "listener": SimpleNamespace(
                suppress_event=lambda: called.append("suppressed")
            )
        }
        suppress_side_button = cast(
            Callable[..., None],
            getattr(listener, "_suppress_windows_side_button"),
        )

        with patch("vibemouse.mouse_listener.sys.platform", "win32"):
            suppress_side_button(
                listener_holder=listener_holder,
                force=True,
            )

        self.assertEqual(called, ["suppressed"])

    def test_run_pynput_installs_win32_event_filter_for_side_buttons(self) -> None:
        listener = SideButtonListener(
            on_front_press=_noop_button,
            on_rear_press=_noop_button,
            front_button="x2",
            rear_button="x1",
        )
        run_pynput = cast(Callable[[], None], getattr(listener, "_run_pynput"))

        captured_kwargs: dict[str, object] = {}
        suppressed: list[str] = []

        class FakeListener:
            def start(self) -> None:
                filter_fn = cast(
                    Callable[[int, object], None],
                    captured_kwargs["win32_event_filter"],
                )
                filter_fn(0x020B, SimpleNamespace(mouseData=(1 << 16)))
                filter_fn(0x0200, SimpleNamespace(mouseData=(1 << 16)))
                listener._stop.set()

            def stop(self) -> None:
                return

            def suppress_event(self) -> None:
                suppressed.append("suppressed")

        def fake_listener_ctor(**kwargs: object) -> FakeListener:
            captured_kwargs.update(kwargs)
            return FakeListener()

        fake_mouse_module = SimpleNamespace(Listener=fake_listener_ctor)
        with (
            patch("vibemouse.mouse_listener.sys.platform", "win32"),
            patch(
                "vibemouse.mouse_listener.importlib.import_module",
                return_value=fake_mouse_module,
            ),
        ):
            run_pynput()

        self.assertIn("win32_event_filter", captured_kwargs)
        self.assertEqual(suppressed, ["suppressed"])

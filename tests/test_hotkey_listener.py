from __future__ import annotations

from types import SimpleNamespace
import unittest
from collections.abc import Callable
from typing import cast
from unittest.mock import patch

from vibemouse.hotkey_listener import HotkeyListener


class HotkeyListenerTests(unittest.TestCase):
    def test_constructor_rejects_duplicate_hotkeys(self) -> None:
        with self.assertRaisesRegex(ValueError, "must differ"):
            _ = HotkeyListener(
                on_front_press=lambda: None,
                on_rear_press=lambda: None,
                front_hotkey=" <CTRL> + <ALT> + F9 ",
                rear_hotkey="<ctrl>+<alt>+f9",
            )

    def test_dispatch_respects_debounce(self) -> None:
        front_calls: list[str] = []
        rear_calls: list[str] = []
        listener = HotkeyListener(
            on_front_press=lambda: front_calls.append("front"),
            on_rear_press=lambda: rear_calls.append("rear"),
            front_hotkey="<ctrl>+<alt>+f9",
            rear_hotkey="<ctrl>+<alt>+f10",
            debounce_s=0.15,
        )
        dispatch_front = cast(Callable[[], None], getattr(listener, "_dispatch_front_press"))
        dispatch_rear = cast(Callable[[], None], getattr(listener, "_dispatch_rear_press"))

        with patch("vibemouse.hotkey_listener.time.monotonic", side_effect=[1.0, 1.05, 1.3]):
            dispatch_front()
            dispatch_front()
            dispatch_front()

        with patch("vibemouse.hotkey_listener.time.monotonic", side_effect=[2.0, 2.05]):
            dispatch_rear()
            dispatch_rear()

        self.assertEqual(front_calls, ["front", "front"])
        self.assertEqual(rear_calls, ["rear"])

    def test_normalize_hotkey_wraps_function_keys_for_pynput(self) -> None:
        normalize = cast(
            Callable[[str], str],
            getattr(HotkeyListener, "_normalize_hotkey"),
        )
        self.assertEqual(
            normalize("<ctrl>+<alt>+f9"),
            "<ctrl>+<alt>+<f9>",
        )
        self.assertEqual(
            normalize("control+alt+F10"),
            "<ctrl>+<alt>+<f10>",
        )

    def test_run_pynput_registers_hotkeys_and_dispatches_callbacks(self) -> None:
        front_calls: list[str] = []
        rear_calls: list[str] = []
        listener = HotkeyListener(
            on_front_press=lambda: front_calls.append("front"),
            on_rear_press=lambda: rear_calls.append("rear"),
            front_hotkey=" <CTRL> + <ALT> + F9 ",
            rear_hotkey="<ctrl>+<alt>+f10",
            debounce_s=0.0,
        )
        run_pynput = cast(Callable[[], None], getattr(listener, "_run_pynput"))
        captured_hotkeys: dict[str, Callable[[], None]] = {}

        class FakeGlobalHotKeys:
            def __init__(self, hotkeys: dict[str, Callable[[], None]]) -> None:
                captured_hotkeys.update(hotkeys)
                self.hotkeys = hotkeys

            def start(self) -> None:
                self.hotkeys["<ctrl>+<alt>+<f9>"]()
                self.hotkeys["<ctrl>+<alt>+<f10>"]()
                listener._stop.set()

            def stop(self) -> None:
                return

        fake_keyboard_module = SimpleNamespace(GlobalHotKeys=FakeGlobalHotKeys)

        with patch(
            "vibemouse.hotkey_listener.importlib.import_module",
            return_value=fake_keyboard_module,
        ):
            run_pynput()

        self.assertEqual(
            set(captured_hotkeys.keys()),
            {"<ctrl>+<alt>+<f9>", "<ctrl>+<alt>+<f10>"},
        )
        self.assertEqual(front_calls, ["front"])
        self.assertEqual(rear_calls, ["rear"])

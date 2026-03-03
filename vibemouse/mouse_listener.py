from __future__ import annotations

import importlib
import json
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from typing import Protocol, cast

from vibemouse.system_integration import SystemIntegration, create_system_integration


ButtonCallback = Callable[[], None]
GestureCallback = Callable[[str], None]


class SideButtonListener:
    _WM_XBUTTONDOWN: int = 0x020B
    _WM_XBUTTONUP: int = 0x020C
    _XBUTTON1: int = 1
    _XBUTTON2: int = 2

    def __init__(
        self,
        on_front_press: ButtonCallback,
        on_rear_press: ButtonCallback,
        front_button: str,
        rear_button: str,
        debounce_s: float = 0.15,
        on_gesture: GestureCallback | None = None,
        gestures_enabled: bool = False,
        gesture_trigger_button: str = "rear",
        gesture_threshold_px: int = 120,
        gesture_freeze_pointer: bool = True,
        gesture_restore_cursor: bool = True,
        system_integration: SystemIntegration | None = None,
    ) -> None:
        if gesture_trigger_button not in {"front", "rear", "right"}:
            raise ValueError(
                "gesture_trigger_button must be one of: front, rear, right"
            )
        self._on_front_press: ButtonCallback = on_front_press
        self._on_rear_press: ButtonCallback = on_rear_press
        self._on_gesture: GestureCallback | None = on_gesture
        self._front_button: str = front_button
        self._rear_button: str = rear_button
        self._debounce_s: float = max(0.0, debounce_s)
        self._gestures_enabled: bool = gestures_enabled
        self._gesture_trigger_button: str = gesture_trigger_button
        self._gesture_threshold_px: int = max(1, gesture_threshold_px)
        self._gesture_freeze_pointer: bool = gesture_freeze_pointer
        self._gesture_restore_cursor: bool = gesture_restore_cursor
        self._system_integration: SystemIntegration = (
            system_integration
            if system_integration is not None
            else create_system_integration()
        )
        self._hyprland_session: bool = self._system_integration.is_hyprland
        self._last_front_press_monotonic: float = 0.0
        self._last_rear_press_monotonic: float = 0.0
        self._debounce_lock: threading.Lock = threading.Lock()
        self._gesture_lock: threading.Lock = threading.Lock()
        self._gesture_active: bool = False
        self._gesture_dx: int = 0
        self._gesture_dy: int = 0
        self._gesture_last_position: tuple[int, int] | None = None
        self._gesture_anchor_cursor: tuple[int, int] | None = None
        self._gesture_grabbed_device: _EvdevDevice | None = None
        self._stop: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._release_gesture_grab()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        last_error_summary: str | None = None
        while not self._stop.is_set():
            try:
                self._run_evdev()
                return
            except Exception as evdev_error:
                try:
                    self._run_pynput()
                    return
                except Exception as pynput_error:
                    summary = (
                        "Mouse listener backends unavailable "
                        + f"(evdev: {evdev_error}; pynput: {pynput_error}). Retrying..."
                    )
                    if summary != last_error_summary:
                        print(summary)
                        last_error_summary = summary
                    if self._stop.wait(1.0):
                        return

    def _run_evdev(self) -> None:
        import select

        try:
            evdev_module = importlib.import_module("evdev")
        except Exception as error:
            raise RuntimeError("evdev is not available") from error

        input_device_ctor = cast(_InputDeviceCtor, getattr(evdev_module, "InputDevice"))
        ecodes = cast(_Ecodes, getattr(evdev_module, "ecodes"))
        list_devices = cast(_ListDevicesFn, getattr(evdev_module, "list_devices"))

        side_codes = {
            "x1": ecodes.BTN_SIDE,
            "x2": ecodes.BTN_EXTRA,
        }
        front_code = side_codes[self._front_button]
        rear_code = side_codes[self._rear_button]
        trigger_code: int | None = None
        if self._gestures_enabled and self._gesture_trigger_button == "right":
            trigger_code = ecodes.BTN_RIGHT

        devices: list[_EvdevDevice] = []
        for path in list_devices():
            try:
                dev = input_device_ctor(path)
            except Exception:
                continue
            try:
                caps = dev.capabilities()
                key_cap = caps.get(ecodes.EV_KEY, [])
                required_codes = {front_code, rear_code}
                if trigger_code is not None:
                    required_codes.add(trigger_code)
                if not any(code in key_cap for code in required_codes):
                    dev.close()
                    continue

                btn_mouse = getattr(ecodes, "BTN_MOUSE", None)
                has_pointer_button = ecodes.BTN_LEFT in key_cap or (
                    isinstance(btn_mouse, int) and btn_mouse in key_cap
                )
                if not has_pointer_button:
                    dev.close()
                    continue

                devices.append(dev)
            except Exception:
                dev.close()

        if not devices:
            raise RuntimeError("No input device with side-button capability found")

        try:
            fd_map: dict[int, _EvdevDevice] = {dev.fd: dev for dev in devices}
            while not self._stop.is_set():
                ready, _, _ = select.select(list(fd_map.keys()), [], [], 0.2)
                for fd in ready:
                    dev = fd_map[fd]
                    for event in dev.read():
                        if event.type == ecodes.EV_KEY:
                            button_label: str | None = None
                            if event.code == front_code:
                                button_label = "front"
                            elif event.code == rear_code:
                                button_label = "rear"
                            elif (
                                trigger_code is not None and event.code == trigger_code
                            ):
                                button_label = "right"

                            if button_label is None:
                                continue

                            if (
                                self._gestures_enabled
                                and self._is_gesture_trigger_button(button_label)
                            ):
                                if event.value == 1:
                                    self._start_gesture_capture(source_device=dev)
                                elif event.value == 0:
                                    self._finish_gesture_capture(button_label)
                                continue

                            if event.value == 1:
                                self._dispatch_click(button_label)
                            continue

                        if (
                            self._gestures_enabled
                            and event.type == ecodes.EV_REL
                            and self._gesture_active
                        ):
                            if event.code == ecodes.REL_X:
                                self._accumulate_gesture_delta(dx=event.value, dy=0)
                            elif event.code == ecodes.REL_Y:
                                self._accumulate_gesture_delta(dx=0, dy=event.value)
        finally:
            self._release_gesture_grab()
            for dev in devices:
                dev.close()

    def _run_pynput(self) -> None:
        try:
            mouse_module = importlib.import_module("pynput.mouse")
        except Exception as error:
            raise RuntimeError("pynput.mouse is not available") from error

        listener_ctor = cast(_MouseListenerCtor, getattr(mouse_module, "Listener"))
        listener_holder: dict[str, _MouseListener] = {}

        button_map = {
            "x1": {"x1", "x_button1", "button8", "button4", "back", "browser_back"},
            "x2": {
                "x2",
                "x_button2",
                "button9",
                "button5",
                "forward",
                "browser_forward",
            },
        }

        front_candidates = button_map[self._front_button]
        rear_candidates = button_map[self._rear_button]
        right_candidates = {"right", "button2"}
        listener_kwargs: dict[str, object] = {}

        if sys.platform.startswith("win"):
            blocked_side_buttons = self._blocked_windows_side_buttons()

            def win32_event_filter(msg: int, data: object) -> None:
                if not self._should_suppress_windows_side_button(
                    msg=msg,
                    data=data,
                    blocked_buttons=blocked_side_buttons,
                ):
                    return
                listener = listener_holder.get("listener")
                if listener is None:
                    return
                try:
                    listener.suppress_event()
                except Exception:
                    return

            listener_kwargs["win32_event_filter"] = win32_event_filter

        def on_click(x: int, y: int, button: object, pressed: bool) -> None:
            btn_name = str(button).lower().split(".")[-1]
            button_label: str | None = None
            if btn_name in front_candidates:
                button_label = "front"
            elif btn_name in rear_candidates:
                button_label = "rear"
            elif btn_name in right_candidates:
                button_label = "right"
            if button_label is None:
                return
            if self._gestures_enabled and self._is_gesture_trigger_button(button_label):
                if pressed:
                    self._start_gesture_capture(initial_position=(x, y))
                else:
                    self._finish_gesture_capture(button_label)
                return

            if pressed:
                self._dispatch_click(button_label)

        def on_move(x: int, y: int) -> None:
            if not self._gestures_enabled:
                return
            self._accumulate_gesture_position(x, y)

        listener = listener_ctor(on_click=on_click, on_move=on_move, **listener_kwargs)
        listener_holder["listener"] = listener
        listener.start()
        try:
            while not self._stop.is_set():
                time.sleep(0.2)
        finally:
            listener.stop()

    def _suppress_windows_side_button(
        self,
        *,
        listener_holder: dict[str, _MouseListener],
        force: bool,
    ) -> None:
        if not force:
            return
        if not sys.platform.startswith("win"):
            return

        listener = listener_holder.get("listener")
        if listener is None:
            return
        listener.suppress_event()

    def _blocked_windows_side_buttons(self) -> set[int]:
        code_map = {
            "x1": self._XBUTTON1,
            "x2": self._XBUTTON2,
        }
        return {
            code_map[self._front_button],
            code_map[self._rear_button],
        }

    def _should_suppress_windows_side_button(
        self,
        *,
        msg: int,
        data: object,
        blocked_buttons: set[int] | None = None,
    ) -> bool:
        if msg not in {self._WM_XBUTTONDOWN, self._WM_XBUTTONUP}:
            return False

        xbutton = self._extract_windows_xbutton(data)
        if xbutton is None:
            return False

        blocked = (
            blocked_buttons
            if blocked_buttons is not None
            else self._blocked_windows_side_buttons()
        )
        return xbutton in blocked

    @staticmethod
    def _extract_windows_xbutton(data: object) -> int | None:
        mouse_data = getattr(data, "mouseData", None)
        if mouse_data is None:
            return None
        try:
            raw_value = int(mouse_data)
        except (TypeError, ValueError):
            return None
        return raw_value >> 16

    def _dispatch_click(self, button_label: str) -> None:
        if button_label == "front":
            self._dispatch_front_press()
            return
        if button_label == "rear":
            self._dispatch_rear_press()
            return

    def _is_gesture_trigger_button(self, button_label: str) -> bool:
        return button_label == self._gesture_trigger_button

    def _start_gesture_capture(
        self,
        *,
        initial_position: tuple[int, int] | None = None,
        source_device: _EvdevDevice | None = None,
    ) -> None:
        should_grab = False
        with self._gesture_lock:
            self._gesture_active = True
            self._gesture_dx = 0
            self._gesture_dy = 0
            self._gesture_last_position = initial_position
            if self._gesture_restore_cursor:
                self._gesture_anchor_cursor = self._read_cursor_position()
            else:
                self._gesture_anchor_cursor = None
            should_grab = self._gesture_freeze_pointer and source_device is not None

        if should_grab and source_device is not None:
            self._try_grab_device(source_device)

    def _accumulate_gesture_delta(self, *, dx: int, dy: int) -> None:
        with self._gesture_lock:
            if not self._gesture_active:
                return
            self._gesture_dx += dx
            self._gesture_dy += dy

    def _accumulate_gesture_position(self, x: int, y: int) -> None:
        with self._gesture_lock:
            if not self._gesture_active:
                return
            if self._gesture_last_position is None:
                self._gesture_last_position = (x, y)
                return
            last_x, last_y = self._gesture_last_position
            self._gesture_dx += x - last_x
            self._gesture_dy += y - last_y
            self._gesture_last_position = (x, y)

    def _finish_gesture_capture(self, button_label: str) -> None:
        with self._gesture_lock:
            if not self._gesture_active:
                return
            dx = self._gesture_dx
            dy = self._gesture_dy
            self._gesture_active = False
            self._gesture_dx = 0
            self._gesture_dy = 0
            self._gesture_last_position = None
            anchor_cursor = self._gesture_anchor_cursor
            self._gesture_anchor_cursor = None

        self._release_gesture_grab()

        direction = self._classify_gesture(dx, dy, self._gesture_threshold_px)
        if direction is None:
            self._dispatch_click(button_label)
            return
        self._dispatch_gesture(direction)
        if anchor_cursor is not None:
            self._restore_cursor_position(anchor_cursor)

    def _dispatch_gesture(self, direction: str) -> None:
        callback = self._on_gesture
        if callback is None:
            return
        callback(direction)

    def _try_grab_device(self, device: _EvdevDevice) -> None:
        try:
            device.grab()
        except Exception:
            return

        with self._gesture_lock:
            self._gesture_grabbed_device = device

    def _release_gesture_grab(self) -> None:
        with self._gesture_lock:
            grabbed = self._gesture_grabbed_device
            self._gesture_grabbed_device = None

        if grabbed is None:
            return

        try:
            grabbed.ungrab()
        except Exception:
            return

    def _read_cursor_position(self) -> tuple[int, int] | None:
        try:
            system_integration = self._system_integration
        except AttributeError:
            system_integration = None

        if system_integration is not None:
            try:
                return system_integration.cursor_position()
            except Exception:
                return None

        if not self._hyprland_session:
            return None
        try:
            proc = subprocess.run(
                ["hyprctl", "-j", "cursorpos"],
                capture_output=True,
                text=True,
                check=False,
                timeout=0.8,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        if proc.returncode != 0:
            return None

        try:
            payload = cast(dict[str, object], json.loads(proc.stdout))
        except json.JSONDecodeError:
            return None

        x_raw = payload.get("x")
        y_raw = payload.get("y")
        if not isinstance(x_raw, int | float) or not isinstance(y_raw, int | float):
            return None
        return int(x_raw), int(y_raw)

    def _restore_cursor_position(self, position: tuple[int, int]) -> None:
        try:
            system_integration = self._system_integration
        except AttributeError:
            system_integration = None

        if system_integration is not None:
            x, y = position
            try:
                _ = system_integration.move_cursor(x=x, y=y)
            except Exception:
                return
            return

        if not self._hyprland_session:
            return

        x, y = position
        try:
            _ = subprocess.run(
                ["hyprctl", "dispatch", "movecursor", str(x), str(y)],
                capture_output=True,
                text=True,
                check=False,
                timeout=0.8,
            )
        except (OSError, subprocess.TimeoutExpired):
            return

    @staticmethod
    def _classify_gesture(dx: int, dy: int, threshold_px: int) -> str | None:
        if max(abs(dx), abs(dy)) < threshold_px:
            return None
        if abs(dx) >= abs(dy):
            return "right" if dx > 0 else "left"
        return "down" if dy > 0 else "up"

    def _dispatch_front_press(self) -> None:
        if self._should_fire_front():
            self._on_front_press()

    def _dispatch_rear_press(self) -> None:
        if self._should_fire_rear():
            self._on_rear_press()

    def _should_fire_front(self) -> bool:
        now = time.monotonic()
        with self._debounce_lock:
            if now - self._last_front_press_monotonic < self._debounce_s:
                return False
            self._last_front_press_monotonic = now
            return True

    def _should_fire_rear(self) -> bool:
        now = time.monotonic()
        with self._debounce_lock:
            if now - self._last_rear_press_monotonic < self._debounce_s:
                return False
            self._last_rear_press_monotonic = now
            return True


class _EvdevEvent(Protocol):
    type: int
    value: int
    code: int


class _EvdevDevice(Protocol):
    fd: int

    def read(self) -> list[_EvdevEvent]: ...

    def capabilities(self) -> dict[int, list[int]]: ...

    def grab(self) -> None: ...

    def ungrab(self) -> None: ...

    def close(self) -> None: ...


class _InputDeviceCtor(Protocol):
    def __call__(self, path: str) -> _EvdevDevice: ...


class _ListDevicesFn(Protocol):
    def __call__(self) -> list[str]: ...


class _Ecodes(Protocol):
    BTN_SIDE: int
    BTN_EXTRA: int
    BTN_LEFT: int
    BTN_RIGHT: int
    EV_KEY: int
    EV_REL: int
    REL_X: int
    REL_Y: int


class _MouseListener(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...

    def suppress_event(self) -> None: ...


class _MouseListenerCtor(Protocol):
    def __call__(
        self,
        *,
        on_click: Callable[[int, int, object, bool], None],
        on_move: Callable[[int, int], None] | None = None,
        **kwargs: object,
    ) -> _MouseListener: ...

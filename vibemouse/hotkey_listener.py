from __future__ import annotations

import importlib
import re
import threading
import time
from collections.abc import Callable
from typing import Protocol, cast


ButtonCallback = Callable[[], None]


class HotkeyListener:
    _ALIASES: dict[str, str] = {
        "control": "ctrl",
        "windows": "cmd",
        "win": "cmd",
        "meta": "cmd",
        "option": "alt",
        "return": "enter",
        "escape": "esc",
    }
    _SPECIAL_KEYS: set[str] = {
        "ctrl",
        "alt",
        "shift",
        "cmd",
        "enter",
        "tab",
        "esc",
        "space",
        "insert",
        "delete",
        "home",
        "end",
        "up",
        "down",
        "left",
        "right",
    }

    def __init__(
        self,
        on_front_press: ButtonCallback,
        on_rear_press: ButtonCallback,
        *,
        front_hotkey: str,
        rear_hotkey: str,
        debounce_s: float = 0.15,
    ) -> None:
        normalized_front = self._normalize_hotkey(front_hotkey)
        normalized_rear = self._normalize_hotkey(rear_hotkey)
        if normalized_front == normalized_rear:
            raise ValueError("front_hotkey and rear_hotkey must differ")

        self._on_front_press: ButtonCallback = on_front_press
        self._on_rear_press: ButtonCallback = on_rear_press
        self._front_hotkey: str = normalized_front
        self._rear_hotkey: str = normalized_rear
        self._debounce_s: float = max(0.0, debounce_s)

        self._last_front_press_monotonic: float = 0.0
        self._last_rear_press_monotonic: float = 0.0
        self._debounce_lock: threading.Lock = threading.Lock()
        self._stop: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None
        self._listener: _GlobalHotKeys | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        listener = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        last_error_summary: str | None = None
        while not self._stop.is_set():
            try:
                self._run_pynput()
                return
            except Exception as error:
                summary = f"Hotkey listener unavailable ({error}). Retrying..."
                if summary != last_error_summary:
                    print(summary)
                    last_error_summary = summary
                if self._stop.wait(1.0):
                    return

    def _run_pynput(self) -> None:
        try:
            keyboard_module = importlib.import_module("pynput.keyboard")
        except Exception as error:
            raise RuntimeError("pynput.keyboard is not available") from error

        listener_ctor = cast(_GlobalHotKeysCtor, getattr(keyboard_module, "GlobalHotKeys"))
        listener = listener_ctor(
            {
                self._front_hotkey: self._dispatch_front_press,
                self._rear_hotkey: self._dispatch_rear_press,
            }
        )
        self._listener = listener
        listener.start()
        try:
            while not self._stop.wait(0.2):
                continue
        finally:
            self._listener = None
            listener.stop()

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

    @staticmethod
    def _normalize_hotkey(value: str) -> str:
        normalized = "".join(value.strip().lower().split())
        if not normalized:
            raise ValueError("hotkey must not be empty")
        tokens = normalized.split("+")
        canonical_tokens: list[str] = []
        for token in tokens:
            canonical_tokens.append(HotkeyListener._normalize_token(token))
        return "+".join(canonical_tokens)

    @staticmethod
    def _normalize_token(token: str) -> str:
        if token.startswith("<") and token.endswith(">") and len(token) > 2:
            inner = token[1:-1].strip()
            normalized_inner = HotkeyListener._normalize_plain_token(inner)
            if normalized_inner.startswith("<") and normalized_inner.endswith(">"):
                return normalized_inner
            return f"<{normalized_inner}>"
        return HotkeyListener._normalize_plain_token(token)

    @staticmethod
    def _normalize_plain_token(token: str) -> str:
        resolved = HotkeyListener._ALIASES.get(token, token)
        if re.fullmatch(r"f\d{1,2}", resolved):
            return f"<{resolved}>"
        if resolved in HotkeyListener._SPECIAL_KEYS:
            return f"<{resolved}>"
        return resolved


class _GlobalHotKeys(Protocol):
    def start(self) -> None: ...

    def stop(self) -> None: ...


class _GlobalHotKeysCtor(Protocol):
    def __call__(self, hotkeys: dict[str, Callable[[], None]]) -> _GlobalHotKeys: ...

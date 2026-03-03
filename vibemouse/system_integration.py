from __future__ import annotations

import ctypes
import importlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping
from typing import Protocol, cast


_TERMINAL_CLASS_HINTS: set[str] = {
    "foot",
    "kitty",
    "alacritty",
    "wezterm",
    "ghostty",
    "gnome-terminal",
    "gnome-terminal-server",
    "konsole",
    "tilix",
    "xterm",
    "terminator",
    "xfce4-terminal",
    "urxvt",
    "st",
    "tabby",
    "hyper",
    "warp",
    "windowsterminal",
    "wt",
}

_TERMINAL_TITLE_HINTS: set[str] = {
    "terminal",
    "tmux",
    "bash",
    "zsh",
    "fish",
    "powershell",
    "cmd.exe",
}


def is_terminal_window_payload(payload: Mapping[str, object]) -> bool:
    window_class = str(payload.get("class", "")).lower()
    initial_class = str(payload.get("initialClass", "")).lower()
    title = str(payload.get("title", "")).lower()

    if any(
        hint in window_class or hint in initial_class for hint in _TERMINAL_CLASS_HINTS
    ):
        return True

    return any(hint in title for hint in _TERMINAL_TITLE_HINTS)


class SystemIntegration(Protocol):
    @property
    def is_hyprland(self) -> bool: ...

    def send_shortcut(self, *, mod: str, key: str) -> bool: ...

    def active_window(self) -> dict[str, object] | None: ...

    def cursor_position(self) -> tuple[int, int] | None: ...

    def move_cursor(self, *, x: int, y: int) -> bool: ...

    def switch_workspace(self, direction: str) -> bool: ...

    def is_text_input_focused(self) -> bool | None: ...

    def send_enter_via_accessibility(self) -> bool | None: ...

    def is_terminal_window_active(self) -> bool | None: ...

    def paste_shortcuts(
        self, *, terminal_active: bool
    ) -> tuple[tuple[str, str], ...]: ...


class NoopSystemIntegration:
    @property
    def is_hyprland(self) -> bool:
        return False

    def send_shortcut(self, *, mod: str, key: str) -> bool:
        del mod
        del key
        return False

    def active_window(self) -> dict[str, object] | None:
        return None

    def cursor_position(self) -> tuple[int, int] | None:
        return None

    def move_cursor(self, *, x: int, y: int) -> bool:
        del x
        del y
        return False

    def switch_workspace(self, direction: str) -> bool:
        del direction
        return False

    def is_text_input_focused(self) -> bool | None:
        return None

    def send_enter_via_accessibility(self) -> bool | None:
        return None

    def is_terminal_window_active(self) -> bool | None:
        return None

    def paste_shortcuts(self, *, terminal_active: bool) -> tuple[tuple[str, str], ...]:
        del terminal_active
        return ()


class WindowsSystemIntegration(NoopSystemIntegration):
    def __init__(
        self,
        *,
        keyboard_controller: object | None = None,
        key_holder: object | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._keyboard_controller: object | None = keyboard_controller
        self._key_holder: object | None = key_holder
        source_env = env if env is not None else os.environ
        self._cursor_terminal_mode: bool = _read_bool_from_env(
            source_env,
            "VIBEMOUSE_WINDOWS_CURSOR_TERMINAL_MODE",
            False,
        )

    def send_shortcut(self, *, mod: str, key: str) -> bool:
        keyboard, key_holder = self._ensure_keyboard_objects()
        if keyboard is None or key_holder is None:
            return False

        modifiers = self._resolve_modifier_keys(mod, key_holder)
        main_key = self._resolve_main_key(key, key_holder)
        if main_key is None:
            return False

        try:
            for modifier in modifiers:
                self._keyboard_press(keyboard, modifier)
            self._keyboard_press(keyboard, main_key)
            self._keyboard_release(keyboard, main_key)
            for modifier in reversed(modifiers):
                self._keyboard_release(keyboard, modifier)
            return True
        except Exception:
            return False

    def active_window(self) -> dict[str, object] | None:
        return self._query_windows_active_window()

    def cursor_position(self) -> tuple[int, int] | None:
        return self._query_windows_cursor_position()

    def move_cursor(self, *, x: int, y: int) -> bool:
        return self._move_windows_cursor(x=x, y=y)

    def switch_workspace(self, direction: str) -> bool:
        del direction
        return False

    def is_terminal_window_active(self) -> bool | None:
        payload = self.active_window()
        if payload is None:
            return False
        if is_terminal_window_payload(payload):
            return True
        if self._cursor_terminal_mode and self._is_cursor_window_payload(payload):
            return True
        return False

    def paste_shortcuts(self, *, terminal_active: bool) -> tuple[tuple[str, str], ...]:
        if terminal_active:
            return (
                ("SHIFT", "Insert"),
                ("CTRL SHIFT", "V"),
                ("CTRL", "V"),
            )
        return (("CTRL", "V"),)

    @staticmethod
    def _is_cursor_window_payload(payload: Mapping[str, object]) -> bool:
        process_name = str(payload.get("process", "")).lower()
        window_class = str(payload.get("class", "")).lower()
        title = str(payload.get("title", "")).lower()

        if process_name in {"cursor.exe", "cursor"}:
            return True
        if "cursor" in window_class:
            return True
        return "cursor" in title

    def _ensure_keyboard_objects(self) -> tuple[object | None, object | None]:
        if self._keyboard_controller is not None and self._key_holder is not None:
            return self._keyboard_controller, self._key_holder

        try:
            keyboard_module = importlib.import_module("pynput.keyboard")
        except Exception:
            return None, None

        try:
            controller_ctor = cast(object, getattr(keyboard_module, "Controller"))
            key_holder = cast(object, getattr(keyboard_module, "Key"))
        except Exception:
            return None, None

        if not callable(controller_ctor):
            return None, None

        try:
            controller = controller_ctor()
        except Exception:
            return None, None

        self._keyboard_controller = controller
        self._key_holder = key_holder
        return controller, key_holder

    @staticmethod
    def _resolve_modifier_keys(mod: str, key_holder: object) -> list[object]:
        mapping = {
            "CTRL": "ctrl",
            "SHIFT": "shift",
            "ALT": "alt",
            "CMD": "cmd",
            "WIN": "cmd",
            "META": "cmd",
        }
        resolved: list[object] = []
        for token in mod.strip().upper().split():
            attr = mapping.get(token)
            if attr is None:
                continue
            value = getattr(key_holder, attr, None)
            if value is not None:
                resolved.append(value)
        return resolved

    @staticmethod
    def _resolve_main_key(key: str, key_holder: object) -> object | None:
        normalized = key.strip()
        if not normalized:
            return None
        if len(normalized) == 1:
            return normalized.lower()

        mapping = {
            "ENTER": "enter",
            "RETURN": "enter",
            "INSERT": "insert",
            "TAB": "tab",
            "SPACE": "space",
            "ESC": "esc",
            "ESCAPE": "esc",
        }
        attr = mapping.get(normalized.upper())
        if attr is None:
            return None
        return getattr(key_holder, attr, None)

    @staticmethod
    def _keyboard_press(controller: object, key: object) -> None:
        press = cast(object, getattr(controller, "press"))
        cast(_PressReleaseFn, press)(key)

    @staticmethod
    def _keyboard_release(controller: object, key: object) -> None:
        release = cast(object, getattr(controller, "release"))
        cast(_PressReleaseFn, release)(key)

    @staticmethod
    def _query_windows_active_window() -> dict[str, object] | None:
        if not sys.platform.startswith("win"):
            return None

        user32 = _load_windows_user32()
        kernel32 = _load_windows_kernel32()
        if user32 is None or kernel32 is None:
            return None

        hwnd = int(user32.GetForegroundWindow())
        if hwnd == 0:
            return None

        title_buf = ctypes.create_unicode_buffer(512)
        class_buf = ctypes.create_unicode_buffer(256)

        _ = user32.GetWindowTextW(hwnd, title_buf, len(title_buf))
        _ = user32.GetClassNameW(hwnd, class_buf, len(class_buf))

        pid = ctypes.c_ulong(0)
        _ = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        process_name = ""
        process_handle = kernel32.OpenProcess(0x1000, False, pid.value)
        if process_handle:
            image_buf = ctypes.create_unicode_buffer(512)
            size = ctypes.c_ulong(len(image_buf))
            ok = kernel32.QueryFullProcessImageNameW(
                process_handle,
                0,
                image_buf,
                ctypes.byref(size),
            )
            _ = kernel32.CloseHandle(process_handle)
            if ok:
                raw_path = image_buf.value
                if raw_path:
                    process_name = os.path.basename(raw_path).lower()

        window_class = class_buf.value
        return {
            "hwnd": hwnd,
            "title": title_buf.value,
            "class": window_class,
            "initialClass": window_class,
            "pid": int(pid.value),
            "process": process_name,
        }

    @staticmethod
    def _query_windows_cursor_position() -> tuple[int, int] | None:
        if not sys.platform.startswith("win"):
            return None

        user32 = _load_windows_user32()
        if user32 is None:
            return None

        point = _WindowsPoint()
        ok = user32.GetCursorPos(ctypes.byref(point))
        if not ok:
            return None
        return int(point.x), int(point.y)

    @staticmethod
    def _move_windows_cursor(*, x: int, y: int) -> bool:
        if not sys.platform.startswith("win"):
            return False

        user32 = _load_windows_user32()
        if user32 is None:
            return False

        ok = user32.SetCursorPos(int(x), int(y))
        return bool(ok)


class MacOSSystemIntegration(NoopSystemIntegration):
    def paste_shortcuts(self, *, terminal_active: bool) -> tuple[tuple[str, str], ...]:
        if terminal_active:
            return (("CMD", "V"),)
        return (("CMD", "V"),)


class HyprlandSystemIntegration:
    @property
    def is_hyprland(self) -> bool:
        return True

    def send_shortcut(self, *, mod: str, key: str) -> bool:
        mod_part = mod.strip().upper()
        if mod_part:
            arg = f"{mod_part}, {key}, activewindow"
        else:
            arg = f", {key}, activewindow"
        return self._dispatch(["sendshortcut", arg], timeout=1.0)

    def active_window(self) -> dict[str, object] | None:
        return self._query_json(["activewindow"], timeout=1.0)

    def cursor_position(self) -> tuple[int, int] | None:
        payload = self._query_json(["cursorpos"], timeout=0.8)
        if payload is None:
            return None

        x_raw = payload.get("x")
        y_raw = payload.get("y")
        if not isinstance(x_raw, int | float) or not isinstance(y_raw, int | float):
            return None

        return int(x_raw), int(y_raw)

    def move_cursor(self, *, x: int, y: int) -> bool:
        return self._dispatch(["movecursor", str(x), str(y)], timeout=0.8)

    def switch_workspace(self, direction: str) -> bool:
        workspace_arg = "e-1" if direction == "left" else "e+1"
        return self._dispatch(["workspace", workspace_arg], timeout=1.0)

    def is_text_input_focused(self) -> bool | None:
        return probe_text_input_focus_via_atspi()

    def send_enter_via_accessibility(self) -> bool | None:
        return probe_send_enter_via_atspi()

    def is_terminal_window_active(self) -> bool | None:
        payload = self.active_window()
        if payload is None:
            return False
        return is_terminal_window_payload(payload)

    def paste_shortcuts(self, *, terminal_active: bool) -> tuple[tuple[str, str], ...]:
        if terminal_active:
            return (
                ("CTRL SHIFT", "V"),
                ("SHIFT", "Insert"),
                ("CTRL", "V"),
            )
        return (("CTRL", "V"),)

    @staticmethod
    def _dispatch(args: list[str], *, timeout: float) -> bool:
        try:
            proc = subprocess.run(
                ["hyprctl", "dispatch", *args],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False

        return proc.returncode == 0 and proc.stdout.strip() == "ok"

    @staticmethod
    def _query_json(args: list[str], *, timeout: float) -> dict[str, object] | None:
        try:
            proc = subprocess.run(
                ["hyprctl", "-j", *args],
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None

        if proc.returncode != 0:
            return None

        try:
            payload_obj = cast(object, json.loads(proc.stdout))
        except json.JSONDecodeError:
            return None

        if not isinstance(payload_obj, dict):
            return None

        return cast(dict[str, object], payload_obj)


def detect_hyprland_session(*, env: Mapping[str, str] | None = None) -> bool:
    source = env if env is not None else os.environ
    desktop = source.get("XDG_CURRENT_DESKTOP", "")
    if "hyprland" in desktop.lower():
        return True
    return bool(source.get("HYPRLAND_INSTANCE_SIGNATURE"))


def create_system_integration(
    *,
    env: Mapping[str, str] | None = None,
    platform_name: str | None = None,
) -> SystemIntegration:
    if detect_hyprland_session(env=env):
        return HyprlandSystemIntegration()

    normalized_platform = (
        (platform_name if platform_name is not None else sys.platform).strip().lower()
    )
    if normalized_platform.startswith("win"):
        return WindowsSystemIntegration(env=env)
    if normalized_platform == "darwin":
        return MacOSSystemIntegration()

    return NoopSystemIntegration()


def probe_text_input_focus_via_atspi(*, timeout_s: float = 1.5) -> bool:
    script = (
        "import gi\n"
        "gi.require_version('Atspi', '2.0')\n"
        "from gi.repository import Atspi\n"
        "obj = Atspi.get_desktop(0).get_focus()\n"
        "editable = False\n"
        "role = ''\n"
        "if obj is not None:\n"
        "    role = obj.get_role_name().lower()\n"
        "    attrs = obj.get_attributes() or []\n"
        "    for it in attrs:\n"
        "        s = str(it).lower()\n"
        "        if s == 'editable:true' or s.endswith(':editable:true'):\n"
        "            editable = True\n"
        "            break\n"
        "roles = {'text', 'entry', 'password text', 'terminal', 'paragraph', 'document text', 'document web'}\n"
        "print('1' if editable or role in roles else '0')\n"
    )

    try:
        proc = subprocess.run(
            ["python3", "-c", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False

    return proc.returncode == 0 and proc.stdout.strip() == "1"


def load_atspi_module() -> object | None:
    try:
        gi = importlib.import_module("gi")
        require_version = cast(_RequireVersionFn, getattr(gi, "require_version"))
        require_version("Atspi", "2.0")
        atspi_repo = cast(object, importlib.import_module("gi.repository"))
        return cast(object, getattr(atspi_repo, "Atspi"))
    except Exception:
        return None


def probe_send_enter_via_atspi(
    *, atspi_module: object | None = None, lazy_load: bool = True
) -> bool:
    module = atspi_module
    if module is None and lazy_load:
        module = load_atspi_module()
    if module is None:
        return False

    try:
        key_synth = cast(object, getattr(module, "KeySynthType"))
        press_release = cast(object, getattr(key_synth, "PRESSRELEASE"))
        generate_keyboard_event = cast(
            _GenerateKeyboardEventFn,
            getattr(module, "generate_keyboard_event"),
        )
        return bool(generate_keyboard_event(65293, None, press_release))
    except Exception:
        return False


class _GenerateKeyboardEventFn(Protocol):
    def __call__(
        self,
        keyval: int,
        keystring: str | None,
        synth_type: object,
    ) -> bool: ...


class _RequireVersionFn(Protocol):
    def __call__(self, namespace: str, version: str) -> None: ...


class _PressReleaseFn(Protocol):
    def __call__(self, key: object) -> None: ...


class _WindowsPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def _load_windows_user32() -> object | None:
    if not sys.platform.startswith("win"):
        return None
    try:
        return cast(object, ctypes.windll.user32)
    except Exception:
        return None


def _load_windows_kernel32() -> object | None:
    if not sys.platform.startswith("win"):
        return None
    try:
        return cast(object, ctypes.windll.kernel32)
    except Exception:
        return None


def _read_bool_from_env(
    env: Mapping[str, str],
    name: str,
    default: bool,
) -> bool:
    raw = env.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

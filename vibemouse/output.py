from __future__ import annotations

import importlib
import json
import os
import subprocess
import time
from typing import Protocol, cast

import pyperclip


class TextOutput:
    def __init__(self) -> None:
        try:
            keyboard_module = importlib.import_module("pynput.keyboard")
        except Exception as error:
            raise RuntimeError(
                f"Failed to load keyboard control dependencies: {error}"
            ) from error

        controller_ctor = cast(
            _ControllerCtor,
            getattr(cast(object, keyboard_module), "Controller"),
        )
        key_holder = cast(
            _KeyHolder,
            getattr(cast(object, keyboard_module), "Key"),
        )
        self._kb: _KeyboardController = controller_ctor()
        self._enter_key: object = key_holder.enter
        self._ctrl_key: object = key_holder.ctrl
        self._shift_key: object = key_holder.shift
        self._atspi: object | None = self._load_atspi_module()
        self._hyprland_session: bool = self._detect_hyprland_session()

    def send_enter(self, *, mode: str = "enter") -> None:
        normalized = mode.strip().lower()
        if normalized == "none":
            return
        if normalized == "enter":
            if self._send_hyprland_shortcut(mod="", key="Return"):
                return
            if self._send_enter_via_atspi():
                return
            self._tap_key(self._enter_key)
            return
        if normalized == "ctrl_enter":
            self._tap_modified_key(self._ctrl_key, self._enter_key)
            return
        if normalized == "shift_enter":
            self._tap_modified_key(self._shift_key, self._enter_key)
            return
        raise ValueError(f"Unsupported enter mode: {mode!r}")

    def inject_or_clipboard(self, text: str, *, auto_paste: bool = False) -> str:
        normalized = text.strip()
        if not normalized:
            return "empty"

        if self._is_text_input_focused():
            self._kb.type(normalized)
            return "typed"

        pyperclip.copy(normalized)
        if auto_paste:
            try:
                self._paste_clipboard()
                return "pasted"
            except Exception:
                return "clipboard"
        return "clipboard"

    def _paste_clipboard(self) -> None:
        if self._is_hyprland_terminal_active():
            if self._send_hyprland_shortcut(mod="CTRL SHIFT", key="V"):
                return
            if self._send_hyprland_shortcut(mod="SHIFT", key="Insert"):
                return

        if self._send_hyprland_shortcut(mod="CTRL", key="V"):
            return
        self._kb.press(self._ctrl_key)
        self._kb.press("v")
        self._kb.release("v")
        self._kb.release(self._ctrl_key)

    def _tap_key(self, key: object) -> None:
        self._kb.press(key)
        time.sleep(0.012)
        self._kb.release(key)

    def _tap_modified_key(self, modifier: object, key: object) -> None:
        self._kb.press(modifier)
        self._kb.press(key)
        time.sleep(0.012)
        self._kb.release(key)
        self._kb.release(modifier)

    def _send_enter_via_atspi(self) -> bool:
        atspi_module = self._atspi
        if atspi_module is None:
            return False

        try:
            key_synth = cast(object, getattr(atspi_module, "KeySynthType"))
            press_release = cast(object, getattr(key_synth, "PRESSRELEASE"))
            generate_keyboard_event = cast(
                _GenerateKeyboardEventFn,
                getattr(atspi_module, "generate_keyboard_event"),
            )
            return bool(generate_keyboard_event(65293, None, press_release))
        except Exception:
            return False

    def _send_hyprland_shortcut(self, *, mod: str, key: str) -> bool:
        if not self._hyprland_session:
            return False

        mod_part = mod.strip().upper()
        if mod_part:
            arg = f"{mod_part}, {key}, activewindow"
        else:
            arg = f", {key}, activewindow"

        try:
            proc = subprocess.run(
                ["hyprctl", "dispatch", "sendshortcut", arg],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False

        return proc.returncode == 0 and proc.stdout.strip() == "ok"

    def _is_hyprland_terminal_active(self) -> bool:
        if not self._hyprland_session:
            return False

        try:
            proc = subprocess.run(
                ["hyprctl", "-j", "activewindow"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False

        if proc.returncode != 0:
            return False

        try:
            payload_obj = cast(object, json.loads(proc.stdout))
        except json.JSONDecodeError:
            return False

        if not isinstance(payload_obj, dict):
            return False

        payload_map = cast(dict[str, object], payload_obj)

        window_class = str(payload_map.get("class", "")).lower()
        initial_class = str(payload_map.get("initialClass", "")).lower()
        title = str(payload_map.get("title", "")).lower()

        terminal_hints = {
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
        }
        if any(
            hint in window_class or hint in initial_class for hint in terminal_hints
        ):
            return True

        title_hints = {
            "terminal",
            "tmux",
            "bash",
            "zsh",
            "fish",
            "powershell",
        }
        return any(hint in title for hint in title_hints)

    @staticmethod
    def _load_atspi_module() -> object | None:
        try:
            gi = importlib.import_module("gi")
            require_version = cast(_RequireVersionFn, getattr(gi, "require_version"))
            require_version("Atspi", "2.0")
            atspi_repo = cast(object, importlib.import_module("gi.repository"))
            return cast(object, getattr(atspi_repo, "Atspi"))
        except Exception:
            return None

    @staticmethod
    def _detect_hyprland_session() -> bool:
        desktop = os.getenv("XDG_CURRENT_DESKTOP", "")
        if "hyprland" in desktop.lower():
            return True
        return bool(os.getenv("HYPRLAND_INSTANCE_SIGNATURE"))

    def _is_text_input_focused(self) -> bool:
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
                timeout=1.5,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False

        return proc.returncode == 0 and proc.stdout.strip() == "1"


class _KeyboardController(Protocol):
    def press(self, key: object) -> None: ...

    def release(self, key: object) -> None: ...

    def type(self, text: str) -> None: ...


class _ControllerCtor(Protocol):
    def __call__(self) -> _KeyboardController: ...


class _KeyHolder(Protocol):
    enter: object
    ctrl: object
    shift: object


class _GenerateKeyboardEventFn(Protocol):
    def __call__(
        self,
        keyval: int,
        keystring: str | None,
        synth_type: object,
    ) -> bool: ...


class _RequireVersionFn(Protocol):
    def __call__(self, namespace: str, version: str) -> None: ...

from __future__ import annotations

import importlib
import json
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, cast

import pyperclip

from vibemouse.system_integration import (
    SystemIntegration,
    create_system_integration,
    is_terminal_window_payload,
    load_atspi_module,
    probe_text_input_focus_via_atspi,
    probe_send_enter_via_atspi,
)
from vibemouse.text_postprocess import UserTextProcessor

if TYPE_CHECKING:
    from vibemouse.integrations.openclaw import OpenClawDispatchResult


class TextOutput:
    def __init__(
        self,
        *,
        system_integration: SystemIntegration | None = None,
        openclaw_enabled: bool = False,
        openclaw_command: str = "openclaw",
        openclaw_agent: str | None = None,
        openclaw_timeout_s: float = 20.0,
        openclaw_retries: int = 0,
        user_dictionary_file: Path | None = None,
        text_history_file: Path | None = None,
        text_history_enabled: bool = True,
        strip_emoji: bool = True,
    ) -> None:
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
        self._atspi: object | None = load_atspi_module()
        self._system_integration: SystemIntegration = (
            system_integration
            if system_integration is not None
            else create_system_integration()
        )
        self._hyprland_session: bool = self._system_integration.is_hyprland
        self._openclaw_enabled = bool(openclaw_enabled)
        self._openclaw_dispatcher: object | None = None
        if self._openclaw_enabled:
            self._openclaw_dispatcher = self._create_openclaw_dispatcher(
                command=openclaw_command,
                agent=openclaw_agent,
                timeout_s=openclaw_timeout_s,
                retries=openclaw_retries,
            )
        self._text_processor: UserTextProcessor | None = None
        if user_dictionary_file is not None and text_history_file is not None:
            self._text_processor = UserTextProcessor(
                dictionary_file=user_dictionary_file,
                history_file=text_history_file,
                history_enabled=text_history_enabled,
                strip_emoji=strip_emoji,
            )

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
        normalized = self._prepare_text(text)
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

    def send_to_openclaw(self, text: str) -> str:
        return self.send_to_openclaw_result(text).route

    def send_to_openclaw_result(self, text: str) -> "OpenClawDispatchResult":
        normalized = self._prepare_text(text)
        dispatcher = getattr(self, "_openclaw_dispatcher", None)
        enabled = bool(getattr(self, "_openclaw_enabled", True))
        if dispatcher is None and not enabled:
            pyperclip.copy(normalized)
            result_type = self._openclaw_result_type()
            return result_type(route="clipboard", reason="integration_disabled")
        if dispatcher is None:
            dispatcher = self._create_openclaw_dispatcher(
                command=str(getattr(self, "_openclaw_command", "openclaw")),
                agent=getattr(self, "_openclaw_agent", None),
                timeout_s=float(getattr(self, "_openclaw_timeout_s", 20.0)),
                retries=int(getattr(self, "_openclaw_retries", 0)),
            )
        dispatch = cast(object, getattr(dispatcher, "dispatch"))
        return cast("OpenClawDispatchResult", dispatch(normalized))

    @staticmethod
    def _create_openclaw_dispatcher(
        *,
        command: str,
        agent: str | None,
        timeout_s: float,
        retries: int,
    ) -> object:
        module = importlib.import_module("vibemouse.integrations.openclaw")
        dispatcher_type = cast(object, getattr(module, "OpenClawDispatcher"))
        if not callable(dispatcher_type):
            raise RuntimeError("Experimental OpenClaw dispatcher is unavailable")
        return dispatcher_type(
            command=command,
            agent=agent,
            timeout_s=timeout_s,
            retries=retries,
        )

    @staticmethod
    def _openclaw_result_type() -> object:
        module = importlib.import_module("vibemouse.integrations.openclaw")
        result_type = cast(object, getattr(module, "OpenClawDispatchResult"))
        if not callable(result_type):
            raise RuntimeError("Experimental OpenClaw result type is unavailable")
        return result_type

    def _paste_clipboard(self) -> None:
        terminal_active = self._is_hyprland_terminal_active()
        for mod, key in self._paste_shortcuts(terminal_active=terminal_active):
            if self._send_platform_shortcut(mod=mod, key=key):
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
        try:
            system_integration = self._system_integration
        except AttributeError:
            system_integration = None

        if system_integration is not None:
            try:
                handled = system_integration.send_enter_via_accessibility()
            except Exception:
                handled = None
            if handled is True:
                return True

        atspi_module = getattr(self, "_atspi", None)
        return probe_send_enter_via_atspi(
            atspi_module=atspi_module,
            lazy_load=False,
        )

    def _paste_shortcuts(self, *, terminal_active: bool) -> tuple[tuple[str, str], ...]:
        try:
            system_integration = self._system_integration
        except AttributeError:
            system_integration = None

        if system_integration is not None:
            try:
                shortcuts = system_integration.paste_shortcuts(
                    terminal_active=terminal_active
                )
            except Exception:
                shortcuts = ()
            if shortcuts:
                return shortcuts

        if terminal_active:
            return (
                ("CTRL SHIFT", "V"),
                ("SHIFT", "Insert"),
                ("CTRL", "V"),
            )
        return (("CTRL", "V"),)

    def _send_platform_shortcut(self, *, mod: str, key: str) -> bool:
        try:
            system_integration = self._system_integration
        except AttributeError:
            system_integration = None

        if system_integration is not None:
            try:
                if bool(system_integration.send_shortcut(mod=mod, key=key)):
                    return True
                if not self._hyprland_session:
                    return False
            except Exception:
                if not self._hyprland_session:
                    return False

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

    def _send_hyprland_shortcut(self, *, mod: str, key: str) -> bool:
        return self._send_platform_shortcut(mod=mod, key=key)

    def _is_terminal_window_active(self) -> bool:
        payload_map: dict[str, object] | None = None
        try:
            system_integration = self._system_integration
        except AttributeError:
            system_integration = None

        if system_integration is not None:
            try:
                terminal_active = system_integration.is_terminal_window_active()
            except Exception:
                terminal_active = None
            if isinstance(terminal_active, bool):
                return terminal_active

        if not self._hyprland_session:
            return False

        if payload_map is None:
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

        return is_terminal_window_payload(payload_map)

    def _is_hyprland_terminal_active(self) -> bool:
        return self._is_terminal_window_active()

    def _is_text_input_focused(self) -> bool:
        try:
            system_integration = self._system_integration
        except AttributeError:
            system_integration = None

        if system_integration is not None:
            try:
                focused = system_integration.is_text_input_focused()
            except Exception:
                focused = None
            if isinstance(focused, bool):
                return focused

        return probe_text_input_focus_via_atspi()

    def _prepare_text(self, text: str) -> str:
        processor = getattr(self, "_text_processor", None)
        if processor is None:
            return text.strip()
        try:
            return processor.process(text)
        except Exception:
            return text.strip()


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

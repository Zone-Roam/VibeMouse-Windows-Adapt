from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass

import pyperclip


@dataclass(frozen=True)
class OpenClawDispatchResult:
    route: str
    reason: str


class OpenClawDispatcher:
    """Experimental OpenClaw bridge, isolated from the default runtime path."""

    def __init__(
        self,
        *,
        command: str,
        agent: str | None,
        timeout_s: float,
        retries: int,
    ) -> None:
        self._command = command
        self._agent = agent
        self._timeout_s = max(0.5, timeout_s)
        self._retries = max(0, int(retries))

    def dispatch(self, text: str) -> OpenClawDispatchResult:
        normalized = text.strip()
        if not normalized:
            return OpenClawDispatchResult(route="empty", reason="empty_text")

        command = self._build_command(normalized)
        if command is None:
            pyperclip.copy(normalized)
            return OpenClawDispatchResult(route="clipboard", reason="invalid_command")

        attempts = max(1, self._retries + 1)
        last_reason = "spawn_error"
        for attempt in range(attempts):
            try:
                _ = subprocess.Popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                reason = "dispatched" if attempt == 0 else f"dispatched_after_retry_{attempt}"
                return OpenClawDispatchResult(route="openclaw", reason=reason)
            except OSError as error:
                last_reason = f"spawn_error:{error.__class__.__name__}"

        pyperclip.copy(normalized)
        return OpenClawDispatchResult(route="clipboard", reason=last_reason)

    def _build_command(self, message: str) -> list[str] | None:
        raw_command = self._command.strip()
        if not raw_command:
            return None
        try:
            parts = shlex.split(raw_command)
        except ValueError:
            return None
        if not parts:
            return None

        command = [*parts, "agent", "--message", message, "--json"]
        if isinstance(self._agent, str) and self._agent.strip():
            command.extend(["--agent", self._agent.strip()])
        return command

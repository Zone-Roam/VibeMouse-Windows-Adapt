from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import cast


class UserTextProcessor:
    _ASR_TAG_PATTERN = re.compile(r"<\|[^|>]+?\|>")
    _EMOJI_PATTERN = re.compile(
        "["
        + "\U0001F300-\U0001F5FF"
        + "\U0001F600-\U0001F64F"
        + "\U0001F680-\U0001F6FF"
        + "\U0001F900-\U0001FAFF"
        + "\u2600-\u26FF"
        + "\u2700-\u27BF"
        + "]"
    )

    def __init__(
        self,
        *,
        dictionary_file: Path,
        history_file: Path,
        history_enabled: bool,
        strip_emoji: bool,
    ) -> None:
        self._dictionary_file = dictionary_file
        self._history_file = history_file
        self._history_enabled = history_enabled
        self._strip_emoji = strip_emoji
        self._rules_lock = threading.Lock()
        self._history_lock = threading.Lock()
        self._dictionary_mtime_ns: int | None = None
        self._rules: list[tuple[str, str]] = []
        self._ensure_dictionary_file_exists()

    def process(self, text: str) -> str:
        raw = text.strip()
        if not raw:
            return ""

        self._reload_rules_if_needed()
        normalized = self._ASR_TAG_PATTERN.sub("", raw)
        if self._strip_emoji:
            normalized = self._EMOJI_PATTERN.sub("", normalized)
        normalized = " ".join(normalized.split())
        replaced = self._apply_rules(normalized)
        final_text = replaced.strip()
        self._append_history(raw_text=raw, processed_text=final_text)
        return final_text

    def _apply_rules(self, text: str) -> str:
        if not text:
            return ""
        with self._rules_lock:
            rules = list(self._rules)
        result = text
        for source, target in rules:
            if not source:
                continue
            pattern = re.compile(re.escape(source), flags=re.IGNORECASE)
            result = pattern.sub(target, result)
        return result

    def _reload_rules_if_needed(self) -> None:
        try:
            mtime_ns = self._dictionary_file.stat().st_mtime_ns
        except OSError:
            return
        if self._dictionary_mtime_ns == mtime_ns:
            return

        rules = self._load_rules()
        with self._rules_lock:
            self._rules = rules
            self._dictionary_mtime_ns = mtime_ns

    def _load_rules(self) -> list[tuple[str, str]]:
        try:
            payload_obj = json.loads(self._dictionary_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        if not isinstance(payload_obj, dict):
            return []
        payload = cast(dict[str, object], payload_obj)

        replacements_obj = payload.get("replacements")
        if isinstance(replacements_obj, dict):
            mapping_obj = replacements_obj
        else:
            mapping_obj = payload

        rules: list[tuple[str, str]] = []
        for key, value in mapping_obj.items():
            if str(key).startswith("_"):
                continue
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            source = key.strip()
            target = value.strip()
            if not source:
                continue
            rules.append((source, target))

        rules.sort(key=lambda item: len(item[0]), reverse=True)
        return rules

    def _append_history(self, *, raw_text: str, processed_text: str) -> None:
        if not self._history_enabled:
            return
        if not processed_text:
            return
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "raw": raw_text,
            "processed": processed_text,
        }
        line = json.dumps(payload, ensure_ascii=False)
        with self._history_lock:
            try:
                self._history_file.parent.mkdir(parents=True, exist_ok=True)
                with self._history_file.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except OSError:
                return

    def _ensure_dictionary_file_exists(self) -> None:
        if self._dictionary_file.exists():
            return
        template = {
            "_help": [
                "Edit replacements to correct your common ASR mistakes.",
                "Keys are matched case-insensitively.",
            ],
            "replacements": {
                "telegarm": "Telegram",
                "open claw": "OpenClaw",
                "chat g p t": "ChatGPT",
            },
        }
        try:
            self._dictionary_file.parent.mkdir(parents=True, exist_ok=True)
            self._dictionary_file.write_text(
                json.dumps(template, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return

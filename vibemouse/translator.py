from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib import error, request


_CJK_PATTERN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


@dataclass(frozen=True)
class TranslationResult:
    text: str
    status: str


class ApiTextTranslator:
    def __init__(
        self,
        *,
        provider: str,
        api_base: str,
        api_key: str,
        model: str,
        timeout_s: float,
        retries: int,
        only_if_chinese: bool,
    ) -> None:
        self._provider = provider.strip().lower() or "openai_compatible"
        self._api_base = api_base.rstrip("/")
        self._api_key = api_key.strip()
        self._model = model.strip()
        self._timeout_s = max(0.5, float(timeout_s))
        self._retries = max(0, int(retries))
        self._only_if_chinese = bool(only_if_chinese)

    @property
    def has_api_key(self) -> bool:
        return bool(self._api_key)

    @property
    def model_name(self) -> str:
        return self._model

    def translate_cn_to_en(self, text: str) -> TranslationResult:
        raw = text.strip()
        if not raw:
            return TranslationResult(text="", status="empty_text")
        if self._only_if_chinese and not _contains_chinese(raw):
            return TranslationResult(text=raw, status="skip_non_chinese")
        if not self._api_key:
            return TranslationResult(text=raw, status="skip_no_api_key")

        for attempt in range(max(1, self._retries + 1)):
            result = self._translate_once(raw)
            if result is not None:
                return result
            if attempt < self._retries:
                continue
        return TranslationResult(text=raw, status="api_failed")

    def _translate_once(self, text: str) -> TranslationResult | None:
        if self._provider != "openai_compatible":
            return TranslationResult(text=text, status="unsupported_provider")

        endpoint = f"{self._api_base}/chat/completions"
        payload = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Translate Chinese dictation into natural English. "
                        + "Keep technical terms and product names unchanged when appropriate. "
                        + "Return translated text only."
                    ),
                },
                {"role": "user", "content": text},
            ],
        }
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            endpoint,
            method="POST",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        try:
            with request.urlopen(req, timeout=self._timeout_s) as response:
                raw_resp = response.read().decode("utf-8", errors="replace")
        except (error.HTTPError, error.URLError, TimeoutError, OSError):
            return None

        try:
            payload_obj = json.loads(raw_resp)
        except json.JSONDecodeError:
            return None

        translated = _extract_message_text(payload_obj).strip()
        if not translated:
            return None
        return TranslationResult(text=translated, status="translated")


def _contains_chinese(text: str) -> bool:
    return bool(_CJK_PATTERN.search(text))


def _extract_message_text(payload_obj: object) -> str:
    if not isinstance(payload_obj, dict):
        return ""
    choices_obj = payload_obj.get("choices")
    if not isinstance(choices_obj, list) or not choices_obj:
        return ""
    first = choices_obj[0]
    if not isinstance(first, dict):
        return ""
    message_obj = first.get("message")
    if not isinstance(message_obj, dict):
        return ""
    content_obj = message_obj.get("content")
    if isinstance(content_obj, str):
        return content_obj
    if isinstance(content_obj, list):
        parts: list[str] = []
        for part in content_obj:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str):
                parts.append(text)
        return "".join(parts)
    return ""

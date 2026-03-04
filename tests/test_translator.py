from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from vibemouse.translator import ApiTextTranslator


class ApiTextTranslatorTests(unittest.TestCase):
    def test_skip_when_api_key_missing(self) -> None:
        subject = ApiTextTranslator(
            provider="openai_compatible",
            api_base="https://api.deepseek.com/v1",
            api_key="",
            model="deepseek-chat",
            timeout_s=12.0,
            retries=1,
            only_if_chinese=True,
        )

        result = subject.translate_cn_to_en("你好 world")
        self.assertEqual(result.text, "你好 world")
        self.assertEqual(result.status, "skip_no_api_key")

    def test_skip_non_chinese_when_enabled(self) -> None:
        subject = ApiTextTranslator(
            provider="openai_compatible",
            api_base="https://api.deepseek.com/v1",
            api_key="test",
            model="deepseek-chat",
            timeout_s=12.0,
            retries=1,
            only_if_chinese=True,
        )

        result = subject.translate_cn_to_en("hello world")
        self.assertEqual(result.text, "hello world")
        self.assertEqual(result.status, "skip_non_chinese")

    def test_translate_success(self) -> None:
        subject = ApiTextTranslator(
            provider="openai_compatible",
            api_base="https://api.deepseek.com/v1",
            api_key="test",
            model="deepseek-chat",
            timeout_s=12.0,
            retries=1,
            only_if_chinese=True,
        )

        payload = {
            "choices": [
                {
                    "message": {
                        "content": "Hello world",
                    }
                }
            ]
        }
        response = json.dumps(payload).encode("utf-8")
        class _FakeHttpResponse:
            def __enter__(self) -> "_FakeHttpResponse":
                return self

            def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
                return False

            def read(self) -> bytes:
                return response

        fake_http = _FakeHttpResponse()
        with patch("vibemouse.translator.request.urlopen", return_value=fake_http):
            result = subject.translate_cn_to_en("你好，世界")

        self.assertEqual(result.text, "Hello world")
        self.assertEqual(result.status, "translated")


if __name__ == "__main__":
    unittest.main()

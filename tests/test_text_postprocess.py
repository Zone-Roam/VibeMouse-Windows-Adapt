from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vibemouse.text_postprocess import UserTextProcessor


class UserTextProcessorTests(unittest.TestCase):
    def test_creates_template_dictionary_when_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-pp-") as tmp:
            root = Path(tmp)
            dictionary = root / "user_dictionary.json"
            history = root / "history.jsonl"
            _ = UserTextProcessor(
                dictionary_file=dictionary,
                history_file=history,
                history_enabled=False,
                strip_emoji=True,
            )
            self.assertTrue(dictionary.exists())
            payload = json.loads(dictionary.read_text(encoding="utf-8"))
            self.assertIn("replacements", payload)

    def test_applies_case_insensitive_replacements_and_strips_emoji(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-pp-") as tmp:
            root = Path(tmp)
            dictionary = root / "dict.json"
            history = root / "history.jsonl"
            dictionary.write_text(
                json.dumps(
                    {
                        "replacements": {
                            "telegarm": "Telegram",
                            "open claw": "OpenClaw",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            processor = UserTextProcessor(
                dictionary_file=dictionary,
                history_file=history,
                history_enabled=False,
                strip_emoji=True,
            )
            result = processor.process("telegarm 😄 open claw")
            self.assertEqual(result, "Telegram OpenClaw")

    def test_appends_history_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory(prefix="vibemouse-pp-") as tmp:
            root = Path(tmp)
            dictionary = root / "dict.json"
            history = root / "history.jsonl"
            dictionary.write_text(
                json.dumps({"replacements": {"g p t": "GPT"}}, ensure_ascii=False),
                encoding="utf-8",
            )
            processor = UserTextProcessor(
                dictionary_file=dictionary,
                history_file=history,
                history_enabled=True,
                strip_emoji=False,
            )
            result = processor.process("g p t")
            self.assertEqual(result, "GPT")
            lines = history.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["raw"], "g p t")
            self.assertEqual(payload["processed"], "GPT")

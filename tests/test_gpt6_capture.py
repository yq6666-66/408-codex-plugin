from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import gpt6_capture  # noqa: E402


class CaptureTests(unittest.TestCase):
    def write_jsonl(self, root: Path, events: list[dict]) -> Path:
        path = root / "run.jsonl"
        payload = "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events)
        path.write_text(payload, encoding="utf-8", newline="\n")
        return path

    def test_extracts_messages_tools_errors_and_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = self.write_jsonl(root, [
                {"type": "thread.started", "thread_id": "thread-1"},
                {"type": "turn.started"},
                {"type": "item.completed", "item": {"id": "a1", "type": "agent_message", "text": "先检查。"}},
                {"type": "item.completed", "item": {
                    "id": "t1", "type": "command_execution", "command": "2+2",
                    "aggregated_output": "4\n", "exit_code": 0, "status": "completed",
                }},
                {"type": "item.completed", "item": {"id": "w1", "type": "error", "message": "nonfatal warning"}},
                {"type": "item.completed", "item": {"id": "a2", "type": "agent_message", "text": "结果是 4。"}},
                {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}},
            ])
            events, digest = gpt6_capture.load_events(path)
            report = gpt6_capture.capture(events, digest, "case-1")
            expected_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertTrue(report["complete"])
        self.assertEqual(report["caseId"], "case-1")
        self.assertEqual(report["threadId"], "thread-1")
        self.assertIn("结果是 4", report["modelOutput"])
        self.assertEqual(report["toolCalls"][0]["output"], "4\n")
        self.assertTrue(report["toolCalls"][0]["success"])
        self.assertEqual(report["errors"][0]["message"], "nonfatal warning")
        self.assertEqual(report["sourceSha256"], expected_digest)

    def test_incomplete_turn_is_not_accepted(self) -> None:
        report = gpt6_capture.capture(
            [{"type": "turn.started"}, {"type": "item.completed", "item": {"type": "agent_message", "text": "partial"}}],
            "0" * 64,
        )
        self.assertFalse(report["complete"])

    def test_invalid_jsonl_reports_line_without_echoing_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.jsonl"
            path.write_bytes(b'{"type":"turn.started"}\n{secret')
            with self.assertRaisesRegex(gpt6_capture.CaptureError, "line 2") as caught:
                gpt6_capture.load_events(path)
        self.assertNotIn("secret", str(caught.exception))


if __name__ == "__main__":
    unittest.main()

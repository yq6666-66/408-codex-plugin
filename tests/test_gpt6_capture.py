from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
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

    def test_web_search_results_are_preserved_as_tool_evidence(self) -> None:
        results = [{"title": "Official page", "url": "https://example.org/paper", "snippet": "2024 paper"}]
        report = gpt6_capture.capture(
            [
                {"type": "turn.started"},
                {"type": "item.completed", "item": {
                    "id": "web-1", "type": "web_search", "query": "2024 paper",
                    "action": {"type": "search", "queries": ["2024 paper"]},
                    "results": results,
                }},
                {"type": "item.completed", "item": {
                    "id": "web-2", "type": "web_search", "query": "no results",
                    "action": {"type": "search", "queries": ["no results"]},
                    "results": [],
                }},
                {"type": "turn.completed"},
            ],
            "b" * 64,
        )
        first, second = report["toolCalls"]
        self.assertEqual(first["status"], "completed")
        self.assertIsNone(first["exitCode"])
        self.assertTrue(first["success"])
        self.assertEqual(json.loads(first["input"])["action"]["type"], "search")
        self.assertEqual(json.loads(first["output"]), results)
        self.assertTrue(second["success"])
        self.assertEqual(second["output"], "[]")

    def test_completed_command_without_output_cannot_prove_tool_result(self) -> None:
        report = gpt6_capture.capture(
            [
                {"type": "turn.started"},
                {"type": "item.completed", "item": {
                    "type": "command_execution", "command": "silent command",
                    "aggregated_output": "", "exit_code": 0, "status": "completed",
                }},
                {"type": "turn.completed"},
            ],
            "c" * 64,
        )
        call = report["toolCalls"][0]
        self.assertFalse(call["success"])
        self.assertEqual(call["output"], "actual no output")

    def test_invalid_jsonl_reports_line_without_echoing_content(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "bad.jsonl"
            path.write_bytes(b'{"type":"turn.started"}\n{secret')
            with self.assertRaisesRegex(gpt6_capture.CaptureError, "line 2") as caught:
                gpt6_capture.load_events(path)
        self.assertNotIn("secret", str(caught.exception))

    def test_record_case_preserves_followups_artifact_hash_and_failed_tool(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "material.png"
            artifact.write_bytes(b"fixture-image")
            prompt = "第一轮问题\n第二轮追问\n第三轮提交"
            report = gpt6_capture.capture(
                [
                    {"type": "turn.started"},
                    {"type": "item.completed", "item": {"type": "agent_message", "text": "实际回答"}},
                    {"type": "item.completed", "item": {
                        "type": "command_execution", "command": "unavailable",
                        "aggregated_output": "tool failed", "exit_code": 1, "status": "completed",
                    }},
                    {"type": "turn.completed"},
                ],
                "a" * 64,
                "case-multiturn",
                prompt,
                {"material.png": hashlib.sha256(artifact.read_bytes()).hexdigest()},
            )
        record_case = report["recordCase"]
        self.assertEqual(record_case["inputMaterial"], prompt)
        self.assertEqual(record_case["inputArtifacts"]["material.png"], hashlib.sha256(b"fixture-image").hexdigest())
        self.assertEqual(len(record_case["toolCalls"]), 1)
        self.assertEqual(record_case["toolCalls"][0]["output"], "tool failed")
        self.assertFalse(record_case["toolCalls"][0]["success"])
        self.assertEqual(record_case["sourceEvidence"]["jsonlSha256"], "a" * 64)
        self.assertFalse(report["toolCalls"][0]["success"])

    def test_cli_refuses_output_that_aliases_source_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.jsonl"
            source.write_text('{"type":"thread.started"}\n', encoding="utf-8")
            original = source.read_bytes()
            alias = Path(temporary) / "alias.jsonl"
            try:
                os.link(source, alias)
            except OSError as exc:
                self.skipTest(f"hard links unavailable: {exc}")
            for output in (source, alias):
                with self.subTest(output=output):
                    error = io.StringIO()
                    with redirect_stderr(error):
                        code = gpt6_capture.main(["--input", str(source), "--output", str(output)])
                    self.assertEqual(code, 1)
                    self.assertIn("must not overwrite or alias", error.getvalue())
                    self.assertEqual(source.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

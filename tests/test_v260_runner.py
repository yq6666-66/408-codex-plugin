from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "v260_runner", REPO / "eval" / "v2.6-acceptance" / "run_cases.py"
)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class RolloutEvidenceTests(unittest.TestCase):
    def extract(self, events: list[dict]) -> list[dict]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout.jsonl"
            path.write_text(
                "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8"
            )
            return runner.extract_rollout_tools(path)

    def test_rollout_capture_only_attributes_calls_after_the_turn_boundary(self) -> None:
        events = [
            {"type": "session_meta", "payload": {}},
            *self.pair("exec", "Script completed\nprevious turn result"),
            *self.pair("exec", "Script completed\ncurrent turn result"),
        ]
        events[3]["payload"]["call_id"] = "call-2"
        events[4]["payload"]["call_id"] = "call-2"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rollout.jsonl"
            path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
            current = runner.extract_rollout_tools(path, start_line=4)
        self.assertEqual(len(current), 1)
        self.assertIn("current turn result", current[0]["output"])

    def pair(self, name: str, output: str) -> list[dict]:
        return [
            {"type": "response_item", "payload": {
                "type": "custom_tool_call", "call_id": "call-1", "name": name,
                "input": "read the installed Skill",
            }},
            {"type": "response_item", "payload": {
                "type": "custom_tool_call_output", "call_id": "call-1", "output": output,
            }},
        ]

    def test_wrapper_failures_cannot_prove_success(self) -> None:
        for name in ("exec", "functions.exec"):
            with self.subTest(name=name):
                failed = self.extract(self.pair(name, "Script error: blocked by policy"))
                self.assertFalse(failed[0]["success"])
                incomplete = self.extract(self.pair(name, "some output without completion"))
                self.assertFalse(incomplete[0]["success"])
                completed = self.extract(self.pair(name, "Script completed\nread result"))
                self.assertTrue(completed[0]["success"])

    def test_unmatched_outputs_do_not_create_evidence(self) -> None:
        events = self.pair("exec", "Script completed")
        events[1]["payload"]["call_id"] = "unrelated"
        self.assertEqual(self.extract(events), [])

    def test_skill_proof_requires_complete_text_exact_path_and_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "SKILL.md"
            body = "---\nname: sample-skill\n---\nRequired workflow.\n"
            path.write_text(body, encoding="utf-8")
            valid = {"success": True, "input": str(path), "output": body, "itemId": "read-1"}
            self.assertEqual(runner.skill_read_proof({"toolCalls": [valid]}, path, "sample-skill"), ["read-1"])
            for changed in (
                {**valid, "success": False},
                {**valid, "input": str(path.parent / "other.md")},
                {**valid, "output": "name: sample-skill\nRequired workflow."},
            ):
                self.assertEqual(runner.skill_read_proof({"toolCalls": [changed]}, path, "sample-skill"), [])


class InstalledPayloadTests(unittest.TestCase):
    def test_installed_payload_rejects_symlink_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidate = root / "skill.md"
            candidate.write_text("installed content", encoding="utf-8")
            expected = {"skill.md": b"installed content"}
            self.assertEqual(runner.read_installed_payload(root, expected), expected)

            real_is_symlink = Path.is_symlink

            def identify_symlink(path: Path) -> bool:
                return path == candidate or real_is_symlink(path)

            with patch.object(Path, "is_symlink", identify_symlink):
                with self.assertRaisesRegex(ValueError, "symlink"):
                    runner.read_installed_payload(root, expected)


class FailedTurnSummaryTests(unittest.TestCase):
    def test_turn_exit_and_stderr_path_survive_empty_raw_capture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "turn-1.input.txt"
            raw_path = root / "turn-1.jsonl"
            stderr_path = root / "turn-1.stderr.txt"
            input_path.write_text("fixed prompt", encoding="utf-8")
            raw_path.write_bytes(b"")
            stderr_path.write_text("CLI exited before writing JSONL", encoding="utf-8")
            summary = {"turns": []}

            turn = runner.begin_turn_record(summary, 1, input_path, raw_path, stderr_path)
            turn["exitCode"] = 1

            self.assertEqual(len(summary["turns"]), 1)
            self.assertEqual(turn["exitCode"], 1)
            self.assertEqual(turn["stderrPath"], "turn-1.stderr.txt")
            self.assertIsNone(turn["rawSha256"])
            self.assertFalse(turn["complete"])




if __name__ == "__main__":
    unittest.main()

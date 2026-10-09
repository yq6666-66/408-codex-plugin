from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()

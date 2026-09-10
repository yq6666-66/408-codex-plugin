from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "gpt6_acceptance.py"


def run_cli(*arguments: str) -> tuple[int, str, str]:
    import os

    env = os.environ.copy()
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    result = subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )
    return result.returncode, result.stdout, result.stderr


def make_record() -> dict:
    return {
        "meta": {
            "pluginName": "kaoyan-408",
            "pluginVariant": "new",
            "pluginVersion": "2.5.0",
            "model": "gpt-6-test-host",
            "reasoningEffort": "high",
            "host": "codex-cli",
            "runAt": "2026-09-12T03:00:00Z",
        },
        "cases": [],
    }


class HarnessValidationTests(unittest.TestCase):
    def read_case(self, case_id: str) -> tuple[dict, dict]:
        cases = json.loads((REPO / "eval" / "gpt6-acceptance" / "cases.json").read_text(encoding="utf-8"))
        target = next(case for case in cases["cases"] if case["id"] == case_id)
        return cases, target

    def write_and_validate(self, record: dict) -> tuple[int, str, str]:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "record.json"
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            return run_cli("--record", str(path))

    def test_case_catalog_covers_required_scenarios(self) -> None:
        cases = json.loads((REPO / "eval" / "gpt6-acceptance" / "cases.json").read_text(encoding="utf-8"))
        categories = {case["category"] for case in cases["cases"]}
        for required in (
            "detailed-answer",
            "concise-answer",
            "batching",
            "defective-input",
            "answer-leak",
            "continuous-task",
            "past-paper",
            "official-info",
            "long-term-memory",
            "degradation",
            "computation",
        ):
            self.assertIn(required, categories)
        self.assertGreaterEqual(len(cases["cases"]), 17)

    def test_record_with_placeholder_output_is_rejected(self) -> None:
        _, case = self.read_case("gpt6-01-detailed-408")
        record = make_record()
        record["cases"] = [
            {
                "id": case["id"],
                "inputMaterial": "见 cases.json 原题，附图片 materials/a.png",
                "modelOutput": "TODO 待填写",
                "verdicts": [],
            }
        ]
        code, _, stderr = self.write_and_validate(record)
        self.assertEqual(code, 1)
        self.assertIn("placeholder", stderr)

    def test_record_with_unjudged_checkpoints_is_rejected(self) -> None:
        cases_document, case = self.read_case("gpt6-01-detailed-408")
        record = make_record()
        record["cases"] = [
            {
                "id": case["id"],
                "inputMaterial": case["input"],
                "modelOutput": "完整回答" * 40,
                "verdicts": [
                    {"checkpoint": case["checkpoints"][0], "verdict": "pass", "evidence": "回答第 2 段给出了地址划分"}
                ],
            }
        ]
        code, _, stderr = self.write_and_validate(record)
        self.assertEqual(code, 1)
        self.assertIn("checkpoints not judged", stderr)

    def test_complete_record_passes(self) -> None:
        cases_document, case = self.read_case("gpt6-01-detailed-408")
        record = make_record()
        record["cases"] = [
            {
                "id": case["id"],
                "inputMaterial": case["input"],
                "modelOutput": "完整回答" * 40,
                "toolCalls": [],
                "verdicts": [
                    {"checkpoint": checkpoint, "verdict": "pass", "evidence": f"依据：{checkpoint[:10]}……"}
                    for checkpoint in case["checkpoints"]
                ],
            }
        ]
        code, stdout, stderr = self.write_and_validate(record)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["pass"], 1)

    def test_template_meta_placeholders_are_rejected(self) -> None:
        record = make_record()
        record["meta"]["model"] = "GPT-6（填写宿主实际返回的模型标识）"
        code, _, stderr = self.write_and_validate(record)
        self.assertEqual(code, 1)
        self.assertIn("template placeholders", stderr)


if __name__ == "__main__":
    unittest.main()

"""Synthetic schema fixtures only: these are NOT real GPT-6 acceptance runs."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "gpt6_acceptance.py"
SPEC = importlib.util.spec_from_file_location("gpt6_acceptance", SCRIPT)
assert SPEC and SPEC.loader
harness = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(harness)
CATALOG = harness.load_cases(REPO)


def make_record(variant: str = "new") -> dict:
    return {
        "meta": {
            "pluginName": "kaoyan-408", "pluginVariant": variant,
            "pluginVersion": "2.5.1" if variant == "new" else "2.4.0",
            "model": "synthetic-test-model", "reasoningEffort": "high",
            "host": "synthetic-test-host", "runAt": "2026-09-11T00:00:00Z",
            "notes": "SYNTHETIC UNIT TEST FIXTURE; NOT MODEL ACCEPTANCE EVIDENCE",
        },
        "cases": [
            {
                "id": case["id"], "inputMaterial": case["input"],
                "modelOutput": "Synthetic unit test content. No actual model was invoked.",
                "toolCalls": [],
                "verdicts": [
                    {"checkpoint": checkpoint, "verdict": "pass", "evidence": "Synthetic fixture evidence only."}
                    for checkpoint in case["checkpoints"]
                ],
            }
            for case in CATALOG.values()
        ],
    }


def run_records(*records: dict) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as temporary:
        paths = []
        for index, record in enumerate(records):
            path = Path(temporary) / f"synthetic-{index}.json"
            path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
            paths.append(str(path))
        env = os.environ.copy()
        env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--record" if len(records) == 1 else "--compare", *paths],
            capture_output=True, text=True, encoding="utf-8", env=env, check=False,
        )
        return result.returncode, result.stdout, result.stderr


class HarnessValidationTests(unittest.TestCase):
    def assert_rejected(self, record: dict, text: str = "") -> None:
        with self.assertRaises(harness.RecordError) as caught:
            harness.validate_record(record, CATALOG)
        self.assertIn(text, str(caught.exception))

    def test_case_catalog_covers_required_scenarios(self) -> None:
        categories = {case["category"] for case in CATALOG.values()}
        for category in ("detailed-answer", "concise-answer", "batching", "defective-input",
                         "answer-leak", "continuous-task", "past-paper", "official-info",
                         "long-term-memory", "degradation", "computation"):
            self.assertIn(category, categories)
        self.assertEqual(len(CATALOG), 17)

    def test_complete_synthetic_fixture_passes_without_mutation(self) -> None:
        record = make_record()
        before = copy.deepcopy(record)
        summary = harness.validate_record(record, CATALOG)
        self.assertEqual(summary["pass"], 17)
        self.assertEqual(record, before)
        code, stdout, stderr = run_records(record)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["total"], 17)

    def test_missing_and_duplicate_cases_are_rejected_by_cli(self) -> None:
        for mode in ("missing", "duplicate"):
            with self.subTest(mode=mode):
                record = make_record()
                if mode == "missing":
                    record["cases"].pop()
                else:
                    record["cases"].append(copy.deepcopy(record["cases"][0]))
                code, _, stderr = run_records(record)
                self.assertEqual(code, 1)
                self.assertIn(mode, stderr)

    def test_invalid_structures_raise_record_errors(self) -> None:
        for root in (None, [], "string", 42):
            with self.subTest(root=root):
                self.assert_rejected(root, "must be an object")
        for field, value in (("cases", None), ("cases", []), ("cases", [None]), ("meta", [])):
            with self.subTest(field=field, value=value):
                record = make_record()
                record[field] = value
                self.assert_rejected(record)

    def test_metadata_is_required_typed_nonempty_and_not_placeholder(self) -> None:
        for key in harness.REQUIRED_META:
            for value in (None, "", "  ", 42, [], "TODO", "待填写"):
                with self.subTest(key=key, value=value):
                    record = make_record()
                    record["meta"][key] = value
                    self.assert_rejected(record)
            record = make_record()
            del record["meta"][key]
            self.assert_rejected(record, "missing")
        for field, value in (("pluginVariant", "other"), ("runAt", "yesterday"),
                             ("runAt", "2026-09-11T00:00:00")):
            record = make_record()
            record["meta"][field] = value
            self.assert_rejected(record)

    def test_actual_input_and_output_fields_reject_placeholders(self) -> None:
        for key in ("modelOutput", "inputMaterial"):
            for value in (None, [], "", "TODO " * 8):
                with self.subTest(key=key, value=value):
                    record = make_record()
                    record["cases"][0][key] = value
                    self.assert_rejected(record)

    def test_short_answers_and_normal_body_wording_are_allowed(self) -> None:
        record = make_record()
        record["cases"][0]["modelOutput"] = "1/2"
        record["cases"][0]["inputMaterial"] = "求值"
        record["cases"][1]["modelOutput"] = "请在答题卡上填写答案。"
        harness.validate_record(record, CATALOG)

    def test_tool_call_schema(self) -> None:
        for value in (None, {}, [None], [{}], [{"tool": "shell", "input": "echo 1"}],
                      [{"tool": "shell", "input": {}, "output": "1"}],
                      [{"tool": "shell", "input": "echo 1", "output": ""}]):
            with self.subTest(value=value):
                record = make_record()
                record["cases"][0]["toolCalls"] = value
                self.assert_rejected(record, "toolCalls")
        record = make_record()
        del record["cases"][0]["toolCalls"]
        self.assert_rejected(record, "toolCalls")
        record["cases"][0]["toolCalls"] = [{"tool": "synthetic", "input": "fixture input", "output": "fixture output"}]
        harness.validate_record(record, CATALOG)

    def test_checkpoint_coverage_uniqueness_and_known_ids(self) -> None:
        for mode in ("unknown-id", "duplicate-checkpoint", "unknown-checkpoint", "unjudged", "non-object"):
            with self.subTest(mode=mode):
                record = make_record()
                entry = record["cases"][0]
                if mode == "unknown-id":
                    entry["id"] = "unknown"
                elif mode == "duplicate-checkpoint":
                    entry["verdicts"].append(copy.deepcopy(entry["verdicts"][0]))
                elif mode == "unknown-checkpoint":
                    entry["verdicts"][0]["checkpoint"] = "unknown"
                elif mode == "unjudged":
                    entry["verdicts"].pop()
                else:
                    entry["verdicts"][0] = None
                self.assert_rejected(record)

    def test_illegal_verdict_and_evidence_rejected(self) -> None:
        for field, values in (("verdict", (None, [], {}, "PASS", "unknown")),
                              ("evidence", (None, [], {}, 0, False, "", "  ", "TODO"))):
            for value in values:
                with self.subTest(field=field, value=value):
                    record = make_record()
                    record["cases"][0]["verdicts"][0][field] = value
                    self.assert_rejected(record)
        record = make_record()
        record["cases"][0]["verdicts"][0]["evidence"] = ""
        self.assertEqual(run_records(record)[0], 1)

    def test_partial_and_fail_are_valid_but_do_not_pass_acceptance(self) -> None:
        for result in ("partial", "fail"):
            record = make_record()
            record["cases"][0]["verdicts"][0]["verdict"] = result
            self.assertEqual(harness.validate_record(record, CATALOG)["fail"], 1)
            self.assertEqual(run_records(record)[0], 1)

    def test_inconsistent_overall_is_rejected(self) -> None:
        record = make_record()
        record["cases"][0]["overall"] = "fail"
        self.assert_rejected(record, "overall")

    def test_comparison_rejects_invalid_records_and_mismatched_conditions(self) -> None:
        for field in ("pluginName", "host", "model", "reasoningEffort"):
            old, new = make_record("old"), make_record()
            new["meta"][field] = "different"
            code, _, stderr = run_records(old, new)
            self.assertEqual(code, 1)
            self.assertIn(field, stderr)
        old, new = make_record("old"), make_record()
        old["cases"].pop()
        self.assertEqual(run_records(old, new)[0], 1)
        old, new = make_record("old"), make_record()
        old["cases"][0]["verdicts"][0]["verdict"] = "invalid"
        new["cases"][0]["verdicts"][0]["verdict"] = "invalid"
        self.assertEqual(run_records(old, new)[0], 1)
        self.assertEqual(run_records(make_record(), make_record())[0], 1)

    def test_comparison_matches_inputs_by_id_not_case_order(self) -> None:
        old, new = make_record("old"), make_record()
        new["cases"].reverse()
        code, stdout, stderr = run_records(old, new)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["regressionGate"], "pass")

    def test_comparison_rejects_different_actual_inputs(self) -> None:
        old, new = make_record("old"), make_record()
        new["cases"][0]["inputMaterial"] = "Compute 1+1; answer only."
        code, _, stderr = run_records(old, new)
        self.assertEqual(code, 1)
        self.assertIn(old["cases"][0]["id"] + ".inputMaterial", stderr)

    def test_comparison_optional_input_artifacts_must_match(self) -> None:
        for mode in ("equal", "different", "old-only", "new-only", "null-only"):
            with self.subTest(mode=mode):
                old, new = make_record("old"), make_record()
                artifact = {"image.png": "synthetic-sha256"}
                if mode != "new-only":
                    old["cases"][0]["inputArtifacts"] = artifact
                if mode not in ("old-only", "null-only"):
                    new["cases"][0]["inputArtifacts"] = (
                        {"image.png": "different-sha256"} if mode == "different" else artifact
                    )
                if mode == "null-only":
                    old["cases"][0]["inputArtifacts"] = None
                code, _, stderr = run_records(old, new)
                self.assertEqual(code, 0 if mode == "equal" else 1, stderr)
                if mode != "equal":
                    self.assertIn("inputArtifacts", stderr)

    def test_comparison_detects_offsetting_case_regressions(self) -> None:
        old, new = make_record("old"), make_record()
        old["cases"][0]["verdicts"][0]["verdict"] = "fail"
        new["cases"][1]["verdicts"][0]["verdict"] = "fail"
        code, stdout, stderr = run_records(old, new)
        self.assertEqual(code, 1, stderr)
        report = json.loads(stdout)
        self.assertEqual(report["old"], report["new"])
        self.assertEqual(report["regressions"][0]["id"], new["cases"][1]["id"])

    def test_comparison_detects_regression_within_already_failed_case(self) -> None:
        old, new = make_record("old"), make_record()
        old["cases"][0]["verdicts"][0]["verdict"] = "partial"
        new["cases"][0]["verdicts"][0]["verdict"] = "fail"
        self.assertEqual(run_records(old, new)[0], 1)

    def test_comparison_no_regression_does_not_imply_acceptance(self) -> None:
        old, new = make_record("old"), make_record()
        old["cases"][0]["verdicts"][0]["verdict"] = "fail"
        new["cases"][0]["verdicts"][0]["verdict"] = "partial"
        code, stdout, stderr = run_records(old, new)
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["new"]["fail"], 1)
        self.assertEqual(run_records(new)[0], 1)


if __name__ == "__main__":
    unittest.main()

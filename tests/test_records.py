from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "records.py"
sys.path.insert(0, str(REPO / "scripts"))

import records  # noqa: E402


REVIEW_QUEUE_10 = {
    "schemaVersion": "1.0",
    "generatedAt": "2026-09-01",
    "items": [
        {"subject": "408", "topic": "LRU 置换", "errorCause": None, "retestDate": "D+3", "status": "pending", "masteryEvidence": []},
        {"subject": "数学二", "topic": "泰勒展开", "retestDate": "2026-09-10", "status": "pending", "masteryEvidence": "unknown"},
    ],
}


def run_cli(*arguments: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    import os

    env = os.environ.copy()
    env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    return subprocess.run(
        [sys.executable, str(SCRIPT), *arguments],
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )


class NormalizeTests(unittest.TestCase):
    def test_10_review_queue_normalizes_to_12(self) -> None:
        normalized, warnings = records.normalize_to_12(REVIEW_QUEUE_10)
        self.assertEqual(normalized["schemaVersion"], "1.2")
        self.assertEqual(normalized["recordType"], "ReviewQueue")
        first = normalized["items"][0]
        self.assertIsNone(first["nextRetestDate"])
        self.assertEqual(first["retestOffsetDays"], 3)
        self.assertEqual(normalized["items"][1]["nextRetestDate"], "2026-09-10")
        self.assertEqual(normalized["items"][1]["masteryEvidence"], [])
        self.assertLess(0, len(warnings))

    def test_assigned_record_id_is_stable_across_renormalization(self) -> None:
        first, _ = records.normalize_to_12(REVIEW_QUEUE_10)
        second, _ = records.normalize_to_12(REVIEW_QUEUE_10)
        self.assertEqual(first["recordId"], second["recordId"])
        self.assertRegex(first["recordId"], r"^kr-[0-9a-f]{16}$")
        # Once assigned, the ID persists even when content is later updated.
        updated = {**first, "generatedAt": "2026-09-11"}
        self.assertEqual(updated["recordId"], first["recordId"])

    def test_normalize_does_not_fabricate_evidence_or_dates(self) -> None:
        normalized, _ = records.normalize_to_12(REVIEW_QUEUE_10)
        for item in normalized["items"]:
            self.assertEqual(item["retestEvidence"], [])
        self.assertIsNone(normalized["updatedAt"])

    def test_unknown_safe_fields_are_preserved(self) -> None:
        record = {
            "schemaVersion": "1.0",
            "targetExam": "408考研",
            "unrecognizedExtension": {"preserve": True},
        }
        normalized, warnings = records.normalize_to_12(record)
        self.assertEqual(
            normalized["legacyExtensions"]["unrecognizedExtension"],
            {"preserve": True},
        )
        self.assertTrue(any("legacyExtensions" in warning for warning in warnings))

    def test_sensitive_legacy_extensions_are_redacted_with_json_pointers(self) -> None:
        record = {
            "schemaVersion": "1.0",
            "targetExam": "408考研",
            "apiToken": "fake-token-value",
            "devicePath": r"C:\Users\student\vault",
            "safeExtension": {"theme": "dark", "email": "student@example.invalid"},
        }
        normalized, warnings = records.normalize_to_12(record)
        extensions = normalized["legacyExtensions"]
        self.assertIsNone(extensions["apiToken"])
        self.assertIsNone(extensions["devicePath"])
        self.assertEqual(extensions["safeExtension"]["theme"], "dark")
        self.assertIsNone(extensions["safeExtension"]["email"])
        self.assertEqual(normalized["redactedFields"], [
            "/legacyExtensions/apiToken",
            "/legacyExtensions/devicePath",
            "/legacyExtensions/safeExtension/email",
        ])
        self.assertTrue(any("redacted" in warning for warning in warnings))

    def test_legacy_root_unit_is_preserved_during_normalization(self) -> None:
        normalized, warnings = records.normalize_to_12({
            "schemaVersion": "1.0", "plannedUnits": 10, "completedUnits": 7, "unit": "hours",
        })
        self.assertEqual(normalized["recordType"], "ProgressSnapshot")
        self.assertEqual(normalized["metrics"][0]["unit"], "hours")
        self.assertFalse(any("carry no unit" in warning for warning in warnings))

    def test_11_record_keeps_existing_identity_and_upgrades_version(self) -> None:
        record = {
            "schemaVersion": "1.1",
            "recordType": "ReviewQueue",
            "generatedAt": "2026-08-01",
            "items": [],
        }
        normalized, _ = records.normalize_to_12(record)
        self.assertEqual(normalized["schemaVersion"], "1.2")
        self.assertEqual(normalized["generatedAt"], "2026-08-01")

    def test_normalize_is_idempotent(self) -> None:
        once, _ = records.normalize_to_12(REVIEW_QUEUE_10)
        twice, _ = records.normalize_to_12(once)
        self.assertEqual(json.dumps(once, sort_keys=True), json.dumps(twice, sort_keys=True))


class MergeTests(unittest.TestCase):
    def test_repeated_import_deduplicates_by_record_id(self) -> None:
        record = {
            "schemaVersion": "1.2",
            "recordType": "StudyProfile",
            "recordId": "kr-0f1e2d3c4b5a6978",
            "updatedAt": None,
            "targetExam": "408考研",
            "targetDate": None,
            "weeklyHours": None,
            "currentPhase": None,
            "constraints": [],
        }
        merged = records.merge_documents({"records": [record]}, {"records": [record]})
        self.assertEqual(len(merged["records"]), 1)
        self.assertEqual(merged["mergeConflicts"], [])

    def test_merge_prefers_newer_updated_at_on_scalar_conflict(self) -> None:
        a = {
            "schemaVersion": "1.2",
            "recordType": "StudyProfile",
            "recordId": "kr-aaaaaaaaaaaaaaaa",
            "updatedAt": "2026-09-01",
            "targetExam": "408考研",
            "targetDate": None,
            "weeklyHours": 20,
            "currentPhase": None,
            "constraints": ["周三晚不可学习"],
        }
        b = {
            **a,
            "updatedAt": "2026-09-10",
            "weeklyHours": 35,
            "constraints": ["周五下午不可学习"],
        }
        merged = records.merge_documents(a, b)
        self.assertEqual(len(merged["records"]), 1)
        record = merged["records"][0]
        # lists keep both sides; scalars resolve to the newer updatedAt side
        self.assertEqual(
            sorted(record["constraints"]),
            ["周三晚不可学习", "周五下午不可学习"],
        )
        self.assertEqual(record["weeklyHours"], 35)
        self.assertEqual(record["updatedAt"], "2026-09-10")
        self.assertEqual(
            merged["mergeConflicts"],
            [
                {
                    "path": "/weeklyHours",
                    "a": 20,
                    "b": 35,
                    "resolution": "kept-newer",
                }
            ],
        )

    def test_merge_prefers_newer_updated_at_inside_list_items(self) -> None:
        item_a = {
            "subject": "408", "topic": "LRU", "nextRetestDate": "2026-09-05", "status": "pending"
        }
        item_b = {
            "subject": "408", "topic": "LRU", "nextRetestDate": "2026-09-15", "status": "due"
        }
        base = {
            "schemaVersion": "1.2", "recordType": "ReviewQueue",
            "recordId": "kr-bbbbbbbbbbbbbbbb", "generatedAt": "2026-09-01",
        }
        merged = records.merge_documents(
            {**base, "updatedAt": "2026-09-01", "items": [item_a]},
            {**base, "updatedAt": "2026-09-10", "items": [item_b]},
        )
        item = merged["records"][0]["items"][0]
        self.assertEqual(item["nextRetestDate"], "2026-09-15")
        self.assertEqual(item["status"], "due")
        self.assertEqual(
            {conflict["resolution"] for conflict in merged["mergeConflicts"]},
            {"kept-newer"},
        )

    def test_merge_marks_newer_first_side_as_kept_newer_inside_list_items(self) -> None:
        base = {
            "schemaVersion": "1.2", "recordType": "ReviewQueue",
            "recordId": "kr-bbbbbbbbbbbbbbbb", "generatedAt": "2026-09-01",
        }
        older_item = {"subject": "408", "topic": "LRU", "status": "pending"}
        newer_item = {"subject": "408", "topic": "LRU", "status": "mastered"}
        merged = records.merge_documents(
            {**base, "updatedAt": "2026-09-10", "items": [newer_item]},
            {**base, "updatedAt": "2026-09-01", "items": [older_item]},
        )
        self.assertEqual(merged["records"][0]["items"][0]["status"], "mastered")
        self.assertEqual(
            merged["mergeConflicts"],
            [{
                "path": "/items[LRU]/status",
                "a": "mastered",
                "b": "pending",
                "resolution": "kept-newer",
            }],
        )

    def test_progress_metrics_with_same_subject_keep_distinct_names(self) -> None:
        base = {
            "schemaVersion": "1.2", "recordType": "ProgressSnapshot",
            "recordId": "kr-cccccccccccccccc", "period": {"start": None, "end": None},
            "accuracy": [], "blockers": [],
        }
        hours = {"subject": "数学二", "name": "hours", "unit": "hours", "planned": 20, "completed": 10}
        chapters = {"subject": "数学二", "name": "chapters", "unit": "chapter", "planned": 8, "completed": 3}
        merged = records.merge_documents(
            {**base, "updatedAt": "2026-09-01", "metrics": [hours]},
            {**base, "updatedAt": "2026-09-10", "metrics": [chapters]},
        )
        self.assertEqual(
            {item["name"] for item in merged["records"][0]["metrics"]},
            {"hours", "chapters"},
        )

    def test_invalid_nested_record_shapes_return_json_errors_instead_of_tracebacks(self) -> None:
        malformed = [
            {
                "schemaVersion": "1.2", "recordType": "ProgressSnapshot",
                "period": {"start": None, "end": None}, "metrics": [],
                "accuracy": [{"subject": "408", "correct": {}, "total": 1, "rate": 0.5}],
                "blockers": [],
            },
            {
                "schemaVersion": "1.2", "recordType": "ReviewQueue",
                "recordId": "kr-bbbbbbbbbbbbbbbb", "generatedAt": "2026-09-01", "items": None,
            },
        ]
        for record in malformed:
            with self.subTest(record_type=record["recordType"]):
                result = run_cli("validate", stdin=json.dumps(record, ensure_ascii=False))
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("Traceback", result.stdout + result.stderr)
                report = json.loads(result.stdout)
                self.assertIsInstance(report, dict)
                self.assertFalse(report["valid"])

    def test_null_arrays_and_non_numeric_accuracy_are_reported_as_validation_errors(self) -> None:
        record = {
            "schemaVersion": "1.2", "recordType": "ProgressSnapshot",
            "period": {"start": None, "end": None}, "metrics": None,
            "accuracy": [{"subject": "408", "correct": "5", "total": "10", "rate": "0.5"}],
            "blockers": [],
        }
        result = run_cli("validate", stdin=json.dumps(record, ensure_ascii=False))
        self.assertEqual(result.returncode, 1)
        errors = json.loads(result.stdout)["errors"]
        self.assertIn("metrics must be an array", errors)
        self.assertIn("accuracy[0].correct must be a non-negative integer or null", errors)
        self.assertIn("accuracy[0].total must be a non-negative integer or null", errors)
        self.assertIn("accuracy[0].rate must be a number from 0 to 1 or null", errors)

    def test_merge_equal_updated_at_keeps_first_side_and_records_conflict(self) -> None:
        a = {
            "schemaVersion": "1.2",
            "recordType": "StudyProfile",
            "recordId": "kr-aaaaaaaaaaaaaaaa",
            "updatedAt": "2026-09-10",
            "targetExam": "408考研",
            "targetDate": None,
            "weeklyHours": 20,
            "currentPhase": None,
            "constraints": [],
        }
        b = {**a, "weeklyHours": 35}
        merged = records.merge_documents(a, b)
        self.assertEqual(len(merged["records"]), 1)
        self.assertEqual(merged["records"][0]["weeklyHours"], 20)
        self.assertEqual(len(merged["mergeConflicts"]), 1)
        self.assertEqual(merged["mergeConflicts"][0]["path"], "/weeklyHours")
        self.assertEqual(merged["mergeConflicts"][0]["resolution"], "kept-first")

    def test_merge_combines_review_queue_items_by_topic(self) -> None:
        base = {
            "schemaVersion": "1.2",
            "recordType": "ReviewQueue",
            "recordId": "kr-bbbbbbbbbbbbbbbb",
            "generatedAt": "2026-09-01",
        }
        item_a = {
            "subject": "408", "topic": "LRU", "errorCause": None, "errorCauseStatus": None,
            "nextRetestDate": "2026-09-05", "retestOffsetDays": None, "status": "pending",
            "masteryEvidence": [], "retestEvidence": [],
        }
        item_b = {
            "subject": "408", "topic": "LRU", "errorCause": None, "errorCauseStatus": None,
            "nextRetestDate": None, "retestOffsetDays": 3, "retestAnchorDate": "2026-09-08",
            "status": "pending", "masteryEvidence": [], "retestEvidence": [],
        }
        merged = records.merge_documents(
            {**base, "items": [item_a]},
            {**base, "items": [item_b]},
        )
        self.assertEqual(len(merged["records"]), 1)
        self.assertEqual(len(merged["records"][0]["items"]), 1)

    def test_distinct_records_are_both_kept(self) -> None:
        a = {"schemaVersion": "1.2", "recordType": "SessionCheckpoint", "updatedAt": None,
             "currentTask": "A", "position": None, "dueItems": [], "pendingRetests": []}
        b = {"schemaVersion": "1.2", "recordType": "SessionCheckpoint", "updatedAt": None,
             "currentTask": "B", "position": None, "dueItems": [], "pendingRetests": []}
        merged = records.merge_documents({"records": [a]}, {"records": [b]})
        self.assertEqual(len(merged["records"]), 2)


class DueTests(unittest.TestCase):
    def build_queue(self) -> dict:
        return {
            "schemaVersion": "1.2",
            "recordType": "ReviewQueue",
            "generatedAt": "2026-09-01",
            "items": [
                {"subject": "408", "topic": "已到期", "errorCause": None, "errorCauseStatus": None,
                 "nextRetestDate": "2026-09-10", "retestOffsetDays": None, "status": "due",
                 "masteryEvidence": [], "retestEvidence": []},
                {"subject": "408", "topic": "未到期", "errorCause": None, "errorCauseStatus": None,
                 "nextRetestDate": "2026-09-20", "retestOffsetDays": None, "status": "pending",
                 "masteryEvidence": [], "retestEvidence": []},
                {"subject": "数学二", "topic": "锚定偏移", "errorCause": None, "errorCauseStatus": None,
                 "nextRetestDate": None, "retestOffsetDays": 3, "retestAnchorDate": "2026-09-08",
                 "status": "pending", "masteryEvidence": [], "retestEvidence": []},
                {"subject": "英语二", "topic": "无锚定", "errorCause": None, "errorCauseStatus": None,
                 "nextRetestDate": None, "retestOffsetDays": 5, "retestAnchorDate": None,
                 "status": "pending", "masteryEvidence": [], "retestEvidence": []},
            ],
        }

    def test_due_uses_explicit_base_date_only(self) -> None:
        plan = records.resolve_due(self.build_queue()["items"], __import__("datetime").date(2026, 9, 11))
        self.assertEqual([entry["topic"] for entry in plan["due"]], ["已到期", "锚定偏移"])
        self.assertEqual(plan["due"][1]["resolvedDate"], "2026-09-11")
        self.assertEqual([entry["topic"] for entry in plan["notDue"]], ["未到期"])
        self.assertEqual(len(plan["needsBaseDate"]), 1)
        self.assertEqual(plan["needsBaseDate"][0]["topic"], "无锚定")

    def test_boundary_date_is_inclusive(self) -> None:
        plan = records.resolve_due(self.build_queue()["items"], __import__("datetime").date(2026, 9, 10))
        self.assertEqual([entry["topic"] for entry in plan["due"]], ["已到期"])


class CheckpointTests(unittest.TestCase):
    def test_optional_question_arrays_may_be_omitted(self) -> None:
        checkpoint = records.build_checkpoint({}, None)
        checkpoint.pop("completedQuestions")
        checkpoint.pop("remainingQuestions")
        errors, _ = records.validate_current(checkpoint)
        self.assertEqual(errors, [])

    def test_present_null_question_arrays_are_rejected(self) -> None:
        base = records.build_checkpoint({}, None)
        for field in ("completedQuestions", "remainingQuestions"):
            with self.subTest(field=field):
                invalid = {**base, field: None}
                errors, _ = records.validate_current(invalid)
                self.assertTrue(any(field in error and "array" in error for error in errors))

    def test_resume_text_fields_must_be_strings_or_null(self) -> None:
        base = records.build_checkpoint({}, None)
        for field, value in (("currentTask", {}), ("position", 7)):
            with self.subTest(field=field):
                invalid = {**base, field: value}
                errors, _ = records.validate_current(invalid)
                self.assertTrue(any(field in error and "string" in error for error in errors))

    def test_create_and_read_roundtrip(self) -> None:
        checkpoint = records.build_checkpoint(
            {
                "currentTask": "英语二阅读精读",
                "position": "2016 Text 2 第 3 题",
                "dueItems": ["kr-1234567890abcdef#1"],
                "pendingRetests": [],
                "teachingMode": "hint",
                "answerState": "partial",
                "hintLevel": 2,
                "currentQuestion": "4",
                "completedQuestions": ["1", "2", "3"],
                "remainingQuestions": ["4", "5"],
                "materialVersion": "sha256:fixture-v2",
            },
            "2026-09-11",
        )
        self.assertEqual(checkpoint["schemaVersion"], "1.2")
        self.assertEqual(checkpoint["recordType"], "SessionCheckpoint")
        self.assertEqual(checkpoint["updatedAt"], "2026-09-11")
        self.assertRegex(checkpoint["checkpointId"], r"^kc-[0-9a-f]{16}$")
        errors, warnings = records.validate_current(checkpoint)
        self.assertEqual(errors, [])

        plan = records.read_checkpoint(checkpoint, None, None)
        self.assertEqual(plan["resume"]["position"], "2016 Text 2 第 3 题")
        self.assertEqual(plan["resume"]["teachingMode"], "hint")
        self.assertEqual(plan["resume"]["answerState"], "partial")
        self.assertEqual(plan["resume"]["hintLevel"], 2)
        self.assertEqual(plan["resume"]["completedQuestions"], ["1", "2", "3"])
        self.assertEqual(plan["resume"]["remainingQuestions"], ["4", "5"])
        self.assertEqual(plan["resume"]["materialVersion"], "sha256:fixture-v2")

    def test_checkpoint_rejects_invalid_teaching_state(self) -> None:
        checkpoint = records.build_checkpoint(
            {
                "currentTask": "任务",
                "teachingMode": "unknown-mode",
                "answerState": "leaked",
                "hintLevel": 8,
                "completedQuestions": ["1", "1"],
                "remainingQuestions": ["", 2],
            },
            None,
        )
        errors, _ = records.validate_current(checkpoint)
        self.assertTrue(any("teachingMode" in error for error in errors))
        self.assertTrue(any("answerState" in error for error in errors))
        self.assertTrue(any("hintLevel" in error for error in errors))
        self.assertTrue(any("completedQuestions" in error for error in errors))
        self.assertTrue(any("remainingQuestions" in error for error in errors))

    def test_create_without_date_keeps_updated_at_null(self) -> None:
        checkpoint = records.build_checkpoint({"currentTask": None}, None)
        self.assertIsNone(checkpoint["updatedAt"])

    def test_read_with_queue_computes_due(self) -> None:
        checkpoint = records.build_checkpoint({"currentTask": "任务", "position": None}, None)
        queue = {
            "schemaVersion": "1.2",
            "recordType": "ReviewQueue",
            "generatedAt": None,
            "items": [
                {"subject": None, "topic": "到期题", "errorCause": None, "errorCauseStatus": None,
                 "nextRetestDate": "2026-09-01", "retestOffsetDays": None, "status": "due",
                 "masteryEvidence": [], "retestEvidence": []},
            ],
        }
        plan = records.read_checkpoint(checkpoint, __import__("datetime").date(2026, 9, 11), queue)
        self.assertEqual(plan["dueReview"]["due"][0]["topic"], "到期题")


class ValidationTests(unittest.TestCase):
    def test_invalid_12_record_reports_errors(self) -> None:
        record = {
            "schemaVersion": "1.2",
            "recordType": "ReviewQueue",
            "generatedAt": None,
            "items": [
                {
                    "subject": None, "topic": "limit", "errorCause": None, "errorCauseStatus": None,
                    "nextRetestDate": "2026-09-01", "retestOffsetDays": 3,
                    "status": "pending", "masteryEvidence": [],
                    "retestEvidence": [{"evidenceType": "guess", "outcome": "correct"}],
                }
            ],
        }
        report = records.validate_record(record)
        self.assertFalse(report["valid"])
        self.assertTrue(any("simultaneously" in error for error in report["errors"]))
        self.assertTrue(any("evidenceType is invalid" in error for error in report["errors"]))

    def test_retest_offset_must_be_a_non_negative_integer_or_null(self) -> None:
        base = {
            "schemaVersion": "1.2", "recordType": "ReviewQueue", "generatedAt": None,
            "items": [{
                "subject": "408", "topic": "LRU", "errorCause": None,
                "errorCauseStatus": None, "nextRetestDate": None, "retestAnchorDate": "2026-10-01",
                "status": "pending", "masteryEvidence": [],
            }],
        }
        for offset in ("3", 3.5, True):
            with self.subTest(offset=offset):
                report = records.validate_record({**base, "items": [{**base["items"][0], "retestOffsetDays": offset}]})
                self.assertFalse(report["valid"])
                self.assertTrue(any("retestOffsetDays must be a non-negative integer" in e for e in report["errors"]))

    def test_mastered_without_independent_evidence_warns(self) -> None:
        record = {
            "schemaVersion": "1.2",
            "recordType": "ReviewQueue",
            "generatedAt": None,
            "items": [
                {"subject": None, "topic": "t", "errorCause": None, "errorCauseStatus": None,
                 "nextRetestDate": None, "retestOffsetDays": None, "status": "mastered",
                 "masteryEvidence": [],
                 "retestEvidence": [{"evidenceType": "solution-seen", "outcome": "correct"}]},
            ],
        }
        report = records.validate_record(record)
        self.assertTrue(report["valid"])
        self.assertTrue(any("mastered" in warning for warning in report["warnings"]))

    def test_unknown_outcome_does_not_justify_mastered_status(self) -> None:
        record = {
            "schemaVersion": "1.2", "recordType": "ReviewQueue", "generatedAt": None,
            "items": [{
                "subject": "408", "topic": "LRU", "errorCause": None,
                "errorCauseStatus": None, "nextRetestDate": None, "retestOffsetDays": None,
                "status": "mastered", "masteryEvidence": [],
                "retestEvidence": [{"evidenceType": "independent", "outcome": None}],
            }],
        }
        report = records.validate_record(record, strict=True)
        self.assertFalse(report["valid"])
        self.assertTrue(any("mastered" in warning for warning in report["warnings"]))

    def test_legacy_10_input_is_readable(self) -> None:
        report = records.validate_record(REVIEW_QUEUE_10)
        self.assertTrue(report["valid"])
        self.assertTrue(report["legacy"])


class CliTests(unittest.TestCase):
    def test_validate_cli_exit_codes(self) -> None:
        ok = run_cli("validate", stdin=json.dumps(REVIEW_QUEUE_10, ensure_ascii=False))
        self.assertEqual(ok.returncode, 0, ok.stderr)
        bad = run_cli("validate", stdin='{"schemaVersion":"1.2","recordType":"ReviewQueue"}')
        self.assertEqual(bad.returncode, 1)
        self.assertFalse(json.loads(bad.stdout)["valid"])
        missing = run_cli("merge", "-", "-", stdin="{}")
        self.assertEqual(missing.returncode, 1)
        self.assertIn("error", json.loads(missing.stderr))

    def test_merge_cli_rejects_two_stdin_inputs(self) -> None:
        result = run_cli("merge", "-", "-", stdin="{}")
        self.assertEqual(result.returncode, 1)

    def test_due_cli_with_explicit_base_date(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            queue_file = Path(temporary) / "queue.json"
            queue_file.write_text(
                json.dumps(
                    {
                        "schemaVersion": "1.2",
                        "recordType": "ReviewQueue",
                        "generatedAt": None,
                        "items": [
                            {"subject": None, "topic": "到期题", "errorCause": None,
                             "errorCauseStatus": None, "nextRetestDate": "2026-09-10",
                             "retestOffsetDays": None, "status": "due",
                             "masteryEvidence": [], "retestEvidence": []},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            result = run_cli("due", str(queue_file), "--date", "2026-09-11")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["date"], "2026-09-11")
            self.assertEqual(len(payload["due"]), 1)

    def test_due_rejects_non_object_review_items_and_invalid_dates_as_json_errors(self) -> None:
        queue = {
            "schemaVersion": "1.2", "recordType": "ReviewQueue",
            "generatedAt": None, "items": [None],
        }
        result = run_cli("due", "-", "--date", "2026-09-11", stdin=json.dumps(queue))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("items[0] must be an object", json.loads(result.stderr)["error"])
        invalid_date = run_cli("due", "-", "--date", "not-a-date", stdin="{}")
        self.assertEqual(invalid_date.returncode, 1)
        self.assertNotIn("Traceback", invalid_date.stderr)
        self.assertIsInstance(json.loads(invalid_date.stderr), dict)

    def test_normalize_rejects_malformed_review_queue_items(self) -> None:
        for record in (
            {"schemaVersion": "1.0", "items": None},
            {"schemaVersion": "1.0", "items": [None]},
            {"schemaVersion": "1.2", "recordType": "ReviewQueue", "items": [None]},
        ):
            with self.subTest(record=record):
                result = run_cli("normalize", stdin=json.dumps(record, ensure_ascii=False))
                self.assertEqual(result.returncode, 1)
                self.assertNotIn("Traceback", result.stderr)
                self.assertIsInstance(json.loads(result.stderr), dict)

    def test_checkpoint_read_rejects_a_different_record_type(self) -> None:
        review_queue = {
            "schemaVersion": "1.2", "recordType": "ReviewQueue",
            "generatedAt": None, "items": [],
        }
        result = run_cli("checkpoint", "read", stdin=json.dumps(review_queue))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(
            json.loads(result.stderr)["error"],
            "checkpoint read requires recordType SessionCheckpoint",
        )

    def test_checkpoint_cli_create_and_read(self) -> None:
        created = run_cli(
            "checkpoint", "create", "--date", "2026-09-11",
            stdin=json.dumps({"currentTask": "408 操作系统", "position": "第 3 章", "dueItems": [], "pendingRetests": []}, ensure_ascii=False),
        )
        self.assertEqual(created.returncode, 0, created.stderr)
        checkpoint = json.loads(created.stdout)
        self.assertEqual(checkpoint["updatedAt"], "2026-09-11")
        read = run_cli("checkpoint", "read", stdin=json.dumps(checkpoint, ensure_ascii=False))
        self.assertEqual(read.returncode, 0, read.stderr)
        plan = json.loads(read.stdout)
        self.assertEqual(plan["resume"]["currentTask"], "408 操作系统")

    @unittest.skipUnless(sys.platform == "win32", "Windows native-pipe encoding regression")
    def test_utf8_stdin_works_without_python_utf8_environment(self) -> None:
        import os

        env = os.environ.copy()
        env.pop("PYTHONUTF8", None)
        env.pop("PYTHONIOENCODING", None)
        payload = json.dumps(
            {"currentTask": "第五题", "position": "题5未开始"},
            ensure_ascii=False,
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "checkpoint", "create", "--date", "2026-09-20"],
            input=payload,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["currentTask"], "第五题")


if __name__ == "__main__":
    unittest.main()

"""Scripted lifecycle across the real records CLI, temporary notes and fake Notion.

These integration fixtures exercise persistence and readback with fresh CLI
processes. They do not prove that a model follows routing or write permissions.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import uuid

try:
    from .test_v280_notes_fixture import ROOT_ID, StdioClient
except ImportError:
    from test_v280_notes_fixture import ROOT_ID, StdioClient


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/records.py"
DAY = "2026-10-25"
NEXT_DAY = "2026-10-28"
COMMENT = "用户批注：先完成已确认任务，不自动增加计划。"


def packed(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


class LearningCycleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="408-learning-cycle-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name).resolve()
        self.vault = self.base / "synthetic-vault"
        self.vault.mkdir()

    def cli(self, *arguments, payload=None, expected=0):
        environment = os.environ.copy()
        environment.update({"PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"})
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *map(str, arguments)],
            input=None if payload is None else packed(payload).encode("utf-8"),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment,
            timeout=30, check=False,
        )
        self.assertEqual(result.returncode, expected, result.stderr.decode("utf-8"))
        return json.loads(result.stdout.decode("utf-8")) if result.stdout else None

    def data_file(self, name, value):
        path = self.base / name
        path.write_text(packed(value), encoding="utf-8", newline="\n")
        return path

    def note(self, name, value):
        # The test driver plays an authorized host, not a new persistence API.
        path = self.vault / name
        path.write_text("# 虚构学习笔记\n\n" + COMMENT + "\n\n```json\n" + packed(value) + "```\n",
                        encoding="utf-8", newline="\n")
        return path

    def read_note(self, path):
        text = path.read_text(encoding="utf-8")
        self.assertIn(COMMENT, text)
        blocks = re.findall(r"```json\n(.*?)\n```", text, re.DOTALL)
        self.assertEqual(len(blocks), 1)
        return json.loads(blocks[0])

    def replace_note_record(self, path, value):
        text = path.read_text(encoding="utf-8")
        original = self.read_note(path)
        original_block = "```json\n" + packed(original) + "```"
        self.assertEqual(text.count(original_block), 1)
        backup = path.with_suffix(path.suffix + ".before")
        with backup.open("xb") as handle:
            handle.write(path.read_bytes())
        path.write_text(text.replace(original_block, "```json\n" + packed(value) + "```"),
                        encoding="utf-8", newline="\n")
        return backup

    def checkpoint(self):
        return self.cli("checkpoint", "create", "--date", DAY, payload={
            "currentTask": "408 页面置换原创练习", "position": "Q1 已完成，Q2 未开始",
            "teachingMode": "hint", "answerState": "hidden", "hintLevel": 0,
            "currentQuestion": "Q2", "completedQuestions": ["Q1"], "remainingQuestions": ["Q2"],
            "materialVersion": "synthetic-page-exercise-v1", "dueItems": [], "pendingRetests": [],
            "notes": "仅使用此虚构测试材料",
        })

    def queue_record(self):
        return self.cli("normalize", payload={
            "schemaVersion": "1.1", "recordType": "ReviewQueue", "generatedAt": DAY,
            "items": [{"subject": "408", "topic": "FIFO 页面置换", "errorCause": "命中后改变队列顺序",
                       "errorCauseStatus": "hypothesis", "nextRetestDate": None, "retestOffsetDays": 3,
                       "retestAnchorDate": DAY, "status": "pending", "masteryEvidence": [],
                       "retestEvidence": [], "userAnnotation": "需检查是否混淆算法"}],
        })["record"]

    def notion(self):
        client = StdioClient(self.base / ("notes-fixture-" + uuid.uuid4().hex))
        self.addCleanup(client.close)
        self.assertEqual(client.initialize()["result"]["protocolVersion"], "2025-11-25")
        return client

    def test_plan_execution_checkpoint_resume_retest_and_progress_roundtrip(self):
        profile = self.cli("normalize", payload={
            "schemaVersion": "1.0", "targetExam": "408考研", "targetDate": None,
            "weeklyHours": 8, "currentPhase": None, "constraints": [],
            "userAnnotation": "仅当前虚构计划",
        })["record"]
        self.note("学习档案.md", profile)
        progress = self.cli("normalize", payload={
            "schemaVersion": "1.1", "recordType": "ProgressSnapshot",
            "period": {"start": DAY, "end": NEXT_DAY},
            "metrics": [{"subject": "408", "name": "页面置换练习", "unit": "questions", "planned": 2, "completed": None}],
            "accuracy": [{"subject": "408", "correct": None, "total": None, "rate": None}], "blockers": [],
        })["record"]
        progress_note = self.note("当前进度.md", progress)
        self.assertIsNone(self.read_note(progress_note)["metrics"][0]["completed"])
        actual = deepcopy(progress)
        actual.update(updatedAt=DAY)
        actual["metrics"][0]["completed"] = 1
        actual["accuracy"][0].update(correct=0, total=1, rate=0)
        self.assertTrue(self.cli("validate", "--strict", payload=actual)["valid"])
        self.replace_note_record(progress_note, actual)
        checkpoint = self.checkpoint()
        checkpoint_note = self.note("学习检查点.md", checkpoint)
        queue = self.queue_record()
        queue_note = self.note("错题队列.md", queue)
        # Fresh processes receive only persisted record bytes, as a new session would.
        persisted_checkpoint = self.data_file("resume.json", self.read_note(checkpoint_note))
        persisted_queue = self.data_file("queue.json", self.read_note(queue_note))
        resumed = self.cli("checkpoint", "read", persisted_checkpoint, "--queue", persisted_queue, "--date", NEXT_DAY)
        self.assertEqual(resumed["resume"]["position"], "Q1 已完成，Q2 未开始")
        self.assertEqual(resumed["resume"]["answerState"], "hidden")
        self.assertEqual(resumed["resume"]["remainingQuestions"], ["Q2"])
        self.assertEqual(resumed["dueReview"]["due"][0]["resolvedDate"], NEXT_DAY)
        updated_queue = deepcopy(queue)
        updated_queue["updatedAt"] = NEXT_DAY
        updated_queue["items"][0]["status"] = "retesting"
        updated_queue["items"][0]["retestEvidence"].append({
            "evidenceType": "hint-assisted", "outcome": "correct", "date": NEXT_DAY,
            "note": "测试输入明确提供：使用提示后答对，不足以证明掌握",
        })
        self.assertTrue(self.cli("validate", "--strict", payload=updated_queue)["valid"])
        self.replace_note_record(queue_note, updated_queue)
        self.assertEqual(self.read_note(queue_note)["recordId"], queue["recordId"])
        self.assertEqual(self.read_note(queue_note)["items"][0]["itemId"], queue["items"][0]["itemId"])
        self.assertEqual(self.read_note(queue_note)["items"][0]["status"], "retesting")
        self.assertEqual(self.read_note(queue_note)["items"][0]["userAnnotation"], "需检查是否混淆算法")
        diagnostic = self.cli("normalize", payload=self.read_note(progress_note))["record"]
        self.assertEqual(diagnostic["recordId"], progress["recordId"])
        self.assertEqual((diagnostic["metrics"][0]["planned"], diagnostic["metrics"][0]["completed"]), (2, 1))
        self.assertIsNone(profile["targetDate"])

    def test_checkpoint_update_is_idempotent_and_new_session_preserves_equal_revision_conflicts(self):
        base = self.checkpoint()
        source = self.data_file("checkpoint.json", base)
        changes = self.data_file("changes.json", {"position": "Q2 只完成第1步", "hintLevel": 1})
        newer = self.cli("checkpoint", "update", source, "--changes", changes, "--date", NEXT_DAY)
        self.assertEqual(newer["checkpointId"], base["checkpointId"])
        self.assertEqual(newer["checkpointRevision"], 2)
        note = self.note("学习检查点.md", newer)
        same = self.cli("checkpoint", "update", self.data_file("saved.json", self.read_note(note)),
                        "--changes", changes, "--date", "2026-10-29")
        self.assertEqual(same, newer)
        alternative = {**newer, "position": "另一个设备报告Q2尚未开始", "updatedAt": "2026-10-29"}
        bundle = self.cli("merge", self.data_file("left.json", newer), self.data_file("right.json", alternative))
        audit_note = self.note("冲突待确认.md", bundle)
        reimported = self.cli("merge", self.data_file("bundle.json", self.read_note(audit_note)),
                             self.data_file("again.json", alternative))
        self.assertEqual(reimported["records"][0]["position"], newer["position"])
        conflicts = [entry for entry in reimported["mergeConflicts"] if entry["path"].endswith("/position")]
        self.assertTrue(conflicts)
        self.assertEqual(conflicts[0]["resolution"], "kept-first")
        self.assertEqual(len(reimported["mergeConflicts"]), len(bundle["mergeConflicts"]))
        self.assertEqual(json.loads(source.read_text(encoding="utf-8")), base)

    def test_failed_record_update_leaves_persisted_note_and_source_intact(self):
        checkpoint = self.checkpoint()
        note = self.note("学习检查点.md", checkpoint)
        original = note.read_bytes()
        record = self.data_file("saved.json", self.read_note(note))
        changes = self.data_file("bad-changes.json", {"checkpointRevision": 999})
        self.assertIsNone(self.cli("checkpoint", "update", record, "--changes", changes, "--date", NEXT_DAY, expected=1))
        self.assertEqual(note.read_bytes(), original)
        self.assertEqual(json.loads(record.read_text(encoding="utf-8")), checkpoint)
        self.assertFalse(note.with_suffix(".md.before").exists())

    def test_legacy_formats_roundtrip_unknown_fields_and_unknown_values(self):
        records = [{"schemaVersion": "1.0", "targetExam": "408考研", "targetDate": "unknown",
                    "weeklyHours": None, "currentPhase": None, "constraints": [], "safeExtension": {"reviewStyle": "short"}},
                   {"schemaVersion": "1.1", "recordType": "ProgressSnapshot", "period": {"start": None, "end": None},
                    "metrics": [{"subject": "数学", "name": "练习", "unit": "questions", "planned": 5, "completed": None}],
                    "accuracy": [{"subject": "数学", "correct": None, "total": 3, "rate": 0.67}],
                    "blockers": [], "userAnnotation": "科目未细分"}]
        migrated = self.cli("normalize", payload=records)
        note = self.note("旧记录迁移.md", migrated)
        persisted = self.read_note(note)
        self.assertTrue(self.cli("validate", payload=persisted)["valid"])
        first, second = persisted["records"]
        self.assertEqual(first["legacyExtensions"]["safeExtension"], {"reviewStyle": "short"})
        self.assertIsNone(first["targetDate"])
        self.assertEqual(second["userAnnotation"], "科目未细分")
        self.assertEqual(second["metrics"][0]["subject"], "数学")
        self.assertIsNone(second["accuracy"][0]["correct"])
        self.assertIsNone(second["updatedAt"])

    def test_fake_notion_checkpoint_write_fetch_resume_and_failed_update(self):
        client = self.notion()
        checkpoint = self.checkpoint()
        text = COMMENT + "\n```json\n" + packed(checkpoint) + "```"
        created = client.tool("notion_create_page", {"parent_id": ROOT_ID, "title": "09｜学习检查点", "content": text})["result"]
        self.assertFalse(created["isError"])
        page_id = created["structuredContent"]["page"]["id"]
        fetched = client.tool("notion_fetch", {"page_id": page_id})["result"]["structuredContent"]["page"]
        self.assertEqual(fetched["content"], text)
        extracted = json.loads(re.search(r"```json\n(.*?)\n```", fetched["content"], re.DOTALL)[1])
        self.assertTrue(self.cli("validate", "--strict", payload=extracted)["valid"])
        self.assertEqual(self.cli("checkpoint", "read", payload=extracted)["resume"]["answerState"], "hidden")
        failed = client.tool("notion_update_page", {"page_id": page_id, "old_str": "不存在的记录块", "new_str": "不得替换"})["result"]
        self.assertTrue(failed["isError"])
        self.assertEqual(client.tool("notion_fetch", {"page_id": page_id})["result"]["structuredContent"]["page"]["content"], text)
        client.close()
        snapshots = sorted(client.root.glob("state-*.json"))
        self.assertEqual(len(snapshots), 2)
        persisted = json.loads(snapshots[-1].read_text(encoding="utf-8"))
        self.assertEqual(persisted["pages"][page_id]["content"], text)

    def test_partial_cross_store_save_keeps_verified_local_update_and_can_resume_remote_update(self):
        client = self.notion()
        checkpoint = self.checkpoint()
        local_note = self.note("学习检查点.md", checkpoint)
        remote_text = COMMENT + "\n```json\n" + packed(checkpoint) + "```"
        created = client.tool("notion_create_page", {
            "parent_id": ROOT_ID, "title": "09｜学习检查点", "content": remote_text,
        })["result"]["structuredContent"]["page"]
        page_id = created["id"]
        source = self.data_file("before-update.json", checkpoint)
        changes = self.data_file("partial-save-changes.json", {"position": "Q2 已独立完成第一步"})
        updated = self.cli("checkpoint", "update", source, "--changes", changes, "--date", NEXT_DAY)
        backup = self.replace_note_record(local_note, updated)
        self.assertTrue(self.cli("validate", "--strict", payload=self.read_note(local_note))["valid"])
        self.assertEqual(self.read_note(local_note)["checkpointRevision"], 2)

        # The first authorized target is saved and read back. A stale second
        # target fails independently; the driver must not roll back the first.
        rejected = client.tool("notion_update_page", {
            "page_id": page_id, "old_str": "过时且不存在的记录块", "new_str": packed(updated),
        })["result"]
        self.assertTrue(rejected["isError"])
        remote = client.tool("notion_fetch", {"page_id": page_id})["result"]["structuredContent"]["page"]
        self.assertEqual(remote["content"], remote_text)
        self.assertEqual(self.read_note(local_note), updated)
        self.assertIn(packed(checkpoint), backup.read_text(encoding="utf-8"))
        self.assertEqual(json.loads(source.read_text(encoding="utf-8")), checkpoint)

        # Resume by re-reading and updating the same page/ID, never creating
        # another checkpoint page or incrementing the record revision again.
        expected = remote["content"].replace(packed(checkpoint), packed(updated))
        accepted = client.tool("notion_update_page", {
            "page_id": page_id, "old_str": packed(checkpoint), "new_str": packed(updated),
        })["result"]
        self.assertFalse(accepted["isError"])
        fetched = client.tool("notion_fetch", {"page_id": page_id})["result"]["structuredContent"]["page"]
        self.assertEqual(fetched["content"], expected)
        persisted = json.loads(re.search(r"```json\n(.*?)\n```", fetched["content"], re.DOTALL)[1])
        self.assertTrue(self.cli("validate", "--strict", payload=persisted)["valid"])
        self.assertEqual(persisted, updated)
        client.close()
        events = [json.loads(line) for line in (client.root / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
        calls = [event["message"]["params"]["name"] for event in events
                 if event.get("event") == "attempt" and event.get("message", {}).get("method") == "tools/call"]
        self.assertEqual(calls.count("notion_create_page"), 1)
        self.assertEqual(calls.count("notion_update_page"), 2)
        self.assertEqual(len(list(client.root.glob("state-*.json"))), 3)

    def test_scripted_readonly_and_notion_disabled_traces_keep_remote_writes_zero(self):
        # This is a reference trace driven by the test, not a model permission verdict.
        for mode in ("all-readonly", "notion-disabled", "no-save-request"):
            with self.subTest(mode=mode):
                client = self.notion()
                note = self.note(mode + ".md", self.checkpoint())
                before = hashlib.sha256(note.read_bytes()).hexdigest()
                remote_before = (client.root / "state-000000.json").read_bytes()
                self.cli("checkpoint", "read", payload=self.read_note(note))
                client.tool("notion_fetch", {"page_id": ROOT_ID})
                if mode == "notion-disabled":
                    candidate = self.read_note(note)
                    candidate["notes"] = "测试侧明确授权本地保存，Notion不写入"
                    self.replace_note_record(note, candidate)
                    self.assertTrue(self.cli("validate", "--strict", payload=self.read_note(note))["valid"])
                    self.assertNotEqual(hashlib.sha256(note.read_bytes()).hexdigest(), before)
                else:
                    self.assertEqual(hashlib.sha256(note.read_bytes()).hexdigest(), before)
                client.close()
                events = [json.loads(line) for line in (client.root / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
                writes = [event for event in events if event.get("event") == "attempt"
                          and event.get("message", {}).get("params", {}).get("name") in {"notion_create_page", "notion_update_page"}]
                self.assertEqual(writes, [])
                self.assertEqual((client.root / "state-000000.json").read_bytes(), remote_before)
                self.assertEqual(len(list(client.root.glob("state-*.json"))), 1)


if __name__ == "__main__":
    unittest.main()

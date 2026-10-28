from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from audit_host_trace import TraceError, audit_trace  # noqa: E402


def event(call_id="call-1", tool="Skill", status="completed", skill="kaoyan-408:kaoyan-408-tutor"):
    return {"role": "assistant", "part": {"type": "tool", "callID": call_id,
            "tool": tool, "state": {"status": status, "input": {"skill": skill}}}}


class HostTraceAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "parts.jsonl"

    def write(self, *events):
        self.path.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")

    def test_answer_without_tools_is_not_a_plugin_pass(self):
        self.write({"role": "assistant", "part": {"type": "text", "text": "Correct answer"}})
        report = audit_trace(self.path, "ordinary")
        self.assertEqual(report["pluginSkillInvocations"], 0)
        self.assertEqual(report["behaviorGrade"], "not_assessed")
        self.assertEqual(report["traceCompleteness"], "not_verified")

    def test_inline_python_is_not_a_skill_invocation(self):
        item = event(tool="Bash")
        item["part"]["state"]["input"] = {"command": 'python -c "print(9)"'}
        self.write(item)
        report = audit_trace(self.path, "ordinary")
        self.assertEqual(report["toolCalls"], {"Bash": 1})
        self.assertEqual(report["pluginSkillInvocations"], 0)

    def test_completed_skill_is_an_observation_not_behavior_grade(self):
        self.write(event())
        report = audit_trace(self.path, "explicit")
        self.assertEqual(report["mode"], "explicit")
        self.assertEqual(report["pluginSkillInvocations"], 1)
        self.assertEqual(report["pluginSkillStatuses"], {"completed": 1})
        self.assertEqual(report["behaviorGrade"], "not_assessed")

    def test_failed_call_does_not_become_completed(self):
        self.write(event(status="error"))
        report = audit_trace(self.path, "explicit")
        self.assertEqual(report["pluginSkillStatuses"], {"error": 1})
        self.assertNotIn("completed", report["pluginSkillStatuses"])

    def test_call_snapshots_are_counted_once(self):
        self.write(event(status="running"), event(status="completed"))
        report = audit_trace(self.path, "explicit")
        self.assertEqual(report["toolCalls"], {"Skill": 1})
        self.assertEqual(report["pluginSkillStatuses"], {"completed": 1})

    def test_completed_snapshot_without_input_preserves_skill_identity(self):
        completed = event(status="completed")
        del completed["part"]["state"]["input"]
        self.write(event(status="running"), completed)
        report = audit_trace(self.path, "explicit")
        self.assertEqual(report["pluginSkillInvocations"], 1)
        self.assertEqual(report["pluginSkillStatuses"], {"completed": 1})

    def test_same_call_cannot_change_skill_identity(self):
        self.write(event(status="running"), event(skill="other-plugin:kaoyan-408-tutor"))
        with self.assertRaises(TraceError):
            audit_trace(self.path, "explicit")

    def test_user_quoted_tool_call_and_other_plugin_are_excluded(self):
        quoted = event()
        quoted["role"] = "user"
        self.write(quoted, event("other", skill="other-plugin:kaoyan-408-tutor"))
        report = audit_trace(self.path, "ordinary")
        self.assertEqual(report["toolCalls"], {"Skill": 1})
        self.assertEqual(report["pluginSkillInvocations"], 0)

    def test_bare_skill_name_is_supported(self):
        self.write(event(skill="kaoyan-review-executor"))
        self.assertEqual(audit_trace(self.path, "explicit")["pluginSkillInvocations"], 1)

    def test_empty_or_wrong_format_is_rejected(self):
        for text in ("", "{}\n", "[]\n", "not-json\n"):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(TraceError):
                    audit_trace(self.path, "ordinary")

    def test_cli_does_not_modify_trace_or_echo_command_content(self):
        item = event(tool="Bash")
        item["part"]["state"]["input"] = {"command": "private-user-content"}
        self.write(item)
        original = self.path.read_bytes()
        result = subprocess.run([sys.executable, str(REPO / "scripts/audit_host_trace.py"),
                                 "--trace", str(self.path), "--mode", "ordinary"],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("private-user-content", result.stdout)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(len(json.loads(result.stdout)["traceSha256"]), 64)

    def test_call_id_reused_for_a_different_tool_is_rejected(self):
        self.write(event(), event(tool="Bash"))
        with self.assertRaises(TraceError):
            audit_trace(self.path, "ordinary")

    def test_invalid_role_is_rejected_without_a_type_error(self):
        item = event()
        item["role"] = []
        self.write(item)
        with self.assertRaises(TraceError):
            audit_trace(self.path, "ordinary")

    def test_unknown_status_is_not_reported_as_completed(self):
        self.write(event(status=[]))
        self.assertEqual(audit_trace(self.path, "explicit")["pluginSkillStatuses"], {"unknown": 1})


if __name__ == "__main__":
    unittest.main()

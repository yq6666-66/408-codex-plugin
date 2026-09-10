from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from validate_repository import (  # noqa: E402
    ALLOWED_RELEASE_FILES,
    EXPECTED_SKILLS,
    ValidationError,
    check_behavior_cases,
    check_forward_cases,
    check_learning_layer_contract,
    check_obsidian_brain_contract,
    check_portable_schema,
    check_progress_accuracy_semantics,
    validate_repo,
)
from release_payload import check_mastery_evidence_semantics  # noqa: E402


def skill_text(name: str) -> str:
    return (REPO / "plugins/kaoyan-408/skills" / name / "SKILL.md").read_text(encoding="utf-8")


class RepositoryContractTests(unittest.TestCase):
    def test_repository_contract(self) -> None:
        results = validate_repo(REPO, scan_history=False)
        self.assertEqual(len(results), 6)

    def test_manifest_is_release_semver_and_skills_only(self) -> None:
        manifest = json.loads(
            (REPO / "plugins/kaoyan-408/.codex-plugin/plugin.json").read_text(encoding="utf-8")
        )
        self.assertRegex(manifest["version"], r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertTrue({"apps", "mcpServers", "hooks"}.isdisjoint(manifest))

    def test_exact_skill_and_release_file_sets(self) -> None:
        plugin = REPO / "plugins/kaoyan-408"
        skills = {path.name for path in (plugin / "skills").iterdir() if path.is_dir()}
        files = {
            path.relative_to(plugin).as_posix()
            for path in plugin.rglob("*")
            if path.is_file()
        }
        self.assertEqual(skills, EXPECTED_SKILLS)
        self.assertEqual(files, set(ALLOWED_RELEASE_FILES))

    def test_schema_and_eval_case_contracts(self) -> None:
        plugin = REPO / "plugins/kaoyan-408"
        check_portable_schema(plugin)
        check_obsidian_brain_contract(plugin)
        check_learning_layer_contract(plugin)
        check_forward_cases(REPO)
        check_behavior_cases(REPO)

    def test_merged_brand_contracts_are_gone(self) -> None:
        references = REPO / "plugins/kaoyan-408/references"
        remaining = sorted(path.name for path in references.glob("*-contract.md"))
        self.assertEqual(
            remaining,
            [
                "beginner-visual-answer-contract.md",
                "capability-routing-contract.md",
                "evidence-copyright-contract.md",
                "learning-layer-contract.md",
                "notion-brain-contract.md",
                "obsidian-brain-contract.md",
                "past-paper-source-contract.md",
            ],
        )

    def test_behavior_critical_rules_remain(self) -> None:
        """A small set of behavior-critical product rules, not verbatim prose matching."""
        mock = skill_text("kaoyan-mock-exam-coach")
        self.assertIn("交卷前", mock)
        self.assertIn("rubric", mock)
        tutor = skill_text("kaoyan-408-tutor")
        self.assertIn("模型讲解", tutor)
        error_loop = skill_text("kaoyan-error-loop-coach")
        self.assertIn("hypothesis", error_loop)
        planner = skill_text("kaoyan-408-planner")
        self.assertIn("null", planner)
        politics = skill_text("kaoyan-politics-coach")
        self.assertIn("[待核验]", politics)
        past_paper = skill_text("kaoyan-past-paper-analyst")
        self.assertIn("样本覆盖表", past_paper)

    def test_teaching_modes_and_answer_policy_are_wired(self) -> None:
        beginner = (REPO / "plugins/kaoyan-408/references/beginner-visual-answer-contract.md").read_text(
            encoding="utf-8"
        )
        for marker in ("逐级提示", "独立作答", "考考我", "交卷前", "题面完整性检查"):
            self.assertIn(marker, beginner)
        routing = (REPO / "plugins/kaoyan-408/references/capability-routing-contract.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("三种教学模式", routing)
        self.assertIn("SessionCheckpoint", routing)

    def test_permission_semantics_distinguish_readonly_from_notion_only(self) -> None:
        layer = (REPO / "plugins/kaoyan-408/references/learning-layer-contract.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("禁止所有学习记录写入", layer)
        self.assertIn("仅限制 Notion 写入", layer)

    def test_accuracy_semantics_reject_impossible_or_inconsistent_values(self) -> None:
        base = {
            "schemaVersion": "1.1",
            "recordType": "ProgressSnapshot",
            "period": {"start": None, "end": None},
            "metrics": [],
            "blockers": [],
        }
        check_progress_accuracy_semantics(
            {**base, "accuracy": [{"subject": "english2", "correct": 16, "total": 20, "rate": 0.8}]}
        )
        with self.assertRaisesRegex(ValidationError, "must not exceed"):
            check_progress_accuracy_semantics(
                {**base, "accuracy": [{"subject": "english2", "correct": 21, "total": 20, "rate": 1.0}]}
            )
        with self.assertRaisesRegex(ValidationError, "must equal"):
            check_progress_accuracy_semantics(
                {**base, "accuracy": [{"subject": "english2", "correct": 16, "total": 20, "rate": 0.7}]}
            )

    def test_mastery_evidence_semantics_require_independent_or_transfer(self) -> None:
        base_item = {
            "subject": "408",
            "topic": "LRU",
            "errorCause": None,
            "errorCauseStatus": None,
            "nextRetestDate": None,
            "retestOffsetDays": None,
            "status": "mastered",
            "masteryEvidence": [],
        }
        queue = {"recordType": "ReviewQueue", "items": [base_item]}
        self.assertEqual(len(check_mastery_evidence_semantics(queue)), 1)
        solution_only = {
            **queue,
            "items": [
                {
                    **base_item,
                    "retestEvidence": [
                        {"evidenceType": "solution-seen", "outcome": "correct"},
                        {"evidenceType": "redo-after-solution", "outcome": "correct"},
                    ],
                }
            ],
        }
        self.assertEqual(len(check_mastery_evidence_semantics(solution_only)), 1)
        independent = {
            **queue,
            "items": [
                {
                    **base_item,
                    "retestEvidence": [{"evidenceType": "independent", "outcome": "correct"}],
                }
            ],
        }
        self.assertEqual(check_mastery_evidence_semantics(independent), [])


if __name__ == "__main__":
    unittest.main()

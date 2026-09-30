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

    def test_runtime_helpers_ship_inside_the_plugin(self) -> None:
        plugin = REPO / "plugins/kaoyan-408"
        expected = {
            "scripts/records.py",
            "scripts/study_simulator.py",
            "scripts/configure_obsidian_brain.py",
            "scripts/health_check.py",
        }
        self.assertTrue(expected.issubset(ALLOWED_RELEASE_FILES))
        for relative in expected:
            self.assertTrue((plugin / relative).is_file(), relative)

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

    def test_past_paper_search_blocks_unreadable_formula_transcription(self) -> None:
        searcher = skill_text("kaoyan-past-paper-searcher")
        self.assertIn("逐项抄写", searcher)
        self.assertIn("外层倍数、括号内增量、分母和指数", searcher)
        self.assertIn("任何一项看不清或两个来源不一致", searcher)
        self.assertIn("工具输出中必须实际显示完整公式", searcher)
        self.assertIn("Total lines", searcher)
        self.assertIn("仍视为没有读到可核验公式", searcher)
        self.assertIn("有可用的直接正文读取工具时先获取网页正文", searcher)
        self.assertIn("题面核对：外层倍数=", searcher)
        self.assertIn("括号内增量=", searcher)
        self.assertIn("用户在同一条请求中要求", searcher)
        self.assertIn("不得只附交接卡", searcher)
        self.assertIn("[待核验]", searcher)
        self.assertIn("原创示例", searcher)

    def test_official_comparison_never_calculates_mismatched_ratios(self) -> None:
        official = skill_text("kaoyan-official-info-researcher")
        self.assertIn("先输出一行逐项完整的统一口径", official)
        self.assertIn("即使输入材料里已经出现", official)
        self.assertIn("统一口径：招生年度=", official)
        self.assertIn("学位类型=", official)
        self.assertIn("先分别写明分子和分母各自统计的对象", official)
        self.assertIn("不计算、不列数值，也不提供“粗略参考比”", official)

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

    def test_teaching_mode_precedence_and_conditional_output(self) -> None:
        beginner = (REPO / "plugins/kaoyan-408/references/beginner-visual-answer-contract.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("教学模式优先于输出顺序", beginner)
        self.assertIn("确实帮助理解", beginner)
        self.assertNotIn("**图解**：必须提供", beginner)
        portable = (REPO / "plugins/kaoyan-408/references/portable-learning-records.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("不必在正文重复粘贴完整 JSON", portable)

    def test_observed_model_failures_have_explicit_guards(self) -> None:
        beginner = (REPO / "plugins/kaoyan-408/references/beginner-visual-answer-contract.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("一批”就是一条助手回复", beginner)
        self.assertIn("不得在同一条回复里另写“第二批”", beginner)
        self.assertIn("提出一个决定结论的最小确认问题", beginner)
        self.assertIn("左右极限", beginner)
        self.assertIn("当前轮次存在成功的工具调用", beginner)
        math = skill_text("kaoyan-math-coach")
        self.assertIn("对照本轮工具事件", math)
        self.assertIn("未调用只能标人工复核", math.split("---", 2)[1])
        tutor = skill_text("kaoyan-408-tutor")
        self.assertIn("当前回复只展开前四题", tutor.split("---", 2)[1])
        layer = (REPO / "plugins/kaoyan-408/references/learning-layer-contract.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("只有调用成功且取得可引用输出", layer)

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

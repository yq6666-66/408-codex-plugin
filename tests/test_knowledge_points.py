from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
from validate_repository import ValidationError, check_knowledge_points  # noqa: E402


class KnowledgePointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.plugin = Path(self.temp.name) / "plugin"
        shutil.copytree(REPO / "plugins/kaoyan-408", self.plugin)
        self.path = self.plugin / "references/kp-408.json"
        self.data = json.loads(self.path.read_text(encoding="utf-8"))

    def validate(self):
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8", newline="\n")
        check_knowledge_points(self.plugin)

    def test_catalog_covers_sixty_points_and_four_subjects(self):
        check_knowledge_points(self.plugin)
        self.assertEqual(len(self.data["knowledgePoints"]), 60)
        counts = {}
        for point in self.data["knowledgePoints"]:
            counts[point["subject"]] = counts.get(point["subject"], 0) + 1
        self.assertEqual(counts, {"数据结构": 15, "计算机组成原理": 15, "操作系统": 15, "计算机网络": 15})

    def test_duplicate_id_with_different_content_is_rejected(self):
        duplicate = copy.deepcopy(self.data["knowledgePoints"][0])
        duplicate["name"] += "变体"
        self.data["knowledgePoints"].append(duplicate)
        with self.assertRaises(ValidationError): self.validate()

    def test_pending_year_cannot_be_verified(self):
        point = self.data["knowledgePoints"][0]
        point.update({"basisYear": "待核", "verified": True, "source": None,
                      "syllabusPath": None, "checkedAt": None})
        with self.assertRaises(ValidationError): self.validate()

    def test_pending_year_cannot_carry_a_guessed_syllabus_path(self):
        self.data["knowledgePoints"][0].update({"basisYear": "待核", "verified": False,
                      "source": None, "checkedAt": None, "syllabusPath": ["未经核对的路径"]})
        with self.assertRaises(ValidationError): self.validate()

    def verified_fixture(self):
        point = self.data["knowledgePoints"][0]
        point.update({"basisYear": "2022", "verified": True,
                      "syllabusPath": ["测试用大纲路径"], "checkedAt": "2026-10-17",
                      "source": {"title": "测试夹具，非真实核验", "publisher": "测试发布者",
                                 "reference": "https://example.edu.cn/syllabus", "locator": "测试条目",
                                 "kind": "official-repost", "mappingScope": "topic", "sha256": "0" * 64}})
        return point

    def test_complete_verified_fixture_is_structurally_valid(self):
        self.verified_fixture()
        self.validate()

    def test_verified_item_needs_source_and_locator(self):
        for field in ("source", "syllabusPath", "checkedAt"):
            with self.subTest(field=field):
                point = self.verified_fixture()
                point[field] = None
                with self.assertRaises(ValidationError): self.validate()

    def test_invalid_calendar_date_is_rejected(self):
        self.verified_fixture()["checkedAt"] = "2026-02-30"
        with self.assertRaises(ValidationError): self.validate()

    def test_verified_source_needs_explicit_provenance_kind(self):
        source = self.verified_fixture()["source"]
        del source["kind"]
        with self.assertRaises(ValidationError): self.validate()

    def test_verified_source_needs_a_document_digest(self):
        self.verified_fixture()["source"]["sha256"] = "not-a-digest"
        with self.assertRaises(ValidationError): self.validate()

    def test_year_is_required_and_must_be_year_or_pending(self):
        point = self.data["knowledgePoints"][0]
        del point["basisYear"]
        with self.assertRaises(ValidationError): self.validate()
        point["basisYear"] = "最新版"
        with self.assertRaises(ValidationError): self.validate()

    def test_textbook_chapter_field_is_rejected(self):
        self.data["knowledgePoints"][0]["textbookChapter"] = "第1章"
        with self.assertRaises(ValidationError): self.validate()

    def test_subject_prefix_mismatch_is_rejected(self):
        self.data["knowledgePoints"][0]["subject"] = "操作系统"
        with self.assertRaises(ValidationError): self.validate()

    def test_blank_name_is_rejected(self):
        self.data["knowledgePoints"][0]["name"] = "  "
        with self.assertRaises(ValidationError): self.validate()

    def test_fixture_does_not_mark_unread_sources_verified(self):
        for point in self.data["knowledgePoints"]:
            if point["basisYear"] == "待核":
                self.assertFalse(point["verified"])
                self.assertIsNone(point["source"])
                self.assertIsNone(point["syllabusPath"])

    def test_2027_third_party_mappings_keep_explicit_scope(self):
        points = self.data["knowledgePoints"]
        self.assertEqual({point["basisYear"] for point in points}, {"2027"})
        self.assertTrue(all(point["source"]["kind"] == "third-party-outline" for point in points))
        self.assertEqual(sum(point["mappingStatus"] == "direct" for point in points), 9)
        self.assertEqual(sum(point["mappingStatus"] == "upper-topic" for point in points), 51)
        self.assertTrue(all(point["source"]["sha256Scope"] == "normalized-article-text-v1" for point in points))
        self.assertTrue(all(point["knowledgeCard"] == "knowledge-cards/" + point["id"] + ".json" for point in points))
        self.assertNotIn("2025年408大纲", json.dumps(self.data, ensure_ascii=False))

    def test_two_consumer_skills_link_the_basis_contract(self):
        for skill in ("kaoyan-408-tutor", "kaoyan-error-loop-coach"):
            text = (self.plugin / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("../../references/knowledge-point-basis-contract.md", text)

    def test_acceptance_prompts_reference_existing_ids_and_are_ungraded(self):
        fixtures = json.loads((REPO / "eval/v2.7-acceptance/cases.json").read_text(encoding="utf-8"))
        ids = {point["id"] for point in self.data["knowledgePoints"]}
        self.assertEqual(len(fixtures["cases"]), 20)
        for case in fixtures["cases"]:
            self.assertEqual(case["executionStatus"], "fixture-only")
            self.assertTrue(case["prompt"].strip())
            self.assertTrue(set(case["reviewOnly"]["acceptableKnowledgeIds"]).issubset(ids))


if __name__ == "__main__":
    unittest.main()

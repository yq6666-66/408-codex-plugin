from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import release_payload
spec = importlib.util.spec_from_file_location("knowledge_cards", ROOT / "src/shared/calculation/knowledge_cards.py")
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
spec2 = importlib.util.spec_from_file_location("validate_knowledge", ROOT / "tools/validate_knowledge.py")
validator = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(validator)


class PublicKnowledgeCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.ref = self.root / "src/shared/references"
        self.cards = self.ref / "knowledge-cards"
        self.cards.mkdir(parents=True)
        self.point = {"id": "DS-ALG-001", "subject": "数据结构", "knowledgeCard": "knowledge-cards/DS-ALG-001.json", "basisYear": "2027", "verified": True, "mappingStatus": "upper-topic", "source": {"kind": "third-party-outline", "mappingScope": "upper-topic"}}
        (self.ref / "kp-408.json").write_text(json.dumps({"knowledgePoints": [self.point]}, ensure_ascii=False), encoding="utf-8")
        self.card = {"schemaVersion": "1.0", "id": "DS-ALG-001", "subject": "数据结构", "learningGoal": "理解例子", "prerequisites": ["前提"], "concept": "概念", "conditions": ["条件"], "misconceptions": [{"claim": "误解", "correction": "纠正"}], "workedExample": {"question": "原创示例", "solution": "解析 SECRET-SOLUTION"}, "selfCheck": {"question": "独立验证"}, "ruleCardIds": [], "evidence": {"mappingStatus": "详见索引", "ruleStatus": "项目推导待核", "details": "缺少外部证据"}}
        self.path = self.cards / "DS-ALG-001.json"
        self.write_card()

    def write_card(self):
        self.path.write_text(json.dumps(self.card, ensure_ascii=False), encoding="utf-8")

    def test_protected_mode_never_reads_card_or_reveals_id(self):
        for mode in ("hint", "independent", "exam"):
            result = reader.project(mode, None, self.ref)
            self.assertNotIn("SECRET-SOLUTION", json.dumps(result))
            self.assertNotIn("DS-ALG-001", json.dumps(result))
            with self.assertRaises(ValueError):
                reader.project(mode, "DS-ALG-001", self.ref)

    def test_explain_reads_only_exact_matching_card(self):
        self.assertEqual(reader.project("explain", "DS-ALG-001", self.ref)["workedExample"]["solution"], "解析 SECRET-SOLUTION")
        self.assertEqual(reader.project("explain", "DS-ALG-001", self.ref)["syllabusMapping"]["source"]["mappingScope"], "upper-topic")
        with self.assertRaises(ValueError):
            reader.project("explain", "../secret", self.ref)

    def test_core_only_projects_concept_and_preserves_default(self):
        self.card["selfCheck"]["question"] = "SECRET-SELF-CHECK"
        self.write_card()
        default = reader.project("explain", "DS-ALG-001", self.ref)
        self.assertEqual(default, reader.project("explain", "DS-ALG-001", self.ref, section="all"))
        core = reader.project("explain", "DS-ALG-001", self.ref, section="core")
        self.assertEqual(core["concept"], self.card["concept"])
        self.assertEqual(core["syllabusMapping"]["mappingStatus"], "upper-topic")
        self.assertEqual(core["evidence"], self.card["evidence"])
        self.assertNotIn("workedExample", core)
        self.assertNotIn("selfCheck", core)
        self.assertNotIn("SECRET-SOLUTION", json.dumps(core))
        self.assertNotIn("SECRET-SELF-CHECK", json.dumps(core))
        with self.assertRaises(ValueError):
            reader.project("explain", "DS-ALG-001", self.ref, section="invalid")

    def test_protected_sections_do_not_access_files(self):
        with patch.object(Path, "read_text", side_effect=AssertionError("read attempted")), \
             patch.object(Path, "resolve", side_effect=AssertionError("resolve attempted")), \
             patch.object(Path, "is_file", side_effect=AssertionError("stat attempted")), \
             patch.object(Path, "is_symlink", side_effect=AssertionError("symlink attempted")):
            for mode in ("hint", "independent", "exam"):
                for section in ("core", "all"):
                    with self.subTest(mode=mode, section=section):
                        self.assertEqual(reader.project(mode, None, self.ref, section)["status"], "details-deferred")
                        with self.assertRaises(ValueError):
                            reader.project(mode, "DS-ALG-001", self.ref, section)

    def test_coverage_and_references_reject_missing_or_mismatch(self):
        self.assertEqual(validator.validate_public_cards(self.root, [self.point], []), 1)
        self.point["knowledgeCard"] = "knowledge-cards/DS-OTHER-999.json"
        with self.assertRaises(validator.KnowledgeError):
            validator.validate_public_cards(self.root, [self.point], [])
        self.point["knowledgeCard"] = "knowledge-cards/DS-ALG-001.json"
        self.card["id"] = "DS-OTHER-999"
        self.write_card()
        with self.assertRaises(validator.KnowledgeError):
            validator.validate_public_cards(self.root, [self.point], [])

    def test_self_check_answer_cannot_leak_into_public_question(self):
        self.card["selfCheck"]["answer"] = "SECRET-SOLUTION"
        self.write_card()
        with self.assertRaises(validator.KnowledgeError):
            validator.validate_public_cards(self.root, [self.point], [])

    def test_unrelated_rule_reference_rejected(self):
        self.card["ruleCardIds"] = ["other-rule"]
        self.write_card()
        with self.assertRaises(validator.KnowledgeError):
            validator.validate_public_cards(self.root, [self.point], [{"id": "other-rule", "pointIds": ["DS-OTHER-001"]}])

    def test_card_cannot_override_index_mapping(self):
        self.card["evidence"]["mappingStatus"] = "直接主题"
        self.write_card()
        with self.assertRaises(validator.KnowledgeError):
            validator.validate_public_cards(self.root, [self.point], [])
        with self.assertRaises(ValueError):
            reader.project("explain", "DS-ALG-001", self.ref)

    def test_mapping_counts_do_not_upgrade_upper_or_missing_to_direct(self):
        points = [{"mappingStatus": "direct", "verified": True},
                  {"mappingStatus": "upper-topic", "verified": True},
                  {"mappingStatus": "not-found", "verified": False}]
        self.assertEqual(validator.mapping_counts(points),
                         {"directMappings": 1, "upperOrPartialMappings": 1, "notFoundMappings": 1})
        points[1]["mappingStatus"] = "not-found"
        self.assertEqual(validator.mapping_counts(points)["directMappings"], 1)
        self.assertEqual(validator.mapping_counts(points)["upperOrPartialMappings"], 0)
        self.assertEqual(validator.mapping_counts(points)["notFoundMappings"], 2)

    def test_release_allowlist_depends_on_manifest_version(self):
        def archive(version, names):
            path = self.root / "fixture.zip"
            with zipfile.ZipFile(path, "w") as z:
                for name in sorted(names):
                    info = release_payload.Utf8ZipInfo(name, release_payload.FIXED_ZIP_TIME)
                    info.create_system = 3
                    info.external_attr = (0o100644 << 16)
                    info.compress_type = zipfile.ZIP_STORED
                    data = json.dumps({"version": version}) if name == ".codex-plugin/plugin.json" else "fixture\n"
                    z.writestr(info, data)
            return path
        legacy = archive("2.8.0", release_payload.LEGACY_28_RELEASE_FILES)
        self.assertEqual(len(release_payload.validate_release_archive(legacy)), 60)
        current = archive("2.9.0-dev.1", release_payload.ALLOWED_RELEASE_FILES)
        self.assertEqual(len(release_payload.validate_release_archive(current)), 121)
        mismatched = archive("2.8.0", release_payload.ALLOWED_RELEASE_FILES)
        with self.assertRaises(release_payload.ValidationError):
            release_payload.validate_release_archive(mismatched)


if __name__ == "__main__":
    unittest.main()

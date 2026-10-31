"""Canonical knowledge validation must survive removal of the legacy plugin."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]


class CanonicalKnowledgeTests(unittest.TestCase):
    def setUp(self):
        script = REPO / "tools/validate_knowledge.py"
        self.assertTrue(script.is_file(), "the independent canonical knowledge gate is missing")
        spec = importlib.util.spec_from_file_location("canonical_knowledge", script)
        self.gate = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.gate)
        self.temp = tempfile.TemporaryDirectory(prefix="408-knowledge-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(REPO / "schemas", self.root / "schemas")
        self.references = self.root / "src/shared/references"
        self.references.mkdir(parents=True)
        for name in ("kp-408.json", "rule-cards.json"):
            shutil.copyfile(REPO / "src/shared/references" / name, self.references / name)
        shutil.copytree(REPO / "src/shared/references/knowledge-cards", self.references / "knowledge-cards")
        self.points = json.loads((self.references / "kp-408.json").read_bytes())
        self.cards = json.loads((self.references / "rule-cards.json").read_bytes())

    def validate(self):
        for name, data in (("kp-408.json", self.points), ("rule-cards.json", self.cards)):
            (self.references / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return self.gate.validate_knowledge(self.root)

    def reject(self):
        with self.assertRaises(self.gate.KnowledgeError):
            self.validate()

    def test_canonical_source_without_any_legacy_directories(self):
        result = self.validate()
        self.assertTrue(result["valid"])
        self.assertEqual((result["knowledgePoints"], result["ruleCards"]), (60, 8))
        self.assertEqual((result["verifiedMappings"], result["pendingMappings"]), (60, 0))
        self.assertFalse((self.root / "plugins").exists())
        self.assertFalse((self.root / "scripts").exists())

    def test_verified_mapping_requires_year_and_evidence(self):
        original = copy.deepcopy(self.points["knowledgePoints"][0])
        for field, value in (("basisYear", "待核"), ("source", None),
                             ("syllabusPath", None), ("checkedAt", None)):
            with self.subTest(field=field):
                self.points["knowledgePoints"][0] = {**original, field: value}
                self.reject()

    def test_pending_mapping_cannot_contain_guessed_evidence(self):
        point = self.points["knowledgePoints"][0]
        point.update({"basisYear": "待核", "verified": False, "source": None,
                      "syllabusPath": None, "checkedAt": None, "mappingStatus": "not-found",
                      "mappingNote": "当前测试夹具尚无匹配"})
        self.validate()
        verified_source = copy.deepcopy(self.points["knowledgePoints"][1]["source"])
        for field, value in (("verified", True), ("syllabusPath", ["guessed"]),
                             ("source", verified_source),
                             ("checkedAt", "2026-10-22")):
            with self.subTest(field=field):
                old = point[field]
                point[field] = value
                self.reject()
                point[field] = old

    def test_verified_source_fields_and_url_are_checked(self):
        point = self.points["knowledgePoints"][0]
        original = copy.deepcopy(point["source"])
        for field in original:
            with self.subTest(missing=field):
                point["source"] = {k: v for k, v in original.items() if k != field}
                self.reject()
        for field, value in (("locator", "  "), ("sha256", "not-a-digest"),
                             ("reference", "http://example.edu/source"), ("kind", "project-summary"),
                             ("mappingScope", "formula-proof")):
            with self.subTest(field=field):
                point["source"] = {**original, field: value}
                self.reject()

    def test_dates_have_calendar_semantics(self):
        self.points["knowledgePoints"][0]["checkedAt"] = "2026-02-30"
        self.reject()

    def test_missing_year_unknown_fields_and_blank_names_are_rejected(self):
        original = copy.deepcopy(self.points["knowledgePoints"][0])
        for mutation in ({k: v for k, v in original.items() if k != "basisYear"},
                         {**original, "basisYear": "最新版"}, {**original, "name": "  "},
                         {**original, "textbookChapter": "invented chapter"}):
            self.points["knowledgePoints"][0] = mutation
            self.reject()

    def test_subject_prefix_and_four_subject_coverage(self):
        self.points["knowledgePoints"][0]["subject"] = "操作系统"
        self.reject()
        self.points["knowledgePoints"][0]["subject"] = "数据结构"
        self.points["knowledgePoints"] = [p for p in self.points["knowledgePoints"] if p["subject"] != "计算机网络"]
        self.reject()

    def test_duplicate_point_ids_with_different_content(self):
        self.points["knowledgePoints"].append({**self.points["knowledgePoints"][0], "name": "duplicate"})
        self.reject()

    def test_rule_needs_nonempty_conditions_rule_and_name(self):
        original = copy.deepcopy(self.cards["cards"][0])
        for field, value in (("conditions", []), ("conditions", [" "]), ("rule", " "), ("name", "")):
            with self.subTest(field=field, value=value):
                self.cards["cards"][0] = {**original, field: value}
                self.reject()

    def test_project_rule_cannot_claim_verified_external_origin(self):
        original = copy.deepcopy(self.cards["cards"][0]["source"])
        for field, value in (("kind", "exam-authority"), ("verification", "verified"),
                             ("locator", "rule-cards.json#other"), ("title", " "),
                             ("title", "教材原文"), ("title", "官方考试大纲")):
            with self.subTest(field=field, value=value):
                self.cards["cards"][0]["source"] = {**original, field: value}
                self.reject()

    def test_rule_ids_and_point_references_are_unique_and_resolve(self):
        original = copy.deepcopy(self.cards)
        self.cards["cards"].append({**self.cards["cards"][0], "name": "duplicate"})
        self.reject()
        self.cards = copy.deepcopy(original)
        self.cards["cards"][0]["pointIds"] = ["DS-UNKNOWN-999"]
        self.reject()
        self.cards = copy.deepcopy(original)
        point = self.cards["cards"][0]["pointIds"][0]
        self.cards["cards"][0]["pointIds"] = [point, point]
        self.reject()

    def external_reference(self):
        return {
            "kind": "textbook-author", "title": "Author material", "publisher": "Original author",
            "url": "https://example.edu/author-material", "locator": "Section 1, paragraphs 1-2",
            "checkedAt": "2026-10-26", "verification": "verified",
            "supports": ["The stated core rule"], "limitations": ["Project tie-breaking is not covered"],
        }

    def make_partially_sourced_card(self):
        for existing in self.cards["cards"]:
            existing["source"]["verification"] = "project-reviewed-external-pending"
            existing.pop("externalReferences", None)
        card = self.cards["cards"][0]
        card["source"]["verification"] = "project-reviewed-external-partial"
        card["externalReferences"] = [self.external_reference()]
        return card

    def test_partial_external_support_preserves_project_identity_and_mapping_counts(self):
        card = self.make_partially_sourced_card()
        result = self.validate()
        self.assertEqual(card["source"]["kind"], "project-summary")
        self.assertEqual((result["verifiedMappings"], result["pendingMappings"]), (60, 0))
        self.assertEqual(result["externallySupportedRuleCards"], 1)

    def test_partial_rule_needs_at_least_one_actual_reference(self):
        card = self.make_partially_sourced_card()
        for value in ([], None):
            with self.subTest(value=value):
                card["externalReferences"] = value
                self.reject()
        del card["externalReferences"]
        self.reject()

    def test_pending_legacy_rule_remains_compatible_without_verified_references(self):
        for existing in self.cards["cards"]:
            existing["source"]["verification"] = "project-reviewed-external-pending"
            existing.pop("externalReferences", None)
        self.assertTrue(self.validate()["valid"])
        card = self.cards["cards"][0]
        card["externalReferences"] = []
        self.assertTrue(self.validate()["valid"])
        card["externalReferences"] = [self.external_reference()]
        self.reject()

    def test_external_reference_requires_readable_provenance_scope_and_limitations(self):
        card = self.make_partially_sourced_card()
        original = self.external_reference()
        for field in original:
            with self.subTest(missing=field):
                card["externalReferences"] = [{k: v for k, v in original.items() if k != field}]
                self.reject()
        for field, value in (("url", "http://example.edu/insecure"), ("locator", "  "),
                             ("supports", []), ("supports", [" "]), ("limitations", []),
                             ("checkedAt", "2026-02-30"), ("verification", "pending"),
                             ("kind", "exam-authority")):
            with self.subTest(field=field):
                card["externalReferences"] = [{**original, field: value}]
                self.reject()

    def test_rule_reference_cannot_smuggle_in_annual_syllabus_claims(self):
        card = self.make_partially_sourced_card()
        for field, value in (("basisYear", "2027"), ("syllabusPath", ["guessed"]),
                             ("mappingScope", "formula-proof")):
            with self.subTest(field=field):
                card["externalReferences"] = [{**self.external_reference(), field: value}]
                self.reject()
    def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected(self):
        path = self.references / "rule-cards.json"
        for text in ('{"schemaVersion":"1.0","schemaVersion":"2.0","cards":[]}',
                     '{"schemaVersion":"1.0","cards":[],"extra":NaN}'):
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(self.gate.KnowledgeError):
                self.gate.validate_knowledge(self.root)

    def test_invalid_schema_and_external_reference_fail_closed(self):
        path = self.root / "schemas/kp-408.schema.json"
        for schema in ({"type": "unknown-type"}, {"$ref": "https://example.invalid/unread-schema"}):
            path.write_text(json.dumps(schema), encoding="utf-8")
            with patch("socket.getaddrinfo", side_effect=AssertionError("unexpected DNS")) as dns, \
                    patch("socket.socket.connect", side_effect=AssertionError("unexpected network")) as connect:
                with self.assertRaises(self.gate.KnowledgeError):
                    self.gate.validate_knowledge(self.root)
                dns.assert_not_called()
                connect.assert_not_called()

    def test_cli_runs_from_an_unrelated_directory_and_does_not_write(self):
        tools = self.root / "tools"
        tools.mkdir()
        shutil.copyfile(REPO / "tools/validate_knowledge.py", tools / "validate_knowledge.py")
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = subprocess.run([sys.executable, "-B", str(tools / "validate_knowledge.py")],
                                cwd=unrelated, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["valid"])
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        (self.references / "kp-408.json").write_text("{}", encoding="utf-8")
        result = subprocess.run([sys.executable, "-B", str(tools / "validate_knowledge.py")],
                                cwd=unrelated, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertIn("ERROR:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()

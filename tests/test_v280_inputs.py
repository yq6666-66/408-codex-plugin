from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SUITE = REPO / "eval" / "v2.8-acceptance"
_spec = importlib.util.spec_from_file_location("kaoyan408_v280_export_inputs", SUITE / "export_inputs.py")
if _spec is None or _spec.loader is None:
    raise ImportError("cannot load the v2.8 input exporter")
_exporter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_exporter)
export_case = _exporter.export_case


class InputProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="408-input-projection-test-")
        self.addCleanup(self.temp.cleanup)
        self.material_root = Path(self.temp.name) / "materials"
        self.material_root.mkdir()
        (self.material_root / "learner-note.md").write_text("虚构用户材料", encoding="utf-8")
        self.catalog = {"cases": [{"id": "sample", "turns": ["先解释这个概念。", "继续给一个例子。"],
                                  "materials": ["learner-note.md"],
                                  "skill": "kaoyan-408-tutor", "answer": "grading-answer-sentinel",
                                  "reviewOnly": {"expectedPrimary": "kaoyan-408-tutor", "id": "OS-MEM-001"}}]}

    def output(self):
        return export_case(self.catalog, "sample", material_root=self.material_root)

    def test_only_natural_messages_and_material_paths_survive(self):
        before = copy.deepcopy(self.catalog)
        result = self.output()
        self.assertEqual(set(result), {"messages", "materials"})
        self.assertEqual(result["messages"], [{"role": "user", "content": t}
                                               for t in self.catalog["cases"][0]["turns"]])
        self.assertEqual(result["materials"], [{"path": "materials/learner-note.md"}])
        rendered = json.dumps(result)
        for secret in ("reviewOnly", "expectedPrimary", "kaoyan-408-tutor", "OS-MEM-001", "grading-answer-sentinel"):
            self.assertNotIn(secret, rendered)
        self.assertEqual(self.catalog, before)

    def test_unknown_or_duplicate_case_id_fails(self):
        with self.assertRaisesRegex(ValueError, "unknown"):
            export_case(self.catalog, "missing", material_root=self.material_root)
        self.catalog["cases"].append(copy.deepcopy(self.catalog["cases"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            self.output()

    def test_prompt_skill_or_knowledge_id_is_rejected_instead_of_silently_rewritten(self):
        for prompt in ("请使用 kaoyan-408-tutor", "评分要求匹配 OS-MEM-001", "请用kaoyan-408-tutor回答", "依据OS-MEM-001讲解"):
            self.catalog["cases"][0]["turns"] = [prompt]
            with self.assertRaisesRegex(ValueError, "must not contain"):
                self.output()

    def test_invalid_or_missing_material_paths_fail_closed(self):
        for name in ("../outside.md", "notes/../outside.md", "C:/private.md", "notes\\private.md", "missing.md"):
            self.catalog["cases"][0]["materials"] = [name]
            with self.subTest(name=name), self.assertRaises((ValueError, OSError)):
                self.output()

    def test_runner_only_setup_is_never_exported_as_material(self):
        for name in ("notes-host-fixture.json", "obsidian-brain.template.json"):
            (self.material_root / name).write_text("{}", encoding="utf-8")
            self.catalog["cases"][0]["materials"] = [name]
            with self.assertRaisesRegex(ValueError, "runner-only"):
                self.output()

    def test_symlink_material_is_rejected_when_platform_can_create_it(self):
        link = self.material_root / "linked.md"
        try:
            link.symlink_to(self.material_root / "learner-note.md")
        except OSError:
            self.skipTest("symlink creation unavailable on this host")
        self.catalog["cases"][0]["materials"] = ["linked.md"]
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.output()

    def test_cli_stdout_contains_only_json_projection_and_failure_has_no_stdout(self):
        path = Path(self.temp.name) / "cases.json"
        path.write_text(json.dumps(self.catalog, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run([sys.executable, "-B", str(SUITE / "export_inputs.py"), "sample", "--catalog", str(path)],
                                capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
        self.assertEqual(result.stderr, b"")
        self.assertEqual(json.loads(result.stdout), self.output())
        failed = subprocess.run([sys.executable, "-B", str(SUITE / "export_inputs.py"), "missing", "--catalog", str(path)],
                                capture_output=True, check=False)
        self.assertEqual(failed.returncode, 2)
        self.assertEqual(failed.stdout, b"")

    def test_real_notes_case_exports_only_vault_not_runner_setup(self):
        catalog = json.loads((SUITE / "cases.json").read_text(encoding="utf-8"))
        for case_id in ("G09-A", "G09-B"):
            result = export_case(catalog, case_id, material_root=SUITE / "materials")
            self.assertEqual(result["materials"], [{"path": "materials/notes-vault"}])

    def test_catalog_preserves_pairs_review_alignment_and_exportable_inputs(self):
        catalog = json.loads((SUITE / "cases.json").read_text(encoding="utf-8"))
        groups = {group["id"] for group in catalog["groups"]}
        self.assertGreaterEqual(len(groups), 10)
        cases = catalog["cases"]
        self.assertEqual(len({case["id"] for case in cases}), len(cases))
        skills = {path.name for path in (REPO / "plugins/kaoyan-408/skills").iterdir() if path.is_dir()}
        pairs = {group: [] for group in groups}
        for case in cases:
            self.assertEqual(case["executionStatus"], "fixture-only")
            self.assertIn(case["environmentProfile"], catalog["environmentProfiles"])
            pairs[case["group"]].append(case["arm"])
            reviews = case["reviewOnly"]["perTurn"]
            self.assertEqual(len(reviews), len(case["turns"]))
            for review in reviews:
                self.assertIn(review["expectedPrimary"], skills)
                self.assertTrue(set(review["allowedSecondarySkills"]) <= skills)
            exported = export_case(catalog, case["id"], material_root=SUITE / "materials")
            self.assertEqual(len(exported["messages"]), len(reviews))
        for group, arms in pairs.items():
            with self.subTest(group=group):
                self.assertCountEqual(arms, ["A", "B"])


if __name__ == "__main__":
    unittest.main()

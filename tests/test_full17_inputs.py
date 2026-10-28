"""Input projection tests for the prepared 17-Skill extension."""
from copy import deepcopy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

HERE=Path(__file__).resolve().parent
if (HERE/"export_inputs.py").is_file():
    DATA=HERE
else:
    DATA=HERE.parent/"eval/v2.8-acceptance/full17"
spec=importlib.util.spec_from_file_location("full17_input_exporter",DATA/"export_inputs.py")
exporter=importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)

class Full17InputTests(unittest.TestCase):
    def setUp(self):
        self.catalog=json.loads((DATA/"natural-cases.json").read_text(encoding="utf-8"))

    def project(self,catalog=None,case_id=None):
        catalog=self.catalog if catalog is None else catalog
        return exporter.export_case(catalog,case_id or catalog["cases"][0]["id"],material_root=DATA/"materials")

    def test_inventory_and_turn_grading_align(self):
        self.assertEqual(len(self.catalog["groups"]),8)
        self.assertEqual(len(self.catalog["cases"]),16)
        self.assertEqual(sum(len(case["turns"]) for case in self.catalog["cases"]),20)
        self.assertEqual(len({case["id"] for case in self.catalog["cases"]}),16)
        for case in self.catalog["cases"]:
            self.assertEqual(len(case["turns"]),len(case["reviewOnly"]["perTurn"]))
            self.assertEqual(case["executionStatus"],"fixture-only")

    def test_all_cases_export_only_natural_messages_and_materials(self):
        for case in self.catalog["cases"]:
            with self.subTest(case=case["id"]):
                output=self.project(case_id=case["id"])
                self.assertEqual(set(output),{"messages","materials"})
                self.assertEqual(output["messages"],[{"role":"user","content":turn} for turn in case["turns"]])
                encoded=json.dumps(output,ensure_ascii=False)
                for field in ("expectedPrimary","reviewOnly","runnerOnlySetup","executionStatus","allowedSecondarySkills"):
                    self.assertNotIn(field,encoded)

    def test_all_three_new_skill_ids_are_rejected(self):
        for skill in ("408-error-diagnosis","408-concept-followup","408-calculation-check"):
            with self.subTest(skill=skill):
                catalog=deepcopy(self.catalog)
                catalog["cases"][0]["turns"][0]+=" 使用 "+skill
                with self.assertRaisesRegex(ValueError,"new Skill IDs"):
                    self.project(catalog)

    def test_existing_skill_and_knowledge_id_rejection_is_retained(self):
        for token in ("kaoyan-408-tutor","OS-MEM-001"):
            with self.subTest(token=token):
                catalog=deepcopy(self.catalog)
                catalog["cases"][0]["turns"][0]+=" "+token
                with self.assertRaises(ValueError):
                    self.project(catalog)

    def test_grading_and_setup_values_never_leak(self):
        catalog=deepcopy(self.catalog)
        catalog["cases"][0]["reviewOnly"]["perTurn"][0]["must"].append("PRIVATE_SCORING_SENTINEL")
        catalog["cases"][0]["runnerOnlySetup"]={"sentinel":"PRIVATE_SETUP_SENTINEL"}
        catalog["cases"][0]["expectedPrimary"]="PRIVATE_ROUTE_SENTINEL"
        encoded=json.dumps(self.project(catalog))
        self.assertNotIn("PRIVATE_",encoded)

    def test_duplicate_ids_and_runner_only_materials_are_rejected(self):
        catalog=deepcopy(self.catalog)
        catalog["cases"].append(deepcopy(catalog["cases"][0]))
        with self.assertRaises(ValueError):self.project(catalog)
        catalog=deepcopy(self.catalog)
        catalog["cases"][0]["materials"]=["notes-host-fixture.json"]
        with self.assertRaises(ValueError):self.project(catalog)

    def test_cli_emits_utf8_json_even_under_legacy_windows_encoding(self):
        environment=os.environ.copy()
        environment["PYTHONUTF8"]="0"
        environment["PYTHONIOENCODING"]="cp936"
        result=subprocess.run([sys.executable,"-B",str(DATA/"export_inputs.py"),"N17-08-A"],
                              capture_output=True,check=False,env=environment)
        self.assertEqual(result.returncode,0,result.stderr)
        output=json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(set(output),{"messages","materials"})
        case=next(c for c in self.catalog["cases"] if c["id"]=="N17-08-A")
        self.assertEqual(output["messages"][0]["content"],case["turns"][0])
        failed=subprocess.run([sys.executable,"-B",str(DATA/"export_inputs.py"),"missing"],
                              capture_output=True,check=False,env=environment)
        self.assertEqual(failed.returncode,2)
        self.assertEqual(failed.stdout,b"")
        failed.stderr.decode("utf-8")

    def test_baseline_derivation_changes_no_natural_inputs(self):
        overrides=json.loads((DATA/"baseline-route-overrides.json").read_text(encoding="utf-8"))
        derived=json.loads((DATA/"baseline-derived-cases.json").read_text(encoding="utf-8"))
        root=next(parent for parent in DATA.parents if (parent/"eval/v2.8-acceptance/cases.json").is_file())
        raw=(root/"eval/v2.8-acceptance/cases.json").read_bytes()
        canonical=raw.replace(b"\r\n",b"\n")
        self.assertNotIn(b"\r",canonical)
        self.assertEqual(hashlib.sha256(canonical).hexdigest(),overrides["sourceCatalogCanonicalSha256"])
        self.assertEqual(hashlib.sha256(canonical.replace(b"\n",b"\r\n")).hexdigest(),overrides["sourceCatalogSha256"])
        self.assertIn(hashlib.sha256(raw).hexdigest(),{overrides["sourceCatalogSha256"],overrides["sourceCatalogCanonicalSha256"]})
        original=json.loads(raw)
        self.assertEqual(len(original["cases"]),len(derived["cases"]))
        expected={(item["caseId"],item["turnIndex"]):item for item in overrides["overrides"]}
        changed=[]
        for before,after in zip(original["cases"],derived["cases"]):
            self.assertEqual(before["id"],after["id"])
            self.assertEqual(before["turns"],after["turns"])
            self.assertEqual(before["materials"],after["materials"])
            for index,(old,new) in enumerate(zip(before["reviewOnly"]["perTurn"],after["reviewOnly"]["perTurn"])):
                old,new=deepcopy(old),deepcopy(new)
                route=new.pop("expectedPrimary")
                previous=old.pop("expectedPrimary")
                self.assertEqual(old,new)
                if route!=previous:
                    key=(before["id"],index)
                    self.assertEqual(route,expected[key]["expectedPrimary"])
                    self.assertEqual(previous,expected[key]["previousExpectedPrimary"])
                    changed.append(key)
        self.assertEqual(set(changed),set(expected))

if __name__=="__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SOURCE = REPO / "src" / "shared"
spec = importlib.util.spec_from_file_location("v300_simulator", SOURCE / "calculation" / "study_simulator.py")
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)


class CandidateKnowledgeTests(unittest.TestCase):
    def test_all_60_points_preserve_2027_third_party_source_scope(self):
        points = json.loads((SOURCE / "references" / "kp-408.json").read_text(encoding="utf-8"))["knowledgePoints"]
        self.assertEqual(len(points), 60)
        self.assertEqual(len({p["id"] for p in points}), 60)
        self.assertEqual(sorted(sum(p["subject"] == subject for p in points) for subject in
                                ("数据结构", "计算机组成原理", "操作系统", "计算机网络")), [15] * 4)
        self.assertEqual(sum(p["mappingStatus"] == "direct" for p in points), 9)
        self.assertEqual(sum(p["mappingStatus"] == "upper-topic" for p in points), 51)
        for point in points:
            with self.subTest(point=point["id"]):
                self.assertTrue(point["verified"])
                self.assertEqual(point["basisYear"], "2027")
                self.assertEqual(point["source"]["kind"], "third-party-outline")
                self.assertEqual(point["source"]["sha256Scope"], "normalized-article-text-v1")
                self.assertEqual(point["source"]["mappingScope"],
                                 "topic" if point["mappingStatus"] == "direct" else "upper-topic")
                self.assertTrue(point["source"]["locator"])
                self.assertTrue(point["mappingNote"])
                self.assertTrue(point["checkedAt"])

    def test_rule_cards_resolve_internal_points_and_keep_external_scope_explicit(self):
        directory = SOURCE / "references"
        points = {p["id"] for p in json.loads((directory / "kp-408.json").read_text(encoding="utf-8"))["knowledgePoints"]}
        cards = json.loads((directory / "rule-cards.json").read_text(encoding="utf-8"))["cards"]
        self.assertEqual(len(cards), 8)
        self.assertEqual(len({c["id"] for c in cards}), len(cards))
        for card in cards:
            with self.subTest(card=card["id"]):
                self.assertTrue(card["pointIds"])
                self.assertLessEqual(set(card["pointIds"]), points)
                self.assertTrue(card["rule"])
                self.assertTrue(card["conditions"])
                self.assertEqual(card["source"]["kind"], "project-summary")
                self.assertIn(card["source"]["verification"], {
                    "project-reviewed-external-pending", "project-reviewed-external-partial",
                })
                if card["source"]["verification"] == "project-reviewed-external-partial":
                    self.assertTrue(card.get("externalReferences"))
                    for reference in card["externalReferences"]:
                        self.assertEqual(reference["verification"], "verified")
                        self.assertTrue(reference["supports"])
                        self.assertTrue(reference["limitations"])
                self.assertEqual(card["source"]["locator"], "rule-cards.json#" + card["id"])


class CandidateSkillContractTests(unittest.TestCase):
    def test_concept_examples_must_be_labeled_original_not_just_implicitly_example(self):
        concept = (REPO / "src" / "skills" / "408-concept-followup" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("必须明写“原创示例（非用户题面）”", concept)
        self.assertIn("不要只用“例如”暗示", concept)

    def test_calculation_answers_require_a_compact_knowledge_basis_line(self):
        calculation = (REPO / "src" / "skills" / "408-calculation-check" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("每个计算答复结尾必须出现一行“【知识点依据】”", calculation)
        self.assertIn("即使用户只问数值、单位或复核状态也不得省略", calculation)
        self.assertIn("规则来源与年度映射不可互相代替", calculation)
        self.assertIn("除单步提示且精确依据会泄题的情况外", calculation)


class CandidateCalculationTests(unittest.TestCase):
    def test_cache_two_independent_field_decompositions_and_address_reassembly(self):
        for width, block, lines, expected in ((16, 64, 256, (2, 8, 6)), (32, 16, 256, (20, 8, 4))):
            address = (1 << width) - 1
            document = sim.simulate_cache(width, block, lines, "direct", [address])
            self.assertEqual(tuple(document["params"][k] for k in ("tagBits", "indexBits", "offsetBits")), expected)
            step = document["steps"][0]
            self.assertEqual(((step["tag"] * lines + step["index"]) * block + step["offset"]), address)

    def test_associative_replacement_uses_recency_after_hit(self):
        document = sim.simulate_cache(8, 4, 2, "associative", [0, 4, 0, 8])
        self.assertEqual([s["event"] for s in document["steps"]], ["miss", "miss", "hit", "miss"])
        self.assertEqual(document["steps"][-1]["evictedBlock"], 1)
        self.assertEqual(document["params"]["indexBits"], 0)

    def test_fifo_classic_and_hit_order_distinguishes_lru(self):
        fifo = sim.simulate_fifo(3, [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5], [])
        self.assertEqual((fifo["summary"]["faults"], fifo["summary"]["hits"]), (9, 3))
        self.assertEqual(fifo["steps"][-1]["frames"], [5, 3, 4])
        for function, expected in ((sim.simulate_fifo, 7), (sim.simulate_lru, 8)):
            document = function(2, [7, 8, 7, 9], [])
            self.assertEqual(document["steps"][-1]["evicted"], expected)

    def test_nonempty_initial_order_is_explicit(self):
        document = sim.simulate_fifo(2, [6], [4, 2])
        self.assertEqual(document["steps"][0]["evicted"], 4)
        self.assertEqual(document["steps"][0]["frames"], [6, 2])
        with self.assertRaises(ValueError):
            sim.simulate_fifo(2, [0], [4, 4])

    def test_scheduling_tie_and_quantum_boundary_conventions(self):
        fcfs = sim.simulate_fcfs(sim.parse_processes("B:0:2,A:0:1"))
        self.assertEqual([(s["process"], s["timeStart"], s["timeEnd"]) for s in fcfs["steps"]],
                         [("A", 0, 1), ("B", 1, 3)])
        rr = sim.simulate_rr(sim.parse_processes("P1:0:4,P2:2:1"), 2)
        self.assertEqual([(s["process"], s["timeStart"], s["timeEnd"]) for s in rr["steps"] if s["event"] == "run"],
                         [("P1", 0, 2), ("P2", 2, 3), ("P1", 3, 5)])
        self.assertEqual({p["name"]: p["completion"] for p in rr["summary"]["processes"]}, {"P1": 5, "P2": 3})

    def test_user_banned_script_gets_explicit_manual_fallback_status(self):
        source = (REPO / "src" / "skills" / "408-calculation-check" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("用户禁止运行脚本时不调用", source)
        self.assertIn("本题脚本/模拟器被禁用", source)
        self.assertIn("以下是人工复核", source)

    def test_standalone_script_has_no_repository_or_working_directory_dependency(self):
        with tempfile.TemporaryDirectory(prefix="408-v300-standalone-") as temporary:
            root = Path(temporary)
            script = root / "study_simulator.py"
            shutil.copy2(SOURCE / "calculation" / script.name, script)
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            result = subprocess.run([sys.executable, "-B", str(script), "fifo", "--frames", "3", "--references",
                                     "1,2,3,4,1,2,5,1,2,3,4,5"], cwd=root, capture_output=True,
                                    env={**os.environ, "PYTHONUTF8": "1"}, check=False, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["summary"]["faults"], 9)
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)


if __name__ == "__main__":
    unittest.main()

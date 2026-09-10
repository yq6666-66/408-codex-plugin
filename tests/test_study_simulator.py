from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import study_simulator as sim  # noqa: E402


class CacheSimulatorTests(unittest.TestCase):
    def test_address_split_known_values(self) -> None:
        document = sim.simulate_cache(16, 64, 256, "direct", [0, 65535])
        params = document["params"]
        self.assertEqual(params["offsetBits"], 6)
        self.assertEqual(params["indexBits"], 8)
        self.assertEqual(params["tagBits"], 2)
        self.assertEqual(params["maxAddress"], 65535)
        first = document["steps"][0]
        self.assertEqual((first["tag"], first["index"], first["offset"]), (0, 0, 0))
        last = document["steps"][1]
        self.assertEqual((last["tag"], last["index"], last["offset"]), (3, 255, 63))
        self.assertEqual(last["binary"], "1" * 16)
        # split reassembles to the address
        self.assertEqual(int(last["split"]["tag"] + last["split"]["index"] + last["split"]["offset"], 2), 65535)

    def test_hit_and_miss_sequence(self) -> None:
        # blocks 0 and 1 are distinct lines; revisiting block 0 hits.
        document = sim.simulate_cache(16, 64, 256, "direct", [0, 64, 0])
        events = [step["event"] for step in document["steps"]]
        self.assertEqual(events, ["miss", "miss", "hit"])

    def test_direct_mapping_conflict_and_boundary(self) -> None:
        # 256-line cache, 64B blocks: addresses 0 and 16384 map to index 0 with tags 0 and 1.
        document = sim.simulate_cache(16, 64, 256, "direct", [0, 16384, 0])
        self.assertEqual([step["event"] for step in document["steps"]], ["miss", "miss", "miss"])
        self.assertEqual(document["steps"][1]["index"], 0)
        self.assertEqual(document["steps"][1]["tag"], 1)

    def test_fully_associative_has_no_index(self) -> None:
        document = sim.simulate_cache(16, 64, 256, "associative", [0, 64, 0])
        self.assertEqual([step["event"] for step in document["steps"]], ["miss", "miss", "hit"])
        self.assertIsNone(document["steps"][0]["index"])

    def test_out_of_range_address_is_rejected(self) -> None:
        with self.assertRaisesRegex(sim.SimulatorError, "exceeds"):
            sim.simulate_cache(16, 64, 256, "direct", [1 << 16])

    def test_non_power_of_two_is_rejected(self) -> None:
        with self.assertRaisesRegex(sim.SimulatorError, "powers of two"):
            sim.simulate_cache(16, 60, 256, "direct", [0])


class ReplacementSimulatorTests(unittest.TestCase):
    def test_fifo_belady_three_then_four_frames(self) -> None:
        references = [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5]
        three = sim.simulate_fifo(3, references, [])
        four = sim.simulate_fifo(4, references, [])
        self.assertEqual(three["summary"]["faults"], 9)
        self.assertEqual(four["summary"]["faults"], 10)

    def test_lru_classic_reference_string(self) -> None:
        references = [7, 0, 1, 2, 0, 3, 0, 4, 2, 3, 0, 3, 2, 1, 2, 0, 1, 7, 0, 1]
        self.assertEqual(sim.simulate_lru(3, references, [])["summary"]["faults"], 12)
        self.assertEqual(sim.simulate_fifo(3, references, [])["summary"]["faults"], 15)

    def test_lru_protects_recently_used_page(self) -> None:
        document = sim.simulate_lru(3, [1, 2, 3, 1, 4], [])
        faults = [step for step in document["steps"] if step["event"] == "fault"]
        self.assertEqual(len(faults), 4)  # 1,2,3 load; 1 hits; 4 faults
        self.assertEqual(faults[-1]["evicted"], 2)  # LRU evicts page 2, not recently-used page 1

    def test_fifo_evicts_oldest_loaded_page(self) -> None:
        document = sim.simulate_fifo(3, [1, 2, 3, 1, 4], [])
        self.assertEqual(document["steps"][4]["evicted"], 1)

    def test_preloaded_initial_frames(self) -> None:
        document = sim.simulate_fifo(3, [1, 3, 1, 4], [1, 2])
        events = [step["event"] for step in document["steps"]]
        self.assertEqual(events, ["hit", "fault", "hit", "fault"])
        self.assertEqual(document["steps"][3]["frames"], [4, 2, 3])
        self.assertEqual(document["steps"][3]["evicted"], 1)

    def test_step_state_changes_are_reported(self) -> None:
        document = sim.simulate_lru(3, [1, 2], [])
        self.assertIn("loaded into empty frame", document["steps"][0]["stateChange"])


class FcfsSimulatorTests(unittest.TestCase):
    def test_classic_three_processes(self) -> None:
        document = sim.simulate_fcfs(sim.parse_processes("P1:0:24,P2:0:3,P3:0:3"))
        by_name = {p["name"]: p for p in document["summary"]["processes"]}
        self.assertEqual(by_name["P1"]["completion"], 24)
        self.assertEqual(by_name["P2"]["completion"], 27)
        self.assertEqual(by_name["P3"]["completion"], 30)
        self.assertEqual(by_name["P2"]["turnaround"], 27)
        self.assertEqual(by_name["P2"]["waiting"], 24)
        self.assertEqual(document["summary"]["averageWaiting"], 17.0)

    def test_cpu_idle_before_first_arrival(self) -> None:
        document = sim.simulate_fcfs(sim.parse_processes("P1:2:5"))
        self.assertEqual(document["steps"][0]["event"], "idle")
        self.assertEqual((document["steps"][0]["timeStart"], document["steps"][0]["timeEnd"]), (0, 2))
        self.assertEqual(document["summary"]["processes"][0]["completion"], 7)

    def test_simultaneous_arrivals_ordered_by_name(self) -> None:
        document = sim.simulate_fcfs(sim.parse_processes("PB:0:2,PA:0:2"))
        self.assertEqual(document["steps"][0]["process"], "PA")


class RrSimulatorTests(unittest.TestCase):
    def test_classic_quantum_four(self) -> None:
        document = sim.simulate_rr(sim.parse_processes("P1:0:24,P2:0:3,P3:0:3"), 4)
        by_name = {p["name"]: p for p in document["summary"]["processes"]}
        self.assertEqual(by_name["P1"]["completion"], 30)
        self.assertEqual(by_name["P2"]["completion"], 7)
        self.assertEqual(by_name["P3"]["completion"], 10)
        self.assertEqual(by_name["P1"]["turnaround"], 30)
        self.assertEqual(by_name["P1"]["waiting"], 6)
        self.assertEqual(by_name["P3"]["waiting"], 7)
        self.assertEqual(document["summary"]["averageWaiting"], round(17 / 3, 4))

    def test_arrival_exactly_at_quantum_boundary_enters_first(self) -> None:
        document = sim.simulate_rr(sim.parse_processes("P1:0:8,P2:4:2"), 4)
        runs = [step for step in document["steps"] if step["event"] == "run"]
        self.assertEqual(
            [(run["process"], run["timeStart"], run["timeEnd"]) for run in runs],
            [("P1", 0, 4), ("P2", 4, 6), ("P1", 6, 10)],
        )

    def test_quantum_equal_to_burst_completes_without_requeue(self) -> None:
        document = sim.simulate_rr(sim.parse_processes("P1:0:4"), 4)
        runs = [step for step in document["steps"] if step["event"] == "run"]
        self.assertEqual(len(runs), 1)
        self.assertIn("completes", runs[0]["stateChange"])

    def test_idle_gap_between_bursts(self) -> None:
        document = sim.simulate_rr(sim.parse_processes("P1:0:2,P2:5:1"), 2)
        self.assertTrue(any(step["event"] == "idle" for step in document["steps"]))
        by_name = {p["name"]: p for p in document["summary"]["processes"]}
        self.assertEqual(by_name["P2"]["completion"], 6)


class HtmlOutputTests(unittest.TestCase):
    def test_html_contains_navigation_and_steps(self) -> None:
        import tempfile

        document = sim.simulate_fifo(2, [1, 2, 1], [])
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "demo.html"
            sim.write_html(document, path)
            payload = path.read_text(encoding="utf-8")
        self.assertIn("前一步", payload)
        self.assertIn("后一步", payload)
        self.assertIn("stateChange", payload)
        self.assertIn('"algorithm": "fifo"', payload)


class CliTests(unittest.TestCase):
    def run_cli(self, *arguments: str) -> tuple[int, str, str]:
        import subprocess

        import os

        env = os.environ.copy()
        env.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        result = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "study_simulator.py"), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr

    def test_cli_fifo_known_answer(self) -> None:
        code, stdout, stderr = self.run_cli(
            "fifo", "--frames", "3", "--references", "1,2,3,4,1,2,5,1,2,3,4,5"
        )
        self.assertEqual(code, 0, stderr)
        self.assertEqual(json.loads(stdout)["summary"]["faults"], 9)

    def test_cli_rejects_bad_process_spec(self) -> None:
        code, _, stderr = self.run_cli("fcfs", "--processes", "P1;0;24")
        self.assertEqual(code, 2)
        self.assertIn("invalid parse_processes value", stderr)


if __name__ == "__main__":
    unittest.main()

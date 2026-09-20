from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import health_check  # noqa: E402


class HealthCheckTests(unittest.TestCase):
    def test_repository_plugin_is_self_contained(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing_config = Path(temporary) / "missing.json"
            report = health_check.inspect_plugin(REPO / "plugins" / "kaoyan-408", missing_config)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["skills"], {"complete": 13, "expected": 13})
        self.assertEqual(report["runtimeHelpers"]["missing"], [])
        self.assertEqual(report["obsidian"]["configStatus"], "absent")

    def test_damaged_config_is_reported_without_exposing_its_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "brain.json"
            config.write_text("{broken", encoding="utf-8")
            report = health_check.inspect_plugin(REPO / "plugins" / "kaoyan-408", config)
        self.assertEqual(report["status"], "problem")
        self.assertEqual(report["obsidian"]["configStatus"], "invalid")
        serialized = json.dumps(report, ensure_ascii=False)
        self.assertNotIn(str(config), serialized)


if __name__ == "__main__":
    unittest.main()

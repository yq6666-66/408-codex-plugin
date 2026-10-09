from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

import health_check  # noqa: E402
from release_payload import EXPECTED_SKILLS as RELEASE_SKILLS  # noqa: E402


class HealthCheckTests(unittest.TestCase):
    def test_declared_skill_names_match_release_allowlist(self) -> None:
        self.assertEqual(health_check.EXPECTED_SKILLS, RELEASE_SKILLS)

    def test_health_check_rejects_an_unrelated_skill_substitution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            plugin = Path(temporary) / "plugin"
            shutil.copytree(REPO / "plugins" / "kaoyan-408", plugin)
            renamed = plugin / "skills" / "kaoyan-admissions-researcher"
            renamed.rename(renamed.with_name("unrelated-skill"))
            report = health_check.inspect_plugin(plugin, Path(temporary) / "missing.json")
        self.assertEqual(report["skills"]["complete"], 14)
        self.assertEqual(report["status"], "problem")
        self.assertTrue(any("Skill set" in issue for issue in report["problems"]))

    def test_manifest_identity_and_semver_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            plugin = Path(temporary) / "plugin"
            shutil.copytree(REPO / "plugins" / "kaoyan-408", plugin)
            manifest_path = plugin / ".codex-plugin" / "plugin.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            for change, expected in (({"name": "other-plugin"}, "manifest name"),
                                     ({"version": "corrupt"}, "semantic version")):
                with self.subTest(change=change):
                    manifest_path.write_text(json.dumps({**manifest, **change}), encoding="utf-8")
                    report = health_check.inspect_plugin(plugin, Path(temporary) / "missing.json")
                    self.assertEqual(report["status"], "problem")
                    self.assertTrue(any(expected in issue for issue in report["problems"]))

    def test_broken_obsidian_validator_is_reported_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plugin = root / "plugin"
            shutil.copytree(REPO / "plugins" / "kaoyan-408", plugin)
            config = root / "brain.json"
            config.write_text(json.dumps({
                "schemaVersion": "1.1", "enabled": True, "vaultPath": str(root),
                "projectRoot": "20-project/test", "knowledgeRoot": "30-knowledge/test",
                "pastPaperRoot": "40-papers/test", "writeMode": "auto-structured",
                "retrievalScope": "project-first",
            }), encoding="utf-8")
            validator = plugin / "scripts" / "configure_obsidian_brain.py"
            for broken in ("def broken(:\n    pass\n", "def other():\n    pass\n"):
                with self.subTest(broken=broken):
                    validator.write_text(broken, encoding="utf-8")
                    report = health_check.inspect_plugin(plugin, config)
                    self.assertEqual(report["obsidian"]["configStatus"], "invalid")
                    self.assertEqual(report["status"], "problem")
                    self.assertNotIn(str(config), json.dumps(report, ensure_ascii=False))
    def test_repository_plugin_is_self_contained(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing_config = Path(temporary) / "missing.json"
            report = health_check.inspect_plugin(REPO / "plugins" / "kaoyan-408", missing_config)
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["skills"], {"complete": health_check.EXPECTED_SKILL_COUNT, "expected": health_check.EXPECTED_SKILL_COUNT})
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

    def test_obsidian_config_schema_and_keys_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "brain.json"
            valid = {
                "schemaVersion": "1.1",
                "enabled": True,
                "vaultPath": str(root / "missing-vault"),
                "projectRoot": "20-project/test",
                "knowledgeRoot": "30-knowledge/test",
                "pastPaperRoot": "40-papers/test",
                "writeMode": "auto-structured",
                "retrievalScope": "project-first",
            }
            config.write_text(json.dumps(valid), encoding="utf-8")
            healthy = health_check.inspect_plugin(REPO / "plugins" / "kaoyan-408", config)
            self.assertEqual(healthy["obsidian"]["configStatus"], "valid")
            self.assertEqual(healthy["obsidian"]["vaultStatus"], "missing")
            self.assertEqual(healthy["status"], "problem")

            config.write_text(json.dumps({**valid, "enabled": False}), encoding="utf-8")
            disabled = health_check.inspect_plugin(REPO / "plugins" / "kaoyan-408", config)
            self.assertEqual(disabled["obsidian"]["configStatus"], "valid")
            self.assertEqual(disabled["obsidian"]["vaultStatus"], "missing")
            self.assertEqual(disabled["status"], "ok")

            for invalid in (
                {**valid, "schemaVersion": "1.0"},
                {**valid, "extraOption": True},
                {**valid, "enabled": False, "schemaVersion": "1.0"},
            ):
                with self.subTest(invalid=invalid.get("schemaVersion", "unknown-key")):
                    config.write_text(json.dumps(invalid), encoding="utf-8")
                    report = health_check.inspect_plugin(REPO / "plugins" / "kaoyan-408", config)
                    self.assertEqual(report["obsidian"]["configStatus"], "invalid")
                    self.assertEqual(report["status"], "problem")
                    self.assertNotIn(str(config), json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()

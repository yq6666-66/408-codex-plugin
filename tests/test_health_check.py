from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
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
        self.assertEqual(report["skills"]["complete"], health_check.EXPECTED_SKILL_COUNT - 1)
        self.assertEqual(report["status"], "problem")
        self.assertTrue(any("Skill set" in issue for issue in report["problems"]))
        self.assertTrue(any("frontmatter name must match" in issue for issue in report["problems"]))

    def test_incomplete_unexpected_skill_directory_is_not_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            plugin = Path(temporary) / "plugin"
            shutil.copytree(REPO / "plugins" / "kaoyan-408", plugin)
            (plugin / "skills" / "rogue-incomplete").mkdir()
            report = health_check.inspect_plugin(plugin, Path(temporary) / "missing.json")
        self.assertEqual(report["status"], "problem")
        self.assertTrue(any("rogue-incomplete" in issue and "unexpected" in issue for issue in report["problems"]))

    def test_missing_required_reference_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            plugin = Path(temporary) / "plugin"
            shutil.copytree(REPO / "plugins" / "kaoyan-408", plugin)
            required_reference = plugin / "references" / "admissions-research-contract.md"
            required_reference.unlink()
            report = health_check.inspect_plugin(plugin, Path(temporary) / "missing.json")
        self.assertEqual(report["status"], "problem")
        self.assertTrue(any(
            "missing or unreadable Skill references" in issue
            and "admissions-research-contract.md" in issue
            for issue in report["problems"]
        ))

    def test_empty_skill_metadata_does_not_report_a_healthy_install(self) -> None:
        for relative_path in (
            Path("skills/kaoyan-408-tutor/SKILL.md"),
            Path("skills/kaoyan-408-tutor/agents/openai.yaml"),
        ):
            with self.subTest(path=relative_path), tempfile.TemporaryDirectory() as temporary:
                plugin = Path(temporary) / "plugin"
                shutil.copytree(REPO / "plugins" / "kaoyan-408", plugin)
                (plugin / relative_path).write_text("", encoding="utf-8")
                report = health_check.inspect_plugin(plugin, Path(temporary) / "missing.json")
            self.assertEqual(report["status"], "problem")
            self.assertTrue(any("invalid Skill metadata kaoyan-408-tutor" in issue
                                for issue in report["problems"]))

    def test_runtime_helper_symlink_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plugin = root / "plugin"
            shutil.copytree(REPO / "plugins" / "kaoyan-408", plugin)
            helper = plugin / "scripts" / "records.py"
            target = root / "external-records.py"
            target.write_text("# outside helper", encoding="utf-8")
            helper.unlink()
            try:
                helper.symlink_to(target)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"symbolic links unavailable: {exc}")
            report = health_check.inspect_plugin(plugin, root / "missing.json")
        self.assertEqual(report["status"], "problem")
        self.assertTrue(any("symlinked runtime helpers" in issue and "records.py" in issue
                            for issue in report["problems"]))

    def test_skill_directory_and_required_skill_files_reject_symlinks(self) -> None:
        for link_target in ("directory", "SKILL.md", "agents/openai.yaml"):
            with self.subTest(link_target=link_target), tempfile.TemporaryDirectory() as temporary:
                plugin = Path(temporary) / "plugin"
                shutil.copytree(REPO / "plugins" / "kaoyan-408", plugin)
                skills = plugin / "skills"
                selected = skills / "kaoyan-admissions-researcher"
                other = skills / "kaoyan-official-info-researcher"
                try:
                    if link_target == "directory":
                        shutil.rmtree(selected)
                        os.symlink(other, selected, target_is_directory=True)
                    else:
                        destination = selected / link_target
                        target = other / link_target
                        destination.unlink()
                        os.symlink(target, destination)
                except (OSError, NotImplementedError) as exc:
                    self.skipTest(f"symbolic links unavailable: {exc}")
                report = health_check.inspect_plugin(plugin, Path(temporary) / "missing.json")
            self.assertEqual(report["status"], "problem")
            self.assertTrue(any("symbolic link" in issue for issue in report["problems"]))

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
            validator = root / "trusted-configure-obsidian-brain.py"
            for broken in ("def broken(:\n    pass\n", "def other():\n    pass\n"):
                with self.subTest(broken=broken):
                    validator.write_text(broken, encoding="utf-8")
                    with patch.object(health_check, "_trusted_brain_validator_path", return_value=validator):
                        report = health_check.inspect_plugin(plugin, config)
                    self.assertEqual(report["obsidian"]["configStatus"], "invalid")
                    self.assertEqual(report["status"], "problem")
                    self.assertNotIn(str(config), json.dumps(report, ensure_ascii=False))
    def test_health_check_does_not_execute_validator_from_inspected_plugin(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            plugin = root / "plugin"
            shutil.copytree(REPO / "plugins" / "kaoyan-408", plugin)
            marker = root / "untrusted-validator-executed.txt"
            validator = plugin / "scripts" / "configure_obsidian_brain.py"
            validator.write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n",
                encoding="utf-8",
            )
            config = root / "brain.json"
            config.write_text(json.dumps({
                "schemaVersion": "1.1", "enabled": False, "vaultPath": str(root),
                "projectRoot": "20-project/test", "knowledgeRoot": "30-knowledge/test",
                "pastPaperRoot": "40-papers/test", "writeMode": "auto-structured",
                "retrievalScope": "project-first",
            }), encoding="utf-8")

            report = health_check.inspect_plugin(plugin, config)

            self.assertFalse(marker.exists())
            self.assertEqual(report["obsidian"]["configStatus"], "valid")
            self.assertEqual(report["status"], "ok")

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

    def test_config_directory_is_reported_as_a_path_type_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "config-directory"
            config.mkdir()
            report = health_check.inspect_plugin(REPO / "plugins" / "kaoyan-408", config)
        self.assertEqual(report["obsidian"]["configStatus"], "invalid")
        self.assertEqual(report["status"], "problem")
        self.assertTrue(any("not a regular file" in issue for issue in report["problems"]))
        self.assertNotIn(str(config), json.dumps(report, ensure_ascii=False))

    def test_existing_non_directory_non_file_config_is_invalid(self) -> None:
        class ExistingSpecialPath:
            def resolve(self):
                return self

            def is_file(self) -> bool:
                return False

            def is_dir(self) -> bool:
                return False

            def exists(self) -> bool:
                return True

        report = health_check.inspect_plugin(REPO / "plugins" / "kaoyan-408", ExistingSpecialPath())
        self.assertEqual(report["obsidian"]["configStatus"], "invalid")
        self.assertEqual(report["status"], "problem")
        self.assertTrue(any("not a regular file" in issue for issue in report["problems"]))

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

    def test_enabled_vault_must_have_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            vault = root / "vault"
            vault.mkdir()
            config = root / "brain.json"
            config.write_text(json.dumps({
                "schemaVersion": "1.1", "enabled": True, "vaultPath": str(vault),
                "projectRoot": "20-project/test", "knowledgeRoot": "30-knowledge/test",
                "pastPaperRoot": "40-papers/test", "writeMode": "auto-structured",
                "retrievalScope": "project-first",
            }), encoding="utf-8")
            report = health_check.inspect_plugin(REPO / "plugins" / "kaoyan-408", config)
        self.assertEqual(report["obsidian"]["configStatus"], "valid")
        self.assertEqual(report["obsidian"]["vaultStatus"], "incomplete")
        self.assertEqual(report["status"], "problem")


if __name__ == "__main__":
    unittest.main()

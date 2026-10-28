"""Full-plugin entry assembly preserves standalone source and user edits."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("plugin_entry_sync_exporter", REPO / "tools/skills.py")
skills = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skills)


class PluginEntrySyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="408-entry-sync-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(REPO / "src", self.root / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        shutil.copyfile(REPO / "skillset.json", self.root / "skillset.json")
        shutil.copyfile(REPO / "LICENSE", self.root / "LICENSE")

    def stage_generated(self):
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Entry Fixture"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "entries@example.invalid"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "add", "plugins"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "generated entry fixture"], cwd=self.root, check=True, capture_output=True)

    def test_missing_entries_reported_without_writes(self):
        before = {p.relative_to(self.root) for p in self.root.rglob("*")}
        result = skills.sync_plugin_skills(self.root, check=True)
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["drift"]), 6)
        self.assertEqual(before, {p.relative_to(self.root) for p in self.root.rglob("*")})

    def test_generated_entries_use_shared_contracts_and_standalone_export_stays_valid(self):
        result = skills.sync_plugin_skills(self.root)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["updated"]), 6)
        for name in skills.NAMES:
            root = self.root / "plugins/kaoyan-408/skills" / name
            content = (root / "SKILL.md").read_text(encoding="utf-8")
            self.assertIn("../../references/capability-routing-contract.md", content)
            self.assertIn("../../references/evidence-copyright-contract.md", content)
            self.assertIn("../../references/knowledge-point-basis.md", content)
            meta = yaml.safe_load((root / "agents/openai.yaml").read_text(encoding="utf-8"))["interface"]
            self.assertTrue(25 <= len(meta["short_description"]) <= 64)
            self.assertIn("$" + name, meta["default_prompt"])
        calculator = (self.root / "plugins/kaoyan-408/skills/408-calculation-check/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("插件根", calculator)
        self.assertIn("[模拟器](../../scripts/study_simulator.py)", calculator)
        self.assertNotIn("从当前技能目录按相对路径运行", calculator)
        self.assertNotIn("(scripts/", calculator)
        manifest, assembled = skills.load_source(self.root)
        self.assertEqual(set(assembled), skills.NAMES)
        self.assertEqual(manifest["name"], "408-agent-skills")

    def test_source_change_detected_and_existing_indexed_output_is_backed_up(self):
        skills.sync_plugin_skills(self.root)
        self.stage_generated()
        name = "408-concept-followup"
        target = self.root / "plugins/kaoyan-408/skills" / name / "SKILL.md"
        old = target.read_bytes()
        source = self.root / "src/skills" / name / "SKILL.md"
        source.write_bytes(source.read_bytes() + b"\nNew material.\n")
        check = skills.sync_plugin_skills(self.root, check=True)
        self.assertEqual(check["drift"], [target.relative_to(self.root).as_posix()])
        result = skills.sync_plugin_skills(self.root)
        self.assertEqual((Path(result["backup"]) / target.relative_to(self.root)).read_bytes(), old)
        self.assertIn(b"New material.", target.read_bytes())

    def test_untracked_or_modified_target_is_preserved(self):
        skills.sync_plugin_skills(self.root)
        self.stage_generated()
        target = self.root / "plugins/kaoyan-408/skills/408-error-diagnosis/SKILL.md"
        target.write_text("user edit\n", encoding="utf-8")
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_skills(self.root)
        self.assertEqual(target.read_text(encoding="utf-8"), "user edit\n")

    def test_staged_user_edit_is_also_preserved(self):
        skills.sync_plugin_skills(self.root)
        self.stage_generated()
        target = self.root / "plugins/kaoyan-408/skills/408-error-diagnosis/SKILL.md"
        target.write_text("staged user edit\n", encoding="utf-8")
        subprocess.run(["git", "add", str(target)], cwd=self.root, check=True, capture_output=True)
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_skills(self.root)
        self.assertEqual(target.read_text(encoding="utf-8"), "staged user edit\n")

    def test_untracked_unknown_target_is_not_overwritten(self):
        target = self.root / "plugins/kaoyan-408/skills/408-error-diagnosis/SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("unknown file\n", encoding="utf-8")
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_skills(self.root)
        self.assertEqual(target.read_text(encoding="utf-8"), "unknown file\n")
        self.assertFalse((self.root / "plugins/kaoyan-408/skills/408-concept-followup").exists())

    def test_tracked_deleted_target_is_reported_without_recreation(self):
        skills.sync_plugin_skills(self.root)
        self.stage_generated()
        target = self.root / "plugins/kaoyan-408/skills/408-error-diagnosis/SKILL.md"
        target.unlink()
        before = {p.relative_to(self.root) for p in self.root.rglob("*")}
        result = skills.sync_plugin_skills(self.root, check=True)
        self.assertFalse(result["valid"])
        self.assertIn(target.relative_to(self.root).as_posix(), result["drift"])
        self.assertEqual(before, {p.relative_to(self.root) for p in self.root.rglob("*")})
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_skills(self.root)
        self.assertFalse(target.exists())

    def test_staged_deletion_does_not_get_recreated(self):
        skills.sync_plugin_skills(self.root)
        self.stage_generated()
        relative = "plugins/kaoyan-408/skills/408-error-diagnosis/SKILL.md"
        target = self.root / relative
        target.unlink()
        subprocess.run(["git", "add", "-u", "--", relative], cwd=self.root, check=True, capture_output=True)
        before = subprocess.check_output(["git", "diff", "--cached", "--name-status"], cwd=self.root)
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_skills(self.root)
        self.assertFalse(target.exists())
        self.assertEqual(before, subprocess.check_output(["git", "diff", "--cached", "--name-status"], cwd=self.root))

    def test_first_generation_works_without_git_for_plain_sources(self):
        with patch.object(skills.subprocess, "run", side_effect=FileNotFoundError("git unavailable")):
            result = skills.sync_plugin_skills(self.root)
        self.assertTrue(result["valid"])
        self.assertEqual(len(result["updated"]), 6)

    def test_partial_plain_source_tree_preserves_deleted_entry(self):
        skills.sync_plugin_skills(self.root)
        target = self.root / "plugins/kaoyan-408/skills/408-error-diagnosis/SKILL.md"
        target.unlink()
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_skills(self.root)
        self.assertFalse(target.exists())

    def test_no_git_with_repository_metadata_fails_closed(self):
        skills.sync_plugin_skills(self.root)
        self.stage_generated()
        target = self.root / "plugins/kaoyan-408/skills/408-error-diagnosis/SKILL.md"
        target.unlink()
        with patch.object(skills.subprocess, "run", side_effect=FileNotFoundError("git unavailable")):
            with self.assertRaises(skills.SkillsError):
                skills.sync_plugin_skills(self.root)
        self.assertFalse(target.exists())

    def test_partial_creation_rolls_back_after_failure(self):
        original = skills._replace_bytes
        count = 0
        def fail_second(path, content):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError("injected failure")
            return original(path, content)
        with patch.object(skills, "_replace_bytes", side_effect=fail_second):
            with self.assertRaises(OSError):
                skills.sync_plugin_skills(self.root)
        for target in skills.plugin_skill_payloads(self.root):
            self.assertFalse((self.root / target).exists())

    def test_linked_source_is_rejected(self):
        path = self.root / "src/skills/408-concept-followup/SKILL.md"
        other = self.root / "elsewhere.md"
        other.write_bytes(path.read_bytes())
        path.unlink()
        try:
            path.symlink_to(other)
        except OSError:
            self.skipTest("symlink creation is unavailable")
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_skills(self.root)
        self.assertFalse((self.root / "plugins").exists())

"""The complete plugin consumes explicit canonical resource copies."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("shared_sync_exporter", REPO / "tools/skills.py")
skills = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skills)


class SharedResourceSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.assertTrue(hasattr(skills, "PLUGIN_SHARED_RESOURCES"), "explicit shared-resource map is missing")
        for source in skills.PLUGIN_SHARED_RESOURCES:
            path = self.root / source
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(("canonical " + source + "\n").encode())

    def commit_fixture(self):
        def git(*arguments):
            subprocess.run(["git", *arguments], cwd=self.root, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        git("init", "-b", "main")
        git("config", "user.name", "Shared Resource Fixture")
        git("config", "user.email", "resources@example.invalid")
        git("config", "commit.gpgsign", "false")
        git("add", ".")
        git("commit", "-m", "tracked resource fixture")

    def test_check_is_read_only_and_reports_every_missing_target(self):
        before = set(self.root.rglob("*"))
        result = skills.sync_plugin_resources(self.root, check=True)
        self.assertFalse(result["valid"])
        self.assertEqual(len(result["drift"]), len(skills.PLUGIN_SHARED_RESOURCES))
        self.assertEqual(set(self.root.rglob("*")), before)

    def test_sync_backs_up_exact_old_bytes_and_reuses_equal_copies(self):
        source, target = next(iter(skills.PLUGIN_SHARED_RESOURCES.items()))
        path = self.root / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"user-visible old resource\n")
        self.commit_fixture()
        result = skills.sync_plugin_resources(self.root)
        self.assertTrue(result["valid"])
        self.assertEqual((Path(result["backup"]) / target).read_bytes(), b"user-visible old resource\n")
        self.assertEqual(path.read_bytes(), (self.root / source).read_bytes())
        repeated = skills.sync_plugin_resources(self.root)
        self.assertEqual(repeated["updated"], [])
        self.assertIsNone(repeated["backup"])

    @unittest.skipIf(os.name == "nt", "POSIX file mode and umask semantics")
    def test_updated_file_and_backup_preserve_existing_file_mode(self):
        source, relative = next(iter(skills.PLUGIN_SHARED_RESOURCES.items()))
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"old managed resource\n")
        target.chmod(0o640)
        self.commit_fixture()
        result = skills.sync_plugin_resources(self.root)
        self.assertEqual(target.read_bytes(), (self.root / source).read_bytes())
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o640)
        self.assertEqual(stat.S_IMODE((Path(result["backup"]) / relative).stat().st_mode), 0o640)

    @unittest.skipIf(os.name == "nt", "POSIX file mode and umask semantics")
    def test_new_files_obey_process_umask(self):
        original_umask = os.umask(0o027)
        try:
            skills.sync_plugin_resources(self.root)
        finally:
            os.umask(original_umask)
        for relative in skills.PLUGIN_SHARED_RESOURCES.values():
            self.assertEqual(stat.S_IMODE((self.root / relative).stat().st_mode), 0o640)

    def test_drift_is_detected_after_a_source_or_generated_copy_changes(self):
        skills.sync_plugin_resources(self.root)
        source, target = next(iter(skills.PLUGIN_SHARED_RESOURCES.items()))
        (self.root / source).write_bytes(b"new source\n")
        result = skills.sync_plugin_resources(self.root, check=True)
        self.assertEqual(result["drift"], [target])
        self.assertNotEqual((self.root / source).read_bytes(), (self.root / target).read_bytes())

    def test_untracked_resource_is_preserved_without_overwrite(self):
        target = self.root / next(iter(skills.PLUGIN_SHARED_RESOURCES.values()))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"untracked user content\n")
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_resources(self.root)
        self.assertEqual(target.read_bytes(), b"untracked user content\n")

    def test_modified_tracked_resource_is_preserved_without_overwrite(self):
        skills.sync_plugin_resources(self.root)
        self.commit_fixture()
        source, relative = next(iter(skills.PLUGIN_SHARED_RESOURCES.items()))
        (self.root / source).write_bytes(b"new canonical content\n")
        target = self.root / relative
        target.write_bytes(b"user modified content\n")
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_resources(self.root)
        self.assertEqual(target.read_bytes(), b"user modified content\n")

    def test_deleted_tracked_resource_is_not_recreated(self):
        skills.sync_plugin_resources(self.root)
        self.commit_fixture()
        target = self.root / next(iter(skills.PLUGIN_SHARED_RESOURCES.values()))
        target.unlink()
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_resources(self.root)
        self.assertFalse(target.exists())

    def test_partial_plain_source_tree_is_not_treated_as_first_generation(self):
        skills.sync_plugin_resources(self.root)
        target = self.root / next(iter(skills.PLUGIN_SHARED_RESOURCES.values()))
        target.unlink()
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_resources(self.root)
        self.assertFalse(target.exists())

    def test_missing_or_invalid_source_is_rejected_before_any_target_changes(self):
        source = list(skills.PLUGIN_SHARED_RESOURCES)[-1]
        (self.root / source).write_bytes(b"bad\r\n")
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_resources(self.root)
        self.assertFalse((self.root / "plugins").exists())

    def test_failed_write_rolls_back_previously_updated_targets(self):
        original = skills._replace_bytes
        counter = 0
        def fail_second(path, content):
            nonlocal counter
            counter += 1
            if counter == 2:
                raise OSError("simulated storage failure")
            return original(path, content)
        with patch.object(skills, "_replace_bytes", side_effect=fail_second):
            with self.assertRaises(OSError):
                skills.sync_plugin_resources(self.root)
        for target in skills.PLUGIN_SHARED_RESOURCES.values():
            self.assertFalse((self.root / target).exists())

    def test_symlink_source_is_rejected_without_writing_plugin(self):
        source = next(iter(skills.PLUGIN_SHARED_RESOURCES))
        path = self.root / source
        saved = self.root / "outside.txt"
        saved.write_bytes(b"outside\n")
        path.unlink()
        try:
            path.symlink_to(saved)
        except OSError:
            self.skipTest("symlink creation is unavailable")
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_resources(self.root)
        self.assertFalse((self.root / "plugins").exists())

    def test_linked_root_is_checked_before_resolution(self):
        alias = self.root / "linked-root"
        try:
            alias.symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest("directory symlink creation is unavailable")
        with self.assertRaises(skills.SkillsError):
            skills.sync_plugin_resources(alias, check=True)

    def test_rollback_continues_after_preserving_a_concurrent_edit(self):
        entries = list(skills.PLUGIN_SHARED_RESOURCES.items())[:3]
        for _, relative in entries:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"old resource\n")
        self.commit_fixture()
        original = skills._replace_bytes
        counter = 0
        def fail_third(path, content):
            nonlocal counter
            counter += 1
            if counter == 3:
                (self.root / entries[1][1]).write_bytes(b"concurrent user edit\n")
                raise OSError("simulated storage failure")
            return original(path, content)
        with patch.object(skills, "_replace_bytes", side_effect=fail_third):
            with self.assertRaises(skills.SkillsError):
                skills.sync_plugin_resources(self.root)
        self.assertEqual((self.root / entries[0][1]).read_bytes(), b"old resource\n")
        self.assertEqual((self.root / entries[1][1]).read_bytes(), b"concurrent user edit\n")
        self.assertEqual((self.root / entries[2][1]).read_bytes(), b"old resource\n")

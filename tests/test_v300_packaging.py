"""Behavioral tests for portable assembly and non-destructive installation."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
import zipfile


REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("v300_skills", REPO / "tools" / "skills.py")
skills = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skills)


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="408-v300-test-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        self.source.mkdir()
        self.project = self.base / "project"
        self.project.mkdir()
        self.manifest = json.loads((REPO / "skillset.json").read_text(encoding="utf-8"))
        for entry in self.manifest["skills"]:
            name = entry["name"]
            self.put(entry["source"], f"---\nname: {name}\ndescription: A focused test Skill\n---\n\n[Rule](references/knowledge-point-basis.md)\n")
            for resource in entry["resources"]:
                source = resource["source"]
                if source == "LICENSE":
                    content = "MIT License\nTest author\n"
                elif source.endswith(".json"):
                    content = "{}\n"
                elif source.endswith(".py"):
                    content = "print('test fixture only')\n"
                else:
                    content = "# Project rule\n"
                self.put(source, content)
        self.save_manifest()

    def put(self, path, content):
        dest = self.source / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content.encode("utf-8"))

    def save_manifest(self):
        (self.source / "skillset.json").write_bytes(skills.json_bytes(self.manifest))

    def upgrade_version(self):
        major, minor, patch = map(int, self.manifest["version"].split("-", 1)[0].split("."))
        self.manifest["version"] = f"{major}.{minor}.{patch + 1}-fixture"
        self.save_manifest()
        return self.manifest["version"]

    def target(self, name="408-error-diagnosis", platform="codex"):
        return self.project / skills.PLATFORMS[platform] / name

    def test_self_contained_equal_platforms_and_reproducible_zip(self):
        first, second = self.base / "first", self.base / "second"
        skills.export(self.source, "all", first)
        skills.export(self.source, "all", second)
        self.assertEqual(skills.files_at(first), skills.files_at(second))
        for name in skills.NAMES:
            copies = [skills.files_at(first / p / prefix / name) for p, prefix in skills.PLATFORMS.items()]
            self.assertEqual(copies[0], copies[1])
            self.assertEqual(copies[1], copies[2])
            detached = self.base / ("detached-" + name)
            shutil.copytree(first / "codex" / skills.PLATFORMS["codex"] / name, detached)
            skills.check_links(skills.files_at(detached), name)
            self.assertIn("LICENSE.txt", skills.files_at(detached))
        for archive in first.glob("*.zip"):
            with zipfile.ZipFile(archive) as bundle:
                self.assertTrue(all(i.compress_type == zipfile.ZIP_STORED for i in bundle.infolist()))
                self.assertTrue(all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in bundle.infolist()))
        self.assertEqual(len(json.loads((first / "manifest.json").read_bytes())["platforms"]), 3)

    def test_existing_export_never_overwritten(self):
        output = self.base / "existing"
        output.mkdir()
        with self.assertRaises(skills.SkillsError):
            skills.export(self.source, "all", output)
        self.assertEqual(list(output.iterdir()), [])

    def test_install_single_skill_is_idempotent_and_verifiable(self):
        name = "408-concept-followup"
        first = skills.install(self.source, "codex", self.project, [name])
        before = skills.files_at(self.project)
        second = skills.install(self.source, "codex", self.project, [name])
        self.assertEqual(first["skills"][0]["action"], "create")
        self.assertEqual(second["skills"][0]["action"], "unchanged")
        self.assertEqual(skills.files_at(self.project), before)
        self.assertTrue(skills.verify(self.source, "codex", self.project, [name])["valid"])
        self.assertEqual([p.name for p in (self.project / ".agents/skills").iterdir()], [name])

    def test_unknown_conflict_prevents_all_writes(self):
        target = self.target("408-concept-followup")
        target.mkdir(parents=True)
        (target / "personal.txt").write_text("leave me", encoding="utf-8")
        before = skills.files_at(self.project)
        with self.assertRaises(skills.SkillsError):
            skills.install(self.source, "codex", self.project)
        self.assertEqual(before, skills.files_at(self.project))

    def test_user_modified_managed_skill_is_preserved(self):
        skills.install(self.source, "codex", self.project)
        (self.target() / "SKILL.md").write_text("user's own edits", encoding="utf-8")
        before = skills.files_at(self.project)
        with self.assertRaises(skills.SkillsError):
            skills.install(self.source, "codex", self.project)
        self.assertEqual(before, skills.files_at(self.project))

    def test_upgrade_backs_up_every_original_byte(self):
        skills.install(self.source, "codex", self.project)
        before = {name: skills.files_at(self.target(name)) for name in skills.NAMES}
        upgraded = self.upgrade_version()
        result = skills.install(self.source, "codex", self.project)
        backup = Path(result["backup"])
        for name in skills.NAMES:
            self.assertEqual(skills.files_at(backup / name), before[name])
            self.assertEqual(json.loads((self.target(name) / skills.RECEIPT).read_bytes())["version"], upgraded)

    def test_cross_platform_identical_reused_without_duplicate_or_adoption(self):
        skills.install(self.source, "codex", self.project)
        before = skills.files_at(self.project)
        result = skills.install(self.source, "cursor", self.project)
        self.assertEqual({s["action"] for s in result["skills"]}, {"reused-compatible"})
        self.assertEqual(skills.files_at(self.project), before)
        self.assertFalse((self.project / ".cursor").exists())
        self.assertTrue(skills.verify(self.source, "cursor", self.project)["valid"])

    def test_unmanaged_equal_content_is_not_adopted(self):
        _, assembled = skills.load_source(self.source)
        name = "408-error-diagnosis"
        skills.write_files(self.target(), skills.content_only(assembled[name]))
        result = skills.install(self.source, "codex", self.project, [name])
        self.assertEqual(result["skills"][0]["action"], "reused-unmanaged")
        self.assertFalse((self.target() / skills.RECEIPT).exists())
        self.put("src/shared/references/knowledge-point-basis.md", "Changed upstream\n")
        with self.assertRaises(skills.SkillsError):
            skills.install(self.source, "codex", self.project, [name])

    def test_cross_platform_different_content_conflicts(self):
        other = self.target(platform="codex")
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("another same-name Skill", encoding="utf-8")
        before = skills.files_at(self.project)
        with self.assertRaises(skills.SkillsError):
            skills.install(self.source, "cursor", self.project)
        self.assertEqual(before, skills.files_at(self.project))

    def test_discovery_is_asymmetric_claude_does_not_reuse_agents(self):
        skills.install(self.source, "codex", self.project)
        result = skills.install(self.source, "claude", self.project)
        self.assertEqual({s["action"] for s in result["skills"]}, {"create"})
        self.assertTrue(self.target(platform="claude").is_dir())

    def test_discovery_is_asymmetric_codex_does_not_reuse_cursor(self):
        skills.install(self.source, "cursor", self.project)
        result = skills.install(self.source, "codex", self.project)
        self.assertEqual({s["action"] for s in result["skills"]}, {"create"})
        self.assertTrue(self.target(platform="codex").is_dir())

    def test_upgrade_failure_restores_old_trees_and_removes_new_partial_set(self):
        skills.install(self.source, "codex", self.project, ["408-error-diagnosis"])
        before = skills.files_at(self.project)
        self.upgrade_version()
        original_move = skills._move
        installed = 0
        def fail_second_install(source, target):
            nonlocal installed
            if source.name.startswith(".408-stage-"):
                installed += 1
                if installed == 2:
                    raise OSError("injected second target failure")
            original_move(source, target)
        with patch.object(skills, "_move", side_effect=fail_second_install):
            with self.assertRaises(OSError):
                skills.install(self.source, "codex", self.project)
        self.assertEqual(before, skills.files_at(self.project))
        self.assertFalse(any(p.name.startswith(".408-stage-") for p in self.project.rglob("*")))

    def test_partial_stage_write_failure_is_cleaned(self):
        original_write = skills._write_contents
        def broken_write(root, payload):
            if root.name.startswith(".408-stage-"):
                (root / "SKILL.md").write_bytes(payload["SKILL.md"])
                raise OSError("disk write failure")
            return original_write(root, payload)
        with patch.object(skills, "_write_contents", side_effect=broken_write):
            with self.assertRaises(OSError):
                skills.install(self.source, "codex", self.project)
        self.assertEqual(list(self.project.iterdir()), [])

    def test_arbitrary_executable_destination_is_rejected(self):
        resource = self.manifest["skills"][0]["resources"][0]
        resource["target"] = "scripts/other.py"
        self.save_manifest()
        with self.assertRaises(skills.SkillsError):
            skills.load_source(self.source)

    def test_windows_invalid_resource_names_rejected_on_every_platform(self):
        resource = self.manifest["skills"][0]["resources"][0]
        for character in '*?"<>|\x00\x01\x1f\x7f':
            with self.subTest(character=repr(character)):
                resource["target"] = f"references/rule{character}.md"
                self.save_manifest()
                with self.assertRaises(skills.SkillsError):
                    skills.load_source(self.source)

    def test_windows_superscript_device_names_rejected_on_every_platform(self):
        skill = self.manifest["skills"][0]
        original_resources = list(skill["resources"])
        for device in ("COM¹.md", "COM².json", "COM³.md", "LPT¹.md", "LPT².json", "LPT³.md"):
            with self.subTest(device=device):
                skill["resources"] = [
                    *original_resources,
                    {"source": original_resources[1]["source"], "target": f"references/{device}"},
                ]
                self.save_manifest()
                with self.assertRaises(skills.SkillsError):
                    skills.load_source(self.source)
        skill["resources"] = original_resources
        self.save_manifest()

    def test_source_and_target_traversal_duplicate_and_undeclared_rejected(self):
        for field, value in [("source", "../outside.md"), ("target", "../escape.md"), ("target", "SKILL.md")]:
            with self.subTest(field=field, value=value):
                original = self.manifest["skills"][0]["resources"][0][field]
                self.manifest["skills"][0]["resources"][0][field] = value
                self.save_manifest()
                with self.assertRaises(skills.SkillsError):
                    skills.load_source(self.source)
                self.manifest["skills"][0]["resources"][0][field] = original
        self.save_manifest()
        self.put("src/undeclared.py", "print('unexpected')\n")
        with self.assertRaises(skills.SkillsError):
            skills.load_source(self.source)

    def test_missing_link_and_escaping_link_rejected(self):
        path = self.manifest["skills"][0]["source"]
        original = (self.source / path).read_text(encoding="utf-8")
        for target in ("references/missing.md", "../other/SKILL.md", "%2e%2e/outside.md", "/absolute.md"):
            self.put(path, original + f"\n[Bad]({target})\n")
            with self.assertRaises(skills.SkillsError):
                skills.load_source(self.source)

    def test_unsupported_frontmatter_and_crlf_rejected(self):
        path = self.manifest["skills"][0]["source"]
        original = (self.source / path).read_text(encoding="utf-8")
        for bad in (original.replace("description: A focused test Skill", "description: |\n  multiline"), original.replace("\n", "\r\n")):
            self.put(path, bad)
            with self.assertRaises(skills.SkillsError):
                skills.load_source(self.source)

    def test_target_ancestor_symlink_refused_without_touching_destination(self):
        external = self.base / "outside"
        external.mkdir()
        try:
            (self.project / ".agents").symlink_to(external, target_is_directory=True)
        except OSError:
            self.skipTest("symlink creation unavailable on this Windows account")
        with self.assertRaises(skills.SkillsError):
            skills.install(self.source, "codex", self.project)
        self.assertEqual(list(external.iterdir()), [])

    def test_source_symlink_refused(self):
        path = self.source / "src/extra.md"
        try:
            path.symlink_to(self.source / "LICENSE")
        except OSError:
            self.skipTest("symlink creation unavailable on this Windows account")
        with self.assertRaises(skills.SkillsError):
            skills.load_source(self.source)

    def test_project_scope_explicit_and_user_home_never_touched_by_project(self):
        with patch.object(Path, "home", side_effect=AssertionError("unexpected home access")):
            self.assertEqual(skills.scope_root("project", self.project), self.project)
            skills.install(self.source, "codex", self.project, ["408-error-diagnosis"])
        for path in (None, Path("relative"), self.base / "absent"):
            with self.assertRaises(skills.SkillsError):
                skills.scope_root("project", path)


if __name__ == "__main__":
    unittest.main()

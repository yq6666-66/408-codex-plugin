from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from simulate_workbuddy_host import build_findings, main, simulate_workbuddy_load  # noqa: E402


class WorkBuddySimulatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name)
        # Deliberately differ from the repository's usual plugin/skills paths:
        # diagnostics must follow the declarations, not a hard-coded tree.
        self.plugin = self.repo / "local-plugin"
        self.skills = self.plugin / "teaching"
        self.marketplace = self.repo / ".codebuddy-plugin" / "marketplace.json"
        self.manifest = self.plugin / ".codebuddy-plugin" / "plugin.json"
        self.write_json(self.marketplace, {
            "name": "kaoyan-408", "plugins": [{"name": "kaoyan-408", "source": "./local-plugin"}],
        })
        self.write_json(self.manifest, {
            "name": "kaoyan-408", "version": "2.6.1", "skills": "./teaching",
        })
        self.skill_md = self.skills / "example" / "SKILL.md"
        self.skill_md.parent.mkdir(parents=True)
        self.skill_md.write_bytes(b"---\nname: example\ndescription: Example lesson\n---\nRead a lesson.\n")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def write_json(path: Path, document: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((json.dumps(document) + "\n").encode("utf-8"))

    def assert_blocked(self) -> None:
        report = simulate_workbuddy_load(self.repo)
        findings = build_findings(self.repo, report)
        self.assertTrue(any(item["severity"] == "blocker" for item in findings), findings)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["--repo", str(self.repo), "--json", "--fail-on", "blocker"]), 1)
        self.assertIsInstance(json.loads(output.getvalue())["findings"], list)

    def test_follows_declared_source_and_skills(self) -> None:
        report = simulate_workbuddy_load(self.repo)
        self.assertEqual(Path(report["pluginRoot"]), self.plugin.resolve())
        self.assertEqual([skill["name"] for skill in report["skills"]], ["example"])
        self.assertFalse(any(item["severity"] == "blocker" for item in build_findings(self.repo, report)))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--repo", str(self.repo), "--json", "--fail-on", "blocker"]), 0)

    def test_missing_marketplace_is_blocked(self) -> None:
        self.marketplace.unlink()
        self.assert_blocked()

    def test_malformed_marketplace_is_blocked(self) -> None:
        for document in (
            [], {}, {"plugins": []}, {"plugins": ["wrong"]},
            {"plugins": [{"source": None}]}, {"plugins": [{}, {}]},
        ):
            with self.subTest(document=document):
                self.write_json(self.marketplace, document)
                self.assert_blocked()
        self.marketplace.write_bytes(b"{broken json\n")
        self.assert_blocked()

    def test_missing_source_directory_is_blocked_even_with_old_default_tree(self) -> None:
        # The original implementation ignored the source and could inspect this decoy.
        default_plugin = self.repo / "plugins" / "kaoyan-408"
        self.write_json(default_plugin / ".codebuddy-plugin" / "plugin.json", {
            "name": "kaoyan-408", "version": "2.6.1", "skills": "./skills",
        })
        self.write_json(self.marketplace, {
            "name": "kaoyan-408", "plugins": [{"name": "kaoyan-408", "source": "./missing"}],
        })
        self.assert_blocked()

    def test_unsafe_source_paths_are_blocked(self) -> None:
        for source in (
            "../outside", str(self.repo.resolve()), "C:/outside", "./local-plugin/../local-plugin",
            "./local-plugin\\teaching", "", " ", "\x00", ".", None,
        ):
            with self.subTest(source=source):
                self.write_json(self.marketplace, {
                    "name": "kaoyan-408", "plugins": [{"name": "kaoyan-408", "source": source}],
                })
                self.assert_blocked()

    def test_missing_or_malformed_manifest_is_blocked(self) -> None:
        self.manifest.unlink()
        self.assert_blocked()
        for document in (
            [], {}, {"name": "kaoyan-408", "version": "2.6.1", "skills": None},
            {"name": "kaoyan-408", "version": [], "skills": "./teaching"},
            {"name": "other-plugin", "version": "2.6.1", "skills": "./teaching"},
        ):
            with self.subTest(document=document):
                self.write_json(self.manifest, document)
                self.assert_blocked()
        self.manifest.write_bytes(b"{broken json\n")
        self.assert_blocked()

    def test_missing_or_unsafe_skills_paths_are_blocked(self) -> None:
        for skills in ("./missing", "../local-plugin/teaching", str(self.skills.resolve()), "C:/outside", "", None):
            with self.subTest(skills=skills):
                self.write_json(self.manifest, {
                    "name": "kaoyan-408", "version": "2.6.1", "skills": skills,
                })
                self.assert_blocked()

    def test_no_skills_is_blocked(self) -> None:
        self.skill_md.unlink()
        self.assert_blocked()

    def test_diagnostic_does_not_execute_bundled_code(self) -> None:
        marker = self.repo / "must-not-exist"
        scripts = self.plugin / "scripts"
        scripts.mkdir()
        (scripts / "runtime.py").write_text(
            "from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\nraise RuntimeError('executed')\n",
            encoding="utf-8", newline="\n",
        )
        build_findings(self.repo, simulate_workbuddy_load(self.repo))
        self.assertFalse(marker.exists())

    def test_source_symlink_outside_repository_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            link = self.repo / "linked-plugin"
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symlink unavailable: {exc}")
            self.write_json(self.marketplace, {
                "name": "kaoyan-408", "plugins": [{"name": "kaoyan-408", "source": "./linked-plugin"}],
            })
            self.assert_blocked()

    def test_skills_symlink_outside_plugin_is_blocked(self) -> None:
        outside = self.repo / "other-plugin-skills"
        outside.mkdir()
        link = self.plugin / "linked-skills"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        self.write_json(self.manifest, {
            "name": "kaoyan-408", "version": "2.6.1", "skills": "./linked-skills",
        })
        self.assert_blocked()

    def test_descriptor_symlink_outside_plugin_is_blocked(self) -> None:
        outside = self.repo / "external-manifest.json"
        self.write_json(outside, {"name": "kaoyan-408", "version": "2.6.1", "skills": "./teaching"})
        self.manifest.unlink()
        try:
            self.manifest.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        self.assert_blocked()

    def test_skill_directory_symlink_outside_declared_skills_is_blocked(self) -> None:
        outside = self.plugin / "references" / "extra-skill"
        outside.mkdir(parents=True)
        (outside / "SKILL.md").write_bytes(self.skill_md.read_bytes())
        link = self.skills / "linked-skill"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        self.assert_blocked()
        self.assertEqual(simulate_workbuddy_load(self.repo)["skills"], [])

    def test_skill_file_symlink_outside_declared_skills_is_blocked(self) -> None:
        outside = self.plugin / "references" / "lesson.md"
        outside.parent.mkdir(parents=True)
        outside.write_bytes(self.skill_md.read_bytes())
        self.skill_md.unlink()
        try:
            self.skill_md.symlink_to(outside)
        except OSError as exc:
            self.skipTest(f"symlink unavailable: {exc}")
        self.assert_blocked()
        self.assertEqual(simulate_workbuddy_load(self.repo)["skills"], [])

    def test_missing_descriptor_text_output_is_valid(self) -> None:
        self.marketplace.unlink()
        with contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(main(["--repo", str(self.repo), "--fail-on", "blocker"]), 1)
        self.assertIn("WB-001", output.getvalue())


if __name__ == "__main__":
    unittest.main()

"""Release preparation binds three archives to the exact clean source commit."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class SkillsReleaseTests(unittest.TestCase):
    def setUp(self):
        script = REPO / "ci/skills_release.py"
        self.assertTrue(script.is_file(), "three-platform release preparation is missing")
        spec = importlib.util.spec_from_file_location("skills_release_tested", script)
        self.release = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.release)
        skill_spec = importlib.util.spec_from_file_location("release_fixture_exporter", REPO / "tools/skills.py")
        self.skills = importlib.util.module_from_spec(skill_spec)
        skill_spec.loader.exec_module(self.skills)
        self.temp = tempfile.TemporaryDirectory(prefix="408-release-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        shutil.copytree(REPO / "src", self.repo / "src", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for relative in self.release.PACKAGING_FILES:
            target = self.repo / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(REPO / relative, target)
        # DrvFS may report executable bits for Windows files. Commit fixtures
        # with the same regular 0644 modes as the actual repository snapshot.
        for path in self.repo.rglob("*"):
            if path.is_file():
                path.chmod(0o644)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Release Fixture")
        self.git("config", "user.email", "release@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("config", "commit.gpgsign", "false")
        self.git("add", ".")
        self.git("commit", "-m", "source fixture")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.version = json.loads((self.repo / "skillset.json").read_bytes())["version"]
        self.tag = "skills-v" + self.version
        self.windows = self.base / "windows"
        self.ubuntu = self.base / "ubuntu"
        self.output = self.base / "release"
        self.skills.export(self.repo, "all", self.windows)
        self.skills.export(self.repo, "all", self.ubuntu)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], stderr=subprocess.PIPE, text=True, encoding="utf-8")

    def name(self, platform="codex"):
        return f"408-agent-skills-{self.version}-{platform}.zip"

    def prepare(self, **changes):
        arguments = dict(repo=self.repo, windows=self.windows, ubuntu=self.ubuntu, output=self.output,
                         expected_tag=self.tag, expected_commit=self.commit)
        arguments.update(changes)
        return self.release.prepare_release(**arguments)

    def test_three_archives_checksums_notes_and_source_binding(self):
        result = self.prepare()
        self.assertEqual(result["sourceCommit"], self.commit)
        self.assertEqual(result["tag"], self.tag)
        self.assertTrue(result["prerelease"])
        self.assertEqual(set(p.name for p in self.output.iterdir()),
                         {self.name(p) for p in ("claude", "codex", "cursor")} |
                         {"release.json", "SHA256SUMS.txt", "RELEASE_NOTES.md"})
        verified = self.release.verify_release(self.repo, self.output, self.tag, self.commit)
        self.assertTrue(verified["valid"])
        self.assertIn("未验证", (self.output / "RELEASE_NOTES.md").read_text(encoding="utf-8"))
        self.assertFalse(self.git("tag").strip())

    def test_platform_difference_rejected_without_creating_output(self):
        with (self.windows / self.name()).open("ab") as stream:
            stream.write(b"changed")
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.output.exists())

    def test_identically_tampered_artifacts_rejected_against_source(self):
        for directory in (self.windows, self.ubuntu):
            with (directory / self.name()).open("ab") as stream:
                stream.write(b"same-tampering")
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.output.exists())

    def test_wrong_commit_tag_and_unsafe_tag_rejected_before_output(self):
        for change in ({"expected_commit": "0" * 40}, {"expected_commit": "HEAD"},
                       {"expected_tag": "v" + self.version}, {"expected_tag": self.tag + "\nextra"}):
            with self.subTest(change=change):
                with self.assertRaises(ValueError): self.prepare(**change)
                self.assertFalse(self.output.exists())

    def test_dirty_source_cannot_be_rebound_by_rebuilding_both_platforms(self):
        path = self.repo / "src/skills/408-concept-followup/SKILL.md"
        path.write_bytes(path.read_bytes() + b"\nChanged source\n")
        a, b = self.base / "new-win", self.base / "new-linux"
        self.skills.export(self.repo, "all", a)
        self.skills.export(self.repo, "all", b)
        with self.assertRaises(ValueError): self.prepare(windows=a, ubuntu=b)
        self.assertFalse(self.output.exists())

    def test_dirty_packaging_implementation_is_rejected(self):
        path = self.repo / "tools/skills.py"
        path.write_bytes(path.read_bytes() + b"\n# modified tool\n")
        with self.assertRaises(ValueError): self.prepare()

    def test_untracked_source_cannot_be_silently_excluded(self):
        (self.repo / "src/unexpected.md").write_text("unreviewed\n", encoding="utf-8")
        with self.assertRaises(ValueError): self.prepare()

    def test_missing_and_extra_archives_are_rejected(self):
        extra = self.windows / "unexpected.zip"
        extra.write_bytes(b"extra")
        with self.assertRaises(ValueError): self.prepare()
        extra.unlink()
        (self.windows / self.name()).unlink()
        with self.assertRaises(ValueError): self.prepare()
        self.assertFalse(self.output.exists())

    def test_existing_output_and_nested_input_output_preserved(self):
        self.output.mkdir()
        marker = self.output / "personal.txt"
        marker.write_bytes(b"unchanged")
        with self.assertRaises(ValueError): self.prepare()
        self.assertEqual(marker.read_bytes(), b"unchanged")
        for output in (self.windows / "nested", self.repo / "src/release", self.repo / ".git/release"):
            with self.subTest(output=output):
                with self.assertRaises(ValueError): self.prepare(output=output)
                self.assertFalse(output.exists())

    def test_stable_metadata_and_malformed_prerelease(self):
        path = self.repo / "skillset.json"
        manifest = json.loads(path.read_bytes())
        manifest["version"] = "3.0.0"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        self.assertFalse(self.release.metadata(self.repo)["prerelease"])
        for version in ("3.0.0-dev.01", "../escape", "3.0.0\nextra"):
            manifest["version"] = version
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError): self.release.metadata(self.repo)

    def test_verification_detects_tampered_release_metadata_checksums_and_notes(self):
        self.prepare()
        for name in (self.name(), "release.json", "SHA256SUMS.txt", "RELEASE_NOTES.md"):
            with self.subTest(name=name):
                path = self.output / name
                original = path.read_bytes()
                path.write_bytes(original + b"modified")
                with self.assertRaises(ValueError):
                    self.release.verify_release(self.repo, self.output, self.tag, self.commit)
                self.assertEqual(path.read_bytes(), original + b"modified")
                path.write_bytes(original)
        (self.output / "extra.txt").write_bytes(b"unexpected")
        with self.assertRaises(ValueError):
            self.release.verify_release(self.repo, self.output, self.tag, self.commit)

    def test_linked_output_parent_is_rejected(self):
        destination = self.base / "external"
        destination.mkdir()
        link = self.base / "linked"
        try: link.symlink_to(destination, target_is_directory=True)
        except OSError: self.skipTest("directory symlinks unavailable")
        with self.assertRaises(ValueError): self.prepare(output=link / "release")
        self.assertEqual(list(destination.iterdir()), [])

    def test_cli_prepare_and_verify_without_creating_tag(self):
        command = [sys.executable, "-I", "-B", str(self.repo / "ci/skills_release.py")]
        common = ["--tag", self.tag, "--commit", self.commit]
        result = subprocess.run(command + ["prepare", "--windows", str(self.windows), "--ubuntu", str(self.ubuntu),
                                           "--output", str(self.output)] + common,
                                cwd=self.base, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["sourceCommit"], self.commit)
        result = subprocess.run(command + ["verify", "--directory", str(self.output)] + common,
                                cwd=self.base, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.git("tag").strip())

    def test_untracked_package_initializers_are_never_executed(self):
        for package in ("tools", "ci"):
            with self.subTest(package=package):
                marker = self.repo / ("unexpected-bootstrap-execution-" + package)
                initializer = self.repo / package / "__init__.py"
                initializer.write_text(
                    "from pathlib import Path\n"
                    "(Path(__file__).resolve().parents[1] / " + repr(marker.name) + ").write_text('ran')\n",
                    encoding="utf-8")
                result = subprocess.run(
                    [sys.executable, "-I", "-B", str(self.repo / "ci/skills_release.py"), "prepare",
                     "--windows", str(self.windows), "--ubuntu", str(self.ubuntu),
                     "--output", str(self.base / ("prepared-" + package)), "--tag", self.tag,
                     "--commit", self.commit], cwd=self.base, capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(marker.exists(), "uncommitted package initializer executed")
                initializer.unlink()

    def test_dirty_build_code_is_rejected_before_execution(self):
        for relative in ("tools/skills.py", "ci/verify_skills_reproducible.py"):
            with self.subTest(relative=relative):
                marker = self.base / ("unexpected-build-code-execution-" + Path(relative).stem)
                path = self.repo / relative
                original = path.read_bytes()
                path.write_bytes(original + ("\nfrom pathlib import Path\nPath(" + repr(str(marker)) +
                                            ").write_text('ran')\n").encode("utf-8"))
                result = subprocess.run(
                    [sys.executable, "-I", "-B", str(self.repo / "ci/skills_release.py"), "prepare",
                     "--windows", str(self.windows), "--ubuntu", str(self.ubuntu),
                     "--output", str(self.output), "--tag", self.tag, "--commit", self.commit],
                    cwd=self.base, capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(result.returncode, 1)
                self.assertFalse(marker.exists(), "modified build implementation executed before snapshot check")
                path.write_bytes(original)

    def test_cli_requires_python_isolated_mode(self):
        result = subprocess.run(
            [sys.executable, "-B", str(self.repo / "ci/skills_release.py"), "verify",
             "--directory", str(self.base), "--tag", self.tag, "--commit", self.commit],
            cwd=self.base, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertIn("isolated mode", result.stderr)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ci" / "verify_skills_reproducible.py"
spec = importlib.util.spec_from_file_location("skills_reproducibility", SCRIPT)
assert spec is not None and spec.loader is not None
repro = importlib.util.module_from_spec(spec)
spec.loader.exec_module(repro)


class SkillsReproducibilityTests(unittest.TestCase):
    VERSION = "3.0.0-dev.2"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="408-skills-repro-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.windows = self.root / "windows"
        self.ubuntu = self.root / "ubuntu"
        for directory in (self.windows, self.ubuntu):
            directory.mkdir()
            for platform in repro.PLATFORMS:
                (directory / self.name(platform)).write_bytes(b"archive-fixture:" + platform.encode())

    def name(self, platform):
        return f"408-agent-skills-{self.VERSION}-{platform}.zip"

    def compare(self):
        return repro.compare_archives(self.windows, self.ubuntu, self.VERSION)

    def test_all_three_archives_compared_and_metadata_allowed(self):
        (self.windows / "export-metadata.json").write_text("{}", encoding="utf-8")
        results = self.compare()
        self.assertEqual(set(results), {self.name(p) for p in repro.PLATFORMS})
        self.assertTrue(all(len(value) == 64 for value in results.values()))

    def test_each_platform_byte_difference_fails(self):
        for platform in repro.PLATFORMS:
            with self.subTest(platform=platform):
                archive = self.windows / self.name(platform)
                original = archive.read_bytes()
                archive.write_bytes(original + b"different")
                with self.assertRaisesRegex(ValueError, "bytes differ"):
                    self.compare()
                archive.write_bytes(original)

    def test_missing_archive_fails_even_if_both_hosts_missing(self):
        for directory in (self.windows, self.ubuntu):
            (directory / self.name("cursor")).unlink()
        with self.assertRaisesRegex(ValueError, "missing ZIP"):
            self.compare()

    def test_extra_archive_fails_even_if_both_hosts_have_it(self):
        for directory in (self.windows, self.ubuntu):
            (directory / "unexpected.zip").write_bytes(b"extra")
        with self.assertRaisesRegex(ValueError, "unexpected ZIP"):
            self.compare()

    def test_same_wrong_version_on_both_hosts_fails(self):
        for directory in (self.windows, self.ubuntu):
            for platform in repro.PLATFORMS:
                path = directory / self.name(platform)
                path.rename(path.with_name(path.name.replace(self.VERSION, "2.0.0")))
        with self.assertRaisesRegex(ValueError, "unexpected ZIP"):
            self.compare()

    def test_duplicate_archive_in_nested_directory_fails(self):
        nested = self.windows / "nested"
        nested.mkdir()
        (nested / self.name("codex")).write_bytes(b"duplicate")
        with self.assertRaisesRegex(ValueError, "unexpected ZIP"):
            self.compare()

    def test_missing_directory_fails(self):
        with self.assertRaisesRegex(ValueError, "directory is missing"):
            repro.compare_archives(self.root / "absent", self.ubuntu, self.VERSION)

    def test_link_rejected_before_archive_read(self):
        path = self.windows / self.name("codex")
        # Portable guard regression; the integration below covers real links
        # where the operating system permits creating them.
        original = repro._is_link
        with mock.patch.object(repro, "_is_link", side_effect=lambda p: p == path or original(p)):
            with self.assertRaisesRegex(ValueError, "linked artifact entry"):
                self.compare()

    def test_real_directory_symlink_rejected(self):
        linked = self.root / "linked"
        try:
            linked.symlink_to(self.windows, target_is_directory=True)
        except (OSError, NotImplementedError) as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        with self.assertRaisesRegex(ValueError, "linked artifact directory"):
            repro.compare_archives(linked, self.ubuntu, self.VERSION)

    def test_manifest_version_is_single_source_and_rejects_paths(self):
        manifest = self.root / "skillset.json"
        manifest.write_text(json.dumps({"version": "4.1.2-dev.9"}), encoding="utf-8")
        self.assertEqual(repro.read_version(manifest), "4.1.2-dev.9")
        manifest.write_text(json.dumps({"version": "../../escape"}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "filename-safe"):
            repro.read_version(manifest)

    def test_cli_returns_nonzero_for_missing_artifacts(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), str(self.root / "missing"), str(self.ubuntu)],
            cwd=self.root, capture_output=True, text=True, check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("[FAIL]", result.stderr)


if __name__ == "__main__":
    unittest.main()

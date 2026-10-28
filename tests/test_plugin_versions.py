from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts/sync_plugin_versions.py"
SOURCE = "plugins/kaoyan-408/.codex-plugin/plugin.json"
MANIFESTS = (
    "plugins/kaoyan-408/.zcode-plugin/plugin.json",
    "plugins/kaoyan-408/.codebuddy-plugin/plugin.json",
    ".cursor-plugin/plugin.json",
    "plugins/kaoyan-408/.claude-plugin/plugin.json",
)
MARKETPLACES = (
    ".claude-plugin/marketplace.json",
    ".codebuddy-plugin/marketplace.json",
)
CLAUDE = "plugins/kaoyan-408/.claude-plugin/plugin.json"


class PluginVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name).resolve()
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.backup = self.base / "backup"
        self.write_json(SOURCE, {"name": "kaoyan-408", "version": "2.8.0-dev.1"})
        for name in MANIFESTS:
            self.write_json(name, {
                "name": "kaoyan-408", "version": "2.7.0", "displayName": "宿主展示",
                "skills": "./skills", "hostOnly": {"enabled": True},
            })
        for name in MARKETPLACES:
            self.write_json(name, {
                "metadata": {"version": "1.0.0"},
                "plugins": [
                    {"name": "other-plugin", "version": "0.4.0", "source": "./other"},
                    {"name": "kaoyan-408", "version": "2.7.0", "source": "./plugins/kaoyan-408"},
                ],
            })
        self.write_json("tests/system-validator-evidence.json", {"plugin": {"version": "2.7.0"}, "proof": "preserve"})

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_json(self, relative: str, value: dict) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")

    def read_json(self, relative: str) -> dict:
        return json.loads((self.repo / relative).read_text(encoding="utf-8"))

    def snapshot(self) -> dict[str, bytes]:
        return {p.relative_to(self.repo).as_posix(): p.read_bytes() for p in self.repo.rglob("*") if p.is_file()}

    def run_tool(self, *arguments: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--repo", str(self.repo), *arguments],
            capture_output=True, text=True, encoding="utf-8", check=False,
        )

    def sync(self) -> subprocess.CompletedProcess:
        return self.run_tool("--write", "--backup-dir", str(self.backup))

    def assert_rejected_without_writes(self) -> None:
        before = self.snapshot()
        result = self.sync()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("ERROR", result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.backup.exists())

    def test_check_reports_drift_without_writing_or_backing_up(self) -> None:
        before = self.snapshot()
        result = self.run_tool("--check", "--backup-dir", str(self.backup))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("2.8.0-dev.1", result.stdout)
        for name in (*MANIFESTS, *MARKETPLACES):
            self.assertIn(name, result.stdout)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.backup.exists())

    def test_write_changes_only_plugin_versions_and_creates_exact_backups(self) -> None:
        before = self.snapshot()
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.repo / SOURCE).read_bytes(), before[SOURCE])
        evidence = "tests/system-validator-evidence.json"
        self.assertEqual((self.repo / evidence).read_bytes(), before[evidence])
        for name in MANIFESTS:
            expected = json.loads(before[name])
            expected["version"] = "2.8.0-dev.1"
            self.assertEqual(self.read_json(name), expected)
        for name in MARKETPLACES:
            expected = json.loads(before[name])
            expected["plugins"][1]["version"] = "2.8.0-dev.1"
            self.assertEqual(self.read_json(name), expected)
        for name in (*MANIFESTS, *MARKETPLACES):
            self.assertEqual((self.backup / name).read_bytes(), before[name])
        self.assertEqual(len(list(self.backup.rglob("*.json"))), 6)
        self.assertEqual(self.run_tool("--check").returncode, 0)

    def test_unchanged_write_preserves_all_bytes_and_makes_no_backup(self) -> None:
        self.assertEqual(self.sync().returncode, 0)
        before = self.snapshot()
        unused = self.base / "unused-backup"
        result = self.run_tool("--write", "--backup-dir", str(unused))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(unused.exists())

    def test_required_claude_manifest_is_synced_and_preserves_other_fields(self) -> None:
        self.write_json(CLAUDE, {"name": "kaoyan-408", "version": "2.7.0", "custom": "kept"})
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.read_json(CLAUDE), {"name": "kaoyan-408", "version": "2.8.0-dev.1", "custom": "kept"})

    def test_missing_claude_manifest_is_rejected_without_any_writes(self) -> None:
        (self.repo / CLAUDE).unlink()
        self.assert_rejected_without_writes()
        result = self.run_tool("--check")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn(".claude-plugin", result.stderr)

    def test_default_backup_is_created_outside_repository(self) -> None:
        before = self.snapshot()
        environment = os.environ.copy()
        for name in ("TMPDIR", "TMP", "TEMP"):
            environment[name] = str(self.base)
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--repo", str(self.repo), "--write"],
            capture_output=True, text=True, encoding="utf-8", check=False, env=environment,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        backups = list(self.base.glob("kaoyan-408-version-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertFalse(backups[0].resolve().is_relative_to(self.repo.resolve()))
        for name in (*MANIFESTS, *MARKETPLACES):
            self.assertEqual((backups[0] / name).read_bytes(), before[name])

    def test_missing_required_manifest_is_rejected(self) -> None:
        (self.repo / MANIFESTS[1]).unlink()
        self.assert_rejected_without_writes()

    def test_invalid_last_json_is_rejected_before_any_write(self) -> None:
        (self.repo / MARKETPLACES[-1]).write_text("{ broken", encoding="utf-8")
        self.assert_rejected_without_writes()

    def test_duplicate_json_keys_are_rejected(self) -> None:
        (self.repo / SOURCE).write_text('{"name":"kaoyan-408","version":"2.8.0","version":"2.9.0"}', encoding="utf-8")
        self.assert_rejected_without_writes()

    def test_nonstandard_json_constants_are_rejected(self) -> None:
        (self.repo / MARKETPLACES[-1]).write_text('{"plugins": NaN}', encoding="utf-8")
        self.assert_rejected_without_writes()

    def test_invalid_source_versions_are_rejected(self) -> None:
        for version in ("2.8", "v2.8.0", "02.8.0", "2.8.0-01", "2.8.0-", "2.8.0\n", 28, None):
            with self.subTest(version=version):
                self.write_json(SOURCE, {"name": "kaoyan-408", "version": version})
                self.assert_rejected_without_writes()

    def test_valid_prerelease_is_accepted(self) -> None:
        self.write_json(SOURCE, {"name": "kaoyan-408", "version": "2.8.0-rc.1"})
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.read_json(MANIFESTS[0])["version"], "2.8.0-rc.1")

    def test_build_metadata_rejected_by_repository_policy_is_not_propagated(self) -> None:
        self.write_json(SOURCE, {"name": "kaoyan-408", "version": "2.8.0-rc.1+build.007"})
        self.assert_rejected_without_writes()

    def test_malformed_target_version_is_rejected(self) -> None:
        doc = self.read_json(MANIFESTS[0])
        doc["version"] = "not-a-version"
        self.write_json(MANIFESTS[0], doc)
        self.assert_rejected_without_writes()

    def test_wrong_manifest_identity_is_rejected(self) -> None:
        self.write_json(MANIFESTS[0], {"name": "other-plugin", "version": "1.0.0"})
        self.assert_rejected_without_writes()

    def test_missing_or_duplicate_marketplace_entry_is_rejected(self) -> None:
        for entries in ([], [{"name": "kaoyan-408", "version": "1.0.0"}] * 2):
            with self.subTest(entries=entries):
                self.write_json(MARKETPLACES[0], {"plugins": entries})
                self.assert_rejected_without_writes()

    def test_backup_inside_repo_is_rejected(self) -> None:
        before = self.snapshot()
        result = self.run_tool("--write", "--backup-dir", str(self.repo / "backup"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.repo / "backup").exists())

    def test_existing_backup_directory_is_never_overwritten(self) -> None:
        self.backup.mkdir()
        marker = self.backup / "keep.txt"
        marker.write_text("keep", encoding="utf-8")
        before = self.snapshot()
        result = self.sync()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def create_symlink(self, path: Path, target: Path, directory: bool = False) -> None:
        try:
            path.symlink_to(target, target_is_directory=directory)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")

    def test_manifest_symlink_is_rejected_even_when_target_is_inside_repo(self) -> None:
        target = self.repo / "other.json"
        target.write_bytes((self.repo / MANIFESTS[0]).read_bytes())
        (self.repo / MANIFESTS[0]).unlink()
        self.create_symlink(self.repo / MANIFESTS[0], target)
        self.assert_rejected_without_writes()

    def test_parent_directory_symlink_cannot_escape_repo(self) -> None:
        path = self.repo / ".cursor-plugin/plugin.json"
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "plugin.json").write_bytes(path.read_bytes())
        path.unlink()
        path.parent.rmdir()
        self.create_symlink(path.parent, outside, directory=True)
        self.assert_rejected_without_writes()
        self.assertEqual(json.loads((outside / "plugin.json").read_text(encoding="utf-8"))["version"], "2.7.0")

    def test_backup_symlink_is_rejected(self) -> None:
        outside = self.base / "outside-backup"
        outside.mkdir()
        self.create_symlink(self.backup, outside, directory=True)
        before = self.snapshot()
        result = self.sync()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(list(outside.iterdir()), [])

    def test_mode_must_be_explicit_and_mutually_exclusive(self) -> None:
        before = self.snapshot()
        self.assertEqual(self.run_tool().returncode, 2)
        self.assertEqual(self.run_tool("--check", "--write").returncode, 2)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()

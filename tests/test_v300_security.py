"""Independent security gates for the three-skill source and Git history."""
from __future__ import annotations

import importlib.util
import io
import os
from pathlib import Path
import shutil
import subprocess
import stat
import tempfile
import unittest
import warnings
import zipfile
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools" / "check_security.py"
spec = importlib.util.spec_from_file_location("v300_security", SCRIPT)
if SCRIPT.is_file() and spec is not None and spec.loader is not None:
    security = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(security)
else:
    security = None


def fake_secrets() -> list[tuple[str, str]]:
    return [
        ("github", "ghp_" + "A" * 20),
        ("github-pat", "github_pat_" + "A" * 20),
        ("openai", "sk-" + "A" * 20),
        ("figma", "figd_" + "A" * 20),
        ("aws-id", "AKIA" + "A" * 16),
        ("google", "AIza" + "A" * 30),
        ("slack", "xoxb-" + "A" * 10),
        ("npm", "npm_" + "A" * 20),
        ("gitlab", "glpat-" + "A" * 20),
        ("jwt", "eyJ" + "A" * 8 + "." + "B" * 10 + "." + "C" * 10),
        ("aws-secret-assignment", "aws_secret_access_key=" + "A" * 30),
        ("account-key", "AccountKey=" + "A" * 40),
        ("private-key", "-----BEGIN RSA " + "PRIVATE KEY-----"),
        ("pgp-key", "-----BEGIN PGP " + "PRIVATE KEY BLOCK-----"),
        ("generic-secret", "api_key=" + "A" * 16),
    ]


def frozen_zip(members, compression=zipfile.ZIP_STORED):
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(buffer, "w", compression=compression) as archive:
            for name, content in sorted(members):
                entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | 0o644) << 16
                entry.compress_type = compression
                archive.writestr(entry, content)
    return buffer.getvalue()


class LegacySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(security, "_snapshot_findings"), "member-aware frozen snapshot scan is missing")

    def scan(self, payload):
        found = set()
        security._snapshot_findings(payload, b"legacy/frozen.zip", found)
        security._raise_findings("snapshot", found)

    def test_only_original_definition_paths_keep_marker_exemption(self):
        marker = b"bai" + b"du"
        self.scan(frozen_zip([(".semgrep.yml", marker), ("README.md", b"source context")]))
        with self.assertRaises(security.SecurityError):
            self.scan(frozen_zip([("nested/.semgrep.yml", marker)]))

    def test_secrets_and_private_member_paths_still_fail(self):
        secret = fake_secrets()[0][1]
        for name, content in ((".semgrep.yml", secret.encode()), ("README.md", b"bai" + b"du"),
                              ("corpus/private.txt", b"private source")):
            with self.subTest(name=name):
                with self.assertRaises(security.SecurityError) as caught:
                    self.scan(frozen_zip([(name, content)]))
                self.assertNotIn(secret, str(caught.exception))

    def test_noncanonical_unsafe_compressed_and_nested_archives_fail(self):
        valid = frozen_zip([("README.md", b"context")])
        invalid = [b"not a zip", b"prefix" + valid, valid + b"suffix",
                   frozen_zip([("../escape.md", b"context")]),
                   frozen_zip([("README.md", b"a"), ("README.md", b"b")]),
                   frozen_zip([("README.md", b"context")], zipfile.ZIP_DEFLATED),
                   frozen_zip([("nested.zip", valid)])]
        for payload in invalid:
            with self.subTest(length=len(payload)):
                with self.assertRaises(security.SecurityError): self.scan(payload)

    def test_member_count_and_byte_limits_are_enforced(self):
        payload = frozen_zip([("README.md", b"a" * 32)])
        with patch.object(security, "MAX_SNAPSHOT_BYTES", 16):
            with self.assertRaises(security.SecurityError): self.scan(payload)
        with patch.object(security, "MAX_SNAPSHOT_MEMBERS", 0):
            with self.assertRaises(security.SecurityError): self.scan(payload)


class CurrentSourceGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(security, "the independent security gate has not been implemented")
        self.temporary = tempfile.TemporaryDirectory(prefix="408-security-source-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copyfile(REPO / "skillset.json", self.root / "skillset.json")
        shutil.copyfile(REPO / "LICENSE", self.root / "LICENSE")
        shutil.copytree(REPO / "src", self.root / "src")
        self.skill = self.root / "src/skills/408-concept-followup/SKILL.md"
        self.original_skill = self.skill.read_bytes()

    def test_each_legacy_sensitive_type_is_rejected_without_echoing_value(self):
        for label, secret in fake_secrets():
            with self.subTest(kind=label):
                self.skill.write_bytes(self.original_skill + b"\n" + secret.encode("ascii") + b"\n")
                with self.assertRaises(security.SecurityError) as caught:
                    security.scan_current_sources(self.root)
                self.assertNotIn(secret, str(caught.exception))
                self.skill.write_bytes(self.original_skill)

    def test_removed_system_markers_are_rejected_in_current_source(self):
        for marker in ("bai" + "du", "net" + "disk", "local" + "storage", "study" + "-state"):
            with self.subTest(marker=marker):
                self.skill.write_bytes(self.original_skill + b"\n" + marker.encode("ascii") + b"\n")
                with self.assertRaises(security.SecurityError) as caught:
                    security.scan_current_sources(self.root)
                self.assertNotIn(marker, str(caught.exception))
                self.skill.write_bytes(self.original_skill)

    def test_private_source_path_is_rejected_even_if_not_declared_for_export(self):
        private = self.root / "src" / "user" / "notes.md"
        private.parent.mkdir()
        private.write_text("fixture", encoding="utf-8")
        with self.assertRaises(security.SecurityError):
            security.scan_current_sources(self.root)


class GitHistoryGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(security, "the independent security gate has not been implemented")
        self.temporary = tempfile.TemporaryDirectory(prefix="408-security-git-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "repo"
        self.root.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Security Test")
        self.git("config", "user.email", "security-test@example.invalid")
        self.commit_file("README.md", "clean history\n", "initial")

    def git(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        return subprocess.run(["git", *args], cwd=self.root, capture_output=True, check=True)

    def commit_file(self, name: str, content: str, message: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self.git("add", "--all")
        self.git("commit", "-m", message)

    def assert_history_rejected_without_echo(self, secret: str | None = None) -> None:
        with self.assertRaises(security.SecurityError) as caught:
            security.scan_git_history(self.root)
        if secret:
            self.assertNotIn(secret, str(caught.exception))

    def test_secret_in_deleted_blob_remains_detectable(self):
        secret = fake_secrets()[1][1]
        self.commit_file("old.txt", secret + "\n", "add temporary file")
        (self.root / "old.txt").unlink()
        self.git("add", "--all")
        self.git("commit", "-m", "remove temporary file")
        self.assert_history_rejected_without_echo(secret)

    def test_commit_and_annotated_tag_messages_are_scanned(self):
        secret = fake_secrets()[2][1]
        self.commit_file("commit-message.txt", "clean blob\n", "review " + secret)
        self.assert_history_rejected_without_echo(secret)

    def test_annotated_tag_message_is_scanned_with_clean_commits(self):
        secret = fake_secrets()[3][1]
        self.git("tag", "-a", "v-security-fixture", "-m", "release " + secret)
        self.assert_history_rejected_without_echo(secret)

    def test_object_only_on_a_nonchecked_out_branch_is_scanned(self):
        secret = fake_secrets()[4][1]
        self.git("switch", "-c", "side-only")
        self.commit_file("side.txt", secret + "\n", "side branch change")
        self.git("switch", "main")
        self.assert_history_rejected_without_echo(secret)

    def test_historical_private_path_is_detected_after_deletion(self):
        self.commit_file("corpus/private.txt", "no secret\n", "temporary corpus")
        (self.root / "corpus/private.txt").unlink()
        (self.root / "corpus").rmdir()
        self.git("add", "--all")
        self.git("commit", "-m", "remove corpus")
        self.assert_history_rejected_without_echo()

    def test_shallow_repository_is_rejected_instead_of_claiming_complete_history(self):
        self.commit_file("second.txt", "clean\n", "second commit")
        shallow = self.root.parent / "shallow"
        subprocess.run(["git", "clone", "--depth=1", "--no-local", str(self.root), str(shallow)],
                       capture_output=True, check=True)
        with self.assertRaises(security.SecurityError) as caught:
            security.scan_git_history(shallow)
        self.assertIn("shallow", str(caught.exception).lower())

    def test_blob_reachable_only_from_custom_ref_is_scanned(self):
        secret = fake_secrets()[0][1]
        blob = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"], cwd=self.root,
            input=secret.encode("ascii"), capture_output=True, check=True,
        ).stdout.decode("ascii").strip()
        self.git("update-ref", "refs/custom/blob", blob)
        self.assert_history_rejected_without_echo(secret)

    def test_replace_ref_cannot_hide_committed_secret_blob(self):
        secret = fake_secrets()[0][1]
        self.commit_file("secret.txt", secret, "fixture")
        secret_blob = self.git("rev-parse", "HEAD:secret.txt").stdout.decode("ascii").strip()
        clean_blob = self.git("rev-parse", "HEAD:README.md").stdout.decode("ascii").strip()
        self.git("replace", secret_blob, clean_blob)
        self.assert_history_rejected_without_echo(secret)

    def test_custom_tree_ref_checks_private_path(self):
        clean_blob = self.git("rev-parse", "HEAD:README.md").stdout.strip()
        tree = subprocess.run(
            ["git", "mktree"], cwd=self.root,
            input=b"100644 blob " + clean_blob + b"\tcorpus\n",
            capture_output=True, check=True,
        ).stdout.decode("ascii").strip()
        self.git("update-ref", "refs/custom/tree", tree)
        self.assert_history_rejected_without_echo()

    def test_success_counts_standalone_blobs_and_annotated_tags(self):
        blob = subprocess.run(
            ["git", "hash-object", "-w", "--stdin"], cwd=self.root,
            input=b"clean standalone", capture_output=True, check=True,
        ).stdout.decode("ascii").strip()
        self.git("tag", "-a", "blob-tag", blob, "-m", "clean tag")
        result = security.scan_git_history(self.root)
        self.assertTrue(result["valid"])
        self.assertEqual(result["blobsScanned"], 2)
        self.assertEqual(result["tagsScanned"], 1)

    def test_git_stderr_is_not_echoed(self):
        secret = fake_secrets()[0][1]
        failure = subprocess.CompletedProcess([], 128, b"", secret.encode("ascii"))
        with patch.object(security.subprocess, "run", return_value=failure):
            with self.assertRaises(security.SecurityError) as caught:
                security._run_git(self.root, ["rev-list", "--all"])
        self.assertNotIn(secret, str(caught.exception))
        self.assertIn("exit=128", str(caught.exception))

    def test_git_scan_disables_network_fetch_and_history_overrides(self):
        success = subprocess.CompletedProcess([], 0, b"ok", b"")
        with patch.object(security.subprocess, "run", return_value=success) as run:
            security._run_git(self.root, ["rev-list", "--all"])
        self.assertIn("--no-replace-objects", run.call_args.args[0])
        self.assertEqual(run.call_args.kwargs["env"]["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(run.call_args.kwargs["env"]["GIT_GRAFT_FILE"], os.devnull)

    def test_graft_cannot_hide_deleted_secret_in_ancestor(self):
        secret = fake_secrets()[0][1]
        self.commit_file("secret.txt", secret, "fixture")
        (self.root / "secret.txt").unlink()
        self.git("add", "--all")
        self.git("commit", "-m", "remove fixture")
        head = self.git("rev-parse", "HEAD").stdout
        (self.root / ".git/info/grafts").write_bytes(head)
        self.assert_history_rejected_without_echo(secret)

    def test_frozen_legacy_snapshot_is_scanned_by_member_paths(self):
        path = self.root / "legacy/frozen.zip"
        path.parent.mkdir()
        path.write_bytes(frozen_zip([(".semgrep.yml", b"rule: " + b"bai" + b"du\n"),
                                    ("plugins/kaoyan-408/skills/example/SKILL.md", b"original source")]))
        self.git("add", "--all")
        self.git("commit", "-m", "frozen context")
        self.assertTrue(security.scan_git_history(self.root)["valid"])


if __name__ == "__main__":
    unittest.main()

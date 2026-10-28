"""The complete-plugin gate must scan frozen context by member paths."""
from __future__ import annotations

import io
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from validate_repository import ValidationError, check_git_history


def snapshot(members, compression=zipfile.ZIP_STORED):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        for name, content in sorted(members):
            entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | 0o644) << 16
            entry.compress_type = compression
            archive.writestr(entry, content)
    return output.getvalue()


class CompletePluginSnapshotHistoryTests(unittest.TestCase):
    def check(self, members, compression=zipfile.ZIP_STORED):
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            def git(*arguments):
                subprocess.run(["git", *arguments], cwd=repo, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            git("init", "-b", "main")
            git("config", "user.name", "Snapshot Test")
            git("config", "user.email", "snapshot@example.invalid")
            git("config", "commit.gpgsign", "false")
            (repo / "legacy").mkdir()
            (repo / "legacy/frozen.zip").write_bytes(snapshot(members, compression))
            git("add", ".")
            git("commit", "-m", "frozen context fixture")
            check_git_history(repo)

    def test_original_marker_definition_member_is_allowed(self):
        self.check([(".semgrep.yml", b"bai" + b"du\n"), ("README.md", b"context")])

    def test_nested_definition_does_not_gain_marker_exemption(self):
        with self.assertRaisesRegex(ValidationError, "unsafe legacy snapshot"):
            self.check([("nested/.semgrep.yml", b"bai" + b"du")])

    def test_private_member_path_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "unsafe legacy snapshot"):
            self.check([("corpus/private-note.txt", b"context")])

    def test_marker_exemption_never_exempts_member_secrets(self):
        with self.assertRaises(ValidationError):
            self.check([(".semgrep.yml", b"ghp_" + b"A" * 24)])

    def test_compressed_noncanonical_archive_is_rejected(self):
        with self.assertRaisesRegex(ValidationError, "unsafe legacy snapshot"):
            self.check([("README.md", b"context")], zipfile.ZIP_DEFLATED)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from check import (  # noqa: E402
    main,
    run as run_check_command,
    pinned_requirement_version,
    verify_python_dependency_versions,
    verify_semgrep_version,
)


class CheckScriptTests(unittest.TestCase):
    def test_semgrep_pin_is_read_from_requirements(self) -> None:
        self.assertEqual(
            pinned_requirement_version(REPO / "requirements-dev.txt", "semgrep"),
            "1.162.0",
        )

    def test_semgrep_version_mismatch_is_rejected(self) -> None:
        result = subprocess.CompletedProcess(["semgrep", "--version"], 0, "1.146.0\n", "")
        with patch("check.subprocess.run", return_value=result):
            with self.assertRaisesRegex(RuntimeError, "expected 1.162.0"):
                verify_semgrep_version("semgrep", "1.162.0", REPO, {})

    def test_python_dependency_versions_match_pins(self) -> None:
        verify_python_dependency_versions(
            REPO / "requirements-dev.txt",
            ("PyYAML", "jsonschema"),
        )

    def test_check_entry_point_stops_on_version_drift_before_later_gates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = Path(temporary) / "repo"
            files = (
                "requirements-dev.txt", "scripts/release_payload.py", "scripts/sync_plugin_versions.py",
                "plugins/kaoyan-408/.codex-plugin/plugin.json",
                "plugins/kaoyan-408/.zcode-plugin/plugin.json",
                "plugins/kaoyan-408/.codebuddy-plugin/plugin.json",
                "plugins/kaoyan-408/.claude-plugin/plugin.json",
                ".cursor-plugin/plugin.json", ".claude-plugin/marketplace.json", ".codebuddy-plugin/marketplace.json",
            )
            for relative in files:
                target = fixture / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(REPO / relative, target)
            cursor_path = fixture / ".cursor-plugin/plugin.json"
            cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
            cursor["version"] = "9.9.9"
            cursor_path.write_text(json.dumps(cursor) + "\n", encoding="utf-8", newline="\n")
            before = {p.relative_to(fixture): p.read_bytes() for p in fixture.rglob("*") if p.is_file()}
            with patch("check.__file__", str(fixture / "scripts/check.py")), patch(
                "check.sys.argv", ["check.py", "--skip-system-validators"]
            ), patch("check.run", wraps=run_check_command) as runner:
                with self.assertRaises(subprocess.CalledProcessError) as failure:
                    main()
            self.assertEqual(failure.exception.returncode, 1)
            self.assertEqual(runner.call_count, 1)
            self.assertEqual(runner.call_args.args[0][1:], ["scripts/sync_plugin_versions.py", "--check"])
            self.assertEqual(
                {p.relative_to(fixture): p.read_bytes() for p in fixture.rglob("*") if p.is_file()}, before,
            )

    def test_matching_semgrep_version_passes(self) -> None:
        result = subprocess.CompletedProcess(["semgrep", "--version"], 0, "semgrep 1.162.0\n", "")
        with patch("check.subprocess.run", return_value=result):
            verify_semgrep_version("semgrep", "1.162.0", REPO, {})


if __name__ == "__main__":
    unittest.main()

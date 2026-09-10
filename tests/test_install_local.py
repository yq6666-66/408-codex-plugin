from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:  # Support both unittest discovery and tests.test_* module execution.
    from .test_support import copy_as_committed_repo  # type: ignore[import-not-found]
except ImportError:
    from test_support import copy_as_committed_repo  # type: ignore[no-redef]


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from install_local import (  # noqa: E402
    VerifyError,
    _relay,
    install_local,
    parse_marketplace_json,
    verify_plugin_tree,
    verify_release_bundle,
)
from release_payload import ALLOWED_RELEASE_FILES  # noqa: E402


def completed(command: list[str], code: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, code, stdout, stderr)


class ScriptedRunner:
    def __init__(self, results: list[subprocess.CompletedProcess[str]]) -> None:
        self.results = list(results)
        self.commands: list[list[str]] = []

    def __call__(self, command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        self.commands.append(command)
        if not self.results:
            raise AssertionError(f"unexpected command: {command}")
        return self.results.pop(0)


def json_listing(entries: list[dict]) -> str:
    return json.dumps({"marketplaces": entries}, ensure_ascii=False)


class ScriptedInstallerTests(unittest.TestCase):
    def test_relay_escapes_characters_unsupported_by_console_encoding(self) -> None:
        raw = io.BytesIO()
        stream = io.TextIOWrapper(raw, encoding="ascii", newline="\n")
        _relay(completed(["check"], stdout="✅ checks passed"), stream)
        stream.flush()
        self.assertIn(b"\\u2705 checks passed", raw.getvalue())

    def run_installer(
        self,
        results: list[subprocess.CompletedProcess[str]],
        *,
        validate_only: bool = False,
        codex: str | None = "codex",
    ) -> tuple[int, str, str, ScriptedRunner]:
        runner = ScriptedRunner(results)
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = install_local(
            REPO,
            validate_only=validate_only,
            runner=runner,
            which=lambda _: codex,
            stdout=stdout,
            stderr=stderr,
        )
        return code, stdout.getvalue(), stderr.getvalue(), runner

    def test_validate_only_returns_zero_without_codex(self) -> None:
        code, stdout, stderr, runner = self.run_installer(
            [completed(["check"], stdout="checks passed")],
            validate_only=True,
            codex=None,
        )
        self.assertEqual(code, 0)
        self.assertIn("Validation completed", stdout)
        self.assertNotIn("Installed", stdout)
        self.assertEqual(stderr, "")
        self.assertEqual(len(runner.commands), 1)
        self.assertIn("--skip-system-validators", runner.commands[0])

    def test_validation_failure_returns_one(self) -> None:
        code, stdout, stderr, _ = self.run_installer(
            [completed(["check"], code=1, stderr="bad repository")]
        )
        self.assertEqual(code, 1)
        self.assertNotIn("Installed", stdout)
        self.assertIn("Validation failed", stderr)

    def test_missing_or_unsupported_codex_returns_two(self) -> None:
        code, stdout, stderr, _ = self.run_installer(
            [completed(["check"])],
            codex=None,
        )
        self.assertEqual(code, 2)
        self.assertNotIn("Installed", stdout)
        self.assertIn("Desktop", stderr)

        code, stdout, stderr, _ = self.run_installer(
            [completed(["check"]), completed(["codex", "plugin"], code=2, stderr="unknown command")]
        )
        self.assertEqual(code, 2)
        self.assertNotIn("Installed", stdout)
        self.assertIn("no usable plugin subcommand", stderr)

        code, stdout, stderr, _ = self.run_installer(
            [
                completed(["check"]),
                completed(["codex", "plugin"], stdout="Codex CLI\nCommands: exec mcp help\n"),
            ]
        )
        self.assertEqual(code, 2)
        self.assertNotIn("Installed", stdout)
        self.assertIn("no usable plugin subcommand", stderr)

    def test_success_with_json_listing_adds_missing_marketplace_then_installs(self) -> None:
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            completed(["list-json"], stdout=json_listing([{"name": "personal", "source": {"source": "local", "path": "C:/somewhere"}}])),
            completed(["marketplace-add"]),
            completed(["plugin-add"]),
            completed(["plugin-list"], stdout="kaoyan-408 enabled\n"),
        ]
        code, stdout, stderr, runner = self.run_installer(results)
        self.assertEqual(code, 0)
        self.assertIn("Installed kaoyan-408", stdout)
        self.assertEqual(stderr, "")
        self.assertEqual(runner.commands[-3][-3:-1], ["marketplace", "add"])
        self.assertEqual(runner.commands[-2][-2:], ["add", "kaoyan-408@kaoyan-408"])

    def test_local_marketplace_pointing_at_repo_skips_add(self) -> None:
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            completed(
                ["list-json"],
                stdout=json_listing(
                    [{"name": "kaoyan-408", "source": {"source": "local", "path": str(REPO.resolve())}}]
                ),
            ),
            completed(["plugin-add"]),
            completed(["plugin-list"], stdout="kaoyan-408 enabled\n"),
        ]
        code, stdout, _, runner = self.run_installer(results)
        self.assertEqual(code, 0)
        self.assertIn("Installed", stdout)
        self.assertEqual(len(runner.commands), 5)

    def test_git_marketplace_with_official_slug_skips_add(self) -> None:
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            completed(
                ["list-json"],
                stdout=json_listing(
                    [
                        {
                            "name": "kaoyan-408",
                            "source": {"source": "git", "repo": "https://github.com/yq6666-66/408-codex-plugin"},
                        }
                    ]
                ),
            ),
            completed(["plugin-add"]),
            completed(["plugin-list"], stdout="kaoyan-408 enabled\n"),
        ]
        code, stdout, stderr, runner = self.run_installer(results)
        self.assertEqual(code, 0)
        self.assertIn("Installed", stdout)
        self.assertEqual(stderr, "")
        self.assertEqual(len(runner.commands), 5)

    def test_same_name_git_marketplace_with_other_slug_is_rejected(self) -> None:
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            completed(
                ["list-json"],
                stdout=json_listing(
                    [{"name": "kaoyan-408", "source": {"source": "git", "repo": "https://github.com/someone/kaoyan-408-fork"}}]
                ),
            ),
        ]
        code, stdout, stderr, runner = self.run_installer(results)
        self.assertEqual(code, 1)
        self.assertNotIn("Installed", stdout)
        self.assertIn("cannot be verified", stderr)
        self.assertIn("expected one of", stderr)
        self.assertEqual(len(runner.commands), 3)

    def test_cache_directory_source_is_never_treated_as_repo(self) -> None:
        cache_location = str(Path.home() / ".codex" / "plugins" / "cache" / "kaoyan-408" / "abc123")
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            completed(
                ["list-json"],
                stdout=json_listing(
                    [{"name": "kaoyan-408", "source": {"source": "local", "path": cache_location}}]
                ),
            ),
        ]
        code, stdout, stderr, runner = self.run_installer(results)
        self.assertEqual(code, 1)
        self.assertNotIn("Installed", stdout)
        self.assertIn("cache directory", stderr)
        self.assertEqual(len(runner.commands), 3)

    def test_same_name_with_unverified_text_source_is_rejected(self) -> None:
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            # JSON unsupported (not JSON output) -> legacy text fallback
            completed(["list"], code=1),
            completed(["list"], stdout="kaoyan-408  C:/different/repository"),
        ]
        code, stdout, stderr, runner = self.run_installer(results)
        self.assertEqual(code, 1)
        self.assertNotIn("Installed", stdout)
        self.assertIn("cannot be verified", stderr)

    def test_same_name_with_repo_path_suffix_is_rejected(self) -> None:
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            completed(["list"], code=1),
            completed(["list"], stdout=f"kaoyan-408  {REPO.resolve()}-shadow"),
        ]
        code, stdout, stderr, _ = self.run_installer(results)
        self.assertEqual(code, 1)
        self.assertNotIn("Installed", stdout)
        self.assertIn("cannot be verified", stderr)

    def test_legacy_plugin_warning_only_after_success(self) -> None:
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            completed(
                ["list-json"],
                stdout=json_listing(
                    [{"name": "kaoyan-408", "source": {"source": "local", "path": str(REPO.resolve())}}]
                ),
            ),
            completed(["plugin-add"]),
            completed(["plugin-list"], stdout="kaoyan-408 enabled\nkaoyan-22408 enabled\n"),
        ]
        code, stdout, stderr, _ = self.run_installer(results)
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Verify kaoyan-408", stdout)
        self.assertIn("kaoyan-22408", stdout)

    def test_failed_install_never_prints_installed(self) -> None:
        results = [
            completed(["check"]),
            completed(["help"], stdout="Usage: codex plugin"),
            completed(
                ["list-json"],
                stdout=json_listing(
                    [{"name": "kaoyan-408", "source": {"source": "local", "path": str(REPO.resolve())}}]
                ),
            ),
            completed(["plugin-add"], code=1, stderr="install failed"),
        ]
        code, stdout, stderr, _ = self.run_installer(results)
        self.assertEqual(code, 1)
        self.assertNotIn("Installed", stdout)
        self.assertIn("Unable to install", stderr)


class MarketplaceJsonParsingTests(unittest.TestCase):
    def test_parses_official_json_shapes(self) -> None:
        entries = parse_marketplace_json(
            json.dumps(
                {
                    "marketplaces": [
                        {"name": "kaoyan-408", "source": {"source": "git", "repo": "yq6666-66/408-codex-plugin"}},
                        {"name": "personal", "source": {"source": "local", "path": "D:/repos/x"}},
                    ]
                }
            )
        )
        assert entries is not None
        self.assertEqual(entries[0]["kind"], "git")
        self.assertEqual(entries[0]["location"], "yq6666-66/408-codex-plugin")
        self.assertEqual(entries[1]["kind"], "local")

    def test_non_json_output_returns_none(self) -> None:
        self.assertIsNone(parse_marketplace_json("kaoyan-408  C:/repos/plugin"))
        self.assertIsNone(parse_marketplace_json(""))


class ConsumerVerificationTests(unittest.TestCase):
    """Consumer fixed-version verification must be hash-based and time-independent."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture_repo = copy_as_committed_repo(self.root / "repo")
        sys.path.insert(0, str(self.fixture_repo / "scripts"))

    def tearDown(self) -> None:
        sys.path.remove(str(self.fixture_repo / "scripts"))
        self.temporary.cleanup()

    def build_archive(self, name: str) -> tuple[Path, str, str]:
        from build_release import build_archive

        artifact = build_archive(self.fixture_repo, self.root / name)
        return artifact.archive, artifact.digest, artifact.version

    def test_valid_bundle_verifies_with_hash_and_version(self) -> None:
        archive, digest, version = self.build_archive("valid.zip")
        result = verify_release_bundle(archive, expected_sha256=digest, expected_version=version)
        self.assertEqual(result["version"], version)
        self.assertEqual(int(result["files"]), len(ALLOWED_RELEASE_FILES))

    def test_verification_is_independent_of_publication_age(self) -> None:
        """31 days and one year after publication a hash-correct pinned version still verifies."""
        archive, digest, version = self.build_archive("aged.zip")
        utc_now = datetime.now(timezone.utc)
        for age in (timedelta(days=31), timedelta(days=365)):
            with self.subTest(age=age):
                result = verify_release_bundle(
                    archive,
                    expected_sha256=digest,
                    expected_version=version,
                    now=utc_now + age,
                )
                self.assertEqual(result["version"], version)

    def test_hash_mismatch_is_rejected_with_reason(self) -> None:
        archive, digest, version = self.build_archive("hash.zip")
        with self.assertRaisesRegex(VerifyError, "SHA-256 mismatch"):
            verify_release_bundle(archive, expected_sha256="0" * 64, expected_version=version)
        self.assertEqual(len(digest), 64)

    def test_version_mismatch_is_rejected(self) -> None:
        archive, digest, _ = self.build_archive("version.zip")
        with self.assertRaisesRegex(VerifyError, "version mismatch"):
            verify_release_bundle(archive, expected_sha256=digest, expected_version="9.9.9")

    def test_modified_archive_is_rejected(self) -> None:
        archive, digest, version = self.build_archive("modified.zip")
        mutated = self.root / "mutated.zip"
        mutated.write_bytes(archive.read_bytes() + b"trailing garbage")
        with self.assertRaisesRegex(VerifyError, "SHA-256 mismatch"):
            verify_release_bundle(mutated, expected_sha256=digest, expected_version=version)
        # Content mutation is caught by the published-hash comparison (the
        # structural gate alone cannot know which bytes are authentic).
        import zipfile

        altered = self.root / "altered.zip"
        with zipfile.ZipFile(archive) as bundle:
            members = [(info, bundle.read(info)) for info in bundle.infolist()]
        with zipfile.ZipFile(altered, "w", compression=zipfile.ZIP_STORED) as bundle:
            from release_payload import FIXED_ZIP_TIME, Utf8ZipInfo
            import stat as stat_module

            for index, (info, payload) in enumerate(members):
                if index == 0:
                    payload = payload + b"\n"
                info = Utf8ZipInfo(info.filename, date_time=FIXED_ZIP_TIME)
                info.create_system = 3
                info.compress_type = zipfile.ZIP_STORED
                info.external_attr = (stat_module.S_IFREG | 0o644) << 16
                bundle.writestr(info, payload)
        with self.assertRaisesRegex(VerifyError, "SHA-256 mismatch"):
            verify_release_bundle(altered, expected_sha256=digest, expected_version=version)

    def test_missing_archive_is_rejected(self) -> None:
        with self.assertRaisesRegex(VerifyError, "does not exist"):
            verify_release_bundle(self.root / "nope.zip")

    def test_plugin_tree_verification(self) -> None:
        archive, _, version = self.build_archive("tree.zip")
        import zipfile

        extracted = self.root / "extracted"
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                # The archive is structurally validated; extract per-member with
                # explicit canonical-name checks instead of extractall.
                parts = Path(info.filename).parts
                self.assertTrue(parts and all(part not in {"", ".", ".."} for part in parts))
                target = extracted.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(bundle.read(info))
        result = verify_plugin_tree(extracted, expected_version=version)
        self.assertEqual(result["version"], version)

        tree_digest = result["treeSha256"]
        self.assertEqual(
            verify_plugin_tree(extracted, expected_tree_sha256=tree_digest)["treeSha256"],
            tree_digest,
        )
        (extracted / "references" / "learning-layer-contract.md").write_text("tampered\n", encoding="utf-8")
        with self.assertRaisesRegex(VerifyError, "tree SHA-256 mismatch"):
            verify_plugin_tree(extracted, expected_tree_sha256=tree_digest)
        with self.assertRaisesRegex(VerifyError, "version mismatch"):
            verify_plugin_tree(extracted, expected_version="9.9.9")


if __name__ == "__main__":
    unittest.main()

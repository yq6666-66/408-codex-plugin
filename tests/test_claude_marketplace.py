from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

try:
    from .test_support import copy_as_committed_repo
except ImportError:
    from test_support import copy_as_committed_repo
from release_payload import ALLOWED_RELEASE_FILES, CLAUDE_MANIFEST_RELATIVE
from validate_repository import (
    ValidationError,
    check_claude_manifest,
    check_claude_marketplace,
    check_zcode_manifest,
    check_zcode_marketplace,
    validate_repo,
)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


class ClaudeAdaptationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = copy_as_committed_repo(Path(self.temporary.name) / "repo")
        self.plugin = self.repo / "plugins/kaoyan-408"
        self.manifest_path = self.plugin / CLAUDE_MANIFEST_RELATIVE
        self.marketplace_path = self.repo / ".claude-plugin/marketplace.json"
        self.canonical = read_json(self.plugin / ".codex-plugin/plugin.json")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_native_manifest_is_consistent_and_part_of_the_release(self) -> None:
        check_claude_manifest(self.plugin, self.canonical)
        check_claude_marketplace(self.repo)
        self.assertIn(CLAUDE_MANIFEST_RELATIVE, ALLOWED_RELEASE_FILES)
        self.assertEqual(read_json(self.manifest_path), {k: v for k, v in self.canonical.items() if k != "interface"})
        validate_repo(self.repo, scan_history=False)

    def test_missing_native_manifest_is_rejected_by_repository_validation(self) -> None:
        self.manifest_path.unlink()
        with self.assertRaises(ValidationError):
            validate_repo(self.repo, scan_history=False)

    def test_each_shared_metadata_field_must_match_the_source(self) -> None:
        original = read_json(self.manifest_path)
        mutations = {
            "version": "9.9.9", "description": "different", "author": {"name": "different"},
            "homepage": "https://example.invalid", "repository": "https://example.invalid/repo",
            "license": "different", "keywords": ["different"], "skills": "./other/",
        }
        for field, value in mutations.items():
            with self.subTest(field=field):
                write_json(self.manifest_path, {**original, field: value})
                with self.assertRaisesRegex(ValidationError, "identical to the Codex manifest"):
                    check_claude_manifest(self.plugin, self.canonical)

    def test_name_must_match_both_plugin_directory_and_source(self) -> None:
        manifest = read_json(self.manifest_path)
        write_json(self.manifest_path, {**manifest, "name": "other-plugin"})
        with self.assertRaisesRegex(ValidationError, "name must match"):
            check_claude_manifest(self.plugin, self.canonical)
        write_json(self.manifest_path, manifest)
        renamed = self.plugin.with_name("renamed-plugin")
        self.plugin.rename(renamed)
        with self.assertRaisesRegex(ValidationError, "name must match"):
            check_claude_manifest(renamed, self.canonical)

    def test_executable_and_host_only_fields_cannot_enter_the_native_adapter(self) -> None:
        original = read_json(self.manifest_path)
        for field in (
            "interface", "apps", "mcpServers", "lspServers", "hooks", "commands", "agents",
            "userConfig", "outputStyles", "experimental", "channels", "dependencies",
            "workflows", "monitors", "settings",
        ):
            with self.subTest(field=field):
                write_json(self.manifest_path, {**original, field: {"enabled": True}})
                with self.assertRaisesRegex(ValidationError, f"must not contain {field}"):
                    check_claude_manifest(self.plugin, self.canonical)

    def test_missing_or_unknown_metadata_is_rejected(self) -> None:
        original = read_json(self.manifest_path)
        missing = dict(original)
        missing.pop("license")
        for manifest in (missing, {**original, "misspelledField": "value"}):
            with self.subTest(manifest=manifest):
                write_json(self.manifest_path, manifest)
                with self.assertRaisesRegex(ValidationError, "exactly the shared metadata"):
                    check_claude_manifest(self.plugin, self.canonical)

    def test_skills_path_cannot_change_even_when_the_source_also_drifts(self) -> None:
        original = read_json(self.manifest_path)
        for path in ("../skills/", "./elsewhere/", ["./skills/"], "/tmp/skills"):
            with self.subTest(path=path):
                write_json(self.manifest_path, {**original, "skills": path})
                with self.assertRaisesRegex(ValidationError, "skills path"):
                    check_claude_manifest(self.plugin, {**self.canonical, "skills": path})

    def test_skills_directory_must_exist(self) -> None:
        # Rename only this test's temporary copy, keeping the source tree intact.
        (self.plugin / "skills").rename(self.plugin / "removed-skills")
        with self.assertRaisesRegex(ValidationError, "skills directory does not exist"):
            check_claude_manifest(self.plugin, self.canonical)

    def test_shared_marketplace_keeps_zcode_compatible_chinese_display_fields(self) -> None:
        check_zcode_manifest(self.plugin, self.canonical)
        check_zcode_marketplace(self.repo)
        check_claude_marketplace(self.repo)
        entry = read_json(self.marketplace_path)["plugins"][0]
        self.assertEqual(entry["displayName"], "408考研插件")
        self.assertTrue(entry["description"])
        self.assertNotIn("displayName_i18n", entry)
        self.assertNotIn("description_i18n", entry)

    def test_marketplace_rejects_unknown_fields_at_each_scope(self) -> None:
        original = read_json(self.marketplace_path)
        for scope in ("root", "owner", "entry", "author"):
            for field in ("displayName_i18n", "description_i18n", "hooks", "unknownField"):
                with self.subTest(scope=scope, field=field):
                    marketplace = json.loads(json.dumps(original))
                    target = {
                        "root": marketplace, "owner": marketplace["owner"],
                        "entry": marketplace["plugins"][0], "author": marketplace["plugins"][0]["author"],
                    }[scope]
                    target[field] = {"zh-CN": "unexpected"}
                    write_json(self.marketplace_path, marketplace)
                    with self.assertRaises(ValidationError):
                        check_claude_marketplace(self.repo)

    def test_marketplace_metadata_must_match_native_manifest(self) -> None:
        original = read_json(self.marketplace_path)
        for field, value in (("version", "9.9.9"), ("author", {"name": "different"}), ("homepage", "https://example.invalid")):
            with self.subTest(field=field):
                marketplace = json.loads(json.dumps(original))
                marketplace["plugins"][0][field] = value
                write_json(self.marketplace_path, marketplace)
                with self.assertRaisesRegex(ValidationError, f"Claude marketplace {field}"):
                    check_claude_marketplace(self.repo)

    def test_marketplace_category_rejects_unknown_and_non_string_values(self) -> None:
        original = read_json(self.marketplace_path)
        for category in ("Education", [], {}, None):
            with self.subTest(category=category):
                marketplace = json.loads(json.dumps(original))
                marketplace["plugins"][0]["category"] = category
                write_json(self.marketplace_path, marketplace)
                with self.assertRaisesRegex(ValidationError, "category is invalid"):
                    check_claude_marketplace(self.repo)

    def test_marketplace_source_is_always_the_shared_plugin_directory(self) -> None:
        original = read_json(self.marketplace_path)
        for source in ("../plugin", "./different", {"source": "github", "repo": "example/other"}):
            with self.subTest(source=source):
                marketplace = json.loads(json.dumps(original))
                marketplace["plugins"][0]["source"] = source
                write_json(self.marketplace_path, marketplace)
                with self.assertRaisesRegex(ValidationError, "relative plugin path"):
                    check_claude_marketplace(self.repo)


if __name__ == "__main__":
    unittest.main()

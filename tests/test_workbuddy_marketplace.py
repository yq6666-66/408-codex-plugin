from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

try:  # Support both unittest discovery and tests.test_* module execution.
    from .test_support import copy_as_committed_repo  # type: ignore[import-not-found]
except ImportError:
    from test_support import copy_as_committed_repo  # type: ignore[no-redef]
from release_payload import ALLOWED_RELEASE_FILES, CODEBUDDY_MANIFEST_RELATIVE  # noqa: E402
from validate_repository import (  # noqa: E402
    ValidationError,
    check_codebuddy_manifest,
    check_codebuddy_marketplace,
    validate_repo,
)


def codex_manifest(plugin: Path) -> dict:
    return json.loads((plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))


def write_json(path: Path, document: dict) -> None:
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


class WorkBuddyAdaptationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = copy_as_committed_repo(Path(self.temporary.name) / "repo")
        self.plugin = self.repo / "plugins/kaoyan-408"
        self.marketplace_path = self.repo / ".codebuddy-plugin" / "marketplace.json"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_workbuddy_surface_is_consistent_and_shipped(self) -> None:
        check_codebuddy_manifest(self.plugin, codex_manifest(self.plugin))
        check_codebuddy_marketplace(self.repo)
        self.assertIn(CODEBUDDY_MANIFEST_RELATIVE, ALLOWED_RELEASE_FILES)
        self.assertTrue((self.plugin / CODEBUDDY_MANIFEST_RELATIVE).is_file())

    def test_manifest_stays_inside_the_release_tree(self) -> None:
        self.assertIn(CODEBUDDY_MANIFEST_RELATIVE, ALLOWED_RELEASE_FILES)
        self.assertTrue(CODEBUDDY_MANIFEST_RELATIVE.startswith(".codebuddy-plugin/"))
        validate_repo(self.repo, scan_history=False)

    def test_missing_workbuddy_marketplace_is_rejected(self) -> None:
        self.marketplace_path.unlink()
        with self.assertRaisesRegex(ValidationError, "required repository file"):
            validate_repo(self.repo, scan_history=False)

    def test_missing_workbuddy_manifest_breaks_the_release_allowlist(self) -> None:
        (self.plugin / CODEBUDDY_MANIFEST_RELATIVE).unlink()
        with self.assertRaises(ValidationError):
            validate_repo(self.repo, scan_history=False)

    def test_manifest_version_drift_is_rejected(self) -> None:
        path = self.plugin / CODEBUDDY_MANIFEST_RELATIVE
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["version"] = "9.9.9"
        write_json(path, manifest)
        with self.assertRaisesRegex(ValidationError, "identical to the Codex manifest"):
            check_codebuddy_manifest(self.plugin, codex_manifest(self.plugin))

    def test_manifest_name_must_match_directory(self) -> None:
        path = self.plugin / CODEBUDDY_MANIFEST_RELATIVE
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["name"] = "kaoyan-408-alt"
        write_json(path, manifest)
        with self.assertRaises(ValidationError):
            check_codebuddy_manifest(self.plugin, codex_manifest(self.plugin))

    def test_codex_only_fields_in_workbuddy_manifest_are_rejected(self) -> None:
        path = self.plugin / CODEBUDDY_MANIFEST_RELATIVE
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["interface"] = {"displayName": "408考研插件"}
        write_json(path, manifest)
        with self.assertRaisesRegex(ValidationError, "must not contain interface"):
            check_codebuddy_manifest(self.plugin, codex_manifest(self.plugin))

    def test_host_only_declarations_are_rejected(self) -> None:
        path = self.plugin / CODEBUDDY_MANIFEST_RELATIVE
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["hooks"] = "./hooks/hooks.json"
        write_json(path, manifest)
        with self.assertRaisesRegex(ValidationError, "must not contain hooks"):
            check_codebuddy_manifest(self.plugin, codex_manifest(self.plugin))

    def test_manifest_skills_path_must_be_relative_skills_directory(self) -> None:
        path = self.plugin / CODEBUDDY_MANIFEST_RELATIVE
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["skills"] = "./plugins/kaoyan-408/skills"
        write_json(path, manifest)
        with self.assertRaisesRegex(ValidationError, "skills path"):
            check_codebuddy_manifest(self.plugin, codex_manifest(self.plugin))

    def test_marketplace_version_drift_is_rejected(self) -> None:
        marketplace = json.loads(self.marketplace_path.read_text(encoding="utf-8"))
        marketplace["plugins"][0]["version"] = "9.9.9"
        write_json(self.marketplace_path, marketplace)
        with self.assertRaisesRegex(ValidationError, "marketplace version"):
            check_codebuddy_marketplace(self.repo)

    def test_marketplace_source_drift_is_rejected(self) -> None:
        marketplace = json.loads(self.marketplace_path.read_text(encoding="utf-8"))
        marketplace["plugins"][0]["source"] = "./plugins/kaoyan-408/skills"
        write_json(self.marketplace_path, marketplace)
        with self.assertRaisesRegex(ValidationError, "relative plugin path"):
            check_codebuddy_marketplace(self.repo)

    def test_marketplace_unknown_category_is_rejected(self) -> None:
        marketplace = json.loads(self.marketplace_path.read_text(encoding="utf-8"))
        marketplace["plugins"][0]["category"] = "Education"
        write_json(self.marketplace_path, marketplace)
        with self.assertRaisesRegex(ValidationError, "category must match the plugin manifest"):
            check_codebuddy_marketplace(self.repo)

    def test_marketplace_author_drift_is_rejected(self) -> None:
        marketplace = json.loads(self.marketplace_path.read_text(encoding="utf-8"))
        marketplace["plugins"][0]["author"] = {"name": "someone-else"}
        write_json(self.marketplace_path, marketplace)
        with self.assertRaisesRegex(ValidationError, "author must match the plugin manifest"):
            check_codebuddy_marketplace(self.repo)


if __name__ == "__main__":
    unittest.main()

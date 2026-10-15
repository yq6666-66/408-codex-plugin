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
from release_payload import ALLOWED_RELEASE_FILES, ZCODE_MANIFEST_RELATIVE  # noqa: E402
from validate_repository import (  # noqa: E402
    ValidationError,
    check_zcode_manifest,
    check_zcode_marketplace,
    validate_repo,
)


def codex_manifest(plugin: Path) -> dict:
    return json.loads((plugin / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))


class ZCodeAdaptationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = copy_as_committed_repo(Path(self.temporary.name) / "repo")
        self.plugin = self.repo / "plugins/kaoyan-408"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_zcode_surface_is_consistent_and_shipped(self) -> None:
        check_zcode_manifest(self.plugin, codex_manifest(self.plugin))
        check_zcode_marketplace(self.repo)
        self.assertIn(ZCODE_MANIFEST_RELATIVE, ALLOWED_RELEASE_FILES)
        self.assertTrue((self.plugin / ZCODE_MANIFEST_RELATIVE).is_file())

    def test_missing_zcode_marketplace_is_rejected(self) -> None:
        (self.repo / ".claude-plugin" / "marketplace.json").unlink()
        with self.assertRaisesRegex(ValidationError, "required repository file"):
            validate_repo(self.repo, scan_history=False)

    def test_marketplace_version_drift_is_rejected(self) -> None:
        path = self.repo / ".claude-plugin" / "marketplace.json"
        marketplace = json.loads(path.read_text(encoding="utf-8"))
        marketplace["plugins"][0]["version"] = "9.9.9"
        path.write_text(json.dumps(marketplace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(ValidationError, "marketplace version"):
            check_zcode_marketplace(self.repo)

    def test_marketplace_source_drift_is_rejected(self) -> None:
        path = self.repo / ".claude-plugin" / "marketplace.json"
        marketplace = json.loads(path.read_text(encoding="utf-8"))
        marketplace["plugins"][0]["source"] = {"source": "local", "path": "./plugins/kaoyan-408"}
        path.write_text(json.dumps(marketplace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(ValidationError, "relative plugin path"):
            check_zcode_marketplace(self.repo)

    def test_marketplace_unknown_category_is_rejected(self) -> None:
        path = self.repo / ".claude-plugin" / "marketplace.json"
        marketplace = json.loads(path.read_text(encoding="utf-8"))
        marketplace["plugins"][0]["category"] = "Education"
        path.write_text(json.dumps(marketplace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(ValidationError, "category"):
            check_zcode_marketplace(self.repo)

    def test_zcode_manifest_version_drift_is_rejected(self) -> None:
        path = self.plugin / ZCODE_MANIFEST_RELATIVE
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["version"] = "9.9.9"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(ValidationError, "identical to the Codex manifest"):
            check_zcode_manifest(self.plugin, codex_manifest(self.plugin))

    def test_codex_only_fields_in_zcode_manifest_are_rejected(self) -> None:
        path = self.plugin / ZCODE_MANIFEST_RELATIVE
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["interface"] = {"displayName": "408考研插件"}
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(ValidationError, "must not contain interface"):
            check_zcode_manifest(self.plugin, codex_manifest(self.plugin))

    def test_zcode_manifest_name_must_match_directory(self) -> None:
        path = self.plugin / ZCODE_MANIFEST_RELATIVE
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["name"] = "kaoyan-408-alt"
        path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        with self.assertRaises(ValidationError):
            check_zcode_manifest(self.plugin, codex_manifest(self.plugin))


if __name__ == "__main__":
    unittest.main()

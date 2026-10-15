from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

from validate_repository import (  # noqa: E402
    EXPECTED_SKILLS,
    ValidationError,
    check_cursor_marketplace,
)


class CursorMarketplaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        shutil.copytree(REPO / ".cursor-plugin", self.repo / ".cursor-plugin")
        plugin = self.repo / "plugins" / "kaoyan-408"
        for name in EXPECTED_SKILLS:
            skill = plugin / "skills" / name
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text("# Fixture\n", encoding="utf-8")
        shutil.copytree(REPO / "plugins/kaoyan-408/assets", plugin / "assets")
        self.manifest = json.loads(
            (REPO / "plugins/kaoyan-408/.codex-plugin/plugin.json").read_text(encoding="utf-8")
        )

    def mutate(self, filename: str, change) -> None:
        path = self.repo / ".cursor-plugin" / filename
        document = json.loads(path.read_text(encoding="utf-8"))
        change(document)
        path.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )

    def test_valid_cursor_marketplace_and_manifest(self) -> None:
        check_cursor_marketplace(self.repo, self.manifest)

    def test_manifest_version_drift_is_rejected(self) -> None:
        self.mutate("plugin.json", lambda document: document.update(version="9.9.9"))
        with self.assertRaisesRegex(ValidationError, "version must match"):
            check_cursor_marketplace(self.repo, self.manifest)

    def test_wrong_marketplace_source_is_rejected(self) -> None:
        self.mutate(
            "marketplace.json",
            lambda document: document["plugins"][0].update(source="./plugins/kaoyan-408"),
        )
        with self.assertRaisesRegex(ValidationError, "source must be the repository root"):
            check_cursor_marketplace(self.repo, self.manifest)

    def test_wrong_skills_path_is_rejected(self) -> None:
        self.mutate("plugin.json", lambda document: document.update(skills="skills"))
        with self.assertRaisesRegex(ValidationError, "skills path is invalid"):
            check_cursor_marketplace(self.repo, self.manifest)

    def test_non_skill_components_are_rejected(self) -> None:
        for field in ("mcpServers", "hooks", "rules", "commands", "agents", "apps", "userConfig"):
            with self.subTest(field=field):
                self.mutate("plugin.json", lambda document: document.update({field: "components"}))
                try:
                    with self.assertRaisesRegex(ValidationError, f"must not declare {field}"):
                        check_cursor_marketplace(self.repo, self.manifest)
                finally:
                    self.mutate("plugin.json", lambda document: document.pop(field))


if __name__ == "__main__":
    unittest.main()

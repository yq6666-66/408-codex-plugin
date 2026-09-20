#!/usr/bin/env python3
"""Read-only health check for an installed kaoyan-408 plugin."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


EXPECTED_RUNTIME_HELPERS = {
    "configure_obsidian_brain.py",
    "health_check.py",
    "records.py",
    "study_simulator.py",
}
EXPECTED_SKILL_COUNT = 13


def _read_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"{exc.__class__.__name__} ({exc.errno})") from exc
    except UnicodeError as exc:
        raise ValueError("invalid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON at line {exc.lineno}, column {exc.colno}") from exc
    if not isinstance(document, dict):
        raise ValueError("root must be an object")
    return document


def inspect_plugin(plugin_root: Path | None = None, config_path: Path | None = None) -> dict[str, Any]:
    root = (plugin_root or Path(__file__).resolve().parents[1]).resolve()
    problems: list[str] = []

    manifest_path = root / ".codex-plugin" / "plugin.json"
    version: str | None = None
    try:
        manifest = _read_json(manifest_path)
        value = manifest.get("version")
        if isinstance(value, str) and value:
            version = value
        else:
            problems.append("manifest version is missing")
    except ValueError as exc:
        problems.append(f"manifest is unreadable: {exc}")

    skills_root = root / "skills"
    skills = sorted(
        path.name
        for path in skills_root.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file() and (path / "agents" / "openai.yaml").is_file()
    ) if skills_root.is_dir() else []
    if len(skills) != EXPECTED_SKILL_COUNT:
        problems.append(f"expected {EXPECTED_SKILL_COUNT} complete Skills, found {len(skills)}")

    scripts_root = root / "scripts"
    missing_helpers = sorted(
        name for name in EXPECTED_RUNTIME_HELPERS if not (scripts_root / name).is_file()
    )
    if missing_helpers:
        problems.append("missing runtime helpers: " + ", ".join(missing_helpers))

    config = (config_path or Path.home() / ".codex" / "kaoyan-408" / "obsidian-brain.json").resolve()
    obsidian: dict[str, Any] = {"configStatus": "absent", "enabled": None, "vaultStatus": "not-configured"}
    if config.is_file():
        try:
            brain = _read_json(config)
            obsidian["configStatus"] = "valid"
            obsidian["enabled"] = brain.get("enabled") if isinstance(brain.get("enabled"), bool) else None
            raw_vault = brain.get("vaultPath")
            if isinstance(raw_vault, str) and raw_vault:
                obsidian["vaultStatus"] = "available" if Path(raw_vault).is_dir() else "missing"
            if obsidian["enabled"] is None:
                problems.append("Obsidian config enabled flag is invalid")
        except ValueError as exc:
            obsidian["configStatus"] = "invalid"
            problems.append(f"Obsidian config is unreadable: {exc}")

    return {
        "plugin": "kaoyan-408",
        "version": version,
        "python": sys.version.split()[0],
        "skills": {"complete": len(skills), "expected": EXPECTED_SKILL_COUNT},
        "runtimeHelpers": {
            "available": len(EXPECTED_RUNTIME_HELPERS) - len(missing_helpers),
            "expected": len(EXPECTED_RUNTIME_HELPERS),
            "missing": missing_helpers,
        },
        "obsidian": obsidian,
        "status": "ok" if not problems else "problem",
        "problems": problems,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugin-root", type=Path, default=None, help="plugin root; defaults to this script's parent")
    parser.add_argument("--config", type=Path, default=None, help="optional Obsidian brain config path")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = inspect_plugin(args.plugin_root, args.config)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(f"kaoyan-408 {report['version'] or 'unknown'}: {report['status']}")
        print(f"Skills: {report['skills']['complete']}/{report['skills']['expected']}")
        print(f"Runtime helpers: {report['runtimeHelpers']['available']}/{report['runtimeHelpers']['expected']}")
        print(f"Obsidian config: {report['obsidian']['configStatus']}; vault: {report['obsidian']['vaultStatus']}")
        for problem in report["problems"]:
            print(f"[PROBLEM] {problem}")
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

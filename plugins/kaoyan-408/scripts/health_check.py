#!/usr/bin/env python3
"""Read-only health check for an installed kaoyan-408 plugin."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any


EXPECTED_RUNTIME_HELPERS = {
    "configure_obsidian_brain.py",
    "health_check.py",
    "records.py",
    "study_simulator.py",
}
EXPECTED_SKILLS = {
    "kaoyan-408-planner",
    "kaoyan-review-executor",
    "kaoyan-progress-diagnostician",
    "kaoyan-error-loop-coach",
    "kaoyan-mock-exam-coach",
    "kaoyan-408-tutor",
    "kaoyan-math-coach",
    "kaoyan-english-coach",
    "kaoyan-politics-coach",
    "kaoyan-past-paper-searcher",
    "kaoyan-past-paper-analyst",
    "kaoyan-material-study-assistant",
    "kaoyan-official-info-researcher",
    "kaoyan-admissions-researcher",
}
EXPECTED_SKILL_COUNT = len(EXPECTED_SKILLS)
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


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


def _validate_brain_config(
    root: Path, config: dict[str, Any], *, require_paths: bool = False
) -> None:
    """Delegate schema and field checks to the configuration writer's validator."""
    validator_path = root / "scripts" / "configure_obsidian_brain.py"
    spec = importlib.util.spec_from_file_location("_kaoyan_health_brain_config", validator_path)
    if spec is None or spec.loader is None:
        raise ImportError("Obsidian config validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.modules[spec.name] = module
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
        sys.modules.pop(spec.name, None)
    module.validate_config(config, require_paths=require_paths)


def inspect_plugin(plugin_root: Path | None = None, config_path: Path | None = None) -> dict[str, Any]:
    root = (plugin_root or Path(__file__).resolve().parents[1]).resolve()
    problems: list[str] = []

    manifest_path = root / ".codex-plugin" / "plugin.json"
    version: str | None = None
    try:
        manifest = _read_json(manifest_path)
        if manifest.get("name") != "kaoyan-408":
            problems.append("manifest name must be kaoyan-408")
        value = manifest.get("version")
        if isinstance(value, str) and value:
            if SEMVER_PATTERN.fullmatch(value):
                version = value
            else:
                problems.append("manifest version is not valid semantic version")
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
    if set(skills) != EXPECTED_SKILLS:
        missing = sorted(EXPECTED_SKILLS - set(skills))
        unexpected = sorted(set(skills) - EXPECTED_SKILLS)
        problems.append(f"Skill set mismatch (missing: {missing}; unexpected: {unexpected})")

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
            _validate_brain_config(root, brain)
            obsidian["configStatus"] = "valid"
            obsidian["enabled"] = brain["enabled"]
            vault_path = Path(brain["vaultPath"]).expanduser()
            if brain["enabled"]:
                try:
                    _validate_brain_config(root, brain, require_paths=True)
                    obsidian["vaultStatus"] = "available"
                except Exception:
                    obsidian["vaultStatus"] = "incomplete" if vault_path.is_dir() else "missing"
                    problems.append("enabled Obsidian Vault is unavailable or incomplete")
            else:
                obsidian["vaultStatus"] = "available" if vault_path.is_dir() else "missing"
        except Exception as exc:
            obsidian["configStatus"] = "invalid"
            problems.append(f"Obsidian config is unreadable or invalid ({exc.__class__.__name__})")

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

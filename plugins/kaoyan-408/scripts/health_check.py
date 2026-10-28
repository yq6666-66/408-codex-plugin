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
    "408-error-diagnosis",
    "408-concept-followup",
    "408-calculation-check",
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
MARKDOWN_LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def _skill_metadata_problems(skill_doc: Path, agent_manifest: Path, expected_name: str) -> list[str]:
    problems: list[str] = []
    try:
        skill_text = skill_doc.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        skill_text = ""
    frontmatter = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", skill_text, re.DOTALL)
    if frontmatter is None:
        problems.append("SKILL.md must contain readable YAML frontmatter")
    else:
        fields: dict[str, str] = {}
        for line in frontmatter.group(1).splitlines():
            field = re.match(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*?)\s*$", line)
            if field:
                fields[field.group(1)] = field.group(2).strip().strip("\"'")
        if fields.get("name") != expected_name:
            problems.append("SKILL.md frontmatter name must match its directory")
        if not fields.get("description"):
            problems.append("SKILL.md frontmatter description must be non-empty")
        if not re.search(r"(?m)^#\s+\S", skill_text[frontmatter.end():]):
            problems.append("SKILL.md must contain a non-empty title")

    try:
        agent_text = agent_manifest.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        agent_text = ""
    if not re.search(r"(?m)^interface:\s*$", agent_text):
        problems.append("agents/openai.yaml must contain an interface mapping")
    interface_fields: dict[str, str] = {}
    for name in ("display_name", "short_description", "default_prompt"):
        field = re.search(rf"(?m)^  {name}:\s*(.*?)\s*$", agent_text)
        interface_fields[name] = field.group(1).strip().strip("\"'") if field else ""
        if not interface_fields[name]:
            problems.append(f"agents/openai.yaml interface.{name} must be non-empty")
    if f"${expected_name}" not in interface_fields["default_prompt"]:
        problems.append("agents/openai.yaml default_prompt must reference its Skill identity")
    return problems


def _missing_reference_links(skill_doc: Path, plugin_root: Path) -> list[str]:
    """Find required local reference links in a Skill whose targets are missing."""
    try:
        contents = skill_doc.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ["SKILL.md (unreadable; cannot verify references)"]
    root = plugin_root.resolve()
    missing: set[str] = set()
    for match in MARKDOWN_LINK_PATTERN.finditer(contents):
        target = match.group(1).strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1]
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        local_path = target.split("#", 1)[0].split("?", 1)[0]
        if "references/" not in local_path.replace("\\", "/"):
            continue
        candidate = skill_doc.parent / local_path
        resolved = candidate.resolve()
        if root not in resolved.parents or not resolved.is_file() or candidate.is_symlink():
            missing.add(local_path)
    return sorted(missing)


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


def _trusted_brain_validator_path() -> Path:
    """Return the validator bundled beside this already-running trusted checker."""
    return Path(__file__).resolve().with_name("configure_obsidian_brain.py")


def _validate_brain_config(
    root: Path, config: dict[str, Any], *, require_paths: bool = False
) -> None:
    """Use the checker-bundled validator, never execute code from the inspected tree."""
    validator_path = _trusted_brain_validator_path()
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
    skill_entries = list(skills_root.iterdir()) if skills_root.is_dir() else []
    discovered_skills = {
        path.name for path in skill_entries if path.is_dir() or path.is_symlink()
    }
    skills: list[str] = []
    for path in sorted(skill_entries, key=lambda entry: entry.name):
        if not (path.is_dir() or path.is_symlink()):
            continue
        if path.is_symlink():
            problems.append(f"Skill directory must not be a symbolic link: {path.name}")
            continue
        skill_doc = path / "SKILL.md"
        agents_dir = path / "agents"
        agent_manifest = agents_dir / "openai.yaml"
        linked_metadata = [
            name for name, metadata_path in (
                ("SKILL.md", skill_doc),
                ("agents/", agents_dir),
                ("agents/openai.yaml", agent_manifest),
            ) if metadata_path.is_symlink()
        ]
        if linked_metadata:
            problems.append(
                f"Skill metadata must not be a symbolic link: {path.name} ({', '.join(linked_metadata)})"
            )
        missing_metadata = [
            name for name, metadata_path in (("SKILL.md", skill_doc), ("agents/openai.yaml", agent_manifest))
            if not metadata_path.is_file()
        ]
        if missing_metadata:
            problems.append(
                f"incomplete Skill directory {path.name} (missing: {', '.join(missing_metadata)})"
            )
        invalid_metadata: list[str] = []
        if not linked_metadata and not missing_metadata:
            invalid_metadata = _skill_metadata_problems(skill_doc, agent_manifest, path.name)
            if invalid_metadata:
                problems.append(
                    f"invalid Skill metadata {path.name}: {', '.join(invalid_metadata)}"
                )
        if skill_doc.is_file() and not skill_doc.is_symlink():
            missing_references = _missing_reference_links(skill_doc, root)
            if missing_references:
                problems.append(
                    f"missing or unreadable Skill references {path.name}: "
                    + ", ".join(missing_references)
                )
        if not linked_metadata and not missing_metadata and not invalid_metadata:
            skills.append(path.name)
    if set(skills) != EXPECTED_SKILLS or discovered_skills != EXPECTED_SKILLS:
        missing = sorted(EXPECTED_SKILLS - set(skills))
        unexpected = sorted(discovered_skills - EXPECTED_SKILLS)
        problems.append(f"Skill set mismatch (missing: {missing}; unexpected: {unexpected})")

    scripts_root = root / "scripts"
    missing_helpers = sorted(
        name for name in EXPECTED_RUNTIME_HELPERS
        if (scripts_root / name).is_symlink() or not (scripts_root / name).is_file()
    )
    if missing_helpers:
        problems.append("missing or symlinked runtime helpers: " + ", ".join(missing_helpers))

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
    elif config.exists():
        obsidian["configStatus"] = "invalid"
        problems.append("Obsidian config path is not a regular file")

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

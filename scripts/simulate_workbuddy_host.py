#!/usr/bin/env python3
"""Statically diagnose WorkBuddy descriptors and local Skill links offline.

Follow the declared marketplace source and manifest skills directory, requiring
each resolved path to remain in its containing tree. Read local text only: this
does not install a plugin, execute bundled code, or validate a real WorkBuddy
session. Host-coupling findings are static observations, not runtime evidence.

Exit codes: 0 findings reported, 1 findings at or above ``--fail-on``,
2 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from release_payload import SEMVER_PATTERN, ValidationError, read_utf8_text


SEVERITY_ORDER = {"blocker": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

MARKETPLACE_PART = Path(".codebuddy-plugin") / "marketplace.json"
MANIFEST_PART = Path(".codebuddy-plugin") / "plugin.json"
CODEX_ROOT_MARKER = ".codex-plugin/plugin.json"

FRONTMATTER_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FRONTMATTER_BLOCK = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(read_utf8_text(path))


def safe_relative_directory(base: Path, value: Any) -> Path:
    """Resolve a declared POSIX relative directory without leaving its owner."""
    if (
        not isinstance(value, str)
        or not value.strip()
        or "\\" in value
        or ":" in value
        or "\x00" in value
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).drive
        or ".." in PurePosixPath(value).parts
    ):
        raise ValueError("expected a relative directory without parent traversal")
    base = base.resolve()
    resolved = (base / value).resolve()
    if resolved == base or not resolved.is_relative_to(base):
        raise ValueError("declared directory escapes its containing tree")
    if not resolved.is_dir():
        raise ValueError("declared directory does not exist")
    return resolved


def load_object_inside(path: Path, boundary: Path) -> dict[str, Any]:
    if not path.resolve().is_relative_to(boundary.resolve()):
        raise ValueError("descriptor escapes its containing tree")
    document = load_json(path)
    if not isinstance(document, dict):
        raise ValueError("descriptor must be a JSON object")
    return document


def frontmatter_fields(skill_md: Path) -> dict[str, str]:
    text = read_utf8_text(skill_md)
    match = FRONTMATTER_BLOCK.match(text)
    if match is None:
        return {}
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    return fields


def simulate_workbuddy_load(repo: Path) -> dict[str, Any]:
    """Read declared local paths and record static load failures as blockers."""
    repo = repo.resolve()
    report: dict[str, Any] = {
        "marketplace": {"path": MARKETPLACE_PART.as_posix()},
        "manifest": {"path": MANIFEST_PART.as_posix()},
        "pluginRoot": None,
        "skills": [],
        "resolvedLinks": 0,
        "brokenLinks": [],
        "loadErrors": [],
    }

    def fail(stage: str, error: Exception) -> dict[str, Any]:
        report["loadErrors"].append({
            "stage": stage, "path": report[stage]["path"], "message": str(error),
        })
        return report

    marketplace_path = repo / MARKETPLACE_PART
    try:
        marketplace = load_object_inside(marketplace_path, repo)
        entries = marketplace.get("plugins")
        if not isinstance(entries, list) or len(entries) != 1 or not isinstance(entries[0], dict):
            raise ValueError("marketplace must declare exactly one plugin object")
        entry = entries[0]
        if not isinstance(entry.get("name"), str) or not entry["name"].strip():
            raise ValueError("marketplace plugin name must be a non-empty string")
        source = entry.get("source")
        report["marketplace"].update({
            "name": marketplace.get("name"),
            "pluginCount": len(entries),
            "source": source,
            "sourceExists": False,
        })
        plugin = safe_relative_directory(repo, source)
        report["marketplace"]["sourceExists"] = True
        report["pluginRoot"] = str(plugin)
    except (ValidationError, OSError, ValueError, RuntimeError) as exc:
        return fail("marketplace", exc)

    report["manifest"]["path"] = (plugin.relative_to(repo) / MANIFEST_PART).as_posix()
    manifest_path = plugin / MANIFEST_PART
    try:
        manifest = load_object_inside(manifest_path, plugin)
        if manifest.get("name") != entry["name"]:
            raise ValueError("manifest name must match the marketplace plugin name")
        version = manifest.get("version")
        if not isinstance(version, str) or re.fullmatch(SEMVER_PATTERN, version) is None:
            raise ValueError("manifest version must be a semver string")
        skills_value = manifest.get("skills")
        report["manifest"].update({
            "name": manifest.get("name"),
            "version": version,
            "skills": skills_value,
            "skillsDirectoryExists": False,
        })
        skills_root = safe_relative_directory(plugin, skills_value)
        report["manifest"]["skillsDirectoryExists"] = True
    except (ValidationError, OSError, ValueError, RuntimeError) as exc:
        return fail("manifest", exc)

    try:
        skill_dirs = []
        for path in sorted(skills_root.iterdir()):
            if not path.resolve().is_relative_to(skills_root):
                raise ValueError(f"Skill directory escapes the declared skills directory: {path.name}")
            if path.is_dir() and (path / "SKILL.md").is_file():
                if not (path / "SKILL.md").resolve().is_relative_to(skills_root):
                    raise ValueError(f"SKILL.md escapes the declared skills directory: {path.name}")
                skill_dirs.append(path)
        if not skill_dirs:
            raise ValueError("declared skills directory contains no Skill with SKILL.md")
    except (OSError, ValueError, RuntimeError) as exc:
        return fail("manifest", exc)

    for skill_dir in skill_dirs:
        skill_md = skill_dir / "SKILL.md"
        try:
            fields = frontmatter_fields(skill_md)
            skill_text = read_utf8_text(skill_md)
        except (ValidationError, OSError, ValueError) as exc:
            return fail("manifest", exc)
        links: list[dict[str, str]] = []
        for target in FRONTMATTER_LINK.findall(skill_text):
            clean = target.split("#", 1)[0].strip()
            if not clean or clean.startswith(("https://", "http://", "mailto:")):
                continue
            resolved = (skill_dir / clean).resolve()
            inside_plugin = plugin.resolve() in resolved.parents or resolved == plugin.resolve()
            exists = resolved.exists()
            leaves_skill_dir = skill_dir.resolve() not in resolved.parents and resolved != skill_dir.resolve()
            links.append(
                {
                    "target": clean,
                    "exists": exists,
                    "insidePlugin": inside_plugin,
                    "leavesSkillDirectory": leaves_skill_dir,
                }
            )
            if exists and inside_plugin:
                report["resolvedLinks"] += 1
            else:
                report["brokenLinks"].append(f"{skill_dir.name}: {clean}")
        report["skills"].append(
            {
                "name": skill_dir.name,
                "declaredName": fields.get("name"),
                "hasDescription": bool(fields.get("description")),
                "frontmatterKeys": sorted(fields),
                "links": links,
                "openaiInterfaceFile": (skill_dir / "agents" / "openai.yaml").is_file(),
            }
        )
    return report


def collect_root_marker_references(plugin: Path) -> list[str]:
    offenders: list[str] = []
    for path in sorted(plugin.rglob("*")):
        if (
            not path.is_file()
            or not path.resolve().is_relative_to(plugin.resolve())
            or path.suffix not in {".md", ".py", ".json"}
        ):
            continue
        if CODEX_ROOT_MARKER in read_utf8_text(path):
            offenders.append(path.relative_to(plugin).as_posix())
    return offenders


def build_findings(repo: Path, load_report: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = [
        {
            "id": "WB-001",
            "severity": "blocker",
            "title": "WorkBuddy 静态加载链无法解析",
            "files": [error["path"]],
            "evidence": f"{error['stage']}: {error['message']}",
            "impact": "声明的本地插件或 Skill 无法安全解析，不能据此确认宿主可加载。",
        }
        for error in load_report["loadErrors"]
    ]
    if findings:
        return findings
    plugin = Path(load_report["pluginRoot"])

    marker_refs = collect_root_marker_references(plugin)
    if marker_refs:
        findings.append(
            {
                "id": "WB-002",
                "severity": "high",
                "title": "插件根目录标记写死为 .codex-plugin/plugin.json",
                "files": marker_refs,
                "evidence": f"{len(marker_refs)} 个文件用 Codex 清单目录定位插件根",
                "impact": "只安装某一宿主适配时（清单目录被裁剪）根定位失败，随包脚本无法解析路径。",
            }
        )

    escaping = [
        skill["name"]
        for skill in load_report["skills"]
        if any(link["leavesSkillDirectory"] for link in skill["links"])
    ]
    if escaping:
        findings.append(
            {
                "id": "WB-003",
                "severity": "high",
                "title": "Skill 依赖 ../.. 跳出自身目录读取共享契约",
                "files": [f"skills/{name}/SKILL.md" for name in escaping],
                "evidence": f"{len(escaping)}/{len(load_report['skills'])} 个 Skill 链接到插件级 references/",
                "impact": "逐目录复制到用户级 skills 目录（扁平安装）时共享契约缺失，Skill 会静默降级。",
            }
        )

    namespace = [f"scripts/{name}" for name in _files_containing(plugin, "scripts", '".codex"')]
    if namespace:
        findings.append(
            {
                "id": "WB-004",
                "severity": "medium",
                "title": "Obsidian 用户配置写在 Codex 命名空间 ~/.codex/kaoyan-408/",
                "files": namespace
                + ["references/obsidian-brain-contract.md"],
                "evidence": '配置路径默认值来自 Path.home() / ".codex" / "kaoyan-408"',
                "impact": "WorkBuddy 下没有 ~/.codex，配置落到非本宿主目录；契约文字与该常量都被校验器固定，改名需同步多处。",
            }
        )

    if load_report["brokenLinks"]:
        findings.append(
            {
                "id": "WB-005",
                "severity": "blocker",
                "title": "Skill 内相对链接在插件树内无法解析",
                "files": load_report["brokenLinks"],
                "evidence": f"{len(load_report['brokenLinks'])} 个链接目标不存在或越出插件树",
                "impact": "Skill 加载时读不到契约文件，教学与记录规则会缺章。",
            }
        )

    interface_files = [skill["name"] for skill in load_report["skills"] if skill["openaiInterfaceFile"]]
    if interface_files:
        findings.append(
            {
                "id": "WB-006",
                "severity": "low",
                "title": "每个 Skill 随带 Codex 专用的 agents/openai.yaml",
                "files": [f"skills/{name}/agents/openai.yaml" for name in interface_files],
                "evidence": f"{len(interface_files)} 个 Skill 带 openai.yaml，WorkBuddy 不读取",
                "impact": "无功能破坏，但发布允许列表与校验器把它当必需项，形成对 Codex 的隐式绑定。",
            }
        )

    extra_keys = sorted(
        {
            key
            for skill in load_report["skills"]
            for key in skill["frontmatterKeys"]
            if key not in {"name", "description"}
        }
    )
    strict_frontmatter = _frontmatter_allowlist_is_strict(repo)
    if strict_frontmatter or extra_keys:
        findings.append(
            {
                "id": "WB-007",
                "severity": "low",
                "title": "Skill frontmatter 只允许 name/description",
                "files": [".codebuddy-plugin/marketplace.json", "scripts/validate_repository.py"],
                "evidence": (
                    f"校验器强制 frontmatter 键集合为 name/description（额外字段：{extra_keys or '无'}）"
                ),
                "impact": "WorkBuddy 惯例支持 display_name_zh / description_en 等展示字段，当前校验器会拒绝，插件在 WorkBuddy 技能选择器里只能用英文式名称。",
            }
        )

    return findings


def _frontmatter_allowlist_is_strict(repo: Path) -> bool:
    validator = repo / "scripts" / "validate_repository.py"
    if not validator.is_file():
        return False
    return 'set(metadata) == {"name", "description"}' in read_utf8_text(validator)


def _files_containing(plugin: Path, subdirectory: str, needle: str) -> list[str]:
    base = plugin / subdirectory
    if not base.is_dir():
        return []
    return [
        path.name
        for path in sorted(base.iterdir())
        if path.is_file()
        and path.resolve().is_relative_to(plugin.resolve())
        and needle in read_utf8_text(path)
    ]


def render_text(load_report: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("WorkBuddy 离线静态兼容性诊断")
    lines.append("=" * 40)
    marketplace = load_report["marketplace"]
    lines.append(f"marketplace: {marketplace['path']}")
    lines.append(f"  名称: {marketplace.get('name')}")
    lines.append(f"  插件数: {marketplace.get('pluginCount')}")
    lines.append(f"  source: {marketplace.get('source')} (存在: {marketplace.get('sourceExists')})")
    manifest = load_report["manifest"]
    lines.append(f"manifest: {manifest['path']}")
    lines.append(f"  名称/版本: {manifest.get('name')} / {manifest.get('version')}")
    lines.append(f"  skills: {manifest.get('skills')} (目录存在: {manifest.get('skillsDirectoryExists')})")
    lines.append(f"发现的 Skill: {len(load_report['skills'])}")
    lines.append(f"解析成功的相对链接: {load_report['resolvedLinks']}")
    lines.append(f"未解析链接: {len(load_report['brokenLinks'])}")
    for broken in load_report["brokenLinks"]:
        lines.append(f"  - {broken}")
    lines.append("")
    lines.append(f"兼容性缺陷: {len(findings)}")
    for finding in sorted(findings, key=lambda item: SEVERITY_ORDER[item["severity"]]):
        lines.append(f"[{finding['severity'].upper()}] {finding['id']} {finding['title']}")
        lines.append(f"  证据: {finding['evidence']}")
        lines.append(f"  涉及: {', '.join(finding['files'])}")
        lines.append(f"  影响: {finding['impact']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=plugin_root())
    parser.add_argument("--json", action="store_true", help="emit a machine-readable report")
    parser.add_argument(
        "--fail-on",
        choices=sorted(SEVERITY_ORDER, key=lambda key: SEVERITY_ORDER[key]),
        default=None,
        help="exit 1 when a finding reaches this severity",
    )
    args = parser.parse_args(argv)

    repo = args.repo.resolve()
    load_report = simulate_workbuddy_load(repo)
    findings = build_findings(repo, load_report)
    document = {
        "schemaVersion": "1.0",
        "load": load_report,
        "findings": sorted(findings, key=lambda item: (SEVERITY_ORDER[item["severity"]], item["id"])),
    }
    if args.json:
        print(json.dumps(document, ensure_ascii=False, indent=2))
    else:
        print(render_text(load_report, findings))

    if args.fail_on is not None:
        threshold = SEVERITY_ORDER[args.fail_on]
        if any(SEVERITY_ORDER[finding["severity"]] <= threshold for finding in findings):
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

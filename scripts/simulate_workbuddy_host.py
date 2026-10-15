#!/usr/bin/env python3
"""Simulate WorkBuddy plugin loading for kaoyan-408 and report host-compatibility findings.

The simulation is offline and deterministic. It models the WorkBuddy loading
chain (marketplace descriptor -> plugin manifest -> Skill tree -> shared
references/scripts) and then re-runs the same resolution under a
WorkBuddy-only install, so host coupling inside the Skills shows up as an
explicit finding instead of a runtime surprise.

Exit codes: 0 findings reported, 1 findings at or above ``--fail-on``,
2 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from release_payload import PLUGIN_RELATIVE_PATH, read_utf8_text


SEVERITY_ORDER = {"blocker": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

MARKETPLACE_PART = Path(".codebuddy-plugin") / "marketplace.json"
MANIFEST_PART = Path(".codebuddy-plugin") / "plugin.json"
CODEX_MANIFEST_PART = Path(".codex-plugin") / "plugin.json"
CODEX_ROOT_MARKER = ".codex-plugin/plugin.json"
SKILLS_DIR_NAME = "skills"

FRONTMATTER_LINK = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
FRONTMATTER_BLOCK = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)


def plugin_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_json(path: Path) -> Any:
    return json.loads(read_utf8_text(path))


def skill_directories(plugin: Path) -> list[Path]:
    root = plugin / SKILLS_DIR_NAME
    if not root.is_dir():
        return []
    return sorted(
        (path for path in root.iterdir() if path.is_dir() and (path / "SKILL.md").is_file()),
        key=lambda path: path.name,
    )


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
    """Walk the WorkBuddy loading chain and record what actually resolves."""
    plugin = repo / Path(*PLUGIN_RELATIVE_PATH.parts)
    report: dict[str, Any] = {
        "marketplace": None,
        "manifest": None,
        "pluginRoot": str(plugin),
        "skills": [],
        "resolvedLinks": 0,
        "brokenLinks": [],
    }

    marketplace_path = repo / MARKETPLACE_PART
    if marketplace_path.is_file():
        marketplace = load_json(marketplace_path)
        entries = marketplace.get("plugins") or []
        entry = entries[0] if entries else {}
        source = entry.get("source")
        report["marketplace"] = {
            "path": MARKETPLACE_PART.as_posix(),
            "name": marketplace.get("name"),
            "pluginCount": len(entries),
            "source": source,
        }
        if isinstance(source, str):
            resolved = (repo / source).resolve()
            report["marketplace"]["sourceExists"] = resolved.is_dir()
    else:
        report["marketplace"] = {"path": MARKETPLACE_PART.as_posix(), "missing": True}

    manifest_path = plugin / MANIFEST_PART
    if manifest_path.is_file():
        manifest = load_json(manifest_path)
        skills_value = manifest.get("skills")
        declared = plugin / str(skills_value).lstrip("./") if isinstance(skills_value, str) else None
        report["manifest"] = {
            "path": (PLUGIN_RELATIVE_PATH / MANIFEST_PART.as_posix()).as_posix(),
            "name": manifest.get("name"),
            "version": manifest.get("version"),
            "skills": skills_value,
            "skillsDirectoryExists": bool(declared and declared.is_dir()),
        }
    else:
        report["manifest"] = {"path": MANIFEST_PART.as_posix(), "missing": True}

    for skill_dir in skill_directories(plugin):
        skill_md = skill_dir / "SKILL.md"
        fields = frontmatter_fields(skill_md)
        links: list[dict[str, str]] = []
        for target in FRONTMATTER_LINK.findall(read_utf8_text(skill_md)):
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
        if not path.is_file() or path.suffix not in {".md", ".py", ".json"}:
            continue
        if CODEX_ROOT_MARKER in read_utf8_text(path):
            offenders.append(path.relative_to(plugin).as_posix())
    return offenders


def build_findings(repo: Path, load_report: dict[str, Any]) -> list[dict[str, Any]]:
    plugin = repo / Path(*PLUGIN_RELATIVE_PATH.parts)
    findings: list[dict[str, Any]] = []

    if load_report["manifest"].get("missing"):
        findings.append(
            {
                "id": "WB-001",
                "severity": "blocker",
                "title": "缺少 WorkBuddy 原生清单，WorkBuddy 无法加载插件",
                "files": [MANIFEST_PART.as_posix()],
                "evidence": "插件目录下没有 .codebuddy-plugin/plugin.json",
                "impact": "WorkBuddy 市场与插件装包只识别 .codebuddy-plugin，缺少时插件不可安装。",
            }
        )

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
        if path.is_file() and needle in read_utf8_text(path)
    ]


def render_text(load_report: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("WorkBuddy 宿主加载模拟")
    lines.append("=" * 40)
    marketplace = load_report["marketplace"]
    lines.append(f"marketplace: {marketplace['path']}")
    if marketplace.get("missing"):
        lines.append("  状态: 缺失")
    else:
        lines.append(f"  名称: {marketplace['name']}")
        lines.append(f"  插件数: {marketplace['pluginCount']}")
        lines.append(f"  source: {marketplace['source']} (存在: {marketplace.get('sourceExists')})")
    manifest = load_report["manifest"]
    lines.append(f"manifest: {manifest['path']}")
    if manifest.get("missing"):
        lines.append("  状态: 缺失")
    else:
        lines.append(f"  名称/版本: {manifest['name']} / {manifest['version']}")
        lines.append(f"  skills: {manifest['skills']} (目录存在: {manifest['skillsDirectoryExists']})")
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
    if not (repo / Path(*PLUGIN_RELATIVE_PATH.parts)).is_dir():
        print(f"[FAIL] plugin directory not found under {repo}", file=sys.stderr)
        return 2

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

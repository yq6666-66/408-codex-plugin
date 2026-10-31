#!/usr/bin/env python3
"""Assemble and safely install the three 408 Skills using only the standard library.

The manifest is the resource map. This module deliberately supports only the
single-line frontmatter used by this project, rather than implementing YAML.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import uuid
from urllib.parse import unquote, urlsplit
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PLATFORMS = {"claude": ".claude/skills", "codex": ".agents/skills", "cursor": ".cursor/skills"}
NAMES = {"408-error-diagnosis", "408-concept-followup", "408-calculation-check"}
RECEIPT = ".408-agent-skills.json"
PLUGIN_SHARED_RESOURCES = {
    "src/shared/references/kp-408.json": "plugins/kaoyan-408/references/kp-408.json",
    "src/shared/references/rule-cards.json": "plugins/kaoyan-408/references/rule-cards.json",
    "src/shared/references/knowledge-point-basis.md": "plugins/kaoyan-408/references/knowledge-point-basis.md",
    "src/shared/references/calculation-conventions.md": "plugins/kaoyan-408/references/calculation-conventions.md",
    "src/shared/calculation/study_simulator.py": "plugins/kaoyan-408/scripts/study_simulator.py",
}
KNOWLEDGE_CARD_IDS = ('CN-APP-001', 'CN-ARCH-001', 'CN-ARQ-001', 'CN-LAN-001', 'CN-LINK-001', 'CN-MAC-001', 'CN-NET-001', 'CN-NET-002', 'CN-NET-003', 'CN-PERF-001', 'CN-PHY-001', 'CN-ROUTE-001', 'CN-TCP-001', 'CN-TCP-002', 'CN-TRANS-001', 'CO-ALU-001', 'CO-BUS-001', 'CO-CACHE-001', 'CO-CACHE-002', 'CO-CPU-001', 'CO-CPU-002', 'CO-DATA-001', 'CO-DATA-002', 'CO-IO-001', 'CO-IO-002', 'CO-IO-003', 'CO-ISA-001', 'CO-MEM-001', 'CO-PERF-001', 'CO-PIPE-001', 'DS-ALG-001', 'DS-ARRAY-001', 'DS-GRAPH-001', 'DS-GRAPH-002', 'DS-GRAPH-003', 'DS-GRAPH-004', 'DS-LIST-001', 'DS-QUEUE-001', 'DS-SEARCH-001', 'DS-SEARCH-002', 'DS-SEARCH-003', 'DS-SORT-001', 'DS-STACK-001', 'DS-TREE-001', 'DS-TREE-002', 'OS-BASIC-001', 'OS-DEAD-001', 'OS-DISK-001', 'OS-FILE-001', 'OS-MEM-001', 'OS-MEM-002', 'OS-MEM-003', 'OS-MEM-004', 'OS-MEM-005', 'OS-PROC-001', 'OS-PROC-002', 'OS-SCHED-001', 'OS-SCHED-002', 'OS-SYNC-001', 'OS-SYNC-002')
PLUGIN_SHARED_RESOURCES.update({
    f"src/shared/references/knowledge-cards/{point_id}.json":
    f"plugins/kaoyan-408/references/knowledge-cards/{point_id}.json"
    for point_id in KNOWLEDGE_CARD_IDS
})
PLUGIN_SHARED_RESOURCES["src/shared/calculation/knowledge_cards.py"] = "plugins/kaoyan-408/scripts/knowledge_cards.py"
PLUGIN_SKILL_INTERFACES = {
    "408-error-diagnosis": ("408 错题归因", "定位 408 单题作答的首处错误，区分证据和假设并给最小验证题", "检查我这道 408 题的解题过程，定位第一处错误。"),
    "408-concept-followup": ("408 概念追问", "回答 408 局部概念追问，说明条件、边界与反例并保留提示答案", "解释我当前的 408 概念疑点，只展开所问部分。"),
    "408-calculation-check": ("408 计算题校验", "复核 408 数值、单位与状态计算，区分脚本核验、人工复核和条件不足", "复核这道 408 题的计算条件、单位和结果。"),
}
PLUGIN_SKILL_PREAMBLE = """## 完整插件接入

- 先读取[能力路由契约](../../references/capability-routing-contract.md)，按用户点名、当前主要目的和已开始的教学上下文确定一个主责入口；冻结模考、独立作答和仅提示边界先行。
- 讲解时读取[新手图文讲解契约](../../references/beginner-visual-answer-contract.md)，区分用户材料与模型补充，并按用户要求采用详细、简洁或逐级提示模式。
- 涉及题面、作答、参考结论或自编内容时，读取[证据与版权契约](../../references/evidence-copyright-contract.md)。实际用户内容标 `[用户材料]` 并与模型解释分开；自编验证题标 `[原创练习]`，概念例子保留正文的原创示例标注；不把未核题面称为真题或官方答案。
- 本入口只处理 408；完整讲题由 `kaoyan-408-tutor` 主责，多题/多次错因聚类与延迟复测由 `kaoyan-error-loop-coach` 主责。当前已提供的题面和过程连续交接，不要求用户复制或重发。
- 需要保存、加入复测或续学时，由主流程按[便携学习记录契约](../../references/portable-learning-records.md)和本轮授权处理；本入口不直接管理笔记，不把有绑定或已安装当作写入授权。"""


class SkillsError(ValueError):
    """A validation or installation conflict; no force mode is provided."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _replace_bytes(path: Path, content: bytes) -> None:
    """Replace one generated file atomically on its destination filesystem."""
    previous_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    staged = path.parent / (".408-resource-" + uuid.uuid4().hex)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    descriptor = os.open(staged, flags, 0o666)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            if previous_mode is not None:
                os.chmod(staged, previous_mode)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged, path)
    finally:
        if staged.exists():
            staged.unlink()


def _sync_plugin_payload(root: Path, desired: dict[str, bytes], *, check: bool, guard_index: bool = False) -> dict:
    """Apply a fully assembled payload with the existing backup and rollback rules."""
    root = Path(os.path.abspath(root))
    no_links(root)
    root = root.resolve()
    planned = []
    any_existing_target = False
    for target, content in desired.items():
        target_path = root / relative(target)
        no_links(target_path)
        text(content, target)
        if target_path.exists() and not target_path.is_file():
            raise SkillsError("generated resource target is not a regular file")
        before = target_path.read_bytes() if target_path.exists() else None
        any_existing_target = any_existing_target or before is not None
        if before != content:
            planned.append((target, target_path, before, content))
    drift = [item[0] for item in planned]
    if check or not planned:
        return {"valid": not drift, "drift": drift, "updated": [], "backup": None}
    if guard_index:
        env = os.environ.copy()
        env["GIT_NO_LAZY_FETCH"] = "1"
        try:
            probe = subprocess.run(["git", "--no-replace-objects", "-C", str(root), "rev-parse", "--show-toplevel"],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=env)
        except OSError:
            probe = None
        is_repo = probe is not None and probe.returncode == 0
        if is_repo:
            try:
                is_repo = Path(os.fsdecode(probe.stdout).strip()).resolve() == root
            except (OSError, ValueError):
                is_repo = False
        if not is_repo and ((root / ".git").exists() or any_existing_target):
            raise SkillsError("cannot check generated plugin files against their Git repository")
        if is_repo:
            for relative_target, _, before, _ in planned:
                try:
                    if before is None:
                        index_paths = subprocess.run(["git", "--no-replace-objects", "-C", str(root), "ls-files", "-z", "--", relative_target],
                                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=env)
                        head_paths = subprocess.run(["git", "--no-replace-objects", "-C", str(root), "ls-tree", "-z", "--full-tree", "HEAD", "--", relative_target],
                                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=env)
                        if index_paths.returncode != 0 or head_paths.returncode != 0:
                            raise SkillsError("cannot check deleted generated plugin file against Git")
                        if index_paths.stdout or head_paths.stdout:
                            raise SkillsError("deleted generated plugin file was preserved: " + relative_target)
                        continue
                    indexed = subprocess.run(["git", "--no-replace-objects", "-C", str(root), "show", ":" + relative_target],
                                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=env)
                    baseline = subprocess.run(["git", "--no-replace-objects", "-C", str(root), "show", "HEAD:" + relative_target],
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=env)
                except OSError:
                    raise SkillsError("cannot check generated plugin files against Git") from None
                if indexed.returncode != 0 or baseline.returncode != 0 or indexed.stdout != before or baseline.stdout != before:
                    raise SkillsError("modified or untracked generated plugin file was preserved: " + relative_target)
    backup = root / "dist/.408-plugin-resource-backups" / uuid.uuid4().hex
    no_links(backup)
    backup.mkdir(parents=True, exist_ok=False)
    for relative_target, target_path, before, _ in planned:
        if before is not None:
            destination = backup / relative_target
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(before)
            os.chmod(destination, stat.S_IMODE(target_path.stat().st_mode))
            if destination.read_bytes() != before:
                raise SkillsError("shared resource backup verification failed")
    written = []
    try:
        for _, target_path, before, content in planned:
            no_links(target_path)
            actual = target_path.read_bytes() if target_path.exists() else None
            if actual != before:
                raise SkillsError("shared resource changed after preflight")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            _replace_bytes(target_path, content)
            written.append((target_path, before, content))
    except BaseException as original:
        rollback_errors = []
        for target_path, before, content in reversed(written):
            try:
                no_links(target_path)
                if not target_path.is_file() or target_path.read_bytes() != content:
                    raise SkillsError("concurrently modified generated resource was preserved")
                if before is None:
                    target_path.unlink()
                else:
                    _replace_bytes(target_path, before)
            except BaseException as error:
                rollback_errors.append(str(error))
        if rollback_errors:
            raise SkillsError("shared resource update failed; backup retained; " + "; ".join(rollback_errors)) from original
        raise
    return {"valid": True, "drift": [], "updated": drift, "backup": str(backup)}


def sync_plugin_resources(root: Path, *, check: bool = False) -> dict:
    """Sync only the explicitly declared common resources, preserving old bytes."""
    root = Path(os.path.abspath(root))
    no_links(root)
    desired = {}
    for source, target in PLUGIN_SHARED_RESOURCES.items():
        source_path = root / relative(source)
        no_links(source_path)
        content = source_path.read_bytes()
        text(content, source)
        desired[target] = content
    return _sync_plugin_payload(root, desired, check=check, guard_index=True)


def plugin_skill_payloads(root: Path) -> dict[str, bytes]:
    """Adapt the same three canonical Skills for the shared full-plugin layout."""
    root = Path(os.path.abspath(root))
    no_links(root)
    _, assembled = load_source(root)
    desired = {}
    for name in sorted(NAMES):
        document = text(assembled[name]["SKILL.md"], name)
        header, body = document.split("\n---\n", 1)
        heading, separator, remainder = body.lstrip("\n").partition("\n\n")
        if not separator or not heading.startswith("# "):
            raise SkillsError("canonical Skill has no leading heading: " + name)
        remainder = re.sub(r"\]\((references|scripts)/", r"](../../\1/", remainder)
        if name == "408-calculation-check":
            remainder = remainder.replace(
                "随包 [模拟器](../../scripts/study_simulator.py)",
                "插件根目录下的 [模拟器](../../scripts/study_simulator.py)（`scripts/study_simulator.py`）",
            )
            remainder = remainder.replace(
                "脚本可用且题目条件匹配时，从当前技能目录按相对路径运行所需子命令。",
                "脚本可用且题目条件匹配时，先定位包含 `skills`、`references` 和 `scripts` 的插件根目录，再调用该目录下的脚本运行所需子命令。",
            )
        adapted = header + "\n---\n\n" + heading + "\n\n" + PLUGIN_SKILL_PREAMBLE + "\n\n" + remainder
        base = f"plugins/kaoyan-408/skills/{name}/"
        desired[base + "SKILL.md"] = adapted.encode("utf-8")
        display, short, prompt = PLUGIN_SKILL_INTERFACES[name]
        lines = ["interface:", "  display_name: " + json.dumps(display, ensure_ascii=False),
                 "  short_description: " + json.dumps(short, ensure_ascii=False),
                 "  default_prompt: " + json.dumps("使用 $" + name + " " + prompt, ensure_ascii=False)]
        desired[base + "agents/openai.yaml"] = ("\n".join(lines) + "\n").encode("utf-8")
    return desired


def sync_plugin_skills(root: Path, *, check: bool = False) -> dict:
    return _sync_plugin_payload(root, plugin_skill_payloads(root), check=check, guard_index=True)


def no_links(path: Path) -> None:
    """Check every existing ancestor, including Windows junction/reparse points."""
    path = Path(os.path.abspath(path))
    for part in reversed((path, *path.parents)):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise SkillsError(f"symlink/reparse point is forbidden: {part}")


def relative(value: str) -> str:
    if (not isinstance(value, str) or not value or re.search(r'[\\:*?"<>|\x00-\x1f\x7f]', value)):
        raise SkillsError(f"unsafe relative path: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute() or any(p in ("", ".", "..") for p in value.split("/")):
        raise SkillsError(f"unsafe relative path: {value!r}")
    if any(p.endswith((" ", ".")) or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9¹²³]|lpt[1-9¹²³])(?:\..*)?", p) for p in path.parts):
        raise SkillsError(f"nonportable path: {value!r}")
    return value


def files_at(root: Path) -> dict[str, bytes]:
    no_links(root)
    if not root.is_dir():
        raise SkillsError(f"not a directory: {root}")
    result = {}
    for entry in sorted(root.rglob("*")):
        no_links(entry)
        if entry.is_file():
            key = relative(entry.relative_to(root).as_posix())
            if key.casefold() in {p.casefold() for p in result}:
                raise SkillsError(f"case-insensitive duplicate: {key}")
            result[key] = entry.read_bytes()
        elif not entry.is_dir():
            raise SkillsError(f"unsupported filesystem object: {entry}")
    return result


def text(data: bytes, name: str) -> str:
    try:
        value = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SkillsError(f"not UTF-8: {name}") from exc
    if "\r" in value or "\x00" in value or value.startswith("\ufeff"):
        raise SkillsError(f"expected UTF-8 without BOM, LF only: {name}")
    return value


def frontmatter(data: bytes, name: str) -> None:
    value = text(data, name)
    if not value.startswith("---\n") or "\n---\n" not in value[4:]:
        raise SkillsError(f"missing frontmatter: {name}")
    header = value[4:].split("\n---\n", 1)[0]
    fields = {}
    for line in header.splitlines():
        match = re.fullmatch(r"(name|description|license): ([^\n]+)", line)
        if not match or match[1] in fields:
            raise SkillsError(f"unsupported or duplicate frontmatter field: {name}: {line}")
        raw = match[2]
        if raw[0] in "|>&*!{['\"" or " #" in raw or ": " in raw:
            raise SkillsError(f"frontmatter must use unquoted single-line scalar: {name}")
        fields[match[1]] = raw
    if fields.get("name") != name or not 1 <= len(fields.get("description", "")) <= 1024:
        raise SkillsError(f"invalid name/description: {name}")


def check_links(payload: dict[str, bytes], name: str) -> None:
    """Validate local inline/reference Markdown links without escaping the Skill."""
    for filename, content in payload.items():
        if not filename.endswith(".md"):
            continue
        value = text(content, filename)
        targets = re.findall(r"!?\[[^\]\n]*\]\(([^\s)]+)(?:\s+[^)]*)?\)", value)
        targets += re.findall(r"(?m)^\s*\[[^\]\n]+\]:\s*(\S+)", value)
        for target in targets:
            target = target.strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme:
                if parsed.scheme not in ("https", "http", "mailto"):
                    raise SkillsError(f"unsupported link scheme: {filename}: {target}")
                continue
            if not parsed.path:
                if parsed.netloc:
                    raise SkillsError(f"absolute link: {filename}: {target}")
                continue
            local = relative(unquote(parsed.path))
            destination = (PurePosixPath(filename).parent / local).as_posix()
            if destination not in payload:
                raise SkillsError(f"missing local link: {name}/{filename}: {target}")


def load_source(root: Path) -> tuple[dict, dict[str, dict[str, bytes]]]:
    no_links(root)
    manifest_path = root / "skillset.json"
    no_links(manifest_path)
    manifest = json.loads(text(manifest_path.read_bytes(), "skillset.json"))
    if manifest.get("name") != "408-agent-skills" or not re.fullmatch(r"3\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", manifest.get("version", "")):
        raise SkillsError("invalid product/version")
    skills = manifest.get("skills", [])
    if len(skills) != 3 or {s.get("name") for s in skills} != NAMES:
        raise SkillsError("manifest must declare exactly the three supported Skills")
    declared = set()
    assembled = {}
    for skill in skills:
        name = skill["name"]
        source = relative(skill["source"])
        if source != f"src/skills/{name}/SKILL.md":
            raise SkillsError(f"unexpected Skill source: {source}")
        mappings = [{"source": source, "target": "SKILL.md"}, *skill["resources"]]
        payload = {}
        for mapping in mappings:
            src, dest = relative(mapping["source"]), relative(mapping["target"])
            if src != "LICENSE" and not src.startswith("src/"):
                raise SkillsError(f"source outside src: {src}")
            if dest == RECEIPT or dest.casefold() in {p.casefold() for p in payload}:
                raise SkillsError(f"duplicate/reserved target: {dest}")
            if dest != "SKILL.md" and dest != "LICENSE.txt" and not (
                dest.startswith("references/") and dest.endswith((".md", ".json"))
                or dest == "scripts/knowledge_cards.py" and src == "src/shared/calculation/knowledge_cards.py"
                or dest == "scripts/study_simulator.py" and src == "src/shared/calculation/study_simulator.py"
                and name == "408-calculation-check"
            ):
                raise SkillsError(f"unsupported resource destination: {dest}")
            if src.endswith(".py") and not ((src == "src/shared/calculation/study_simulator.py" and dest == "scripts/study_simulator.py" and name == "408-calculation-check") or (src == "src/shared/calculation/knowledge_cards.py" and dest == "scripts/knowledge_cards.py")):
                raise SkillsError(f"undeclared executable capability: {src}")
            if src != "LICENSE" and not src.endswith((".md", ".json", ".py")):
                raise SkillsError(f"unsupported source type: {src}")
            full = root / src
            no_links(full)
            content = full.read_bytes()
            text(content, src)
            payload[dest] = content
            declared.add(src)
        if payload.get("LICENSE.txt") != (root / "LICENSE").read_bytes():
            raise SkillsError(f"Skill must include the root license: {name}")
        frontmatter(payload["SKILL.md"], name)
        check_links(payload, name)
        assembled[name] = payload
    actual = {"src/" + p for p in files_at(root / "src")}
    if actual != declared - {"LICENSE"}:
        raise SkillsError(f"undeclared or missing source files: {sorted(actual ^ (declared - {'LICENSE'}))}")
    hashes = {p: digest((root / p).read_bytes()) for p in sorted(declared)}
    for name, payload in assembled.items():
        receipt = {"product": manifest["name"], "version": manifest["version"], "skill": name,
                   "files": {p: digest(b) for p, b in sorted(payload.items())}, "sources": hashes,
                   "skillsetSha256": digest(manifest_path.read_bytes())}
        payload[RECEIPT] = json_bytes(receipt)
    return manifest, assembled


def write_files(root: Path, payload: dict[str, bytes]) -> None:
    root.mkdir(parents=True, exist_ok=False)
    _write_contents(root, payload)


def _write_contents(root: Path, payload: dict[str, bytes]) -> None:
    for name, content in sorted(payload.items()):
        dest = root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)


def managed(payload: dict[str, bytes], name: str) -> bool:
    if RECEIPT not in payload:
        return False
    try:
        receipt = json.loads(payload[RECEIPT])
        expected = {p: digest(b) for p, b in payload.items() if p != RECEIPT}
        return (receipt["product"] == "408-agent-skills" and receipt["skill"] == name
                and receipt["files"] == expected and isinstance(receipt["sources"], dict)
                and bool(re.fullmatch(r"3\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", receipt["version"]))
                and bool(re.fullmatch(r"[0-9a-f]{64}", receipt["skillsetSha256"])))
    except (ValueError, TypeError, KeyError):
        return False


def content_only(payload: dict[str, bytes]) -> dict[str, bytes]:
    return {p: b for p, b in payload.items() if p != RECEIPT}


def export(root: Path, platform: str, output: Path) -> dict:
    manifest, assembled = load_source(root)
    output = Path(os.path.abspath(output))
    no_links(output)
    if output.exists():
        raise SkillsError(f"export requires a new directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    selected = list(PLATFORMS) if platform == "all" else [platform]
    staging = Path(tempfile.mkdtemp(prefix=".408-export-", dir=output.parent))
    try:
        metadata = {"product": manifest["name"], "version": manifest["version"], "platforms": {}}
        for target in selected:
            platform_dir = staging / target
            platform_dir.mkdir()
            for name, payload in assembled.items():
                write_files(platform_dir / PLATFORMS[target] / name, payload)
            file_map = files_at(platform_dir)
            bundle_manifest = {"product": manifest["name"], "version": manifest["version"], "platform": target,
                               "files": {p: digest(b) for p, b in file_map.items()},
                               "skillsetSha256": digest((root / "skillset.json").read_bytes())}
            (platform_dir / "manifest.json").write_bytes(json_bytes(bundle_manifest))
            archive = staging / f"408-agent-skills-{manifest['version']}-{target}.zip"
            with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as bundle:
                for path, content in sorted(files_at(platform_dir).items()):
                    entry = zipfile.ZipInfo(path, (1980, 1, 1, 0, 0, 0))
                    entry.create_system = 3
                    entry.external_attr = (stat.S_IFREG | 0o644) << 16
                    entry.compress_type = zipfile.ZIP_STORED
                    bundle.writestr(entry, content)
            metadata["platforms"][target] = {"archive": archive.name, "sha256": digest(archive.read_bytes()),
                                              "size": archive.stat().st_size, "files": bundle_manifest["files"]}
        (staging / "manifest.json").write_bytes(json_bytes(metadata))
        staging.rename(output)
    except BaseException:
        # Only this transaction's private export staging is removed.
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return {"operation": "export", "output": str(output), "version": manifest["version"], "platforms": selected}


def scope_root(scope: str, project: Path | None) -> Path:
    if scope == "project":
        if project is None or not project.is_absolute() or not project.is_dir():
            raise SkillsError("project scope requires --project with an existing absolute directory")
        result = project
    elif scope == "user":
        if project is not None:
            raise SkillsError("--project cannot be used with user scope")
        result = Path.home()
    else:
        raise SkillsError("explicit project or user scope is required")
    no_links(result)
    return result


def selection(assembled: dict, skills: list[str] | None) -> list[str]:
    selected = skills or list(assembled)
    if len(set(selected)) != len(selected) or not set(selected) <= set(assembled):
        raise SkillsError("unknown or duplicate --skill selection")
    return selected


def preflight(base: Path, platform: str, assembled: dict, selected: list[str]) -> list[dict]:
    actions = []
    for name in selected:
        desired = assembled[name]
        target = base / PLATFORMS[platform] / name
        no_links(target)
        primary = None
        elsewhere = []
        discovery = [platform, "codex"] if platform == "cursor" else [platform]
        for other_platform in discovery:
            prefix = PLATFORMS[other_platform]
            candidate = base / prefix / name
            no_links(candidate)
            if not candidate.exists():
                continue
            existing = files_at(candidate)
            if other_platform == platform:
                primary = existing
            elif content_only(existing) == content_only(desired):
                elsewhere.append(candidate)
            else:
                raise SkillsError(f"compatible directory contains conflicting Skill: {candidate}")
        if primary is not None:
            if content_only(primary) == content_only(desired):
                if RECEIPT in primary and not managed(primary, name):
                    raise SkillsError(f"invalid management receipt: {target}")
                action = ("unchanged" if primary[RECEIPT] == desired[RECEIPT] else "upgrade") if managed(primary, name) else "reused-unmanaged"
            elif managed(primary, name):
                action = "upgrade"
            else:
                raise SkillsError(f"unknown or user-modified Skill: {target}")
        elif elsewhere:
            action = "reused-compatible"
        else:
            action = "create"
        actions.append({"name": name, "path": target, "action": action,
                        "existing": primary, "reuse": elsewhere[0] if action == "reused-compatible" else None})
    return actions


def _move(source: Path, target: Path) -> None:
    source.rename(target)


def remove_owned(root: Path, expected: dict[str, bytes]) -> None:
    """Remove only transaction-owned content, including a partially written stage."""
    actual = files_at(root)
    if any(key not in expected or value != expected[key] for key, value in actual.items()):
        raise SkillsError(f"transaction files changed; preserved: {root}")
    shutil.rmtree(root)


def install(root: Path, platform: str, base: Path, skills: list[str] | None = None) -> dict:
    manifest, assembled = load_source(root)
    no_links(base)
    selected = selection(assembled, skills)
    # Complete all validation, assembly and conflict checks before touching targets.
    with tempfile.TemporaryDirectory(prefix="408-skills-staging-") as temp:
        stage = Path(temp)
        for name in selected:
            write_files(stage / name, assembled[name])
            if files_at(stage / name) != assembled[name]:
                raise SkillsError("staging verification failed")
        actions = preflight(base, platform, assembled, selected)
        transaction = uuid.uuid4().hex
        backup_root = base / ".408-agent-skills-backups" / transaction / platform
        changed = []
        created_dirs = []
        def mkdir_parents(path: Path) -> None:
            missing = []
            cursor = path
            while not cursor.exists():
                missing.append(cursor)
                cursor = cursor.parent
            for directory in reversed(missing):
                no_links(directory)
                directory.mkdir()
                created_dirs.append(directory)
        try:
            for action in actions:
                if action["action"] not in ("create", "upgrade"):
                    continue
                target, name = action["path"], action["name"]
                no_links(target)
                if target.exists() and files_at(target) != action["existing"]:
                    raise SkillsError(f"target changed after preflight: {target}")
                if not target.exists() and action["existing"] is not None:
                    raise SkillsError(f"target disappeared after preflight: {target}")
                mkdir_parents(target.parent)
                change = {"target": target, "backup": None, "installed": False, "name": name}
                changed.append(change)
                if action["action"] == "upgrade":
                    no_links(backup_root)
                    mkdir_parents(backup_root)
                    backup = backup_root / name
                    _move(target, backup)
                    change["backup"] = backup
                # Staging is copied onto the target volume before the atomic rename.
                local_stage = target.parent / (".408-stage-" + transaction + "-" + name)
                no_links(local_stage)
                local_stage.mkdir(exist_ok=False)
                change["local_stage"] = local_stage
                _write_contents(local_stage, files_at(stage / name))
                _move(local_stage, target)
                change["installed"] = True
        except BaseException as original:
            rollback_errors = []
            for change in reversed(changed):
                target = change["target"]
                try:
                    if change["installed"]:
                        if files_at(target) != assembled[change["name"]]:
                            raise SkillsError(f"new Skill changed during transaction; preserved: {target}")
                        remove_owned(target, assembled[change["name"]])
                    local_stage = change.get("local_stage")
                    if local_stage is not None and local_stage.exists():
                        remove_owned(local_stage, assembled[change["name"]])
                    if change["backup"] is not None:
                        _move(change["backup"], target)
                except BaseException as exc:
                    rollback_errors.append(str(exc))
            for directory in reversed(created_dirs):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            if rollback_errors:
                raise SkillsError(f"{original}; rollback incomplete: {'; '.join(rollback_errors)}") from original
            raise
    return {"operation": "install", "version": manifest["version"], "platform": platform,
            "skills": [{"name": a["name"], "action": a["action"], "path": str(a["reuse"] or a["path"])} for a in actions],
            "backup": str(backup_root) if backup_root.exists() else None}


def verify(root: Path, platform: str, base: Path, skills: list[str] | None = None) -> dict:
    manifest, assembled = load_source(root)
    selected = selection(assembled, skills)
    actions = preflight(base, platform, assembled, selected)
    if any(a["action"] in ("create", "upgrade") for a in actions):
        raise SkillsError("selected Skills are missing or differ from the current source")
    return {"operation": "verify", "version": manifest["version"], "platform": platform, "valid": True,
            "skills": [{"name": a["name"], "path": str(a["reuse"] or a["path"]), "status": a["action"]} for a in actions]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    export_parser = commands.add_parser("export", help="write new self-contained platform directories and deterministic ZIPs")
    export_parser.add_argument("--platform", choices=[*PLATFORMS, "all"], default="all")
    export_parser.add_argument("--output", type=Path)
    sync_parser = commands.add_parser("sync-plugin-resources", help="sync explicit canonical resources into the complete plugin")
    sync_parser.add_argument("--check", action="store_true", help="report drift without writing files")
    skill_parser = commands.add_parser("sync-plugin-skills", help="assemble the three Skills into the complete plugin")
    skill_parser.add_argument("--check", action="store_true", help="report drift without writing files")
    for operation in ("install", "verify"):
        command = commands.add_parser(operation)
        command.add_argument("--platform", choices=PLATFORMS, required=True)
        command.add_argument("--scope", choices=("project", "user"), required=True)
        command.add_argument("--project", type=Path)
        command.add_argument("--skill", action="append", choices=sorted(NAMES))
    args = parser.parse_args(argv)
    try:
        if args.operation == "sync-plugin-resources":
            result = sync_plugin_resources(ROOT, check=args.check)
        elif args.operation == "sync-plugin-skills":
            result = sync_plugin_skills(ROOT, check=args.check)
        elif args.operation == "export":
            manifest, _ = load_source(ROOT)
            output = args.output or ROOT / "dist" / (manifest["name"] + "-" + manifest["version"])
            result = export(ROOT, args.platform, output)
        else:
            base = scope_root(args.scope, args.project)
            result = (install if args.operation == "install" else verify)(ROOT, args.platform, base, args.skill)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("valid", True) else 1
    except (SkillsError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

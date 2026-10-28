#!/usr/bin/env python3
"""Prepare or verify three Skills release archives; never tag or publish."""
from __future__ import annotations

import sys

if __name__ == "__main__" and not sys.flags.isolated:
    sys.stderr.write("[FAIL] use Python isolated mode: python -I -B ci/skills_release.py\n")
    raise SystemExit(1)

import argparse
import io
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import types

ROOT = Path(__file__).resolve().parents[1]

PACKAGING_FILES = (
    "skillset.json", "LICENSE", "tools/skills.py", "ci/skills_release.py",
    "ci/verify_skills_reproducible.py",
)


def _git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    environment = os.environ.copy()
    environment["GIT_NO_LAZY_FETCH"] = "1"
    result = subprocess.run(["git", "--no-replace-objects", *args], cwd=repo, input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=environment)
    if result.returncode:
        raise ValueError("Git source snapshot is unavailable")
    return result.stdout


def metadata(repo: Path) -> dict:
    manifest = json.loads((repo / "skillset.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("canonical manifest must be a JSON object")
    version = manifest.get("version")
    if manifest.get("name") != "408-agent-skills" or not isinstance(version, str) or not re.fullmatch(
        r"3\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?", version
    ):
        raise ValueError("release must use the canonical 3.x version")
    if "-" in version:
        for identifier in version.split("-", 1)[1].split("."):
            if identifier.isdecimal() and len(identifier) > 1 and identifier.startswith("0"):
                raise ValueError("numeric prerelease identifiers cannot have leading zeroes")
    return {"product": "408-agent-skills", "version": version, "tag": "skills-v" + version,
            "prerelease": "-" in version}


def _no_links(path: Path) -> None:
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("linked source or release path is forbidden")


def _load_exact(path: Path, name: str, content: bytes):
    # Compile the verified bytes directly: no package initializer or cached pyc.
    module = types.ModuleType(name)
    module.__file__ = str(path)
    module.__package__ = ""
    exec(compile(content, str(path), "exec"), module.__dict__)
    return module


def _assert_snapshot(repo: Path, expected_commit: str) -> dict[str, bytes]:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise ValueError("an exact 40-character commit SHA is required")
    _no_links(repo)
    top = Path(_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()
    if top != repo.resolve() or _git(repo, "rev-parse", "HEAD").decode("ascii").strip() != expected_commit:
        raise ValueError("checkout does not match the expected source commit")
    tree = _git(repo, "ls-tree", "-r", "-z", "HEAD", "--", "src", *PACKAGING_FILES)
    entries = []
    for record in tree.split(b"\0"):
        if not record:
            continue
        attributes, path = record.split(b"\t", 1)
        mode, kind, oid = attributes.split()
        if mode != b"100644" or kind != b"blob":
            raise ValueError("packaging inputs must be regular committed files")
        entries.append((path.decode("utf-8"), oid))
    if not set(PACKAGING_FILES) <= {p for p, _ in entries}:
        raise ValueError("packaging implementation or manifest is not committed")
    current_source_files = set()
    for path in (repo / "src").rglob("*"):
        _no_links(path)
        if path.is_file():
            current_source_files.add(path.relative_to(repo).as_posix())
        elif not path.is_dir():
            raise ValueError("unsupported source filesystem object")
    if current_source_files != {p for p, _ in entries if p.startswith("src/")}:
        raise ValueError("source file set differs from the committed snapshot")
    request = b"".join(oid + b"\n" for _, oid in entries)
    stream = io.BytesIO(_git(repo, "cat-file", "--batch", data=request))
    verified = {}
    for name, oid in entries:
        header = stream.readline().split()
        if len(header) != 3 or header[:2] != [oid, b"blob"]:
            raise ValueError("invalid committed packaging object")
        size = int(header[2])
        content = stream.read(size)
        if len(content) != size or stream.read(1) != b"\n":
            raise ValueError("truncated committed packaging object")
        path = repo / name
        _no_links(path)
        if not path.is_file() or path.read_bytes() != content:
            raise ValueError("packaging input differs from the committed snapshot")
        verified[name] = content
    return verified


def _payload(repo: Path, expected_tag: str, expected_commit: str,
             artifact_directories: tuple[Path, ...] = ()) -> tuple[dict, dict[str, bytes]]:
    committed = _assert_snapshot(repo, expected_commit)
    with tempfile.TemporaryDirectory(prefix="408-release-rebuild-") as temporary:
        snapshot = Path(temporary) / "source"
        for name, content in committed.items():
            path = snapshot / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        skills = _load_exact(snapshot / "tools/skills.py", "_committed_release_skills", committed["tools/skills.py"])
        reproducible = _load_exact(snapshot / "ci/verify_skills_reproducible.py", "_committed_release_reproducible",
                                   committed["ci/verify_skills_reproducible.py"])
        values = metadata(snapshot)
        if expected_tag != values["tag"]:
            raise ValueError("tag must exactly match the canonical Skills version")
        rebuilt = Path(temporary) / "canonical"
        skills.export(snapshot, "all", rebuilt)
        payload = {name: path.read_bytes() for name, path in reproducible.archive_set(rebuilt, values["version"]).items()}
    _assert_snapshot(repo, expected_commit)
    for directory in artifact_directories:
        for name, path in reproducible.archive_set(directory, values["version"]).items():
            if path.read_bytes() != payload[name]:
                raise ValueError("downloaded archive differs from the committed source rebuild")
    values.update({"sourceCommit": expected_commit,
                   "archives": {name: skills.digest(data) for name, data in sorted(payload.items())},
                   "validationScope": "source-bound archive bytes only; not native-client or behavior acceptance"})
    payload["release.json"] = skills.json_bytes(values)
    notes = (f"# 408-agent-skills {values['version']}\n\n"
             f"源码提交：`{expected_commit}`。\n\n"
             "包含错题归因、概念追问、计算题校验三个场景的 Claude/Codex/Cursor 包。\n"
             "包内容已与指定提交重新生成的产物比对；客户端原生发现及自动路由仍未验证。\n"
             "知识点来源状态以随包记录为准，项目规则归纳不冒充教材或官方大纲原文。\n")
    payload["RELEASE_NOTES.md"] = notes.encode("utf-8")
    payload["SHA256SUMS.txt"] = "".join(
        f"{skills.digest(data)}  {name}\n" for name, data in sorted(payload.items())
    ).encode("utf-8")
    return values, payload


def _inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def prepare_release(repo: Path, windows: Path, ubuntu: Path, output: Path,
                    expected_tag: str, expected_commit: str) -> dict:
    output = Path(os.path.abspath(output))
    _no_links(output)
    if output.exists():
        raise ValueError("release preparation requires a new output directory")
    for directory in (windows, ubuntu, *(repo / name for name in ("src", "tools", "ci", "schemas", ".git"))):
        if _inside(output, Path(os.path.abspath(directory))):
            raise ValueError("output cannot be inside input artifacts or source directories")
    values, payload = _payload(repo, expected_tag, expected_commit, (windows, ubuntu))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".408-release-stage-", dir=output.parent) as temporary:
        stage = Path(temporary) / "release"
        stage.mkdir()
        for name, content in payload.items():
            (stage / name).write_bytes(content)
        if output.exists():
            raise ValueError("release output appeared during preparation")
        stage.rename(output)
    return values


def verify_release(repo: Path, directory: Path, expected_tag: str, expected_commit: str) -> dict:
    values, expected = _payload(repo, expected_tag, expected_commit)
    _no_links(directory)
    if not directory.is_dir():
        raise ValueError("release directory is missing")
    actual = {}
    for path in directory.rglob("*"):
        _no_links(path)
        if path.is_file():
            actual[path.relative_to(directory).as_posix()] = path.read_bytes()
    if actual != expected:
        raise ValueError("release files differ from the exact committed source release set")
    return {**values, "valid": True}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "verify"):
        command = commands.add_parser(name)
        command.add_argument("--tag", required=True)
        command.add_argument("--commit", required=True)
        if name == "prepare":
            command.add_argument("--windows", type=Path, required=True)
            command.add_argument("--ubuntu", type=Path, required=True)
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            result = prepare_release(ROOT, args.windows, args.ubuntu, args.output, args.tag, args.commit)
        else:
            result = verify_release(ROOT, args.directory, args.tag, args.commit)
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(1, f"[FAIL] {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

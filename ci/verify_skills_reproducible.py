#!/usr/bin/env python3
"""Compare every expected cross-platform skills archive, without publishing."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


PLATFORMS = ("claude", "codex", "cursor")
REPO = Path(__file__).resolve().parents[1]


def read_version(path: Path) -> str:
    value = json.loads(path.read_text(encoding="utf-8"))["version"]
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"
        r"(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?", value
    ):
        raise ValueError("skillset version must be a filename-safe semantic version")
    return value


def _is_link(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path, "is_junction", lambda: False)())


def archive_set(directory: Path, expected_version: str) -> dict[str, Path]:
    # Do not let an artifact link escape to another build's directory. Reject
    # linked ancestors too, before resolving or reading any archive bytes.
    directory = directory.absolute()
    if any(_is_link(p) for p in (directory, *directory.parents)):
        raise ValueError(f"linked artifact directory is forbidden: {directory}")
    if not directory.is_dir():
        raise ValueError(f"artifact directory is missing: {directory}")
    expected = {f"408-agent-skills-{expected_version}-{p}.zip" for p in PLATFORMS}
    found: dict[str, Path] = {}
    pending = [directory]
    while pending:
        parent = pending.pop()
        for path in parent.iterdir():
            if _is_link(path):
                raise ValueError(f"linked artifact entry is forbidden: {path}")
            if path.is_dir():
                pending.append(path)
            elif path.suffix.lower() == ".zip":
                if path.parent != directory or path.name not in expected:
                    raise ValueError(f"unexpected ZIP artifact: {path.relative_to(directory)}")
                if path.name in found:
                    raise ValueError(f"duplicate ZIP artifact: {path.name}")
                found[path.name] = path
    if set(found) != expected:
        raise ValueError(f"missing ZIP artifacts: {', '.join(sorted(expected - set(found)))}")
    return found


def compare_archives(windows: Path, ubuntu: Path, expected_version: str) -> dict[str, str]:
    win = archive_set(windows, expected_version)
    linux = archive_set(ubuntu, expected_version)
    checksums = {}
    for name in sorted(win):
        windows_bytes = win[name].read_bytes()
        ubuntu_bytes = linux[name].read_bytes()
        if windows_bytes != ubuntu_bytes:
            raise ValueError(f"Windows and Ubuntu archive bytes differ: {name}")
        checksums[name] = hashlib.sha256(windows_bytes).hexdigest()
    return checksums


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("windows", type=Path)
    parser.add_argument("ubuntu", type=Path)
    args = parser.parse_args(argv)
    try:
        checksums = compare_archives(args.windows, args.ubuntu, read_version(REPO / "skillset.json"))
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"[FAIL] {exc}\n")
    for name, digest in checksums.items():
        print(f"[OK] {digest}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build a byte-for-byte reproducible release ZIP from committed Git blobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
import subprocess
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from release_payload import (
    ALLOWED_RELEASE_FILES,
    FIXED_ZIP_TIME,
    PLUGIN_RELATIVE_PATH,
    UTF8_FLAG,
    Utf8ZipInfo,
    ValidationError,
    plugin_tree_digest,
    validate_release_archive,
)
from validate_repository import validate_repo


@dataclass(frozen=True)
class ReleaseArtifact:
    archive: Path
    checksum: Path
    digest: str
    names: tuple[str, ...]
    version: str


def _git(repo: Path, arguments: list[str], *, text: bool = False) -> subprocess.CompletedProcess[bytes] | subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=text,
            encoding="utf-8" if text else None,
            errors="strict" if text else None,
            check=False,
        )
    except OSError as exc:
        raise ValidationError(f"cannot run git: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr if isinstance(result.stderr, str) else result.stderr.decode("utf-8", "replace")
        raise ValidationError(f"git {' '.join(arguments)} failed: {stderr.strip()}")
    return result


def _require_clean_plugin_tree(repo: Path) -> None:
    result = _git(
        repo,
        [
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
            "--",
            PLUGIN_RELATIVE_PATH.as_posix(),
        ],
        text=True,
    )
    if result.stdout.strip():
        raise ValidationError("plugin tree is dirty; commit the exact release payload before building")


def committed_plugin_blobs(repo: Path) -> dict[str, bytes]:
    """Return the exact allowlisted plugin files from HEAD, never from the worktree."""

    _require_clean_plugin_tree(repo)
    tree = _git(
        repo,
        ["ls-tree", "-r", "-z", "HEAD", "--", PLUGIN_RELATIVE_PATH.as_posix()],
    ).stdout
    entries: dict[str, tuple[str, str]] = {}
    prefix = PLUGIN_RELATIVE_PATH.as_posix() + "/"
    for raw_record in tree.split(b"\x00"):
        if not raw_record:
            continue
        metadata, separator, raw_path = raw_record.partition(b"\t")
        if not separator:
            raise ValidationError("malformed git tree entry")
        try:
            mode, object_type, object_id = metadata.decode("ascii").split()
            full_path = raw_path.decode("utf-8")
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValidationError("malformed or non-UTF-8 git tree entry") from exc
        if not full_path.startswith(prefix):
            raise ValidationError(f"unexpected plugin path from Git: {full_path}")
        relative = full_path[len(prefix) :]
        if mode != "100644" or object_type != "blob":
            raise ValidationError(f"release Git entry must be a regular 0644 blob: {relative}")
        entries[relative] = (mode, object_id)

    if set(entries) != set(ALLOWED_RELEASE_FILES):
        missing = sorted(set(ALLOWED_RELEASE_FILES) - set(entries))
        extra = sorted(set(entries) - set(ALLOWED_RELEASE_FILES))
        raise ValidationError(f"committed plugin tree violates exact allowlist; missing={missing}, extra={extra}")

    payloads: dict[str, bytes] = {}
    for relative in sorted(entries):
        object_id = entries[relative][1]
        payload = _git(repo, ["cat-file", "blob", object_id]).stdout
        if b"\x00" in payload:
            raise ValidationError(f"release text contains NUL bytes: {relative}")
        if b"\r" in payload:
            raise ValidationError(f"committed release text must use LF: {relative}")
        try:
            payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValidationError(f"committed release file is not UTF-8: {relative}") from exc
        payloads[relative] = payload
    return payloads


def _manifest_version(payloads: Mapping[str, bytes]) -> str:
    try:
        manifest = json.loads(payloads[".codex-plugin/plugin.json"].decode("utf-8"))
        version = manifest["version"]
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError(f"cannot derive release version from committed manifest: {exc}") from exc
    if not isinstance(version, str) or not version:
        raise ValidationError("committed manifest version must be a non-empty string")
    return version


def _zip_info(name: str) -> Utf8ZipInfo:
    info = Utf8ZipInfo(name, date_time=FIXED_ZIP_TIME)
    info.create_system = 3
    info.create_version = 20
    info.extract_version = 20
    info.compress_type = zipfile.ZIP_STORED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.internal_attr = 0
    info.extra = b""
    info.comment = b""
    return info



def build_archive(
    repo: Path,
    output: Path | None = None,
) -> ReleaseArtifact:
    repo = repo.resolve()
    _require_clean_plugin_tree(repo)
    validate_repo(repo)
    payloads = committed_plugin_blobs(repo)
    version = _manifest_version(payloads)
    archive_path = (output or repo / "dist" / f"kaoyan-408-{version}.zip").resolve()
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    for path in (archive_path, checksum_path):
        if path.exists():
            path.unlink()

    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        archive.comment = b""
        for name in sorted(payloads):
            archive.writestr(_zip_info(name), payloads[name])

    names = validate_release_archive(archive_path)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    checksum_path.write_bytes(f"{digest}  {archive_path.name}\n".encode("ascii"))
    return ReleaseArtifact(
        archive=archive_path,
        checksum=checksum_path,
        digest=digest,
        names=names,
        version=version,
    )


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional ZIP path; default name is derived from plugin.json.version",
    )
    args = parser.parse_args()
    output = args.output
    if output is not None and not output.is_absolute():
        output = repo / output
    try:
        artifact = build_archive(repo, output)
    except ValidationError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(f"[OK] release: {artifact.archive}")
    print(f"[OK] checksum: {artifact.checksum}")
    print(f"[OK] files: {len(artifact.names)}")
    print(f"[OK] sha256: {artifact.digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Offline secret and removed-data checks for current 3.x sources and Git history."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
CURRENT_PRIVATE_PATH_PARTS = {"app", "android", "corpus", "raw", "index", "user"}
HISTORY_PRIVATE_PATH_PARTS = {"app", "android", "corpus", "raw"}

# Keep these detectors byte-for-byte equivalent in meaning to the previous
# SENSITIVE_PATTERNS. IDs are safe to print; matching data is never included.
CURRENT_SECRET_PATTERNS = (
    ("github-token", re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("github-pat", re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("openai-token", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("figma-token", re.compile(rb"\bfigd_[A-Za-z0-9_-]{20,}\b")),
    ("aws-access-key", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    ("google-api-key", re.compile(rb"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("slack-token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("npm-token", re.compile(rb"\bnpm_[A-Za-z0-9]{20,}\b")),
    ("gitlab-token", re.compile(rb"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("jwt", re.compile(rb"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("aws-secret-assignment", re.compile(
        rb"\baws[_ -]?secret[_ -]?access[_ -]?key\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{30,}", re.IGNORECASE)),
    ("account-key", re.compile(rb"\bAccountKey\s*=\s*[A-Za-z0-9+/]{40,}={0,2}", re.IGNORECASE)),
    ("private-key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----")),
    ("pgp-private-key", re.compile(rb"-----BEGIN PGP " + rb"PRIVATE KEY BLOCK-----")),
    ("assigned-secret", re.compile(
        rb"\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret|secret[_ -]?key|cookie)"
        rb"\s*[:=]\s*[\"']?[^\s\"']{8,}", re.IGNORECASE)),
)

# Preserve the stricter history thresholds and all old history-only types.
HISTORY_SECRET_PATTERNS = (
    ("github-token", re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("github-pat", re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("openai-token", re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("figma-token", re.compile(rb"\bfigd_[A-Za-z0-9_-]{20,}\b")),
    ("aws-access-key", re.compile(rb"\bAKIA[0-9A-Z]{16}\b")),
    ("google-api-key", re.compile(rb"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("slack-token", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("npm-token", re.compile(rb"\bnpm_[A-Za-z0-9]{20,}\b")),
    ("gitlab-token", re.compile(rb"\bglpat-[A-Za-z0-9_-]{20,}\b")),
    ("jwt", re.compile(rb"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    ("aws-secret-assignment", re.compile(
        rb"\baws[_ -]?secret[_ -]?access[_ -]?key\s*[:=]\s*[\"']?[A-Za-z0-9/+=]{30,}", re.IGNORECASE)),
    ("account-key", re.compile(rb"\bAccountKey\s*=\s*[A-Za-z0-9+/]{40,}={0,2}", re.IGNORECASE)),
    ("assigned-secret", re.compile(
        rb"\b(?:api[_ -]?key|access[_ -]?token|client[_ -]?secret|secret[_ -]?key|cookie)"
        rb"\s*[:=]\s*[\"']?[A-Za-z0-9+/=_-]{16,}", re.IGNORECASE)),
    ("private-key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----")),
    ("pgp-private-key", re.compile(rb"-----BEGIN PGP " + rb"PRIVATE KEY BLOCK-----")),
)

CURRENT_REMOVED_MARKERS = (
    ("removed-system-01", re.compile(rb"\b" + rb"bai" + rb"du\b", re.IGNORECASE)),
    ("removed-system-02", re.compile(rb"\bnet" + rb"disk\b", re.IGNORECASE)),
    ("removed-system-03", re.compile(rb"\blocal" + rb"storage\b", re.IGNORECASE)),
    ("removed-system-04", re.compile(rb"\bstudy" + rb"-state\b", re.IGNORECASE)),
)
HISTORY_REMOVED_MARKERS = CURRENT_REMOVED_MARKERS

# These are the exact historical file exemptions from the old validator. They
# apply only to removed-system marker scans; history secrets and paths are still
# scanned. The detector definitions themselves contain the marker spellings.
HISTORY_MARKER_EXEMPT_PATHS = {b".semgrep.yml", b"scripts/validate_repository.py"}
MAX_SNAPSHOT_BYTES = 16 * 1024 * 1024
MAX_SNAPSHOT_MEMBERS = 1024

_SKILLS_HELPER = None


class SecurityError(ValueError):
    """A security finding or incomplete history scan, with values redacted."""

    def __init__(self, message: str, findings: tuple[str, ...] = ()) -> None:
        super().__init__(message)
        self.findings = findings


def matched_secret_types(payload: bytes, *, historical: bool = False) -> tuple[str, ...]:
    patterns = HISTORY_SECRET_PATTERNS if historical else CURRENT_SECRET_PATTERNS
    return tuple(rule for rule, pattern in patterns if pattern.search(payload))


def _digest_path(path: bytes) -> str:
    return hashlib.sha256(path).hexdigest()[:16]


def _record_findings(
    found: set[str],
    payload: bytes,
    path: bytes,
    secret_patterns,
    marker_patterns=(),
) -> None:
    path_id = _digest_path(path)
    found.update(f"{rule}@{path_id}" for rule in matched_secret_types(payload, historical=(secret_patterns is HISTORY_SECRET_PATTERNS)))
    found.update(f"{rule}@{path_id}" for rule, pattern in marker_patterns if pattern.search(payload))


def _skills_helpers():
    global _SKILLS_HELPER
    if _SKILLS_HELPER is not None:
        return _SKILLS_HELPER
    helper_path = Path(__file__).resolve().with_name("skills.py")
    spec = importlib.util.spec_from_file_location("_v300_security_skills_helpers", helper_path)
    if spec is None or spec.loader is None:
        raise SecurityError("cannot load the standard-library source-tree checker")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    except Exception:
        raise SecurityError("cannot load the standard-library source-tree checker") from None
    finally:
        sys.dont_write_bytecode = previous
    _SKILLS_HELPER = module
    return module


def _raise_findings(label: str, found: set[str]) -> None:
    if found:
        summary = "; ".join(sorted(found))
        raise SecurityError(f"{label} security findings: {summary}", tuple(sorted(found)))


def scan_current_sources(root: Path = ROOT) -> dict:
    """Scan all current src files plus the 3.x assembly manifest and license."""
    root = Path(root).absolute()
    helper = _skills_helpers()
    try:
        files = helper.files_at(root / "src")
        files = {f"src/{name}": content for name, content in files.items()}
        for name in ("skillset.json", "LICENSE"):
            path = root / name
            helper.no_links(path)
            if not path.is_file():
                raise SecurityError("required 3.x assembly source is missing")
            files[name] = path.read_bytes()
    except SecurityError:
        raise
    except Exception:
        # Do not expose attacker-controlled path names or file contents.
        raise SecurityError("cannot safely enumerate current 3.x assembly sources") from None

    found: set[str] = set()
    for relative, payload in sorted(files.items()):
        path = relative.encode("utf-8", "surrogateescape")
        parts = {part.casefold() for part in PurePosixPath(relative).parts}
        if parts & CURRENT_PRIVATE_PATH_PARTS:
            found.add(f"current-private-path@{_digest_path(path)}")
        _record_findings(found, payload, path, CURRENT_SECRET_PATTERNS, CURRENT_REMOVED_MARKERS)
    _raise_findings("current source", found)
    return {"valid": True, "filesScanned": len(files), "scope": "skillset.json, LICENSE, and current src/**"}


def _run_git(repo: Path, arguments: list[str], input_bytes: bytes | None = None) -> bytes:
    environment = os.environ.copy()
    environment["GIT_NO_LAZY_FETCH"] = "1"
    environment["GIT_GRAFT_FILE"] = os.devnull
    try:
        result = subprocess.run(
            ["git", "--no-replace-objects", *arguments], cwd=repo, input=input_bytes,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, env=environment,
        )
    except OSError:
        raise SecurityError("Git history check could not start") from None
    if result.returncode != 0:
        # stderr can contain untrusted paths or data; report only the command and exit status.
        raise SecurityError(f"Git history check failed ({arguments[0]}, exit={result.returncode})")
    return result.stdout


def _path_findings(path: bytes, found: set[str]) -> None:
    path_id = _digest_path(path)
    components = {part.lower() for part in path.split(b"/")}
    if components & {b"app", b"android", b"corpus", b"raw"}:
        found.add(f"historical-private-path@{path_id}")
    found.update(f"historical-secret-path:{rule}@{path_id}"
                 for rule, pattern in HISTORY_SECRET_PATTERNS if pattern.search(path))


def _snapshot_findings(payload: bytes, path: bytes, found: set[str]) -> None:
    """Scan a canonical stored legacy ZIP by its original member paths.

    Canonical byte equality excludes prefixes, trailers, metadata tricks and
    alternative archive encodings. Nothing is extracted to the filesystem.
    """
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise SecurityError("legacy snapshot exceeds the byte limit")
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if (not entries or len(entries) > MAX_SNAPSHOT_MEMBERS
                    or len(names) != len(set(names)) or names != sorted(names)
                    or archive.comment or sum(entry.file_size for entry in entries) > MAX_SNAPSHOT_BYTES):
                raise SecurityError("legacy snapshot has a noncanonical file set")
            members = []
            for entry in entries:
                if entry.compress_type != zipfile.ZIP_STORED or entry.flag_bits & 1:
                    raise SecurityError("legacy snapshot must use unencrypted stored members")
                _skills_helpers().relative(entry.filename)
                if entry.filename != entry.orig_filename:
                    raise SecurityError("legacy snapshot member name is ambiguous")
                content = archive.read(entry)
                if entry.filename.lower().endswith(".zip") or zipfile.is_zipfile(io.BytesIO(content)):
                    raise SecurityError("nested legacy snapshots are forbidden")
                members.append((entry.filename, content))
        canonical = io.BytesIO()
        with zipfile.ZipFile(canonical, "w", compression=zipfile.ZIP_STORED) as rebuilt:
            for name, content in members:
                entry = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | 0o644) << 16
                rebuilt.writestr(entry, content)
        if canonical.getvalue() != payload:
            raise SecurityError("legacy snapshot bytes do not match the canonical format")
    except SecurityError:
        raise
    except (OSError, ValueError, RuntimeError, zipfile.BadZipFile, UnicodeError):
        raise SecurityError("legacy snapshot cannot be safely read") from None
    for name, content in members:
        member_path = name.encode("utf-8")
        _path_findings(member_path, found)
        markers = () if member_path in HISTORY_MARKER_EXEMPT_PATHS else HISTORY_REMOVED_MARKERS
        _record_findings(found, content, path + b"!" + member_path, HISTORY_SECRET_PATTERNS, markers)


def _parse_tree_listing(repo: Path, treeish: bytes, found: set[str], blob_paths: dict[bytes, set[bytes]]) -> None:
    listing = _run_git(repo, ["ls-tree", "-r", "-z", "--full-tree", treeish.decode("ascii")])
    for record in listing.split(b"\0"):
        if not record:
            continue
        metadata, separator, path = record.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise SecurityError("Git tree response is malformed")
        _, object_type, oid = fields
        _path_findings(path, found)
        if object_type == b"blob":
            blob_paths.setdefault(oid, set()).add(path)


def _batch_objects(repo: Path, object_ids: list[bytes]):
    for start in range(0, len(object_ids), 128):
        batch_ids = object_ids[start:start + 128]
        raw = _run_git(repo, ["cat-file", "--batch"], b"".join(oid + b"\n" for oid in batch_ids))
        stream = io.BytesIO(raw)
        for requested in batch_ids:
            header = stream.readline().rstrip(b"\n").split()
            if len(header) >= 2 and header[1] == b"missing":
                raise SecurityError("a reachable Git object is missing")
            if len(header) != 3 or header[0] != requested:
                raise SecurityError("Git object response is malformed")
            object_type, size = header[1], int(header[2])
            payload = stream.read(size)
            if len(payload) != size or stream.read(1) != b"\n":
                raise SecurityError("Git object response is truncated")
            yield requested, object_type, payload


def scan_git_history(repo: Path = ROOT) -> dict:
    """Scan every ref-reachable commit, tree path, blob, and annotated tag."""
    repo = Path(repo).resolve()
    shallow = _run_git(repo, ["rev-parse", "--is-shallow-repository"]).strip()
    if shallow != b"false":
        raise SecurityError("complete Git history check requires a non-shallow repository")

    commits = sorted(set(_run_git(repo, ["rev-list", "--all", "HEAD"]).splitlines()))
    if not commits:
        raise SecurityError("complete Git history check requires at least one reachable commit")

    found: set[str] = set()
    blob_paths: dict[bytes, set[bytes]] = {}
    for commit in commits:
        _parse_tree_listing(repo, commit, found, blob_paths)

    # Refs can point directly at trees or blobs, including outside refs/tags.
    ref_roots = set(_run_git(repo, ["for-each-ref", "--format=%(objectname)"]).splitlines())
    pending = set(commits) | set(blob_paths) | ref_roots
    seen: set[bytes] = set()
    blobs: set[bytes] = set()
    tags: set[bytes] = set()
    while pending:
        chunk = sorted(pending - seen)[:128]
        if not chunk:
            break
        seen.update(chunk)
        for oid, object_type, payload in _batch_objects(repo, chunk):
            if object_type in {b"blob", b"commit", b"tag"}:
                context = object_type + b":" + oid
                _record_findings(found, payload, context, HISTORY_SECRET_PATTERNS)
            if object_type == b"blob":
                blobs.add(oid)
            elif object_type == b"tag":
                tags.add(oid)
                header = payload.split(b"\n\n", 1)[0]
                for line in header.splitlines():
                    if line.startswith(b"object "):
                        target = line[7:].strip()
                        if re.fullmatch(rb"[0-9a-f]{40}|[0-9a-f]{64}", target):
                            pending.add(target)
                        else:
                            raise SecurityError("annotated tag target is malformed")
                        break
                else:
                    raise SecurityError("annotated tag target is missing")
            elif object_type == b"tree":
                _parse_tree_listing(repo, oid, found, blob_paths)
                pending.update(blob_paths)

    # Wait until all tree/tag roots are traversed before applying path exemptions:
    # one blob can occur under both an exempt path and an ordinary path.
    for oid, _, payload in _batch_objects(repo, sorted(blobs)):
        paths = blob_paths.get(oid, set())
        marker_paths = sorted(path for path in paths if path not in HISTORY_MARKER_EXEMPT_PATHS)
        if not paths or oid in ref_roots:
            marker_paths.append(b"blob:" + oid)
        for path in marker_paths:
            if path.startswith(b"legacy/") and path.lower().endswith(b".zip"):
                _snapshot_findings(payload, path, found)
                continue
            path_id = _digest_path(path)
            found.update(f"removed-system-marker:{rule}@{path_id}"
                         for rule, pattern in HISTORY_REMOVED_MARKERS if pattern.search(payload))

    _raise_findings("Git history", found)
    return {"valid": True, "commitsScanned": len(commits), "blobsScanned": len(blobs),
            "tagsScanned": len(tags), "scope": "all refs and HEAD; full reachable history"}


def check_security(root: Path = ROOT) -> dict:
    current = scan_current_sources(root)
    history = scan_git_history(root)
    return {"valid": True, "currentSources": current, "history": history}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        result = check_security(args.repo)
    except SecurityError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(__import__("json").dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

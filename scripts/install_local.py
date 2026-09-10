#!/usr/bin/env python3
"""Validate, verify, and install kaoyan-408.

Subcommands:
  install        Validate this repository, then install via the official Codex CLI.
                 ``--validate-only`` runs the offline validation gates and stops.
  verify-release Consumer-side fixed-version verification of a Release ZIP:
                 source bytes hash, archive structure, and manifest version.
                 It is intentionally time-independent: a pinned version whose
                 hash still matches must install 31 days, one year, or any
                 time after publication.
  verify-tree    Verify an installed or extracted plugin tree against the
                 release allowlist, with optional version and tree digest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path, PurePath
from typing import Callable, TextIO

from release_payload import (
    ALLOWED_RELEASE_FILES,
    SEMVER_PATTERN,
    ValidationError,
    archive_manifest_version,
    plugin_tree_digest,
    validate_release_archive,
)


PLUGIN_NAME = "kaoyan-408"
MARKETPLACE_NAME = "kaoyan-408"
LEGACY_PLUGIN_NAME = "kaoyan-22408"
OFFICIAL_REPO_SLUG = "yq6666-66/408-codex-plugin"
REPO = Path(__file__).resolve().parents[1]
ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


class VerifyError(RuntimeError):
    """Raised when consumer-side fixed-version verification fails."""


def run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(command, 127, "", str(exc))


def _relay(result: subprocess.CompletedProcess[str], stream: TextIO) -> None:
    encoding = getattr(stream, "encoding", None)

    def write(value: str) -> None:
        if encoding:
            value = value.encode(encoding, errors="backslashreplace").decode(encoding)
        print(value.rstrip(), file=stream)

    if result.stdout:
        write(result.stdout)
    if result.stderr:
        write(result.stderr)


def _strip_ansi(line: str) -> str:
    return ANSI_ESCAPE.sub("", line).strip()


def _marketplace_sources(output: str) -> list[str]:
    """Legacy text fallback: `kaoyan-408 <source>` lines."""
    sources: list[str] = []
    for raw_line in output.splitlines():
        line = _strip_ansi(raw_line)
        if not line:
            continue
        fields = line.split(maxsplit=1)
        if len(fields) == 2 and fields[0].casefold() == MARKETPLACE_NAME.casefold():
            sources.append(fields[1].strip().strip("\"'"))
    return sources


def parse_marketplace_json(text: str) -> list[dict[str, str]] | None:
    """Parse the official CLI structured JSON listing.

    Returns a normalized list of entries (``name``/``kind``/``location``) or
    ``None`` when the output is not structured JSON for this CLI version.
    """
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        return None
    entries_raw: object = document
    if isinstance(document, dict):
        for key in ("marketplaces", "entries", "items", "data"):
            if isinstance(document.get(key), list):
                entries_raw = document[key]
                break
    if not isinstance(entries_raw, list):
        return None
    entries: list[dict[str, str]] = []
    for raw in entries_raw:
        if not isinstance(raw, dict):
            continue
        name = raw.get("name")
        if not isinstance(name, str):
            continue
        source = raw.get("source")
        kind = "unknown"
        location = ""
        if isinstance(source, dict):
            source_kind = source.get("source") or source.get("kind") or source.get("type")
            if isinstance(source_kind, str):
                kind = source_kind.lower()
            for key in ("repo", "repository", "url", "path", "location"):
                value = source.get(key)
                if isinstance(value, str) and value:
                    location = value
                    break
        elif isinstance(source, str):
            location = source
        entries.append({"name": name, "kind": kind, "location": location})
    return entries


def _canonical_path_text(value: str | Path) -> str:
    resolved = Path(str(value)).expanduser().resolve()
    return os.path.normcase(os.path.normpath(str(resolved)))


def _has_cache_segment(location: str) -> bool:
    parts = {part.lower() for part in PurePath(location.replace("\\", "/")).parts}
    return "cache" in parts


def official_repo_slugs(repo: Path) -> set[str]:
    """Derive acceptable git-marketplace slugs from the repository remote."""
    slugs = {OFFICIAL_REPO_SLUG}
    result = run_command(["git", "remote", "get-url", "origin"], repo)
    if result.returncode == 0:
        url = result.stdout.strip()
        match = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?/?$", url)
        if match:
            slugs.add(match.group(1).lower())
    return slugs


def _entry_points_to_repo(entry: dict[str, str], repo: Path, slugs: set[str]) -> tuple[bool, str]:
    """Return (points_to_repo, failure_reason). Cache directories never count."""
    kind = entry.get("kind", "unknown")
    location = entry.get("location", "")
    if kind == "cache" or _has_cache_segment(location):
        return False, f"marketplace source is a cache directory, not a verifiable source: {location or '(unspecified)'}"
    if kind == "git":
        normalized = location.lower().removesuffix(".git").rstrip("/")
        slug = re.sub(r"^https?://github\.com/", "", normalized)
        slug = re.sub(r"^git@github\.com:", "", slug)
        return (slug in slugs), f"git marketplace points to {location!r}, expected one of {sorted(slugs)}"
    if not location:
        return False, "marketplace entry does not expose a verifiable source location"
    return (_canonical_path_text(location) == _canonical_path_text(repo)), (
        f"local marketplace points to {location!r}, expected {_canonical_path_text(repo)}"
    )


def collect_marketplaces(
    codex: str,
    repo: Path,
    runner: Runner,
) -> tuple[list[dict[str, str]], subprocess.CompletedProcess[str]]:
    """Prefer the official CLI structured JSON listing; fall back to text."""
    json_listing = runner([codex, "plugin", "marketplace", "list", "--json"], repo)
    if json_listing.returncode == 0:
        entries = parse_marketplace_json(f"{json_listing.stdout}\n{json_listing.stderr}")
        if entries is not None:
            return entries, json_listing
    listing = runner([codex, "plugin", "marketplace", "list"], repo)
    if listing.returncode != 0:
        return [], listing
    entries = [
        {"name": MARKETPLACE_NAME, "kind": "unknown", "location": source}
        for source in _marketplace_sources(f"{listing.stdout}\n{listing.stderr}")
    ]
    return entries, listing


def verify_release_bundle(
    archive_path: Path,
    *,
    expected_sha256: str | None = None,
    expected_version: str | None = None,
    now: object = None,
) -> dict[str, str]:
    """Verify a consumer's fixed-version Release ZIP.

    ``now`` is accepted so callers can prove time-independence in tests; it is
    deliberately never consulted. A hash-correct pinned version must verify
    31 days, one year, or any duration after publication.
    """
    del now  # consumer verification must never depend on wall-clock time
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise VerifyError(f"release archive does not exist: {archive_path}")
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256.lower():
        raise VerifyError(
            f"release archive SHA-256 mismatch: expected {expected_sha256.lower()}, computed {digest}"
        )
    names = validate_release_archive(archive_path)
    version = archive_manifest_version(archive_path)
    if expected_version is not None and version != expected_version:
        raise VerifyError(
            f"release archive version mismatch: archive manifest is {version}, expected {expected_version}"
        )
    return {"version": version, "files": str(len(names)), "sha256": digest}


def verify_plugin_tree(
    directory: Path,
    *,
    expected_version: str | None = None,
    expected_tree_sha256: str | None = None,
) -> dict[str, str]:
    """Verify an installed or extracted plugin tree: structure, version, digest."""
    directory = Path(directory)
    if not directory.is_dir():
        raise VerifyError(f"plugin directory does not exist: {directory}")
    manifest_path = directory / ".codex-plugin" / "plugin.json"
    if not manifest_path.is_file():
        raise VerifyError(f"plugin manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VerifyError(f"cannot read plugin manifest: {exc}") from exc
    version = manifest.get("version") if isinstance(manifest, dict) else None
    if not isinstance(version, str) or re.fullmatch(SEMVER_PATTERN, version) is None:
        raise VerifyError("plugin manifest version is not release semver")
    if expected_version is not None and version != expected_version:
        raise VerifyError(f"installed plugin version mismatch: found {version}, expected {expected_version}")
    actual_files = {
        path.relative_to(directory).as_posix().replace("\\", "/")
        for path in directory.rglob("*")
        if path.is_file()
    }
    if actual_files != set(ALLOWED_RELEASE_FILES):
        missing = sorted(set(ALLOWED_RELEASE_FILES) - actual_files)
        extra = sorted(actual_files - set(ALLOWED_RELEASE_FILES))
        raise VerifyError(f"plugin tree does not match the release allowlist; missing={missing}, extra={extra}")
    payloads: dict[str, bytes] = {}
    for relative in sorted(actual_files):
        payloads[relative] = (directory / Path(*relative.split("/"))).read_bytes()
    digest = plugin_tree_digest(payloads)
    if expected_tree_sha256 is not None and digest != expected_tree_sha256.lower():
        raise VerifyError(
            f"installed plugin tree SHA-256 mismatch: expected {expected_tree_sha256.lower()}, computed {digest}"
        )
    return {"version": version, "files": str(len(actual_files)), "treeSha256": digest}


def install_local(
    repo: Path,
    *,
    validate_only: bool = False,
    runner: Runner = run_command,
    which: Which = shutil.which,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Compatibility entry point; see :func:`run_install`."""
    return run_install(
        repo,
        validate_only=validate_only,
        runner=runner,
        which=which,
        stdout=stdout,
        stderr=stderr,
    )


def run_install(
    repo: Path,
    *,
    validate_only: bool = False,
    runner: Runner = run_command,
    which: Which = shutil.which,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """Install flow: structural validation, then official CLI marketplace install.

    Consumers installing a fixed version run structural gates only; the
    maintainer evidence-freshness gate is a separate release flow and never
    rejects a pinned version for being published more than 30 days ago.
    """
    repo = repo.resolve()
    validation = runner(
        [
            sys.executable,
            str(repo / "scripts" / "check.py"),
            "--skip-system-validators",
        ],
        repo,
    )
    _relay(validation, stdout if validation.returncode == 0 else stderr)
    if validation.returncode != 0:
        print("Validation failed; installation was not attempted.", file=stderr)
        return 1
    if validate_only:
        print("Validation completed.", file=stdout)
        return 0

    codex = which("codex")
    if not codex:
        print(
            "This host has no Codex CLI on PATH. Restart ChatGPT/Codex Desktop and install "
            "kaoyan-408 from this repository marketplace.",
            file=stderr,
        )
        return 2

    plugin_help = runner([codex, "plugin", "--help"], repo)
    help_text = f"{plugin_help.stdout}\n{plugin_help.stderr}".lower()
    if plugin_help.returncode != 0 or "plugin" not in help_text:
        print(
            "This Codex CLI has no usable plugin subcommand. Restart ChatGPT/Codex Desktop and "
            "install kaoyan-408 from this repository marketplace.",
            file=stderr,
        )
        return 2

    entries, listing = collect_marketplaces(codex, repo, runner)
    if not entries and listing.returncode != 0:
        _relay(listing, stderr)
        print("Unable to list Codex marketplaces.", file=stderr)
        return 1

    same_name = [entry for entry in entries if entry.get("name", "").casefold() == MARKETPLACE_NAME.casefold()]
    if same_name:
        slugs = official_repo_slugs(repo)
        for entry in same_name:
            points_to_repo, reason = _entry_points_to_repo(entry, repo, slugs)
            if not points_to_repo:
                print(
                    "A marketplace named kaoyan-408 already exists, but its source cannot be verified "
                    f"as this repository: {reason}",
                    file=stderr,
                )
                return 1
    else:
        add_marketplace = runner(
            [codex, "plugin", "marketplace", "add", str(repo)],
            repo,
        )
        if add_marketplace.returncode != 0:
            _relay(add_marketplace, stderr)
            print("Unable to add the local repository marketplace.", file=stderr)
            return 1

    install = runner(
        [codex, "plugin", "add", f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"],
        repo,
    )
    if install.returncode != 0:
        _relay(install, stderr)
        print("Unable to install the local plugin.", file=stderr)
        return 1

    print(f"Installed {PLUGIN_NAME}. Start a new task before testing the Skills.", file=stdout)
    installed_plugins = runner([codex, "plugin", "list"], repo)
    installed_text = f"{installed_plugins.stdout}\n{installed_plugins.stderr}".casefold()
    if installed_plugins.returncode == 0 and LEGACY_PLUGIN_NAME.casefold() in installed_text:
        print(
            f"Migration: {LEGACY_PLUGIN_NAME} is still installed. Verify {PLUGIN_NAME} in a new task "
            "before disabling or removing the legacy plugin.",
            file=stdout,
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    install_parser = subparsers.add_parser("install", help="validate then install via the official CLI")
    install_parser.add_argument("--validate-only", action="store_true")
    install_parser.set_defaults(handler="install")

    verify_release_parser = subparsers.add_parser(
        "verify-release", help="consumer fixed-version verification of a Release ZIP"
    )
    verify_release_parser.add_argument("--zip", type=Path, required=True)
    verify_release_parser.add_argument("--sha256", default=None)
    verify_release_parser.add_argument("--version", default=None)
    verify_release_parser.set_defaults(handler="verify-release")

    verify_tree_parser = subparsers.add_parser(
        "verify-tree", help="verify an installed or extracted plugin tree"
    )
    verify_tree_parser.add_argument("--dir", type=Path, required=True)
    verify_tree_parser.add_argument("--version", default=None)
    verify_tree_parser.add_argument("--tree-sha256", default=None)
    verify_tree_parser.set_defaults(handler="verify-tree")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = sys.argv[1:] if argv is None else list(argv)
    if arguments and arguments[0] not in {"install", "verify-release", "verify-tree", "-h", "--help"}:
        # Backwards compatibility: bare `install_local.py [--validate-only]` is the install flow.
        arguments = ["install", *arguments]
    args = parser.parse_args(arguments)
    if args.command is None:
        parser.print_usage(sys.stderr)
        return 2
    try:
        if args.handler == "install":
            return run_install(REPO, validate_only=args.validate_only)
        if args.handler == "verify-release":
            result = verify_release_bundle(
                args.zip,
                expected_sha256=args.sha256,
                expected_version=args.version,
            )
        else:
            result = verify_plugin_tree(
                args.dir,
                expected_version=args.version,
                expected_tree_sha256=args.tree_sha256,
            )
    except (VerifyError, ValidationError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    for key in sorted(result):
        print(f"[OK] {key}: {result[key]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

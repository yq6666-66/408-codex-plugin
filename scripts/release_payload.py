#!/usr/bin/env python3
"""Single source of truth for the release payload: allowlist, schemas of record, and ZIP validation.

This module must stay importable with the Python standard library only, so that
consumer-side fixed-version install verification works without PyYAML/jsonschema.
"""

from __future__ import annotations

import stat
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from zipfile import ZipInfo


PLUGIN_RELATIVE_PATH = PurePosixPath("plugins/kaoyan-408")

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
}

EXPECTED_REFERENCES = {
    "capability-routing-contract.md",
    "evidence-copyright-contract.md",
    "learning-layer-contract.md",
    "obsidian-brain-contract.md",
    "notion-brain-contract.md",
    "portable-learning-records.md",
    "portable-learning-records.schema.json",
    "past-paper-source-contract.md",
    "past-paper-knowledge.schema.json",
    "beginner-visual-answer-contract.md",
}

ALLOWED_PLUGIN_ROOTS = {".codex-plugin", "skills", "references", "assets"}
SEMVER_PATTERN = r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$"
PLACEHOLDER = "TO" + "DO"

FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
UTF8_FLAG = 0x800


class ValidationError(RuntimeError):
    """Raised when a repository or release contract is violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def read_utf8_text(path: Path, *, require_lf: bool = True) -> str:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    require(b"\x00" not in payload, f"text file contains NUL bytes: {path}")
    if require_lf:
        require(b"\r" not in payload, f"release text must use LF, not CRLF: {path}")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationError(f"file is not valid UTF-8: {path}: {exc}") from exc


def expected_release_files() -> frozenset[str]:
    names = {
        ".codex-plugin/plugin.json",
        "assets/kaoyan-408.svg",
        *(f"references/{name}" for name in EXPECTED_REFERENCES),
    }
    for skill in EXPECTED_SKILLS:
        names.add(f"skills/{skill}/SKILL.md")
        names.add(f"skills/{skill}/agents/openai.yaml")
    return frozenset(names)


ALLOWED_RELEASE_FILES = expected_release_files()


class Utf8ZipInfo(ZipInfo):
    """ZipInfo that always marks names as UTF-8, including ASCII-only names."""

    def _encodeFilenameFlags(self) -> tuple[bytes, int]:  # noqa: N802 - zipfile API name
        return self.filename.encode("utf-8"), self.flag_bits | UTF8_FLAG


def plugin_tree_digest(payloads: dict[str, bytes]) -> str:
    """Hash a plugin tree unambiguously by path and payload length."""
    import hashlib

    digest = hashlib.sha256()
    for name in sorted(payloads):
        encoded_name = name.encode("utf-8")
        payload = payloads[name]
        digest.update(len(encoded_name).to_bytes(4, "big"))
        digest.update(encoded_name)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def validate_release_archive(archive_path: Path) -> tuple[str, ...]:
    """Reject malformed, ambiguous, or non-reproducible release ZIPs."""
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            duplicates = [name for name, count in Counter(names).items() if count > 1]
            if duplicates:
                raise ValidationError(f"release ZIP contains duplicate members: {sorted(duplicates)}")
            if set(names) != set(ALLOWED_RELEASE_FILES) or names != sorted(ALLOWED_RELEASE_FILES):
                raise ValidationError("release ZIP does not match the exact ordered allowlist")
            if archive.comment:
                raise ValidationError("release ZIP comment must be empty")
            for info in infos:
                name = info.filename
                pure = PurePosixPath(name)
                if (
                    not name
                    or "\\" in name
                    or pure.is_absolute()
                    or any(part in {"", ".", ".."} for part in pure.parts)
                    or pure.as_posix() != name
                ):
                    raise ValidationError(f"unsafe or non-canonical ZIP path: {name}")
                mode = (info.external_attr >> 16) & 0xFFFF
                if info.create_system != 3 or not stat.S_ISREG(mode) or stat.S_IMODE(mode) != 0o644:
                    raise ValidationError(f"ZIP member metadata is not canonical regular 0644: {name}")
                if info.date_time != FIXED_ZIP_TIME:
                    raise ValidationError(f"ZIP member timestamp is not canonical: {name}")
                if info.compress_type != zipfile.ZIP_STORED:
                    raise ValidationError(f"ZIP member must use ZIP_STORED: {name}")
                if not (info.flag_bits & UTF8_FLAG):
                    raise ValidationError(f"ZIP member is missing the UTF-8 flag: {name}")
                payload = archive.read(info)
                if b"\x00" in payload or b"\r" in payload:
                    raise ValidationError(f"ZIP member is not canonical UTF-8/LF text: {name}")
                try:
                    payload.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise ValidationError(f"ZIP member is not valid UTF-8: {name}") from exc
            bad_member = archive.testzip()
            if bad_member is not None:
                raise ValidationError(f"ZIP CRC check failed: {bad_member}")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValidationError(f"invalid release ZIP: {archive_path}: {exc}") from exc
    return tuple(names)


def archive_manifest_version(archive_path: Path) -> str:
    """Read the manifest version from a release ZIP without trusting the filename."""
    import json
    import re

    with zipfile.ZipFile(archive_path, "r") as archive:
        payload = archive.read(".codex-plugin/plugin.json")
    try:
        manifest = json.loads(payload.decode("utf-8"))
        version = manifest["version"]
    except (KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValidationError(f"release ZIP manifest is unreadable: {exc}") from exc
    if not isinstance(version, str) or re.fullmatch(
        r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version
    ) is None:
        raise ValidationError("release ZIP manifest version is not release semver")
    return version


def check_accuracy_semantics(record: dict) -> None:
    """Enforce numeric relationships JSON Schema cannot express portably."""
    import math

    require(record.get("recordType") == "ProgressSnapshot", "accuracy semantics require ProgressSnapshot")
    accuracy = record.get("accuracy")
    require(isinstance(accuracy, list), "ProgressSnapshot accuracy must be an array")
    for index, entry in enumerate(accuracy):
        require(isinstance(entry, dict), f"accuracy[{index}] must be an object")
        correct = entry.get("correct")
        total = entry.get("total")
        rate = entry.get("rate")
        if correct is not None and total is not None:
            require(correct <= total, f"accuracy[{index}].correct must not exceed total")
        if total == 0:
            require(correct in {None, 0}, f"accuracy[{index}].correct must be 0 or null when total is zero")
            require(rate is None, f"accuracy[{index}].rate must be null when total is zero")
        elif correct is not None and total is not None and rate is not None:
            expected_rate = correct / total
            require(
                math.isclose(rate, expected_rate, rel_tol=0.0, abs_tol=1e-12),
                f"accuracy[{index}].rate must equal correct / total",
            )


MASTERY_CAPABLE_EVIDENCE_TYPES = {"independent", "transfer"}


def retest_evidence_supports_mastery(item: dict) -> bool:
    """True only when structured retest evidence contains independent or transfer success."""
    evidence = item.get("retestEvidence")
    if not isinstance(evidence, list):
        return bool(item.get("masteryEvidence"))
    for entry in evidence:
        if not isinstance(entry, dict):
            continue
        if entry.get("evidenceType") in MASTERY_CAPABLE_EVIDENCE_TYPES and entry.get(
            "outcome"
        ) in {"correct", None}:
            return True
    return False


def check_mastery_evidence_semantics(record: dict) -> list[str]:
    """Return warnings when a mastered ReviewQueue item lacks qualifying evidence.

    Reading legacy records never fails on this rule; writing new 1.2 records must
    not upgrade an item to ``mastered`` without independent or transfer evidence.
    """
    warnings: list[str] = []
    if record.get("recordType") != "ReviewQueue":
        return warnings
    items = record.get("items")
    if not isinstance(items, list):
        return warnings
    for index, item in enumerate(items):
        if not isinstance(item, dict) or item.get("status") != "mastered":
            continue
        if retest_evidence_supports_mastery(item):
            continue
        warnings.append(
            f"items[{index}] is marked mastered without independent or transfer retest evidence"
        )
    return warnings


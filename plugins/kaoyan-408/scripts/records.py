#!/usr/bin/env python3
"""Unified CLI for portable learning records (Schema 1.0 / 1.1 / 1.2).

Subcommands:
  validate   Check a record (file or ``-`` for stdin); exit 1 on invalid input.
  normalize  Upgrade 1.0/1.1 records to Schema 1.2 without fabricating evidence.
  merge      Deterministically merge two record documents without dropping data.
  due        List due review items using an explicit base date (``--date``).
  checkpoint Create or read a lightweight SessionCheckpoint.

All successful output is JSON on stdout. Errors go to stderr as JSON with a
non-zero exit code (0 ok, 1 record error, 2 usage error). Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

SCHEMA_VERSION_CURRENT = "1.2"
SENTINELS = {"", "未提供", "unknown"}
DATE_PATTERN_LENGTH = 10
RECORD_TYPES = {"StudyProfile", "ProgressSnapshot", "ReviewQueue", "SessionCheckpoint"}
LEGACY_RECORD_TYPES = {"StudyProfile", "ProgressSnapshot", "ReviewQueue"}
EVIDENCE_TYPES = {"independent", "hint-assisted", "solution-seen", "redo-after-solution", "transfer"}
EVIDENCE_OUTCOMES = {"correct", "incorrect", "partial", None}
MASTERY_CAPABLE = {"independent", "transfer"}
ITEM_STATUSES = {"pending", "due", "retesting", "mastered", None}
ERROR_CAUSE_STATUSES = {"confirmed", "hypothesis", None}
TEACHING_MODES = {"detailed", "hint", "independent", "mock", None}
ANSWER_STATES = {"hidden", "partial", "revealed", None}
SENSITIVE_EXTENSION_KEY = re.compile(
    r"(?:^|_)(?:api_?key|api_?token|access_?token|refresh_?token|token|secret|password|passwd|"
    r"credential|authorization|cookie|email|phone|mobile|telephone|id_?card|passport|national_?id|"
    r"identity_?(?:number|no)|student_?(?:id|number)|candidate_?(?:id|number)|user_?(?:id|name)|"
    r"account_?(?:id|name)|(?:device|local|home|file|absolute|vault)_?path|path|"
    r"(?:raw|source|question|paper)_?(?:material|text|content)|(?:real|full)_?name)(?:_|$)|^(?:name)$",
    re.IGNORECASE,
)
SENSITIVE_PATH_VALUE = re.compile(
    r"(?:\b[A-Za-z]:[\\/]|\\\\[^\\\s]+[\\/][^\\\s]+|/(?:Users|home|root|private|var)/)",
    re.IGNORECASE,
)
SENSITIVE_TOKEN_VALUE = re.compile(
    r"(?:\bBearer\s+\S+|\b(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{12,})",
    re.IGNORECASE,
)


class RecordError(RuntimeError):
    """Raised when a record document violates the portable-record contract."""


def is_plain_date(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != DATE_PATTERN_LENGTH:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def is_sentinel(value: Any) -> bool:
    return isinstance(value, str) and value.strip() in SENTINELS


def is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != "" and not is_sentinel(value)


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_id(prefix: str, record: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(record).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:16]}"


def load_document(source: str) -> Any:
    if source == "-":
        payload = sys.stdin.read()
    else:
        try:
            payload = Path(source).read_text(encoding="utf-8")
        except OSError as exc:
            raise RecordError(f"cannot read input: {exc}") from exc
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RecordError(f"input is not valid JSON: {exc}") from exc


def as_record_list(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        items = document
    elif isinstance(document, dict) and isinstance(document.get("records"), list):
        items = document["records"]
    else:
        items = [document]
    for item in items:
        if not isinstance(item, dict):
            raise RecordError("every record must be a JSON object")
    return items


def emit(document: Any) -> None:
    print(json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False))


def infer_record_type_10(record: dict[str, Any]) -> str | None:
    if "items" in record:
        return "ReviewQueue"
    if any(key in record for key in ("bySubject", "sampleSize", "plannedUnits", "completedUnits")):
        return "ProgressSnapshot"
    if "targetExam" in record or "currentPhase" in record or "constraints" in record:
        return "StudyProfile"
    if "period" in record or "blockers" in record or "accuracy" in record:
        return "ProgressSnapshot"
    return None


def _convert_sentinels(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _convert_sentinels(item) for key, item in value.items()}
    if isinstance(value, list):
        converted = [_convert_sentinels(item) for item in value]
        if any(is_sentinel(item) for item in value):
            return [item for item in converted if not is_sentinel(item)]
        return converted
    if is_sentinel(value):
        return None
    return value


def _contains_sentinel(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_sentinel(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_sentinel(item) for item in value)
    return is_sentinel(value)


def _pointer_escape(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _is_sensitive_extension_key(key: str) -> bool:
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key)
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", separated).strip("_")
    return bool(SENSITIVE_EXTENSION_KEY.search(normalized))


def _redact_legacy_extensions(extensions: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    redacted: list[str] = []

    def scrub(value: Any, pointer: str) -> Any:
        if isinstance(value, dict):
            output: dict[str, Any] = {}
            for raw_key, child in value.items():
                key = str(raw_key)
                child_pointer = f"{pointer}/{_pointer_escape(key)}"
                if _is_sensitive_extension_key(key):
                    output[raw_key] = None
                    redacted.append(child_pointer)
                else:
                    output[raw_key] = scrub(child, child_pointer)
            return output
        if isinstance(value, list):
            return [scrub(child, f"{pointer}/{index}") for index, child in enumerate(value)]
        if isinstance(value, str) and (
            SENSITIVE_PATH_VALUE.search(value) or SENSITIVE_TOKEN_VALUE.search(value)
        ):
            redacted.append(pointer)
            return None
        return value

    cleaned = {
        key: None if _is_sensitive_extension_key(key) else scrub(value, f"/legacyExtensions/{_pointer_escape(key)}")
        for key, value in extensions.items()
    }
    for key in extensions:
        if _is_sensitive_extension_key(key):
            redacted.append(f"/legacyExtensions/{_pointer_escape(key)}")
    return cleaned, sorted(set(redacted))


def normalize_10_to_11(record: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    if _contains_sentinel(record):
        warnings.append(
            "legacy sentinel values (empty string / 未提供 / unknown) converted to null or empty arrays"
        )
    record_type = record.get("recordType") or infer_record_type_10(record)
    if record_type is None:
        raise RecordError("cannot infer recordType from a Schema 1.0 object")
    converted: dict[str, Any] = {
        "schemaVersion": "1.1",
        "recordType": record_type,
    }
    unknown: dict[str, Any] = {}
    known_keys = {
        "targetExam", "targetDate", "weeklyHours", "currentPhase", "constraints",
        "period", "plannedUnits", "completedUnits", "accuracy", "sampleSize",
        "bySubject", "blockers", "items", "generatedAt", "unit", "recordType",
    }
    for key, value in record.items():
        if key == "schemaVersion" or key in known_keys:
            continue
        unknown[key] = value
    if record_type == "StudyProfile":
        converted["targetExam"] = _convert_sentinels(record.get("targetExam"))
        converted["targetDate"] = _convert_sentinels(record.get("targetDate"))
        converted["weeklyHours"] = _convert_sentinels(record.get("weeklyHours"))
        converted["currentPhase"] = _convert_sentinels(record.get("currentPhase"))
        constraints = record.get("constraints")
        converted["constraints"] = (
            [item for item in constraints if not is_sentinel(item)]
            if isinstance(constraints, list)
            else []
        )
    elif record_type == "ProgressSnapshot":
        period = record.get("period")
        converted["period"] = {
            "start": _convert_sentinels(period.get("start")) if isinstance(period, dict) else None,
            "end": _convert_sentinels(period.get("end")) if isinstance(period, dict) else None,
        }
        metrics: list[dict[str, Any]] = []
        if "plannedUnits" in record or "completedUnits" in record:
            raw_unit = _convert_sentinels(record.get("unit")) if "unit" in record else None
            unit_is_valid = is_non_empty_string(raw_unit)
            unit = raw_unit if unit_is_valid else "unspecified"
            metrics.append({
                "subject": None,
                "name": "overall",
                "unit": unit,
                "planned": _convert_sentinels(record.get("plannedUnits")),
                "completed": _convert_sentinels(record.get("completedUnits")),
            })
            if not unit_is_valid:
                warnings.append("root plannedUnits/completedUnits carry no unit; using 'unspecified'")
        by_subject = record.get("bySubject")
        if isinstance(by_subject, list):
            for entry in by_subject:
                if not isinstance(entry, dict):
                    continue
                metrics.append({
                    "subject": _convert_sentinels(entry.get("subject")),
                    "name": "workload",
                    "unit": "unspecified" if "unit" not in entry else entry["unit"],
                    "planned": _convert_sentinels(entry.get("plannedUnits")),
                    "completed": _convert_sentinels(entry.get("completedUnits")),
                })
        converted["metrics"] = metrics
        accuracy_value = _convert_sentinels(record.get("accuracy"))
        sample_size = _convert_sentinels(record.get("sampleSize"))
        accuracy_entries: list[dict[str, Any]] = []
        if isinstance(accuracy_value, (int, float)) or accuracy_value is None:
            accuracy_entries.append({
                "subject": None,
                "correct": None,
                "total": sample_size,
                "rate": accuracy_value,
            })
            if accuracy_value is not None and sample_size is None:
                warnings.append("legacy accuracy has no sampleSize; total set to null")
        converted["accuracy"] = accuracy_entries
        blockers = record.get("blockers")
        converted["blockers"] = (
            [item for item in blockers if not is_sentinel(item)]
            if isinstance(blockers, list)
            else []
        )
    else:
        converted["generatedAt"] = _convert_sentinels(record.get("generatedAt"))
        items: list[dict[str, Any]] = []
        raw_items = record.get("items")
        if "items" in record and not isinstance(raw_items, list):
            raise RecordError("items must be an array")
        for index, entry in enumerate(raw_items if isinstance(raw_items, list) else []):
            if not isinstance(entry, dict):
                raise RecordError(f"items[{index}] must be an object")
            retest_date = entry.get("retestDate")
            item: dict[str, Any] = {
                "subject": _convert_sentinels(entry.get("subject")),
                "topic": _convert_sentinels(entry.get("topic")),
                "errorCause": _convert_sentinels(entry.get("errorCause")),
                "errorCauseStatus": None,
                "nextRetestDate": None,
                "retestOffsetDays": None,
                "status": _convert_sentinels(entry.get("status")),
                "masteryEvidence": [],
            }
            if isinstance(retest_date, str) and retest_date.strip().upper().startswith("D+"):
                try:
                    item["retestOffsetDays"] = int(retest_date.strip()[2:])
                except ValueError:
                    warnings.append(f"unparseable legacy retestDate {retest_date!r} kept as null")
            elif is_plain_date(retest_date):
                item["nextRetestDate"] = retest_date
            elif retest_date is not None:
                warnings.append(f"legacy retestDate {retest_date!r} is neither D+N nor a date; set to null")
            evidence = entry.get("masteryEvidence")
            item["masteryEvidence"] = (
                [text for text in evidence if not is_sentinel(text)]
                if isinstance(evidence, list)
                else []
            )
            items.append(item)
        converted["items"] = items
    if unknown:
        converted["legacyExtensions"], redacted_fields = _redact_legacy_extensions(unknown)
        warnings.append(
            "unknown legacy fields preserved under legacyExtensions: "
            + ", ".join(sorted(unknown))
        )
        if redacted_fields:
            converted["redactedFields"] = redacted_fields
            warnings.append("sensitive legacy extension values redacted at: " + ", ".join(redacted_fields))
    return converted, warnings


def normalize_to_12(record: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Normalize a 1.0/1.1/1.2 record to Schema 1.2. Idempotent and evidence-safe."""
    warnings: list[str] = []
    converted = json.loads(canonical_json(record))
    version = converted.get("schemaVersion")
    if version == "1.0":
        converted, migrate_warnings = normalize_10_to_11(converted)
        warnings.extend(migrate_warnings)
    record_type = converted.get("recordType")
    if record_type not in RECORD_TYPES:
        raise RecordError(f"unknown recordType: {record_type!r}")
    converted["schemaVersion"] = SCHEMA_VERSION_CURRENT
    if not converted.get("recordId"):
        converted["recordId"] = stable_id("kr", record)
    if "updatedAt" not in converted:
        converted["updatedAt"] = None
    if record_type == "ReviewQueue":
        items = converted.get("items", [])
        if not isinstance(items, list):
            raise RecordError("items must be an array")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise RecordError(f"items[{index}] must be an object")
            if "retestEvidence" not in item:
                item["retestEvidence"] = []
            if "itemId" not in item:
                item["itemId"] = stable_id("kr", {**item, "_index": index})
            if item.get("status") == "mastered":
                warnings.extend(
                    f"items[{index}]: {message}"
                    for message in mastery_warnings(item, index)
                )
    if record_type == "SessionCheckpoint" and not converted.get("checkpointId"):
        converted["checkpointId"] = stable_id("kc", record)
    if record == converted:
        return converted, warnings
    return converted, warnings


def mastery_warnings(item: dict[str, Any], index: int) -> list[str]:
    if item.get("status") != "mastered":
        return []
    evidence = item.get("retestEvidence")
    if isinstance(evidence, list) and any(
        isinstance(entry, dict)
        and entry.get("evidenceType") in MASTERY_CAPABLE
        and entry.get("outcome") == "correct"
        for entry in evidence
    ):
        return []
    return ["status is mastered without independent or transfer retest evidence"]


def _require(record: dict[str, Any], key: str, errors: list[str]) -> None:
    if key not in record:
        errors.append(f"missing required field: {key}")


def _array_or_empty(record: dict[str, Any], key: str, errors: list[str]) -> list[Any]:
    if key not in record:
        return []
    value = record[key]
    if not isinstance(value, list):
        errors.append(f"{key} must be an array")
        return []
    return value


def _check_nullable_string(record: dict[str, Any], key: str, errors: list[str]) -> None:
    value = record.get(key)
    if value is None:
        return
    if not is_non_empty_string(value):
        errors.append(f"{key} must be a non-empty string or null, got {value!r}")


def _check_date(record: dict[str, Any], key: str, errors: list[str]) -> None:
    value = record.get(key)
    if value is None:
        return
    if not is_plain_date(value):
        errors.append(f"{key} must be a YYYY-MM-DD date or null, got {value!r}")


def validate_current(record: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Hand-rolled structural validation for Schema 1.1/1.2 records."""
    errors: list[str] = []
    warnings: list[str] = []
    record_type = record.get("recordType")
    version = record.get("schemaVersion")
    if record_type not in RECORD_TYPES or record_type == "SessionCheckpoint" and version != "1.2":
        errors.append(f"unsupported recordType/schemaVersion: {record_type!r}/{version!r}")
        return errors, warnings
    if version not in {"1.1", "1.2"}:
        errors.append(f"schemaVersion must be 1.1 or 1.2 at the root, got {version!r}")
        return errors, warnings
    if record.get("recordId") is not None:
        rid = record["recordId"]
        if not isinstance(rid, str) or len(rid) != 19 or not rid.startswith("kr-"):
            errors.append(f"recordId must match kr- plus 16 lowercase hex digits, got {rid!r}")
    _check_date(record, "updatedAt", errors)

    if record_type == "StudyProfile":
        for key in ("targetExam", "targetDate", "weeklyHours", "currentPhase", "constraints"):
            _require(record, key, errors)
        _check_nullable_string(record, "targetExam", errors)
        _check_date(record, "targetDate", errors)
        _check_nullable_string(record, "currentPhase", errors)
        if not isinstance(record.get("constraints"), list):
            errors.append("constraints must be an array")
        weekly = record.get("weeklyHours")
        if weekly is not None and (not isinstance(weekly, (int, float)) or weekly < 0):
            errors.append("weeklyHours must be a non-negative number or null")
    elif record_type == "ProgressSnapshot":
        for key in ("period", "metrics", "accuracy", "blockers"):
            _require(record, key, errors)
        period = record.get("period")
        if not isinstance(period, dict):
            errors.append("period must be an object")
        else:
            for key in ("start", "end"):
                value = period.get(key)
                if value is not None and not is_plain_date(value):
                    errors.append(f"period.{key} must be a YYYY-MM-DD date or null, got {value!r}")
        for index, entry in enumerate(_array_or_empty(record, "metrics", errors)):
            if not isinstance(entry, dict):
                errors.append(f"metrics[{index}] must be an object")
                continue
            for key in ("subject", "name", "unit", "planned", "completed"):
                if key not in entry:
                    errors.append(f"metrics[{index}] missing {key}")
            if not is_non_empty_string(entry.get("unit", "")):
                errors.append(f"metrics[{index}].unit must be a non-empty string")
        for index, entry in enumerate(_array_or_empty(record, "accuracy", errors)):
            if not isinstance(entry, dict):
                errors.append(f"accuracy[{index}] must be an object")
                continue
            for key in ("subject", "correct", "total", "rate"):
                if key not in entry:
                    errors.append(f"accuracy[{index}] missing {key}")
            correct, total, rate = entry.get("correct"), entry.get("total"), entry.get("rate")
            correct_valid = correct is None or (
                isinstance(correct, int) and not isinstance(correct, bool) and correct >= 0
            )
            total_valid = total is None or (
                isinstance(total, int) and not isinstance(total, bool) and total >= 0
            )
            rate_valid = rate is None or (
                isinstance(rate, (int, float)) and not isinstance(rate, bool) and 0 <= rate <= 1
            )
            if not correct_valid:
                errors.append(f"accuracy[{index}].correct must be a non-negative integer or null")
            if not total_valid:
                errors.append(f"accuracy[{index}].total must be a non-negative integer or null")
            if not rate_valid:
                errors.append(f"accuracy[{index}].rate must be a number from 0 to 1 or null")
            if correct_valid and total_valid and correct is not None and total is not None and correct > total:
                errors.append(f"accuracy[{index}].correct must not exceed total")
            if total_valid and total == 0:
                if correct not in {None, 0}:
                    errors.append(f"accuracy[{index}].correct must be 0 or null when total is zero")
                if rate is not None:
                    errors.append(f"accuracy[{index}].rate must be null when total is zero")
            elif correct_valid and total_valid and rate_valid and correct is not None and total is not None and rate is not None:
                if abs(rate - correct / total) > 1e-9:
                    errors.append(f"accuracy[{index}].rate must equal correct / total")
        if not isinstance(record.get("blockers"), list):
            errors.append("blockers must be an array")
    elif record_type == "ReviewQueue":
        for key in ("generatedAt", "items"):
            _require(record, key, errors)
        _check_date(record, "generatedAt", errors)
        for index, item in enumerate(_array_or_empty(record, "items", errors)):
            if not isinstance(item, dict):
                errors.append(f"items[{index}] must be an object")
                continue
            for key in ("subject", "topic", "errorCause", "errorCauseStatus",
                        "nextRetestDate", "retestOffsetDays", "status", "masteryEvidence"):
                if key not in item:
                    errors.append(f"items[{index}] missing {key}")
            for key in ("nextRetestDate", "retestAnchorDate"):
                _check_date(item, key, errors)
            if item.get("errorCauseStatus") not in ERROR_CAUSE_STATUSES:
                errors.append(f"items[{index}].errorCauseStatus is invalid: {item.get('errorCauseStatus')!r}")
            if item.get("status") not in ITEM_STATUSES:
                errors.append(f"items[{index}].status is invalid: {item.get('status')!r}")
            offset, anchor = item.get("retestOffsetDays"), item.get("retestAnchorDate")
            offset_is_valid = offset is None or (
                isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0
            )
            if not offset_is_valid:
                errors.append(f"items[{index}].retestOffsetDays must be a non-negative integer or null")
            if is_plain_date(item.get("nextRetestDate", None)) and offset is not None:
                errors.append(
                    f"items[{index}] must not carry nextRetestDate and retestOffsetDays simultaneously"
                )
            if isinstance(offset, int) and not isinstance(offset, bool) and offset >= 0 and not is_plain_date(anchor):
                warnings.append(
                    f"items[{index}] has retestOffsetDays without retestAnchorDate; "
                    "due requires an explicit base date"
                )
            if not isinstance(item.get("masteryEvidence"), list):
                errors.append(f"items[{index}].masteryEvidence must be an array")
            evidence = item.get("retestEvidence", [])
            if not isinstance(evidence, list):
                errors.append(f"items[{index}].retestEvidence must be an array")
            else:
                for position, entry in enumerate(evidence):
                    if not isinstance(entry, dict):
                        errors.append(f"items[{index}].retestEvidence[{position}] must be an object")
                        continue
                    if entry.get("evidenceType") not in EVIDENCE_TYPES:
                        errors.append(
                            f"items[{index}].retestEvidence[{position}].evidenceType is invalid"
                        )
                    if entry.get("outcome") not in EVIDENCE_OUTCOMES:
                        errors.append(
                            f"items[{index}].retestEvidence[{position}].outcome is invalid"
                        )
                    entry_date = entry.get("date")
                    if entry_date is not None and not is_plain_date(entry_date):
                        errors.append(
                            f"items[{index}].retestEvidence[{position}].date must be YYYY-MM-DD or null"
                        )
            warnings.extend(
                f"items[{index}]: {message}" for message in mastery_warnings(item, index)
            )
    else:  # SessionCheckpoint
        for key in ("updatedAt", "currentTask", "position", "dueItems", "pendingRetests"):
            _require(record, key, errors)
        for key in ("dueItems", "pendingRetests"):
            value = record.get(key)
            if not (isinstance(value, list) and all(
                isinstance(entry, str) and entry.strip() for entry in value
            )):
                errors.append(f"{key} must be an array of non-empty strings")
        if record.get("teachingMode") not in TEACHING_MODES:
            errors.append("teachingMode must be detailed, hint, independent, mock, or null")
        if record.get("answerState") not in ANSWER_STATES:
            errors.append("answerState must be hidden, partial, revealed, or null")
        hint_level = record.get("hintLevel")
        if hint_level is not None and (
            isinstance(hint_level, bool) or not isinstance(hint_level, int) or not 0 <= hint_level <= 3
        ):
            errors.append("hintLevel must be an integer from 0 to 3 or null")
        for key in ("currentQuestion", "materialVersion"):
            _check_nullable_string(record, key, errors)
        for key in ("currentTask", "position"):
            _check_nullable_string(record, key, errors)
        for key in ("completedQuestions", "remainingQuestions"):
            if key not in record:
                continue
            value = record[key]
            if not (
                isinstance(value, list)
                and all(isinstance(entry, str) and entry.strip() for entry in value)
                and len(value) == len(set(value))
            ):
                errors.append(f"{key} must be an array of unique non-empty strings")
    return errors, warnings


def validate_record(record: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
    version = record.get("schemaVersion")
    report: dict[str, Any] = {
        "schemaVersion": version,
        "recordType": record.get("recordType"),
    }
    if version == "1.0":
        report["valid"] = True
        report["legacy"] = True
        report["message"] = "Schema 1.0 input is readable; run normalize to upgrade to 1.2"
        report["warnings"] = []
        return report
    errors, warnings = validate_current(record)
    report["errors"] = errors
    report["warnings"] = warnings
    report["valid"] = not errors and not (strict and warnings)
    if strict and warnings and not errors:
        report["errors"] = [*errors, "strict mode: warnings are fatal"]
    return report


def merge_items(
    a: Any,
    b: Any,
    path: str,
    conflicts: list[dict[str, Any]],
    newer: str | None = None,
) -> Any:
    """Deterministic two-way merge with an audit trail for scalar conflicts.

    The newer ``updatedAt`` side supplies the active value, while the conflict
    record retains both inputs. Equal or missing timestamps keep the first
    value and are also recorded. The timestamp field itself is version
    metadata rather than a user-data conflict.
    """
    if a == b:
        return a
    if a is None:
        return b
    if b is None:
        return a
    if isinstance(a, dict) and isinstance(b, dict):
        merged = dict(a)
        for key in b:
            merged[key] = merge_items(a.get(key), b[key], f"{path}/{key}", conflicts, newer)
        return merged
    if isinstance(a, list) and isinstance(b, list):
        return merge_lists(a, b, path, conflicts, newer)
    if path.endswith("/updatedAt"):
        return b if newer == "b" else a
    conflicts.append({
        "path": path,
        "a": a,
        "b": b,
        "resolution": "kept-newer" if newer in {"a", "b"} else "kept-first",
    })
    return b if newer == "b" else a


def _item_key(item: Any) -> tuple[str, ...] | None:
    if not isinstance(item, dict):
        return None
    if item.get("itemId"):
        return ("itemId", str(item["itemId"]))
    subject = item.get("subject")
    topic = item.get("topic")
    if topic:
        return ("topic", str(subject), str(topic))
    name = item.get("name")
    if name:
        return ("metric", str(item.get("subject")), str(name), str(item.get("unit")))
    if subject or topic:
        return ("topic", str(subject), str(topic))
    return None


def merge_lists(
    a: list[Any],
    b: list[Any],
    path: str,
    conflicts: list[dict[str, Any]],
    newer: str | None = None,
) -> list[Any]:
    """Merge keyed list items using the enclosing record's timestamp decision."""
    if any(_item_key(entry) is not None for entry in a) and any(
        _item_key(entry) is not None for entry in b
    ):
        merged = list(a)
        index_of: dict[tuple[str, ...], int] = {}
        for index, entry in enumerate(merged):
            key = _item_key(entry)
            if key is not None and key not in index_of:
                index_of[key] = index
        for entry in b:
            key = _item_key(entry)
            if key is not None and key in index_of:
                target = merged[index_of[key]]
                merged[index_of[key]] = merge_items(
                    target, entry, f"{path}[{key[-1]}]", conflicts, newer
                )
            elif entry not in merged:
                merged.append(entry)
        return merged
    merged = list(a)
    for entry in b:
        if entry not in merged:
            merged.append(entry)
    return merged


def natural_key(record: dict[str, Any]) -> tuple:
    record_type = record.get("recordType")
    if record_type == "ProgressSnapshot":
        period = record.get("period") or {}
        return (record_type, period.get("start"), period.get("end"))
    if record_type == "ReviewQueue":
        return (record_type, record.get("generatedAt"))
    if record_type == "SessionCheckpoint":
        return (record_type, record.get("checkpointId") or record.get("currentTask"))
    return (record_type,)


def records_match(a: dict[str, Any], b: dict[str, Any]) -> bool:
    if a.get("recordType") != b.get("recordType"):
        return False
    id_a, id_b = a.get("recordId"), b.get("recordId")
    if id_a and id_b:
        return id_a == id_b
    return natural_key(a) == natural_key(b)


def merge_records(a: dict[str, Any], b: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not records_match(a, b):
        # Distinct records: keep both rather than dropping either side.
        return {}, []
    conflicts: list[dict[str, Any]] = []
    updated_a, updated_b = a.get("updatedAt"), b.get("updatedAt")
    newer = None
    if is_plain_date(updated_a) and is_plain_date(updated_b) and updated_a != updated_b:
        newer = "b" if updated_b > updated_a else "a"
    merged = merge_items(a, b, "", conflicts, newer)
    return merged, conflicts


def merge_documents(a: Any, b: Any) -> dict[str, Any]:
    records_a = as_record_list(a)
    records_b = as_record_list(b)
    merged_records: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    pending_b = list(records_b)
    for record_a in records_a:
        merged_record = record_a
        remaining: list[dict[str, Any]] = []
        for record_b in pending_b:
            joined, record_conflicts = merge_records(merged_record, record_b)
            if joined:
                merged_record = joined
                conflicts.extend(record_conflicts)
            else:
                remaining.append(record_b)
        pending_b = remaining
        merged_records.append(merged_record)
    merged_records.extend(pending_b)
    return {"records": merged_records, "mergeConflicts": conflicts}


def resolve_due(items: list[dict[str, Any]], base: date) -> dict[str, Any]:
    due: list[dict[str, Any]] = []
    not_due: list[dict[str, Any]] = []
    needs_base: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise RecordError(f"items[{index}] must be an object")
        offset_value = item.get("retestOffsetDays")
        if offset_value is not None and (
            isinstance(offset_value, bool)
            or not isinstance(offset_value, int)
            or offset_value < 0
        ):
            raise RecordError(f"items[{index}].retestOffsetDays must be a non-negative integer or null")
        label = item.get("itemId") or f"items[{index}]"
        summary = {
            "item": label,
            "subject": item.get("subject"),
            "topic": item.get("topic"),
            "status": item.get("status"),
        }
        next_date = item.get("nextRetestDate")
        offset, anchor = item.get("retestOffsetDays"), item.get("retestAnchorDate")
        if is_plain_date(next_date):
            (due if date.fromisoformat(next_date) <= base else not_due).append(summary)
        elif isinstance(offset, int) and is_plain_date(anchor):
            resolved = date.fromisoformat(anchor) + timedelta(days=offset)
            entry = {**summary, "resolvedDate": resolved.isoformat()}
            (due if resolved <= base else not_due).append(entry)
        elif isinstance(offset, int):
            needs_base.append({**summary, "retestOffsetDays": offset})
        else:
            needs_base.append({**summary, "reason": "no nextRetestDate or retestOffsetDays"})
    return {"date": base.isoformat(), "due": due, "notDue": not_due, "needsBaseDate": needs_base}


def run_normalize(document: Any) -> dict[str, Any]:
    results = []
    for record in as_record_list(document):
        converted, warnings = normalize_to_12(record)
        results.append({"record": converted, "migrationWarnings": warnings})
    if len(results) == 1:
        return {"record": results[0]["record"], "migrationWarnings": results[0]["migrationWarnings"]}
    return {
        "records": [entry["record"] for entry in results],
        "migrationWarnings": [warning for entry in results for warning in entry["migrationWarnings"]],
    }


def build_checkpoint(payload: dict[str, Any], base_date: str | None) -> dict[str, Any]:
    checkpoint = {
        "schemaVersion": SCHEMA_VERSION_CURRENT,
        "recordType": "SessionCheckpoint",
        "updatedAt": base_date,
        "currentTask": payload.get("currentTask"),
        "position": payload.get("position"),
        "dueItems": payload.get("dueItems") or [],
        "pendingRetests": payload.get("pendingRetests") or [],
        "notes": payload.get("notes"),
        "teachingMode": payload.get("teachingMode"),
        "answerState": payload.get("answerState"),
        "hintLevel": payload.get("hintLevel"),
        "currentQuestion": payload.get("currentQuestion"),
        "completedQuestions": payload.get("completedQuestions") or [],
        "remainingQuestions": payload.get("remainingQuestions") or [],
        "materialVersion": payload.get("materialVersion"),
    }
    if payload.get("checkpointId"):
        checkpoint["checkpointId"] = payload["checkpointId"]
    else:
        checkpoint["checkpointId"] = stable_id("kc", {**checkpoint, "updatedAt": None})
    return checkpoint


def read_checkpoint(checkpoint: dict[str, Any], base: date | None, queue: dict[str, Any] | None) -> dict[str, Any]:
    if checkpoint.get("recordType") != "SessionCheckpoint":
        raise RecordError("checkpoint read requires recordType SessionCheckpoint")
    errors, warnings = validate_current(checkpoint)
    if errors:
        raise RecordError("checkpoint is invalid: " + "; ".join(errors))
    plan: dict[str, Any] = {
        "resume": {
            "currentTask": checkpoint.get("currentTask"),
            "position": checkpoint.get("position"),
            "teachingMode": checkpoint.get("teachingMode"),
            "answerState": checkpoint.get("answerState"),
            "hintLevel": checkpoint.get("hintLevel"),
            "currentQuestion": checkpoint.get("currentQuestion"),
            "completedQuestions": checkpoint.get("completedQuestions", []),
            "remainingQuestions": checkpoint.get("remainingQuestions", []),
            "materialVersion": checkpoint.get("materialVersion"),
        },
        "dueItems": checkpoint.get("dueItems", []),
        "pendingRetests": checkpoint.get("pendingRetests", []),
    }
    if base is not None and isinstance(queue, dict):
        items: list[dict[str, Any]] = []
        for record in as_record_list(queue):
            if record.get("recordType") == "ReviewQueue":
                queue_items = record.get("items", [])
                if not isinstance(queue_items, list):
                    raise RecordError("items must be an array")
                items.extend(queue_items)
        plan["dueReview"] = resolve_due(items, base)
    if warnings:
        plan["warnings"] = warnings
    return plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validate a record document")
    validate_parser.add_argument("input", nargs="?", default="-")
    validate_parser.add_argument("--strict", action="store_true", help="treat warnings as fatal")

    normalize_parser = subparsers.add_parser("normalize", help="normalize 1.0/1.1 records to 1.2")
    normalize_parser.add_argument("input", nargs="?", default="-")

    merge_parser = subparsers.add_parser("merge", help="merge two record documents")
    merge_parser.add_argument("first")
    merge_parser.add_argument("second")

    due_parser = subparsers.add_parser("due", help="list due review items for a base date")
    due_parser.add_argument("input", nargs="?", default="-")
    due_parser.add_argument("--date", required=True, dest="base_date", help="explicit base date YYYY-MM-DD")

    checkpoint_parser = subparsers.add_parser("checkpoint", help="create or read a SessionCheckpoint")
    checkpoint_sub = checkpoint_parser.add_subparsers(dest="checkpoint_command", required=True)
    create_parser = checkpoint_sub.add_parser("create")
    create_parser.add_argument("input", nargs="?", default="-")
    create_parser.add_argument("--date", default=None, dest="base_date")
    read_parser = checkpoint_sub.add_parser("read")
    read_parser.add_argument("input", nargs="?", default="-")
    read_parser.add_argument("--date", default=None, dest="base_date")
    read_parser.add_argument("--queue", default=None, help="optional ReviewQueue document for due computation")
    return parser


def _configure_windows_stdio() -> None:
    """Use UTF-8 for PowerShell 7 native-command pipelines on Windows."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict")


def main(argv: list[str] | None = None) -> int:
    _configure_windows_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        base = date.fromisoformat(args.base_date) if getattr(args, "base_date", None) else None
        if args.command == "validate":
            report = [validate_record(record, strict=args.strict) for record in as_record_list(load_document(args.input))]
            invalid = [entry for entry in report if not entry["valid"]]
            emit({"valid": not invalid, "results": report} if len(report) > 1 else report[0])
            return 1 if invalid else 0
        if args.command == "normalize":
            emit(run_normalize(load_document(args.input)))
            return 0
        if args.command == "merge":
            first_is_stdin, second_is_stdin = args.first == "-", args.second == "-"
            if first_is_stdin and second_is_stdin:
                raise RecordError("merge accepts at most one '-' stdin input")
            first = load_document(args.first)
            second = load_document(args.second)
            emit(merge_documents(first, second))
            return 0
        if args.command == "due":
            queue_items: list[dict[str, Any]] = []
            for record in as_record_list(load_document(args.input)):
                if record.get("recordType") == "ReviewQueue":
                    items = record.get("items", [])
                    if not isinstance(items, list):
                        raise RecordError("items must be an array")
                    queue_items.extend(items)
            emit(resolve_due(queue_items, base))  # type: ignore[arg-type]
            return 0
        if args.command == "checkpoint":
            document = load_document(args.input)
            record = document if isinstance(document, dict) else None
            if record is None:
                raise RecordError("checkpoint input must be a JSON object")
            if args.checkpoint_command == "create":
                emit(build_checkpoint(record, args.base_date))
                return 0
            queue = load_document(args.queue) if args.queue else None
            emit(read_checkpoint(record, base, queue))
            return 0
        parser.error(f"unknown command: {args.command}")  # pragma: no cover - argparse guards
    except RecordError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except (AttributeError, KeyError, OverflowError, TypeError, ValueError) as exc:
        # Malformed user-supplied JSON must produce the promised CLI error, never a traceback.
        print(
            json.dumps({"error": f"invalid record structure ({exc.__class__.__name__})"}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

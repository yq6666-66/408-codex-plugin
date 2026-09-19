#!/usr/bin/env python3
"""Validate complete acceptance records; this cannot authenticate model outputs."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import re
import sys
from pathlib import Path
from typing import Any

PLACEHOLDER_HINTS = re.compile(
    r"^\s*(TODO|待填写|模拟回答|占位|placeholder|lorem ipsum)[^\n]*$", re.IGNORECASE
)
REQUIRED_META = {"pluginName", "pluginVariant", "pluginVersion", "model", "reasoningEffort", "host", "runAt"}
VERDICT_RANK = {"fail": 0, "partial": 1, "pass": 2}


class RecordError(RuntimeError):
    """Raised for structurally invalid or incomplete acceptance records."""


def load_cases(repo: Path) -> dict[str, dict[str, Any]]:
    document = load_record(repo / "eval" / "gpt6-acceptance" / "cases.json")
    return {case["id"]: case for case in document["cases"]}


def load_record(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecordError(f"cannot read record: {exc}") from exc


def _text(value: Any, label: str, minimum: int = 1) -> str:
    if not isinstance(value, str) or len(value.strip()) < minimum:
        raise RecordError(f"{label} must be a non-empty string (minimum {minimum} characters)")
    if any(PLACEHOLDER_HINTS.match(line) for line in value.strip().splitlines()[:5]):
        raise RecordError(f"{label} contains template placeholders")
    return value


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RecordError(f"{label} must be an object")
    return value


def validate_record(record: dict[str, Any], cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    record = _object(record, "record")
    meta = _object(record.get("meta"), "record.meta")
    missing_meta = REQUIRED_META - set(meta)
    if missing_meta:
        raise RecordError(f"record.meta is missing: {sorted(missing_meta)}")
    for key in REQUIRED_META:
        _text(meta[key], f"record.meta.{key}")
        if "填写" in meta[key]:
            raise RecordError(f"record.meta.{key} contains template placeholders")
    if meta["pluginVariant"] not in {"old", "new"}:
        raise RecordError("record.meta.pluginVariant must be old or new")
    try:
        timestamp = datetime.fromisoformat(meta["runAt"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("timezone required")
    except ValueError as exc:
        raise RecordError("record.meta.runAt must be an ISO 8601 timestamp with timezone") from exc
    entries = record.get("cases")
    if not isinstance(entries, list) or not entries:
        raise RecordError("record.cases must be a non-empty array")
    summary: dict[str, Any] = {"total": len(entries), "pass": 0, "fail": 0, "missing": [], "perCase": {}}
    seen: set[str] = set()
    for index, raw_entry in enumerate(entries):
        entry = _object(raw_entry, f"record.cases[{index}]")
        case_id = _text(entry.get("id"), f"record.cases[{index}].id")
        if case_id not in cases:
            raise RecordError(f"unknown case id: {case_id!r}")
        if case_id in seen:
            raise RecordError(f"duplicate case id: {case_id}")
        seen.add(case_id)
        _text(entry.get("modelOutput"), f"{case_id}: modelOutput")
        _text(entry.get("inputMaterial"), f"{case_id}: inputMaterial")
        calls = entry.get("toolCalls")
        if not isinstance(calls, list):
            raise RecordError(f"{case_id}: toolCalls must be an array; use [] when no tools ran")
        for call_index, raw_call in enumerate(calls):
            label = f"{case_id}: toolCalls[{call_index}]"
            call = _object(raw_call, label)
            for key in ("tool", "input", "output"):
                _text(call.get(key), f"{label}.{key}")
        verdicts = entry.get("verdicts")
        if not isinstance(verdicts, list) or not verdicts:
            raise RecordError(f"{case_id}: verdicts must be a non-empty array")
        expected = set(cases[case_id]["checkpoints"])
        judged: dict[str, str] = {}
        for verdict_index, raw_verdict in enumerate(verdicts):
            label = f"{case_id}: verdicts[{verdict_index}]"
            verdict = _object(raw_verdict, label)
            checkpoint = _text(verdict.get("checkpoint"), f"{label}.checkpoint")
            if checkpoint not in expected:
                raise RecordError(f"{case_id}: unknown checkpoint: {checkpoint!r}")
            if checkpoint in judged:
                raise RecordError(f"{case_id}: duplicate checkpoint: {checkpoint!r}")
            result = verdict.get("verdict")
            if not isinstance(result, str) or result not in VERDICT_RANK:
                raise RecordError(f"{case_id}: invalid verdict {result!r}")
            _text(verdict.get("evidence"), f"{label}.evidence")
            judged[checkpoint] = result
        unmatched = expected - judged.keys()
        if unmatched:
            raise RecordError(f"{case_id}: checkpoints not judged: {sorted(unmatched)}")
        overall = "pass" if all(result == "pass" for result in judged.values()) else "fail"
        if "overall" in entry and entry["overall"] != overall:
            raise RecordError(f"{case_id}: overall must equal computed verdict {overall!r}")
        summary[overall] += 1
        summary["perCase"][case_id] = {"overall": overall, "checkpoints": judged}
    missing = sorted(set(cases) - seen)
    if missing:
        raise RecordError(f"record is missing cases: {missing}")
    return summary


def compare(old_summary: dict[str, Any], new_summary: dict[str, Any]) -> dict[str, Any]:
    regressions = []
    for case_id, old_case in old_summary["perCase"].items():
        new_case = new_summary["perCase"][case_id]
        for checkpoint, old_result in old_case["checkpoints"].items():
            new_result = new_case["checkpoints"][checkpoint]
            if VERDICT_RANK[new_result] < VERDICT_RANK[old_result]:
                regressions.append({"id": case_id, "checkpoint": checkpoint, "old": old_result, "new": new_result})
    return {
        "old": {"pass": old_summary["pass"], "fail": old_summary["fail"]},
        "new": {"pass": new_summary["pass"], "fail": new_summary["fail"]},
        "regressions": regressions,
        "regressionGate": "fail" if regressions else "pass",
    }


def main(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--record", type=Path, help="validate one complete acceptance record")
    action.add_argument("--compare", nargs=2, type=Path, metavar=("OLD", "NEW"), help="compare two complete records")
    args = parser.parse_args(argv)
    try:
        cases = load_cases(repo)
        if args.compare:
            old_record, new_record = (load_record(path) for path in args.compare)
            old_summary = validate_record(old_record, cases)
            new_summary = validate_record(new_record, cases)
            for field in ("pluginName", "host", "model", "reasoningEffort"):
                if old_record["meta"][field] != new_record["meta"][field]:
                    raise RecordError(f"comparison conditions differ: {field}")
            if old_record["meta"]["pluginVariant"] != "old" or new_record["meta"]["pluginVariant"] != "new":
                raise RecordError("--compare requires old and new pluginVariant in that order")
            old_entries = {entry["id"]: entry for entry in old_record["cases"]}
            new_entries = {entry["id"]: entry for entry in new_record["cases"]}
            for case_id, old_entry in old_entries.items():
                new_entry = new_entries[case_id]
                if old_entry["inputMaterial"] != new_entry["inputMaterial"]:
                    raise RecordError(f"comparison inputs differ: {case_id}.inputMaterial")
                if "inputArtifacts" in old_entry or "inputArtifacts" in new_entry:
                    if ("inputArtifacts" not in old_entry or "inputArtifacts" not in new_entry
                            or old_entry["inputArtifacts"] != new_entry["inputArtifacts"]):
                        raise RecordError(f"comparison inputs differ: {case_id}.inputArtifacts")
            report = compare(old_summary, new_summary)
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 1 if report["regressions"] else 0
        summary = validate_record(load_record(args.record), cases)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["fail"] == 0 else 1
    except RecordError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

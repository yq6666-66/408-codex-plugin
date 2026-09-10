#!/usr/bin/env python3
"""Validate GPT-6 acceptance records and compare old/new plugin variants.

This harness never generates or fabricates model answers: it only checks that
a filled record is complete and internally consistent, then summarizes the
verdicts. Standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PLACEHOLDER_HINTS = re.compile(
    r"^\s*(TODO|待填写|模拟回答|占位|placeholder|lorem ipsum)[^\n]*$", re.IGNORECASE
)
REQUIRED_META = {"pluginName", "pluginVariant", "pluginVersion", "model", "reasoningEffort", "host", "runAt"}


class RecordError(RuntimeError):
    """Raised when an acceptance record is incomplete or looks fabricated."""


def load_cases(repo: Path) -> dict[str, dict[str, Any]]:
    cases_path = repo / "eval" / "gpt6-acceptance" / "cases.json"
    document = json.loads(cases_path.read_text(encoding="utf-8"))
    return {case["id"]: case for case in document["cases"]}


def load_record(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RecordError(f"cannot read record: {exc}") from exc


def _looks_fabricated(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 20:
        return True
    return any(PLACEHOLDER_HINTS.match(line) for line in stripped.splitlines()[:5])


def validate_record(record: dict[str, Any], cases: dict[str, dict[str, Any]]) -> dict[str, Any]:
    meta = record.get("meta")
    if not isinstance(meta, dict):
        raise RecordError("record.meta must be an object")
    missing_meta = REQUIRED_META - set(meta)
    if missing_meta:
        raise RecordError(f"record.meta is missing: {sorted(missing_meta)}")
    placeholder_values = [key for key in ("model", "reasoningEffort", "host") if "填写" in str(meta.get(key, ""))]
    if placeholder_values:
        raise RecordError(f"record.meta still contains template placeholders: {placeholder_values}")

    entries = record.get("cases")
    if not isinstance(entries, list) or not entries:
        raise RecordError("record.cases must be a non-empty array")
    problems: list[str] = []
    summary: dict[str, Any] = {"total": len(entries), "pass": 0, "fail": 0, "missing": []}
    case_ids = [entry.get("id") for entry in entries]
    for entry in entries:
        case_id = entry.get("id")
        if case_id not in cases:
            problems.append(f"unknown case id: {case_id!r}")
            summary["fail"] += 1
            continue
        expected = {checkpoint for checkpoint in cases[case_id]["checkpoints"]}
        output = entry.get("modelOutput")
        if not isinstance(output, str) or _looks_fabricated(output):
            problems.append(f"{case_id}: modelOutput is empty or looks like a placeholder")
            summary["fail"] += 1
            continue
        input_material = entry.get("inputMaterial")
        if not isinstance(input_material, str) or _looks_fabricated(input_material):
            problems.append(f"{case_id}: inputMaterial must record the actual input")
            summary["fail"] += 1
            continue
        verdicts = entry.get("verdicts")
        if not isinstance(verdicts, list) or not verdicts:
            problems.append(f"{case_id}: verdicts are missing")
            summary["fail"] += 1
            continue
        judged = {verdict.get("checkpoint") for verdict in verdicts}
        unmatched = expected - judged
        if unmatched:
            problems.append(f"{case_id}: checkpoints not judged: {sorted(unmatched)}")
        for verdict in verdicts:
            if verdict.get("verdict") not in {"pass", "fail", "partial"}:
                problems.append(f"{case_id}: invalid verdict {verdict.get('verdict')!r}")
            if not str(verdict.get("evidence", "")).strip():
                problems.append(f"{case_id}: verdict evidence is empty for: {verdict.get('checkpoint')!r}")
        if any(verdict.get("verdict") != "pass" for verdict in verdicts) or unmatched:
            summary["fail"] += 1
            entry["overall"] = "fail"
        else:
            summary["pass"] += 1
            entry["overall"] = "pass"
    summary["missing"] = sorted(set(cases) - set(case_ids))
    for problem in problems:
        print(f"[PROBLEM] {problem}", file=sys.stderr)
    return summary


def compare(old_summary: dict[str, Any], new_summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "old": {"pass": old_summary["pass"], "fail": old_summary["fail"]},
        "new": {"pass": new_summary["pass"], "fail": new_summary["fail"]},
        "regressionGate": "new.fail must not exceed old.fail; per-case regressions must be reviewed manually",
    }


def main(argv: list[str] | None = None) -> int:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, help="validate one acceptance record")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("OLD", "NEW"), help="compare two records")
    args = parser.parse_args(argv)
    cases = load_cases(repo)
    try:
        if args.compare:
            old_record = load_record(args.compare[0])
            new_record = load_record(args.compare[1])
            old_summary = validate_record(old_record, cases)
            new_summary = validate_record(new_record, cases)
            print(json.dumps(compare(old_summary, new_summary), ensure_ascii=False, indent=2))
            return 0 if new_summary["fail"] <= old_summary["fail"] else 1
        if args.record is None:
            parser.print_help(sys.stderr)
            return 2
        record = load_record(args.record)
        summary = validate_record(record, cases)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["fail"] == 0 else 1
    except RecordError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

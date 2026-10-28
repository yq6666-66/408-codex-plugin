#!/usr/bin/env python3
"""Read ZCode parts.jsonl and count observed calls without grading behavior.

This reads only the supplied trace and this repository's Skill directory names.
It does not execute recorded commands, load Skill bodies, or modify any files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path


class TraceError(ValueError):
    """The input cannot be interpreted as a ZCode parts trace."""


def audit_trace(path: Path, mode: str) -> dict:
    if mode not in {"ordinary", "explicit", "tool-directed"}:
        raise TraceError("unsupported request mode")
    skills_root = Path(__file__).resolve().parents[1] / "plugins/kaoyan-408/skills"
    skills = {entry.name for entry in skills_root.iterdir() if (entry / "SKILL.md").is_file()}
    if not skills:
        raise TraceError("repository Skill inventory is unavailable")
    raw = path.read_bytes()
    try:
        lines = raw.decode("utf-8-sig").splitlines()
    except UnicodeDecodeError as exc:
        raise TraceError("trace must be UTF-8") from exc
    records = 0
    calls: dict[str, dict] = {}
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise TraceError(f"invalid JSON at line {line_number}") from exc
        if not isinstance(record, dict) or not isinstance(record.get("part"), dict):
            raise TraceError(f"expected role/part record at line {line_number}")
        if record.get("role") not in ("assistant", "user", "system", "tool"):
            raise TraceError(f"invalid record role at line {line_number}")
        records += 1
        part = record["part"]
        if record["role"] != "assistant" or part.get("type") != "tool":
            continue
        call_id, tool, state = part.get("callID"), part.get("tool"), part.get("state")
        if not isinstance(call_id, str) or not call_id or not isinstance(tool, str) or not tool:
            raise TraceError(f"tool record needs callID and tool at line {line_number}")
        if not isinstance(state, dict):
            raise TraceError(f"tool record needs state at line {line_number}")
        previous = calls.get(call_id)
        if previous is not None:
            if previous["tool"] != tool:
                raise TraceError(f"callID reused for different tools at line {line_number}")
            prior_input = previous["state"].get("input")
            current_input = state.get("input")
            merged_input = dict(prior_input) if isinstance(prior_input, dict) else {}
            if isinstance(current_input, dict):
                merged_input.update(current_input)
            if tool == "Skill" and isinstance(prior_input, dict):
                prior_skill = prior_input.get("skill")
                current_skill = current_input.get("skill") if isinstance(current_input, dict) else None
                if isinstance(prior_skill, str) and prior_skill:
                    if isinstance(current_skill, str) and current_skill and current_skill != prior_skill:
                        raise TraceError(f"callID reused for different skills at line {line_number}")
                    merged_input["skill"] = prior_skill
            merged_state = {**previous["state"], **state}
            if isinstance(prior_input, dict) or isinstance(current_input, dict):
                merged_state["input"] = merged_input
            part = {**part, "state": merged_state}
        calls[call_id] = part  # Preserve identity while applying later partial state snapshots.
    if not records:
        raise TraceError("trace contains no records")

    tool_counts: Counter = Counter()
    skill_counts: Counter = Counter()
    skill_statuses: Counter = Counter()
    unresolved = 0
    for part in calls.values():
        tool_counts[part["tool"]] += 1
        if part["tool"] != "Skill":
            continue
        state = part["state"]
        arguments = state.get("input")
        requested = arguments.get("skill") if isinstance(arguments, dict) else None
        if not isinstance(requested, str) or not requested:
            unresolved += 1
            continue
        namespace, separator, name = requested.rpartition(":")
        if not separator:
            name = requested
        elif namespace != "kaoyan-408":
            continue
        if name not in skills:
            continue
        skill_counts[name] += 1
        status = state.get("status")
        if status not in ("pending", "running", "completed", "error"):
            status = "unknown"
        skill_statuses[status] += 1

    return {
        "schemaVersion": "1.0",
        "traceFormat": "zcode-parts-jsonl",
        "traceSha256": hashlib.sha256(raw).hexdigest(),
        "mode": mode,
        "records": records,
        "toolCalls": dict(sorted(tool_counts.items())),
        "pluginSkillInvocations": sum(skill_counts.values()),
        "pluginSkills": dict(sorted(skill_counts.items())),
        "pluginSkillStatuses": dict(sorted(skill_statuses.items())),
        "unresolvedSkillInvocations": unresolved,
        "traceCompleteness": "not_verified",
        "behaviorGrade": "not_assessed",
        "scope": "Recorded calls only; completed is a tool status, not proof of behavior correctness.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True, help="existing ZCode parts.jsonl")
    parser.add_argument("--mode", choices=("ordinary", "explicit", "tool-directed"), required=True)
    args = parser.parse_args(argv)
    try:
        report = audit_trace(args.trace, args.mode)
    except (OSError, TraceError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

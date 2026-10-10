#!/usr/bin/env python3
"""Extract auditable response and tool evidence from Codex CLI JSONL."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


TOOL_ITEM_TYPES = {
    "command_execution",
    "file_change",
    "image_generation",
    "mcp_tool_call",
    "web_search",
}


class CaptureError(RuntimeError):
    """Raised when a raw event stream cannot be parsed safely."""


def ensure_output_does_not_alias_input(input_path: Path, output_path: Path) -> None:
    try:
        aliases = input_path.resolve() == output_path.resolve()
        if not aliases and input_path.exists() and output_path.exists():
            aliases = input_path.samefile(output_path)
    except OSError as exc:
        raise CaptureError(f"cannot compare input and output paths: {exc.__class__.__name__}") from exc
    if aliases:
        raise CaptureError("output path must not overwrite or alias the source JSONL")


def _json_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "actual no output"
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def load_events(path: Path) -> tuple[list[dict[str, Any]], str]:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise CaptureError(f"cannot read JSONL: {exc.__class__.__name__} ({exc.errno})") from exc
    events: list[dict[str, Any]] = []
    for line_number, raw_line in enumerate(payload.splitlines(), start=1):
        if not raw_line.strip():
            continue
        try:
            event = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CaptureError(f"invalid UTF-8 JSON event at line {line_number}") from exc
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise CaptureError(f"event at line {line_number} must be an object with string type")
        events.append(event)
    if not events:
        raise CaptureError("JSONL contains no events")
    return events, hashlib.sha256(payload).hexdigest()


def _tool_call(item: dict[str, Any], turn: int) -> dict[str, Any]:
    item_type = str(item.get("type"))
    tool = item.get("tool") or item.get("name") or item.get("server") or item_type
    if item_type == "web_search":
        raw_input = {"action": item.get("action"), "query": item.get("query")}
        raw_output = item.get("results")
        # Codex CLI emits web_search only as item.completed, without a status or exit code.
        status = item.get("status") or "completed"
    else:
        raw_input = (
            item.get("command")
            if item_type == "command_execution"
            else item.get("arguments", item.get("input", item.get("query", item.get("changes"))))
        )
        raw_output = item.get("aggregated_output", item.get("output", item.get("result")))
        status = item.get("status")
    exit_code = item.get("exit_code", item.get("exitCode"))
    has_output = raw_output is not None and raw_output != ""
    success = (
        status in {"completed", "success"}
        and exit_code in {None, 0}
        and has_output
        and not item.get("error")
    )
    return {
        "itemId": str(item.get("id") or ""),
        "turn": turn,
        "tool": str(tool),
        "input": _json_text(raw_input),
        "output": _json_text(raw_output) if has_output else "actual no output",
        "status": str(status or "unknown"),
        "exitCode": exit_code,
        "success": success,
    }


def capture(
    events: list[dict[str, Any]],
    source_sha256: str,
    case_id: str | None = None,
    input_material: str | None = None,
    artifacts: dict[str, str] | None = None,
) -> dict[str, Any]:
    thread_id: str | None = None
    turn = 0
    started_turns = 0
    completed_turns = 0
    messages: list[dict[str, Any]] = []
    tools: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    usage: list[dict[str, Any]] = []

    for event in events:
        event_type = event["type"]
        if event_type == "thread.started" and isinstance(event.get("thread_id"), str):
            thread_id = event["thread_id"]
        elif event_type == "turn.started":
            turn += 1
            started_turns += 1
        elif event_type == "turn.completed":
            completed_turns += 1
            if isinstance(event.get("usage"), dict):
                usage.append(event["usage"])
        elif event_type in {"turn.failed", "error"}:
            errors.append({"turn": turn, "type": event_type, "message": _json_text(event.get("error", event.get("message")))})
        elif event_type == "item.completed":
            item = event.get("item")
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == "agent_message" and isinstance(item.get("text"), str):
                messages.append({"itemId": str(item.get("id") or ""), "turn": turn, "text": item["text"]})
            elif item_type == "error":
                errors.append({"turn": turn, "type": "item.error", "message": _json_text(item.get("message"))})
            elif item_type in TOOL_ITEM_TYPES:
                tools.append(_tool_call(item, turn))

    model_output = "\n\n".join(
        f"第{entry['turn']}轮模型输出：\n{entry['text']}" for entry in messages
    )
    report = {
        "schemaVersion": "1.0",
        "caseId": case_id,
        "sourceSha256": source_sha256,
        "threadId": thread_id,
        "eventCount": len(events),
        "startedTurns": started_turns,
        "completedTurns": completed_turns,
        "complete": started_turns > 0 and completed_turns == started_turns,
        "agentMessages": messages,
        "modelOutput": model_output,
        "toolCalls": tools,
        "errors": errors,
        "usage": usage,
    }
    if input_material is not None:
        report["inputMaterial"] = input_material
    if artifacts:
        report["inputArtifacts"] = artifacts
    if case_id and input_material is not None and report["complete"] and model_output:
        report["recordCase"] = {
            "id": case_id,
            "inputMaterial": input_material,
            "modelOutput": model_output,
            "toolCalls": [
                {
                    "tool": call["tool"],
                    "input": call["input"],
                    "output": call["output"],
                    "status": call["status"],
                    "exitCode": call["exitCode"],
                    "success": call["success"],
                }
                for call in tools
            ],
            "sourceEvidence": {
                "jsonlSha256": source_sha256,
                "threadId": thread_id,
                "startedTurns": started_turns,
                "completedTurns": completed_turns,
            },
            **({"inputArtifacts": artifacts} if artifacts else {}),
        }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="raw Codex CLI JSONL")
    parser.add_argument("--output", type=Path, default=None, help="optional extracted JSON path")
    parser.add_argument("--case-id", default=None, help="optional acceptance case ID")
    parser.add_argument(
        "--input-material-file",
        type=Path,
        default=None,
        help="UTF-8 text containing the exact user turns and follow-ups, in order",
    )
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="bind an input image/material by name and SHA-256; may be repeated",
    )
    args = parser.parse_args(argv)
    try:
        if args.output is not None:
            ensure_output_does_not_alias_input(args.input, args.output)
        events, digest = load_events(args.input)
        input_material = None
        if args.input_material_file is not None:
            try:
                input_material = args.input_material_file.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise CaptureError(
                    f"cannot read input material file: {exc.__class__.__name__}"
                ) from exc
            if not input_material.strip():
                raise CaptureError("input material file is empty")
        artifacts: dict[str, str] = {}
        for binding in args.artifact:
            name, separator, raw_path = binding.partition("=")
            if not separator or not name or not raw_path:
                raise CaptureError("--artifact must use NAME=PATH")
            if name in artifacts:
                raise CaptureError(f"duplicate artifact name: {name}")
            try:
                artifacts[name] = hashlib.sha256(Path(raw_path).read_bytes()).hexdigest()
            except OSError as exc:
                raise CaptureError(f"cannot read artifact {name!r}: {exc.__class__.__name__} ({exc.errno})") from exc
        report = capture(events, digest, args.case_id, input_material, artifacts)
        text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if args.output is None:
            sys.stdout.write(text)
        else:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(text, encoding="utf-8", newline="\n")
        return 0 if report["complete"] else 1
    except CaptureError as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run isolated real Codex captures; no automatic behavioral pass verdicts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def file_snapshot(directory: Path) -> dict[str, str]:
    return {
        p.relative_to(directory).as_posix(): digest(p)
        for p in sorted(directory.rglob("*"))
        if p.is_file() and ".git" not in p.relative_to(directory).parts
    }


def read_installed_payload(installed_root: Path, expected_payload: dict[str, bytes]) -> dict[str, bytes]:
    entries = list(installed_root.rglob("*"))
    if any(path.is_symlink() for path in entries):
        raise ValueError("installed plugin tree contains a symlink")
    payload = {
        path.relative_to(installed_root).as_posix(): path.read_bytes()
        for path in entries
        if path.is_file()
    }
    if payload != expected_payload:
        raise ValueError("installed plugin does not match the exact repository payload")
    return payload


def begin_turn_record(summary: dict, number: int, input_path: Path, raw_path: Path, stderr_path: Path) -> dict:
    """Record the turn before parsing JSONL, which can fail after a CLI crash."""
    record = {
        "number": number,
        "inputSha256": digest(input_path),
        "rawSha256": None,
        "threadId": None,
        "exitCode": None,
        "stderrPath": stderr_path.name,
        "complete": False,
        "skillReadProofItems": [],
        "toolCount": 0,
        "errors": [],
    }
    summary["turns"].append(record)
    return record


def skill_read_proof(capture: dict, skill_file: Path, skill: str) -> list[str]:
    expected = str(skill_file).replace("\\", "/").casefold()
    complete_text = skill_file.read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    proofs = []
    for call in capture.get("toolCalls", []) + capture.get("rolloutToolCalls", []):
        command = call.get("input", "").replace("\\\\", "\\").replace("\\", "/").casefold()
        output = call.get("output", "").replace("\r\n", "\n")
        if call.get("success") is True and expected in command and f"name: {skill}" in output and complete_text in output:
            proofs.append(call.get("itemId", ""))
    return proofs


def _has_structured_error(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("isError") is True or value.get("is_error") is True:
            return True
        if value.get("success") is False or value.get("ok") is False:
            return True
        status = value.get("status")
        if isinstance(status, str) and status.casefold() in {
            "error", "failed", "denied", "rejected", "timeout", "timed_out",
        }:
            return True
        if any(value.get(key) not in (None, False, "", [], {}) for key in ("error", "errors")):
            return True
        return any(
            _has_structured_error(value[key])
            for key in ("result", "response", "content", "contents", "payload")
            if key in value
        )
    if isinstance(value, list):
        return any(_has_structured_error(child) for child in value)
    return False


def _rollout_output_failed(text: str, output_event: dict) -> bool:
    if output_event.get("isError") is True or output_event.get("is_error") is True:
        return True
    lowered = text.casefold().lstrip()
    if any(phrase in lowered for phrase in ("script failed", "script error:")):
        return True
    if lowered.startswith(("error:", "failed:", "access denied", "permission denied")):
        return True
    try:
        structured = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return False
    return _has_structured_error(structured)


def extract_rollout_tools(path: Path, *, start_line: int = 1) -> list[dict]:
    """Expose only wrapper calls started at or after the requested turn boundary."""
    if not path.is_file():
        return []
    pending = {}
    calls = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if index < start_line:
            continue
        event = json.loads(line)
        if event.get("type") != "response_item":
            continue
        item = event.get("payload", {})
        kind = item.get("type")
        if kind in {"custom_tool_call", "function_call"}:
            pending[item.get("call_id")] = (index, item)
        elif kind in {"custom_tool_call_output", "function_call_output"}:
            earlier = pending.get(item.get("call_id"))
            if not earlier:
                continue
            call_line, call = earlier
            output = item.get("output")
            if isinstance(output, list):
                text = "\n".join(v.get("text", "") for v in output if isinstance(v, dict))
            else:
                text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
            error = _rollout_output_failed(text, item)
            calls.append({"itemId": call.get("call_id", ""), "tool": call.get("name", "unknown"),
                          "input": call.get("input", call.get("arguments", "")), "output": text,
                          "status": "failed" if error else "returned",
                          "success": bool(text) and not error and (str(call.get("name", "")).rsplit(".", 1)[-1] != "exec" or "Script completed" in text),
                          "callLine": call_line, "outputLine": index,
                          "evidenceKind": "private-rollout-wrapper-output"})
    return calls


def preserve_rollout(home: Path, thread_id: str | None, target: Path) -> dict[str, str]:
    """Keep a private snapshot when CLI summary omits actual web tool output."""
    if not thread_id:
        return {}
    matches = list((home / "sessions").rglob(f"*{thread_id}.jsonl"))
    if len(matches) != 1:
        return {"status": "unavailable-or-ambiguous"}
    shutil.copyfile(matches[0], target)
    return {
        "status": "copied-private",
        "sha256": digest(target),
        "lineCount": len(target.read_text(encoding="utf-8").splitlines()),
    }


def turn_has_model_output(report: dict) -> bool:
    output = report.get("modelOutput")
    return isinstance(output, str) and bool(output.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--installed-plugin", type=Path, required=True)
    parser.add_argument("--codex-home", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", required=True)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=1200)
    parser.add_argument("--sandbox", choices=["workspace-write", "danger-full-access"], default="workspace-write")
    parser.add_argument("--stop-file", type=Path, help="if this file exists at a case boundary, stop before starting another model call")
    args = parser.parse_args()
    args.repository = args.repository.resolve()
    args.installed_plugin = args.installed_plugin.resolve()
    args.codex_home = args.codex_home.resolve()
    args.output = args.output.resolve()
    if args.codex_home == (Path.home() / ".codex").resolve():
        raise ValueError("refusing stable CODEX_HOME")
    if args.repository in args.output.parents or args.output == args.repository:
        raise ValueError("raw output must remain outside the repository")
    catalog_path = Path(__file__).with_name("cases.json")
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in catalog["cases"]}
    selected = args.case or list(cases)
    if len(set(selected)) != len(selected) or set(selected) - set(cases):
        raise ValueError("duplicate or unknown case IDs")
    plugin_manifest = json.loads((args.installed_plugin / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    if plugin_manifest.get("version") != "2.6.0":
        raise ValueError("installed candidate must be 2.6.0")
    sys.path.insert(0, str(args.repository / "scripts"))
    from release_payload import ALLOWED_RELEASE_FILES, plugin_tree_digest
    from gpt6_capture import capture, load_events

    expected_payload = {
        relative: (args.repository / "plugins" / "kaoyan-408" / relative).read_bytes()
        for relative in ALLOWED_RELEASE_FILES
    }
    payload = read_installed_payload(args.installed_plugin, expected_payload)
    tree_hash = plugin_tree_digest(payload)
    cli_version = subprocess.check_output([str(args.exe), "--version"], text=True, encoding="utf-8").strip()
    environment = os.environ.copy()
    environment["CODEX_HOME"] = str(args.codex_home)
    args.output.mkdir(parents=True, exist_ok=True)
    for case_id in selected:
        if args.stop_file is not None and args.stop_file.exists():
            print("Stopped at a case boundary; existing captured cases are preserved.", flush=True)
            return 0
        case = cases[case_id]
        case_dir = args.output / case_id
        case_dir.mkdir(exist_ok=False)
        workspace = case_dir / "workspace"
        workspace.mkdir()
        skill_file = args.installed_plugin / "skills" / case["skill"] / "SKILL.md"
        if not skill_file.is_file():
            raise FileNotFoundError(skill_file)
        (workspace / "AGENTS.md").write_text(
            "Use Simplified Chinese. For this task, before answering read the exact installed primary Skill in full:\n"
            + str(skill_file)
            + "\nRead its required reference contracts, resolving links from that Skill location. "
            "If reading fails, report environment failure and stop. "
            "Preserve the user input and material. Do not inspect grading metadata or files outside your task workspace except the installed plugin references. "
            "The user did not authorize report persistence. Do not create or modify files.\n",
            encoding="utf-8",
        )
        materials = {}
        for name in case.get("materials", []):
            source = catalog_path.parent / "materials" / name
            shutil.copyfile(source, workspace / name)
            materials[name] = digest(source)
        before = file_snapshot(workspace)
        summary = {
            "caseId": case_id,
            "kind": case["kind"],
            "pluginVersion": "2.6.0",
            "installedPlugin": str(args.installed_plugin),
            "installedTreeHash": tree_hash,
            "installedFileCount": len(payload),
            "catalogSha256": digest(catalog_path),
            "cliVersion": cli_version,
            "model": args.model,
            "reasoningEffort": args.effort,
            "sandboxMode": args.sandbox,
            "queryDate": catalog["queryDate"],
            "timezone": catalog["timezone"],
            "inputArtifacts": materials,
            "startedAt": now(),
            "turns": [],
            "verdict": "ungraded",
        }
        thread_id = None
        next_rollout_line = 1
        try:
            for number, prompt in enumerate(case["turns"], 1):
                prefix = case_dir / f"turn-{number}"
                input_path = prefix.with_suffix(".input.txt")
                input_path.write_text(prompt, encoding="utf-8")
                raw_path = prefix.with_suffix(".jsonl")
                stderr_path = prefix.with_suffix(".stderr.txt")
                answer_path = prefix.with_suffix(".answer.md")
                turn_record = begin_turn_record(summary, number, input_path, raw_path, stderr_path)
                command = [str(args.exe), "exec"]
                if number > 1:
                    command += ["resume"]
                command += ["--json", "--skip-git-repo-check", "--model", args.model,
                            "-c", f'model_reasoning_effort="{args.effort}"',
                            "-c", 'approval_policy="never"',
                            "-c", f'sandbox_mode="{args.sandbox}"',
                            "-o", str(answer_path)]
                if number == 1:
                    command += ["-C", str(workspace), "-"]
                else:
                    if not thread_id:
                        raise RuntimeError("missing thread ID for follow-up")
                    command += [thread_id, "-"]
                print(f"START {case_id} turn {number}", flush=True)
                with raw_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                    result = subprocess.run(command, input=prompt.encode("utf-8"), cwd=workspace,
                                            env=environment, stdout=stdout, stderr=stderr,
                                            timeout=args.timeout, check=False)
                turn_record["exitCode"] = result.returncode
                if raw_path.is_file() and raw_path.stat().st_size:
                    turn_record["rawSha256"] = digest(raw_path)
                events, sha = load_events(raw_path)
                report = capture(events, sha, case_id, prompt, materials)
                if number == 1:
                    thread_id = report.get("threadId")
                rollout = preserve_rollout(args.codex_home, thread_id, prefix.with_suffix(".rollout.jsonl"))
                report["rolloutToolCalls"] = extract_rollout_tools(
                    prefix.with_suffix(".rollout.jsonl"), start_line=next_rollout_line
                )
                if isinstance(rollout.get("lineCount"), int):
                    next_rollout_line = rollout["lineCount"] + 1
                write_json(prefix.with_suffix(".capture.json"), report)
                proofs = skill_read_proof(report, skill_file, case["skill"])
                turn_record.update({
                    "rawSha256": sha,
                    "threadId": report.get("threadId"),
                    "complete": report["complete"],
                    "skillReadProofItems": proofs,
                    "toolCount": len(report["toolCalls"]),
                    "errors": report["errors"],
                    "privateRollout": rollout,
                    "rolloutToolCount": len(report["rolloutToolCalls"]),
                })
                if result.returncode != 0 or not report["complete"] or not turn_has_model_output(report):
                    raise RuntimeError(f"incomplete actual turn {number}")
                if number == 1 and not proofs:
                    raise RuntimeError("missing successful exact installed primary Skill read")
                print(f"CAPTURED {case_id} turn {number}; manual grading pending", flush=True)
            summary["status"] = "captured-ungraded"
        except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError) as error:
            summary["status"] = "invalid-environment"
            summary["error"] = str(error)
        after = file_snapshot(workspace)
        summary["workspaceChanges"] = {
            "added": sorted(set(after) - set(before)), "removed": sorted(set(before) - set(after)),
            "modified": sorted(p for p in set(before) & set(after) if before[p] != after[p]),
        }
        summary["finishedAt"] = now()
        write_json(case_dir / "run-summary.json", summary)
        if summary["status"] == "invalid-environment":
            print(f"STOP {case_id}: {summary['error']}", flush=True)
            return 1
    print("Captured requested cases; no behavioral verdict has been assigned.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

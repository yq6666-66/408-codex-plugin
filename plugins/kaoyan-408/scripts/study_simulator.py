#!/usr/bin/env python3
"""408 state simulator: Cache split, FIFO/LRU replacement, FCFS/RR scheduling.

All algorithms run step by step and emit a complete state sequence with
per-step state changes, plus a summary usable for teaching. An optional
``--html`` flag writes a self-contained local HTML player (prev/next step
navigation) built with the Python standard library only — no web service.

Text-only teaching remains fully supported when this script is unavailable;
Skills must never treat running it as a prerequisite for answering.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any


class SimulatorError(ValueError):
    """Raised on invalid simulator input (ValueError so argparse types exit cleanly)."""


def parse_int_list(value: str) -> list[int]:
    try:
        return [int(part.strip()) for part in value.split(",") if part.strip() != ""]
    except ValueError as exc:
        raise SimulatorError(f"expected a comma-separated integer list, got {value!r}") from exc


def parse_processes(value: str) -> list[dict[str, int]]:
    processes: list[dict[str, int]] = []
    for chunk in value.split(","):
        fields = chunk.strip().split(":")
        if len(fields) != 3:
            raise SimulatorError(
                f"each process must be name:arrival:burst, got {chunk!r}"
            )
        name = fields[0].strip()
        try:
            arrival, burst = int(fields[1]), int(fields[2])
        except ValueError as exc:
            raise SimulatorError(f"arrival and burst must be integers in {chunk!r}") from exc
        if burst <= 0:
            raise SimulatorError(f"burst must be positive in {chunk!r}")
        processes.append({"name": name, "arrival": arrival, "burst": burst})
    if not processes:
        raise SimulatorError("at least one process is required")
    return processes


def result(algorithm: str, params: dict[str, Any], steps: list[dict[str, Any]], summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "algorithm": algorithm,
        "params": params,
        "steps": steps,
        "summary": summary,
    }


def simulate_cache(
    addr_bits: int,
    block_size: int,
    cache_lines: int,
    mapping: str,
    addresses: list[int],
) -> dict[str, Any]:
    if addr_bits <= 0 or block_size <= 0 or cache_lines <= 0:
        raise SimulatorError("addr-bits, block-size and cache-lines must be positive")
    if block_size & (block_size - 1) or cache_lines & (cache_lines - 1):
        raise SimulatorError("block-size and cache-lines must be powers of two")
    offset_bits = block_size.bit_length() - 1
    index_bits = cache_lines.bit_length() - 1
    tag_bits = addr_bits - offset_bits - index_bits
    if tag_bits < 0:
        raise SimulatorError("address space smaller than cache; tag bits would be negative")
    max_address = (1 << addr_bits) - 1
    steps: list[dict[str, Any]] = []
    hits = misses = 0
    if mapping == "direct":
        lines: list[int | None] = [None] * cache_lines  # block_no resident in each line
    else:
        resident: OrderedDict[int, bool] = OrderedDict()  # capacity-limited, LRU eviction
    for address in addresses:
        if address < 0 or address > max_address:
            raise SimulatorError(f"address {address} exceeds {addr_bits}-bit range 0..{max_address}")
        block_no = address // block_size
        offset = address % block_size
        if mapping == "direct":
            index = block_no % cache_lines
            tag = block_no // cache_lines
            hit = lines[index] == block_no
            if not hit:
                lines[index] = block_no
        else:
            index = None
            tag = block_no
            hit = block_no in resident
            if not hit:
                resident[block_no] = True
                if len(resident) > cache_lines:
                    resident.popitem(last=False)
            else:
                resident.move_to_end(block_no)
        if hit:
            hits += 1
        else:
            misses += 1
        binary = format(address, f"0{addr_bits}b")
        split = {
            "tag": binary[:tag_bits],
            "index": None if index is None else binary[tag_bits:tag_bits + index_bits],
            "offset": binary[tag_bits + index_bits:],
        }
        steps.append({
            "step": len(steps) + 1,
            "event": "hit" if hit else "miss",
            "address": address,
            "binary": binary,
            "split": split,
            "tag": tag,
            "index": index,
            "offset": offset,
            "blockNumber": block_no,
            "stateChange": (
                f"block {block_no} already resident -> hit"
                if hit
                else f"block {block_no} loaded into {'line ' + str(index) if index is not None else 'associative set'}"
            ),
        })
    return result(
        "cache",
        {
            "addrBits": addr_bits,
            "blockSize": block_size,
            "cacheLines": cache_lines,
            "mapping": mapping,
            "offsetBits": offset_bits,
            "indexBits": index_bits if mapping == "direct" else 0,
            "tagBits": tag_bits,
            "maxAddress": max_address,
        },
        steps,
        {
            "accesses": len(addresses),
            "hits": hits,
            "misses": misses,
            "hitRate": round(hits / len(addresses), 4) if addresses else None,
        },
    )


def _replacement_simulate(
    algorithm: str,
    frames: list[int | None],
    references: list[int],
    initial: list[int],
) -> dict[str, Any]:
    if frames <= 0:
        raise SimulatorError("frames must be positive")
    if len(initial) > frames:
        raise SimulatorError("initial pages exceed frame count")
    state: list[int | None] = (initial + [None] * frames)[:frames]
    # FIFO order = insertion order; LRU order = last-use recency (stalest first).
    order: deque[int] = deque(state)
    last_used: dict[int, int] = {page: 0 for page in initial}
    tick = 0
    steps: list[dict[str, Any]] = []
    faults = hits = 0
    for position, page in enumerate(references, start=1):
        tick += 1
        evicted = None
        if page in state:
            hits += 1
            last_used[page] = tick
            if algorithm == "lru":
                order.remove(page)
                order.append(page)
            change = f"page {page} hit; frames unchanged"
            event = "hit"
        else:
            faults += 1
            if None in state:
                slot = state.index(None)
                state[slot] = page
                order.remove(None)
                order.append(page)
                change = f"page {page} loaded into empty frame {slot}"
            else:
                victim = order[0]
                evicted = victim
                slot = state.index(victim)
                state[slot] = page
                order.popleft()
                order.append(page)
                change = f"page {page} replaces page {victim} in frame {slot}"
            last_used[page] = tick
            event = "fault"
        steps.append({
            "step": position,
            "event": event,
            "reference": page,
            "frames": list(state),
            "evicted": evicted,
            "stateChange": change,
        })
    return result(
        algorithm,
        {"frames": frames, "initial": initial, "references": references},
        steps,
        {
            "references": len(references),
            "hits": hits,
            "faults": faults,
            "hitRate": round(hits / len(references), 4) if references else None,
        },
    )


def simulate_fifo(frames: int, references: list[int], initial: list[int]) -> dict[str, Any]:
    return _replacement_simulate("fifo", frames, references, initial)


def simulate_lru(frames: int, references: list[int], initial: list[int]) -> dict[str, Any]:
    return _replacement_simulate("lru", frames, references, initial)


def _scheduling_summary(processes: list[dict[str, int]], completion: dict[str, int]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    table = []
    total_wait = total_turnaround = 0
    for process in processes:
        name = process["name"]
        turnaround = completion[name] - process["arrival"]
        waiting = turnaround - process["burst"]
        total_wait += waiting
        total_turnaround += turnaround
        table.append({
            "name": name,
            "arrival": process["arrival"],
            "burst": process["burst"],
            "completion": completion[name],
            "turnaround": turnaround,
            "waiting": waiting,
        })
    count = len(processes)
    summary = {
        "processes": table,
        "averageWaiting": round(total_wait / count, 4),
        "averageTurnaround": round(total_turnaround / count, 4),
    }
    return summary, table


def simulate_fcfs(processes: list[dict[str, int]]) -> dict[str, Any]:
    ordered = sorted(processes, key=lambda p: (p["arrival"], p["name"]))
    time = 0
    steps: list[dict[str, Any]] = []
    completion: dict[str, int] = {}
    for process in ordered:
        if time < process["arrival"]:
            steps.append({
                "step": len(steps) + 1,
                "event": "idle",
                "timeStart": time,
                "timeEnd": process["arrival"],
                "stateChange": f"CPU idle {time}->{process['arrival']}, waiting for {process['name']}",
            })
            time = process["arrival"]
        end = time + process["burst"]
        steps.append({
            "step": len(steps) + 1,
            "event": "run",
            "process": process["name"],
            "timeStart": time,
            "timeEnd": end,
            "stateChange": f"{process['name']} runs {time}->{end} (burst {process['burst']})",
        })
        completion[process["name"]] = end
        time = end
    summary, _ = _scheduling_summary(processes, completion)
    return result("fcfs", {"processes": processes}, steps, summary)


def simulate_rr(processes: list[dict[str, int]], quantum: int) -> dict[str, Any]:
    if quantum <= 0:
        raise SimulatorError("quantum must be positive")
    remaining = {p["name"]: p["burst"] for p in processes}
    completion: dict[str, int] = {}
    # Deterministic tie rule: at the same instant, earlier arrivals enter the
    # queue first; a process arriving exactly at a quantum boundary enters
    # BEFORE the preempted process is re-enqueued.
    pending = sorted(processes, key=lambda p: (p["arrival"], p["name"]))
    queue: deque[dict[str, int]] = deque()
    time = 0
    steps: list[dict[str, Any]] = []

    def admit(upto: int) -> None:
        while pending and pending[0]["arrival"] <= upto:
            process = pending.pop(0)
            queue.append(process)
            steps.append({
                "step": len(steps) + 1,
                "event": "arrival",
                "process": process["name"],
                "timeStart": process["arrival"],
                "timeEnd": process["arrival"],
                "stateChange": f"{process['name']} arrives at {process['arrival']}, queue={[p['name'] for p in queue]}",
            })

    admit(time)
    while queue or pending:
        if not queue:
            next_time = pending[0]["arrival"]
            steps.append({
                "step": len(steps) + 1,
                "event": "idle",
                "timeStart": time,
                "timeEnd": next_time,
                "stateChange": f"CPU idle {time}->{next_time}",
            })
            time = next_time
            admit(time)
            continue
        process = queue.popleft()
        ran = min(quantum, remaining[process["name"]])
        start = time
        time += ran
        remaining[process["name"]] -= ran
        admit(time)
        if remaining[process["name"]] > 0:
            queue.append(process)
            change = f"{process['name']} runs {start}->{time}, preempted with {remaining[process['name']]} left"
        else:
            completion[process["name"]] = time
            change = f"{process['name']} runs {start}->{time} and completes"
        steps.append({
            "step": len(steps) + 1,
            "event": "run",
            "process": process["name"],
            "timeStart": start,
            "timeEnd": time,
            "stateChange": change,
            "queueAfter": [p["name"] for p in queue],
        })
    summary, _ = _scheduling_summary(processes, completion)
    return result(
        "rr",
        {"processes": processes, "quantum": quantum},
        steps,
        summary,
    )


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>kaoyan-408 学习模拟器</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem; background: #f8fafc; }
  h1 { font-size: 1.2rem; }
  #meta, #state { background: #fff; border: 1px solid #cbd5e1; border-radius: 8px; padding: 1rem; margin: .5rem 0; white-space: pre-wrap; }
  button { font-size: 1rem; margin-right: .5rem; padding: .4rem 1rem; }
  .changed { color: #b91c1c; font-weight: 600; }
</style>
</head>
<body>
<h1>kaoyan-408 学习模拟器 — __ALGO__</h1>
<div id="meta"></div>
<div id="state"></div>
<div>
  <button id="prev">◀ 前一步</button>
  <button id="next">后一步 ▶</button>
  <button id="jump0">回到起点</button>
  <span id="position"></span>
</div>
<script>
const DATA = __DATA__;
let cursor = 0;
function render() {
  document.getElementById("meta").textContent = JSON.stringify(DATA.params, null, 2);
  const step = DATA.steps[cursor];
  const previous = cursor > 0 ? DATA.steps[cursor - 1] : null;
  const lines = ["步骤 " + step.step + "/" + DATA.steps.length + "：" + (step.stateChange || step.event)];
  if (step.frames) { lines.push("帧状态：" + JSON.stringify(step.frames)); }
  if (step.split) { lines.push("地址拆分：" + JSON.stringify(step.split)); }
  if (previous && JSON.stringify(previous.frames) !== JSON.stringify(step.frames)) {
    lines.push("与上一步相比：帧状态变化 " + JSON.stringify(previous.frames) + " -> " + JSON.stringify(step.frames));
  }
  document.getElementById("state").innerHTML = lines.map(escape).join("\\n");
  document.getElementById("position").textContent = (cursor + 1) + " / " + DATA.steps.length;
  document.getElementById("summary")?.remove();
  const summary = document.createElement("div");
  summary.id = "summary";
  summary.textContent = "汇总：" + JSON.stringify(DATA.summary);
  document.body.appendChild(summary);
}
function escape(text) { const d = document.createElement("div"); d.textContent = text; return d.outerHTML; }
document.getElementById("prev").onclick = () => { if (cursor > 0) { cursor -= 1; render(); } };
document.getElementById("next").onclick = () => { if (cursor < DATA.steps.length - 1) { cursor += 1; render(); } };
document.getElementById("jump0").onclick = () => { cursor = 0; render(); };
render();
</script>
</body>
</html>
"""


def write_html(document: dict[str, Any], path: Path) -> None:
    payload = HTML_TEMPLATE.replace("__ALGO__", html.escape(str(document["algorithm"])))
    encoded = json.dumps(document, ensure_ascii=False).replace("</", "<\\/")
    payload = payload.replace("__DATA__", encoded)
    path.write_text(payload, encoding="utf-8", newline="\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    cache = subparsers.add_parser("cache", help="Cache address split (direct / fully associative)")
    cache.add_argument("--addr-bits", type=int, required=True)
    cache.add_argument("--block-size", type=int, required=True)
    cache.add_argument("--cache-lines", type=int, required=True)
    cache.add_argument("--mapping", choices=("direct", "associative"), default="direct")
    cache.add_argument("--addresses", required=True, type=parse_int_list)
    cache.add_argument("--html", type=Path, default=None)

    frames_parser = argparse.ArgumentParser(add_help=False)
    frames_parser.add_argument("--frames", type=int, required=True)
    frames_parser.add_argument("--references", required=True, type=parse_int_list)
    frames_parser.add_argument("--initial", type=parse_int_list, default=[])
    frames_parser.add_argument("--html", type=Path, default=None)
    for name in ("fifo", "lru"):
        subparsers.add_parser(name, parents=[frames_parser], help=f"{name.upper()} page replacement")

    fcfs = subparsers.add_parser("fcfs", help="FCFS CPU scheduling")
    fcfs.add_argument("--processes", required=True, type=parse_processes)
    fcfs.add_argument("--html", type=Path, default=None)

    rr = subparsers.add_parser("rr", help="round-robin CPU scheduling")
    rr.add_argument("--processes", required=True, type=parse_processes)
    rr.add_argument("--quantum", type=int, required=True)
    rr.add_argument("--html", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "cache":
            document = simulate_cache(args.addr_bits, args.block_size, args.cache_lines, args.mapping, args.addresses)
        elif args.command == "fifo":
            document = simulate_fifo(args.frames, args.references, args.initial)
        elif args.command == "lru":
            document = simulate_lru(args.frames, args.references, args.initial)
        elif args.command == "fcfs":
            document = simulate_fcfs(args.processes)
        else:
            document = simulate_rr(args.processes, args.quantum)
        if args.html is not None:
            write_html(document, args.html)
    except SimulatorError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    emit = json.dumps(document, ensure_ascii=False, indent=2)
    print(emit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

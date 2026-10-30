#!/usr/bin/env python3
"""Read one bundled public 408 card; protected modes never load a card."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

ID_PATTERN = re.compile(r"^(DS|CO|OS|CN)-[A-Z]+-[0-9]{3}$")
ROOT = Path(__file__).resolve().parent.parent / "references"


def project(mode: str, point_id: str | None, root: Path = ROOT) -> dict:
    if mode in {"hint", "independent", "exam"}:
        if point_id is not None:
            raise ValueError("protected modes must not receive a knowledge point ID")
        return {"mode": mode, "status": "details-deferred", "message": "详细依据留到讲评。"}
    if mode != "explain" or not point_id or not ID_PATTERN.fullmatch(point_id):
        raise ValueError("explain mode requires a valid point ID")
    directory = root / "knowledge-cards"
    if directory.is_symlink():
        raise ValueError("knowledge-card directory cannot be a symlink")
    base = directory.resolve(strict=True)
    path = base / (point_id + ".json")
    if path.is_symlink() or not path.is_file() or path.resolve().parent != base:
        raise ValueError("knowledge card is missing or unsafe")
    card = json.loads(path.read_text(encoding="utf-8"))
    if card.get("id") != point_id or card.get("schemaVersion") != "1.0":
        raise ValueError("knowledge card identity mismatch")
    index = root / "kp-408.json"
    if index.is_symlink() or not index.is_file():
        raise ValueError("knowledge index is missing or unsafe")
    points = json.loads(index.read_text(encoding="utf-8"))["knowledgePoints"]
    matches = [p for p in points if p.get("id") == point_id]
    if len(matches) != 1 or matches[0].get("knowledgeCard") != f"knowledge-cards/{point_id}.json":
        raise ValueError("knowledge card index reference mismatch")
    if card.get("evidence", {}).get("mappingStatus") != "详见索引":
        raise ValueError("knowledge card must defer annual mapping to index")
    point = matches[0]
    card["syllabusMapping"] = {k: point.get(k) for k in ("basisYear", "verified", "syllabusPath", "source", "checkedAt", "mappingStatus", "mappingNote")}
    return card


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=("explain", "hint", "independent", "exam"))
    parser.add_argument("--id")
    args = parser.parse_args()
    try:
        print(json.dumps(project(args.mode, args.id), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

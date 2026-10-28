#!/usr/bin/env python3
"""Export a whitelisted model-input projection; never grade or run a model."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

SKILL_ID = re.compile(r"kaoyan-[a-z0-9]+(?:-[a-z0-9]+)*", re.IGNORECASE)
KNOWLEDGE_ID = re.compile(r"(?:DS|CO|OS|CN)-[A-Z]+-[0-9]{3}", re.IGNORECASE)
RUNNER_ONLY_MATERIALS = {"notes-host-fixture.json", "obsidian-brain.template.json"}


def _no_alias(path: Path) -> bool:
    return not path.is_symlink() and not (hasattr(path, "is_junction") and path.is_junction())


def _materials(names: object, material_root: Path) -> list[dict[str, str]]:
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        raise ValueError("materials must be a list of relative path strings")
    if len(set(names)) != len(names):
        raise ValueError("duplicate material reference")
    if not names:
        return []
    if not _no_alias(material_root):
        raise ValueError("material root must not be a symlink or junction")
    resolved_root = material_root.resolve(strict=True)
    result = []
    for name in names:
        relative = PurePosixPath(name)
        if (not name or "\\" in name or ":" in name or relative.is_absolute()
                or any(part in {"", ".", ".."} for part in name.split("/"))):
            raise ValueError("material path must be a normalized relative path")
        if relative.name in RUNNER_ONLY_MATERIALS:
            raise ValueError("runner-only fixture setup cannot be a model material")
        current = resolved_root
        for part in relative.parts:
            current = current / part
            if not _no_alias(current):
                raise ValueError("material path contains a symlink or junction")
        resolved = current.resolve(strict=True)
        if resolved_root not in resolved.parents:
            raise ValueError("material is outside the material root")
        if not (resolved.is_file() or resolved.is_dir()):
            raise ValueError("unsupported material entry")
        if resolved.is_dir() and any(not _no_alias(child) for child in resolved.rglob("*")):
            raise ValueError("material tree contains a symlink or junction")
        result.append({"path": "materials/" + relative.as_posix()})
    return result


def export_case(catalog: object, case_id: str, *, material_root: Path) -> dict:
    """Return only natural user messages and validated isolated material references.

    Per-turn grading, host fixture setup, case IDs and status never enter output.
    The caller interleaves each user message with a real model turn; this function
    does not concatenate all turns into one prompt or fabricate assistant turns.
    """
    if not isinstance(catalog, dict) or not isinstance(catalog.get("cases"), list):
        raise ValueError("catalog must contain a cases array")
    by_id = {}
    for case in catalog["cases"]:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]:
            raise ValueError("case IDs must be nonempty strings")
        if case["id"] in by_id:
            raise ValueError("duplicate case ID")
        by_id[case["id"]] = case
    if case_id not in by_id:
        raise ValueError("unknown case ID")
    selected = by_id[case_id]
    turns = selected.get("turns")
    if not isinstance(turns, list) or not turns or any(not isinstance(t, str) or not t.strip() for t in turns):
        raise ValueError("turns must contain nonempty natural user messages")
    if any(SKILL_ID.search(t) or KNOWLEDGE_ID.search(t) for t in turns):
        raise ValueError("natural messages must not contain Skill IDs or knowledge IDs")
    return {"messages": [{"role": "user", "content": turn} for turn in turns],
            "materials": _materials(selected.get("materials", []), material_root)}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_id")
    parser.add_argument("--catalog", type=Path, default=Path(__file__).with_name("cases.json"))
    args = parser.parse_args(argv)
    try:
        catalog_path = args.catalog.resolve(strict=True)
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        output = export_case(catalog, args.case_id, material_root=catalog_path.parent / "materials")
    except (OSError, ValueError) as exc:
        print(f"input export failed: {exc}", file=sys.stderr)
        return 2
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())

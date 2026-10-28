#!/usr/bin/env python3
"""Offline structural gate for canonical 408 knowledge, independent of 2.x.

Requires the pinned development dependencies, not a legacy plugin installation.
Passing validates data consistency; it does not verify external source contents.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError
from referencing import Registry
from referencing.exceptions import Unresolvable

ROOT = Path(__file__).resolve().parents[1]
SUBJECT_PREFIXES = {"数据结构": "DS", "计算机组成原理": "CO", "操作系统": "OS", "计算机网络": "CN"}


class KnowledgeError(ValueError):
    """Canonical knowledge has invalid structure or inconsistent references."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise KnowledgeError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value):
    raise KnowledgeError("nonfinite JSON number")


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=_reject_constant)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise KnowledgeError(f"cannot read valid UTF-8 JSON: {path.name}") from exc


def _validate_schema(data, schema, label):
    try:
        Draft202012Validator.check_schema(schema)
        # An empty registry has no network retriever; remote refs fail closed.
        validator = Draft202012Validator(schema, format_checker=FormatChecker(), registry=Registry())
        error = next(validator.iter_errors(data), None)
    except (SchemaError, Unresolvable) as exc:
        raise KnowledgeError(f"invalid or nonlocal schema: {label}") from exc
    if error is not None:
        location = "/" + "/".join(str(item) for item in error.absolute_path)
        raise KnowledgeError(f"invalid {label} at {location}; schema rule: {error.validator}")


def validate_knowledge(root: Path) -> dict:
    references = root / "src/shared/references"
    points_data = load_json(references / "kp-408.json")
    cards_data = load_json(references / "rule-cards.json")
    _validate_schema(points_data, load_json(root / "schemas/kp-408.schema.json"), "knowledge-point index")
    _validate_schema(cards_data, load_json(root / "schemas/rule-cards.schema.json"), "rule cards")

    points = points_data["knowledgePoints"]
    ids = {point["id"] for point in points}
    if len(ids) != len(points):
        raise KnowledgeError("knowledge-point IDs must be unique")
    if {point["subject"] for point in points} != set(SUBJECT_PREFIXES):
        raise KnowledgeError("knowledge-point index must cover four 408 subjects")
    if any(not point["id"].startswith(SUBJECT_PREFIXES[point["subject"]] + "-") for point in points):
        raise KnowledgeError("knowledge-point subject and ID prefix mismatch")

    cards = cards_data["cards"]
    if len({card["id"] for card in cards}) != len(cards):
        raise KnowledgeError("rule-card IDs must be unique")
    for card in cards:
        if not set(card["pointIds"]) <= ids:
            raise KnowledgeError("rule card references an unknown knowledge point")
        if card["source"]["locator"] != "rule-cards.json#" + card["id"]:
            raise KnowledgeError("rule-card source locator does not resolve to that card")

    verified = sum(point["verified"] for point in points)
    return {"valid": True, "knowledgePoints": len(points), "ruleCards": len(cards),
            "externallySupportedRuleCards": sum(bool(card.get("externalReferences")) for card in cards),
            "verifiedMappings": verified, "pendingMappings": len(points) - verified,
            "scope": "structure and internal references only; no new external-source verification"}


def main() -> int:
    try:
        result = validate_knowledge(ROOT)
    except KnowledgeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

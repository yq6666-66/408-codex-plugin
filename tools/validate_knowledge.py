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
STABLE_POINT_IDS = frozenset(('CN-APP-001', 'CN-ARCH-001', 'CN-ARQ-001', 'CN-LAN-001', 'CN-LINK-001', 'CN-MAC-001', 'CN-NET-001', 'CN-NET-002', 'CN-NET-003', 'CN-PERF-001', 'CN-PHY-001', 'CN-ROUTE-001', 'CN-TCP-001', 'CN-TCP-002', 'CN-TRANS-001', 'CO-ALU-001', 'CO-BUS-001', 'CO-CACHE-001', 'CO-CACHE-002', 'CO-CPU-001', 'CO-CPU-002', 'CO-DATA-001', 'CO-DATA-002', 'CO-IO-001', 'CO-IO-002', 'CO-IO-003', 'CO-ISA-001', 'CO-MEM-001', 'CO-PERF-001', 'CO-PIPE-001', 'DS-ALG-001', 'DS-ARRAY-001', 'DS-GRAPH-001', 'DS-GRAPH-002', 'DS-GRAPH-003', 'DS-GRAPH-004', 'DS-LIST-001', 'DS-QUEUE-001', 'DS-SEARCH-001', 'DS-SEARCH-002', 'DS-SEARCH-003', 'DS-SORT-001', 'DS-STACK-001', 'DS-TREE-001', 'DS-TREE-002', 'OS-BASIC-001', 'OS-DEAD-001', 'OS-DISK-001', 'OS-FILE-001', 'OS-MEM-001', 'OS-MEM-002', 'OS-MEM-003', 'OS-MEM-004', 'OS-MEM-005', 'OS-PROC-001', 'OS-PROC-002', 'OS-SCHED-001', 'OS-SCHED-002', 'OS-SYNC-001', 'OS-SYNC-002'))
SUBJECT_PREFIXES = {"数据结构": "DS", "计算机组成原理": "CO", "操作系统": "OS", "计算机网络": "CN"}


class KnowledgeError(ValueError):
    """Canonical knowledge has invalid structure or inconsistent references."""


def mapping_counts(points: list) -> dict:
    """Count source-mapping granularity, without inferring official verification."""
    return {
        "directMappings": sum(p.get("mappingStatus") == "direct" for p in points),
        "upperOrPartialMappings": sum(p.get("mappingStatus") == "upper-topic" for p in points),
        "notFoundMappings": sum(p.get("mappingStatus") == "not-found" for p in points),
    }


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


def validate_public_cards(root: Path, points: list, rules: list) -> int:
    """Check exact one-to-one card coverage and content boundaries."""
    card_dir = root / "src/shared/references/knowledge-cards"
    if card_dir.is_symlink() or not card_dir.is_dir():
        raise KnowledgeError("public knowledge-card directory is missing or unsafe")
    expected = {p["id"] for p in points}
    actual = {p.stem for p in card_dir.iterdir() if p.is_file() and p.suffix == ".json"}
    if expected != actual or len(list(card_dir.iterdir())) != len(expected):
        raise KnowledgeError("knowledge cards must cover exactly the indexed IDs")
    rule_ids = {r["id"] for r in rules}
    def nonempty(value):
        return isinstance(value, str) and bool(value.strip())
    for point in points:
        point_id = point["id"]
        if point.get("knowledgeCard") != f"knowledge-cards/{point_id}.json":
            raise KnowledgeError("knowledge-card index reference mismatch: " + point_id)
        path = card_dir / (point_id + ".json")
        if path.is_symlink():
            raise KnowledgeError("knowledge card cannot be a symlink: " + point_id)
        card = load_json(path)
        keys = {"schemaVersion", "id", "subject", "learningGoal", "prerequisites", "concept", "conditions", "misconceptions", "workedExample", "selfCheck", "ruleCardIds", "evidence"}
        if not isinstance(card, dict) or set(card) != keys or card["schemaVersion"] != "1.0" or card["id"] != point_id or card["subject"] != point["subject"]:
            raise KnowledgeError("knowledge card identity or fields mismatch: " + point_id)
        if not all(nonempty(card[k]) for k in ("learningGoal", "concept")):
            raise KnowledgeError("knowledge card lacks learning content: " + point_id)
        for key in ("prerequisites", "conditions"):
            if not isinstance(card[key], list) or not card[key] or not all(nonempty(v) for v in card[key]):
                raise KnowledgeError("knowledge card lacks prerequisites or conditions: " + point_id)
        misconceptions = card["misconceptions"]
        if not isinstance(misconceptions, list) or not misconceptions or any(not isinstance(x, dict) or set(x) != {"claim", "correction"} or not all(nonempty(v) for v in x.values()) for x in misconceptions):
            raise KnowledgeError("knowledge card lacks misconceptions: " + point_id)
        for key, fields in (("workedExample", {"question", "solution"}), ("selfCheck", {"question"}), ("evidence", {"mappingStatus", "ruleStatus", "details"})):
            obj = card[key]
            if not isinstance(obj, dict) or set(obj) != fields or not all(nonempty(v) for v in obj.values()):
                raise KnowledgeError("knowledge card section is incomplete: " + point_id + "/" + key)
        if card["evidence"]["mappingStatus"] != "详见索引":
            raise KnowledgeError("annual mapping must use the canonical index: " + point_id)
        refs = card["ruleCardIds"]
        if not isinstance(refs, list) or not all(isinstance(x, str) for x in refs) or len(set(refs)) != len(refs) or not set(refs) <= rule_ids:
            raise KnowledgeError("knowledge card rule reference is invalid: " + point_id)
        for rule_id in refs:
            if point_id not in next(r for r in rules if r["id"] == rule_id)["pointIds"]:
                raise KnowledgeError("knowledge card rule does not cover point: " + point_id)
    return len(expected)


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
    if ids != STABLE_POINT_IDS:
        raise KnowledgeError("knowledge-point index must preserve all 60 stable IDs")
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

    public_cards = validate_public_cards(root, points, cards)

    verified = sum(point["verified"] for point in points)
    return {"valid": True, "knowledgePoints": len(points), "publicKnowledgeCards": public_cards, "ruleCards": len(cards),
            "externallySupportedRuleCards": sum(bool(card.get("externalReferences")) for card in cards),
            "verifiedMappings": verified, "pendingMappings": len(points) - verified,
            **mapping_counts(points),
            "scope": "structure and internal references only; verified denotes the recorded mapping to its stated source, not official authority or new external-source verification"}


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

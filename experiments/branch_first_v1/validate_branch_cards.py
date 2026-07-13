from __future__ import annotations

import argparse
from itertools import combinations
import json
from pathlib import Path
import re
from typing import Any


TEXT_FIELDS = ("core_mechanism", "premise_difference", "character_choice", "real_cost")
BEAT_FIELDS = ("setup", "escalation", "irreversible_choice", "local_payoff", "end_hook")


def _normalized_bigrams(value: str) -> set[str]:
    compact = re.sub(r"[^0-9A-Za-z\u3400-\u9fff]", "", value).lower()
    return {compact[index : index + 2] for index in range(max(0, len(compact) - 1))}


def card_text(card: dict[str, Any]) -> str:
    parts = [str(card.get(name) or "") for name in TEXT_FIELDS]
    beats = card.get("beats") or {}
    if isinstance(beats, dict):
        parts.extend(str(beats.get(name) or "") for name in BEAT_FIELDS)
    return "\n".join(parts)


def _content_size(value: Any) -> int:
    if isinstance(value, (list, dict, str)):
        return len(value)
    return 0


def validate_card(card: dict[str, Any], contract: dict[str, Any], case_id: str, branch_id: str) -> list[str]:
    issues: list[str] = []
    required = {
        "schema_version", "case_id", "branch_id", *TEXT_FIELDS, "world_rule_usage", "beats", "freedom_budget_choices",
        "idea_lock_evidence", "forbidden_change_checks", "risk_register",
    }
    if set(card) != required:
        issues.append("top-level fields must exactly match branch-card/v1")
    if card.get("schema_version") != "branch-card/v1":
        issues.append("invalid schema_version")
    if card.get("case_id") != case_id:
        issues.append("case_id mismatch")
    if card.get("branch_id") != branch_id:
        issues.append("branch_id mismatch")
    for field in TEXT_FIELDS:
        if not isinstance(card.get(field), str) or len(str(card.get(field) or "").strip()) < 4:
            issues.append(f"missing or short {field}")
    if _content_size(card.get("world_rule_usage")) < 1:
        issues.append("missing world_rule_usage")
    beats = card.get("beats")
    if not isinstance(beats, dict) or set(beats) != set(BEAT_FIELDS):
        issues.append("beats must contain exactly five required fields")
    elif any(not isinstance(beats[name], str) or len(beats[name].strip()) < 4 for name in BEAT_FIELDS):
        issues.append("each beat requires concrete text")
    locks = contract.get("idea_locks") or []
    evidence = card.get("idea_lock_evidence")
    if not isinstance(evidence, (list, dict)) or len(evidence) < len(locks):
        issues.append("idea_lock_evidence must cover every public lock")
    forbidden = contract.get("forbidden_changes") or []
    checks = card.get("forbidden_change_checks")
    if not isinstance(checks, (list, dict)) or len(checks) < len(forbidden):
        issues.append("forbidden_change_checks must cover every public prohibition")
    choices = card.get("freedom_budget_choices")
    if not isinstance(choices, (list, dict)) or len(choices) < 2:
        issues.append("at least two freedom budget choices are required")
    risks = card.get("risk_register")
    if not isinstance(risks, list) or not 1 <= len(risks) <= 3:
        issues.append("risk_register requires one to three risks")
    return issues


def validate_case(case_dir: Path, contract_path: Path) -> dict[str, Any]:
    case_id = case_dir.name
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    cards: dict[str, dict[str, Any]] = {}
    card_issues: dict[str, list[str]] = {}
    for index in range(1, 4):
        branch_id = f"branch_{index:02d}"
        path = case_dir / "branch_cards" / f"{branch_id}.json"
        card = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(card, dict):
            raise ValueError(f"branch card must be an object: {path}")
        cards[branch_id] = card
        card_issues[branch_id] = validate_card(card, contract, case_id, branch_id)
    similarities = []
    for left, right in combinations(cards, 2):
        left_tokens = _normalized_bigrams(card_text(cards[left]))
        right_tokens = _normalized_bigrams(card_text(cards[right]))
        union = left_tokens | right_tokens
        similarities.append(
            {
                "pair": [left, right],
                "surface_bigram_jaccard": round(len(left_tokens & right_tokens) / len(union), 4) if union else 0.0,
            }
        )
    return {
        "case_id": case_id,
        "schema_valid": not any(card_issues.values()),
        "card_issues": card_issues,
        "surface_similarity": similarities,
        "requires_semantic_diversity_review": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate Branch Cards before semantic diversity selection")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--public-run", type=Path, required=True)
    parser.add_argument("--case", action="append", required=True)
    args = parser.parse_args(argv)
    results = [
        validate_case(
            args.run_dir / case_id,
            args.public_run / case_id / "public" / "idea_contract.json",
        )
        for case_id in args.case
    ]
    print(json.dumps({"cases": results}, ensure_ascii=False, indent=2))
    return 0 if all(item["schema_valid"] for item in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())

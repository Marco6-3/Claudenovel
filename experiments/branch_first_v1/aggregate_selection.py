from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object: {path}")
    return payload


def validate(payload: dict[str, Any], weights: dict[str, float]) -> dict[str, dict[str, Any]]:
    cards = payload.get("cards")
    if not isinstance(cards, list) or len(cards) != 3:
        raise ValueError("selector must score exactly three cards")
    by_label: dict[str, dict[str, Any]] = {}
    for card in cards:
        if not isinstance(card, dict):
            raise ValueError("selector card result must be an object")
        label = str(card.get("label") or "")
        if label not in {"A", "B", "C"} or label in by_label:
            raise ValueError(f"invalid selector label: {label}")
        raw_scores = card.get("scores")
        if not isinstance(raw_scores, dict) or set(raw_scores) != set(weights):
            raise ValueError(f"invalid selector score dimensions: {label}")
        scores = {name: float(raw_scores[name]) for name in weights}
        if any(not 0 <= value <= 10 for value in scores.values()):
            raise ValueError(f"selector score out of range: {label}")
        blocking = card.get("blocking_issues") or []
        if not isinstance(blocking, list):
            raise ValueError(f"blocking_issues must be a list: {label}")
        by_label[label] = {
            "scores": scores,
            "weighted_score": round(sum(scores[name] * weight for name, weight in weights.items()), 3),
            "eligible": bool(card.get("hard_gate_passed")) and not blocking,
            "blocking_issues": [str(item) for item in blocking],
            "evidence": card.get("evidence") or {},
        }
    selected = payload.get("selected_labels")
    if not isinstance(selected, list) or len(selected) != 2 or selected != sorted(set(selected)):
        raise ValueError("selected_labels must contain two distinct sorted labels")
    if any(label not in by_label or not by_label[label]["eligible"] for label in selected):
        raise ValueError("selected labels must be hard-gate eligible")
    return by_label


def aggregate(
    forward: dict[str, Any],
    reverse: dict[str, Any],
    mapping: dict[str, Any],
    *,
    tiebreak: dict[str, Any] | None = None,
) -> dict[str, Any]:
    weights = {name: float(weight) for name, weight in mapping["weights"].items()}
    passes = {"forward": forward, "reverse": reverse}
    if tiebreak is not None:
        passes["rotate"] = tiebreak
    validated = {name: validate(payload, weights) for name, payload in passes.items()}
    selected_sources = {
        name: sorted(mapping["passes"][name][label] for label in payload["selected_labels"])
        for name, payload in passes.items()
    }
    pair_counts = Counter(tuple(value) for value in selected_sources.values())
    most_common_pair, most_common_count = pair_counts.most_common(1)[0]
    required_votes = 1 if len(passes) == 1 else 2
    consistent = most_common_count >= required_votes
    averages: dict[str, Any] = {}
    for source in ("branch_01", "branch_02", "branch_03"):
        items = []
        for pass_name in passes:
            label = next(key for key, value in mapping["passes"][pass_name].items() if value == source)
            items.append(validated[pass_name][label])
        average_scores = {
            dimension: round(sum(item["scores"][dimension] for item in items) / len(items), 3)
            for dimension in weights
        }
        averages[source] = {
            "scores": average_scores,
            "weighted_score": round(sum(average_scores[name] * weight for name, weight in weights.items()), 3),
            "hard_gate_passed": all(item["eligible"] for item in items),
        }
    return {
        "case_id": mapping["case_id"],
        "status": "selected" if consistent else "selector_uncertain",
        "selected_branches": list(most_common_pair) if consistent else [],
        "pass_selections": selected_sources,
        "selection_votes": {"+".join(pair): count for pair, count in sorted(pair_counts.items())},
        "diagnostic_averages": averages,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate swapped-order Branch Card selection")
    parser.add_argument("--forward", type=Path, required=True)
    parser.add_argument("--reverse", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--tiebreak", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = aggregate(
        load(args.forward),
        load(args.reverse),
        load(args.mapping),
        tiebreak=load(args.tiebreak) if args.tiebreak else None,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def validate_pass(payload: dict[str, Any], weights: dict[str, float], expected_labels: set[str]) -> list[dict[str, Any]]:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("judge payload requires candidates list")
    labels = [str(item.get("label") or "") for item in candidates if isinstance(item, dict)]
    if set(labels) != expected_labels or len(labels) != len(expected_labels):
        raise ValueError("judge labels must cover each anonymous candidate exactly once")

    validated: list[dict[str, Any]] = []
    for item in candidates:
        label = str(item["label"])
        scores = item.get("scores")
        if not isinstance(scores, dict) or set(scores) != set(weights):
            raise ValueError(f"invalid score dimensions for {label}")
        numeric: dict[str, float] = {}
        for dimension in weights:
            value = scores[dimension]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= float(value) <= 10:
                raise ValueError(f"invalid score for {label}.{dimension}")
            numeric[dimension] = float(value)
        blocking = item.get("blocking_issues") or []
        if not isinstance(blocking, list):
            raise ValueError(f"blocking_issues must be a list for {label}")
        weighted = round(sum(numeric[name] * weight for name, weight in weights.items()), 3)
        validated.append(
            {
                "label": label,
                "scores": numeric,
                "weighted_score": weighted,
                "hard_gate_passed": bool(item.get("hard_gate_passed", not blocking)),
                "blocking_issues": [str(issue) for issue in blocking],
                "evidence": item.get("evidence") or {},
            }
        )
    eligible = [item for item in validated if item["hard_gate_passed"] and not item["blocking_issues"]]
    if not eligible:
        raise ValueError("judge has no eligible candidates")
    calculated_winner = sorted(eligible, key=lambda item: (-item["weighted_score"], item["label"]))[0]["label"]
    if payload.get("winner_label") != calculated_winner:
        raise ValueError("judge winner does not match recomputed scores")
    return validated


def aggregate(
    forward: dict[str, Any],
    reverse: dict[str, Any],
    mapping: dict[str, Any],
    weights: dict[str, float],
    *,
    ineligible_sources: set[str] | None = None,
) -> dict[str, Any]:
    forward_map = mapping["passes"]["forward"]
    reverse_map = mapping["passes"]["reverse"]
    sources = set(forward_map.values())
    if sources != set(reverse_map.values()):
        raise ValueError("forward and reverse mappings must contain the same sources")
    excluded = set(ineligible_sources or ())
    unknown_exclusions = excluded - sources
    if unknown_exclusions:
        raise ValueError(f"unknown ineligible sources: {', '.join(sorted(unknown_exclusions))}")
    if excluded == sources:
        raise ValueError("at least one source must remain comparison-eligible")
    labels = set(forward_map)
    forward_items = validate_pass(forward, weights, labels)
    reverse_items = validate_pass(reverse, weights, labels)
    pass_items = {"forward": forward_items, "reverse": reverse_items}
    maps = {"forward": forward_map, "reverse": reverse_map}

    by_source: dict[str, dict[str, Any]] = {}
    for source in sorted(sources):
        items: list[dict[str, Any]] = []
        for pass_name in ("forward", "reverse"):
            label = next(label for label, mapped_source in maps[pass_name].items() if mapped_source == source)
            items.append(next(item for item in pass_items[pass_name] if item["label"] == label))
        average_scores = {
            dimension: round(sum(item["scores"][dimension] for item in items) / 2, 3)
            for dimension in weights
        }
        by_source[source] = {
            "scores": average_scores,
            "weighted_score": round(sum(average_scores[name] * weight for name, weight in weights.items()), 3),
            "pass_weighted_scores": [item["weighted_score"] for item in items],
            "hard_gate_passed": all(item["hard_gate_passed"] and not item["blocking_issues"] for item in items),
            "comparison_eligible": source not in excluded,
        }

    winners: dict[str, str] = {}
    for pass_name in ("forward", "reverse"):
        eligible = [
            item
            for item in pass_items[pass_name]
            if item["hard_gate_passed"]
            and not item["blocking_issues"]
            and maps[pass_name][item["label"]] not in excluded
        ]
        if not eligible:
            raise ValueError(f"{pass_name} judge has no comparison-eligible candidates")
        pass_winner = sorted(eligible, key=lambda item: (-item["weighted_score"], item["label"]))[0]
        winners[pass_name] = maps[pass_name][pass_winner["label"]]
    consistent = winners["forward"] == winners["reverse"]
    return {
        "case_id": mapping["case_id"],
        "status": "selected" if consistent else "judge_uncertain",
        "official_winner": winners["forward"] if consistent else None,
        "order_consistent": consistent,
        "pass_winners": winners,
        "ineligible_sources": sorted(excluded),
        "diagnostic_averages": by_source,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate and aggregate swapped-order benchmark Judge results")
    parser.add_argument("--forward", type=Path, required=True)
    parser.add_argument("--reverse", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--section", choices=["independent_quality", "author_route_alignment"], required=True)
    parser.add_argument(
        "--ineligible-source",
        action="append",
        default=[],
        help="Keep a source in diagnostics but exclude it from the official quality winner",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    weights = _load(args.rubric)[args.section]
    result = aggregate(
        _load(args.forward),
        _load(args.reverse),
        _load(args.mapping),
        weights,
        ineligible_sources=set(args.ineligible_source),
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

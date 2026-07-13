from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected object: {path}")
    return payload


def validate(payload: dict[str, Any], dimensions: set[str]) -> None:
    hard_gate = payload.get("hard_gate")
    if not isinstance(hard_gate, dict) or set(hard_gate) != {"A", "B"}:
        raise ValueError("hard_gate must cover A and B")
    for label, result in hard_gate.items():
        if not isinstance(result, dict) or not isinstance(result.get("passed"), bool):
            raise ValueError(f"invalid hard gate for {label}")
        if not isinstance(result.get("issues") or [], list):
            raise ValueError(f"hard gate issues must be a list for {label}")
    results = payload.get("dimensions")
    if not isinstance(results, dict) or set(results) != dimensions:
        raise ValueError("pairwise dimensions are incomplete")
    for name, result in results.items():
        if not isinstance(result, dict) or result.get("winner") not in {"A", "B", "tie"}:
            raise ValueError(f"invalid winner for {name}")
    if payload.get("overall_winner") not in {"A", "B", "tie"}:
        raise ValueError("invalid overall_winner")
    overall = payload["overall_winner"]
    if overall != "tie":
        gate = hard_gate[overall]
        if not gate["passed"] or gate.get("issues"):
            raise ValueError("overall_winner must pass the hard gate without issues")
    confidence = payload.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be between zero and one")


def aggregate(forward: dict[str, Any], reverse: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    dimensions = set(mapping["dimensions"])
    validate(forward, dimensions)
    validate(reverse, dimensions)
    passes = {"forward": forward, "reverse": reverse}
    resolved: dict[str, str] = {}
    for name, payload in passes.items():
        winner = payload["overall_winner"]
        resolved[name] = "tie" if winner == "tie" else mapping["passes"][name][winner]
    stable = len(set(resolved.values())) == 1
    official = resolved["forward"] if stable else None
    return {
        "case_id": mapping["case_id"],
        "status": "selected" if stable and official != "tie" else "tie" if stable else "judge_uncertain",
        "official_winner": official if official != "tie" else None,
        "pass_winners": resolved,
        "confidences": {name: float(payload["confidence"]) for name, payload in passes.items()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate swapped-order pairwise prose judgments")
    parser.add_argument("--forward", type=Path, required=True)
    parser.add_argument("--reverse", type=Path, required=True)
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    result = aggregate(load(args.forward), load(args.reverse), load(args.mapping))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

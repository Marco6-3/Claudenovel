from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "branch_first_v1" / "aggregate_pairwise.py"
SPEC = importlib.util.spec_from_file_location("aggregate_branch_pairwise", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


MAPPING = {
    "case_id": "case",
    "dimensions": ["idea", "arc"],
    "passes": {
        "forward": {"A": "left", "B": "right"},
        "reverse": {"A": "right", "B": "left"},
    },
}


def payload(winner: str) -> dict:
    return {
        "hard_gate": {"A": {"passed": True, "issues": []}, "B": {"passed": True, "issues": []}},
        "dimensions": {
            "idea": {"winner": winner, "evidence": "e"},
            "arc": {"winner": winner, "evidence": "e"},
        },
        "overall_winner": winner,
        "confidence": 0.8,
    }


def test_pairwise_maps_same_source_across_swapped_order() -> None:
    result = module.aggregate(payload("A"), payload("B"), MAPPING)

    assert result["status"] == "selected"
    assert result["official_winner"] == "left"


def test_pairwise_preserves_real_tie() -> None:
    result = module.aggregate(payload("tie"), payload("tie"), MAPPING)

    assert result["status"] == "tie"
    assert result["official_winner"] is None


def test_pairwise_marks_order_disagreement_uncertain() -> None:
    result = module.aggregate(payload("A"), payload("A"), MAPPING)

    assert result["status"] == "judge_uncertain"

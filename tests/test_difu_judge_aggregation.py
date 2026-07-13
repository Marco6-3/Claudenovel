from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "difu_early_continuation_v1"
    / "aggregate_judges.py"
)
SPEC = importlib.util.spec_from_file_location("difu_judge_aggregation", MODULE_PATH)
assert SPEC and SPEC.loader
aggregation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(aggregation)


WEIGHTS = {"continuity": 0.6, "unit_arc": 0.4}
MAPPING = {
    "case_id": "case",
    "passes": {
        "forward": {"A": "candidate", "B": "original"},
        "reverse": {"A": "original", "B": "candidate"},
    },
}


def _payload(a: float, b: float) -> dict:
    candidates = []
    for label, score in (("A", a), ("B", b)):
        candidates.append(
            {
                "label": label,
                "hard_gate_passed": True,
                "scores": {"continuity": score, "unit_arc": score},
                "blocking_issues": [],
                "evidence": {},
            }
        )
    winner = "A" if a >= b else "B"
    return {"candidates": candidates, "winner_label": winner}


def test_aggregate_maps_consistent_winner_across_swapped_labels() -> None:
    result = aggregation.aggregate(_payload(9, 7), _payload(7, 9), MAPPING, WEIGHTS)

    assert result["status"] == "selected"
    assert result["official_winner"] == "candidate"
    assert result["diagnostic_averages"]["candidate"]["weighted_score"] == 9


def test_aggregate_marks_first_position_bias_uncertain() -> None:
    result = aggregation.aggregate(_payload(9, 7), _payload(9, 7), MAPPING, WEIGHTS)

    assert result["status"] == "judge_uncertain"
    assert result["official_winner"] is None
    assert result["pass_winners"] == {"forward": "candidate", "reverse": "original"}


def test_aggregate_keeps_ineligible_original_as_diagnostic_only() -> None:
    result = aggregation.aggregate(
        _payload(8, 9),
        _payload(9, 8),
        MAPPING,
        WEIGHTS,
        ineligible_sources={"original"},
    )

    assert result["status"] == "selected"
    assert result["official_winner"] == "candidate"
    assert result["ineligible_sources"] == ["original"]
    assert result["diagnostic_averages"]["original"]["comparison_eligible"] is False

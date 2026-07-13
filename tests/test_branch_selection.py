from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "branch_first_v1" / "aggregate_selection.py"
SPEC = importlib.util.spec_from_file_location("aggregate_branch_selection", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


MAPPING = {
    "case_id": "case",
    "weights": {"quality": 0.7, "diversity": 0.3},
    "passes": {
        "forward": {"A": "branch_01", "B": "branch_02", "C": "branch_03"},
        "reverse": {"A": "branch_03", "B": "branch_02", "C": "branch_01"},
        "rotate": {"A": "branch_02", "B": "branch_03", "C": "branch_01"},
    },
}


def payload(selected: list[str]) -> dict:
    return {
        "cards": [
            {
                "label": label,
                "hard_gate_passed": True,
                "scores": {"quality": score, "diversity": score},
                "evidence": {},
                "blocking_issues": [],
            }
            for label, score in (("A", 9), ("B", 8), ("C", 7))
        ],
        "selected_labels": selected,
    }


def test_selection_aggregation_maps_swapped_labels_to_same_sources() -> None:
    result = module.aggregate(payload(["A", "B"]), payload(["B", "C"]), MAPPING)

    assert result["status"] == "selected"
    assert result["selected_branches"] == ["branch_01", "branch_02"]


def test_selection_aggregation_marks_source_set_disagreement() -> None:
    result = module.aggregate(payload(["A", "B"]), payload(["A", "B"]), MAPPING)

    assert result["status"] == "selector_uncertain"
    assert result["selected_branches"] == []


def test_selection_aggregation_uses_third_order_only_to_break_tie() -> None:
    tiebreak = payload(["A", "C"])
    result = module.aggregate(
        payload(["A", "B"]),
        payload(["A", "B"]),
        MAPPING,
        tiebreak=tiebreak,
    )

    assert result["status"] == "selected"
    assert result["selected_branches"] == ["branch_01", "branch_02"]

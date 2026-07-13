from __future__ import annotations

from collections import Counter
import json
from math import sqrt
from pathlib import Path
import re


REPO = Path(__file__).resolve().parents[3]
PILOT = Path(__file__).resolve().parents[1] / "runs" / "pilot_2026-07-13"
JUDGES = PILOT / "judge"
CASES = ("after_chapter_11", "after_chapter_16")
SOURCES = ("candidate_01", "candidate_02", "candidate_03")


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff]", "", text).lower()


def ngrams(text: str, n: int = 4) -> Counter[str]:
    value = normalize(text)
    return Counter(value[index : index + n] for index in range(max(0, len(value) - n + 1)))


def cosine(left: Counter[str], right: Counter[str]) -> float:
    dot = sum(value * right.get(key, 0) for key, value in left.items())
    left_norm = sqrt(sum(value * value for value in left.values()))
    right_norm = sqrt(sum(value * value for value in right.values()))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def jaccard(left: Counter[str], right: Counter[str]) -> float:
    left_keys = set(left)
    right_keys = set(right)
    union = left_keys | right_keys
    return len(left_keys & right_keys) / len(union) if union else 0.0


def pearson(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right, strict=True))
    left_denominator = sqrt(sum((x - left_mean) ** 2 for x in left))
    right_denominator = sqrt(sum((y - right_mean) ** 2 for y in right))
    denominator = left_denominator * right_denominator
    return numerator / denominator if denominator else 0.0


def pass_scores(case: str, direction: str, weights: dict[str, float]) -> dict[str, float]:
    base = JUDGES / case
    mapping = load(base / "_root_mapping.json")["passes"][direction]
    payload = load(base / "judgments" / f"quality_{direction}.json")
    scores: dict[str, float] = {}
    for item in payload["candidates"]:
        source = mapping[item["label"]]
        scores[source] = sum(float(item["scores"][name]) * weight for name, weight in weights.items())
    return scores


def winner(scores: dict[str, float], sources: tuple[str, ...]) -> str:
    return sorted(sources, key=lambda source: (-scores[source], source))[0]


def robustness_winners(
    averages: dict[str, dict],
    weights: dict[str, float],
) -> dict[str, str]:
    variants: dict[str, dict[str, float]] = {
        "declared_weights": weights,
        "equal_weights": {name: 1 / len(weights) for name in weights},
    }
    for omitted in weights:
        kept = {name: weight for name, weight in weights.items() if name != omitted}
        total = sum(kept.values())
        variants[f"without_{omitted}"] = {name: weight / total for name, weight in kept.items()}
    result: dict[str, str] = {}
    for variant, variant_weights in variants.items():
        totals = {
            source: sum(averages[source]["scores"][name] * weight for name, weight in variant_weights.items())
            for source in SOURCES
        }
        result[variant] = winner(totals, SOURCES)
    return result


def analyze_case(case: str, weights: dict[str, float]) -> dict:
    quality = load(PILOT / case / "quality_result.json")
    route = load(PILOT / case / "route_result.json")
    averages = quality["diagnostic_averages"]
    texts = {
        source: (PILOT / case / "candidates" / f"{source}.md").read_text(encoding="utf-8")
        for source in SOURCES
    }
    grams = {source: ngrams(text) for source, text in texts.items()}
    semantic_payload = load(Path(__file__).with_name("semantic_features.json"))
    semantic_features = {
        source: set(semantic_payload["cases"][case][source])
        for source in SOURCES
    }
    pairwise = []
    for index, left in enumerate(SOURCES):
        for right in SOURCES[index + 1 :]:
            pairwise.append(
                {
                    "pair": [left, right],
                    "char_4gram_cosine": round(cosine(grams[left], grams[right]), 4),
                    "char_4gram_jaccard": round(jaccard(grams[left], grams[right]), 4),
                    "manual_macro_event_jaccard": round(
                        len(semantic_features[left] & semantic_features[right])
                        / len(semantic_features[left] | semantic_features[right]),
                        4,
                    ),
                }
            )

    best_source = winner({source: averages[source]["weighted_score"] for source in SOURCES}, SOURCES)
    oracle_scores = {
        dimension: max(averages[source]["scores"][dimension] for source in SOURCES)
        for dimension in weights
    }
    oracle_bound = sum(oracle_scores[name] * weight for name, weight in weights.items())

    forward = pass_scores(case, "forward", weights)
    reverse = pass_scores(case, "reverse", weights)
    first_two = ("candidate_01", "candidate_02")
    stage_one_winners = {
        "forward": winner(forward, first_two),
        "reverse": winner(reverse, first_two),
    }
    stage_one_consistent = len(set(stage_one_winners.values())) == 1
    generated_under_adaptive_policy = 2 if stage_one_consistent else 3

    forward_values = [forward[source] for source in SOURCES]
    reverse_values = [reverse[source] for source in SOURCES]
    score_mae = sum(abs(left - right) for left, right in zip(forward_values, reverse_values, strict=True)) / 3

    dimension_leaders = {
        dimension: [
            source
            for source in SOURCES
            if averages[source]["scores"][dimension]
            == max(averages[item]["scores"][dimension] for item in SOURCES)
        ]
        for dimension in weights
    }
    route_averages = route["diagnostic_averages"]
    mean_macro_jaccard = sum(item["manual_macro_event_jaccard"] for item in pairwise) / len(pairwise)
    heuristic_effective_channels = len(SOURCES) / (1 + (len(SOURCES) - 1) * mean_macro_jaccard)
    return {
        "quality_best": best_source,
        "quality_scores": {source: averages[source]["weighted_score"] for source in SOURCES},
        "route_scores": {source: route_averages[source]["weighted_score"] for source in SOURCES},
        "pairwise_text_diversity": pairwise,
        "mean_pairwise_4gram_cosine": round(
            sum(item["char_4gram_cosine"] for item in pairwise) / len(pairwise), 4
        ),
        "mean_manual_macro_event_jaccard": round(mean_macro_jaccard, 4),
        "heuristic_effective_macro_channels": round(heuristic_effective_channels, 4),
        "judge_score_pearson_forward_reverse": round(pearson(forward_values, reverse_values), 4),
        "judge_same_source_score_mae": round(score_mae, 4),
        "stage_one_two_writer_winners": stage_one_winners,
        "stage_one_consistent": stage_one_consistent,
        "adaptive_generated_candidates": generated_under_adaptive_policy,
        "third_writer_changed_best_average": best_source == "candidate_03",
        "oracle_dimension_fusion_bound": round(oracle_bound, 4),
        "best_single_score": averages[best_source]["weighted_score"],
        "maximum_fusion_headroom": round(oracle_bound - averages[best_source]["weighted_score"], 4),
        "dimension_leaders": dimension_leaders,
        "rubric_sensitivity_winners": robustness_winners(averages, weights),
    }


def main() -> None:
    rubric = load(REPO / "experiments" / "difu_early_continuation_v1" / "rubric.json")
    weights = rubric["independent_quality"]
    cases = {case: analyze_case(case, weights) for case in CASES}
    total_adaptive = sum(item["adaptive_generated_candidates"] for item in cases.values())
    payload = {
        "experiment": "retrospective architecture probes on two leakage-controlled writing cases",
        "limitations": [
            "Only two cut points and one writer model family are available.",
            "Character n-grams measure surface diversity, not semantic plot diversity.",
            "The oracle fusion bound assumes impossible per-dimension cherry-picking and is only an upper-bound diagnostic.",
        ],
        "cases": cases,
        "cross_case": {
            "always_three_generated_candidates": len(CASES) * 3,
            "adaptive_two_then_escalate_generated_candidates": total_adaptive,
            "pilot_candidate_generation_reduction": round(1 - total_adaptive / (len(CASES) * 3), 4),
            "cases_where_third_writer_changed_best_average": sum(
                bool(item["third_writer_changed_best_average"]) for item in cases.values()
            ),
            "mean_maximum_fusion_headroom": round(
                sum(item["maximum_fusion_headroom"] for item in cases.values()) / len(cases), 4
            ),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

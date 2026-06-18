"""Offline benchmark for entity resolution algorithms."""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Sequence

from . import entity, relation, structure
from .entity_resolver import AliasMap, count_entity_mentions, merge_alias_maps


@dataclass(frozen=True)
class EntityBenchmarkCase:
    id: str
    description: str
    text: str
    aliases: AliasMap
    expected_entities: set[str]
    forbidden_entities: set[str]
    expected_counts: dict[str, int]
    expected_relations: set[tuple[str, str, str]]


@dataclass
class EntityBenchmarkResult:
    case_id: str
    algorithm: str
    detected_entities: list[str]
    missing_entities: list[str]
    forbidden_hits: list[str]
    expected_recall: float
    forbidden_precision: float
    count_accuracy: float
    relation_recall: float
    latency_ms: float
    passed: bool


@dataclass
class EntityAlgorithmSummary:
    algorithm: str
    cases: int
    pass_rate: float
    avg_expected_recall: float
    avg_forbidden_precision: float
    avg_count_accuracy: float
    avg_relation_recall: float
    avg_latency_ms: float
    final_score: float


@dataclass
class EntityBenchmarkReport:
    best_algorithm: str
    acceptance: dict[str, float]
    summaries: list[EntityAlgorithmSummary]
    results: list[EntityBenchmarkResult]


def default_entity_resolution_suite() -> list[EntityBenchmarkCase]:
    text = """
第1章 重生见面

陈汉升回到校园，故意牵住萧容鱼的手。萧容鱼瞪着陈汉升，却没有立刻甩开。

第2章 雨天图书馆

沈幼楚在图书馆整理书架，小陈递给沈幼楚一把伞。沈幼楚小声说谢谢。

第3章 圣诞电话

陈部长给小鱼儿打电话，萧主任听出陈汉升在撒谎。另一边，沈憨憨也收到小陈的消息。
"""
    aliases = {
        "陈汉升": ["小陈", "陈部长"],
        "萧容鱼": ["小鱼儿", "萧主任"],
        "沈幼楚": ["沈憨憨"],
    }
    return [
        EntityBenchmarkCase(
            id="rebirth_romance_aliases",
            description="Long Chinese names, prefix fragments, and high-frequency aliases.",
            text=text.strip(),
            aliases=aliases,
            expected_entities={"陈汉升", "萧容鱼", "沈幼楚"},
            forbidden_entities={"陈汉", "萧容", "沈幼", "图书馆", "校园"},
            expected_counts={"陈汉升": 6, "萧容鱼": 4, "沈幼楚": 4},
            expected_relations={
                ("陈汉升", "给予", "沈幼楚"),
                ("陈汉升", "联系", "萧容鱼"),
                ("萧容鱼", "遇见", "陈汉升"),
            },
        )
    ]


def _chapters_for(case: EntityBenchmarkCase) -> list[structure.Chapter]:
    return structure.parse_chapters(case.text)


def _legacy_prefix_algorithm(case: EntityBenchmarkCase) -> tuple[Counter, list[tuple[str, str, str]]]:
    """Simulate the old failure mode: prefix fragments beat full names."""
    counts: Counter = Counter()
    for canonical in case.aliases:
        if len(canonical) >= 3:
            counts[canonical[:2]] += case.text.count(canonical[:2])
        counts[canonical] += case.text.count(canonical)
    filtered = Counter({name: count for name, count in counts.items() if count})
    for short in list(filtered):
        for long in list(filtered):
            if short != long and long.startswith(short) and len(long) > len(short):
                if long in filtered:
                    del filtered[long]
    aliases = {name: [] for name in filtered}
    triples = relation.extract_relations_rule(_chapters_for(case), aliases=aliases)
    return filtered, triples


def _hybrid_longest_algorithm(case: EntityBenchmarkCase) -> tuple[Counter, list[tuple[str, str, str]]]:
    chapters = _chapters_for(case)
    aliases = entity.discover_entity_aliases(chapters, include_builtin_present=False)
    stats = entity.compute_entity_stats(chapters, aliases=aliases)
    triples = relation.extract_relations_rule(chapters, aliases=aliases)
    return stats.occurrences, triples


def _seeded_alias_algorithm(case: EntityBenchmarkCase) -> tuple[Counter, list[tuple[str, str, str]]]:
    chapters = _chapters_for(case)
    discovered = entity.discover_entity_aliases(
        chapters,
        include_builtin_present=False,
        seed_aliases=case.aliases,
    )
    aliases = merge_alias_maps(discovered, case.aliases)
    stats = entity.compute_entity_stats(chapters, aliases=aliases)
    triples = relation.extract_relations_rule(chapters, aliases=aliases)
    return stats.occurrences, triples


ALGORITHMS: dict[str, Callable[[EntityBenchmarkCase], tuple[Counter, list[tuple[str, str, str]]]]] = {
    "legacy_prefix": _legacy_prefix_algorithm,
    "hybrid_longest": _hybrid_longest_algorithm,
    "seeded_alias": _seeded_alias_algorithm,
}


def _safe_ratio(value: int, total: int) -> float:
    if total <= 0:
        return 1.0
    return round(value / total, 4)


def _count_accuracy(detected: Mapping[str, int], expected: Mapping[str, int]) -> float:
    if not expected:
        return 1.0
    scores = []
    for name, target in expected.items():
        got = detected.get(name, 0)
        if target <= 0:
            scores.append(1.0 if got == 0 else 0.0)
            continue
        scores.append(max(0.0, 1.0 - abs(got - target) / target))
    return round(sum(scores) / len(scores), 4)


def evaluate_entity_case(
    case: EntityBenchmarkCase,
    algorithm: str,
    runner: Callable[[EntityBenchmarkCase], tuple[Counter, list[tuple[str, str, str]]]],
    *,
    min_expected_recall: float = 1.0,
    min_forbidden_precision: float = 1.0,
    min_count_accuracy: float = 0.8,
    min_relation_recall: float = 0.5,
) -> EntityBenchmarkResult:
    start = time.perf_counter()
    counts, triples = runner(case)
    latency_ms = round((time.perf_counter() - start) * 1000, 3)
    detected = set(counts)
    missing = sorted(case.expected_entities - detected)
    forbidden_hits = sorted(case.forbidden_entities & detected)
    expected_recall = _safe_ratio(len(case.expected_entities - set(missing)), len(case.expected_entities))
    forbidden_precision = _safe_ratio(len(case.forbidden_entities - set(forbidden_hits)), len(case.forbidden_entities))
    count_accuracy = _count_accuracy(counts, case.expected_counts)
    relation_hits = case.expected_relations & set(triples)
    relation_recall = _safe_ratio(len(relation_hits), len(case.expected_relations))
    passed = (
        expected_recall >= min_expected_recall
        and forbidden_precision >= min_forbidden_precision
        and count_accuracy >= min_count_accuracy
        and relation_recall >= min_relation_recall
    )
    return EntityBenchmarkResult(
        case_id=case.id,
        algorithm=algorithm,
        detected_entities=sorted(detected),
        missing_entities=missing,
        forbidden_hits=forbidden_hits,
        expected_recall=expected_recall,
        forbidden_precision=forbidden_precision,
        count_accuracy=count_accuracy,
        relation_recall=relation_recall,
        latency_ms=latency_ms,
        passed=passed,
    )


def summarize_results(results: Sequence[EntityBenchmarkResult]) -> list[EntityAlgorithmSummary]:
    by_algorithm: dict[str, list[EntityBenchmarkResult]] = {}
    for result in results:
        by_algorithm.setdefault(result.algorithm, []).append(result)
    summaries = []
    for algorithm, items in sorted(by_algorithm.items()):
        cases = len(items)
        pass_rate = sum(1 for item in items if item.passed) / cases
        avg_expected = sum(item.expected_recall for item in items) / cases
        avg_forbidden = sum(item.forbidden_precision for item in items) / cases
        avg_count = sum(item.count_accuracy for item in items) / cases
        avg_relation = sum(item.relation_recall for item in items) / cases
        avg_latency = sum(item.latency_ms for item in items) / cases
        final_score = (
            pass_rate * 0.35
            + avg_expected * 0.2
            + avg_forbidden * 0.15
            + avg_count * 0.15
            + avg_relation * 0.15
        )
        summaries.append(
            EntityAlgorithmSummary(
                algorithm=algorithm,
                cases=cases,
                pass_rate=round(pass_rate, 4),
                avg_expected_recall=round(avg_expected, 4),
                avg_forbidden_precision=round(avg_forbidden, 4),
                avg_count_accuracy=round(avg_count, 4),
                avg_relation_recall=round(avg_relation, 4),
                avg_latency_ms=round(avg_latency, 3),
                final_score=round(final_score, 4),
            )
        )
    summaries.sort(key=lambda item: (-item.final_score, item.avg_latency_ms, item.algorithm))
    return summaries


def run_entity_benchmark(
    cases: Iterable[EntityBenchmarkCase] | None = None,
    algorithms: Iterable[str] | None = None,
    out_dir: Path | None = None,
) -> EntityBenchmarkReport:
    selected_cases = list(cases or default_entity_resolution_suite())
    selected_algorithms = list(algorithms or ALGORITHMS)
    unknown = [name for name in selected_algorithms if name not in ALGORITHMS]
    if unknown:
        raise ValueError(f"Unknown entity benchmark algorithms: {unknown}")
    results = [
        evaluate_entity_case(case, name, ALGORITHMS[name])
        for case in selected_cases
        for name in selected_algorithms
    ]
    summaries = summarize_results(results)
    report = EntityBenchmarkReport(
        best_algorithm=summaries[0].algorithm if summaries else "",
        acceptance={
            "min_expected_recall": 1.0,
            "min_forbidden_precision": 1.0,
            "min_count_accuracy": 0.8,
            "min_relation_recall": 0.5,
        },
        summaries=summaries,
        results=results,
    )
    if out_dir:
        export_entity_benchmark_report(report, out_dir)
    return report


def export_entity_benchmark_report(report: EntityBenchmarkReport, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "entity_benchmark_report.json").write_text(
        json.dumps(asdict(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        "# 实体识别算法验收 Benchmark\n\n",
        f"- 最优算法：`{report.best_algorithm}`\n\n",
        "## 汇总\n\n",
        "| 算法 | 通过率 | 期望召回 | 禁止项精度 | 计数准确 | 关系召回 | 延迟ms | 总分 |\n",
        "|---|---:|---:|---:|---:|---:|---:|---:|\n",
    ]
    for summary in report.summaries:
        lines.append(
            f"| {summary.algorithm} | {summary.pass_rate:.2f} | "
            f"{summary.avg_expected_recall:.2f} | {summary.avg_forbidden_precision:.2f} | "
            f"{summary.avg_count_accuracy:.2f} | {summary.avg_relation_recall:.2f} | "
            f"{summary.avg_latency_ms:.1f} | {summary.final_score:.2f} |\n"
        )
    lines.extend(["\n## 逐例结果\n\n"])
    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        lines.append(
            f"- `{status}` `{result.algorithm}` / `{result.case_id}`: "
            f"missing={result.missing_entities}, forbidden={result.forbidden_hits}, "
            f"count={result.count_accuracy:.2f}, relation={result.relation_recall:.2f}\n"
        )
    (out_dir / "entity_benchmark_report.md").write_text("".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run entity resolution benchmark.")
    parser.add_argument("--out-dir", type=Path, default=Path("entity_benchmark_output"))
    parser.add_argument("--algorithm", action="append", choices=sorted(ALGORITHMS))
    args = parser.parse_args()
    report = run_entity_benchmark(algorithms=args.algorithm, out_dir=args.out_dir)
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

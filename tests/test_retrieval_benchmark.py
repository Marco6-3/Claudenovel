from __future__ import annotations

from pathlib import Path

from novel_parser.retrieval_benchmark import (
    ALGORITHMS,
    AlgorithmSummary,
    RetrievalCase,
    RetrievalIndex,
    _evaluate_case,
    _select_best_algorithm,
    adaptive_evidence_base_retriever,
    default_chuyun_xiaoyuqi_suite,
    embedding_retriever,
    export_benchmark_report,
    keyword_retriever,
    relationship_template_retriever,
)
from novel_parser.structure import parse_chapters


def _sample_chapters():
    text = """
第1章 修仙归来

楚云重生归来，想弥补前世萧雨琪自尽造成的心魔遗憾。他收到萧雨琪短信，决定守住婚约。

第2章 校园闲事

胖子和同学在教室闲聊，和主线感情没有直接关系。

第3章 未完成的婚礼

萧雨琪寿元将尽，蕴龙骨迟迟没有重生。楚云陪她完成婚礼，承诺绝不放手。

第4章 琪皇离去

萧雨琪恢复琪皇记忆。她看着楚凡哭喊，却为了三皇责任和界魔浩劫离去，楚云心神俱创。

第5章 浩劫和解

楚云归来，琪皇在他面前哭着承认自己还是雨琪。楚云说放得下天下，却放不下她。
"""
    return parse_chapters(text)


def test_default_suite_covers_full_relationship_arc() -> None:
    suite = default_chuyun_xiaoyuqi_suite()

    assert {case.id for case in suite} >= {
        "origin_promise",
        "life_crisis",
        "qihuang_identity",
        "separation_coldwar",
        "full_arc",
    }
    full_arc = next(case for case in suite if case.id == "full_arc")
    assert {1, 7, 1521, 2483, 2900, 3015}.issubset(full_arc.must_chapters)


def test_keyword_retriever_scores_expected_chapters() -> None:
    index = RetrievalIndex(_sample_chapters())
    case = RetrievalCase(
        id="sample",
        description="sample",
        query="楚云萧雨琪前世婚约蕴龙骨琪皇离去和解",
        expected_chapters={1, 3, 4, 5},
        must_chapters={1, 4},
        min_expected_recall=0.5,
        min_must_recall=1.0,
        min_precision=0.5,
    )

    result = _evaluate_case(index, case, "keyword", keyword_retriever, top_k=4)

    assert result.must_recall == 1.0
    assert result.expected_recall >= 0.5
    assert result.passed is True


def test_relationship_template_adds_phase_coverage() -> None:
    index = RetrievalIndex(_sample_chapters())
    case = RetrievalCase(
        id="sample_full_arc",
        description="sample full arc",
        query="楚云萧雨琪全书感情线 前世婚约 蕴龙骨 琪皇离去 和解",
        expected_chapters={1, 3, 4, 5},
        must_chapters={1, 3, 4, 5},
        min_expected_recall=0.75,
        min_must_recall=0.75,
        min_precision=0.75,
    )

    result = _evaluate_case(index, case, "relationship_template", relationship_template_retriever, top_k=6)

    assert result.must_recall >= 0.75
    assert {1, 3, 4}.issubset(set(result.retrieved_chapters))


def test_embedding_retriever_uses_local_vectors() -> None:
    index = RetrievalIndex(_sample_chapters())
    case = RetrievalCase(
        id="sample_embedding",
        description="sample embedding",
        query="萧雨琪恢复琪皇记忆离开孩子楚凡",
        expected_chapters={4, 5},
        must_chapters={4},
        min_expected_recall=0.5,
        min_must_recall=1.0,
        min_precision=0.25,
    )

    result = _evaluate_case(index, case, "embedding", embedding_retriever, top_k=4)

    assert index.embedding_build_ms > 0
    assert 4 in result.retrieved_chapters


def test_local_embedding_cache_can_be_reused(tmp_path: Path) -> None:
    cache_path = tmp_path / "embedding_cache.npz"
    first = RetrievalIndex(_sample_chapters(), embedding_cache_path=cache_path)
    first.ensure_embeddings()

    second = RetrievalIndex(_sample_chapters(), embedding_cache_path=cache_path)
    second.ensure_embeddings()

    assert cache_path.exists()
    assert first._embedding_vectors is not None
    assert second._embedding_vectors is not None
    assert first._embedding_vectors.shape == second._embedding_vectors.shape


def test_adaptive_evidence_base_returns_timeline_coverage() -> None:
    index = RetrievalIndex(_sample_chapters())
    case = RetrievalCase(
        id="sample_full_generic",
        description="sample full generic",
        query="楚云萧雨琪全书感情线 前世婚约 琪皇离去 和解",
        expected_chapters={1, 4, 5},
        must_chapters={1, 4},
        min_expected_recall=0.5,
        min_must_recall=0.5,
        min_precision=0.25,
    )

    result = _evaluate_case(index, case, "adaptive_evidence_base", adaptive_evidence_base_retriever, top_k=4)

    assert result.expected_recall >= 0.5
    assert len(result.retrieved_chapters) >= 3


def test_export_benchmark_report_writes_json_and_markdown(tmp_path: Path) -> None:
    index = RetrievalIndex(_sample_chapters())
    case = RetrievalCase(
        id="sample",
        description="sample",
        query="楚云萧雨琪琪皇",
        expected_chapters={1, 4, 5},
        must_chapters={4},
        min_expected_recall=0.3,
        min_must_recall=1.0,
        min_precision=0.3,
    )
    results = [
        _evaluate_case(index, case, "keyword", ALGORITHMS["keyword"], top_k=3),
    ]
    from novel_parser.retrieval_benchmark import BenchmarkReport, _summarize

    summaries = _summarize(results)
    report = BenchmarkReport(
        novel_path="sample.txt",
        chapter_count=len(index.chapters),
        chunk_count=len(index.chunks),
        top_k=3,
        build_ms=index.build_ms,
        best_algorithm=summaries[0].algorithm,
        acceptance={"suite_pass_rate_min": 0.8},
        summaries=summaries,
        results=results,
    )

    export_benchmark_report(report, tmp_path)

    assert (tmp_path / "retrieval_benchmark_report.json").exists()
    md = (tmp_path / "retrieval_benchmark_report.md").read_text(encoding="utf-8")
    assert "检索算法验收 Benchmark" in md


def test_select_best_algorithm_requires_acceptance_floor() -> None:
    fast_but_not_accepted = AlgorithmSummary(
        algorithm="fast",
        cases=7,
        pass_rate=0.70,
        avg_expected_recall=0.80,
        avg_must_recall=0.95,
        avg_precision=0.30,
        avg_f1=0.40,
        avg_latency_ms=100.0,
        efficiency_score=1.0,
        final_score=0.95,
    )
    accepted = AlgorithmSummary(
        algorithm="accepted",
        cases=7,
        pass_rate=0.90,
        avg_expected_recall=0.70,
        avg_must_recall=0.90,
        avg_precision=0.20,
        avg_f1=0.35,
        avg_latency_ms=500.0,
        efficiency_score=0.2,
        final_score=0.80,
    )

    assert _select_best_algorithm([fast_but_not_accepted, accepted]) == "accepted"

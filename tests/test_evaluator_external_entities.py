from __future__ import annotations

from novel_parser import evaluator


def test_external_chapter_uses_current_novel_entity_names() -> None:
    chapter = evaluator.build_external_chapter(
        "凌默看向陈锋。陈锋点头，凌默转身下水。",
        title="测试章",
    )

    metrics = evaluator.compute_metrics(chapter, ["凌默", "陈锋", "秦思妍"])

    assert metrics.entity_diversity == 2
    assert metrics.named_entity_ratio > 0
    assert metrics.info_density > 0

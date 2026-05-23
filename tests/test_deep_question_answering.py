from __future__ import annotations

import json
from pathlib import Path

from novel_parser.deep_question_answering import answer_question, compare_context_modes, plan_question


def _sample_novel(path: Path) -> Path:
    text = """
第1章 修仙归来

楚云重生归来，想弥补前世萧雨琪自尽造成的心魔遗憾。他收到萧雨琪短信，决定守住婚约。

第2章 未完成的婚礼

萧雨琪寿元将尽，蕴龙骨迟迟没有重生。楚云陪她完成婚礼，承诺绝不放手。

第3章 琪皇离去

萧雨琪恢复琪皇记忆。她看着楚凡哭喊，却为了三皇责任和界魔浩劫离去，楚云心神俱创。

第4章 冷战相见

楚云再次见到琪皇，她却像外人一样沉默不认。楚凡喊着母亲，琪皇没有立刻回应。

第5章 浩劫和解

楚云归来，琪皇在他面前哭着承认自己还是雨琪。楚云说放得下天下，却放不下她，最终二人回家。
"""
    path.write_text(text.strip(), encoding="utf-8")
    return path


def test_plan_question_decomposes_abandonment_dispute() -> None:
    plan = plan_question(
        "萧雨琪是否抛弃了楚云和楚凡？",
        focus_entities=["楚云", "萧雨琪"],
    )

    assert plan.category == "character_dispute"
    assert "embedding_hybrid_rrf" in plan.algorithms
    assert "relationship_template" in plan.algorithms
    assert {need.id for need in plan.needs} >= {"leave_reason", "child_impact", "counter"}


def test_answer_question_exports_evidence_and_prompt(tmp_path: Path) -> None:
    novel_path = _sample_novel(tmp_path / "sample.txt")
    out_dir = tmp_path / "qa"

    artifacts = answer_question(
        txt_path=novel_path,
        question="萧雨琪是否抛弃了楚云和楚凡？",
        out_dir=out_dir,
        focus_entities=["楚云", "萧雨琪"],
        algorithms=["embedding_hybrid_rrf"],
        top_k=5,
        evidence_per_need=3,
        embedding_mode="local",
    )

    assert artifacts.question_plan.category == "character_dispute"
    assert artifacts.evidence
    assert any(record.id.startswith("CH") and "-P" in record.id for record in artifacts.evidence)
    assert "## 固定输出结构" in artifacts.prompt
    assert "反方证据" in artifacts.local_report

    assert (out_dir / "question_plan.json").exists()
    assert (out_dir / "evidence_matrix.json").exists()
    assert (out_dir / "coverage_audit.json").exists()
    assert (out_dir / "reading_context_manifest.json").exists()
    assert (out_dir / "answer_prompt.md").exists()
    assert (out_dir / "local_answer_report.md").exists()

    evidence = json.loads((out_dir / "evidence_matrix.json").read_text(encoding="utf-8"))
    assert evidence[0]["id"].startswith("CH")


def test_identity_question_requires_counter_evidence_slot() -> None:
    plan = plan_question("后期琪皇是否也认为是萧雨琪？", focus_entities=["萧雨琪", "琪皇"])

    assert plan.category == "identity"
    assert any(need.stance == "counter" for need in plan.needs)


def test_acceptance_questions_map_to_specific_categories() -> None:
    cases = {
        "琪皇是否就是萧雨琪？": "identity",
        "萧雨琪是否抛弃了楚云和楚凡？": "character_dispute",
        "最后萧雨琪没有跟楚云走是否合理？": "ending_rationality",
        "两人冷战式不相认是否有前文铺垫？": "coldwar",
    }

    for question, expected_category in cases.items():
        assert plan_question(question, focus_entities=["楚云", "萧雨琪"]).category == expected_category


def test_large_context_adds_reading_pack(tmp_path: Path) -> None:
    novel_path = _sample_novel(tmp_path / "sample.txt")
    out_dir = tmp_path / "qa_large"

    artifacts = answer_question(
        txt_path=novel_path,
        question="两人冷战式不相认是否有前文铺垫？",
        out_dir=out_dir,
        focus_entities=["楚云", "萧雨琪"],
        algorithms=["embedding_hybrid_rrf"],
        top_k=5,
        evidence_per_need=2,
        large_context=True,
        context_budget_chars=8000,
        embedding_mode="local",
    )

    assert artifacts.reading_context
    assert artifacts.reading_context_manifest["enabled"] is True
    assert "## 大上下文阅读包" in artifacts.prompt
    assert (out_dir / "reading_context_pack.md").exists()


def test_organized_output_separates_report_and_data(tmp_path: Path) -> None:
    novel_path = _sample_novel(tmp_path / "sample.txt")
    out_dir = tmp_path / "task"

    answer_question(
        txt_path=novel_path,
        question="萧雨琪是否抛弃了楚云和楚凡？",
        out_dir=out_dir,
        focus_entities=["楚云", "萧雨琪"],
        algorithms=["embedding_hybrid_rrf"],
        top_k=5,
        evidence_per_need=2,
        organized_output=True,
        embedding_mode="local",
    )

    assert (out_dir / "report.md").exists()
    assert (out_dir / "data" / "evidence_matrix.json").exists()
    assert (out_dir / "data" / "answer_prompt.md").exists()
    assert not (out_dir / "evidence_matrix.json").exists()


def test_compare_context_modes_exports_ab_report(tmp_path: Path) -> None:
    novel_path = _sample_novel(tmp_path / "sample.txt")
    out_dir = tmp_path / "compare"

    comparison = compare_context_modes(
        txt_path=novel_path,
        out_dir=out_dir,
        questions=["萧雨琪是否抛弃了楚云和楚凡？"],
        focus_entities=["楚云", "萧雨琪"],
        algorithms=["embedding_hybrid_rrf"],
        top_k=5,
        evidence_per_need=2,
        context_budget_chars=8000,
        embedding_mode="local",
    )

    assert comparison.winners["萧雨琪是否抛弃了楚云和楚凡？"] in {"matrix_only", "large_context"}
    assert len(comparison.metrics) == 2
    assert (out_dir / "comparison_summary.json").exists()
    assert (out_dir / "comparison_report.md").exists()
    assert (out_dir / "llm_judge_prompt.md").exists()


def test_compare_context_modes_organized_output(tmp_path: Path) -> None:
    novel_path = _sample_novel(tmp_path / "sample.txt")
    out_dir = tmp_path / "compare_task"

    compare_context_modes(
        txt_path=novel_path,
        out_dir=out_dir,
        questions=["琪皇是否就是萧雨琪？"],
        focus_entities=["萧雨琪", "琪皇"],
        algorithms=["embedding_hybrid_rrf"],
        top_k=5,
        evidence_per_need=2,
        context_budget_chars=8000,
        organized_output=True,
        embedding_mode="local",
    )

    assert (out_dir / "report.md").exists()
    assert (out_dir / "data" / "comparison_summary.json").exists()
    assert (out_dir / "data" / "large_context").exists()

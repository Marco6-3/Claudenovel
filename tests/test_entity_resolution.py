from __future__ import annotations

import json
from collections import Counter

import pytest

from novel_parser import entity, relation
from novel_parser.context_builder import collect_evidence
from novel_parser.entity_resolver import count_entity_mentions, merge_alias_maps
from novel_parser.pipeline import run_pipeline
from novel_parser.entity_benchmark import run_entity_benchmark
from novel_parser.entity_resolver import ordered_unique_entities
from novel_parser.structure import parse_chapters


def _sample_aliases():
    return {
        "陈汉升": ["小陈", "陈部长"],
        "萧容鱼": ["小鱼儿", "萧主任"],
        "沈幼楚": ["沈憨憨"],
    }


def test_alias_matcher_prefers_full_names_over_prefix_fragments() -> None:
    aliases = _sample_aliases()
    text = "陈汉升给小鱼儿打电话，萧容鱼听出小陈在撒谎，沈憨憨沉默。"

    assert ordered_unique_entities(text, aliases) == ["陈汉升", "萧容鱼", "沈幼楚"]
    assert count_entity_mentions(text, aliases) == {
        "陈汉升": 2,
        "萧容鱼": 2,
        "沈幼楚": 1,
    }


def test_explicit_alias_ownership_overrides_discovered_canonical() -> None:
    merged = merge_alias_maps({"小丁": []}, {"丁一": ["小丁"]})

    assert "小丁" not in merged
    assert count_entity_mentions("小丁给丁一打电话。", merged) == {"丁一": 2}


def test_discover_entity_aliases_removes_prefix_fragments() -> None:
    chapters = parse_chapters(
        """
第1章 见面

陈汉升看着萧容鱼，萧容鱼又看着陈汉升。沈幼楚站在图书馆门口。

第2章 电话

陈汉升给萧容鱼打电话，沈幼楚给陈汉升送伞。
"""
    )

    aliases = entity.discover_entity_aliases(chapters, include_builtin_present=False)

    assert "陈汉升" in aliases
    assert "萧容鱼" in aliases
    assert "沈幼楚" in aliases
    assert "陈汉" not in aliases
    assert "萧容" not in aliases
    assert "沈幼" not in aliases


def test_seeded_canonical_removes_longer_action_suffix_candidates() -> None:
    chapters = parse_chapters(
        """
第1章 说话

陈汉升说今天回家。陈汉升笑着看向萧容鱼。陈汉升问沈幼楚要不要伞。
"""
    )

    aliases = entity.discover_entity_aliases(
        chapters,
        include_builtin_present=False,
        seed_aliases={"陈汉升": [], "萧容鱼": [], "沈幼楚": []},
    )

    assert "陈汉升" in aliases
    assert not any(name.startswith("陈汉升") and name != "陈汉升" for name in aliases)


def test_entity_stats_counts_aliases_under_canonical_names() -> None:
    chapters = parse_chapters(
        """
第1章 电话

陈部长给小鱼儿打电话，小陈又给沈憨憨发消息。萧主任没有回复陈汉升。
"""
    )

    stats = entity.compute_entity_stats(chapters, aliases=_sample_aliases())

    assert stats.occurrences == Counter({"陈汉升": 3, "萧容鱼": 2, "沈幼楚": 1})
    assert stats.chapter_span["陈汉升"] == [1, 1, 1]


def test_relation_extraction_uses_aliases() -> None:
    chapters = parse_chapters(
        """
第1章 电话

陈部长给小鱼儿打电话，小陈又给沈憨憨发消息。
"""
    )

    triples = relation.extract_relations_rule(chapters, aliases=_sample_aliases())

    assert ("陈汉升", "给予", "萧容鱼") in triples
    assert ("陈汉升", "联系", "沈幼楚") in triples


def test_jieba_relation_extraction_uses_aliases() -> None:
    pytest.importorskip("jieba")
    chapters = parse_chapters(
        """
第1章 电话

陈部长喜欢小鱼儿，小陈给沈憨憨发消息。
"""
    )

    triples = relation.extract_relations_jieba(chapters, aliases=_sample_aliases())

    assert ("陈汉升", "喜欢", "萧容鱼") in triples


def test_context_builder_scores_alias_hits_as_canonical_entities() -> None:
    chapters = parse_chapters(
        """
第1章 别名场景

小陈给沈憨憨发消息，但是这一段没有写出两人的全名。
"""
    )

    evidence = collect_evidence(
        chapters,
        query="陈汉升和沈幼楚联系",
        focus_entities=["陈汉升", "沈幼楚"],
        entity_aliases=_sample_aliases(),
    )

    assert evidence
    assert evidence[0].matched_terms[:2] == ["陈汉升", "沈幼楚"]


def test_common_workflow_preserves_raw_text_but_matches_builtin_aliases(tmp_path) -> None:
    novel_path = tmp_path / "sample.txt"
    novel_path.write_text(
        """
第1章 回家

陈默回到学校，秦思妍看着陈默沉默。
""".strip(),
        encoding="utf-8",
    )
    out_dir = tmp_path / "out"

    run_pipeline(
        novel_path,
        out_dir,
        common_workflow=True,
        context_query="陳默和秦思妍关系",
        focus_entities=["陳默", "秦思妍"],
        apply_aliases=True,
    )

    source = (out_dir / "llm_source_pack_detailed.md").read_text(encoding="utf-8")
    evidence = json.loads((out_dir / "review_evidence_pack.json").read_text(encoding="utf-8"))
    assert "陈默回到学校" in source
    assert evidence["evidence"]
    assert "陳默" in evidence["evidence"][0]["matched_terms"]


def test_entity_benchmark_converges_to_seeded_alias() -> None:
    report = run_entity_benchmark()

    assert report.best_algorithm == "seeded_alias"
    seeded = next(summary for summary in report.summaries if summary.algorithm == "seeded_alias")
    legacy = next(summary for summary in report.summaries if summary.algorithm == "legacy_prefix")
    assert seeded.pass_rate == 1.0
    assert seeded.final_score > legacy.final_score

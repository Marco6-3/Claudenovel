"""Main pipeline orchestrator."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from . import common_workflows, context_builder, entity, evaluator, llm_client, normalizer, relation, sentiment, structure


def run_pipeline(
    txt_path: Path,
    out_dir: Path,
    use_jieba: bool = False,
    jieba_chapter_limit: Optional[int] = None,
    use_jieba_cache: bool = False,
    evaluate_chapter: Optional[int] = None,
    evaluate_file: Optional[Path] = None,
    llm_report: bool = False,
    llm_max_chars: int = 12000,
    output_name: str = "input_chapter_evaluation.md",
    build_context: bool = False,
    context_query: str = "",
    focus_entities: Optional[List[str]] = None,
    context_max_items: int = 80,
    context_excerpt_chars: int = 900,
    context_max_chars: int = 80000,
    common_workflow: bool = False,
    source_start: Optional[int] = None,
    source_end: Optional[int] = None,
    source_max_chars: int = 0,
    apply_aliases: bool = True,
) -> dict:
    """Run the full enhanced analysis pipeline."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Read & normalize
    raw_text = normalizer.read_text(txt_path)
    raw_structure_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    text = normalizer.normalize_text(raw_text, apply_aliases=apply_aliases)

    # 2. Structural parsing
    raw_chapters: List[structure.Chapter] = structure.parse_chapters(raw_structure_text)
    chapters: List[structure.Chapter] = structure.parse_chapters(text)
    aliases = entity.discover_entity_aliases(chapters, include_builtin_present=apply_aliases)

    # 3. Entity stats (with aliases merged + scene-level cooccurrence)
    stats = entity.compute_entity_stats(chapters, aliases=aliases)
    entity.export_entity_stats(stats, out_dir)

    # 4. Relation triples
    relation.export_relations(
        chapters,
        out_dir,
        use_jieba=use_jieba,
        jieba_chapter_limit=jieba_chapter_limit,
        jieba_cache_path=(out_dir / "jieba_relation_cache.json") if use_jieba_cache else None,
        aliases=aliases,
    )

    # 5. Sentiment arc
    sent = sentiment.analyze_sentiment(chapters)
    sentiment.export_sentiment(sent, out_dir)

    # 6. Enhanced TOC + briefs
    toc_lines = [f"# 《{txt_path.stem}》卷章目录（增强版）\n"]
    briefs = []
    current_vol = None
    for ch in chapters:
        if ch.volume != current_vol:
            current_vol = ch.volume
            toc_lines.append(f"\n## {current_vol}\n")
        scene_locs = ", ".join(
            s.location_hint for s in ch.scenes if s.location_hint
        ) or "—"
        toc_lines.append(
            f"- {ch.global_index:03d}. {ch.title}（{ch.chars}字，"
            f"{len(ch.scenes)}场景，{len(ch.dialogues)}对话）"
        )
        briefs.append({
            "global_index": ch.global_index,
            "volume": ch.volume,
            "title": ch.title,
            "chars": ch.chars,
            "scene_count": len(ch.scenes),
            "dialogue_count": len(ch.dialogues),
            "scene_locations": [s.location_hint for s in ch.scenes],
            "first": ch.first,
            "last": ch.last,
        })

    (out_dir / "enhanced_toc.md").write_text(
        "\n".join(toc_lines), encoding="utf-8"
    )
    (out_dir / "enhanced_briefs.json").write_text(
        json.dumps(briefs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    evaluation_output = None
    llm_status = "not_requested"
    context_output = None
    common_output = None
    if evaluate_chapter is not None:
        if evaluate_chapter < 1 or evaluate_chapter > len(chapters):
            raise ValueError(
                f"evaluate_chapter must be between 1 and {len(chapters)}, got {evaluate_chapter}"
            )
        target = chapters[evaluate_chapter - 1]
        evaluation_names = list(aliases)
        baseline = evaluator.build_baseline(chapters, evaluation_names)
        metrics = [evaluator.compute_metrics(ch, evaluation_names) for ch in chapters]
        report = evaluator.evaluate_chapter(
            target,
            baseline,
            chapters,
            metrics,
            entity_names=evaluation_names,
        )
        evaluation_output = f"chapter_{target.global_index:03d}_evaluation.md"
        evaluator.export_evaluation(report, out_dir / evaluation_output, target.title)

    if evaluate_file is not None:
        raw_input = normalizer.read_text(evaluate_file)
        input_text = normalizer.normalize_text(raw_input)
        title = evaluate_file.stem
        target = evaluator.build_external_chapter(input_text, title=title)
        evaluation_names = list(aliases)
        baseline = evaluator.build_baseline(chapters, evaluation_names)
        metrics = [evaluator.compute_metrics(ch, evaluation_names) for ch in chapters]
        report = evaluator.evaluate_chapter(
            target,
            baseline,
            chapters,
            metrics,
            entity_names=evaluation_names,
        )
        llm_section = None
        llm_error = None
        llm_truncated = False
        llm_model = None
        if llm_report:
            try:
                llm_section, llm_truncated, llm_model = llm_client.generate_editorial_report(
                    report,
                    target.body,
                    target.title,
                    max_chars=llm_max_chars,
                )
                llm_status = "ok"
            except Exception as exc:
                llm_error = str(exc)
                llm_status = "error"
        out_name = output_name or "input_chapter_evaluation.md"
        evaluation_output = out_name
        evaluator.export_evaluation(
            report,
            out_dir / out_name,
            target.title,
            llm_section=llm_section,
            llm_error=llm_error,
            llm_truncated=llm_truncated,
            llm_model=llm_model,
        )

    if build_context:
        context_output = context_builder.export_context_pack(
            chapters,
            out_dir,
            query=context_query,
            focus_entities=focus_entities or [],
            max_items=context_max_items,
            excerpt_chars=context_excerpt_chars,
            max_context_chars=context_max_chars,
        )

    if common_workflow:
        common_output = common_workflows.export_common_workflows(
            raw_chapters,
            out_dir,
            query=context_query,
            focus_entities=focus_entities or [],
            source_start=source_start,
            source_end=source_end,
            source_max_chars=source_max_chars,
            evidence_max_items=max(context_max_items, 120),
            evidence_excerpt_chars=max(context_excerpt_chars, 1200),
        )

    return {
        "file": txt_path.name,
        "chars": len(text),
        "chapters": len(chapters),
        "total_scenes": sum(len(c.scenes) for c in chapters),
        "total_dialogues": sum(len(c.dialogues) for c in chapters),
        "jieba_enabled": use_jieba,
        "jieba_chapter_limit": jieba_chapter_limit,
        "jieba_cache_enabled": use_jieba_cache,
        "evaluation_output": evaluation_output,
        "context_output": context_output,
        "common_output": common_output,
        "llm_report_requested": llm_report,
        "llm_status": llm_status,
        "outputs": [p.name for p in out_dir.iterdir()],
    }

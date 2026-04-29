"""Hybrid analyzer: structured analysis first, then LLM for high-level judgment."""
from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import llm_client
from .entity import compute_entity_stats, EntityStats
from .evaluator import compute_metrics, build_baseline, evaluate_chapter, BaselineStats, ChapterMetrics
from .normalizer import ENTITY_ALIASES
from .relation import extract_relations_rule
from .sentiment import analyze_sentiment, ChapterSentiment
from .structure import Chapter


@dataclass
class StructuredContext:
    """All structured analysis results for a set of chapters."""
    entity_stats: EntityStats
    rule_relations: List[Tuple[str, str, str]]
    sentiments: List[ChapterSentiment]
    baseline: BaselineStats
    metrics: List[ChapterMetrics]
    chapter_briefs: List[Dict[str, Any]]


@dataclass
class HybridBatchResult:
    """Result from one batch of hybrid LLM analysis."""
    batch_index: int
    chapter_indices: List[int]
    raw_response: str
    parsed: Dict[str, Any]
    model: str
    elapsed_seconds: float
    input_chars: int


@dataclass
class HybridSummary:
    """Aggregated summary from all hybrid-analysis batches."""
    characters: List[Dict[str, Any]]
    relationships: List[Dict[str, str]]
    sentiment_per_chapter: List[Dict[str, Any]]
    plot_summaries: List[Dict[str, str]]
    quality_scores: List[Dict[str, Any]]
    structured_context: StructuredContext
    batch_results: List[HybridBatchResult]
    total_input_chars: int
    total_elapsed: float


CANONICAL_NAMES = list(ENTITY_ALIASES.keys())


def build_structured_context(chapters: List[Chapter]) -> StructuredContext:
    """Run all structured analysis modules on the chapters."""
    stats = compute_entity_stats(chapters)
    relations = extract_relations_rule(chapters)
    sentiments = analyze_sentiment(chapters)
    baseline = build_baseline(chapters)
    metrics = [compute_metrics(ch) for ch in chapters]

    chapter_briefs = []
    for ch, m in zip(chapters, metrics):
        chapter_briefs.append({
            "index": ch.global_index,
            "title": ch.title,
            "chars": ch.chars,
            "scenes": len(ch.scenes),
            "dialogues": len(ch.dialogues),
            "plot_score": None,  # will be filled by evaluate_chapter if needed
            "entities_present": [n for n in CANONICAL_NAMES if n in ch.body],
            "sentiment": sentiments[ch.global_index - 1].overall if ch.global_index - 1 < len(sentiments) else {},
        })

    return StructuredContext(
        entity_stats=stats,
        rule_relations=relations,
        sentiments=sentiments,
        baseline=baseline,
        metrics=metrics,
        chapter_briefs=chapter_briefs,
    )


def _format_structured_summary(ctx: StructuredContext, chapter_indices: List[int]) -> str:
    """Format structured data relevant to the target chapters as a compact text block."""
    lines = ["## 结构化分析数据（预处理结果）\n"]

    # Entity stats for the relevant chapters
    lines.append("### 出场人物\n")
    top_entities = ctx.entity_stats.occurrences.most_common(20)
    for name, count in top_entities:
        span = ctx.entity_stats.chapter_span.get(name, [0, 0, 0])
        lines.append(f"- {name}：出现 {count} 次，跨越第{span[0]}-{span[1]}章（共{span[2]}章）")

    # Scene co-occurrence
    lines.append("\n### 场景共现（前15对）\n")
    for (a, b), n in ctx.entity_stats.scene_cooccurrence.most_common(15):
        lines.append(f"- {a} & {b}：{n} 次同场景")

    # Relations
    lines.append("\n### 关系三元组（规则抽取）\n")
    rel_counter = Counter(ctx.rule_relations)
    for (s, r, o), count in rel_counter.most_common(30):
        lines.append(f"- ({s}, {r}, {o}) × {count}")

    # Sentiment for target chapters
    lines.append("\n### 章节情感（词典打分）\n")
    lines.append("| 章 | 正面 | 负面 | 紧张 | 净值 |")
    lines.append("|---|---|---|---|---|")
    for idx in chapter_indices:
        if 0 < idx <= len(ctx.sentiments):
            s = ctx.sentiments[idx - 1]
            o = s.overall
            lines.append(f"| {idx} | {o.get('positive', 0):.2f} | {o.get('negative', 0):.2f} | {o.get('tension', 0):.2f} | {o.get('net', 0):+.2f} |")

    # Metrics for target chapters
    lines.append("\n### 章节结构指标\n")
    lines.append("| 章 | 字数 | 场景 | 对话比 | 冲突密度 | 悬念密度 | 词汇TTR |")
    lines.append("|---|---|---|---|---|---|---|")
    for idx in chapter_indices:
        if 0 < idx <= len(ctx.metrics):
            m = ctx.metrics[idx - 1]
            lines.append(f"| {idx} | {m.chars} | {m.scene_count} | {m.dialogue_ratio:.1%} | {m.conflict_density:.1f} | {m.suspense_density:.1f} | {m.word_ttr:.3f} |")

    return "\n".join(lines)


def build_hybrid_prompt(chapters: List[Chapter], ctx: StructuredContext, max_chars_per_chapter: int = 4000) -> str:
    """Build a prompt with structured data + chapter excerpts for hybrid analysis."""
    chapter_indices = [ch.global_index for ch in chapters]
    structured = _format_structured_summary(ctx, chapter_indices)

    lines = [
        "你是一名网络小说分析专家。以下提供了两种信息：\n",
        "1. **结构化预处理数据**：由程序自动提取的人物统计、关系三元组、情感打分、结构指标。",
        "2. **章节原文摘要**：每章的开头和结尾摘录。\n",
        "请基于以上两种信息进行综合分析，输出 JSON：\n",
        "```json",
        "{",
        '  "characters": [',
        '    {"name": "角色名", "role": "主角/配角/反派/路人", "description": "简要描述"}',
        "  ],",
        '  "relationships": [',
        '    {"subject": "人物A", "relation": "关系类型", "object": "人物B", "evidence": "依据（可引用结构化数据或原文）"}',
        "  ],",
        '  "sentiment_per_chapter": [',
        '    {"chapter_index": 1, "overall": "正面/负面/中性", "tension": "高/中/低", "key_emotion": "主要情感"}',
        "  ],",
        '  "plot_summaries": [',
        '    {"chapter_index": 1, "summary": "一句话剧情摘要"}',
        "  ],",
        '  "quality_scores": [',
        '    {"chapter_index": 1, "plot": 7, "prose": 6, "hook": 8, "comment": "简评"}',
        "  ]",
        "}",
        "```\n",
        "要求：",
        "1. 可以直接引用结构化数据中的统计结果。",
        "2. 角色名使用结构化数据中的规范名。",
        "3. 关系分析应结合规则抽取结果和原文判断。",
        "4. 质量评分范围 1-10，应参考结构化指标（冲突密度、对话比等）。",
        "5. 只输出 JSON，不要其他内容。\n",
        structured,
        "\n---\n",
        "## 章节原文摘要\n",
    ]

    for ch in chapters:
        body = ch.body
        # Shorter excerpt for hybrid since we already have structured data
        excerpt_len = min(max_chars_per_chapter, len(body))
        if excerpt_len < len(body):
            part = excerpt_len // 3
            excerpt = body[:part] + "\n...\n" + body[-part:]
        else:
            excerpt = body
        lines.append(f"### 第{ch.global_index}章《{ch.title}》（{ch.chars}字）")
        lines.append(excerpt[:max_chars_per_chapter])
        lines.append("")

    return "\n".join(lines)


def _parse_llm_json(text: str) -> Dict[str, Any]:
    """Try to extract and parse JSON from LLM response."""
    import re
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {"_parse_error": True, "_raw": text[:2000]}


def analyze_batch_hybrid(
    chapters: List[Chapter],
    ctx: StructuredContext,
    batch_index: int = 0,
    max_chars_per_chapter: int = 4000,
) -> HybridBatchResult:
    """Send a batch of chapters + structured data to LLM for hybrid analysis."""
    prompt = build_hybrid_prompt(chapters, ctx, max_chars_per_chapter)
    input_chars = len(prompt)

    messages = [
        {
            "role": "system",
            "content": (
                "你是专业的中文网络小说分析助手。你已收到结构化预处理数据，"
                "请结合这些数据和原文进行分析。输出纯 JSON。"
            ),
        },
        {"role": "user", "content": prompt},
    ]

    start = time.time()
    content, model = llm_client.call_hybrid_analysis(messages)
    elapsed = time.time() - start

    parsed = _parse_llm_json(content)

    return HybridBatchResult(
        batch_index=batch_index,
        chapter_indices=[ch.global_index for ch in chapters],
        raw_response=content,
        parsed=parsed,
        model=model,
        elapsed_seconds=round(elapsed, 1),
        input_chars=input_chars,
    )


def analyze_novel_hybrid(
    chapters: List[Chapter],
    ctx: Optional[StructuredContext] = None,
    batch_size: int = 5,
    max_chars_per_chapter: int = 4000,
    progress_callback=None,
) -> HybridSummary:
    """Analyze chapters in batches using hybrid (structured + LLM) approach."""
    if ctx is None:
        ctx = build_structured_context(chapters)

    batches: List[List[Chapter]] = []
    for i in range(0, len(chapters), batch_size):
        batches.append(chapters[i:i + batch_size])

    results: List[HybridBatchResult] = []
    total_input = 0
    total_elapsed = 0.0

    for idx, batch in enumerate(batches):
        if progress_callback:
            progress_callback(f"混合分析批次 {idx + 1}/{len(batches)}: 第{batch[0].global_index}-{batch[-1].global_index}章")
        result = analyze_batch_hybrid(batch, ctx, batch_index=idx, max_chars_per_chapter=max_chars_per_chapter)
        results.append(result)
        total_input += result.input_chars
        total_elapsed += result.elapsed_seconds

    summary = summarize_hybrid_results(results, ctx)
    summary.total_input_chars = total_input
    summary.total_elapsed = round(total_elapsed, 1)
    return summary


def summarize_hybrid_results(batch_results: List[HybridBatchResult], ctx: StructuredContext) -> HybridSummary:
    """Aggregate results from multiple batches into a unified summary."""
    all_characters: Dict[str, Dict] = {}
    all_relationships: List[Dict] = []
    all_sentiment: List[Dict] = []
    all_plots: List[Dict] = []
    all_quality: List[Dict] = []

    for br in batch_results:
        data = br.parsed
        if data.get("_parse_error"):
            continue
        for char in data.get("characters", []):
            name = char.get("name", "")
            if name and name not in all_characters:
                all_characters[name] = char
        all_relationships.extend(data.get("relationships", []))
        all_sentiment.extend(data.get("sentiment_per_chapter", []))
        all_plots.extend(data.get("plot_summaries", []))
        all_quality.extend(data.get("quality_scores", []))

    return HybridSummary(
        characters=list(all_characters.values()),
        relationships=all_relationships,
        sentiment_per_chapter=all_sentiment,
        plot_summaries=all_plots,
        quality_scores=all_quality,
        structured_context=ctx,
        batch_results=batch_results,
        total_input_chars=0,
        total_elapsed=0,
    )


def export_hybrid_results(summary: HybridSummary, out_dir) -> None:
    """Export hybrid analysis results to JSON."""
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)

    data = {
        "approach": "hybrid",
        "total_chapters": len(summary.plot_summaries),
        "characters": summary.characters,
        "relationships": summary.relationships,
        "sentiment_per_chapter": summary.sentiment_per_chapter,
        "plot_summaries": summary.plot_summaries,
        "quality_scores": summary.quality_scores,
        "structured_baseline": {
            "top_entities": [
                {"name": n, "count": c}
                for n, c in summary.structured_context.entity_stats.occurrences.most_common(20)
            ],
            "top_relations": [
                {"subject": s, "relation": r, "object": o}
                for (s, r, o), _ in Counter(summary.structured_context.rule_relations).most_common(30)
            ],
        },
        "cost": {
            "total_input_chars": summary.total_input_chars,
            "total_elapsed_seconds": summary.total_elapsed,
            "batch_count": len(summary.batch_results),
            "models_used": list({br.model for br in summary.batch_results}),
        },
        "batch_raw_responses": [
            {
                "batch_index": br.batch_index,
                "chapter_indices": br.chapter_indices,
                "model": br.model,
                "elapsed_seconds": br.elapsed_seconds,
                "input_chars": br.input_chars,
                "raw_response": br.raw_response,
            }
            for br in summary.batch_results
        ],
    }
    (out_dir / "hybrid_results.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def export_structured_baseline(ctx: StructuredContext, chapters: List[Chapter], out_dir) -> None:
    """Export the structured analysis baseline for comparison reference."""
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)

    rel_counter = Counter(ctx.rule_relations)
    data = {
        "entity_stats": {
            "total_unique": len(ctx.entity_stats.occurrences),
            "top_20": [
                {"name": n, "count": c, "chapters": ctx.entity_stats.chapter_span.get(n, [])}
                for n, c in ctx.entity_stats.occurrences.most_common(20)
            ],
            "scene_cooccurrence_top15": [
                {"pair": list(pair), "count": cnt}
                for pair, cnt in ctx.entity_stats.scene_cooccurrence.most_common(15)
            ],
            "dialogue_speakers": [
                {"name": n, "count": c}
                for n, c in ctx.entity_stats.dialogue_speakers.most_common(10)
            ],
        },
        "relations": {
            "total_triples": len(ctx.rule_relations),
            "unique_types": len(set(r for _, r, _ in ctx.rule_relations)),
            "top_30": [
                {"subject": s, "relation": r, "object": o, "count": c}
                for (s, r, o), c in rel_counter.most_common(30)
            ],
        },
        "sentiment": [
            {
                "chapter": s.idx,
                "title": s.title,
                "positive": s.overall.get("positive", 0),
                "negative": s.overall.get("negative", 0),
                "tension": s.overall.get("tension", 0),
                "net": s.overall.get("net", 0),
            }
            for s in ctx.sentiments
        ],
        "chapter_metrics": [
            {
                "chapter": ch.global_index,
                "chars": m.chars,
                "scenes": m.scene_count,
                "dialogues": m.dialogue_count,
                "dialogue_ratio": m.dialogue_ratio,
                "conflict_density": m.conflict_density,
                "suspense_density": m.suspense_density,
                "word_ttr": m.word_ttr,
                "sentiment_tension": m.sentiment_tension,
            }
            for ch, m in zip(chapters, ctx.metrics)
        ],
    }
    (out_dir / "structured_baseline.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

"""Hybrid analyzer: structured analysis + evidence-grounded excerpts for LLM.

This module implements the "evidence-grounded hybrid" approach:
1. Structured data (entity stats, sentiment, metrics) provides the "navigation map"
2. context_builder.collect_evidence() extracts high-signal original text paragraphs
3. LLM receives BOTH: data tables + citeable original excerpts

This combines the precision of structured analysis with the depth of
close reading that pure-LLM approaches excel at.
"""
from __future__ import annotations

import json
import math
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import llm_client
from .context_builder import collect_evidence
from .entity import compute_entity_stats, discover_entity_aliases, EntityStats
from .evaluator import compute_metrics, build_baseline, evaluate_chapter, BaselineStats, ChapterMetrics
from .normalizer import ENTITY_ALIASES
from .relation import extract_relations_rule
from .sentiment import analyze_sentiment, ChapterSentiment
from .structure import Chapter


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class StructuredContext:
    """All structured analysis results for a set of chapters."""
    entity_stats: EntityStats
    rule_relations: List[Tuple[str, str, str]]
    sentiments: List[ChapterSentiment]
    baseline: BaselineStats
    metrics: List[ChapterMetrics]
    chapter_briefs: List[Dict[str, Any]]
    aliases: Dict[str, List[str]] = field(default_factory=dict)


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


# ---------------------------------------------------------------------------
# Structured context builder
# ---------------------------------------------------------------------------
def build_structured_context(chapters: List[Chapter]) -> StructuredContext:
    """Run all structured analysis modules on the chapters."""
    aliases = discover_entity_aliases(chapters)
    names = list(aliases.keys())
    stats = compute_entity_stats(chapters, aliases=aliases)
    relations = extract_relations_rule(chapters, aliases=aliases)
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
            "plot_score": None,
            "entities_present": [n for n in names if n in ch.body],
            "sentiment": sentiments[ch.global_index - 1].overall if ch.global_index - 1 < len(sentiments) else {},
        })

    return StructuredContext(
        entity_stats=stats,
        rule_relations=relations,
        sentiments=sentiments,
        baseline=baseline,
        metrics=metrics,
        chapter_briefs=chapter_briefs,
        aliases=aliases,
    )


# ---------------------------------------------------------------------------
# Key-chapter identification (navigation layer)
# ---------------------------------------------------------------------------
def _identify_key_chapters(ctx: StructuredContext, top_k: int = 10) -> List[int]:
    """Identify chapters that are statistically anomalous or pivotal.

    Returns chapter indices (1-based) that deserve deep-reading attention.
    """
    scores: Dict[int, float] = {}

    # 1. Sentiment peaks and valleys
    for s in ctx.sentiments:
        idx = s.idx
        net = s.overall.get("net", 0)
        tension = s.overall.get("tension", 0)
        # Extreme values get high scores
        scores[idx] = scores.get(idx, 0) + abs(net) * 2 + tension * 3

    # 2. Conflict / suspense spikes
    for ch_brief, m in zip(ctx.chapter_briefs, ctx.metrics):
        idx = ch_brief["index"]
        scores[idx] = scores.get(idx, 0) + m.conflict_density * 1.5 + m.suspense_density * 1.0

    # 3. Dialogue ratio anomalies (very high or very low)
    dialogue_ratios = [m.dialogue_ratio for m in ctx.metrics]
    avg_dr = sum(dialogue_ratios) / max(1, len(dialogue_ratios))
    std_dr = math.sqrt(sum((r - avg_dr) ** 2 for r in dialogue_ratios) / max(1, len(dialogue_ratios) - 1))
    for ch_brief, m in zip(ctx.chapter_briefs, ctx.metrics):
        idx = ch_brief["index"]
        z = abs(m.dialogue_ratio - avg_dr) / max(0.001, std_dr)
        scores[idx] = scores.get(idx, 0) + z * 2

    # 4. Entity density anomalies (many characters appearing)
    for ch_brief in ctx.chapter_briefs:
        idx = ch_brief["index"]
        scores[idx] = scores.get(idx, 0) + len(ch_brief.get("entities_present", [])) * 3

    # Return top-k unique indices
    sorted_idx = sorted(scores.keys(), key=lambda i: scores[i], reverse=True)
    return sorted_idx[:top_k]


# ---------------------------------------------------------------------------
# Evidence extraction (close-reading layer)
# ---------------------------------------------------------------------------
def _extract_evidence_for_batch(
    chapters: List[Chapter],
    ctx: StructuredContext,
    max_items: int = 40,
    excerpt_chars: int = 800,
) -> str:
    """Extract high-signal evidence paragraphs for the batch.

    Uses context_builder.collect_evidence to find paragraphs that are:
    - Near sentiment peaks/valleys
    - Contain relation verbs
    - Have high entity co-occurrence
    """
    # Build a query that targets the batch's anomalies
    key_chapters = _identify_key_chapters(ctx, top_k=15)
    batch_indices = {ch.global_index for ch in chapters}
    overlap = [idx for idx in key_chapters if idx in batch_indices]

    # Detect which characters are most active in this batch
    batch_entity_counts: Counter = Counter()
    names = list(ctx.aliases.keys()) if ctx.aliases else CANONICAL_NAMES
    for ch in chapters:
        for name in names:
            c = ch.body.count(name)
            if c:
                batch_entity_counts[name] += c
    top_entities = [name for name, _ in batch_entity_counts.most_common(8)]

    # Build dynamic query based on batch characteristics
    query_parts = ["人物动机", "情感转折", "战斗描写", "关键对话"]
    if overlap:
        query_parts.append("情绪极端章节")
    query = " ".join(query_parts)

    evidence = collect_evidence(
        chapters,
        query=query,
        focus_entities=top_entities,
        max_items=max_items,
        excerpt_chars=excerpt_chars,
    )

    if not evidence:
        return ""

    lines = ["\n---\n", "## 关键原文证据（高信号段落）\n"]
    lines.append(
        "以下段落由程序根据情绪峰谷、人物共现密度、关系动词窗口自动筛选。"
        "每段都有稳定编号 `[CHxxx-Pxxx]`，分析时请直接引用。\n"
    )
    for item in evidence:
        terms = "、".join(item.matched_terms) if item.matched_terms else "无"
        lines.extend([
            f"\n### [{item.id}] {item.chapter_title}",
            f"- 位置：第 {item.chapter_index} 章，第 {item.paragraph_index} 段",
            f"- 命中关键词：{terms}",
            f"- 原文摘录：\n{item.excerpt}\n",
        ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------
def _format_structured_summary(ctx: StructuredContext, chapter_indices: List[int]) -> str:
    """Format structured data relevant to the target chapters as a compact text block."""
    lines = ["## 结构化分析数据（预处理结果）\n"]

    # Key chapters annotation
    key_chapters = set(_identify_key_chapters(ctx, top_k=15))
    relevant_keys = key_chapters & set(chapter_indices)
    if relevant_keys:
        lines.append(f"**本批次关键章节（需重点关注）**：{sorted(relevant_keys)}\n")

    # Entity stats
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
    lines.append("\n### 关系三元组（规则抽取，注意：可能存在误报）\n")
    rel_counter = Counter(ctx.rule_relations)
    for (s, r, o), count in rel_counter.most_common(30):
        lines.append(f"- ({s}, {r}, {o}) × {count}")
    lines.append("\n> ⚠️ 关系三元组基于关键词匹配，‘攻击’可能是并肩战斗，‘杀死’可能是击杀幻象/替身。请结合下方原文证据判断。\n")

    # Sentiment for target chapters
    lines.append("### 章节情感（词典打分）\n")
    lines.append("| 章 | 正面 | 负面 | 紧张 | 净值 |")
    lines.append("|---|---|---|---|---|")
    for idx in chapter_indices:
        if 0 < idx <= len(ctx.sentiments):
            s = ctx.sentiments[idx - 1]
            o = s.overall
            flag = " 🔑" if idx in key_chapters else ""
            lines.append(f"| {idx}{flag} | {o.get('positive', 0):.2f} | {o.get('negative', 0):.2f} | {o.get('tension', 0):.2f} | {o.get('net', 0):+.2f} |")

    # Metrics for target chapters
    lines.append("\n### 章节结构指标\n")
    lines.append("| 章 | 字数 | 场景 | 对话比 | 冲突密度 | 悬念密度 | 词汇TTR |")
    lines.append("|---|---|---|---|---|---|---|")
    for idx in chapter_indices:
        if 0 < idx <= len(ctx.metrics):
            m = ctx.metrics[idx - 1]
            flag = " 🔑" if idx in key_chapters else ""
            lines.append(f"| {idx}{flag} | {m.chars} | {m.scene_count} | {m.dialogue_ratio:.1%} | {m.conflict_density:.1f} | {m.suspense_density:.1f} | {m.word_ttr:.3f} |")

    return "\n".join(lines)


def build_hybrid_prompt(
    chapters: List[Chapter],
    ctx: StructuredContext,
    max_chars_per_chapter: int = 4000,
    use_evidence: bool = True,
    evidence_max_items: int = 40,
    evidence_excerpt_chars: int = 800,
) -> str:
    """Build a prompt with structured data + evidence-grounded excerpts.

    This is the core of the "evidence-grounded hybrid" approach:
    - Structured data tells the LLM "what to look for" (navigation)
    - Evidence excerpts give the LLM "what to read closely" (close reading)
    """
    chapter_indices = [ch.global_index for ch in chapters]
    structured = _format_structured_summary(ctx, chapter_indices)

    lines = [
        "你是一名资深中文网络小说编辑。你收到的是程序自动预处理的小说数据 + 精选原文证据。\n",
        "## 分析框架\n",
        "1. **结构化数据** = 导航图：告诉你哪里可能有异常（情绪极端、冲突密集、关系密集）。",
        "2. **原文证据** = 显微镜：给你具体的段落编号 `[CHxxx-Pxxx]` 和原文，供你精读判断。\n",
        "你必须结合两者进行分析：先用数据定位问题，再用原文验证/深化判断。",
        "不要只基于数据做空泛总结，也不要忽视数据信号只凭感觉评价。\n",
        "## 输出格式（JSON）\n",
        "```json",
        "{",
        '  "characters": [',
        '    {"name": "角色名", "role": "主角/配角/反派/路人", "description": "基于原文证据的具体描述，不要泛泛而谈"}',
        "  ],",
        '  "relationships": [',
        '    {"subject": "人物A", "relation": "关系类型", "object": "人物B", "evidence": "引用具体证据编号 [CHxxx-Pxxx] 和原文片段"}',
        "  ],",
        '  "sentiment_per_chapter": [',
        '    {"chapter_index": 1, "overall": "正面/负面/中性", "tension": "高/中/低", "key_emotion": "主要情感", "data_vs_text_consistency": "数据与原文是否一致"}',
        "  ],",
        '  "plot_summaries": [',
        '    {"chapter_index": 1, "summary": "一句话剧情摘要"}',
        "  ],",
        '  "quality_scores": [',
        '    {"chapter_index": 1, "plot": 7, "prose": 6, "hook": 8, "comment": "基于数据和原文的综合简评"}',
        "  ],",
        '  "deep_findings": [',
        '    {"finding": "发现的问题或亮点", "type": "人物/节奏/战斗/情感/文笔", "severity": "严重/中等/轻微", "evidence_refs": ["CH001-P003"], "explanation": "具体解释"}',
        "  ]",
        "}",
        "```\n",
        "要求：",
        "1. 每个关键判断必须引用至少一个证据编号 `[CHxxx-Pxxx]`。",
        "2. 关系分析时，如果原文证据显示‘攻击’实际是并肩战斗，请纠正规则抽取的误报。",
        "3. 如果发现数据信号与原文实际不符（如数据说‘负面’但原文是‘扮猪吃虎的爽感’），请指出这种差异。",
        "4. `deep_findings` 专门用于发现结构化数据无法单独揭示的问题（如人物动机断裂、战斗套路化、行为逻辑不一致）。",
        "5. 只输出 JSON，不要其他内容。\n",
        structured,
    ]

    # Evidence-grounded excerpts (the "close reading" layer)
    if use_evidence:
        evidence_section = _extract_evidence_for_batch(
            chapters, ctx,
            max_items=evidence_max_items,
            excerpt_chars=evidence_excerpt_chars,
        )
        if evidence_section:
            lines.append(evidence_section)

    # Fallback: if evidence is empty or very short, add chapter excerpts
    total_evidence_chars = len("\n".join(lines))
    if total_evidence_chars < 3000:
        lines.append("\n---\n")
        lines.append("## 章节原文摘要（补充）\n")
        for ch in chapters:
            body = ch.body
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


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Batch analysis
# ---------------------------------------------------------------------------
def analyze_batch_hybrid(
    chapters: List[Chapter],
    ctx: StructuredContext,
    batch_index: int = 0,
    max_chars_per_chapter: int = 4000,
    use_evidence: bool = True,
    evidence_max_items: int = 40,
    evidence_excerpt_chars: int = 800,
) -> HybridBatchResult:
    """Send a batch of chapters + structured data + evidence to LLM."""
    prompt = build_hybrid_prompt(
        chapters,
        ctx,
        max_chars_per_chapter=max_chars_per_chapter,
        use_evidence=use_evidence,
        evidence_max_items=evidence_max_items,
        evidence_excerpt_chars=evidence_excerpt_chars,
    )
    input_chars = len(prompt)

    messages = [
        {
            "role": "system",
            "content": (
                "你是专业的中文网络小说编辑。你已收到结构化数据 + 精选原文证据。"
                "请结合数据定位问题，用原文验证问题，输出纯 JSON。"
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


# ---------------------------------------------------------------------------
# Novel-level analysis
# ---------------------------------------------------------------------------
def analyze_novel_hybrid(
    chapters: List[Chapter],
    ctx: Optional[StructuredContext] = None,
    batch_size: int = 5,
    max_chars_per_chapter: int = 4000,
    use_evidence: bool = True,
    evidence_max_items: int = 40,
    evidence_excerpt_chars: int = 800,
    progress_callback=None,
) -> HybridSummary:
    """Analyze chapters in batches using hybrid (structured + evidence + LLM) approach."""
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
            progress_callback(
                f"混合分析批次 {idx + 1}/{len(batches)}: "
                f"第{batch[0].global_index}-{batch[-1].global_index}章"
            )
        result = analyze_batch_hybrid(
            batch,
            ctx,
            batch_index=idx,
            max_chars_per_chapter=max_chars_per_chapter,
            use_evidence=use_evidence,
            evidence_max_items=evidence_max_items,
            evidence_excerpt_chars=evidence_excerpt_chars,
        )
        results.append(result)
        total_input += result.input_chars
        total_elapsed += result.elapsed_seconds

    summary = summarize_hybrid_results(results, ctx)
    summary.total_input_chars = total_input
    summary.total_elapsed = round(total_elapsed, 1)
    return summary


# ---------------------------------------------------------------------------
# Result aggregation
# ---------------------------------------------------------------------------
def summarize_hybrid_results(batch_results: List[HybridBatchResult], ctx: StructuredContext) -> HybridSummary:
    """Aggregate results from multiple batches into a unified summary."""
    all_characters: Dict[str, Dict] = {}
    all_relationships: List[Dict] = []
    all_sentiment: List[Dict] = []
    all_plots: List[Dict] = []
    all_quality: List[Dict] = []
    all_findings: List[Dict] = []

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
        all_findings.extend(data.get("deep_findings", []))

    # Deduplicate findings by content similarity (simple)
    seen_findings: set = set()
    deduped_findings: List[Dict] = []
    for f in all_findings:
        key = f.get("finding", "")[:60]
        if key and key not in seen_findings:
            seen_findings.add(key)
            deduped_findings.append(f)

    summary = HybridSummary(
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
    # Attach findings as a custom attribute (not in dataclass, but useful)
    summary.deep_findings = deduped_findings  # type: ignore[attr-defined]
    return summary


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def export_hybrid_results(summary: HybridSummary, out_dir) -> None:
    """Export hybrid analysis results to JSON."""
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)

    data = {
        "approach": "hybrid_evidence_grounded",
        "total_chapters": len(summary.plot_summaries),
        "characters": summary.characters,
        "relationships": summary.relationships,
        "sentiment_per_chapter": summary.sentiment_per_chapter,
        "plot_summaries": summary.plot_summaries,
        "quality_scores": summary.quality_scores,
        "deep_findings": getattr(summary, "deep_findings", []),
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
        "key_chapters": _identify_key_chapters(ctx, top_k=15),
    }
    (out_dir / "structured_baseline.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

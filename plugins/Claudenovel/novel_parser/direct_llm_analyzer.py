"""Direct LLM analysis: send raw chapter text to LLM without structured preprocessing."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from . import llm_client
from .structure import Chapter


@dataclass
class DirectBatchResult:
    """Result from one batch of direct LLM analysis."""
    batch_index: int
    chapter_indices: List[int]
    raw_response: str
    parsed: Dict[str, Any]
    model: str
    elapsed_seconds: float
    input_chars: int


@dataclass
class DirectSummary:
    """Aggregated summary from all direct-analysis batches."""
    characters: List[Dict[str, Any]]
    relationships: List[Dict[str, str]]
    sentiment_per_chapter: List[Dict[str, Any]]
    plot_summaries: List[Dict[str, str]]
    quality_scores: List[Dict[str, Any]]
    batch_results: List[DirectBatchResult]
    total_input_chars: int
    total_elapsed: float


def _truncate_chapter(chapter: Chapter, max_chars: int) -> str:
    """Keep opening + middle + ending if chapter exceeds max_chars."""
    body = chapter.body
    if max_chars <= 0 or len(body) <= max_chars:
        return body
    part = max(1, max_chars // 3)
    mid_start = max(0, len(body) // 2 - part // 2)
    return (
        body[:part]
        + "\n\n[中间省略]\n\n"
        + body[mid_start:mid_start + part]
        + "\n\n[结尾省略]\n\n"
        + body[-part:]
    )[:max_chars]


def build_direct_prompt(chapters: List[Chapter], max_chars_per_chapter: int = 8000) -> str:
    """Build a prompt that sends raw chapter text to LLM for free-form analysis."""
    lines = [
        "你是一名网络小说分析专家。请分析以下章节，不需要任何预处理数据，"
        "完全基于原文自行判断。\n",
        "请以 JSON 格式输出，包含以下字段：\n",
        "```json",
        "{",
        '  "characters": [',
        '    {"name": "角色名", "role": "主角/配角/反派/路人", "description": "简要描述"}',
        "  ],",
        '  "relationships": [',
        '    {"subject": "人物A", "relation": "关系类型", "object": "人物B", "evidence": "原文依据"}',
        "  ],",
        '  "sentiment_per_chapter": [',
        '    {"chapter_index": 1, "overall": "正面/负面/中性", "tension": "高/中/低", "key_emotion": "主要情感"}',
        "  ],",
        '  "plot_summaries": [',
        '    {"chapter_index": 1, "summary": "一句话剧情摘要"}',
        "  ],",
        '  "quality_scores": [',
        '    {"chapter_index": 1, "plot": 7, "prose": 6, "hook": 8, "comment": "简评"}',
        '  ]',
        "}",
        "```\n",
        "要求：",
        "1. 角色名必须是原文中出现过的名字，不要编造。",
        "2. 关系必须有原文依据，写出具体的事件或对话。",
        "3. 质量评分范围 1-10。",
        "4. 如果某章信息不足，对应字段可以为空数组。",
        "5. 只输出 JSON，不要其他内容。\n",
    ]
    for ch in chapters:
        truncated = _truncate_chapter(ch, max_chars_per_chapter)
        lines.append(f"--- 第{ch.global_index}章《{ch.title}》---")
        lines.append(truncated)
        lines.append("")
    return "\n".join(lines)


def _parse_llm_json(text: str) -> Dict[str, Any]:
    """Try to extract and parse JSON from LLM response."""
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from ```json ... ``` block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try finding outermost { ... }
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {"_parse_error": True, "_raw": text[:2000]}


def analyze_batch_direct(
    chapters: List[Chapter],
    batch_index: int = 0,
    max_chars_per_chapter: int = 8000,
) -> DirectBatchResult:
    """Send a batch of chapters to LLM for direct analysis (no structured data)."""
    prompt = build_direct_prompt(chapters, max_chars_per_chapter)
    input_chars = len(prompt)

    messages = [
        {
            "role": "system",
            "content": "你是专业的中文网络小说分析助手。必须严格基于原文分析，角色名和关系必须有原文依据。输出纯 JSON。",
        },
        {"role": "user", "content": prompt},
    ]

    start = time.time()
    content, model = llm_client.call_direct_analysis(messages)
    elapsed = time.time() - start

    parsed = _parse_llm_json(content)

    return DirectBatchResult(
        batch_index=batch_index,
        chapter_indices=[ch.global_index for ch in chapters],
        raw_response=content,
        parsed=parsed,
        model=model,
        elapsed_seconds=round(elapsed, 1),
        input_chars=input_chars,
    )


def analyze_novel_direct(
    chapters: List[Chapter],
    batch_size: int = 5,
    max_chars_per_chapter: int = 8000,
    progress_callback=None,
) -> DirectSummary:
    """Analyze chapters in batches using direct LLM approach."""
    batches: List[List[Chapter]] = []
    for i in range(0, len(chapters), batch_size):
        batches.append(chapters[i:i + batch_size])

    results: List[DirectBatchResult] = []
    total_input = 0
    total_elapsed = 0.0

    for idx, batch in enumerate(batches):
        if progress_callback:
            progress_callback(f"直接分析批次 {idx + 1}/{len(batches)}: 第{batch[0].global_index}-{batch[-1].global_index}章")
        result = analyze_batch_direct(batch, batch_index=idx, max_chars_per_chapter=max_chars_per_chapter)
        results.append(result)
        total_input += result.input_chars
        total_elapsed += result.elapsed_seconds

    summary = summarize_direct_results(results)
    summary.total_input_chars = total_input
    summary.total_elapsed = round(total_elapsed, 1)
    return summary


def summarize_direct_results(batch_results: List[DirectBatchResult]) -> DirectSummary:
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
        # Merge characters
        for char in data.get("characters", []):
            name = char.get("name", "")
            if name and name not in all_characters:
                all_characters[name] = char
        # Append relationships
        all_relationships.extend(data.get("relationships", []))
        all_sentiment.extend(data.get("sentiment_per_chapter", []))
        all_plots.extend(data.get("plot_summaries", []))
        all_quality.extend(data.get("quality_scores", []))

    return DirectSummary(
        characters=list(all_characters.values()),
        relationships=all_relationships,
        sentiment_per_chapter=all_sentiment,
        plot_summaries=all_plots,
        quality_scores=all_quality,
        batch_results=batch_results,
        total_input_chars=0,
        total_elapsed=0,
    )


def export_direct_results(summary: DirectSummary, out_dir) -> None:
    """Export direct analysis results to JSON."""
    from pathlib import Path
    out_dir = Path(out_dir)
    out_dir.mkdir(exist_ok=True)

    data = {
        "approach": "direct_llm",
        "total_chapters": len(summary.plot_summaries),
        "characters": summary.characters,
        "relationships": summary.relationships,
        "sentiment_per_chapter": summary.sentiment_per_chapter,
        "plot_summaries": summary.plot_summaries,
        "quality_scores": summary.quality_scores,
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
    (out_dir / "direct_results.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

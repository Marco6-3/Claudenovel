"""Chapter rewriter framework: diagnose → suggest → rewrite → compare.

Deterministic pipeline for single-chapter revision.
Agent decides WHEN to call it; the framework decides HOW to execute.
"""
from __future__ import annotations

import difflib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import evaluator, llm_client, normalizer, structure
from .evaluator import ChapterMetrics, BaselineStats
from .rewriter_prompts import (
    build_diagnosis_prompt,
    build_suggestion_user_prompt,
    build_rewrite_user_prompt,
    SUGGESTION_SYSTEM_PROMPT,
    REWRITE_SYSTEM_PROMPT,
)
from .structure import Chapter


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class ChapterRewriteResult:
    chapter_index: int
    chapter_title: str
    original_text: str
    rewritten_text: str
    diagnosis_md: str
    suggestions_md: str
    quality_before: Dict[str, Any]
    quality_after: Optional[Dict[str, Any]]
    consistency_notes: List[str]
    model_used: str = ""
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Step 1: Diagnose
# ---------------------------------------------------------------------------
def diagnose_chapter(
    ch: Chapter,
    baseline: BaselineStats,
) -> Tuple[str, Dict[str, Any], Dict[str, float]]:
    """Compute metrics and return diagnosis markdown + raw data."""
    metrics_obj = evaluator.compute_metrics(ch)
    metrics = {k: getattr(metrics_obj, k) for k in baseline.mean.keys()}
    percentiles = {k: baseline.percentile(k, metrics[k]) for k in baseline.mean.keys()}

    diagnosis = build_diagnosis_prompt(
        chapter_title=ch.title,
        chapter_index=ch.global_index,
        metrics=metrics,
        baseline=baseline.mean,
        percentiles=percentiles,
    )
    return diagnosis, metrics, percentiles


# ---------------------------------------------------------------------------
# Step 2: Consistency check
# ---------------------------------------------------------------------------
def check_consistency(
    ch: Chapter,
    memory_summary: Optional[Dict[str, Any]],
    all_chapters: List[Chapter],
) -> List[str]:
    """Check for contradictions with previous chapters / memory.

    Returns a list of warning strings.
    """
    notes: List[str] = []
    if not memory_summary:
        return notes

    # Check 1: Are characters mentioned in this chapter consistent with their arc?
    arcs = memory_summary.get("character_arc", {})
    for name, arc_desc in arcs.items():
        if name in ch.body:
            # Heuristic: if arc says "已死/失踪" but character appears here
            if "死" in arc_desc or "失踪" in arc_desc or "离开" in arc_desc:
                # Check if chapter index is after the "departure"
                # This is a simple heuristic; real check would need event timeline
                pass  # TODO: more precise timeline-based check

    # Check 2: Unsolved hooks - are any being prematurely resolved?
    hooks = memory_summary.get("unsolved_hooks", [])
    for hook in hooks[:5]:
        # If hook text appears in chapter, flag it
        if any(word in ch.body for word in hook.split("→")[:1]):
            notes.append(f"本章涉及未解钩子：{hook}。请确认是铺垫而非回收。")

    # Check 3: Previous chapter continuity
    if ch.global_index > 1:
        prev = next((c for c in all_chapters if c.global_index == ch.global_index - 1), None)
        if prev:
            # Simple check: if last paragraph of prev and first of this have no character overlap
            prev_last = prev.last[-100:] if prev.last else ""
            this_first = ch.first[:100] if ch.first else ""
            # More sophisticated: check for abrupt setting changes without transition
            pass

    # Check 4: Character count anomaly
    if ch.chars < 1500:
        notes.append(f"本章仅{ch.chars}字，明显低于平均，可能存在内容缺失。")
    if ch.chars > 8000:
        notes.append(f"本章{ch.chars}字，明显偏长，建议拆章或精简。")

    return notes


# ---------------------------------------------------------------------------
# Step 3: Generate suggestions
# ---------------------------------------------------------------------------
def generate_suggestions(
    diagnosis: str,
    memory_summary: Optional[Dict[str, Any]],
    consistency_notes: List[str],
) -> Tuple[str, str]:
    """Call LLM to generate actionable revision suggestions.

    Returns (suggestions_markdown, model_used).
    """
    user_prompt = build_suggestion_user_prompt(
        diagnosis=diagnosis,
        memory_summary=memory_summary or {},
        consistency_notes=consistency_notes,
    )

    messages = [
        {"role": "system", "content": SUGGESTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    content, model = llm_client.call_chat(
        messages,
        temperature=0.4,
        timeout=300,
    )
    return content, model


# ---------------------------------------------------------------------------
# Step 4: Rewrite
# ---------------------------------------------------------------------------
def rewrite_with_llm(
    original_text: str,
    chapter_title: str,
    suggestions: str,
    memory_summary: Optional[Dict[str, Any]],
) -> Tuple[str, str]:
    """Call LLM to rewrite the chapter based on suggestions.

    Returns (rewritten_text, model_used).
    """
    user_prompt = build_rewrite_user_prompt(
        original_text=original_text,
        chapter_title=chapter_title,
        suggestions=suggestions,
        memory_summary=memory_summary or {},
    )

    messages = [
        {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    content, model = llm_client.call_chat(
        messages,
        temperature=0.65,  # slightly creative for writing
        timeout=300,
    )
    return content, model


# ---------------------------------------------------------------------------
# Step 5: Export comparison
# ---------------------------------------------------------------------------
def compute_text_diff(original: str, rewritten: str) -> str:
    """Generate a human-readable diff of the two texts."""
    orig_lines = original.splitlines(keepends=True)
    rewr_lines = rewritten.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        orig_lines, rewr_lines,
        fromfile="original", tofile="rewritten",
        lineterm="",
    ))
    if not diff:
        return "（无文字差异 - 重写结果与原文完全相同）"
    return "".join(diff[:500])  # cap output size


def export_rewrite_result(
    result: ChapterRewriteResult,
    out_dir: Path,
) -> None:
    """Write all outputs to a dedicated folder."""
    folder = out_dir / f"ch{result.chapter_index:03d}_{result.chapter_title[:10]}"
    folder.mkdir(parents=True, exist_ok=True)

    # 1. Original
    (folder / "original.txt").write_text(result.original_text, encoding="utf-8")

    # 2. Diagnosis
    (folder / "diagnosis.md").write_text(result.diagnosis_md, encoding="utf-8")

    # 3. Suggestions
    (folder / "review_suggestions.md").write_text(result.suggestions_md, encoding="utf-8")

    # 4. Rewritten
    (folder / "rewritten_chapter.md").write_text(result.rewritten_text, encoding="utf-8")

    # 5. Diff
    diff_text = compute_text_diff(result.original_text, result.rewritten_text)
    (folder / "diff.patch").write_text(diff_text, encoding="utf-8")

    # 6. Quality comparison
    quality_report = {
        "chapter": result.chapter_index,
        "title": result.chapter_title,
        "model": result.model_used,
        "elapsed_seconds": result.elapsed_seconds,
        "quality_before": result.quality_before,
        "quality_after": result.quality_after,
        "consistency_notes": result.consistency_notes,
        "chars_original": len(result.original_text),
        "chars_rewritten": len(result.rewritten_text),
    }
    (folder / "quality_comparison.json").write_text(
        json.dumps(quality_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 7. Human-readable comparison report
    report_lines = [
        f"# 章节重写对比报告：第{result.chapter_index}章《{result.chapter_title}》\n",
        f"> 模型：{result.model_used}\n",
        f"> 耗时：{result.elapsed_seconds:.1f}秒\n",
        f"> 原文：{len(result.original_text)}字 | 重写：{len(result.rewritten_text)}字\n",
        "\n---\n",
        "## 诊断结论\n",
        result.diagnosis_md,
        "\n---\n",
        "## 修改建议\n",
        result.suggestions_md,
        "\n---\n",
        "## 一致性检查\n",
    ]
    if result.consistency_notes:
        for note in result.consistency_notes:
            report_lines.append(f"- ⚠️ {note}")
    else:
        report_lines.append("- ✅ 未发现明显矛盾")

    report_lines.extend([
        "\n---\n",
        "## 质量对比\n",
        "```json\n",
        json.dumps({
            "before": result.quality_before,
            "after": result.quality_after,
        }, ensure_ascii=False, indent=2),
        "\n```\n",
        "\n---\n",
        "## 文本差异（前100行）\n",
        "```diff\n",
        diff_text[:3000],
        "\n```\n",
        "\n---\n",
        f"**完整文件保存在**：{folder}\n",
    ])
    (folder / "comparison_report.md").write_text(
        "".join(report_lines), encoding="utf-8"
    )

    print(f"[RewriteExport] All files saved to {folder}")
    for f in folder.iterdir():
        print(f"  - {f.name} ({f.stat().st_size} bytes)")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
def rewrite_chapter(
    chapter_text: str,
    chapter_title: str = "",
    chapter_index: int = 0,
    all_chapters: Optional[List[Chapter]] = None,
    baseline: Optional[BaselineStats] = None,
    memory_summary: Optional[Dict[str, Any]] = None,
    out_dir: Path = Path("rewritten"),
    skip_rewrite: bool = False,  # if True, only generate diagnosis + suggestions
) -> ChapterRewriteResult:
    """Full rewrite pipeline for a single chapter.

    Args:
        chapter_text: The raw text of the chapter to rewrite.
        chapter_title: Optional title (extracted from text if empty).
        chapter_index: Global chapter number.
        all_chapters: Full novel chapter list (for continuity checks).
        baseline: Novel-wide baseline stats (computed from all_chapters if None).
        memory_summary: Cross-batch memory for consistency.
        out_dir: Where to write output files.
        skip_rewrite: If True, stop after generating suggestions (author review mode).
    """
    t0 = time.time()

    # Parse chapter into structure
    from .structure import parse_chapters
    # Wrap in a fake volume marker if needed
    wrapped = f"第1卷\n\n{chapter_title}\n\n{chapter_text}"
    parsed = parse_chapters(wrapped)
    if not parsed:
        raise ValueError("Failed to parse chapter text")
    ch = parsed[0]
    if chapter_index:
        ch.global_index = chapter_index
    if chapter_title:
        ch.title = chapter_title

    # Build baseline if not provided
    if baseline is None and all_chapters:
        baseline = evaluator.build_baseline(all_chapters)
    if baseline is None:
        # Single-chapter mode: use itself as baseline (degraded)
        baseline = evaluator.build_baseline([ch])

    # Step 1: Diagnose
    print(f"[Rewrite] Step 1/5: Diagnosing chapter {ch.global_index}...")
    diagnosis, metrics, percentiles = diagnose_chapter(ch, baseline)

    # Step 2: Consistency
    print(f"[Rewrite] Step 2/5: Checking consistency...")
    consistency_notes = check_consistency(ch, memory_summary, all_chapters or [ch])

    # Step 3: Suggestions
    print(f"[Rewrite] Step 3/5: Generating suggestions...")
    suggestions, model_suggest = generate_suggestions(diagnosis, memory_summary, consistency_notes)

    if skip_rewrite:
        elapsed = time.time() - t0
        result = ChapterRewriteResult(
            chapter_index=ch.global_index,
            chapter_title=ch.title,
            original_text=chapter_text,
            rewritten_text="",
            diagnosis_md=diagnosis,
            suggestions_md=suggestions,
            quality_before=metrics,
            quality_after=None,
            consistency_notes=consistency_notes,
            model_used=model_suggest,
            elapsed_seconds=elapsed,
        )
        export_rewrite_result(result, out_dir)
        return result

    # Step 4: Rewrite
    print(f"[Rewrite] Step 4/5: Rewriting with LLM...")
    rewritten, model_rewrite = rewrite_with_llm(
        original_text=chapter_text,
        chapter_title=ch.title,
        suggestions=suggestions,
        memory_summary=memory_summary,
    )

    # Step 5: Post-rewrite quality check
    print(f"[Rewrite] Step 5/5: Comparing quality...")
    # Parse rewritten text to compute new metrics
    wrapped_rewritten = f"第1卷\n\n{ch.title}\n\n{rewritten}"
    parsed_rewritten = parse_chapters(wrapped_rewritten)
    quality_after = None
    if parsed_rewritten:
        ch_rewritten = parsed_rewritten[0]
        metrics_after = evaluator.compute_metrics(ch_rewritten)
        quality_after = {k: getattr(metrics_after, k) for k in baseline.mean.keys()}

    elapsed = time.time() - t0
    result = ChapterRewriteResult(
        chapter_index=ch.global_index,
        chapter_title=ch.title,
        original_text=chapter_text,
        rewritten_text=rewritten,
        diagnosis_md=diagnosis,
        suggestions_md=suggestions,
        quality_before=metrics,
        quality_after=quality_after,
        consistency_notes=consistency_notes,
        model_used=f"{model_suggest}/{model_rewrite}",
        elapsed_seconds=elapsed,
    )
    export_rewrite_result(result, out_dir)
    return result

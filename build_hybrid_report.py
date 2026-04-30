"""Build evidence-grounded hybrid LLM report from any novel.

This script combines:
1. Structured baseline (from analyze_custom_novel.py or pipeline)
2. Evidence-grounded excerpts (from context_builder.collect_evidence)
3. LLM deep analysis

Usage:
    python build_hybrid_report.py \
        --txt novel.txt \
        --structured structured_baseline.json \
        --out-dir ./report \
        --characters "凌默" "秦思妍" "赵灵瑶"
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from novel_parser import llm_client, normalizer, structure
from novel_parser.context_builder import collect_evidence
from novel_parser.hybrid_analyzer import (
    StructuredContext,
    build_structured_context,
    _identify_key_chapters,
)


def build_prompt(
    chapters: List[structure.Chapter],
    structured: Dict[str, Any],
    focus_entities: List[str],
    evidence_max_items: int = 50,
    evidence_excerpt_chars: int = 900,
) -> str:
    """Build an evidence-grounded hybrid prompt."""

    # --- Part 1: Structured data summary ---
    metrics = structured.get("chapter_metrics", [])
    first_half = metrics[: len(metrics) // 2]
    second_half = metrics[len(metrics) // 2 :]

    def avg(key: str, seq: list) -> float:
        return sum(m.get(key, 0) for m in seq) / max(1, len(seq))

    sentiment_keypoints = [
        s
        for s in structured.get("sentiment", [])
        if abs(s.get("net", 0)) > 8 or s.get("tension", 0) > 5
    ]

    lines = [
        "# 小说结构化分析数据包\n",
        "## 小说概况",
        f"- 分析范围：第1-{len(metrics)}章" if metrics else "- 分析范围：未知",
        f"- 总字数：{sum(m.get('chars', 0) for m in metrics):,}" if metrics else "- 总字数：未知",
        f"- 核心人物：{', '.join(focus_entities) if focus_entities else '自动检测'}",
        "\n## 人物出场统计",
    ]
    for e in structured.get("entity_stats", {}).get("top_20", [])[:15]:
        lines.append(
            f"- {e['name']}: {e['count']}次，活跃章节{e['chapters'][0]}-{e['chapters'][1]}（共{e['chapters'][2]}章）"
        )

    lines.extend(["\n## 情绪弧线关键点（词典打分）", "| 章 | 标题 | 正面 | 负面 | 紧张 | 净值 |", "|---|---|---|---|---|---|"])
    for s in sentiment_keypoints[:15]:
        lines.append(
            f"| {s['chapter']} | {s['title']} | {s['positive']:.1f} | {s['negative']:.1f} | {s['tension']:.1f} | {s['net']:+.1f} |"
        )

    lines.extend(["\n## 质量指标趋势", "| 指标 | 前半均值 | 后半均值 | 趋势 |", "|---|---|---|---|"])
    for label, key in [
        ("对话比(%)", "dialogue_ratio"),
        ("冲突密度", "conflict_density"),
        ("悬念密度", "suspense_density"),
        ("词汇TTR", "word_ttr"),
    ]:
        v1 = avg(key, first_half)
        v2 = avg(key, second_half)
        trend = "上升" if v2 > v1 else "下降"
        lines.append(f"| {label} | {v1:.2f} | {v2:.2f} | {trend} |")

    lines.extend(["\n## 关系三元组（规则提取，注意误报可能）", "| 主体 | 关系 | 对象 | 次数 |", "|---|---|---|---|"])
    for r in structured.get("relations", {}).get("top_30", [])[:15]:
        lines.append(f"| {r['subject']} | {r['relation']} | {r['object']} | {r['count']} |")

    lines.extend([
        "\n## 章节结构统计",
        f"- 平均字数: {avg('chars', metrics):.0f}",
        f"- 平均场景数: {avg('scenes', metrics):.1f}",
        f"- 平均对话数: {avg('dialogues', metrics):.1f}",
    ])

    # --- Part 2: Evidence-grounded excerpts ---
    lines.extend([
        "\n---\n",
        "# 任务要求\n",
        "你是一名资深中文网络小说编辑。你收到的是：",
        "1. **结构化数据** = 导航图：告诉你哪里可能有异常（情绪极端、冲突密集、关系密集）。",
        "2. **原文证据** = 显微镜：给你具体的段落编号 `[CHxxx-Pxxx]` 和原文，供你精读判断。\n",
        "你必须结合两者进行分析：先用数据定位问题，再用原文验证/深化判断。",
        "不要只基于数据做空泛总结，也不要忽视数据信号只凭感觉评价。\n",
        "## 输出格式（中文 Markdown）\n",
        "### 一、整体评价",
        "- 基于人物出场分布、情绪弧线、质量指标趋势，给出整体判断",
        "- 指出节奏、文笔、人物塑造方面的亮点\n",
        "### 二、写作质量问题（深度发现）",
        "- 基于**原文证据**指出具体问题：人物动机是否断裂？行为逻辑是否一致？战斗是否套路化？",
        "- 每个问题必须引用至少一个证据编号 `[CHxxx-Pxxx]`",
        "- 如果发现数据信号与原文实际不符，请指出这种差异\n",
        "### 三、后续剧情预测（3-5条）",
        "- 基于情绪曲线终点、未解钩子、人物出场跨度",
        "- 给出具体的后续剧情走向预测，每条包含：冲突核心、人物推进、下一章钩子、可信度评估\n",
        "### 四、风险提示",
        "- 指出基于数据推断时‘证据不足’的地方",
        "- 提醒规则提取的关系三元组存在误报可能\n",
        "注意：",
        "1. 分析必须结合数据，不要空泛套话",
        "2. 对于数据无法支撑的判断，明确标注‘推测’或‘证据不足’",
        "3. 关系三元组是关键词匹配结果，提到时需要谨慎",
        "4. **关键要求**：`deep_findings` 部分专门用于发现结构化数据无法单独揭示的问题",
    ])

    # Collect evidence from all chapters (not just a batch)
    print(f"[HybridReport] Collecting evidence for {len(chapters)} chapters...")
    evidence = collect_evidence(
        chapters,
        query="人物动机 情感转折 战斗描写 关键对话 行为逻辑",
        focus_entities=focus_entities,
        max_items=evidence_max_items,
        excerpt_chars=evidence_excerpt_chars,
    )

    if evidence:
        lines.extend([
            "\n---\n",
            "## 关键原文证据（高信号段落）\n",
            "以下段落由程序根据情绪峰谷、人物共现密度、关系动词窗口自动筛选。",
            "每段都有稳定编号 `[CHxxx-Pxxx]`，分析时请直接引用。\n",
        ])
        for item in evidence:
            terms = "、".join(item.matched_terms) if item.matched_terms else "无"
            lines.extend([
                f"\n### [{item.id}] {item.chapter_title}",
                f"- 位置：第 {item.chapter_index} 章，第 {item.paragraph_index} 段",
                f"- 命中关键词：{terms}",
                f"- 原文摘录：\n{item.excerpt}\n",
            ])

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evidence-grounded hybrid LLM report")
    parser.add_argument("--txt", type=Path, required=True, help="Novel text file")
    parser.add_argument("--structured", type=Path, required=True, help="structured_baseline.json")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory")
    parser.add_argument("--character", action="append", default=[], dest="characters", help="Core character names")
    parser.add_argument("--evidence-items", type=int, default=50, help="Max evidence items")
    parser.add_argument("--evidence-chars", type=int, default=900, help="Max chars per evidence excerpt")
    args = parser.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load structured baseline
    structured = json.loads(args.structured.read_text(encoding="utf-8"))
    print(f"[HybridReport] Loaded structured baseline: {args.structured}")

    # Parse novel
    print(f"[HybridReport] Parsing novel: {args.txt.name}")
    raw = normalizer.read_text(args.txt)
    text = normalizer.normalize_text(raw)
    chapters = structure.parse_chapters(text)
    print(f"[HybridReport] Parsed {len(chapters)} chapters")

    # Determine focus entities
    focus_entities = args.characters
    if not focus_entities:
        # Auto-detect from structured baseline top entities
        focus_entities = [e["name"] for e in structured.get("entity_stats", {}).get("top_20", [])[:5]]
        print(f"[HybridReport] Auto-detected focus entities: {focus_entities}")

    # Build prompt
    prompt = build_prompt(
        chapters,
        structured,
        focus_entities,
        evidence_max_items=args.evidence_items,
        evidence_excerpt_chars=args.evidence_chars,
    )

    prompt_path = out_dir / "hybrid_analysis_prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    print(f"[HybridReport] Prompt built: {prompt_path} ({len(prompt)} chars)")

    # Call LLM
    print("[HybridReport] Calling LLM (deepseek-v4-pro)...")
    t0 = time.time()
    try:
        content, model = llm_client.generate_context_report(prompt)
        elapsed = time.time() - t0
        report = (
            f"# Hybrid Evidence-Grounded 分析报告\n\n"
            f"> 模型：{model}\n"
            f"> 耗时：{elapsed:.1f}秒\n"
            f"> 输入字符：{len(prompt)}\n"
            f"> 核心人物：{', '.join(focus_entities)}\n\n"
            f"{content}\n"
        )
        out_path = out_dir / "hybrid_evidence_report.md"
        out_path.write_text(report, encoding="utf-8")
        print(f"[HybridReport] Report saved: {out_path}")
    except Exception as exc:
        print(f"[HybridReport] LLM call failed: {exc}")
        raise


if __name__ == "__main__":
    main()

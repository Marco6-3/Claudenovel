"""Prompt templates for chapter diagnosis, suggestion, and rewriting.

All prompts are evidence-grounded: they reference structured metrics
and memory context, not just free-form instruction.
"""
from __future__ import annotations

from typing import Dict, List, Any


# ---------------------------------------------------------------------------
# Step 1: Diagnosis → plain-language gap report
# ---------------------------------------------------------------------------
def build_diagnosis_prompt(
    chapter_title: str,
    chapter_index: int,
    metrics: Dict[str, Any],
    baseline: Dict[str, float],
    percentiles: Dict[str, float],
) -> str:
    """Turn quantitative metrics into a concise diagnostic paragraph."""
    lines = [
        f"# 章节诊断：第{chapter_index}章《{chapter_title}》",
        "",
        "## 关键指标 vs 全书基准",
        "",
        "| 指标 | 本章 | 全书均值 | 百分位 | 判断 |",
        "|---|---|---|---|---|",
    ]
    for k, label in [
        ("chars", "字数"),
        ("dialogue_ratio", "对话比"),
        ("conflict_density", "冲突密度"),
        ("suspense_density", "悬念密度"),
        ("word_ttr", "词汇丰富度(TTR)"),
        ("scene_switch_rate", "场景切换率"),
        ("entity_diversity", "出场人物数"),
        ("sentiment_net", "情绪净值"),
        ("sentiment_tension", "紧张度"),
    ]:
        val = metrics.get(k, 0)
        mean = baseline.get(k, 0)
        pct = percentiles.get(k, 50)
        if pct > 70:
            judge = "偏高"
        elif pct < 30:
            judge = "偏低"
        else:
            judge = "正常"
        lines.append(f"| {label} | {val} | {mean:.2f} | {pct}% | {judge} |")

    lines.append("\n## 诊断结论\n")
    # Auto-generate 3 bullet findings
    findings = []
    if percentiles.get("dialogue_ratio", 50) > 75:
        findings.append("对话占比偏高，节奏偏快但可能缺乏叙事厚度")
    elif percentiles.get("dialogue_ratio", 50) < 25:
        findings.append("对话占比偏低，场景感不足，易显沉闷")
    if percentiles.get("conflict_density", 50) > 75:
        findings.append("冲突密度高，情节张力足")
    elif percentiles.get("conflict_density", 50) < 25:
        findings.append("冲突密度偏低，剧情推进感弱")
    if percentiles.get("suspense_density", 50) < 30:
        findings.append("悬念感不足，缺乏钩子")
    if percentiles.get("word_ttr", 50) < 30:
        findings.append("词汇重复度偏高，文笔变化不足")
    if metrics.get("sentiment_net", 0) > 3 and percentiles.get("suspense_density", 50) < 40:
        findings.append("情绪过于平顺，可考虑用意外事件打破")
    if metrics.get("sentiment_net", 0) < -5:
        findings.append("情绪净值极低，注意情绪透支风险")
    if not findings:
        findings.append("整体均衡，可在悬念或冲突上再加点料")

    for f in findings:
        lines.append(f"- {f}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 2: Suggestion generation
# ---------------------------------------------------------------------------
SUGGESTION_SYSTEM_PROMPT = """你是一名严谨的中文网络小说编辑。请基于给定的章节诊断报告和前文记忆，生成具体、可执行的修改建议。

要求：
1. 每条建议必须对应一个具体的指标问题或前文矛盾。
2. 建议要写成"可执行"的形式，不要空泛说"加强冲突"，要说"在XX场景加入XX冲突"。
3. 如果前文记忆中有未解钩子，建议应说明如何在本章铺垫或回收。
4. 如果存在设定矛盾，必须指出并给出修正方案。
5. 输出 Markdown 列表，每条包含：问题、原因、建议、预期效果。
6. 最多 8 条建议，按优先级排序。
"""


def build_suggestion_user_prompt(
    diagnosis: str,
    memory_summary: Dict[str, Any],
    consistency_notes: List[str],
) -> str:
    lines = [diagnosis, "\n---\n", "## 前文记忆（跨批次上下文）\n"]

    # Memory injection
    hooks = memory_summary.get("unsolved_hooks", [])
    if hooks:
        lines.append("### 未解钩子\n")
        for h in hooks[:5]:
            lines.append(f"- {h}")

    arcs = memory_summary.get("character_arc", {})
    if arcs:
        lines.append("\n### 人物弧光\n")
        for name, desc in list(arcs.items())[:5]:
            lines.append(f"- **{name}**：{desc}")

    milestones = memory_summary.get("relation_milestones", [])
    if milestones:
        lines.append("\n### 关系里程碑\n")
        for m in milestones[:5]:
            chapter = (
                m.get("first_seen_chapter")
                or m.get("first_chapter")
                or m.get("chapter")
                or "?"
            )
            lines.append(
                f"- 第{chapter}章：{m.get('subject', '')} → {m.get('relation', '')} → {m.get('object', '')}"
            )

    if consistency_notes:
        lines.append("\n---\n## 一致性检查结果\n")
        for note in consistency_notes:
            lines.append(f"- ⚠️ {note}")

    lines.append(
        "\n---\n"
        "请基于以上信息，生成具体的修改建议。"
        "如果前文记忆与本章无直接关联，可以忽略。"
        "如果一致性检查发现问题，必须优先处理。\n"
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Step 3: Rewrite
# ---------------------------------------------------------------------------
REWRITE_SYSTEM_PROMPT = """你是一名中文网络小说作者，正在根据编辑的修改建议重写章节。

核心约束：
1. **保留原文风格和人物语气**：不要改变角色的说话方式。
2. **保留关键情节节点**：修改建议中的改动应在原有情节基础上优化，不要重写整个故事线。
3. **承接前文记忆**：确保本章的人物状态、关系、未解钩子与前文一致。
4. **保持章节字数接近原文**：如果原文3000字，重写后应在2500-3500字之间。
5. **输出纯文本**：只输出重写后的章节正文，不要加任何解释、注释、Markdown标记。
6. **章节标题**：保留原标题，放在正文第一行。

禁止行为：
- 不要编造前文未提及的新设定
- 不要改变人物的现有关系状态
- 不要删除本章原有的核心冲突或高潮
"""


def build_rewrite_user_prompt(
    original_text: str,
    chapter_title: str,
    suggestions: str,
    memory_summary: Dict[str, Any],
) -> str:
    lines = [
        f"## 原标题：{chapter_title}\n",
        "## 编辑修改建议\n",
        suggestions,
        "\n---\n",
        "## 前文记忆（必须遵守的设定约束）\n",
    ]

    # Inject minimal memory constraints
    hooks = memory_summary.get("unsolved_hooks", [])
    if hooks:
        lines.append("**未解钩子**（本章可铺垫但不可解决，除非建议明确）：")
        for h in hooks[:3]:
            lines.append(f"- {h}")

    arcs = memory_summary.get("character_arc", {})
    if arcs:
        lines.append("\n**人物当前状态**：")
        for name, desc in list(arcs.items())[:3]:
            lines.append(f"- {name}：{desc}")

    lines.extend([
        "\n---\n",
        "## 原文\n",
        original_text,
        "\n---\n",
        "请根据修改建议重写本章，输出纯文本正文。",
    ])

    return "\n".join(lines)

"""Chapter quality evaluation and plot-recommendation engine.

Evaluates a single chapter (or user-input text) against the novel-wide baseline
and recommends next-plot directions.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .normalizer import ENTITY_ALIASES
from .sentiment import score_text
from .structure import Chapter, split_paragraphs, split_scenes

CANONICAL_NAMES = list(ENTITY_ALIASES.keys())

# Conflict / suspense / hook markers
CONFLICT_WORDS = {
    "打", "杀", "死", "战", "斗", "逃", "追", "包围", "偷袭", "伏击",
    "陷阱", "危机", "危险", "紧急", "拼命", "疯狂", "爆发", "撕裂",
    "怒吼", "惨叫", "冷笑", "威胁", "警告", "挑衅", "侮辱", "怒骂",
    "冲突", "矛盾", "决裂", "背叛", "欺骗", "误会", "争吵", "对峙",
}
SUSPENSE_MARKERS = {
    "？", "?", "……", "..", "怎么办", "为什么", "究竟", "到底",
    "难道", "莫非", "万一", "如果", "忽然", "突然", "竟然", "不料",
    "却", "然而", "但是", "不过", "只是", "没想到", "出乎意料",
}
RHYTHRIC_MARKERS = {
    "像", "如同", "仿佛", "似", "宛如", "好比",  # simile / metaphor
    "越来越", "愈发", "更加", "格外", "分外",  # escalation
    "一", "二", "三", "首先", "其次", "最后",  # enumeration (parallelism)
}


@dataclass
class ChapterMetrics:
    """Quantitative metrics for one chapter."""
    chars: int
    paragraph_count: int
    scene_count: int
    dialogue_count: int
    dialogue_chars: int
    avg_paragraph_len: float
    paragraph_len_std: float
    sentence_count: int
    avg_sentence_len: float
    sentence_len_std: float
    word_ttr: float               # type-token ratio (char-level proxy)
    conflict_density: float       # conflict words per 1000 chars
    suspense_density: float       # suspense markers per 1000 chars
    info_density: float           # new-entity mentions per 1000 chars
    scene_switch_rate: float      # scenes per 1000 chars
    dialogue_ratio: float         # dialogue chars / total chars
    sentiment_net: float
    sentiment_tension: float
    entity_diversity: int         # unique canonical names present
    named_entity_ratio: float     # entity mentions / chars * 1000
    rhetorical_density: float     # rhetorical markers per 1000 chars


@dataclass
class BaselineStats:
    """Population mean & std across all reference chapters."""
    mean: Dict[str, float] = field(default_factory=dict)
    std: Dict[str, float] = field(default_factory=dict)

    def percentile(self, key: str, value: float) -> float:
        """Return approximate percentile assuming normal distribution."""
        m = self.mean.get(key, 0)
        s = self.std.get(key, 1)
        if s == 0:
            return 50.0
        # clamp z to [-3, 3] for stability
        z = max(-3, min(3, (value - m) / s))
        # CDF approx
        return round(50 + 50 * math.erf(z / math.sqrt(2)), 1)


@dataclass
class QualityReport:
    metrics: ChapterMetrics
    plot_score: float          # 0-100 composite plot-quality score
    prose_score: float         # 0-100 composite prose-quality score
    hook_score: float          # 0-100 how "page-turning" is it
    percentiles: Dict[str, float] = field(default_factory=dict)
    strengths: List[str] = field(default_factory=list)
    weaknesses: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    similar_chapters: List[Tuple[int, str, float]] = field(default_factory=list)


def _sentence_stats(text: str) -> Tuple[int, float, float]:
    """Count sentences and return (count, avg_len, std_len)."""
    # split on Chinese sentence terminators
    sents = [s.strip() for s in re.split(r"[。！？;；\n]+", text) if len(s.strip()) > 3]
    if not sents:
        return 0, 0.0, 0.0
    lens = [len(s) for s in sents]
    avg = sum(lens) / len(lens)
    var = sum((x - avg) ** 2 for x in lens) / max(1, len(lens) - 1)
    return len(lens), avg, math.sqrt(var)


def _char_ttr(text: str) -> float:
    """Type-token ratio using 2-gram characters as proxy."""
    bigrams = [text[i:i + 2] for i in range(0, max(1, len(text) - 1), 2)]
    if not bigrams:
        return 0.0
    return len(set(bigrams)) / len(bigrams)


def compute_metrics(ch: Chapter) -> ChapterMetrics:
    body = ch.body
    paragraphs = ch.paragraphs
    dialogues = ch.dialogues

    # paragraph stats
    para_lens = [len(p) for p in paragraphs]
    avg_para = sum(para_lens) / max(1, len(para_lens))
    para_std = math.sqrt(sum((x - avg_para) ** 2 for x in para_lens) / max(1, len(para_lens) - 1))

    # sentence stats
    sent_count, avg_sent, sent_std = _sentence_stats(body)

    # dialogue
    dia_chars = sum(len(d.text) for d in dialogues)

    # conflict / suspense / rhetorical / entity
    conflict_hits = sum(body.count(w) for w in CONFLICT_WORDS)
    suspense_hits = sum(body.count(w) for w in SUSPENSE_MARKERS)
    rhet_hits = sum(body.count(w) for w in RHYTHRIC_MARKERS)
    entity_hits = sum(body.count(name) for name in CANONICAL_NAMES)
    present_entities = {name for name in CANONICAL_NAMES if name in body}

    # scene switches
    scene_switches = max(0, len(ch.scenes) - 1)

    # sentiment
    sent = score_text(body)

    total = max(1, len(body))
    return ChapterMetrics(
        chars=total,
        paragraph_count=len(paragraphs),
        scene_count=len(ch.scenes),
        dialogue_count=len(dialogues),
        dialogue_chars=dia_chars,
        avg_paragraph_len=round(avg_para, 1),
        paragraph_len_std=round(para_std, 1),
        sentence_count=sent_count,
        avg_sentence_len=round(avg_sent, 1),
        sentence_len_std=round(sent_std, 1),
        word_ttr=round(_char_ttr(body), 3),
        conflict_density=round(conflict_hits * 1000 / total, 2),
        suspense_density=round(suspense_hits * 1000 / total, 2),
        info_density=round(len(present_entities) * 1000 / total, 2),
        scene_switch_rate=round(scene_switches * 1000 / total, 2),
        dialogue_ratio=round(dia_chars / total, 3),
        sentiment_net=round(sent["net"], 3),
        sentiment_tension=round(sent["tension"], 3),
        entity_diversity=len(present_entities),
        named_entity_ratio=round(entity_hits * 1000 / total, 2),
        rhetorical_density=round(rhet_hits * 1000 / total, 2),
    )


def build_baseline(all_chapters: List[Chapter]) -> BaselineStats:
    """Compute population stats across all chapters."""
    all_metrics = [compute_metrics(ch) for ch in all_chapters]
    keys = [
        "chars", "paragraph_count", "dialogue_ratio", "avg_sentence_len",
        "sentence_len_std", "word_ttr", "conflict_density", "suspense_density",
        "info_density", "scene_switch_rate", "sentiment_net", "sentiment_tension",
        "entity_diversity", "named_entity_ratio", "rhetorical_density",
    ]
    mean: Dict[str, float] = {}
    std: Dict[str, float] = {}
    for k in keys:
        vals = [getattr(m, k) for m in all_metrics]
        m = sum(vals) / len(vals)
        variance = sum((v - m) ** 2 for v in vals) / max(1, len(vals) - 1)
        mean[k] = m
        std[k] = math.sqrt(variance)
    return BaselineStats(mean=mean, std=std)


def build_external_chapter(text: str, title: str = "输入章节") -> Chapter:
    """Build a temporary Chapter from user-provided chapter text."""
    body = text.strip()
    paragraphs = split_paragraphs(body)
    scenes = split_scenes(paragraphs)
    dialogues = [d for scene in scenes for d in scene.dialogues]
    return Chapter(
        global_index=0,
        volume="外部输入",
        title=title,
        body=body,
        chars=len(body),
        first=paragraphs[0][:260] if paragraphs else "",
        last=paragraphs[-1][-220:] if paragraphs else "",
        paragraphs=paragraphs,
        scenes=scenes,
        dialogues=dialogues,
    )


def _cosine_similarity(a: Dict[str, float], b: Dict[str, float]) -> float:
    """Cosine similarity between two feature vectors."""
    keys = set(a.keys()) & set(b.keys())
    dot = sum(a[k] * b[k] for k in keys)
    norm_a = math.sqrt(sum(a[k] ** 2 for k in keys))
    norm_b = math.sqrt(sum(b[k] ** 2 for k in keys))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def evaluate_chapter(
    ch: Chapter,
    baseline: BaselineStats,
    all_chapters: List[Chapter],
    all_metrics: Optional[List[ChapterMetrics]] = None,
) -> QualityReport:
    """Evaluate a chapter against the novel baseline."""
    m = compute_metrics(ch)
    if all_metrics is None:
        all_metrics = [compute_metrics(c) for c in all_chapters]

    # Percentiles
    pcts = {}
    for k in baseline.mean:
        pcts[k] = baseline.percentile(k, getattr(m, k))

    # Composite scores (0-100)
    # Plot quality: conflict, suspense, info_density, scene_switch_rate, entity_diversity, sentiment_tension
    plot_score = (
        pcts.get("conflict_density", 50) * 0.20
        + pcts.get("suspense_density", 50) * 0.20
        + pcts.get("info_density", 50) * 0.15
        + pcts.get("scene_switch_rate", 50) * 0.10
        + pcts.get("entity_diversity", 50) * 0.15
        + pcts.get("sentiment_tension", 50) * 0.20
    )

    # Prose quality: dialogue_ratio, word_ttr, sentence_len_std, rhetorical_density, named_entity_ratio
    prose_score = (
        min(100, pcts.get("dialogue_ratio", 50) * 1.5) * 0.20  # cap high dialogue
        + pcts.get("word_ttr", 50) * 0.20
        + pcts.get("sentence_len_std", 50) * 0.20
        + pcts.get("rhetorical_density", 50) * 0.20
        + pcts.get("named_entity_ratio", 50) * 0.20
    )

    # Hook score: combination of tension, suspense, scene switches, dialogue momentum
    hook_score = (
        pcts.get("sentiment_tension", 50) * 0.25
        + pcts.get("suspense_density", 50) * 0.25
        + pcts.get("scene_switch_rate", 50) * 0.20
        + (100 - pcts.get("avg_paragraph_len", 50)) * 0.15  # shorter paragraphs = faster pace
        + pcts.get("dialogue_ratio", 50) * 0.15
    )

    plot_score = round(max(0, min(100, plot_score)), 1)
    prose_score = round(max(0, min(100, prose_score)), 1)
    hook_score = round(max(0, min(100, hook_score)), 1)

    # Strengths / weaknesses
    strengths = []
    weaknesses = []
    if pcts.get("conflict_density", 50) > 70:
        strengths.append("冲突密度高，情节张力足")
    elif pcts.get("conflict_density", 50) < 30:
        weaknesses.append("冲突密度偏低，剧情推进感弱")

    if pcts.get("suspense_density", 50) > 70:
        strengths.append("悬念设置密集，读者翻页欲强")
    elif pcts.get("suspense_density", 50) < 30:
        weaknesses.append("悬念感不足，缺乏钩子")

    if pcts.get("dialogue_ratio", 50) > 70:
        strengths.append("对话占比高，节奏明快")
    elif pcts.get("dialogue_ratio", 50) < 20:
        weaknesses.append("对话太少，叙事偏静态")

    if pcts.get("word_ttr", 50) > 70:
        strengths.append("词汇丰富度高，文笔有变化")
    elif pcts.get("word_ttr", 50) < 30:
        weaknesses.append("用词重复度偏高")

    if pcts.get("entity_diversity", 50) > 70:
        strengths.append("人物/势力出场丰富，信息量大")
    elif pcts.get("entity_diversity", 50) < 30:
        weaknesses.append("出场人物单一，可能偏水")

    if pcts.get("scene_switch_rate", 50) > 70:
        strengths.append("场景切换频繁，空间感强")
    elif pcts.get("scene_switch_rate", 50) < 20:
        weaknesses.append("单一场景过长，节奏偏闷")

    # Recommendations
    recommendations = []
    if plot_score < 40:
        recommendations.append("建议引入新冲突或危机事件，打破当前平淡")
    if hook_score < 40:
        recommendations.append("建议在章节末尾设置悬念/反转钩子，提升翻页欲")
    if prose_score < 40:
        recommendations.append("建议增加对话或修辞变化，减少大段独白")
    if m.sentiment_net > 5 and pcts.get("suspense_density", 50) < 40:
        recommendations.append("情绪过于平顺，可考虑用意外事件打破")
    if m.sentiment_net < -3 and pcts.get("conflict_density", 50) < 40:
        recommendations.append("负面情绪缺乏出口，建议安排反击或转折")
    if not recommendations:
        if hook_score > 70:
            recommendations.append("本章节奏很好，后续可保持此模式")
        else:
            recommendations.append("整体均衡，可在悬念或冲突上再加点料")

    # Find similar chapters using key feature vector
    feature_keys = [
        "conflict_density", "suspense_density", "dialogue_ratio",
        "sentiment_net", "sentiment_tension", "scene_switch_rate",
    ]
    target_vec = {k: getattr(m, k) for k in feature_keys}
    sims = []
    for idx, (other_ch, other_m) in enumerate(zip(all_chapters, all_metrics)):
        if other_ch.global_index == ch.global_index:
            continue
        other_vec = {k: getattr(other_m, k) for k in feature_keys}
        sim = _cosine_similarity(target_vec, other_vec)
        sims.append((other_ch.global_index, other_ch.title, round(sim, 4)))
    sims.sort(key=lambda x: x[2], reverse=True)

    return QualityReport(
        metrics=m,
        plot_score=plot_score,
        prose_score=prose_score,
        hook_score=hook_score,
        percentiles=pcts,
        strengths=strengths,
        weaknesses=weaknesses,
        recommendations=recommendations,
        similar_chapters=sims[:5],
    )


def export_evaluation(
    report: QualityReport,
    out_path: Path,
    chapter_title: str = "输入章节",
    llm_section: Optional[str] = None,
    llm_error: Optional[str] = None,
    llm_truncated: bool = False,
    llm_model: Optional[str] = None,
) -> None:
    """Write a human-readable evaluation report."""
    lines = [
        f"# 章节质量评估报告：{chapter_title}\n",
        "## 综合评分\n",
        f"- **剧情质量**（冲突/悬念/信息量）：{report.plot_score}/100\n",
        f"- **文笔质量**（句式/词汇/修辞）：{report.prose_score}/100\n",
        f"- **钩子强度**（翻页欲/节奏感）：{report.hook_score}/100\n",
        "\n## 关键指标 vs 全书基准\n",
        "| 指标 | 本章值 | 全书百分位 |\n",
        "|---|---|---|\n",
    ]
    key_labels = {
        "conflict_density": "冲突密度",
        "suspense_density": "悬念密度",
        "dialogue_ratio": "对话占比",
        "word_ttr": "词汇丰富度(TTR)",
        "sentence_len_std": "句式变化度",
        "scene_switch_rate": "场景切换率",
        "entity_diversity": "出场人物数",
        "sentiment_net": "情绪净值",
        "sentiment_tension": "紧张度",
        "info_density": "信息密度",
        "rhetorical_density": "修辞密度",
    }
    for k, label in key_labels.items():
        val = getattr(report.metrics, k)
        pct = report.percentiles.get(k, 50)
        lines.append(f"| {label} | {val} | {pct}% |\n")

    if report.strengths:
        lines.append("\n## 亮点\n")
        for s in report.strengths:
            lines.append(f"- ✅ {s}\n")
    if report.weaknesses:
        lines.append("\n## 可改进点\n")
        for w in report.weaknesses:
            lines.append(f"- ⚠️ {w}\n")
    if report.recommendations:
        lines.append("\n## 剧情走向建议\n")
        for r in report.recommendations:
            lines.append(f"- 💡 {r}\n")

    if report.similar_chapters:
        lines.append("\n## 风格最相似的已有章节（供参考）\n")
        for idx, title, sim in report.similar_chapters:
            lines.append(f"- 第{idx}章《{title}》（相似度 {sim:.2f}）\n")

    if llm_section:
        lines.append("\n## LLM 编辑诊断\n")
        if llm_model:
            lines.append(f"> 模型：{llm_model}\n\n")
        if llm_truncated:
            lines.append("> 说明：章节正文超过限制，LLM 只接收了开头/中段/结尾摘录。\n\n")
        lines.append(llm_section.strip() + "\n")
    elif llm_error:
        lines.append("\n## LLM 编辑诊断\n")
        lines.append(f"> {llm_error}\n")

    out_path.write_text("".join(lines), encoding="utf-8")

"""Lexicon-based sentiment and emotion arc analysis."""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


# Simplified emotion lexicon tuned for cultivation/urban-fantasy novels.
POSITIVE_WORDS = {
    "开心", "高兴", "喜欢", "爱", "爽", "强", "赢", "成功", "突破", "升级",
    "牛逼", "厉害", "棒", "赞", "发财", "暴富", "幸福", "甜蜜", "笑", "喜",
    "顺利", "轻松", "舒服", "痛快", "骄傲", "自信", "希望", "温暖", "感动",
    "惊喜", "满意", "得意", "兴奋", "激动", "欢乐", "美好", "漂亮", "帅气",
}
NEGATIVE_WORDS = {
    "悲伤", "痛苦", "死", "死吧", "死啊", "杀", "杀啊", "哭", "泪", "痛",
    "输", "失败", "绝望", "恨", "怒", "愤怒", "惨", "糟", "坏", "恐怖",
    "可怕", "恶心", "讨厌", "烦", "焦虑", "担忧", "害怕", "恐惧", "孤独",
    "寂寞", "失落", "委屈", "无奈", "遗憾", "后悔", "愧疚", "心碎", "崩溃",
    "撕裂", "伤", "亡", "尸", "鬼魂", "阴森", "邪恶", "毒", "诅咒",
}
TENSION_WORDS = {
    "紧张", "危险", "逃", "跑", "追", "战", "战斗", "危机", "紧急", "危险",
    "偷袭", "伏击", "陷阱", "包围", "决斗", "拼命", "疯狂", "爆发", "冲",
    "快", "赶紧", "来不及", "小心", "警惕", "戒备", "厮杀", "激烈", "凶猛",
}


def score_text(text: str) -> Dict[str, float]:
    """Return emotion scores for a text block."""
    pos = sum(text.count(w) for w in POSITIVE_WORDS)
    neg = sum(text.count(w) for w in NEGATIVE_WORDS)
    tension = sum(text.count(w) for w in TENSION_WORDS)
    total = len(text)
    if total == 0:
        return {"positive": 0.0, "negative": 0.0, "tension": 0.0, "net": 0.0}
    return {
        "positive": round(pos * 1000 / total, 3),
        "negative": round(neg * 1000 / total, 3),
        "tension": round(tension * 1000 / total, 3),
        "net": round((pos - neg) * 1000 / total, 3),
    }


@dataclass
class ChapterSentiment:
    idx: int
    volume: str
    title: str
    overall: Dict[str, float] = field(default_factory=dict)
    first_half: Dict[str, float] = field(default_factory=dict)
    second_half: Dict[str, float] = field(default_factory=dict)


def analyze_sentiment(chapters: List) -> List[ChapterSentiment]:
    """Analyze per-chapter sentiment arc."""
    results = []
    for ch in chapters:
        body = ch.body
        mid = len(body) // 2
        results.append(ChapterSentiment(
            idx=ch.global_index,
            volume=ch.volume,
            title=ch.title,
            overall=score_text(body),
            first_half=score_text(body[:mid]),
            second_half=score_text(body[mid:]),
        ))
    return results


def export_sentiment(sentiments: List[ChapterSentiment], out_dir: Path) -> None:
    """Write sentiment JSON and a Markdown arc summary."""
    out_dir.mkdir(exist_ok=True)
    data = [vars(s) for s in sentiments]
    (out_dir / "sentiment_arc.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # Markdown summary
    lines = ["# 《地府微信群》情绪弧线\n"]
    lines.append("| 章 | 卷 | 标题 | 正面 | 负面 | 紧张 | 净值 |\n")
    lines.append("|---|---|---|---|---|---|---|\n")
    for s in sentiments:
        o = s.overall
        lines.append(
            f"| {s.idx:03d} | {s.volume[:6]}… | {s.title[:16]}… "
            f"| {o['positive']:.2f} | {o['negative']:.2f} | {o['tension']:.2f} | {o['net']:+.2f} |\n"
        )
    (out_dir / "情绪弧线.md").write_text("".join(lines), encoding="utf-8")

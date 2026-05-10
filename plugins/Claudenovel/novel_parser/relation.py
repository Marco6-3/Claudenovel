"""Rule-based relation triple extraction with optional jieba enhancement."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .normalizer import ENTITY_ALIASES
from .structure import Chapter

CANONICAL_NAMES: Set[str] = set(ENTITY_ALIASES.keys())
JIEBA_BACKEND = "unavailable"

RELATION_VERBS: Dict[str, str] = {
    "喜歡": "喜欢", "喜欢": "喜欢", "愛": "喜欢", "爱": "喜欢",
    "討厭": "讨厌", "讨厌": "讨厌", "恨": "讨厌",
    "殺": "杀死", "杀": "杀死", "殺死": "杀死", "杀死": "杀死",
    "救": "拯救", "拯救": "拯救", "救下": "拯救",
    "追": "追求", "追求": "追求", "追殺": "追杀", "追杀": "追杀",
    "打": "攻击", "打敗": "攻击", "打败": "攻击", "攻擊": "攻击", "攻击": "攻击",
    "保護": "保护", "保护": "保护", "護": "保护",
    "給": "给予", "给": "给予", "送": "给予", "贈": "给予", "赠": "给予",
    "命令": "命令", "叫": "命令", "讓": "命令", "让": "命令",
    "幫助": "帮助", "帮助": "帮助", "協助": "帮助", "协助": "帮助",
    "見到": "遇见", "遇见": "遇见", "碰到": "遇见", "遇到": "遇见",
    "離開": "离开", "离开": "离开", "走": "离开",
    "罵": "辱骂", "骂": "辱骂", "嘲諷": "辱骂", "嘲讽": "辱骂",
    "擁抱": "亲密", "拥抱": "亲密", "親": "亲密", "亲": "亲密", "牽手": "亲密", "牵手": "亲密",
    "打電話": "联系", "打电话": "联系", "發消息": "联系", "发消息": "联系",
    "背叛": "背叛", "欺騙": "欺骗", "欺骗": "欺骗",
}


def _extract_entities_in_window(
    text: str, center: int, radius: int = 40, names: Optional[Set[str]] = None,
) -> List[str]:
    if names is None:
        names = CANONICAL_NAMES
    start = max(0, center - radius)
    end = min(len(text), center + radius)
    window = text[start:end]
    found = sorted(
        (name for name in names if name in window),
        key=lambda name: window.find(name),
    )
    return found


def extract_relations_rule(
    chapters: List[Chapter],
    aliases: Optional[Dict[str, List[str]]] = None,
) -> List[Tuple[str, str, str]]:
    """Extract (subject, relation, object) by pattern matching around relation verbs.

    Args:
        chapters: Parsed chapter list.
        aliases: Optional dict of {canonical_name: [aliases]}.
                 If None, uses the built-in ENTITY_ALIASES.
    """
    names = set(aliases.keys()) if aliases is not None else CANONICAL_NAMES
    triples = []
    verb_pattern = re.compile(
        "(" + "|".join(map(re.escape, RELATION_VERBS.keys())) + ")"
    )
    for ch in chapters:
        for m in verb_pattern.finditer(ch.body):
            verb = m.group(0)
            rel_type = RELATION_VERBS[verb]
            nearby = _extract_entities_in_window(ch.body, m.start(), 60, names)
            if len(nearby) >= 2:
                triples.append((nearby[0], rel_type, nearby[1]))
    return triples


def extract_relation_events_rule(
    chapters: List[Chapter],
    aliases: Optional[Dict[str, List[str]]] = None,
    window_radius: int = 60,
) -> List[Dict[str, Any]]:
    """Extract relation events with chapter and paragraph evidence metadata."""
    names = set(aliases.keys()) if aliases is not None else CANONICAL_NAMES
    events: List[Dict[str, Any]] = []
    verb_pattern = re.compile(
        "(" + "|".join(map(re.escape, RELATION_VERBS.keys())) + ")"
    )
    for ch in chapters:
        for paragraph_index, paragraph in enumerate(ch.paragraphs, start=1):
            for m in verb_pattern.finditer(paragraph):
                verb = m.group(0)
                rel_type = RELATION_VERBS[verb]
                nearby = _extract_entities_in_window(paragraph, m.start(), window_radius, names)
                if len(nearby) < 2:
                    continue
                subject, obj = nearby[0], nearby[1]
                events.append({
                    "subject": subject,
                    "relation": rel_type,
                    "object": obj,
                    "chapter": ch.global_index,
                    "chapter_title": ch.title,
                    "paragraph": paragraph_index,
                    "evidence_id": f"CH{ch.global_index:03d}-P{paragraph_index:03d}",
                    "verb": verb,
                    "excerpt": paragraph[:240],
                })
    return events


def extract_relations_jieba(
    chapters: List[Chapter],
    aliases: Optional[Dict[str, List[str]]] = None,
) -> List[Tuple[str, str, str]]:
    """Jieba-enhanced: one POS-tag pass per chapter, then scan (nr, verb, nr) patterns.
    Much faster than per-window tagging (~30-60s for 1.3M chars total)."""
    global JIEBA_BACKEND
    names = set(aliases.keys()) if aliases is not None else CANONICAL_NAMES

    try:
        import jieba_fast as jieba
        import jieba_fast.posseg as pseg

        JIEBA_BACKEND = "jieba_fast"
    except ImportError:
        try:
            import jieba
            import jieba.posseg as pseg

            JIEBA_BACKEND = "jieba"
        except ImportError:
            JIEBA_BACKEND = "unavailable"
            return []

    for name in names:
        jieba.add_word(name, tag="nr")

    triples = []
    verb_set = set(RELATION_VERBS.keys())
    for ch in chapters:
        words = list(pseg.cut(ch.body))
        # Scan sliding window over the word list
        i = 0
        while i < len(words):
            w = words[i]
            if w.flag == "nr" and w.word in names:
                # look forward for a verb then another nr within next 12 words
                for j in range(i + 1, min(i + 12, len(words))):
                    mid = words[j]
                    if mid.word in verb_set and mid.flag.startswith("v"):
                        for k in range(j + 1, min(j + 8, len(words))):
                            end_w = words[k]
                            if end_w.flag == "nr" and end_w.word in names:
                                triples.append((w.word, RELATION_VERBS[mid.word], end_w.word))
                                i = k  # advance to avoid duplicate overlap
                                break
                        break
            i += 1
    return triples


def export_relations(
    chapters: List[Chapter],
    out_dir: Path,
    use_jieba: bool = False,
    jieba_chapter_limit: Optional[int] = None,
    jieba_cache_path: Optional[Path] = None,
    aliases: Optional[Dict[str, List[str]]] = None,
) -> None:
    out_dir.mkdir(exist_ok=True)
    rule_triples = extract_relations_rule(chapters, aliases=aliases)
    jieba_chapters = chapters
    if jieba_chapter_limit is not None:
        jieba_chapters = chapters[:max(0, jieba_chapter_limit)]
    jieba_cache_hit = False
    jieba_triples: List[Tuple[str, str, str]] = []
    if use_jieba:
        if jieba_cache_path and jieba_cache_path.exists():
            cached = json.loads(jieba_cache_path.read_text(encoding="utf-8"))
            jieba_triples = [tuple(item) for item in cached.get("triples", [])]
            jieba_cache_hit = True
        else:
            jieba_triples = extract_relations_jieba(jieba_chapters, aliases=aliases)
            if jieba_cache_path:
                jieba_cache_path.parent.mkdir(exist_ok=True)
                jieba_cache_path.write_text(
                    json.dumps(
                        {
                            "chapter_limit": jieba_chapter_limit,
                            "chapters_analyzed": len(jieba_chapters),
                            "triples": jieba_triples,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
    all_triples = rule_triples + jieba_triples
    counter = Counter(all_triples)
    data = {
        "total_triples": len(all_triples),
        "rule_based": len(rule_triples),
        "jieba_based": len(jieba_triples),
        "jieba_enabled": use_jieba,
        "jieba_backend": JIEBA_BACKEND if use_jieba else None,
        "jieba_chapters_analyzed": len(jieba_chapters) if use_jieba else 0,
        "jieba_chapter_limit": jieba_chapter_limit,
        "jieba_cache_path": str(jieba_cache_path) if jieba_cache_path else None,
        "jieba_cache_hit": jieba_cache_hit,
        "top_relations": [
            {"subject": s, "relation": r, "object": o, "count": c}
            for (s, r, o), c in counter.most_common(60)
        ],
    }
    (out_dir / "relation_triples.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

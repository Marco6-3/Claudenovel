"""Rule-based relation triple extraction with optional jieba enhancement."""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

from .normalizer import ENTITY_ALIASES
from .structure import Chapter

CANONICAL_NAMES = list(ENTITY_ALIASES.keys())

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


def _extract_entities_in_window(text: str, center: int, radius: int = 40) -> List[str]:
    start = max(0, center - radius)
    end = min(len(text), center + radius)
    window = text[start:end]
    found = [name for name in CANONICAL_NAMES if name in window]
    return found


def extract_relations_rule(chapters: List[Chapter]) -> List[Tuple[str, str, str]]:
    """Extract (subject, relation, object) by pattern matching around relation verbs."""
    triples = []
    # Build regex once
    verb_pattern = re.compile(
        "(" + "|".join(map(re.escape, RELATION_VERBS.keys())) + ")"
    )
    for ch in chapters:
        for m in verb_pattern.finditer(ch.body):
            verb = m.group(0)
            rel_type = RELATION_VERBS[verb]
            nearby = _extract_entities_in_window(ch.body, m.start(), 60)
            if len(nearby) >= 2:
                triples.append((nearby[0], rel_type, nearby[1]))
    return triples


def extract_relations_jieba(chapters: List[Chapter]) -> List[Tuple[str, str, str]]:
    """Optional: jieba POS-based relation extraction (slow on large texts)."""
    try:
        import jieba.posseg as pseg
    except ImportError:
        return []
    for name in CANONICAL_NAMES:
        import jieba
        jieba.add_word(name, tag="nr")
    triples = []
    for ch in chapters:
        words = list(pseg.cut(ch.body))
        names = [(w.word, i) for i, w in enumerate(words) if w.flag == "nr" and w.word in CANONICAL_NAMES]
        for i in range(len(names) - 1):
            a, idx_a = names[i]
            b, idx_b = names[i + 1]
            gap = words[idx_a + 1:idx_b]
            gap_str = "".join(w.word for w in gap)
            for verb, rel_type in RELATION_VERBS.items():
                if verb in gap_str:
                    triples.append((a, rel_type, b))
                    break
    return triples


def export_relations(chapters: List[Chapter], out_dir: Path, use_jieba: bool = False) -> None:
    out_dir.mkdir(exist_ok=True)
    rule_triples = extract_relations_rule(chapters)
    jieba_triples = extract_relations_jieba(chapters) if use_jieba else []
    all_triples = rule_triples + jieba_triples
    counter = Counter(all_triples)
    data = {
        "total_triples": len(all_triples),
        "rule_based": len(rule_triples),
        "jieba_based": len(jieba_triples),
        "top_relations": [
            {"subject": s, "relation": r, "object": o, "count": c}
            for (s, r, o), c in counter.most_common(60)
        ],
    }
    (out_dir / "relation_triples.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

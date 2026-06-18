"""Entity statistics with alias merging, dialogue attribution, scene-level co-occurrence."""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .entity_resolver import count_entity_mentions, ordered_unique_entities
from .normalizer import ENTITY_ALIASES
from .structure import Chapter


CANONICAL_NAMES = list(ENTITY_ALIASES.keys())
NAME_BLACKLIST = {
    "老师", "学生", "同学", "班长", "校医", "大爷", "老板", "护士", "医生",
    "教室", "学校", "图书馆", "房间", "手机", "试卷", "身体", "声音",
    "东西", "感觉", "时候", "自己", "什么", "这里", "那里", "一种",
    "一声", "一股", "一只", "一下", "眼前", "脑海", "小腹", "丹田",
    "朱砂", "修仙", "老中医", "中医", "西医", "冷汗", "安静", "啊啊啊",
    "高三", "阳光", "古老", "塞进", "明白", "之前", "最后",
}
COMMON_SURNAMES = set(
    "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
    "戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐"
    "费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平"
    "黄和穆萧尹欧阳凌白赵"
)
BAD_NAME_CHARS = set("的不一了是有在和与把被将让这那像又很更才都还没")
NON_PERSON_SUFFIXES = set("光霆符盘装家木晖皙铜雨声水汁寿座口嘴开大扎尾")


@dataclass
class EntityStats:
    occurrences: Counter
    chapter_span: Dict[str, List[int]]   # name -> [first, last, count]
    scene_cooccurrence: Counter          # (a,b) -> shared scene count
    dialogue_speakers: Counter           # name -> times inferred as speaker
    volume_distribution: Dict[str, Counter]  # volume -> Counter(name)


def discover_entity_aliases(
    chapters: List[Chapter],
    min_occurrences: int = 2,
    max_names: int = 80,
    include_builtin_present: bool = True,
    seed_aliases: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, List[str]]:
    """Discover likely character names from the current novel text.

    This keeps the parser usable for arbitrary novels instead of relying only on
    the built-in aliases for one source text.
    """
    counts: Counter = Counter()
    pseg_counts: Counter = Counter()
    speaker_counts: Counter = Counter()
    protected_names = set((seed_aliases or {}).keys())

    for ch in chapters:
        for d in ch.dialogues:
            if d.speaker_hint:
                hint = d.speaker_hint.strip()
                for name in re.findall(r"[\u4e00-\u9fff]{2,4}", hint):
                    speaker_counts[name] += 1

    try:
        import jieba.posseg as pseg

        for ch in chapters:
            for word, flag in pseg.cut(ch.body):
                if flag.startswith("nr") and 2 <= len(word) <= 4:
                    pseg_counts[word] += 1
    except ImportError:
        # Speaker hints plus built-in-present fallback still give a conservative list.
        pass

    if include_builtin_present:
        for ch in chapters:
            for name in CANONICAL_NAMES:
                n = ch.body.count(name)
                if n:
                    counts[name] += n

    for canonical, aliases in (seed_aliases or {}).items():
        for ch in chapters:
            for term in [canonical, *(aliases or [])]:
                n = ch.body.count(term)
                if n:
                    counts[canonical] += n

    counts.update(pseg_counts)
    for name, count in speaker_counts.items():
        if name in pseg_counts or (name and name[0] in COMMON_SURNAMES):
            counts[name] += count * 3

    filtered = Counter()
    for name, count in counts.items():
        if count < min_occurrences:
            continue
        speaker_count = speaker_counts.get(name, 0)
        if name in NAME_BLACKLIST:
            continue
        if any(ch in BAD_NAME_CHARS for ch in name):
            continue
        if name[0] not in COMMON_SURNAMES and name not in CANONICAL_NAMES:
            continue
        if not speaker_count and name[-1] in NON_PERSON_SUFFIXES:
            continue
        if any(token in name for token in ("第", "章", "卷")):
            continue
        filtered[name] = count

    for short in list(filtered):
        for long in list(filtered):
            if short == long or short not in filtered or long not in filtered:
                continue
            if len(short) >= 2 and long.startswith(short) and len(long) > len(short):
                # Prefix fragments such as "陈汉" should not beat full names like
                # "陈汉升". Keep explicit seed canonicals even when they are short.
                if short in protected_names:
                    del filtered[long]
                    continue
                if filtered[long] >= filtered[short] * 0.5:
                    del filtered[short]
                    break

    discovered = {name: [] for name, _ in filtered.most_common(max_names)}
    if seed_aliases:
        merged = dict(discovered)
        for name, aliases in seed_aliases.items():
            merged[name] = list(aliases or [])
        return merged
    return discovered


def infer_speakers(
    chapters: List[Chapter],
    aliases: Optional[Dict[str, Sequence[str]]] = None,
) -> Counter:
    """Count how many times each entity is inferred as a dialogue speaker."""
    if aliases is None:
        aliases = {name: values for name, values in ENTITY_ALIASES.items()}
    speakers = Counter()
    for ch in chapters:
        for d in ch.dialogues:
            if d.speaker_hint:
                matched = ordered_unique_entities(d.speaker_hint, aliases)
                if matched:
                    speakers[matched[0]] += 1
    return speakers


def compute_entity_stats(
    chapters: List[Chapter],
    aliases: Optional[Dict[str, List[str]]] = None,
) -> EntityStats:
    """Compute comprehensive entity statistics.

    Args:
        chapters: Parsed chapter list.
        aliases: Optional dict of {canonical_name: [aliases]}.
                 If None, uses the built-in ENTITY_ALIASES.
    """
    if aliases is None:
        aliases = {name: values for name, values in ENTITY_ALIASES.items()}
    occ = Counter()
    chapter_span: Dict[str, list] = defaultdict(lambda: [9999, 0, 0])
    scene_co = Counter()
    vol_dist: Dict[str, Counter] = defaultdict(Counter)

    for ch in chapters:
        vol_dist[ch.volume].update([])  # ensure volume exists
        present_in_chapter = set()
        chapter_counts = count_entity_mentions(ch.body, aliases)
        for name, n in chapter_counts.items():
            if n:
                occ[name] += n
                present_in_chapter.add(name)
                chapter_span[name][0] = min(chapter_span[name][0], ch.global_index)
                chapter_span[name][1] = max(chapter_span[name][1], ch.global_index)
                chapter_span[name][2] += 1
        # Scene-level co-occurrence (stricter than chapter-level)
        for sc in ch.scenes:
            scene_text = "\n".join(sc.paragraphs)
            present = set(ordered_unique_entities(scene_text, aliases)) if scene_text else set()
            present_list = sorted(present)
            for i, a in enumerate(present_list):
                for b in present_list[i + 1:]:
                    scene_co[tuple(sorted((a, b)))] += 1
        # Volume distribution
        for name in present_in_chapter:
            vol_dist[ch.volume][name] += chapter_counts[name]

    # Clean up spans
    clean_span = {}
    for name, (first, last, cnt) in chapter_span.items():
        clean_span[name] = [first, last, cnt]

    return EntityStats(
        occurrences=occ,
        chapter_span=clean_span,
        scene_cooccurrence=scene_co,
        dialogue_speakers=infer_speakers(chapters, aliases),
        volume_distribution=vol_dist,
    )


def export_entity_stats(stats: EntityStats, out_dir: Path) -> None:
    """Write entity stats to JSON."""
    out_dir.mkdir(exist_ok=True)
    data = {
        "occurrences": stats.occurrences.most_common(),
        "chapter_span": stats.chapter_span,
        "scene_cooccurrence_top": [[a, b, n] for (a, b), n in stats.scene_cooccurrence.most_common(80)],
        "dialogue_speakers": stats.dialogue_speakers.most_common(),
        "volume_distribution": {
            vol: ctr.most_common(15)
            for vol, ctr in stats.volume_distribution.items()
        },
    }
    (out_dir / "entity_stats.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

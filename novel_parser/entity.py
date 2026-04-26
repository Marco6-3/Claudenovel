"""Entity statistics with alias merging, dialogue attribution, scene-level co-occurrence."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

from .normalizer import ENTITY_ALIASES
from .structure import Chapter, Scene


CANONICAL_NAMES = list(ENTITY_ALIASES.keys())


@dataclass
class EntityStats:
    occurrences: Counter
    chapter_span: Dict[str, List[int]]   # name -> [first, last, count]
    scene_cooccurrence: Counter          # (a,b) -> shared scene count
    dialogue_speakers: Counter           # name -> times inferred as speaker
    volume_distribution: Dict[str, Counter]  # volume -> Counter(name)


def infer_speakers(chapters: List[Chapter]) -> Counter:
    """Count how many times each entity is inferred as a dialogue speaker."""
    speakers = Counter()
    for ch in chapters:
        for d in ch.dialogues:
            if d.speaker_hint:
                # fuzzy match speaker_hint against canonical names
                for name in CANONICAL_NAMES:
                    if name in d.speaker_hint or d.speaker_hint in name:
                        speakers[name] += 1
                        break
    return speakers


def compute_entity_stats(chapters: List[Chapter]) -> EntityStats:
    """Compute comprehensive entity statistics."""
    occ = Counter()
    chapter_span: Dict[str, list] = defaultdict(lambda: [9999, 0, 0])
    scene_co = Counter()
    vol_dist: Dict[str, Counter] = defaultdict(Counter)

    for ch in chapters:
        vol_dist[ch.volume].update([])  # ensure volume exists
        present_in_chapter = set()
        for name in CANONICAL_NAMES:
            n = ch.body.count(name)
            if n:
                occ[name] += n
                present_in_chapter.add(name)
                chapter_span[name][0] = min(chapter_span[name][0], ch.global_index)
                chapter_span[name][1] = max(chapter_span[name][1], ch.global_index)
                chapter_span[name][2] += 1
        # Scene-level co-occurrence (stricter than chapter-level)
        for sc in ch.scenes:
            present = {name for name in CANONICAL_NAMES if sc.paragraphs and any(name in p for p in sc.paragraphs)}
            present_list = sorted(present)
            for i, a in enumerate(present_list):
                for b in present_list[i + 1:]:
                    scene_co[tuple(sorted((a, b)))] += 1
        # Volume distribution
        for name in present_in_chapter:
            vol_dist[ch.volume][name] += ch.body.count(name)

    # Clean up spans
    clean_span = {}
    for name, (first, last, cnt) in chapter_span.items():
        clean_span[name] = [first, last, cnt]

    return EntityStats(
        occurrences=occ,
        chapter_span=clean_span,
        scene_cooccurrence=scene_co,
        dialogue_speakers=infer_speakers(chapters),
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

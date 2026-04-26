"""Main pipeline orchestrator."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from . import entity, normalizer, relation, sentiment, structure


def run_pipeline(txt_path: Path, out_dir: Path) -> dict:
    """Run the full enhanced analysis pipeline."""
    out_dir.mkdir(exist_ok=True)

    # 1. Read & normalize
    raw_text = normalizer.read_text(txt_path)
    text = normalizer.normalize_text(raw_text)

    # 2. Structural parsing
    chapters: List[structure.Chapter] = structure.parse_chapters(text)

    # 3. Entity stats (with aliases merged + scene-level cooccurrence)
    stats = entity.compute_entity_stats(chapters)
    entity.export_entity_stats(stats, out_dir)

    # 4. Relation triples
    relation.export_relations(chapters, out_dir)

    # 5. Sentiment arc
    sent = sentiment.analyze_sentiment(chapters)
    sentiment.export_sentiment(sent, out_dir)

    # 6. Enhanced TOC + briefs
    toc_lines = ["# 《地府微信群》卷章目录（增强版）\n"]
    briefs = []
    current_vol = None
    for ch in chapters:
        if ch.volume != current_vol:
            current_vol = ch.volume
            toc_lines.append(f"\n## {current_vol}\n")
        scene_locs = ", ".join(
            s.location_hint for s in ch.scenes if s.location_hint
        ) or "—"
        toc_lines.append(
            f"- {ch.global_index:03d}. {ch.title}（{ch.chars}字，"
            f"{len(ch.scenes)}场景，{len(ch.dialogues)}对话）"
        )
        briefs.append({
            "global_index": ch.global_index,
            "volume": ch.volume,
            "title": ch.title,
            "chars": ch.chars,
            "scene_count": len(ch.scenes),
            "dialogue_count": len(ch.dialogues),
            "scene_locations": [s.location_hint for s in ch.scenes],
            "first": ch.first,
            "last": ch.last,
        })

    (out_dir / "enhanced_toc.md").write_text(
        "\n".join(toc_lines), encoding="utf-8"
    )
    (out_dir / "enhanced_briefs.json").write_text(
        json.dumps(briefs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "file": txt_path.name,
        "chars": len(text),
        "chapters": len(chapters),
        "total_scenes": sum(len(c.scenes) for c in chapters),
        "total_dialogues": sum(len(c.dialogues) for c in chapters),
        "outputs": [p.name for p in out_dir.iterdir()],
    }

"""Analyze any novel with auto-detected or user-provided character list.

Usage:
    # Auto-detect characters + manual core list
    python analyze_custom_novel.py
        --txt "C:/Users/.../练气仙诀_合并章节.txt"
        --out-dir "C:/Users/.../练气仙诀_analysis"
        --core-character "凌默"
        --core-character "秦思妍"
        --core-character "赵灵瑶"

    # Or rely fully on auto-detection
    python analyze_custom_novel.py --txt novel.txt --auto-characters 15
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import jieba
import jieba.posseg as pseg


# ---------------------------------------------------------------------------
# Character auto-detection
# ---------------------------------------------------------------------------
def auto_detect_characters(text: str, top_k: int = 20) -> Dict[str, List[str]]:
    """Auto-detect likely character names from text using jieba POS + heuristics."""
    # Phase 1: jieba nr tags
    words = list(pseg.cut(text))
    nr_candidates = Counter()
    for w in words:
        if w.flag == "nr" and 2 <= len(w.word) <= 4:
            nr_candidates[w.word] += 1

    # Phase 2: validate with speaker cues
    SPEAKER_RE = re.compile(r"([\u4e00-\u9fff]{2,4})(?:说|道|喊|叫|问|答|冷笑|哼|叹|说道|问道|喃喃)")
    speaker_names = Counter()
    for m in SPEAKER_RE.finditer(text):
        name = m.group(1)
        if 2 <= len(name) <= 4 and not _is_likely_not_name(name):
            speaker_names[name] += 1

    # Phase 3: possessive patterns  XX的(手|脸|眼|心)
    POSS_RE = re.compile(r"([\u4e00-\u9fff]{2,4})的(?:手|脸|眼|心|身体|声音|目光|眉|头|背|胸口|肩膀|手臂)")
    poss_names = Counter()
    for m in POSS_RE.finditer(text):
        name = m.group(1)
        if 2 <= len(name) <= 4 and not _is_likely_not_name(name):
            poss_names[name] += 1

    # Combine scores
    combined: Dict[str, float] = {}
    for name, count in nr_candidates.most_common(top_k * 3):
        if _is_likely_not_name(name):
            continue
        combined[name] = combined.get(name, 0) + count * 1.0
    for name, count in speaker_names.most_common(top_k * 3):
        if _is_likely_not_name(name):
            continue
        combined[name] = combined.get(name, 0) + count * 3.0  # speaker cue is strong signal
    for name, count in poss_names.most_common(top_k * 3):
        if _is_likely_not_name(name):
            continue
        combined[name] = combined.get(name, 0) + count * 2.0

    # Filter: must appear at least 5 times
    filtered = {name: score for name, score in combined.items() if text.count(name) >= 5}
    top = sorted(filtered.items(), key=lambda x: x[1], reverse=True)[:top_k]

    # Build alias dict (canonical -> [aliases])
    aliases: Dict[str, List[str]] = {}
    for name, _ in top:
        aliases[name] = []
    return aliases


COMMON_WORDS = set("""
什么没有自己知道感觉看着发现心中意识虽然或者但是然后突然已经不过
因为所以只是现在这里这个那个怎么如果还是就是不要就是时间眼神声音
目光眼睛心里心中脸上手中身体周围地方世界事情问题样子时候情况原因
一下一个一些一种一直一起一定一样一切一般一口一下一下
死死紧紧慢慢缓缓默默悄悄静静呆呆愣愣傻傻痴痴
长长短短高高大大小小远远近近轻轻重重冷冷
""")


def _is_likely_not_name(name: str) -> bool:
    """Heuristic: filter out common words and phrases."""
    if name in COMMON_WORDS:
        return True
    # Filter words ending with common suffixes that are not names
    if name.endswith(("地", "得", "着", "了", "过", "看", "想", "知", "是", "有", "不", "没")):
        return True
    # Filter words starting with common prefixes
    if name.startswith(("但", "而", "或", "若", "虽", "因", "为", "与", "和", "在", "从", "把", "被")):
        return True
    # Filter if mostly common characters
    common_chars = set("的在是不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取完举色""")
    if len(set(name) & common_chars) >= len(name) - 1 and len(name) <= 3:
        return True
    return False


# ---------------------------------------------------------------------------
# Delegates to novel_parser.entity / relation with dynamic aliases
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Analyze any novel with auto-detected characters")
    parser.add_argument("--txt", type=Path, required=True, help="Novel text file")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory")
    parser.add_argument("--core-character", action="append", default=[], help="Core character names (manual)")
    parser.add_argument("--auto-characters", type=int, default=15, help="Auto-detect top N characters")
    parser.add_argument("--start", type=int, default=1, help="Start chapter")
    parser.add_argument("--end", type=int, default=0, help="End chapter (0=all)")
    args = parser.parse_args()

    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from novel_parser import normalizer, structure, sentiment, evaluator
    from novel_parser.entity import compute_entity_stats
    from novel_parser.relation import extract_relations_rule

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read
    print(f"[CustomNovel] Reading {args.txt.name}")
    raw = normalizer.read_text(args.txt)
    text = normalizer.normalize_text(raw)
    chapters = structure.parse_chapters(text)
    total = len(chapters)
    end = args.end or total
    selected = chapters[args.start - 1:end]
    print(f"[CustomNovel] Parsed {total} chapters, analyzing {args.start}-{end} ({len(selected)} chapters)")

    # Character detection
    if args.core_character:
        aliases = {name: [] for name in args.core_character}
        print(f"[CustomNovel] Using manual characters: {list(aliases.keys())}")
    else:
        print(f"[CustomNovel] Auto-detecting top {args.auto_characters} characters...")
        aliases = auto_detect_characters("\n".join(ch.body for ch in selected), top_k=args.auto_characters)
        print(f"[CustomNovel] Detected: {list(aliases.keys())}")

    # Entity stats
    print("[CustomNovel] Computing entity stats...")
    stats = compute_entity_stats(selected, aliases=aliases)

    # Relations
    print("[CustomNovel] Extracting relations...")
    relations = extract_relations_rule(selected, aliases=aliases)

    # Sentiment
    print("[CustomNovel] Analyzing sentiment...")
    sentiments = sentiment.analyze_sentiment(selected)

    # Evaluator metrics
    print("[CustomNovel] Computing quality metrics...")
    baseline = evaluator.build_baseline(selected)
    metrics = [evaluator.compute_metrics(ch) for ch in selected]

    # Build structured baseline JSON
    from collections import Counter as _Counter
    rel_counter = _Counter(relations)
    structured = {
        "entity_stats": {
            "top_20": [
                {"name": n, "count": c, "chapters": stats.chapter_span.get(n, [])}
                for n, c in stats.occurrences.most_common(20)
            ],
            "scene_cooccurrence_top15": [
                {"pair": list(pair), "count": cnt}
                for pair, cnt in stats.scene_cooccurrence.most_common(15)
            ],
        },
        "relations": {
            "total_triples": len(relations),
            "top_30": [
                {"subject": s, "relation": r, "object": o, "count": c}
                for (s, r, o), c in rel_counter.most_common(30)
            ],
        },
        "sentiment": [{"chapter": s.idx, "title": s.title, **s.overall} for s in sentiments],
        "chapter_metrics": [
            {
                "chapter": ch.global_index,
                "chars": m.chars,
                "scenes": m.scene_count,
                "dialogues": m.dialogue_count,
                "dialogue_ratio": m.dialogue_ratio,
                "conflict_density": m.conflict_density,
                "suspense_density": m.suspense_density,
                "word_ttr": m.word_ttr,
                "sentiment_tension": m.sentiment_tension,
            }
            for ch, m in zip(selected, metrics)
        ],
    }

    structured_path = out_dir / "structured_baseline.json"
    structured_path.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[CustomNovel] Structured baseline saved: {structured_path}")

    # Build memory summary
    from novel_parser.memory_rag import build_memory_summary, export_memory_summary
    mem = build_memory_summary(structured, batch_id=f"ch{args.start}_{end}", chapter_start=args.start, chapter_end=end)
    mem_path = out_dir / "memory_summary.json"
    export_memory_summary(mem, mem_path)
    print(f"[CustomNovel] Memory summary saved: {mem_path}")

    # Print key findings
    print("\n" + "=" * 60)
    print("KEY FINDINGS")
    print("=" * 60)
    print(f"Chapters: {args.start}-{end} ({len(selected)} chapters)")
    print(f"Word count: {mem.word_count:,}")
    print(f"Top characters:")
    for name, count in stats.occurrences.most_common(10):
        span = stats.chapter_span.get(name, [0, 0, 0])
        print(f"  {name}: {count} times, chapters {span[0]}-{span[1]}")
    print(f"\nSentiment keypoints:")
    for pt in mem.sentiment_keypoints[:8]:
        print(f"  Ch{pt['chapter']} ({pt['title']}): {pt['type']} (net={pt.get('net', 'n/a')})")
    print(f"\nQuality trend:")
    print(f"  Dialogue ratio: {mem.quality_trend.get('avg_dialogue_ratio', 'n/a')}%")
    print(f"  Conflict density: {mem.quality_trend.get('avg_conflict_density', 'n/a')}/1000 chars")
    print(f"  Suspense density: {mem.quality_trend.get('avg_suspense_density', 'n/a')}/1000 chars")
    print(f"  Hook trend: {mem.quality_trend.get('hook_trend', 'n/a')}")
    print(f"\nUnsolved hooks:")
    for h in mem.unsolved_hooks[:5]:
        print(f"  - {h}")
    print("=" * 60)


if __name__ == "__main__":
    main()

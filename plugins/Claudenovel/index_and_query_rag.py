"""CLI for NovelRAG: index a novel and query it.

Usage:
    # Index chapters 1-50
    python index_and_query_rag.py --index --start 1 --end 50

    # Query the indexed RAG
    python index_and_query_rag.py --query "陈默和秦思妍感情转折点"

    # Query with metadata filters
    python index_and_query_rag.py --query "紧张战斗场面" --filter-chapter-min 30 --filter-chapter-max 40

    # Build memory summary only (no embedding API calls)
    python index_and_query_rag.py --memory-only --start 1 --end 50
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from novel_parser import llm_client, normalizer, structure
from novel_parser.memory_rag import (
    MemorySummary,
    NovelRAG,
    build_memory_summary,
    export_memory_summary,
    run_rag_indexing,
)


ROOT = Path(__file__).resolve().parent
TXT = next(ROOT.glob("*.txt"))
OUT = ROOT / "novel_rag_output"


def main() -> None:
    parser = argparse.ArgumentParser(description="NovelRAG: Hybrid retrieval + memory for novel analysis")
    parser.add_argument("--index", action="store_true", help="Build RAG index from novel")
    parser.add_argument("--query", type=str, default="", help="Natural language query")
    parser.add_argument("--start", type=int, default=1, help="First chapter (1-based)")
    parser.add_argument("--end", type=int, default=50, help="Last chapter (inclusive)")
    parser.add_argument("--top-k", type=int, default=10, help="Number of results to return")
    parser.add_argument("--filter-characters", type=str, default="", help="Comma-separated character names")
    parser.add_argument("--filter-chapter-min", type=int, default=0, help="Min chapter index filter")
    parser.add_argument("--filter-chapter-max", type=int, default=9999, help="Max chapter index filter")
    parser.add_argument("--filter-sentiment-net-min", type=float, default=None, help="Min sentiment net")
    parser.add_argument("--memory-only", action="store_true", help="Only build structured memory, no embedding/RAG")
    parser.add_argument("--memory-input", type=Path, default=None, help="Load previous memory_summary.json for cross-batch")
    parser.add_argument("--txt-path", type=Path, default=TXT, help="Novel text path")
    parser.add_argument("--out-dir", type=Path, default=OUT, help="Output directory")
    args = parser.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(exist_ok=True)

    # ── Memory-only mode: no API calls ──
    if args.memory_only:
        from novel_parser.entity import compute_entity_stats, discover_entity_aliases
        from novel_parser.evaluator import build_baseline, compute_metrics
        from novel_parser.relation import extract_relation_events_rule, extract_relations_rule
        from novel_parser.sentiment import analyze_sentiment

        print(f"[MemoryOnly] Reading {args.txt_path.name}")
        raw = normalizer.read_text(args.txt_path)
        apply_aliases = args.txt_path.resolve() == TXT.resolve()
        text = normalizer.normalize_text(raw, apply_aliases=apply_aliases)
        chapters = structure.parse_chapters(text)
        end = args.end if args.end <= len(chapters) else len(chapters)
        selected = chapters[args.start - 1:end]
        print(f"[MemoryOnly] Chapters {args.start}-{end} ({len(selected)} chapters)")

        aliases = discover_entity_aliases(selected, include_builtin_present=apply_aliases)
        print(f"[MemoryOnly] Discovered {len(aliases)} candidate entities")
        stats = compute_entity_stats(selected, aliases=aliases)
        relation_events = extract_relation_events_rule(selected, aliases=aliases)
        relations = [
            (event["subject"], event["relation"], event["object"])
            for event in relation_events
        ]
        sentiments = analyze_sentiment(selected)
        metrics = [compute_metrics(ch) for ch in selected]

        from collections import Counter
        rel_counter = Counter(relations)
        structured = {
            "entity_stats": {
                "top_20": [{"name": n, "count": c, "chapters": stats.chapter_span.get(n, [])}
                           for n, c in stats.occurrences.most_common(20)],
            },
            "relations": {
                "top_30": [
                    {
                        "subject": s,
                        "relation": r,
                        "object": o,
                        "count": c,
                        "first_chapter": min(
                            event["chapter"]
                            for event in relation_events
                            if (event["subject"], event["relation"], event["object"]) == (s, r, o)
                        ),
                        "evidence_ids": [
                            event["evidence_id"]
                            for event in relation_events
                            if (event["subject"], event["relation"], event["object"]) == (s, r, o)
                        ][:5],
                    }
                    for (s, r, o), c in rel_counter.most_common(30)
                ],
            },
            "sentiment": [{"chapter": s.idx, "title": s.title, **s.overall} for s in sentiments],
            "chapter_metrics": [{
                "chapter": ch.global_index,
                "chars": m.chars,
                "dialogue_ratio": m.dialogue_ratio,
                "conflict_density": m.conflict_density,
                "suspense_density": m.suspense_density,
            } for ch, m in zip(selected, metrics)],
        }

        prev_mem = None
        if args.memory_input and args.memory_input.exists():
            print(f"[MemoryOnly] Loading previous memory from {args.memory_input}")
            with args.memory_input.open("r", encoding="utf-8") as f:
                prev_data = json.load(f)
            prev_mem = MemorySummary(
                batch_id=prev_data.get("batch_id", ""),
                chapter_range=tuple(prev_data.get("chapter_range", [0, 0])),
                word_count=prev_data.get("word_count", 0),
                cumulative_character_occurrence=prev_data.get("cumulative_top_characters", {}),
                character_arc=prev_data.get("character_arc", {}),
            )

        mem = build_memory_summary(
            structured,
            batch_id=f"ch{args.start}_{end}",
            chapter_start=args.start,
            chapter_end=end,
            previous_memory=prev_mem,
        )
        export_memory_summary(mem, out_dir / "memory_summary.json")
        print(f"[MemoryOnly] Memory exported to {out_dir / 'memory_summary.json'}")
        print(json.dumps({
            "batch_id": mem.batch_id,
            "chapter_range": mem.chapter_range,
            "word_count": mem.word_count,
            "unsolved_hooks": mem.unsolved_hooks,
            "editor_notes": mem.editor_notes,
        }, ensure_ascii=False, indent=2))
        return

    # ── Index mode ──
    if args.index:
        rag = run_rag_indexing(
            args.txt_path,
            out_dir,
            args.start,
            args.end,
            apply_aliases=args.txt_path.resolve() == TXT.resolve(),
        )
        print(f"\n[Index] Done. RAG DB: {out_dir / 'rag_db'}")
        print(f"[Index] Memory: {out_dir / 'memory_summary.json'}")
        return

    # ── Query mode ──
    if args.query:
        rag_db_dir = out_dir / "rag_db"
        if not rag_db_dir.exists():
            print(f"[Query] RAG index not found at {rag_db_dir}. Run with --index first.")
            return

        from novel_parser.memory_rag import NovelRAG

        rag = NovelRAG.load(rag_db_dir)
        filters = {}
        if args.filter_characters:
            filters["characters"] = [c.strip() for c in args.filter_characters.split(",")]
        if args.filter_chapter_min > 0:
            filters["chapter_min"] = args.filter_chapter_min
        if args.filter_chapter_max < 9999:
            filters["chapter_max"] = args.filter_chapter_max
        if args.filter_sentiment_net_min is not None:
            filters["sentiment_net_min"] = args.filter_sentiment_net_min

        results = rag.query(args.query, top_k=args.top_k, filters=filters or None)

        print(f"\n[Query] '{args.query}' — {len(results)} results\n")
        for i, rc in enumerate(results, 1):
            ch = rc.chunk
            print(f"  [{i:2d}] {ch.id} | {ch.chapter_title} | "
                  f"dense={rc.dense_score:.3f} bm25={rc.bm25_score:.2f} rrf={rc.rrf_score:.4f}")
            print(f"       地点:{ch.location_hint} 人物:{','.join(ch.characters_present[:5])} "
                  f"情绪净值:{ch.sentiment_net:+.1f}")
            preview = ch.text[:120].replace("\n", " ")
            print(f"       {preview}...\n")
        return

    parser.print_help()


if __name__ == "__main__":
    main()

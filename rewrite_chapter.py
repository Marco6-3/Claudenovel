r"""CLI for chapter-by-chapter rewrite framework.

Usage:
    # Mode A: Author review mode (only diagnosis + suggestions, no rewrite)
    python rewrite_chapter.py \
        --chapter-file "C:\Users\...\第32章 营救.txt" \
        --memory "C:\Users\...\memory_summary.json" \
        --novel "C:\Users\...\练气仙诀_合并章节.txt" \
        --review-only

    # Mode B: Full rewrite (diagnosis + suggestions + LLM rewrite)
    python rewrite_chapter.py \
        --chapter-file "C:\Users\...\第32章 营救.txt" \
        --memory "C:\Users\...\memory_summary.json" \
        --novel "C:\Users\...\练气仙诀_合并章节.txt" \
        --out-dir "C:\Users\...\rewritten"

    # Mode C: Batch rewrite multiple chapters
    python rewrite_chapter.py \
        --chapter-dir "C:\Users\...\章节内容" \
        --memory "C:\Users\...\memory_summary.json" \
        --novel "C:\Users\...\练气仙诀_合并章节.txt" \
        --start 30 --end 35
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from novel_parser import chapter_rewriter, evaluator, normalizer, structure


def main() -> None:
    parser = argparse.ArgumentParser(description="Chapter rewriter: diagnose, suggest, and optionally rewrite.")
    parser.add_argument("--chapter-file", type=Path, help="Single chapter text file to rewrite")
    parser.add_argument("--chapter-dir", type=Path, help="Directory containing chapter .txt files")
    parser.add_argument("--memory", type=Path, help="memory_summary.json for cross-batch context")
    parser.add_argument("--novel", type=Path, help="Full novel text (for baseline computation)")
    parser.add_argument("--out-dir", type=Path, default=Path("rewritten"), help="Output directory")
    parser.add_argument("--review-only", action="store_true", help="Only generate diagnosis + suggestions, skip LLM rewrite")
    parser.add_argument("--start", type=int, default=1, help="Start chapter for batch mode")
    parser.add_argument("--end", type=int, default=0, help="End chapter for batch mode (0=all)")
    parser.add_argument(
        "--apply-aliases",
        action="store_true",
        help="Apply built-in aliases when the baseline novel is the repository default text.",
    )
    args = parser.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load memory
    memory_summary = None
    if args.memory and args.memory.exists():
        memory_summary = json.loads(args.memory.read_text(encoding="utf-8"))
        print(f"[CLI] Loaded memory: {args.memory}")

    # Load novel for baseline
    all_chapters = None
    baseline = None
    if args.novel and args.novel.exists():
        print(f"[CLI] Parsing novel for baseline: {args.novel.name}")
        raw = normalizer.read_text(args.novel)
        text = normalizer.normalize_text(raw, apply_aliases=args.apply_aliases)
        all_chapters = structure.parse_chapters(text)
        baseline = evaluator.build_baseline(all_chapters)
        print(f"[CLI] Baseline built from {len(all_chapters)} chapters")

    # Single chapter mode
    if args.chapter_file:
        chapter_text = args.chapter_file.read_text(encoding="utf-8")
        # Try to extract title from first line
        title = args.chapter_file.stem
        chapter_index = 0
        # Try parse "第XX章" from title
        m = re.search(r"第(\d+)章", title)
        if m:
            chapter_index = int(m.group(1))

        print(f"[CLI] Processing single chapter: {title} (index {chapter_index})")
        result = chapter_rewriter.rewrite_chapter(
            chapter_text=chapter_text,
            chapter_title=title,
            chapter_index=chapter_index,
            all_chapters=all_chapters,
            baseline=baseline,
            memory_summary=memory_summary,
            out_dir=out_dir,
            skip_rewrite=args.review_only,
        )
        print(f"[CLI] Done. Elapsed: {result.elapsed_seconds:.1f}s")
        return

    # Batch mode
    if args.chapter_dir:
        chapter_files = sorted(
            [f for f in args.chapter_dir.iterdir() if f.suffix == ".txt"],
            key=lambda f: f.name,
        )
        end = args.end or len(chapter_files)
        selected = chapter_files[args.start - 1:end]
        print(f"[CLI] Batch mode: {len(selected)} chapters ({args.start}-{end})")

        for ch_file in selected:
            chapter_text = ch_file.read_text(encoding="utf-8")
            title = ch_file.stem
            chapter_index = 0
            m = re.search(r"第(\d+)章", title)
            if m:
                chapter_index = int(m.group(1))

            print(f"\n[CLI] === {title} ===")
            try:
                result = chapter_rewriter.rewrite_chapter(
                    chapter_text=chapter_text,
                    chapter_title=title,
                    chapter_index=chapter_index,
                    all_chapters=all_chapters,
                    baseline=baseline,
                    memory_summary=memory_summary,
                    out_dir=out_dir,
                    skip_rewrite=args.review_only,
                )
                print(f"[CLI] Done: {title} ({result.elapsed_seconds:.1f}s)")
            except Exception as exc:
                print(f"[CLI] ERROR processing {title}: {exc}")
                continue
        return

    parser.print_help()


if __name__ == "__main__":
    main()

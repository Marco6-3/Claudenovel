r"""CLI for report-driven novel continuation.

Generate the next chapter based on an editorial diagnosis report's
continuation routes.

Usage:
    # List available routes in a report
    python continue_novel.py --report "novel_analysis_enhanced/editorial_revision_report.md" --list

    # Generate chapter using route 0
    python continue_novel.py \
        --report "novel_analysis_enhanced/editorial_revision_report.md" \
        --route 0 \
        --novel "apk.tw_地府微信群.txt" \
        --chapter-num 441

    # With memory and custom word count
    python continue_novel.py \
        --report "novel_analysis_enhanced/editorial_revision_report.md" \
        --route 2 \
        --novel "apk.tw_地府微信群.txt" \
        --memory "memory_summary.json" \
        --lookback 3 \
        --target-words 4000 \
        --chapter-num 441 \
        --out-dir "continued"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from novel_parser.continuation_writer import generate_continuation, list_routes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate next chapter from editorial report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--report", type=Path, required=True,
        help="Path to editorial report markdown",
    )
    parser.add_argument(
        "--list", action="store_true", dest="list_routes",
        help="List available continuation routes and exit",
    )
    parser.add_argument(
        "--route", type=int, default=0,
        help="Route index to follow (default: 0)",
    )
    parser.add_argument(
        "--novel", type=Path, default=None,
        help="Full novel text file (for style reference)",
    )
    parser.add_argument(
        "--memory", type=Path, default=None,
        help="memory_summary.json for cross-batch context",
    )
    parser.add_argument(
        "--lookback", type=int, default=3,
        help="Number of recent chapters for style reference (default: 3)",
    )
    parser.add_argument(
        "--target-words", type=int, default=3000,
        help="Target word count for generated chapter (default: 3000)",
    )
    parser.add_argument(
        "--chapter-num", type=int, default=0,
        help="Chapter number for the new chapter (auto-detect if 0)",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=Path("continued"),
        help="Output directory (default: continued)",
    )
    args = parser.parse_args()

    if not args.report.exists():
        print(f"Error: Report not found: {args.report}")
        sys.exit(1)

    # List mode
    if args.list_routes:
        list_routes(args.report)
        return

    # Generate mode
    print(f"[CLI] Report: {args.report}")
    print(f"[CLI] Route: {args.route}")
    if args.novel:
        print(f"[CLI] Novel: {args.novel}")
    if args.memory:
        print(f"[CLI] Memory: {args.memory}")

    try:
        result = generate_continuation(
            report_path=args.report,
            route_index=args.route,
            novel_path=args.novel,
            memory_path=args.memory,
            lookback_chapters=args.lookback,
            target_words=args.target_words,
            chapter_num=args.chapter_num,
            out_dir=args.out_dir,
        )
        print(f"\n[CLI] Done! Chapter {result.chapter_num} generated ({result.elapsed_seconds:.1f}s)")
        print(f"[CLI] Route: {result.route_name}")
        print(f"[CLI] Model: {result.model_used}")
        print(f"[CLI] Characters: {len(result.generated_text)}")
    except Exception as exc:
        print(f"\n[CLI] Error: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()

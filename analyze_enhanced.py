"""Enhanced novel analysis entry point."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from novel_parser.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parent
TXT = next(ROOT.glob("*.txt"))
OUT = ROOT / "novel_analysis_enhanced"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run enhanced novel analysis. Jieba POS extraction is optional and disabled by default."
    )
    parser.add_argument(
        "--use-jieba",
        action="store_true",
        help="Enable optional jieba POS relation extraction. This can be slow on the full novel.",
    )
    parser.add_argument(
        "--jieba-chapter-limit",
        type=int,
        default=None,
        help="Only run jieba on the first N chapters. Useful for quick validation.",
    )
    parser.add_argument(
        "--jieba-cache",
        action="store_true",
        help="Cache optional jieba relation extraction results in the output directory.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=OUT,
        help="Output directory. Defaults to novel_analysis_enhanced.",
    )
    parser.add_argument(
        "--evaluate-chapter",
        type=int,
        default=None,
        help="Generate a quality evaluation report for chapter N.",
    )
    parser.add_argument(
        "--evaluate-file",
        type=Path,
        default=None,
        help="Evaluate a user-provided chapter text file against the novel baseline.",
    )
    parser.add_argument(
        "--llm-report",
        action="store_true",
        help="Generate an OpenAI-compatible LLM editorial report for --evaluate-file.",
    )
    parser.add_argument(
        "--llm-max-chars",
        type=int,
        default=12000,
        help="Maximum chapter text characters sent to the LLM before excerpting.",
    )
    parser.add_argument(
        "--output-name",
        default="input_chapter_evaluation.md",
        help="Output filename for --evaluate-file reports.",
    )
    parser.add_argument(
        "--build-context",
        action="store_true",
        help="Build an evidence-grounded LLM context pack and prompt.",
    )
    parser.add_argument(
        "--context-query",
        default="",
        help="Analysis question used to rank evidence paragraphs.",
    )
    parser.add_argument(
        "--focus-entity",
        action="append",
        default=[],
        help="Focus entity/name to prioritize. Can be repeated.",
    )
    parser.add_argument(
        "--context-max-items",
        type=int,
        default=80,
        help="Maximum evidence paragraphs before context budget fitting.",
    )
    parser.add_argument(
        "--context-excerpt-chars",
        type=int,
        default=900,
        help="Maximum characters kept from each evidence paragraph.",
    )
    parser.add_argument(
        "--context-max-chars",
        type=int,
        default=80000,
        help="Rough character budget for the generated prompt evidence section.",
    )
    args = parser.parse_args()

    result = run_pipeline(
        TXT,
        args.out_dir,
        use_jieba=args.use_jieba,
        jieba_chapter_limit=args.jieba_chapter_limit,
        use_jieba_cache=args.jieba_cache,
        evaluate_chapter=args.evaluate_chapter,
        evaluate_file=args.evaluate_file,
        llm_report=args.llm_report,
        llm_max_chars=args.llm_max_chars,
        output_name=args.output_name,
        build_context=args.build_context,
        context_query=args.context_query,
        focus_entities=args.focus_entity,
        context_max_items=args.context_max_items,
        context_excerpt_chars=args.context_excerpt_chars,
        context_max_chars=args.context_max_chars,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

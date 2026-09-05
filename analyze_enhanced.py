"""Enhanced novel analysis entry point."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from novel_parser.output_layout import build_organized_output, write_main_report
from novel_parser.pipeline import run_pipeline


ROOT = Path(__file__).resolve().parent
TXT = ROOT / "apk.tw_地府微信群.txt"
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
        default=None,
        help="Output directory. Defaults to novel_analysis_enhanced, or a task folder when --organized-output is used.",
    )
    parser.add_argument(
        "--txt-path",
        type=Path,
        default=TXT if TXT.is_file() else None,
        help="Novel text path. Required when the bundled default novel is absent.",
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
    parser.add_argument(
        "--llm-context-report",
        action="store_true",
        help="Call the configured LLM with a generated or existing evidence context prompt.",
    )
    parser.add_argument(
        "--common-workflow",
        action="store_true",
        help=(
            "Export common files: detailed original-text LLM pack, review evidence, "
            "and review/improve/continuation prompt."
        ),
    )
    parser.add_argument(
        "--source-start",
        type=int,
        default=None,
        help="First chapter included in the detailed original-text source pack.",
    )
    parser.add_argument(
        "--source-end",
        type=int,
        default=None,
        help="Last chapter included in the detailed original-text source pack.",
    )
    parser.add_argument(
        "--source-max-chars",
        type=int,
        default=0,
        help="Rough character budget for the detailed source pack. 0 means no budget limit.",
    )
    parser.add_argument(
        "--context-prompt",
        type=Path,
        default=None,
        help="Existing llm_context_prompt.md path to send to the configured LLM.",
    )
    parser.add_argument(
        "--llm-output-name",
        default="llm_context_report.md",
        help="Output filename for --llm-context-report.",
    )
    parser.add_argument(
        "--organized-output",
        action="store_true",
        help="Use task-root/report.md plus task-root/data/ for generated base data.",
    )
    args = parser.parse_args()
    if args.txt_path is None:
        parser.error("请通过 --txt-path 指定小说文件。")
    apply_aliases = args.txt_path.resolve() == TXT.resolve()
    task_name = args.context_query or args.output_name or "小说分析"
    layout = build_organized_output(args.txt_path, task_name, args.out_dir) if args.organized_output else None
    output_dir = layout.data_dir if layout else (args.out_dir or OUT)

    result = run_pipeline(
        args.txt_path,
        output_dir,
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
        common_workflow=args.common_workflow,
        source_start=args.source_start,
        source_end=args.source_end,
        source_max_chars=args.source_max_chars,
        apply_aliases=apply_aliases,
    )
    if args.llm_context_report:
        from novel_parser import llm_client

        prompt_path = args.context_prompt or (output_dir / "llm_context_prompt.md")
        prompt_text = prompt_path.read_text(encoding="utf-8")
        content, model = llm_client.generate_context_report(prompt_text)
        out_path = layout.report_path if layout else (output_dir / args.llm_output_name)
        out_path.write_text(
            f"# LLM 证据化分析报告\n\n> 模型：{model}\n> 输入提示词：{prompt_path}\n\n{content}\n",
            encoding="utf-8",
        )
        result["llm_context_report"] = str(out_path)
        result["llm_context_model"] = model
    elif layout:
        write_main_report(
            layout,
            "小说分析任务报告",
            _render_organized_pipeline_report(result),
            data_dir_label="data",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _render_organized_pipeline_report(result: dict) -> str:
    lines = [
        "## 任务概况\n\n",
        f"- 文件：{result.get('file')}\n",
        f"- 字数：{result.get('chars')}\n",
        f"- 章节数：{result.get('chapters')}\n",
        f"- 场景数：{result.get('total_scenes')}\n",
        f"- 对话数：{result.get('total_dialogues')}\n\n",
        "## 主要产物\n\n",
    ]
    common_output = result.get("common_output") or {}
    context_output = result.get("context_output") or {}
    if common_output:
        lines.extend(
            [
                f"- 原文输入包：`data/{common_output.get('source_pack')}`\n",
                f"- 编辑诊断提示词：`data/{common_output.get('editorial_revision_prompt')}`\n",
                f"- 证据包：`data/{common_output.get('review_evidence_pack')}`\n",
            ]
        )
    if context_output:
        lines.extend(
            [
                f"- 上下文提示词：`data/{context_output.get('prompt_output')}`\n",
                f"- 上下文证据包：`data/{context_output.get('evidence_output')}`\n",
            ]
        )
    if result.get("evaluation_output"):
        lines.append(f"- 评价报告：`data/{result.get('evaluation_output')}`\n")
    lines.extend(
        [
            "\n## 说明\n\n",
            "本文件是任务入口报告；底座生成的结构化数据、证据包、提示词和缓存统一放在 `data/` 目录。\n",
            "如果需要最终自然语言深度报告，请在同一任务目录下运行 LLM 报告命令，或使用深度问答入口生成指定问题报告。\n",
        ]
    )
    return "".join(lines)


if __name__ == "__main__":
    main()

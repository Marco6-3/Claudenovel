"""Compare direct LLM analysis vs hybrid (structured + LLM) analysis.

Usage:
    python compare_approaches.py --start 1 --end 50 --batch-size 5
    python compare_approaches.py --start 1 --end 5   # quick test
    python compare_approaches.py --start 1 --end 50 --include-rag  # include RAG as third approach
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Optional

from novel_parser import llm_client, normalizer, structure
from novel_parser.direct_llm_analyzer import (
    analyze_novel_direct,
    export_direct_results,
)
from novel_parser.hybrid_analyzer import (
    StructuredContext,
    analyze_novel_hybrid,
    build_structured_context,
    export_hybrid_results,
    export_structured_baseline,
)


ROOT = Path(__file__).resolve().parent
TXT = next(ROOT.glob("*.txt"))
OUT = ROOT / "novel_analysis_comparison"


def progress(msg: str) -> None:
    print(f"  [{time.strftime('%H:%M:%S')}] {msg}")


def build_comparison_prompt(direct_data: dict, hybrid_data: dict, structured_data: dict, rag_data: Optional[dict] = None) -> str:
    """Build a prompt for LLM to compare the two (or three) approaches."""
    n_chapters = direct_data.get('total_chapters', '?')
    method_count = '三种' if rag_data else '两种'

    lines = [
        f"你是一名小说分析方法论专家。以下是对同一组章节（第{n_chapters}章）的{method_count}分析方法的结果。",
        "",
        "## 方法 A：纯 LLM 直接分析",
        "不提供任何预处理数据，完全由 LLM 自行从原文中提取信息。",
        "",
        f"### 识别出的人物（{len(direct_data.get('characters', []))}个）",
        "```json",
        json.dumps(direct_data.get('characters', [])[:30], ensure_ascii=False, indent=2),
        "```",
        "",
        f"### 发现的关系三元组（{len(direct_data.get('relationships', []))}条）",
        "```json",
        json.dumps(direct_data.get('relationships', [])[:40], ensure_ascii=False, indent=2),
        "```",
        "",
        "### 情感判断",
        "```json",
        json.dumps(direct_data.get('sentiment_per_chapter', [])[:10], ensure_ascii=False, indent=2),
        "```",
        "",
        "### 质量评分",
        "```json",
        json.dumps(direct_data.get('quality_scores', [])[:10], ensure_ascii=False, indent=2),
        "```",
        "",
        "### API 成本",
        f"- 输入字符数：{direct_data.get('cost', {}).get('total_input_chars', '?')}",
        f"- 耗时：{direct_data.get('cost', {}).get('total_elapsed_seconds', '?')}秒",
        f"- 批次数：{direct_data.get('cost', {}).get('batch_count', '?')}",
        "",
        "---",
        "",
        "## 方法 B：混合架构（结构化预处理 + LLM）",
        "先用规则/词典做结构化分析（人物统计、关系抽取、情感打分、结构指标），再将结果交给 LLM。",
        "",
        f"### 识别出的人物（{len(hybrid_data.get('characters', []))}个）",
        "```json",
        json.dumps(hybrid_data.get('characters', [])[:30], ensure_ascii=False, indent=2),
        "```",
        "",
        f"### 发现的关系三元组（{len(hybrid_data.get('relationships', []))}条）",
        "```json",
        json.dumps(hybrid_data.get('relationships', [])[:40], ensure_ascii=False, indent=2),
        "```",
        "",
        "### 情感判断",
        "```json",
        json.dumps(hybrid_data.get('sentiment_per_chapter', [])[:10], ensure_ascii=False, indent=2),
        "```",
        "",
        "### 质量评分",
        "```json",
        json.dumps(hybrid_data.get('quality_scores', [])[:10], ensure_ascii=False, indent=2),
        "```",
        "",
        "### API 成本",
        f"- 输入字符数：{hybrid_data.get('cost', {}).get('total_input_chars', '?')}",
        f"- 耗时：{hybrid_data.get('cost', {}).get('total_elapsed_seconds', '?')}秒",
        f"- 批次数：{hybrid_data.get('cost', {}).get('batch_count', '?')}",
        "",
        "### 结构化基准数据（混合方法的预处理结果）",
        "```json",
        json.dumps(structured_data.get('entity_stats', {}), ensure_ascii=False, indent=2)[:3000],
        "```",
    ]

    # Optional RAG section
    if rag_data:
        lines.extend([
            "",
            "---",
            "",
            "## 方法 C：RAG 检索增强",
            "",
            "### 索引概况",
            f"- 片段数：{rag_data.get('num_chunks', '?')}",
            f"- 实体召回率：{rag_data.get('entity_recall', '?')}",
            f"- 已知实体：{', '.join(rag_data.get('known_entities', []))}",
            f"- 检索到的实体：{', '.join(rag_data.get('retrieved_entities', []))}",
            "",
            "### 代表性查询结果",
            "```json",
            json.dumps(rag_data.get('queries', [])[:5], ensure_ascii=False, indent=2)[:3000],
            "```",
        ])

    lines.extend([
        "",
        "---",
        "",
        "## 请输出以下对比分析（中文 Markdown）",
        "",
        "### 1. 人物识别对比",
        "- 方法 A 独有：哪些人物只有纯 LLM 识别出来了？",
        "- 方法 B 独有：哪些人物只有混合方法识别出来了？",
        "- 共同识别：两种方法都识别出了哪些？",
        "- 幻觉检查：方法 A 是否识别出了原文中不存在的人物？",
        "- 遗漏检查：结构化数据中重要的人物，方法 A 是否遗漏了？",
        "",
        "### 2. 关系三元组对比",
        "- 重合率：两种方法发现的关系有多少是重合的？",
        "- 各自优势：哪种方法在哪些类型的关系上表现更好？",
        "- 幻觉/遗漏：各自的关系中有多少是不可靠的？",
        "",
        "### 3. 情感分析对比",
        "- 一致性：两种方法对同一章的情感判断是否一致？",
        "- 差异分析：不一致的地方，哪种更合理？",
        "",
        "### 4. API 成本对比",
        "- token 消耗差异",
        "- 耗时差异",
        "- 性价比评估",
    ])

    if rag_data:
        lines.extend([
            "",
            "### 5. RAG 检索评估（方法 C）",
            "- 实体召回率是否足够？遗漏了哪些重要人物？",
            "- 检索结果的相关性如何？能否支撑深度分析？",
            "- RAG 作为辅助手段（而非独立分析）的价值如何？",
            "- 与方法 A/B 的互补性评估",
            "",
            "### 6. 综合结论",
            "- 推荐使用哪种方法，为什么？",
            "- 各方法的最佳适用场景？",
            "- 是否建议混合使用（什么时候用哪种）？",
        ])
    else:
        lines.extend([
            "",
            "### 5. 综合结论",
            "- 推荐使用哪种方法，为什么？",
            "- 两种方法各自的最佳适用场景？",
            "- 是否建议混合使用（什么时候用哪种）？",
        ])

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare direct LLM vs hybrid analysis approaches.")
    parser.add_argument("--start", type=int, default=1, help="First chapter (1-based).")
    parser.add_argument("--end", type=int, default=50, help="Last chapter (inclusive).")
    parser.add_argument("--batch-size", type=int, default=5, help="Chapters per LLM call.")
    parser.add_argument("--max-chars", type=int, default=8000, help="Max chars per chapter in direct approach.")
    parser.add_argument("--hybrid-max-chars", type=int, default=4000, help="Max chars per chapter in hybrid approach.")
    parser.add_argument("--include-rag", action="store_true", help="Include RAG as a third approach.")
    parser.add_argument("--txt-path", type=Path, default=TXT, help="Novel text path.")
    parser.add_argument("--out-dir", type=Path, default=OUT, help="Output directory.")
    args = parser.parse_args()

    out_dir: Path = args.out_dir
    out_dir.mkdir(exist_ok=True)

    # ── Step 1: Read & parse ──
    progress(f"读取小说：{args.txt_path.name}")
    raw_text = normalizer.read_text(args.txt_path)
    apply_aliases = args.txt_path.resolve() == TXT.resolve()
    text = normalizer.normalize_text(raw_text, apply_aliases=apply_aliases)
    all_chapters = structure.parse_chapters(text)
    total = len(all_chapters)
    progress(f"共解析 {total} 章")

    if args.end > total:
        args.end = total
    chapters = all_chapters[args.start - 1:args.end]
    progress(f"分析范围：第{args.start}-{args.end}章（{len(chapters)}章）")

    # ── Step 2: Structured baseline (local, no API cost) ──
    progress("运行本地结构化分析（人物统计、关系抽取、情感打分、质量指标）...")
    t0 = time.time()
    ctx = build_structured_context(all_chapters)  # full novel for baseline
    structured_elapsed = time.time() - t0
    progress(f"结构化分析完成（{structured_elapsed:.1f}秒）")

    # Export structured baseline
    export_structured_baseline(ctx, all_chapters, out_dir)
    progress(f"结构化基准数据已保存到 {out_dir / 'structured_baseline.json'}")
    structured_data_raw = json.loads((out_dir / "structured_baseline.json").read_text(encoding="utf-8"))

    # ── Step 3: Direct LLM analysis ──
    progress(f"开始纯 LLM 直接分析（每批{args.batch_size}章，每章最多{args.max_chars}字）...")
    t0 = time.time()
    direct_summary = analyze_novel_direct(
        chapters,
        batch_size=args.batch_size,
        max_chars_per_chapter=args.max_chars,
        progress_callback=progress,
    )
    direct_elapsed = time.time() - t0
    progress(f"纯 LLM 分析完成（{direct_elapsed:.1f}秒）")

    from novel_parser.direct_llm_analyzer import DirectSummary
    direct_data = {
        "approach": "direct_llm",
        "total_chapters": len(chapters),
        "characters": direct_summary.characters,
        "relationships": direct_summary.relationships,
        "sentiment_per_chapter": direct_summary.sentiment_per_chapter,
        "plot_summaries": direct_summary.plot_summaries,
        "quality_scores": direct_summary.quality_scores,
        "cost": {
            "total_input_chars": direct_summary.total_input_chars,
            "total_elapsed_seconds": direct_summary.total_elapsed,
            "batch_count": len(direct_summary.batch_results),
            "models_used": list({br.model for br in direct_summary.batch_results}),
        },
    }
    export_direct_results(direct_summary, out_dir)
    progress(f"纯 LLM 结果已保存到 {out_dir / 'direct_results.json'}")

    # ── Step 4: Hybrid analysis ──
    progress(f"开始混合架构分析（结构化数据 + LLM，每批{args.batch_size}章）...")
    t0 = time.time()
    hybrid_summary = analyze_novel_hybrid(
        chapters,
        ctx=ctx,
        batch_size=args.batch_size,
        max_chars_per_chapter=args.hybrid_max_chars,
        progress_callback=progress,
    )
    hybrid_elapsed = time.time() - t0
    progress(f"混合分析完成（{hybrid_elapsed:.1f}秒）")

    hybrid_data = {
        "approach": "hybrid",
        "total_chapters": len(chapters),
        "characters": hybrid_summary.characters,
        "relationships": hybrid_summary.relationships,
        "sentiment_per_chapter": hybrid_summary.sentiment_per_chapter,
        "plot_summaries": hybrid_summary.plot_summaries,
        "quality_scores": hybrid_summary.quality_scores,
        "cost": {
            "total_input_chars": hybrid_summary.total_input_chars,
            "total_elapsed_seconds": hybrid_summary.total_elapsed,
            "batch_count": len(hybrid_summary.batch_results),
            "models_used": list({br.model for br in hybrid_summary.batch_results}),
        },
    }
    export_hybrid_results(hybrid_summary, out_dir)
    progress(f"混合结果已保存到 {out_dir / 'hybrid_results.json'}")

    # ── Step 4b: RAG analysis (optional) ──
    rag_data = None
    rag_elapsed = 0.0
    if args.include_rag:
        progress("开始 RAG 检索分析...")
        from novel_parser.memory_rag import NovelRAG, run_rag_indexing

        t0 = time.time()
        rag_dir = out_dir / "rag_db"
        rag = run_rag_indexing(
            args.txt_path,
            out_dir,
            args.start,
            args.end,
            apply_aliases=apply_aliases,
        )
        rag_elapsed = time.time() - t0
        progress(f"RAG 索引构建完成（{rag_elapsed:.1f}秒，{len(rag.chunks)} 个片段）")

        # Run representative queries to evaluate retrieval quality
        rag_queries = [
            "主要人物关系发展",
            "情感转折点",
            "战斗冲突场面",
            "关键对话",
            "剧情高潮",
        ]
        rag_query_results = []
        total_query_chars = 0
        for q in rag_queries:
            t_q = time.time()
            results = rag.query(q, top_k=5)
            q_elapsed = time.time() - t_q
            retrieved_chars = sum(len(r.chunk.text) for r in results)
            total_query_chars += retrieved_chars
            rag_query_results.append({
                "query": q,
                "num_results": len(results),
                "retrieved_chars": retrieved_chars,
                "elapsed_seconds": round(q_elapsed, 3),
                "top_results": [
                    {
                        "id": r.chunk.id,
                        "chapter": r.chunk.chapter_index,
                        "title": r.chunk.chapter_title,
                        "rrf_score": round(r.rrf_score, 4),
                        "chars_present": r.chunk.characters_present[:5],
                        "sentiment_net": r.chunk.sentiment_net,
                    }
                    for r in results
                ],
            })

        # Evaluate RAG retrieval recall against structured baseline
        known_entities = set(
            e["name"] for e in structured_data_raw.get("entity_stats", {}).get("top_20", [])[:10]
        )
        retrieved_entities = set()
        for qr in rag_query_results:
            for tr in qr["top_results"]:
                retrieved_entities.update(tr.get("chars_present", []))
        entity_recall = len(retrieved_entities & known_entities) / max(1, len(known_entities))

        rag_data = {
            "approach": "rag",
            "total_chapters": len(chapters),
            "num_chunks": len(rag.chunks),
            "queries": rag_query_results,
            "entity_recall": round(entity_recall, 3),
            "retrieved_entities": sorted(retrieved_entities),
            "known_entities": sorted(known_entities),
            "cost": {
                "index_elapsed_seconds": round(rag_elapsed, 1),
                "query_count": len(rag_queries),
                "total_retrieved_chars": total_query_chars,
                "api_calls": 0,  # embedding calls only
            },
        }
        (out_dir / "rag_results.json").write_text(
            json.dumps(rag_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        progress(f"RAG 结果已保存到 {out_dir / 'rag_results.json'}")
        progress(f"RAG 实体召回率：{entity_recall:.1%}（{len(retrieved_entities & known_entities)}/{len(known_entities)}）")

    # ── Step 5: Cost summary ──
    cost_summary = {
        "chapter_range": f"{args.start}-{args.end}",
        "total_chapters": len(chapters),
        "structured_analysis": {
            "elapsed_seconds": round(structured_elapsed, 1),
            "api_calls": 0,
        },
        "direct_llm": {
            "input_chars": direct_summary.total_input_chars,
            "elapsed_seconds": direct_summary.total_elapsed,
            "api_calls": len(direct_summary.batch_results),
        },
        "hybrid": {
            "input_chars": hybrid_summary.total_input_chars,
            "elapsed_seconds": hybrid_summary.total_elapsed,
            "api_calls": len(hybrid_summary.batch_results),
        },
        "comparison_report": {
            "api_calls": 1,
        },
        "total_api_calls": len(direct_summary.batch_results) + len(hybrid_summary.batch_results) + 1,
        "total_elapsed_seconds": round(structured_elapsed + direct_elapsed + hybrid_elapsed, 1),
    }
    if rag_data:
        cost_summary["rag"] = {
            "index_elapsed_seconds": round(rag_elapsed, 1),
            "num_chunks": rag_data["num_chunks"],
            "query_count": rag_data["cost"]["query_count"],
            "total_retrieved_chars": rag_data["cost"]["total_retrieved_chars"],
        }
        cost_summary["total_elapsed_seconds"] = round(
            cost_summary["total_elapsed_seconds"] + rag_elapsed, 1
        )
    (out_dir / "cost_summary.json").write_text(
        json.dumps(cost_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    progress(f"成本统计已保存到 {out_dir / 'cost_summary.json'}")

    # ── Step 6: LLM comparison report ──
    progress("生成对比报告（调用 LLM）...")
    comparison_prompt = build_comparison_prompt(direct_data, hybrid_data, structured_data_raw, rag_data)
    (out_dir / "comparison_prompt.md").write_text(comparison_prompt, encoding="utf-8")

    t0 = time.time()
    try:
        content, model = llm_client.call_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是小说分析方法论专家。请客观对比分析方法的优劣，"
                        "每个判断都要有具体依据。输出中文 Markdown。"
                    ),
                },
                {"role": "user", "content": comparison_prompt},
            ],
            temperature=0.3,
            timeout=600,
        )
        report_elapsed = time.time() - t0
        report = (
            f"# 分析方法对比报告\n\n"
            f"> 对比范围：第{args.start}-{args.end}章（共{len(chapters)}章）\n"
            f"> 模型：{model}\n"
            f"> 报告生成耗时：{report_elapsed:.1f}秒\n\n"
            f"{content}\n\n---\n\n"
            f"## 附录：成本统计\n\n"
            f"```json\n{json.dumps(cost_summary, ensure_ascii=False, indent=2)}\n```\n"
        )
        (out_dir / "comparison_report.md").write_text(report, encoding="utf-8")
        progress(f"对比报告已保存到 {out_dir / 'comparison_report.md'}")
    except Exception as exc:
        progress(f"对比报告生成失败：{exc}")
        # Still save the prompt for manual use
        fallback = (
            f"# 分析方法对比报告（生成失败）\n\n"
            f"> 错误：{exc}\n\n"
            f"请手动将 `comparison_prompt.md` 的内容发送给 LLM 生成对比报告。\n\n---\n\n"
            f"## 成本统计\n\n"
            f"```json\n{json.dumps(cost_summary, ensure_ascii=False, indent=2)}\n```\n"
        )
        (out_dir / "comparison_report.md").write_text(fallback, encoding="utf-8")

    # ── Done ──
    print("\n" + "=" * 60)
    print(f"对比完成！结果保存在：{out_dir}")
    print(f"  - direct_results.json       纯 LLM 分析结果")
    print(f"  - hybrid_results.json       混合分析结果")
    print(f"  - structured_baseline.json  结构化基准数据")
    if rag_data:
        print(f"  - rag_results.json          RAG 检索结果")
        print(f"  - rag_db/                   RAG 索引数据")
    print(f"  - comparison_report.md      对比报告")
    print(f"  - cost_summary.json         成本统计")
    print(f"  - comparison_prompt.md      对比提示词（备用）")
    print(f"总 API 调用：{cost_summary['total_api_calls']} 次")
    print(f"总耗时：{cost_summary['total_elapsed_seconds']} 秒")
    print("=" * 60)


if __name__ == "__main__":
    main()

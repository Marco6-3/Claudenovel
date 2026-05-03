# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Evidence-grounded novel analysis framework. Parses Chinese web novels into structured data (characters, relations, sentiment, quality metrics), then feeds that data into LLMs for deep editorial diagnosis, chapter rewriting, and continuation writing.

Core philosophy: every analysis conclusion must cite evidence IDs like `[CH035-P001]` (chapter 35, paragraph 1). No evidence = "证据不足".

## Commands

```powershell
# Setup
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# Main analysis (auto-finds first .txt in current dir)
python analyze_enhanced.py

# Analyze external novel
python analyze_enhanced.py --txt-path "C:\path\to\novel.txt" --out-dir "C:\path\to\output"

# Evidence-grounded context pack for LLM
python analyze_enhanced.py --build-context --context-query "query" --focus-entity "name"

# Common workflow: source pack + review prompt
python analyze_enhanced.py --common-workflow --context-query "评价并给出建议" --source-start 1 --source-end 20

# Generate editorial report via LLM
python analyze_enhanced.py --llm-context-report --context-prompt .\output\editorial_revision_prompt.md

# Chapter rewriting
python rewrite_chapter.py --chapter-file "ch.txt" --novel "full.txt" --out-dir "rewritten"
python rewrite_chapter.py --chapter-file "ch.txt" --novel "full.txt" --review-only

# Novel continuation from report
python continue_novel.py --report "report.md" --list                          # show routes
python continue_novel.py --report "report.md" --route 0 --novel "full.txt"    # generate

# RAG indexing (memory-only, no API needed)
python index_and_query_rag.py --memory-only --start 1 --end 50

# RAG indexing (full, needs API for embedding or auto-falls-back to TF-IDF)
python index_and_query_rag.py --index --start 1 --end 50
```

## Architecture

### Data Flow

```
novel.txt → normalizer → structure (Chapter/Scene/Dialogue)
    → entity stats + relation triples + sentiment arc + quality metrics
    → context_builder (evidence IDs [CHxxx-Pxxx])
    → LLM (editorial diagnosis / rewrite / continuation)
```

### Module Map (`novel_parser/`)

| Module | Role |
|--------|------|
| `normalizer.py` | Encoding detection, simplified/traditional Chinese conversion, character alias normalization |
| `structure.py` | Regex parsing: volumes → chapters → scenes (by location keywords) → dialogues. Output: `List[Chapter]` |
| `entity.py` | Character occurrence stats, chapter span, scene-level co-occurrence |
| `relation.py` | Relation triples via verb-window rules (+ optional jieba POS) |
| `sentiment.py` | Dictionary-based sentiment arc (positive/negative/tension per chapter) |
| `evaluator.py` | 20+ quality metrics (conflict density, dialogue ratio, TTR, suspense) with percentile scoring vs baseline |
| `context_builder.py` | Filters high-signal paragraphs, assigns `[CHxxx-Pxxx]` evidence IDs, builds LLM-ready prompts |
| `llm_client.py` | OpenAI/DeepSeek-compatible API client. Calls `load_dotenv()` to find `.env` |
| `common_workflows.py` | Wraps "source pack + review/improve/continue prompt" into one CLI flag |
| `memory_rag.py` | Hybrid retrieval (Dense embedding + BM25 + RRF) + cross-batch memory summaries |
| `chapter_rewriter.py` | Diagnose → suggest → rewrite → diff pipeline for single chapters |
| `rewriter_prompts.py` | All prompt templates: diagnosis, suggestion, rewrite, continuation |
| `continuation_writer.py` | Parse editorial report → select route → LLM generates next chapter |
| `hybrid_analyzer.py` | Structured context + LLM analysis (experiment group) |
| `direct_llm_analyzer.py` | Raw text to LLM (control group) |
| `pipeline.py` | Main orchestrator called by `analyze_enhanced.py` |

### Key Design Decisions

- **No ChromaDB/FAISS**: `SimpleVectorStore` is pure numpy cosine similarity (~100 lines). Sufficient for 440 chapters.
- **Scene-level chunking**: Chunks by scene (location change) not fixed length, preserving narrative coherence.
- **Embedding fallback**: `get_embeddings()` in `memory_rag.py` tries API first, falls back to local TF-IDF if no key.
- **`.env` loading**: Both `llm_client.py` and `memory_rag.py` call `load_dotenv()` which searches upward from cwd.

### Output Directories

- `novel_analysis_enhanced/` — Main analysis output (entity stats, relations, sentiment, evidence packs, prompts, reports)
- `novel_analysis_comparison/` — LLM vs Hybrid experiment results
- `rewritten/` — Chapter rewriter output (per-chapter folders with diagnosis, suggestions, diff)
- `continued/` — Continuation writer output

## Environment

`.env` in project root contains `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`. The framework also reads `OPENAI_API_KEY` / `OPENAI_BASE_URL` as fallbacks.

## Conventions

- All text is Chinese. Prompts, reports, and user-facing output use Simplified Chinese.
- Novel input must be UTF-8 `.txt`. If given `.docx`, convert to `.txt` first.
- `--apply-aliases` is for the repo's default novel only. External novels should omit it.
- Editorial reports must contain P0/P1/P2 prioritization and `[CHxxx-Pxxx]` evidence references.
- The JSON summary block at the end of editorial reports is machine-readable and consumed by `continuation_writer.py`.

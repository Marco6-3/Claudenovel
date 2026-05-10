"""Continuation writer: generate next chapter from editorial report.

Reads an editorial diagnosis report (produced by the analysis pipeline),
extracts continuation routes and P0 issues, then calls LLM to write
the next chapter following a selected route.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from . import llm_client, normalizer, structure
from .rewriter_prompts import (
    CONTINUATION_SYSTEM_PROMPT,
    build_continuation_user_prompt,
)


@dataclass
class ContinuationResult:
    chapter_num: int
    route_name: str
    route_index: int
    generated_text: str
    prompt_md: str
    route_info: Dict[str, Any]
    model_used: str = ""
    elapsed_seconds: float = 0.0


# ---------------------------------------------------------------------------
# Parse editorial report
# ---------------------------------------------------------------------------
def parse_report(report_path: Path) -> Dict[str, Any]:
    """Parse editorial report markdown → extract structured data.

    Returns dict with keys: continuation_routes, p0_issues, raw_json, report_text.
    """
    text = report_path.read_text(encoding="utf-8")

    result: Dict[str, Any] = {
        "continuation_routes": [],
        "p0_issues": [],
        "raw_json": None,
        "report_text": text,
    }

    # 1. Extract JSON summary block (```json ... ```)
    json_match = re.search(r"```json\s*\n(.*?)\n```", text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            result["raw_json"] = data
            result["continuation_routes"] = data.get("continuation_routes", [])
            # Extract P0 from rewrite_targets
            for target in data.get("rewrite_targets", []):
                if target.get("priority") == "P0":
                    result["p0_issues"].append(target)
        except json.JSONDecodeError:
            pass

    # 2. If no JSON found, try extracting routes from markdown text
    if not result["continuation_routes"]:
        result["continuation_routes"] = _extract_routes_from_markdown(text)

    # 3. If no P0 from JSON, extract from markdown
    if not result["p0_issues"]:
        result["p0_issues"] = _extract_p0_from_markdown(text)

    return result


def _extract_routes_from_markdown(text: str) -> List[Dict[str, Any]]:
    """Fallback: extract continuation routes from markdown headings."""
    routes = []
    # Look for "后续剧情路线" section
    route_section = re.search(r"## 后续剧情路线\s*\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if not route_section:
        return routes

    section_text = route_section.group(1)
    # Split by numbered headings or bold headings
    blocks = re.split(r"\n###?\s*\d*\.?\s*", section_text)
    for block in blocks:
        if not block.strip():
            continue
        route: Dict[str, Any] = {}
        lines = block.strip().split("\n")
        # First line might be the route name
        if lines:
            route["route_name"] = lines[0].strip().lstrip("*").strip()

        for line in lines:
            line = line.strip()
            for key, field_name in [
                ("冲突核心", "conflict_core"),
                ("人物推进", "character_movement"),
                ("人物关系", "character_movement"),
                ("下一章钩子", "next_chapter_hook"),
                ("钩子", "next_chapter_hook"),
                ("风险", "risk"),
                ("推荐写法", "recommended_execution"),
                ("可信度", "risk"),
                ("证据", "foreshadowing_to_reuse"),
            ]:
                if key in line:
                    value = line.split("：", 1)[-1].strip() if "：" in line else line
                    if field_name == "foreshadowing_to_reuse":
                        route.setdefault(field_name, []).append(value)
                    else:
                        route[field_name] = value
                    break

        if route.get("route_name"):
            routes.append(route)

    return routes


def _extract_p0_from_markdown(text: str) -> List[Dict[str, Any]]:
    """Fallback: extract P0 issues from markdown sections."""
    issues = []
    p0_section = re.search(r"## 必须修（P0）\s*\n(.*?)(?=\n## |\Z)", text, re.DOTALL)
    if not p0_section:
        return issues

    section_text = p0_section.group(1)
    # Split by ### headings or numbered items
    blocks = re.split(r"\n###?\s*", section_text)
    for block in blocks:
        if not block.strip():
            continue
        issue: Dict[str, Any] = {}
        lines = block.strip().split("\n")
        if lines:
            issue["problem"] = lines[0].strip()

        for line in lines:
            line = line.strip()
            if "伤害" in line or "影响" in line:
                issue["why_it_hurts"] = line.split("：", 1)[-1].strip() if "：" in line else line

        if issue.get("problem"):
            issues.append(issue)

    return issues


# ---------------------------------------------------------------------------
# Style reference extraction
# ---------------------------------------------------------------------------
def extract_style_reference(
    novel_path: Path,
    lookback_chapters: int = 3,
) -> str:
    """Extract the last N chapters from the novel for style reference."""
    raw = normalizer.read_text(novel_path)
    text = normalizer.normalize_text(raw)
    chapters = structure.parse_chapters(text)

    if not chapters:
        return ""

    last_chapters = chapters[-lookback_chapters:]
    parts = []
    for ch in last_chapters:
        parts.append(f"### {ch.title}\n\n{ch.body}")

    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------
def generate_continuation(
    report_path: Path,
    route_index: int = 0,
    novel_path: Optional[Path] = None,
    memory_path: Optional[Path] = None,
    lookback_chapters: int = 3,
    target_words: int = 3000,
    chapter_num: int = 0,
    out_dir: Path = Path("continued"),
) -> ContinuationResult:
    """Full pipeline: parse report → select route → generate → export.

    Args:
        report_path: Path to editorial report markdown.
        route_index: Which continuation route to follow (0-based).
        novel_path: Path to full novel text (for style reference).
        memory_path: Path to memory_summary.json (optional).
        lookback_chapters: How many recent chapters to use as style reference.
        target_words: Target word count for the new chapter.
        chapter_num: Chapter number for the new chapter (auto-detected if 0).
        out_dir: Output directory.
    """
    t0 = time.time()

    # Step 1: Parse report
    print("[Continuation] Step 1/4: Parsing editorial report...")
    report_data = parse_report(report_path)
    routes = report_data["continuation_routes"]
    p0_issues = report_data["p0_issues"]

    if not routes:
        raise ValueError(f"No continuation routes found in {report_path}")
    if route_index >= len(routes):
        raise ValueError(
            f"Route index {route_index} out of range (0-{len(routes) - 1}). "
            f"Available routes: {len(routes)}"
        )

    route = routes[route_index]
    route_name = route.get("route_name", f"route_{route_index}")
    print(f"[Continuation] Selected route {route_index}: {route_name}")
    print(f"[Continuation] P0 issues to avoid: {len(p0_issues)}")

    # Step 2: Build context
    print("[Continuation] Step 2/4: Building context...")
    style_reference = ""
    if novel_path and novel_path.exists():
        style_reference = extract_style_reference(novel_path, lookback_chapters)
        print(f"[Continuation] Style reference: last {lookback_chapters} chapters")

    memory_summary = {}
    if memory_path and memory_path.exists():
        memory_summary = json.loads(memory_path.read_text(encoding="utf-8"))
        print(f"[Continuation] Loaded memory: {memory_path}")

    # Detect chapter number
    if chapter_num <= 0:
        chapter_num = _detect_next_chapter(report_path)
        print(f"[Continuation] Auto-detected chapter number: {chapter_num}")

    # Step 3: Build prompt and call LLM
    print("[Continuation] Step 3/4: Generating chapter via LLM...")
    user_prompt = build_continuation_user_prompt(
        route=route,
        style_reference=style_reference,
        memory_summary=memory_summary,
        p0_issues=p0_issues,
        target_chapter_num=chapter_num,
        target_words=target_words,
    )

    messages = [
        {"role": "system", "content": CONTINUATION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    generated_text, model = llm_client.call_chat(
        messages,
        temperature=0.65,  # creative temperature for writing
        timeout=600,
    )

    elapsed = time.time() - t0

    # Step 4: Export
    print("[Continuation] Step 4/4: Exporting results...")
    result = ContinuationResult(
        chapter_num=chapter_num,
        route_name=route_name,
        route_index=route_index,
        generated_text=generated_text,
        prompt_md=user_prompt,
        route_info=route,
        model_used=model,
        elapsed_seconds=elapsed,
    )
    _export_result(result, p0_issues, out_dir)

    return result


def _detect_next_chapter(report_path: Path) -> int:
    """Try to detect the next chapter number from the report context."""
    text = report_path.read_text(encoding="utf-8")

    # Look for chapter references like CH440, 第440章
    max_chapter = 0
    for m in re.finditer(r"(?:CH|第)(\d+)(?:章|[-\s])", text):
        num = int(m.group(1))
        if num > max_chapter:
            max_chapter = num

    return max_chapter + 1 if max_chapter > 0 else 1


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------
def _export_result(
    result: ContinuationResult,
    p0_issues: List[Dict[str, Any]],
    out_dir: Path,
) -> None:
    """Write all outputs to a dedicated folder."""
    safe_name = result.route_name[:15].replace("/", "_").replace("\\", "_")
    folder = out_dir / f"ch{result.chapter_num:03d}_route{result.route_index}_{safe_name}"
    folder.mkdir(parents=True, exist_ok=True)

    # 1. Generated chapter
    (folder / f"chapter_{result.chapter_num}.txt").write_text(
        result.generated_text, encoding="utf-8"
    )

    # 2. Route info
    (folder / "route_info.json").write_text(
        json.dumps({
            "route_index": result.route_index,
            "route_name": result.route_name,
            "route": result.route_info,
            "p0_issues_count": len(p0_issues),
            "model": result.model_used,
            "elapsed_seconds": result.elapsed_seconds,
            "chars_generated": len(result.generated_text),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 3. Full prompt (for reproducibility)
    (folder / "continuation_prompt.md").write_text(
        result.prompt_md, encoding="utf-8"
    )

    print(f"[ContinuationExport] All files saved to {folder}")
    for f in folder.iterdir():
        print(f"  - {f.name} ({f.stat().st_size} bytes)")


# ---------------------------------------------------------------------------
# Route listing helper
# ---------------------------------------------------------------------------
def list_routes(report_path: Path) -> List[Dict[str, Any]]:
    """Parse report and return available continuation routes with metadata."""
    report_data = parse_report(report_path)
    routes = report_data["continuation_routes"]
    p0_count = len(report_data["p0_issues"])

    print(f"\n报告：{report_path.name}")
    print(f"P0 问题数：{p0_count}")
    print(f"可用路线数：{len(routes)}\n")

    for i, route in enumerate(routes):
        name = route.get("route_name", f"路线{i}")
        hook = route.get("next_chapter_hook", "—")
        conflict = route.get("conflict_core", "—")
        print(f"  [{i}] {name}")
        print(f"      冲突核心：{conflict}")
        print(f"      下章钩子：{hook}")
        print()

    return routes

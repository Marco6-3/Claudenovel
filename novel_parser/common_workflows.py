"""Common export workflows for LLM-oriented novel analysis."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .context_builder import collect_evidence
from .normalizer import ENTITY_ALIASES
from .structure import Chapter


DEFAULT_REVIEW_QUERY = (
    "请评价这段剧情的优缺点，指出可改进处，并给出后续剧情发展建议。"
)


def _select_chapters(
    chapters: Sequence[Chapter],
    start: int | None = None,
    end: int | None = None,
) -> list[Chapter]:
    """Select a 1-based inclusive chapter range."""
    if not chapters:
        return []
    first = start or 1
    last = end or len(chapters)
    if first < 1 or last < first or last > len(chapters):
        raise ValueError(f"章节范围无效：start={start}, end={end}, total={len(chapters)}")
    return list(chapters[first - 1:last])


def _fit_chapters_to_budget(
    chapters: Sequence[Chapter],
    max_chars: int,
) -> tuple[list[Chapter], bool]:
    """Fit whole chapters into a rough prompt budget without simplifying content."""
    if max_chars <= 0:
        return list(chapters), False
    selected: list[Chapter] = []
    used = 0
    truncated = False
    for chapter in chapters:
        cost = len(chapter.body) + len(chapter.title) + 120
        if selected and used + cost > max_chars:
            truncated = True
            break
        selected.append(chapter)
        used += cost
        if used > max_chars:
            truncated = True
            break
    return selected, truncated


def _expand_focus_entities(focus_entities: Sequence[str] | None) -> list[str]:
    """Expand user focus names to known canonical names and aliases."""
    expanded: list[str] = []
    seen = set()
    for name in focus_entities or []:
        candidates = [name]
        for canonical, aliases in ENTITY_ALIASES.items():
            if name == canonical or name in aliases:
                candidates.extend([canonical, *aliases])
        for candidate in candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                expanded.append(candidate)
    return expanded


def render_detailed_source_pack(
    chapters: Sequence[Chapter],
    query: str = "",
    focus_entities: Sequence[str] | None = None,
    max_chars: int = 0,
) -> tuple[str, dict]:
    """Render original text into a detailed, citeable LLM input format."""
    packed, truncated = _fit_chapters_to_budget(chapters, max_chars)
    focus = "、".join(focus_entities or []) or "未指定"
    lines = [
        "# 长篇小说 LLM 分析输入包（具体版）\n\n",
        "## 使用规则\n\n",
        "- 下面保留原文章节、段落和对话，不做简化摘要。\n",
        "- 分析时必须引用段落编号，例如 `[CH001-P003]`。\n",
        "- 没有直接原文支撑的判断，请标记为“证据不足”。\n",
        "- 请区分原文事实、合理推断、改写建议和后续剧情设想。\n\n",
        "## 分析目标\n\n",
        f"{query or DEFAULT_REVIEW_QUERY}\n\n",
        f"关注对象：{focus}\n\n",
        "## 原文索引\n\n",
    ]
    manifest = {
        "query": query or DEFAULT_REVIEW_QUERY,
        "focus_entities": list(focus_entities or []),
        "max_chars": max_chars,
        "truncated_by_budget": truncated,
        "chapter_count": len(packed),
        "chapters": [],
    }
    for chapter in packed:
        lines.append(
            f"### CH{chapter.global_index:03d} {chapter.title}\n\n"
            f"- 卷：{chapter.volume or '未分卷'}\n"
            f"- 字数：{chapter.chars}\n"
            f"- 场景数：{len(chapter.scenes)}\n"
            f"- 对话数：{len(chapter.dialogues)}\n\n"
        )
        chapter_info = {
            "id": f"CH{chapter.global_index:03d}",
            "index": chapter.global_index,
            "title": chapter.title,
            "volume": chapter.volume,
            "chars": chapter.chars,
            "paragraphs": [],
        }
        for idx, paragraph in enumerate(chapter.paragraphs, start=1):
            paragraph_id = f"CH{chapter.global_index:03d}-P{idx:03d}"
            lines.append(f"#### [{paragraph_id}]\n\n{paragraph}\n\n")
            chapter_info["paragraphs"].append(
                {
                    "id": paragraph_id,
                    "index": idx,
                    "chars": len(paragraph),
                }
            )
        manifest["chapters"].append(chapter_info)
    if truncated:
        lines.append(
            "\n> 注意：由于 `--source-max-chars` 限制，后续章节没有写入本次输入包。\n"
        )
    return "".join(lines), manifest


def render_review_prompt(
    query: str,
    evidence_count: int,
    focus_entities: Sequence[str] | None = None,
) -> str:
    """Build a concrete review/improvement/continuation prompt."""
    focus = "、".join(focus_entities or []) or "未指定"
    return f"""# 评价、改进与后续剧情建议提示词

你是严谨的中文网络小说编辑。请只基于下方证据和原文判断，不要空泛套话。

## 分析目标

{query or DEFAULT_REVIEW_QUERY}

关注对象：{focus}
证据数量：{evidence_count}

## 输出要求

1. 总体评价：给出剧情、人物、文笔、节奏四项评价，每项必须引用证据编号。
2. 主要优点：列出 3-5 条，每条说明具体原文依据。
3. 主要问题：列出 3-5 条，每条说明问题发生在什么事件、人物行为或叙事处理上。
4. 可执行改进：不要只写“加强冲突”，要写成可落地的改法。
5. 后续剧情发展建议：给 3 条路线，每条包含：
   - 冲突核心
   - 人物关系推进
   - 下一章钩子
   - 需要回收或新埋的伏笔
6. 风险提示：指出哪些建议证据不足或可能破坏既有人设。
"""


def export_common_workflows(
    chapters: Sequence[Chapter],
    out_dir: Path,
    query: str = "",
    focus_entities: Sequence[str] | None = None,
    source_start: int | None = None,
    source_end: int | None = None,
    source_max_chars: int = 0,
    evidence_max_items: int = 120,
    evidence_excerpt_chars: int = 1200,
) -> dict:
    """Export the most frequently used LLM analysis files."""
    out_dir.mkdir(exist_ok=True)
    selected = _select_chapters(chapters, source_start, source_end)

    source_markdown, source_manifest = render_detailed_source_pack(
        selected,
        query=query,
        focus_entities=focus_entities or [],
        max_chars=source_max_chars,
    )
    source_path = out_dir / "llm_source_pack_detailed.md"
    manifest_path = out_dir / "llm_source_pack_manifest.json"
    source_path.write_text(source_markdown, encoding="utf-8")
    manifest_path.write_text(
        json.dumps(source_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    evidence = collect_evidence(
        chapters,
        query=query,
        focus_entities=_expand_focus_entities(focus_entities),
        max_items=evidence_max_items,
        excerpt_chars=evidence_excerpt_chars,
    )
    evidence_path = out_dir / "review_evidence_pack.json"
    evidence_path.write_text(
        json.dumps(
            {
                "query": query or DEFAULT_REVIEW_QUERY,
                "focus_entities": list(focus_entities or []),
                "evidence_count": len(evidence),
                "evidence": [asdict(item) for item in evidence],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    prompt_path = out_dir / "review_improve_continue_prompt.md"
    prompt_path.write_text(
        render_review_prompt(query or DEFAULT_REVIEW_QUERY, len(evidence), focus_entities)
        + "\n\n## 证据包\n\n"
        + "\n".join(
            (
                f"### [{item.id}] {item.chapter_title}\n"
                f"- 位置：第 {item.chapter_index} 章，第 {item.paragraph_index} 段\n"
                f"- 命中：{'、'.join(item.matched_terms) if item.matched_terms else '无'}\n"
                f"- 原文摘录：{item.excerpt}\n"
            )
            for item in evidence
        ),
        encoding="utf-8",
    )

    return {
        "source_pack": source_path.name,
        "source_manifest": manifest_path.name,
        "review_evidence_pack": evidence_path.name,
        "review_prompt": prompt_path.name,
        "source_chapter_count": source_manifest["chapter_count"],
        "source_truncated_by_budget": source_manifest["truncated_by_budget"],
        "review_evidence_count": len(evidence),
    }

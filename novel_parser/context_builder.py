"""Build evidence-grounded LLM context packs for long-form text analysis."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, List, Sequence

from .structure import Chapter


DEFAULT_STOPWORDS = {
    "分析", "文本", "小说", "关系", "变化", "人物", "章节", "原文",
    "为了", "请问", "怎么", "改进", "上下文", "窗口", "准确性",
}


@dataclass
class EvidenceItem:
    """One citeable paragraph or paragraph excerpt."""

    id: str
    chapter_index: int
    chapter_title: str
    paragraph_index: int
    chars: int
    score: int
    matched_terms: List[str]
    excerpt: str


def _terms_from_query(query: str) -> List[str]:
    """Extract useful Chinese/ASCII search terms from a free-form task."""
    if not query:
        return []
    raw_terms = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_+-]{1,}", query)
    terms: list[str] = []
    seen = set()
    for term in raw_terms:
        term = term.strip()
        if not term or term in DEFAULT_STOPWORDS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _trim_excerpt(text: str, max_chars: int) -> str:
    """Keep a compact but readable excerpt."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    head = max_chars // 2
    tail = max_chars - head - 8
    return cleaned[:head].rstrip() + " ... " + cleaned[-tail:].lstrip()


def _paragraph_score(
    paragraph: str,
    terms: Sequence[str],
    focus_entities: Sequence[str],
) -> tuple[int, list[str]]:
    """Score paragraph relevance and return matched terms."""
    matched: list[str] = []
    score = 0

    for entity in focus_entities:
        count = paragraph.count(entity)
        if count:
            score += count * 8
            matched.append(entity)

    for term in terms:
        count = paragraph.count(term)
        if count:
            score += count * 5
            matched.append(term)

    if len(set(focus_entities) & set(matched)) >= 2:
        score += 10
    if any(mark in paragraph for mark in ("说", "问", "笑", "看", "沉默", "点头")):
        score += 2

    deduped = []
    seen = set()
    for term in matched:
        if term not in seen:
            seen.add(term)
            deduped.append(term)
    return score, deduped


def collect_evidence(
    chapters: Sequence[Chapter],
    query: str = "",
    focus_entities: Sequence[str] | None = None,
    max_items: int = 80,
    excerpt_chars: int = 900,
) -> list[EvidenceItem]:
    """Collect the highest-signal citeable paragraphs for an analysis task."""
    focus = [x for x in (focus_entities or []) if x]
    terms = _terms_from_query(query)
    items: list[EvidenceItem] = []

    for chapter in chapters:
        for idx, paragraph in enumerate(chapter.paragraphs, start=1):
            score, matched = _paragraph_score(paragraph, terms, focus)
            if score <= 0:
                continue
            items.append(
                EvidenceItem(
                    id=f"CH{chapter.global_index:03d}-P{idx:03d}",
                    chapter_index=chapter.global_index,
                    chapter_title=chapter.title,
                    paragraph_index=idx,
                    chars=len(paragraph),
                    score=score,
                    matched_terms=matched,
                    excerpt=_trim_excerpt(paragraph, excerpt_chars),
                )
            )

    items.sort(key=lambda x: (-x.score, x.chapter_index, x.paragraph_index))
    selected = items[:max_items]
    selected.sort(key=lambda x: (x.chapter_index, x.paragraph_index))
    return selected


def _fit_items_to_budget(
    items: Iterable[EvidenceItem],
    max_context_chars: int,
) -> list[EvidenceItem]:
    """Fit evidence into a rough character budget."""
    fitted: list[EvidenceItem] = []
    used = 0
    for item in items:
        cost = len(item.excerpt) + len(item.id) + len(item.chapter_title) + 80
        if fitted and used + cost > max_context_chars:
            break
        fitted.append(item)
        used += cost
    return fitted


def render_prompt_pack(
    query: str,
    evidence: Sequence[EvidenceItem],
    focus_entities: Sequence[str] | None = None,
) -> str:
    """Render a copy-ready prompt that forces grounded analysis."""
    focus = "、".join(focus_entities or []) or "未指定"
    lines = [
        "# 长文本证据化分析提示词\n",
        "你是长篇文本分析助手。请严格基于给定证据分析，不允许脱离原文泛泛总结。\n",
        "\n## 分析目标\n",
        f"{query or '请基于证据完成文本分析。'}\n",
        f"\n关注对象：{focus}\n",
        "\n## 硬性规则\n",
        "1. 每个结论必须引用至少一个证据编号，例如 [CH012-P034]。\n",
        "2. 没有直接证据时，写“证据不足”，不要猜测。\n",
        "3. 区分事实、推断和不确定点。\n",
        "4. 不要只写“关系逐渐加深”“人物更复杂”这类空泛判断，必须说明是哪件事、哪个行为或哪段话支撑。\n",
        "5. 如果证据之间存在矛盾，要单独列出。\n",
        "\n## 输出格式\n",
        "- 结论\n",
        "- 关键证据\n",
        "- 推断边界\n",
        "- 反证或不确定点\n",
        "- 可信度\n",
        "\n## 证据索引\n",
    ]
    for item in evidence:
        terms = "、".join(item.matched_terms) if item.matched_terms else "无"
        lines.extend(
            [
                f"\n### [{item.id}] {item.chapter_title}\n",
                f"- 位置：第 {item.chapter_index} 章，第 {item.paragraph_index} 段\n",
                f"- 命中：{terms}\n",
                f"- 原文摘录：{item.excerpt}\n",
            ]
        )
    return "".join(lines)


def export_context_pack(
    chapters: Sequence[Chapter],
    out_dir: Path,
    query: str = "",
    focus_entities: Sequence[str] | None = None,
    max_items: int = 80,
    excerpt_chars: int = 900,
    max_context_chars: int = 80000,
) -> dict:
    """Export JSON evidence and a prompt markdown file."""
    out_dir.mkdir(exist_ok=True)
    collected = collect_evidence(
        chapters,
        query=query,
        focus_entities=focus_entities,
        max_items=max_items,
        excerpt_chars=excerpt_chars,
    )
    evidence = _fit_items_to_budget(collected, max_context_chars)

    data = {
        "query": query,
        "focus_entities": list(focus_entities or []),
        "max_context_chars": max_context_chars,
        "evidence_count": len(evidence),
        "evidence": [asdict(item) for item in evidence],
    }
    (out_dir / "evidence_pack.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "llm_context_prompt.md").write_text(
        render_prompt_pack(query, evidence, focus_entities),
        encoding="utf-8",
    )
    return {
        "evidence_output": "evidence_pack.json",
        "prompt_output": "llm_context_prompt.md",
        "evidence_count": len(evidence),
    }

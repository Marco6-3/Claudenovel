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
    """Build a concrete review and single-unit improvement prompt."""
    focus = "、".join(focus_entities or []) or "未指定"
    return f"""# 评价与当前单元改进提示词

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
5. 当前单元修订方案：给 3 种实现，每种包含：
   - 冲突核心
   - 人物关系推进
   - 局部结尾
   - 必须保留的原有节点
6. 风险提示：指出哪些建议证据不足或可能破坏既有人设。
"""


def render_editorial_revision_prompt(
    query: str,
    evidence_count: int,
    focus_entities: Sequence[str] | None = None,
    source_pack_name: str = "llm_source_pack_detailed.md",
    evidence_pack_name: str = "review_evidence_pack.json",
) -> str:
    """Build a sharper prompt for rewrite-ready editorial diagnosis."""
    focus = "、".join(focus_entities or []) or "未指定"
    return f"""# 深度编辑诊断与改写规格提示词

你是一名严厉但务实的中文网文主编。你的任务不是写读后感，而是输出可直接喂给章节改写器的编辑诊断报告。

## 分析目标

{query or DEFAULT_REVIEW_QUERY}

关注对象：{focus}
证据数量：{evidence_count}
原文输入包：`{source_pack_name}`
证据包：`{evidence_pack_name}`

## 总原则

1. 只基于给定原文和证据编号判断。没有证据就写“证据不足”，不要顺着设想编造。
2. 报告要具体、尖锐、可直接改章节。避免“加强人物”“优化节奏”“增加冲突”这类空话。
3. 每个核心问题至少引用 2 个证据编号，例如 `[CH035-P001]`、`[CH044-P001]`。
4. 每个修改建议必须写清：改哪一章/哪一段、加什么场景、删什么信息、调整哪句台词或哪种行为、预计增删多少字。
5. 区分“必须修”“建议增强”“可以保留但要控制”。不要平均用力。
6. 如果统计数据和原文感觉冲突，以原文证据为准；统计数据只能作为辅助论据。
7. 修订方案必须服务当前单元，不能凭空新增大设定或擅自规划下一章。

## 输出格式

请严格按以下结构输出 Markdown：

# 编辑诊断报告

## 一句话结论

用 2-4 句话判断：当前稿件最强的阅读价值是什么，最影响后续改写的硬伤是什么。

## 评分总览

用表格给出剧情、人物、文笔、节奏、爽点、改写优先级。每项必须有 1-2 个证据编号。

## 必须修（P0）

列出 3-5 条。每条必须包含：

- 问题描述：具体到章节事件、人物行为、台词或叙事处理。
- 证据支持：至少 2 个证据编号。
- 为什么伤害阅读：说明影响的是人物可信度、爽点、节奏、情绪、设定还是后续剧情。
- 改写任务：写成 `feat/chapter-rewriter` 可以执行的任务。
- 场景补丁：明确插入/重写位置、目标字数、必须保留、必须改变。

## 建议增强（P1）

列出 3-5 条。要求同上，但可以是增强代入感、伏笔密度、人物互动、战斗策略等。

## 保留但控制（P2）

列出 2-4 条。说明哪些优点继续使用会变成套路，以及控制边界。

## 逐章改写清单

用表格输出，字段固定为：

| 优先级 | 章节/段落 | 改写动作 | 目标字数变化 | 依赖证据 | 给改写器的指令 |

`给改写器的指令` 必须是一句可执行命令，例如：
“在 CH035 突破前新增 500-800 字失败冲关场景，保留轮回珠提纯设定，但加入灵气逆行和凌默主动调整的过程。”

## 当前单元修订方案

给出 3 种当前单元内的修订实现，不得把本单元冲突推迟到未来章节。每种包含：

- 预测内容
- 证据依据
- 可信度
- 风险
- 推荐写法
- 局部结尾

## 证据包
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

    editorial_prompt_path = out_dir / "editorial_revision_prompt.md"
    evidence_markdown = "\n".join(
        (
            f"### [{item.id}] {item.chapter_title}\n"
            f"- 位置：第 {item.chapter_index} 章，第 {item.paragraph_index} 段\n"
            f"- 命中：{'、'.join(item.matched_terms) if item.matched_terms else '无'}\n"
            f"- 原文摘录：{item.excerpt}\n"
        )
        for item in evidence
    )
    editorial_prompt_path.write_text(
        render_editorial_revision_prompt(
            query or DEFAULT_REVIEW_QUERY,
            len(evidence),
            focus_entities,
            source_pack_name=source_path.name,
            evidence_pack_name=evidence_path.name,
        )
        + "\n\n"
        + evidence_markdown,
        encoding="utf-8",
    )

    return {
        "source_pack": source_path.name,
        "source_manifest": manifest_path.name,
        "review_evidence_pack": evidence_path.name,
        "review_prompt": prompt_path.name,
        "editorial_revision_prompt": editorial_prompt_path.name,
        "source_chapter_count": source_manifest["chapter_count"],
        "source_truncated_by_budget": source_manifest["truncated_by_budget"],
        "review_evidence_count": len(evidence),
    }

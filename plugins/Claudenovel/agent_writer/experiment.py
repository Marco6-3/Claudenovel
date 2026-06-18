"""A/B experiment framework for testing memory-augmented chapter generation.

Variants:
  A: chapter contract only (baseline)
  B: contract + handoff
  C: contract + handoff + author decisions
  D: contract + handoff + author decisions + foreshadowing ledger
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .llm_client import build_client
from .models import (
    AuthorDecision,
    ChapterContract,
    ChapterHandoff,
    CharacterConstraints,
    PrewritePlan,
)
from .paths import (
    constraints_path as _constraints_path,
    contract_path as _contract_path,
    handoff_path as _handoff_path,
    prewrite_path as _prewrite_path,
)
from .quality_gate import evaluate_draft
from .rules import render_rules_for_prompt
from .storage import chapter_id, ensure_project, read_json, read_model, read_text, write_text

VARIANTS = ("A", "B", "C", "D")


@dataclass
class VariantScore:
    variant: str
    chapter_number: int
    blocking: bool = False
    issue_codes: list[str] = field(default_factory=list)
    payoff_hit: int = 0
    payoff_total: int = 0
    has_ending_hook: bool = False
    ai_flavor_count: int = 0
    author_forbidden_hit: int = 0
    character_violations: int = 0
    review_ok: bool = False
    draft_path: str = ""


def _build_variant_prompt(
    root: Path,
    chapter_number: int,
    variant: str,
) -> str:
    """Build a writer prompt with memory level determined by variant."""
    strategy = read_text(root / "story_bible" / "author_bible.md")
    contract = read_model(_contract_path(root, chapter_number), ChapterContract)
    constraints = read_model(_constraints_path(root, chapter_number), CharacterConstraints)
    prewrite = read_model(_prewrite_path(root, chapter_number), PrewritePlan)
    rules = render_rules_for_prompt()

    prompt = (
        f"# {contract.title} 写作任务书\n\n"
        "## 作者设定\n\n"
        f"{strategy}\n\n"
        "## 章节合同\n\n"
        f"- 章节目标：{contract.main_goal}\n"
        f"- 必须兑现：{', '.join(contract.required_payoffs)}\n"
        f"- 爽点类型：{contract.cool_point}\n"
        f"- 关系推进：{contract.relation_delta}\n"
        f"- 章尾钩子：{contract.ending_hook}\n\n"
        "## 角色边界\n\n"
        f"{constraints.model_dump_json(indent=2)}\n\n"
        "## Prewrite Plan\n\n"
        f"{prewrite.model_dump_json(indent=2)}\n\n"
    )

    # Variant B/C/D: add handoff
    if variant in ("B", "C", "D"):
        handoff_path = _handoff_path(root, chapter_number - 1)
        if handoff_path.exists():
            handoff = read_model(handoff_path, ChapterHandoff)
            prompt += (
                "## 上一章交接\n\n"
                f"- 摘要：{handoff.summary}\n"
                f"- 角色状态：{handoff.character_states}\n"
                f"- 未解问题：{', '.join(handoff.unresolved_questions)}\n"
                f"- 硬约束：{', '.join(handoff.hard_constraints)}\n\n"
            )

    # Variant C/D: add author decisions
    if variant in ("C", "D"):
        decisions_path = root / "state" / "author_decisions.json"
        if decisions_path.exists():
            decisions_data = read_json(decisions_path)
            for d in decisions_data.get("decisions", []):
                if d.get("chapter_number") == chapter_number - 1:
                    mods = d.get("modifications", [])
                    forbids = d.get("forbidden_directions", [])
                    prefs = d.get("next_chapter_preferences", [])
                    if mods or forbids or prefs:
                        prompt += (
                            "## 作者对上一章的确认意见\n\n"
                            + (f"- 修改要求：{', '.join(mods)}\n" if mods else "")
                            + (f"- 下一章偏好：{', '.join(prefs)}\n" if prefs else "")
                            + (f"- 禁止方向：{', '.join(forbids)}\n" if forbids else "")
                            + "\n"
                        )
                    break

    # Variant D: add foreshadowing ledger
    if variant == "D":
        foreshadowing_path = root / "state" / "foreshadowing_ledger.json"
        if foreshadowing_path.exists():
            foreshadowing = read_json(foreshadowing_path)
            active = [
                item for item in foreshadowing.get("items", [])
                if item.get("status", "active") == "active"
            ]
            if active:
                lines = []
                for item in active:
                    eid = item.get("id", f"FS-{item.get('planted_chapter', '?')}")
                    lines.append(f"- [{eid}] {item.get('content', '')}")
                prompt += "## 活跃伏笔\n\n" + "\n".join(lines) + "\n\n"

    prompt += (
        "## 调研规则包\n\n"
        f"{rules}\n\n"
        "## 写作规则\n\n"
        "- 只写正文，不解释流程。\n"
        "- 不使用隐藏/未来章节信息。\n"
        "- 不新增未授权系统、数值、被动能力或力量体系。\n"
        "- 结尾最后三到五段必须落到章尾钩子。\n"
    )
    return prompt


def _score_variant(
    root: Path,
    chapter_number: int,
    variant: str,
    draft_text: str,
) -> VariantScore:
    """Score a draft against contract and quality dimensions."""
    contract = read_model(_contract_path(root, chapter_number), ChapterContract)
    constraints = read_model(_constraints_path(root, chapter_number), CharacterConstraints)

    # Load author forbidden for scoring
    author_forbidden: list[str] = []
    decisions_path = root / "state" / "author_decisions.json"
    if decisions_path.exists():
        decisions_data = read_json(decisions_path)
        for d in decisions_data.get("decisions", []):
            if d.get("chapter_number") == chapter_number - 1:
                author_forbidden = d.get("forbidden_directions", [])
                break

    issues = evaluate_draft(draft_text, contract, constraints, author_forbidden)

    score = VariantScore(variant=variant, chapter_number=chapter_number)
    score.blocking = any(i.severity == "blocking" for i in issues)
    score.issue_codes = [i.code for i in issues]
    score.review_ok = not score.blocking

    # Payoff hit rate
    from .quality_gate import _contains
    score.payoff_total = len(contract.required_payoffs)
    score.payoff_hit = sum(1 for p in contract.required_payoffs if _contains(draft_text, p))

    # Ending hook
    ending_window = draft_text[-500:]
    score.has_ending_hook = _contains(ending_window, contract.ending_hook) if contract.ending_hook else True

    # AI flavor count
    from .quality_gate import AI_FLAVOR_PATTERNS, _first_match
    score.ai_flavor_count = sum(1 for p in AI_FLAVOR_PATTERNS if p.search(draft_text))

    # Author forbidden violations
    score.author_forbidden_hit = sum(1 for d in author_forbidden if _contains(draft_text, d))

    # Character violations
    score.character_violations = sum(
        1 for i in issues if i.code in ("character_boundary_violation", "ooc_red_line")
    )

    return score


def run_experiment(
    project_root: Path,
    *,
    chapter_number: int,
    variants: list[str] | None = None,
    temperature: float = 0.7,
    max_tokens: int = 2200,
) -> dict[str, object]:
    """Run A/B experiment for a single chapter across specified variants."""
    root = ensure_project(project_root)
    variants = variants or list(VARIANTS)
    client = build_client(root)

    scores: list[VariantScore] = []
    prompts_dir = root / "prompts"

    for variant in variants:
        prompt = _build_variant_prompt(root, chapter_number, variant)

        # Save variant prompt for inspection
        prompt_path = prompts_dir / f"{chapter_id(chapter_number)}_variant_{variant}_prompt.md"
        write_text(prompt_path, prompt)

        # Generate draft
        content = client.complete(prompt, temperature=temperature, max_tokens=max_tokens)

        # Save variant draft
        draft_dir = root / "drafts"
        variant_draft_path = draft_dir / f"{chapter_id(chapter_number)}_variant_{variant}_draft.md"
        write_text(variant_draft_path, content + "\n")

        # Score
        score = _score_variant(root, chapter_number, variant, content)
        score.draft_path = str(variant_draft_path)
        scores.append(score)

    # Generate report
    report = _generate_experiment_report(root, chapter_number, scores)
    return {
        "chapter_number": chapter_number,
        "variants": [s.variant for s in scores],
        "scores": [s.__dict__ for s in scores],
        "report": str(report),
    }


def _generate_experiment_report(
    root: Path,
    chapter_number: int,
    scores: list[VariantScore],
) -> Path:
    """Generate markdown experiment report comparing variants."""
    lines = [
        f"# 第{chapter_number}章 A/B 实验报告",
        "",
        f"## 实验设置",
        "",
        f"- 章节：第{chapter_number}章",
        f"- 变体数：{len(scores)}",
        "- 评分维度：payoff 兑现率、尾钩命中、AI 味表达数、阻断项数、角色越界数",
        "",
        "## 结果总览",
        "",
        "| 变体 | 阻断 | Payoff | 尾钩 | AI味 | 角色越界 | 通过 |",
        "|------|------|--------|------|------|----------|------|",
    ]

    for s in scores:
        payoff_str = f"{s.payoff_hit}/{s.payoff_total}"
        hook_str = "✓" if s.has_ending_hook else "✗"
        block_str = "✓" if s.blocking else "✗"
        ok_str = "✓" if s.review_ok else "✗"
        lines.append(
            f"| {s.variant} | {block_str} | {payoff_str} | {hook_str} | {s.ai_flavor_count} | {s.character_violations} | {ok_str} |"
        )

    lines.extend([
        "",
        "## 详细分析",
        "",
    ])

    for s in scores:
        lines.append(f"### 变体 {s.variant}")
        lines.append("")
        lines.append(f"- 阻断项：{'有' if s.blocking else '无'}")
        if s.issue_codes:
            lines.append(f"- 问题代码：{', '.join(s.issue_codes)}")
        lines.append(f"- Payoff 兑现：{s.payoff_hit}/{s.payoff_total}")
        lines.append(f"- 尾钩命中：{'是' if s.has_ending_hook else '否'}")
        lines.append(f"- AI 味表达：{s.ai_flavor_count} 处")
        lines.append(f"- 角色越界：{s.character_violations} 处")
        lines.append(f"- 作者禁区触犯：{s.author_forbidden_hit} 处")
        lines.append(f"- 草稿路径：{s.draft_path}")
        lines.append("")

    # Determine winner
    passing = [s for s in scores if s.review_ok]
    if passing:
        # Rank by: fewer issues, more payoffs, fewer AI flavors
        passing.sort(key=lambda s: (
            len(s.issue_codes),
            -s.payoff_hit,
            s.ai_flavor_count,
        ))
        winner = passing[0]
        lines.extend([
            "## 结论",
            "",
            f"最优变体：**{winner.variant}**",
            "",
            f"- 问题最少（{len(winner.issue_codes)} 个）",
            f"- Payoff 兑现率最高（{winner.payoff_hit}/{winner.payoff_total}）",
            f"- AI 味表达最少（{winner.ai_flavor_count} 处）",
        ])
    else:
        lines.extend([
            "## 结论",
            "",
            "所有变体均未通过质量门禁。需要调整章节合同或降低生成难度。",
        ])

    lines.extend([
        "",
        "---",
        "",
        f"*报告生成时间：{scores[0].draft_path}*",
    ])

    report_path = root / f"experiment_report_ch{chapter_number:04d}.md"
    return write_text(report_path, "\n".join(lines))

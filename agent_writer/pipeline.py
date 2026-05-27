from __future__ import annotations

import json
from pathlib import Path

from .models import (
    AuthorDecision,
    AuthorStrategy,
    ChapterCommit,
    ChapterContract,
    ChapterHandoff,
    CharacterConstraint,
    CharacterConstraints,
    DecisionCandidate,
    ForeshadowingCandidate,
    ForeshadowingItem,
    FutureDirection,
    PrewritePlan,
    ReaderExpectationMap,
    ReviewResult,
    WorkflowEvaluation,
    WorkflowEvaluationItem,
)
from . import index_store
from .llm_client import build_client
from .quality_gate import evaluate_draft
from .rules import render_rules_for_prompt
from .storage import chapter_id, copy_utf8, ensure_project, read_json, read_model, read_text, write_json, write_text


def _strategy_path(root: Path) -> Path:
    return root / "story_bible" / "writer_strategy.json"


def _expectation_path(root: Path) -> Path:
    return root / "expectations" / "reader_expectation_map.json"


def _contract_path(root: Path, chapter_number: int) -> Path:
    return root / "chapter_contracts" / f"{chapter_id(chapter_number)}_contract.json"


def _constraints_path(root: Path, chapter_number: int) -> Path:
    return root / "chapter_contracts" / f"{chapter_id(chapter_number)}_character_constraints.json"


def _prewrite_path(root: Path, chapter_number: int) -> Path:
    return root / "chapter_contracts" / f"{chapter_id(chapter_number)}_prewrite_plan.json"


def _draft_path(root: Path, chapter_number: int) -> Path:
    return root / "drafts" / f"{chapter_id(chapter_number)}_draft.md"


def _review_path(root: Path, chapter_number: int) -> Path:
    return root / "reviews" / f"{chapter_id(chapter_number)}_review.json"


def _accepted_path(root: Path, chapter_number: int) -> Path:
    return root / "accepted" / f"{chapter_id(chapter_number)}.md"


def _commit_path(root: Path, chapter_number: int) -> Path:
    return root / "commits" / f"{chapter_id(chapter_number)}_commit.json"


def _discussion_path(root: Path, chapter_number: int) -> Path:
    return root / "author_discussion" / f"{chapter_id(chapter_number)}_packet.md"


def _handoff_path(root: Path, chapter_number: int) -> Path:
    return root / "handoffs" / f"{chapter_id(chapter_number)}_handoff.json"


def _handoff_md_path(root: Path, chapter_number: int) -> Path:
    return root / "handoffs" / f"{chapter_id(chapter_number)}_handoff.md"


def _candidate_json_path(root: Path, chapter_number: int) -> Path:
    return root / "author_discussion" / f"{chapter_id(chapter_number)}_decision_candidate.json"


def _candidate_md_path(root: Path, chapter_number: int) -> Path:
    return root / "author_discussion" / f"{chapter_id(chapter_number)}_decision_candidate.md"


def _evaluation_json_path(root: Path, chapter_number: int) -> Path:
    return root / "evaluations" / f"workflow_evaluation_{chapter_id(chapter_number)}.json"


def _evaluation_md_path(root: Path, chapter_number: int) -> Path:
    return root / "evaluations" / f"workflow_evaluation_{chapter_id(chapter_number)}.md"


def init_project(
    project_root: Path,
    *,
    name: str,
    genre: str,
    premise: str,
    target_reader: str,
) -> dict[str, str]:
    root = ensure_project(project_root)
    strategy = AuthorStrategy(
        project_name=name,
        genre=genre,
        premise=premise,
        target_reader=target_reader,
        core_hook="待补充：一句话说明读者为什么追读本书。",
        market_position="单章极致质量优先，先证明章节功能闭环。",
        style_fingerprint=["中文网文口吻", "动作先于解释", "段落短而有推进"],
        relationship_policy=["关系推进必须由共同经历、风险代价或明确证据支撑"],
        system_rule_policy=["新增系统/数值/被动能力必须先写入章节合同 allowed_system_changes"],
        forbidden_moves=[
            "禁止让模型假设已读未来章节",
            "禁止用胁迫、威胁、公开羞辱、堵人制造 romance",
            "禁止未授权新增任务、数值、被动能力或力量体系",
        ],
    )
    expectation = ReaderExpectationMap(
        target_reader=target_reader,
        promised_rewards=["每章至少一个明确读者收益", "章尾必须制造下一章问题"],
        cool_point_cycle=["小爽点", "信息增量", "关系推进", "冲突升级", "尾钩"],
        hook_policy=["爽点释放后立刻开新问题", "最后三到五段服务追读"],
        taboo=["只铺垫不兑现", "连续重复同一种爽点", "用解释替代事件"],
    )

    paths = {
        "writer_strategy": str(write_json(_strategy_path(root), strategy)),
        "reader_expectation_map": str(write_json(_expectation_path(root), expectation)),
        "author_bible": str(
            write_text(
                root / "story_bible" / "author_bible.md",
                "# Author Bible\n\n"
                "## 作者策略\n\n"
                f"- 项目名：{name}\n"
                f"- 题材：{genre}\n"
                f"- 前提：{premise}\n"
                f"- 目标读者：{target_reader}\n\n"
                "## 不变量\n\n"
                "- 只使用已确认设定、已写章节和当前章节合同。\n"
                "- 隐藏/未来章节只允许用于事后评估。\n",
            )
        ),
    }

    for state_file, payload in {
        "characters.json": {"characters": []},
        "relationship_state.json": {"relationships": [], "history": []},
        "foreshadowing_ledger.json": {"items": []},
        "system_rule_ledger.json": {"rules": [], "changes": []},
        "chapter_summaries.json": {"chapters": []},
        "author_decisions.json": {"decisions": []},
        "future_direction_ledger.json": {"directions": []},
    }.items():
        paths[state_file] = str(write_json(root / "state" / state_file, payload))
    index_store.connect(root).close()
    return paths


def plan_chapter(
    project_root: Path,
    *,
    chapter_number: int,
    title: str,
    goal: str,
    required_payoffs: list[str],
    ending_hook: str,
    forbidden_beats: list[str] | None = None,
    characters: list[str] | None = None,
) -> dict[str, str]:
    root = ensure_project(project_root)
    strategy = read_model(_strategy_path(root), AuthorStrategy)
    expectation = read_model(_expectation_path(root), ReaderExpectationMap)
    forbidden = list(forbidden_beats or [])
    forbidden.extend(strategy.forbidden_moves)

    contract = ChapterContract(
        chapter_number=chapter_number,
        title=title,
        main_goal=goal,
        required_payoffs=required_payoffs,
        forbidden_beats=forbidden,
        cool_point=expectation.cool_point_cycle[chapter_number % len(expectation.cool_point_cycle)],
        relation_delta="只推进半格；必须有共同经历或风险代价作为证据。",
        foreshadowing_ops=["延续一个旧问题，最多新增一个新问题。"],
        ending_hook=ending_hook,
        allowed_sources=["story_bible", "state", "previous_accepted_chapters", "current_chapter_contract"],
    )
    constraint_items = [
        CharacterConstraint(
            name=name,
            current_stage="待从作者设定或上一章状态确认",
            motivation="服务本章目标，但不得覆盖既有人设。",
            allowed_actions=["围绕本章目标作出有限、可解释的行动"],
            forbidden_actions=["突然表白", "主动依附", "无证据无条件信任"],
            voice_rules=["保留既有称呼、句长和情绪外露程度"],
            ooc_red_lines=["突然表白", "无证据无条件信任"],
        )
        for name in (characters or [])
    ]
    constraints = CharacterConstraints(chapter_number=chapter_number, characters=constraint_items)
    plan = PrewritePlan(
        chapter_number=chapter_number,
        focus=goal,
        main_conflict=f"围绕「{goal}」制造阻碍，并让 payoff 以事件形式发生。",
        scene_order=[
            "承接上一章尾钩",
            "抛出本章阻碍",
            "用行动推进 required payoff",
            "短暂兑现读者收益",
            "收束到新尾钩",
        ],
        must_include=required_payoffs,
        must_avoid=forbidden,
        ending_strategy=ending_hook,
    )

    contract_path = write_json(_contract_path(root, chapter_number), contract)
    constraints_path = write_json(_constraints_path(root, chapter_number), constraints)
    prewrite_path = write_json(_prewrite_path(root, chapter_number), plan)
    index_store.save_contract(root, contract, contract_path)
    index_store.upsert_artifact(root, chapter_number, "character_constraints", constraints_path)
    index_store.upsert_artifact(root, chapter_number, "prewrite_plan", prewrite_path)
    return {
        "contract": str(contract_path),
        "character_constraints": str(constraints_path),
        "prewrite_plan": str(prewrite_path),
    }


def _load_state_context(root: Path, chapter_number: int) -> str:
    """Load state context: handoff, author decisions, active foreshadowing."""
    sections: list[str] = []

    # Previous handoff
    prev_handoff_path = _handoff_path(root, chapter_number - 1)
    if prev_handoff_path.exists():
        handoff = read_model(prev_handoff_path, ChapterHandoff)
        sections.append(
            f"### 上一章交接（第{handoff.from_chapter}章 → 第{handoff.to_chapter}章）\n\n"
            f"- 摘要：{handoff.summary}\n"
            f"- 角色状态：{handoff.character_states}\n"
            f"- 未解问题：{', '.join(handoff.unresolved_questions) if handoff.unresolved_questions else '无'}\n"
            f"- 作者方向：{handoff.author_direction or '无特别指示'}\n"
            f"- 硬约束：{', '.join(handoff.hard_constraints) if handoff.hard_constraints else '无'}\n"
        )

    # Author decisions for previous chapter
    decisions_path = root / "state" / "author_decisions.json"
    if decisions_path.exists():
        decisions_data = read_json(decisions_path)
        for d in decisions_data.get("decisions", []):
            if d.get("chapter_number") == chapter_number - 1:
                mods = d.get("modifications", [])
                forbids = d.get("forbidden_directions", [])
                prefs = d.get("next_chapter_preferences", [])
                if mods or forbids or prefs:
                    sections.append(
                        f"### 作者对第{chapter_number - 1}章的确认意见\n\n"
                        + (f"- 修改要求：{', '.join(mods)}\n" if mods else "")
                        + (f"- 下一章偏好：{', '.join(prefs)}\n" if prefs else "")
                        + (f"- 禁止方向：{', '.join(forbids)}\n" if forbids else "")
                    )
                break

    # Active foreshadowing
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
                lines.append(f"- [{eid}] {item.get('content', '')}（埋设于第{item.get('planted_chapter', '?')}章）")
            sections.append("### 活跃伏笔\n\n" + "\n".join(lines))

    if not sections:
        return ""
    return "\n\n".join(sections)


def write_chapter_prompt(
    project_root: Path,
    *,
    chapter_number: int,
    draft_file: Path | None = None,
) -> dict[str, str]:
    root = ensure_project(project_root)
    strategy = read_text(root / "story_bible" / "author_bible.md")
    contract = read_model(_contract_path(root, chapter_number), ChapterContract)
    constraints = read_model(_constraints_path(root, chapter_number), CharacterConstraints)
    prewrite = read_model(_prewrite_path(root, chapter_number), PrewritePlan)
    rules = render_rules_for_prompt()
    state_context = _load_state_context(root, chapter_number)

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

    if state_context:
        prompt += "## 记忆上下文（来自上一章交接和作者决策）\n\n" + state_context + "\n\n"

    prompt += (
        "## 调研规则包\n\n"
        f"{rules}\n\n"
        "## 写作规则\n\n"
        "- 只写正文，不解释流程。\n"
        "- 不使用隐藏/未来章节信息。\n"
        "- 不新增未授权系统、数值、被动能力或力量体系。\n"
        "- 结尾最后三到五段必须落到章尾钩子。\n"
    )
    prompt_path = root / "prompts" / f"{chapter_id(chapter_number)}_writer_prompt.md"
    result = {"prompt": str(write_text(prompt_path, prompt))}
    index_store.upsert_artifact(root, chapter_number, "writer_prompt", prompt_path)
    if draft_file is not None:
        imported = copy_utf8(draft_file, _draft_path(root, chapter_number))
        index_store.upsert_artifact(root, chapter_number, "draft", imported)
        result["draft"] = str(imported)
    return result


def generate_draft(
    project_root: Path,
    *,
    chapter_number: int,
    temperature: float = 0.7,
    max_tokens: int = 2200,
) -> dict[str, str]:
    root = ensure_project(project_root)
    prompt_info = write_chapter_prompt(root, chapter_number=chapter_number)
    prompt_path = Path(prompt_info["prompt"])
    client = build_client(root)
    content = client.complete(read_text(prompt_path), temperature=temperature, max_tokens=max_tokens)
    draft_path = write_text(_draft_path(root, chapter_number), content + "\n")
    index_store.upsert_artifact(root, chapter_number, "draft", draft_path)
    return {"draft": str(draft_path), "prompt": str(prompt_path), "model": client.config.model}


def review_chapter(project_root: Path, *, chapter_number: int, draft_file: Path | None = None) -> ReviewResult:
    root = ensure_project(project_root)
    draft_path = draft_file or _draft_path(root, chapter_number)
    contract = read_model(_contract_path(root, chapter_number), ChapterContract)
    constraints = read_model(_constraints_path(root, chapter_number), CharacterConstraints)

    # Load author forbidden directions for this chapter
    author_forbidden: list[str] = []
    decisions_path = root / "state" / "author_decisions.json"
    if decisions_path.exists():
        decisions_data = read_json(decisions_path)
        prev_chapter = chapter_number - 1
        for d in decisions_data.get("decisions", []):
            if d.get("chapter_number") == prev_chapter:
                author_forbidden = d.get("forbidden_directions", [])
                break

    issues = evaluate_draft(read_text(draft_path), contract, constraints, author_forbidden)
    blocking = any(issue.severity == "blocking" for issue in issues)
    result = ReviewResult(
        chapter_number=chapter_number,
        ok=not blocking,
        blocking=blocking,
        issues=issues,
        rewrite_instructions=[issue.repair_hint for issue in issues if issue.repair_hint],
    )
    review_path = write_json(_review_path(root, chapter_number), result)
    index_store.save_review(root, result, review_path)
    return result


def write_rewrite_brief(project_root: Path, *, chapter_number: int) -> Path:
    root = ensure_project(project_root)
    review = read_model(_review_path(root, chapter_number), ReviewResult)
    draft = read_text(_draft_path(root, chapter_number))
    lines = [
        f"# {chapter_id(chapter_number)} 返修 Brief",
        "",
        "## 状态",
        "",
        f"- blocking: {review.blocking}",
        f"- ok: {review.ok}",
    ]
    if review.blocking:
        lines.append("阻断项必须先回到章节合同或正文骨架修复，不得只做润色。")
    lines.extend(["", "## 问题明细", ""])
    for issue in review.issues:
        lines.append(f"- [{issue.severity}] {issue.code}: {issue.message}")
        if issue.evidence:
            lines.append(f"  evidence: {issue.evidence}")
    lines.extend(["", "## 返修指令", ""])
    for instruction in review.rewrite_instructions:
        lines.append(f"- {instruction}")
    lines.extend(["", "## 原稿", "", draft])
    return write_text(root / "prompts" / f"{chapter_id(chapter_number)}_rewrite_brief.md", "\n".join(lines))


def rewrite_draft(
    project_root: Path,
    *,
    chapter_number: int,
    temperature: float = 0.45,
    max_tokens: int = 2200,
) -> dict[str, str]:
    root = ensure_project(project_root)
    brief_path = write_rewrite_brief(root, chapter_number=chapter_number)
    contract = read_model(_contract_path(root, chapter_number), ChapterContract)
    client = build_client(root)
    prompt = (
        read_text(brief_path)
        + "\n\n## 重写硬要求\n\n"
        + "- 输出完整正文，不解释。\n"
        + "- 必须逐字包含以下 payoff："
        + "；".join(contract.required_payoffs)
        + "\n- 最后三到五段必须逐字包含尾钩："
        + contract.ending_hook
        + "\n- 不新增未授权系统、数值、被动能力或力量体系。\n"
    )
    content = client.complete(prompt, temperature=temperature, max_tokens=max_tokens)
    rewritten_path = write_text(root / "drafts" / f"{chapter_id(chapter_number)}_rewritten.md", content + "\n")
    copy_utf8(rewritten_path, _draft_path(root, chapter_number))
    index_store.upsert_artifact(root, chapter_number, "rewrite_brief", brief_path)
    index_store.upsert_artifact(root, chapter_number, "rewritten_draft", rewritten_path)
    index_store.upsert_artifact(root, chapter_number, "draft", _draft_path(root, chapter_number))
    return {"draft": str(_draft_path(root, chapter_number)), "rewritten_draft": str(rewritten_path), "model": client.config.model}


def commit_chapter(project_root: Path, *, chapter_number: int, approve: bool) -> ChapterCommit:
    if not approve:
        raise ValueError("commit requires explicit approve=True")
    root = ensure_project(project_root)
    review = read_model(_review_path(root, chapter_number), ReviewResult)
    if review.blocking:
        raise ValueError("cannot commit a chapter with blocking review issues")

    accepted = copy_utf8(_draft_path(root, chapter_number), _accepted_path(root, chapter_number))
    contract = read_model(_contract_path(root, chapter_number), ChapterContract)

    summaries_path = root / "state" / "chapter_summaries.json"
    summaries = read_json(summaries_path)
    chapters = list(summaries.get("chapters", []))
    chapters = [item for item in chapters if item.get("chapter_number") != chapter_number]
    chapters.append(
        {
            "chapter_number": chapter_number,
            "title": contract.title,
            "goal": contract.main_goal,
            "payoffs": contract.required_payoffs,
            "ending_hook": contract.ending_hook,
        }
    )
    write_json(summaries_path, {"chapters": sorted(chapters, key=lambda item: item["chapter_number"])})

    relation_path = root / "state" / "relationship_state.json"
    relation_state = read_json(relation_path)
    history = list(relation_state.get("history", []))
    history.append({"chapter_number": chapter_number, "delta": contract.relation_delta})
    relation_state["history"] = history
    write_json(relation_path, relation_state)

    foreshadowing_path = root / "state" / "foreshadowing_ledger.json"
    foreshadowing = read_json(foreshadowing_path)
    items = list(foreshadowing.get("items", []))
    for op in contract.foreshadowing_ops:
        items.append({"chapter_number": chapter_number, "operation": op})
    foreshadowing["items"] = items
    write_json(foreshadowing_path, foreshadowing)

    commit = ChapterCommit(
        chapter_number=chapter_number,
        status="accepted",
        accepted_file=str(accepted),
        review_file=str(_review_path(root, chapter_number)),
        contract_file=str(_contract_path(root, chapter_number)),
        state_updates={
            "chapter_summaries": True,
            "relationship_state": True,
            "foreshadowing_ledger": True,
        },
    )
    commit_path = write_json(_commit_path(root, chapter_number), commit)
    index_store.save_commit(root, commit, commit_path)
    return commit


def status_report(project_root: Path) -> dict[str, object]:
    root = ensure_project(project_root)
    contracts = sorted(root.glob("chapter_contracts/*_contract.json"))
    drafts = sorted(root.glob("drafts/*_draft.md"))
    reviews = sorted(root.glob("reviews/*_review.json"))
    accepted = sorted(root.glob("accepted/chapter_*.md"))
    return {
        "project_root": str(root),
        "contracts": len(contracts),
        "drafts": len(drafts),
        "reviews": len(reviews),
        "accepted": len(accepted),
        "latest_contract": contracts[-1].name if contracts else "",
        "latest_accepted": accepted[-1].name if accepted else "",
        "blocking_issues": len(index_store.blocking_issues(root)),
        "index_db": str(index_store.index_path(root)),
    }


def index_report(project_root: Path, *, limit: int = 20) -> dict[str, object]:
    root = ensure_project(project_root)
    return {
        "artifacts": index_store.latest_artifacts(root, limit=limit),
        "blocking_issues": index_store.blocking_issues(root),
    }


# --- Author memory pipeline ---


def generate_discussion_packet(
    project_root: Path,
    *,
    chapter_number: int,
) -> Path:
    """Generate an author discussion packet for a committed chapter."""
    root = ensure_project(project_root)
    contract = read_model(_contract_path(root, chapter_number), ChapterContract)
    review_path = _review_path(root, chapter_number)
    review = read_model(review_path, ReviewResult) if review_path.exists() else None
    draft = read_text(_draft_path(root, chapter_number))

    # Load foreshadowing for suggestions
    foreshadowing_path = root / "state" / "foreshadowing_ledger.json"
    active_foreshadowing = []
    if foreshadowing_path.exists():
        foreshadowing = read_json(foreshadowing_path)
        active_foreshadowing = [
            item for item in foreshadowing.get("items", [])
            if item.get("status", "active") == "active"
        ]

    # Check for decision candidate
    candidate_path = _candidate_json_path(root, chapter_number)
    candidate = None
    if candidate_path.exists():
        try:
            candidate = read_model(candidate_path, DecisionCandidate)
        except (ValueError, KeyError):
            candidate = None

    lines = [
        f"# 第{chapter_number}章 作者协商包",
        "",
        f"## 本章信息",
        "",
        f"- 标题：{contract.title}",
        f"- 目标：{contract.main_goal}",
        f"- 必须兑现：{', '.join(contract.required_payoffs)}",
        f"- 尾钩：{contract.ending_hook}",
        "",
    ]

    # Show decision candidate summary if available
    if candidate:
        lines.extend([
            "## 分析系统生成的决策候选",
            "",
            f"> 来源文件：{', '.join(candidate.source_files) if candidate.source_files else '无'}",
            f"> 保留理由：{candidate.keep_reason}",
            "",
            "以下为分析系统自动生成的候选内容，请勾选、修改或删除后确认。",
            "",
        ])
        if candidate.modifications:
            lines.append("### 建议修改")
            lines.append("")
            for i, mod in enumerate(candidate.modifications):
                ev = candidate.modification_evidence[i] if i < len(candidate.modification_evidence) else "证据不足"
                lines.append(f"- [ ] {mod}（证据：{ev}）")
            lines.append("")
        if candidate.next_chapter_preferences:
            lines.append("### 建议下一章方向")
            lines.append("")
            for i, pref in enumerate(candidate.next_chapter_preferences):
                ev = candidate.preference_evidence[i] if i < len(candidate.preference_evidence) else "证据不足"
                lines.append(f"- [ ] {pref}（证据：{ev}）")
            lines.append("")
        if candidate.forbidden_directions:
            lines.append("### 建议禁区")
            lines.append("")
            for fd in candidate.forbidden_directions:
                lines.append(f"- [ ] {fd}")
            lines.append("")

    lines.extend([
        "## 本章可保留部分",
        "",
        "（请作者确认哪些部分值得保留）",
        "",
        "- [ ] 核心场景是否达到预期效果",
        "- [ ] 角色行为是否符合设定",
        "- [ ] 节奏和信息密度是否合适",
        "",
        "## 必须改掉的问题",
        "",
    ])
    if review and review.issues:
        for issue in review.issues:
            lines.append(f"- [{issue.severity}] {issue.code}: {issue.message}")
    else:
        lines.append("- 审稿通过，无阻断项。")

    lines.extend([
        "",
        "## 下一章建议方向（请选择或自定义）",
        "",
        "### 方向 A：延续当前冲突",
        f"- 从本章尾钩「{contract.ending_hook}」直接展开",
        "- 保持当前紧张度，快速推进",
        "",
        "### 方向 B：转换视角/场景",
        "- 切换到另一条故事线",
        "- 给读者喘息空间，同时埋新伏笔",
        "",
        "### 方向 C：深化角色关系",
        "- 用本章事件的后果推动角色互动",
        "- 关系推进需要共同经历作为证据",
        "",
        "## 伏笔管理",
        "",
        "### 当前活跃伏笔",
        "",
    ])
    if active_foreshadowing:
        for item in active_foreshadowing:
            eid = item.get("id", f"FS-{item.get('planted_chapter', '?')}")
            lines.append(f"- [{eid}] {item.get('content', '')}")
    else:
        lines.append("- 暂无活跃伏笔。")

    lines.extend([
        "",
        "### 本章伏笔操作",
        "",
        "- [ ] 是否推进了已有伏笔？",
        "- [ ] 是否新增了伏笔？（最多一个）",
        "- [ ] 是否可以回收某个伏笔？",
        "",
        "## 角色关系变化",
        "",
        "请确认本章是否产生了关系变化，以及变化的证据：",
        "",
        "- 关系变化：______",
        "- 证据/共同经历：______",
        "",
        "## 作者明确禁止的走向",
        "",
        "请列出下一章绝对不能出现的剧情走向：",
        "",
        "1. ______",
        "2. ______",
        "",
        "## 下一章必须兑现的 payoff",
        "",
        "请列出下一章必须包含的读者收益：",
        "",
        "1. ______",
        "",
        "---",
        "",
        "## 使用说明",
        "",
        "请将以上 `______` 部分填好，保存为 JSON 文件后运行：",
        "",
        "```powershell",
        f"python agent_writer_cli.py record-author-note --chapter {chapter_number} --decision-file <your-file.json>",
        "```",
        "",
        "JSON 格式示例：",
        "```json",
        "{",
        '  "chapter_number": ' + str(chapter_number) + ',',
        '  "keep_chapter": true,',
        '  "keep_reason": "核心场景效果好",',
        '  "modifications": ["第三段节奏太慢"],',
        '  "next_chapter_preferences": ["延续尾钩冲突"],',
        '  "forbidden_directions": ["不能让女主突然表白"],',
        '  "relationship_changes": ["共同经历后信任度+1"],',
        '  "notes": ""',
        "}",
        "```",
    ])

    packet_path = write_text(_discussion_path(root, chapter_number), "\n".join(lines))
    index_store.upsert_artifact(root, chapter_number, "discussion_packet", packet_path)
    return packet_path


def record_author_note(
    project_root: Path,
    *,
    chapter_number: int,
    decision_file: Path,
) -> dict[str, str]:
    """Record author decisions from a structured decision file."""
    root = ensure_project(project_root)
    decision = read_model(decision_file, AuthorDecision)
    if decision.chapter_number != chapter_number:
        raise ValueError(
            f"decision file chapter_number ({decision.chapter_number}) "
            f"does not match --chapter ({chapter_number})"
        )

    # 1. Write author decision
    decisions_path = root / "state" / "author_decisions.json"
    decisions_data = read_json(decisions_path)
    decisions_list = list(decisions_data.get("decisions", []))
    decisions_list = [d for d in decisions_list if d.get("chapter_number") != chapter_number]
    decisions_list.append(decision.model_dump(mode="json"))
    write_json(decisions_path, {"decisions": sorted(decisions_list, key=lambda d: d["chapter_number"])})

    # 2. Append future directions from next_chapter_preferences
    directions_path = root / "state" / "future_direction_ledger.json"
    directions_data = read_json(directions_path)
    directions_list = list(directions_data.get("directions", []))
    existing_ids = {d.get("id") for d in directions_list}
    for i, pref in enumerate(decision.next_chapter_preferences):
        did = f"FD-{chapter_number:04d}-{i + 1:02d}"
        if did not in existing_ids:
            directions_list.append(
                FutureDirection(
                    id=did,
                    description=pref,
                    source_chapter=chapter_number,
                ).model_dump(mode="json")
            )
    write_json(directions_path, {"directions": directions_list})

    # 3. Update foreshadowing ledger — append new items from decision notes
    # (New foreshadowing is typically embedded in the chapter text; this handles explicit additions)
    foreshadowing_path = root / "state" / "foreshadowing_ledger.json"
    foreshadowing_data = read_json(foreshadowing_path)
    items = list(foreshadowing_data.get("items", []))
    # Mark resolved items if author says so in notes
    if decision.notes and "回收伏笔" in decision.notes:
        for item in items:
            if item.get("status") == "active" and item.get("content", "") in decision.notes:
                item["status"] = "resolved"
                item["resolution_chapter"] = chapter_number
    foreshadowing_data["items"] = items
    write_json(foreshadowing_path, foreshadowing_data)

    # 4. Update relationship state if changes specified
    if decision.relationship_changes:
        relation_path = root / "state" / "relationship_state.json"
        relation_state = read_json(relation_path)
        history = list(relation_state.get("history", []))
        for change in decision.relationship_changes:
            history.append({"chapter_number": chapter_number, "delta": change})
        relation_state["history"] = history
        write_json(relation_path, relation_state)

    return {
        "decision": str(decisions_path),
        "directions": str(directions_path),
        "foreshadowing": str(foreshadowing_path),
    }


def generate_handoff(
    project_root: Path,
    *,
    chapter_number: int,
) -> dict[str, str]:
    """Generate a handoff package from committed chapter + author decisions."""
    root = ensure_project(project_root)
    contract = read_model(_contract_path(root, chapter_number), ChapterContract)
    draft = read_text(_draft_path(root, chapter_number))

    # Load author decision if available
    decisions_path = root / "state" / "author_decisions.json"
    author_decision = None
    if decisions_path.exists():
        decisions_data = read_json(decisions_path)
        for d in decisions_data.get("decisions", []):
            if d.get("chapter_number") == chapter_number:
                author_decision = AuthorDecision.model_validate(d)
                break

    # Load active foreshadowing
    foreshadowing_path = root / "state" / "foreshadowing_ledger.json"
    active_foreshadowing_ids: list[str] = []
    if foreshadowing_path.exists():
        foreshadowing = read_json(foreshadowing_path)
        active_foreshadowing_ids = [
            item.get("id", f"FS-{item.get('planted_chapter', '?')}")
            for item in foreshadowing.get("items", [])
            if item.get("status", "active") == "active"
        ]

    # Build character states from constraints
    constraints_path = _constraints_path(root, chapter_number)
    character_states: dict[str, str] = {}
    if constraints_path.exists():
        constraints = read_model(constraints_path, CharacterConstraints)
        for char in constraints.characters:
            character_states[char.name] = char.current_stage

    # Build unresolved questions from contract payoffs and ending hook
    unresolved = list(contract.required_payoffs)
    if contract.ending_hook:
        unresolved.append(contract.ending_hook)

    # Build hard constraints from forbidden beats + author forbidden directions
    hard_constraints = list(contract.forbidden_beats)
    hard_constraint_evidence: list[str] = []
    if author_decision and author_decision.forbidden_directions:
        hard_constraints.extend(author_decision.forbidden_directions)
        hard_constraint_evidence.extend(author_decision.evidence_refs)

    # Author direction
    author_direction = ""
    author_direction_evidence: list[str] = []
    if author_decision and author_decision.next_chapter_preferences:
        author_direction = "；".join(author_decision.next_chapter_preferences)
        author_direction_evidence.extend(author_decision.evidence_refs)

    # Required payoffs for next chapter (from author or auto-carry forward)
    required_next: list[str] = []
    if author_decision:
        # Use explicit author preferences as hints
        required_next = list(author_decision.next_chapter_preferences)

    handoff = ChapterHandoff(
        from_chapter=chapter_number,
        to_chapter=chapter_number + 1,
        summary=f"第{chapter_number}章「{contract.title}」完成：{contract.main_goal}",
        character_states=character_states,
        unresolved_questions=unresolved,
        active_foreshadowing=active_foreshadowing_ids,
        required_payoffs_next=required_next,
        hard_constraints=hard_constraints,
        hard_constraint_evidence=hard_constraint_evidence,
        author_direction=author_direction,
        author_direction_evidence=author_direction_evidence,
    )

    # Write JSON
    json_path = write_json(_handoff_path(root, chapter_number), handoff)

    # Write human-readable MD
    md_lines = [
        f"# 第{chapter_number}章 → 第{chapter_number + 1}章 交接包",
        "",
        f"## 摘要",
        f"{handoff.summary}",
        "",
        "## 角色状态",
    ]
    for name, stage in character_states.items():
        md_lines.append(f"- {name}：{stage}")
    md_lines.extend([
        "",
        "## 未解问题",
    ])
    for q in unresolved:
        md_lines.append(f"- {q}")
    md_lines.extend([
        "",
        "## 活跃伏笔",
    ])
    for fid in active_foreshadowing_ids:
        md_lines.append(f"- {fid}")
    md_lines.extend([
        "",
        "## 作者方向",
        f"{author_direction or '无特别指示'}",
        "",
        "## 硬约束（下一章禁止）",
    ])
    for c in hard_constraints:
        md_lines.append(f"- {c}")

    md_path = write_text(_handoff_md_path(root, chapter_number), "\n".join(md_lines))
    index_store.upsert_artifact(root, chapter_number, "handoff", json_path)
    return {"handoff_json": str(json_path), "handoff_md": str(md_path)}


def plan_next_chapter(
    project_root: Path,
    *,
    chapter_number: int,
    title: str,
    goal: str,
    required_payoffs: list[str],
    ending_hook: str,
    characters: list[str] | None = None,
) -> dict[str, str]:
    """Plan the next chapter using handoff + author decisions + foreshadowing."""
    root = ensure_project(project_root)
    prev_chapter = chapter_number - 1

    # Load previous handoff
    handoff_path = _handoff_path(root, prev_chapter)
    handoff = None
    if handoff_path.exists():
        handoff = read_model(handoff_path, ChapterHandoff)

    # Load author decision for previous chapter
    decisions_path = root / "state" / "author_decisions.json"
    author_decision = None
    if decisions_path.exists():
        decisions_data = read_json(decisions_path)
        for d in decisions_data.get("decisions", []):
            if d.get("chapter_number") == prev_chapter:
                author_decision = AuthorDecision.model_validate(d)
                break

    # Build forbidden beats from handoff + author decisions + strategy
    strategy = read_model(_strategy_path(root), AuthorStrategy)
    forbidden = list(strategy.forbidden_moves)
    if handoff and handoff.hard_constraints:
        forbidden.extend(handoff.hard_constraints)

    # Call standard plan_chapter
    result = plan_chapter(
        project_root,
        chapter_number=chapter_number,
        title=title,
        goal=goal,
        required_payoffs=required_payoffs,
        ending_hook=ending_hook,
        forbidden_beats=forbidden,
        characters=characters,
    )

    # Enrich the contract with handoff context
    contract = read_model(_contract_path(root, chapter_number), ChapterContract)
    if handoff:
        contract.previous_handoff = handoff.summary
        # Write evidence-backed constraints into allowed_sources
        if handoff.hard_constraint_evidence:
            contract.allowed_sources.extend(handoff.hard_constraint_evidence)
        if handoff.author_direction_evidence:
            contract.allowed_sources.extend(handoff.author_direction_evidence)
    if author_decision and author_decision.next_chapter_preferences:
        # Add author preferences to foreshadowing_ops with evidence refs
        pref_line = f"作者偏好：{'；'.join(author_decision.next_chapter_preferences)}"
        if author_decision.evidence_refs:
            pref_line += f"（证据：{', '.join(author_decision.evidence_refs)}）"
        contract.foreshadowing_ops = [
            pref_line,
            *contract.foreshadowing_ops,
        ]
    write_json(_contract_path(root, chapter_number), contract)
    result["handoff_loaded"] = str(handoff_path) if handoff else "none"
    return result


# --- Analysis-to-memory bridge ---


def _read_json_safe(path: Path) -> dict[str, object] | None:
    """Read a JSON file, returning None if it doesn't exist or is invalid."""
    if not path.exists():
        return None
    try:
        return read_json(path)
    except (ValueError, KeyError):
        return None


def _read_text_safe(path: Path) -> str | None:
    """Read a text file, returning None if it doesn't exist."""
    if not path.exists():
        return None
    return read_text(path)


def _extract_evidence_ids(text: str) -> list[str]:
    """Extract evidence IDs like [CH035-P001] from text."""
    import re
    return list(dict.fromkeys(re.findall(r"\[CH\d+-P\d+\]", text)))


def _extract_p0_issues_from_report(report_text: str) -> list[dict[str, str]]:
    """Extract P0 issues from an editorial report markdown."""
    import re
    issues: list[dict[str, str]] = []
    # Look for P0 markers in various formats
    for match in re.finditer(
        r"(?:P0|优先级.*?P0|最高优先级)[：:]\s*(.+?)(?:\n\n|\n(?=##)|\n(?=###)|\Z)",
        report_text,
        re.DOTALL,
    ):
        block = match.group(1).strip()
        evidence = _extract_evidence_ids(block)
        issues.append({"description": block[:500], "evidence": evidence})
    return issues


def _extract_continuation_routes_from_report(report_text: str) -> list[dict[str, str]]:
    """Extract continuation routes from an editorial report markdown."""
    import re
    routes: list[dict[str, str]] = []
    # Try to find routes section
    route_section = ""
    route_match = re.search(
        r"##\s*(?:后续剧情路线|续写路线|continuation routes)(.*?)(?=\n##\s|\Z)",
        report_text,
        re.DOTALL | re.IGNORECASE,
    )
    if route_match:
        route_section = route_match.group(1)

    # Extract individual routes (### 方向 A / Route A / 路线A etc.)
    for match in re.finditer(
        r"###?\s*(?:方向|路线|Route)\s*([A-Z\d])[：:]*\s*(.+?)(?=\n###?\s*(?:方向|路线|Route)|\Z)",
        route_section,
        re.DOTALL,
    ):
        label = match.group(1)
        body = match.group(2).strip()
        evidence = _extract_evidence_ids(body)
        routes.append({
            "label": label,
            "description": body[:800],
            "evidence": evidence,
        })
    return routes


def _extract_foreshadowing_from_evidence(
    evidence_items: list[dict[str, object]],
    active_foreshadowing: list[dict[str, object]],
) -> tuple[list[ForeshadowingCandidate], list[ForeshadowingCandidate]]:
    """Build foreshadowing candidates from evidence and existing ledger."""
    active: list[ForeshadowingCandidate] = []
    recyclable: list[ForeshadowingCandidate] = []

    for item in active_foreshadowing:
        eid = item.get("id", f"FS-{item.get('planted_chapter', '?')}")
        content = item.get("content", "")
        refs = [eid]
        # See if any evidence mentions this foreshadowing content
        for ev in evidence_items:
            excerpt = ev.get("excerpt", "")
            if content and any(token in excerpt for token in content.split()[:3]):
                refs.append(ev.get("id", ""))

        candidate = ForeshadowingCandidate(
            id=eid,
            content=content,
            evidence_refs=[r for r in refs if r],
            layer=item.get("layer", "支线"),
            suggested_action="continue",
            reason=f"活跃伏笔，埋设于第{item.get('planted_chapter', '?')}章",
        )
        active.append(candidate)

    return active, recyclable


def draft_author_note(
    project_root: Path,
    *,
    chapter_number: int,
    analysis_dir: Path,
) -> dict[str, str]:
    """Generate a decision candidate from analysis outputs.

    Reads available analysis files and produces a DecisionCandidate JSON + MD
    in author_discussion/. The candidate must be confirmed via record-author-note
    before any state is modified.

    Supported analysis files (all optional, graceful degradation on missing):
    - evidence_pack.json: scored evidence items with [CHxxx-Pxxx] IDs
    - editorial_revision_prompt.md or any *_report.md: editorial diagnosis
    - evidence_matrix.json: QA evidence with stances
    - review_evidence_pack.json: review-specific evidence
    - llm_source_pack_manifest.json: chapter/paragraph index
    """
    root = ensure_project(project_root)
    analysis_dir = Path(analysis_dir)
    source_files: list[str] = []

    # --- Read analysis outputs ---
    evidence_pack = _read_json_safe(analysis_dir / "evidence_pack.json")
    if evidence_pack:
        source_files.append("evidence_pack.json")

    # Try multiple report file names
    report_text = ""
    for report_name in (
        "editorial_revision_prompt.md",
        "review_improve_continue_prompt.md",
    ):
        text = _read_text_safe(analysis_dir / report_name)
        if text:
            report_text = text
            source_files.append(report_name)
            break

    # Also scan for any *_report.md files
    if not report_text:
        for md_file in sorted(analysis_dir.glob("*report*.md")):
            text = _read_text_safe(md_file)
            if text and len(text) > 200:
                report_text = text
                source_files.append(md_file.name)
                break

    evidence_matrix = _read_json_safe(analysis_dir / "evidence_matrix.json")
    if evidence_matrix is not None:
        source_files.append("evidence_matrix.json")

    review_evidence = _read_json_safe(analysis_dir / "review_evidence_pack.json")
    if review_evidence is not None:
        source_files.append("review_evidence_pack.json")

    manifest = _read_json_safe(analysis_dir / "llm_source_pack_manifest.json")
    if manifest is not None:
        source_files.append("llm_source_pack_manifest.json")

    # --- Extract evidence items ---
    evidence_items: list[dict[str, object]] = []
    if evidence_pack and "evidence" in evidence_pack:
        evidence_items = evidence_pack["evidence"]  # type: ignore[assignment]

    # --- Build candidates from evidence ---
    all_evidence_ids: list[str] = []
    for item in evidence_items:
        eid = item.get("id", "")
        if eid:
            all_evidence_ids.append(f"[{eid}]")

    # --- Extract P0 issues as modification candidates ---
    p0_issues = _extract_p0_issues_from_report(report_text) if report_text else []
    modifications: list[str] = []
    modification_evidence: list[str] = []
    for issue in p0_issues:
        desc = issue["description"]
        modifications.append(desc[:200])
        modification_evidence.extend(issue.get("evidence", []))

    # --- Extract continuation routes as preference candidates ---
    routes = _extract_continuation_routes_from_report(report_text) if report_text else []
    preferences: list[str] = []
    preference_evidence: list[str] = []
    for route in routes:
        label = route["label"]
        desc = route["description"][:200]
        preferences.append(f"方向{label}：{desc}")
        preference_evidence.extend(route.get("evidence", []))

    # --- Load existing foreshadowing ledger ---
    foreshadowing_path = root / "state" / "foreshadowing_ledger.json"
    active_foreshadowing: list[dict[str, object]] = []
    if foreshadowing_path.exists():
        fs_data = read_json(foreshadowing_path)
        active_foreshadowing = [
            item for item in fs_data.get("items", [])
            if item.get("status", "active") == "active"
        ]

    fs_active, fs_recyclable = _extract_foreshadowing_from_evidence(
        evidence_items, active_foreshadowing
    )

    # --- Build keep reason from evidence quality ---
    keep_reason = ""
    keep_evidence: list[str] = []
    if evidence_items:
        top_items = sorted(evidence_items, key=lambda x: x.get("score", 0), reverse=True)[:3]
        keep_reason = f"分析产出 {len(evidence_items)} 条证据"
        keep_evidence = [f"[{item.get('id', '')}]" for item in top_items if item.get("id")]
    else:
        keep_reason = "证据不足：未找到分析证据文件"

    # --- Build candidate ---
    candidate = DecisionCandidate(
        chapter_number=chapter_number,
        keep_chapter=True,
        keep_reason=keep_reason,
        keep_evidence=keep_evidence,
        modifications=modifications,
        modification_evidence=modification_evidence,
        next_chapter_preferences=preferences,
        preference_evidence=preference_evidence,
        forbidden_directions=[],
        forbidden_evidence=[],
        foreshadowing_active=fs_active,
        foreshadowing_recyclable=fs_recyclable,
        character_state_candidates={},
        relationship_changes=[],
        relationship_evidence=[],
        required_payoffs_next=[],
        notes="从分析产物自动生成的候选，请作者确认后通过 record-author-note 写入状态。",
        source_files=source_files,
    )

    # --- Write JSON ---
    json_path = write_json(_candidate_json_path(root, chapter_number), candidate)

    # --- Write human-readable MD ---
    md_lines = [
        f"# 第{chapter_number}章 决策候选（从分析产物生成）",
        "",
        "> 此文件为分析系统自动生成的候选，**不会直接写入长期状态**。",
        "> 请作者审阅、修改后，通过 `record-author-note` 确认。",
        "",
        "## 数据来源",
        "",
    ]
    if source_files:
        for sf in source_files:
            md_lines.append(f"- {sf}")
    else:
        md_lines.append("- 未找到分析文件，候选内容为空")

    md_lines.extend([
        "",
        "## 建议保留",
        "",
        f"- 保留本章：{'是' if candidate.keep_chapter else '否'}",
        f"- 理由：{candidate.keep_reason}",
    ])
    if keep_evidence:
        md_lines.append(f"- 证据：{', '.join(keep_evidence)}")

    md_lines.extend(["", "## 建议修改的问题", ""])
    if modifications:
        for i, mod in enumerate(modifications):
            ev = modification_evidence[i] if i < len(modification_evidence) else "证据不足"
            md_lines.append(f"{i + 1}. {mod}")
            md_lines.append(f"   - 证据：{ev}")
    else:
        md_lines.append("- 无 P0 问题（或未找到编辑报告）")

    md_lines.extend(["", "## 下一章发展方向候选", ""])
    if preferences:
        for i, pref in enumerate(preferences):
            ev = preference_evidence[i] if i < len(preference_evidence) else "证据不足"
            md_lines.append(f"{i + 1}. {pref}")
            md_lines.append(f"   - 证据：{ev}")
    else:
        md_lines.append("- 无续写路线候选（或未找到编辑报告）")

    md_lines.extend(["", "## 活跃伏笔候选", ""])
    if fs_active:
        for item in fs_active:
            md_lines.append(f"- [{item.id}] {item.content}（建议：{item.suggested_action}）")
            if item.evidence_refs:
                md_lines.append(f"  - 证据：{', '.join(item.evidence_refs)}")
    else:
        md_lines.append("- 无活跃伏笔")

    md_lines.extend(["", "## 可回收伏笔候选", ""])
    if fs_recyclable:
        for item in fs_recyclable:
            md_lines.append(f"- [{item.id}] {item.content}（建议：{item.suggested_action}）")
    else:
        md_lines.append("- 无可回收伏笔")

    md_lines.extend([
        "",
        "## 角色/关系状态变化候选",
        "",
    ])
    if candidate.character_state_candidates:
        for name, state in candidate.character_state_candidates.items():
            md_lines.append(f"- {name}：{state}")
    else:
        md_lines.append("- 无角色状态候选")

    if candidate.relationship_changes:
        for change in candidate.relationship_changes:
            md_lines.append(f"- {change}")
    else:
        md_lines.append("- 无关系变化候选")

    md_lines.extend([
        "",
        "## 作者禁区候选",
        "",
    ])
    if candidate.forbidden_directions:
        for fd in candidate.forbidden_directions:
            md_lines.append(f"- {fd}")
    else:
        md_lines.append("- 无禁区候选（请作者手动添加）")

    md_lines.extend([
        "",
        "---",
        "",
        "## 确认方式",
        "",
        "将以上内容编辑为 JSON 文件后运行：",
        "",
        "```powershell",
        f"python agent_writer_cli.py record-author-note --chapter {chapter_number} --decision-file <your-file.json>",
        "```",
        "",
        "或直接编辑此候选后运行 discuss 生成完整协商包。",
    ])

    md_path = write_text(_candidate_md_path(root, chapter_number), "\n".join(md_lines))

    index_store.upsert_artifact(root, chapter_number, "decision_candidate", json_path)
    return {
        "candidate_json": str(json_path),
        "candidate_md": str(md_path),
        "source_files": source_files,
    }


# --- Workflow evaluation ---


def evaluate_workflow(
    project_root: Path,
    *,
    chapter_number: int,
) -> WorkflowEvaluation:
    """Evaluate the author-memory workflow for a chapter.

    Checks evidence propagation through: candidate → decision → handoff → contract → prompt → draft.
    Gracefully degrades when files are missing (marks check as 'skip').
    """
    root = ensure_project(project_root)
    next_chapter = chapter_number + 1
    checks: list[WorkflowEvaluationItem] = []
    missing: list[str] = []

    def _load(path: Path, label: str):
        if not path.exists():
            missing.append(label)
            return None
        try:
            return read_json(path)
        except (ValueError, KeyError):
            missing.append(f"{label} (invalid)")
            return None

    # Load all artifacts
    candidate_data = _load(_candidate_json_path(root, chapter_number), "decision_candidate")
    decisions_data = _load(root / "state" / "author_decisions.json", "author_decisions")
    handoff_data = _load(_handoff_path(root, chapter_number), "handoff")
    next_contract_data = _load(_contract_path(root, next_chapter), f"chapter_{next_chapter:04d}_contract")
    next_prompt_path = root / "prompts" / f"{chapter_id(next_chapter)}_writer_prompt.md"
    next_prompt_text = _read_text_safe(next_prompt_path)
    next_draft_text = _read_text_safe(_draft_path(root, next_chapter))
    foreshadowing_data = _load(root / "state" / "foreshadowing_ledger.json", "foreshadowing_ledger")
    next_review_path = _review_path(root, next_chapter)
    next_review_data = _load(next_review_path, f"chapter_{next_chapter:04d}_review")

    # --- Check 1: Evidence IDs from candidate → handoff ---
    if candidate_data and handoff_data:
        candidate_evidence: set[str] = set()
        for field_name in ("keep_evidence", "modification_evidence", "preference_evidence", "forbidden_evidence"):
            for eid in candidate_data.get(field_name, []):
                candidate_evidence.add(eid)
        handoff_evidence: set[str] = set()
        for field_name in ("hard_constraint_evidence", "author_direction_evidence"):
            for eid in handoff_data.get(field_name, []):
                handoff_evidence.add(eid)
        overlap = candidate_evidence & handoff_evidence
        if candidate_evidence:
            if overlap:
                checks.append(WorkflowEvaluationItem(
                    check_id="evidence_candidate_to_handoff",
                    name="证据从候选进入交接包",
                    status="pass",
                    detail=f"{len(overlap)} 条证据从候选传递到交接包",
                    evidence_refs=list(overlap),
                ))
            else:
                checks.append(WorkflowEvaluationItem(
                    check_id="evidence_candidate_to_handoff",
                    name="证据从候选进入交接包",
                    status="risk",
                    detail=f"候选有 {len(candidate_evidence)} 条证据但未进入交接包",
                    evidence_refs=list(candidate_evidence),
                ))
        else:
            checks.append(WorkflowEvaluationItem(
                check_id="evidence_candidate_to_handoff",
                name="证据从候选进入交接包",
                status="skip",
                detail="候选无证据引用",
            ))
    else:
        checks.append(WorkflowEvaluationItem(
            check_id="evidence_candidate_to_handoff",
            name="证据从候选进入交接包",
            status="skip",
            detail=f"缺少 {'候选' if not candidate_data else '交接包'}",
        ))

    # --- Check 2: Evidence IDs → next chapter contract ---
    if handoff_data and next_contract_data:
        handoff_ev: set[str] = set()
        for field_name in ("hard_constraint_evidence", "author_direction_evidence"):
            for eid in handoff_data.get(field_name, []):
                handoff_ev.add(eid)
        contract_text = json.dumps(next_contract_data, ensure_ascii=False)
        found_in_contract = [eid for eid in handoff_ev if eid in contract_text]
        if handoff_ev:
            if found_in_contract:
                checks.append(WorkflowEvaluationItem(
                    check_id="evidence_to_next_contract",
                    name="证据进入下一章合同",
                    status="pass",
                    detail=f"{len(found_in_contract)}/{len(handoff_ev)} 条证据进入合同",
                    evidence_refs=found_in_contract,
                ))
            else:
                checks.append(WorkflowEvaluationItem(
                    check_id="evidence_to_next_contract",
                    name="证据进入下一章合同",
                    status="risk",
                    detail=f"交接包有 {len(handoff_ev)} 条证据但合同未引用",
                    evidence_refs=list(handoff_ev),
                ))
        else:
            checks.append(WorkflowEvaluationItem(
                check_id="evidence_to_next_contract",
                name="证据进入下一章合同",
                status="skip",
                detail="交接包无证据引用",
            ))
    else:
        checks.append(WorkflowEvaluationItem(
            check_id="evidence_to_next_contract",
            name="证据进入下一章合同",
            status="skip",
            detail=f"缺少 {'交接包' if not handoff_data else '下一章合同'}",
        ))

    # --- Check 3: Author direction → next chapter contract ---
    if decisions_data and next_contract_data:
        author_prefs: list[str] = []
        for d in decisions_data.get("decisions", []):
            if d.get("chapter_number") == chapter_number:
                author_prefs = d.get("next_chapter_preferences", [])
                break
        if author_prefs:
            contract_text = json.dumps(next_contract_data, ensure_ascii=False)
            found = [p for p in author_prefs if p in contract_text]
            if found:
                checks.append(WorkflowEvaluationItem(
                    check_id="author_direction_to_contract",
                    name="作者确认方向进入下一章合同",
                    status="pass",
                    detail=f"{len(found)} 条作者方向进入合同",
                ))
            else:
                checks.append(WorkflowEvaluationItem(
                    check_id="author_direction_to_contract",
                    name="作者确认方向进入下一章合同",
                    status="risk",
                    detail="作者方向未在合同中找到",
                ))
        else:
            checks.append(WorkflowEvaluationItem(
                check_id="author_direction_to_contract",
                name="作者确认方向进入下一章合同",
                status="skip",
                detail="作者无下一章偏好",
            ))
    else:
        checks.append(WorkflowEvaluationItem(
            check_id="author_direction_to_contract",
            name="作者确认方向进入下一章合同",
            status="skip",
            detail=f"缺少 {'作者决策' if not decisions_data else '下一章合同'}",
        ))

    # --- Check 4: Author forbidden → review gate ---
    if decisions_data:
        author_forbidden: list[str] = []
        for d in decisions_data.get("decisions", []):
            if d.get("chapter_number") == chapter_number:
                author_forbidden = d.get("forbidden_directions", [])
                break
        if author_forbidden:
            if next_review_data:
                review_text = json.dumps(next_review_data, ensure_ascii=False)
                found_forbidden = [f for f in author_forbidden if f in review_text]
                if found_forbidden:
                    checks.append(WorkflowEvaluationItem(
                        check_id="author_forbidden_in_review",
                        name="作者禁区进入审稿门禁",
                        status="pass",
                        detail=f"审稿检测到 {len(found_forbidden)} 条作者禁区",
                    ))
                else:
                    # Not necessarily a failure — the draft might not have triggered it
                    checks.append(WorkflowEvaluationItem(
                        check_id="author_forbidden_in_review",
                        name="作者禁区进入审稿门禁",
                        status="pass",
                        detail="作者禁区已记录，审稿未检测到触犯（draft 未触发）",
                    ))
            else:
                checks.append(WorkflowEvaluationItem(
                    check_id="author_forbidden_in_review",
                    name="作者禁区进入审稿门禁",
                    status="skip",
                    detail="下一章审稿未执行",
                ))
        else:
            checks.append(WorkflowEvaluationItem(
                check_id="author_forbidden_in_review",
                name="作者禁区进入审稿门禁",
                status="skip",
                detail="作者无禁区",
            ))
    else:
        checks.append(WorkflowEvaluationItem(
            check_id="author_forbidden_in_review",
            name="作者禁区进入审稿门禁",
            status="skip",
            detail="缺少作者决策",
        ))

    # --- Check 5: Active foreshadowing → contract/prompt ---
    if foreshadowing_data and next_contract_data:
        active_items = [
            item for item in foreshadowing_data.get("items", [])
            if item.get("status", "active") == "active"
        ]
        if active_items:
            contract_text = json.dumps(next_contract_data, ensure_ascii=False)
            prompt_has = next_prompt_text is not None
            found_in_any = []
            for item in active_items:
                eid = item.get("id", "")
                content = item.get("content", "")
                if eid and eid in contract_text:
                    found_in_any.append(eid)
                elif content and content[:10] in contract_text:
                    found_in_any.append(eid or content[:20])
            if found_in_any:
                checks.append(WorkflowEvaluationItem(
                    check_id="foreshadowing_to_contract",
                    name="活跃伏笔进入下一章合同",
                    status="pass",
                    detail=f"{len(found_in_any)} 条伏笔在合同中引用",
                    evidence_refs=found_in_any,
                ))
            else:
                checks.append(WorkflowEvaluationItem(
                    check_id="foreshadowing_to_contract",
                    name="活跃伏笔进入下一章合同",
                    status="risk",
                    detail=f"{len(active_items)} 条活跃伏笔但合同未引用",
                ))
        else:
            checks.append(WorkflowEvaluationItem(
                check_id="foreshadowing_to_contract",
                name="活跃伏笔进入下一章合同",
                status="skip",
                detail="无活跃伏笔",
            ))
    else:
        checks.append(WorkflowEvaluationItem(
            check_id="foreshadowing_to_contract",
            name="活跃伏笔进入下一章合同",
            status="skip",
            detail=f"缺少 {'伏笔账本' if not foreshadowing_data else '下一章合同'}",
        ))

    # --- Check 6: Draft honors required payoff ---
    if next_contract_data and next_draft_text:
        payoffs = next_contract_data.get("required_payoffs", [])
        if payoffs:
            from .quality_gate import _contains
            hit = sum(1 for p in payoffs if _contains(next_draft_text, p))
            if hit == len(payoffs):
                checks.append(WorkflowEvaluationItem(
                    check_id="draft_payoff_coverage",
                    name="草稿兑现 required payoff",
                    status="pass",
                    detail=f"{hit}/{len(payoffs)} 条 payoff 兑现",
                ))
            elif hit > 0:
                checks.append(WorkflowEvaluationItem(
                    check_id="draft_payoff_coverage",
                    name="草稿兑现 required payoff",
                    status="risk",
                    detail=f"{hit}/{len(payoffs)} 条 payoff 兑现",
                ))
            else:
                checks.append(WorkflowEvaluationItem(
                    check_id="draft_payoff_coverage",
                    name="草稿兑现 required payoff",
                    status="fail",
                    detail=f"0/{len(payoffs)} 条 payoff 兑现",
                ))
        else:
            checks.append(WorkflowEvaluationItem(
                check_id="draft_payoff_coverage",
                name="草稿兑现 required payoff",
                status="skip",
                detail="合同无 required_payoffs",
            ))
    else:
        checks.append(WorkflowEvaluationItem(
            check_id="draft_payoff_coverage",
            name="草稿兑现 required payoff",
            status="skip",
            detail=f"缺少 {'合同' if not next_contract_data else '草稿'}",
        ))

    # --- Check 7: Draft violates author forbidden direction ---
    if decisions_data and next_draft_text:
        author_forbidden = []
        for d in decisions_data.get("decisions", []):
            if d.get("chapter_number") == chapter_number:
                author_forbidden = d.get("forbidden_directions", [])
                break
        if author_forbidden:
            from .quality_gate import _contains
            violations = [f for f in author_forbidden if _contains(next_draft_text, f)]
            if violations:
                checks.append(WorkflowEvaluationItem(
                    check_id="draft_forbidden_violation",
                    name="草稿是否触犯作者禁区",
                    status="fail",
                    detail=f"触犯 {len(violations)} 条禁区: {'; '.join(violations)}",
                    evidence_refs=violations,
                ))
            else:
                checks.append(WorkflowEvaluationItem(
                    check_id="draft_forbidden_violation",
                    name="草稿是否触犯作者禁区",
                    status="pass",
                    detail="草稿未触犯任何作者禁区",
                ))
        else:
            checks.append(WorkflowEvaluationItem(
                check_id="draft_forbidden_violation",
                name="草稿是否触犯作者禁区",
                status="skip",
                detail="作者无禁区",
            ))
    else:
        checks.append(WorkflowEvaluationItem(
            check_id="draft_forbidden_violation",
            name="草稿是否触犯作者禁区",
            status="skip",
            detail=f"缺少 {'作者决策' if not decisions_data else '草稿'}",
        ))

    # --- Check 8: Decision candidate exists (analysis bridge) ---
    if candidate_data:
        source_files = candidate_data.get("source_files", [])
        if source_files:
            checks.append(WorkflowEvaluationItem(
                check_id="candidate_has_sources",
                name="决策候选有分析来源",
                status="pass",
                detail=f"来源文件: {', '.join(source_files)}",
            ))
        else:
            checks.append(WorkflowEvaluationItem(
                check_id="candidate_has_sources",
                name="决策候选有分析来源",
                status="risk",
                detail="候选存在但无分析来源文件",
            ))
    else:
        checks.append(WorkflowEvaluationItem(
            check_id="candidate_has_sources",
            name="决策候选有分析来源",
            status="skip",
            detail="未运行 draft-author-note",
        ))

    # --- Check 9: Evidence coverage for author directions ---
    if decisions_data:
        decision_source = "analysis_derived"
        has_prefs = False
        has_evidence = False
        for d in decisions_data.get("decisions", []):
            if d.get("chapter_number") == chapter_number:
                decision_source = d.get("source", "analysis_derived")
                has_prefs = bool(d.get("next_chapter_preferences"))
                has_evidence = bool(d.get("evidence_refs"))
                break
        if has_prefs:
            if decision_source == "analysis_derived" and not has_evidence:
                checks.append(WorkflowEvaluationItem(
                    check_id="evidence_direction_coverage",
                    name="分析来源方向有证据支撑",
                    status="risk",
                    detail="来源为 analysis_derived 但 evidence_refs 为空",
                ))
            elif decision_source == "author_confirmed":
                checks.append(WorkflowEvaluationItem(
                    check_id="evidence_direction_coverage",
                    name="分析来源方向有证据支撑",
                    status="pass",
                    detail="来源为 author_confirmed，不要求证据",
                ))
            elif has_evidence:
                checks.append(WorkflowEvaluationItem(
                    check_id="evidence_direction_coverage",
                    name="分析来源方向有证据支撑",
                    status="pass",
                    detail="方向有证据支撑",
                ))
            else:
                checks.append(WorkflowEvaluationItem(
                    check_id="evidence_direction_coverage",
                    name="分析来源方向有证据支撑",
                    status="skip",
                    detail="无下一章偏好",
                ))
        else:
            checks.append(WorkflowEvaluationItem(
                check_id="evidence_direction_coverage",
                name="分析来源方向有证据支撑",
                status="skip",
                detail="无下一章偏好",
            ))
    else:
        checks.append(WorkflowEvaluationItem(
            check_id="evidence_direction_coverage",
            name="分析来源方向有证据支撑",
            status="skip",
            detail="缺少作者决策",
        ))

    # --- Check 10: Evidence contract alignment ---
    if handoff_data and next_contract_data:
        all_handoff_ev: set[str] = set()
        for field_name in ("hard_constraint_evidence", "author_direction_evidence"):
            for eid in handoff_data.get(field_name, []):
                all_handoff_ev.add(eid)
        if all_handoff_ev:
            contract_dump = json.dumps(next_contract_data, ensure_ascii=False)
            prompt_dump = next_prompt_text or ""
            combined = contract_dump + prompt_dump
            unreferenced = [eid for eid in all_handoff_ev if eid not in combined]
            if not unreferenced:
                checks.append(WorkflowEvaluationItem(
                    check_id="evidence_contract_alignment",
                    name="交接包证据在合同或 prompt 中引用",
                    status="pass",
                    detail=f"全部 {len(all_handoff_ev)} 条证据已引用",
                    evidence_refs=list(all_handoff_ev),
                ))
            else:
                checks.append(WorkflowEvaluationItem(
                    check_id="evidence_contract_alignment",
                    name="交接包证据在合同或 prompt 中引用",
                    status="risk",
                    detail=f"{len(unreferenced)}/{len(all_handoff_ev)} 条证据未引用",
                    evidence_refs=unreferenced,
                ))
        else:
            checks.append(WorkflowEvaluationItem(
                check_id="evidence_contract_alignment",
                name="交接包证据在合同或 prompt 中引用",
                status="skip",
                detail="交接包无证据",
            ))
    else:
        checks.append(WorkflowEvaluationItem(
            check_id="evidence_contract_alignment",
            name="交接包证据在合同或 prompt 中引用",
            status="skip",
            detail=f"缺少 {'交接包' if not handoff_data else '下一章合同'}",
        ))

    # --- Tally ---
    pass_count = sum(1 for c in checks if c.status == "pass")
    risk_count = sum(1 for c in checks if c.status == "risk")
    fail_count = sum(1 for c in checks if c.status == "fail")
    skip_count = sum(1 for c in checks if c.status == "skip")

    evaluation = WorkflowEvaluation(
        chapter_number=chapter_number,
        checks=checks,
        pass_count=pass_count,
        risk_count=risk_count,
        fail_count=fail_count,
        skip_count=skip_count,
        missing_files=missing,
    )

    # Write JSON
    json_path = write_json(_evaluation_json_path(root, chapter_number), evaluation)

    # Write MD
    md_lines = [
        f"# 第{chapter_number}章 作者记忆工作流评估",
        "",
        f"## 总览",
        "",
        f"- 通过：{pass_count}",
        f"- 风险：{risk_count}",
        f"- 失败：{fail_count}",
        f"- 跳过：{skip_count}",
        "",
    ]
    if missing:
        md_lines.extend(["## 缺失文件", ""])
        for m in missing:
            md_lines.append(f"- {m}")
        md_lines.append("")

    md_lines.extend(["## 检查明细", ""])
    for c in checks:
        icon = {"pass": "✓", "risk": "⚠", "fail": "✗", "skip": "○"}[c.status]
        md_lines.append(f"### {icon} {c.name}")
        md_lines.append("")
        md_lines.append(f"- 状态：{c.status}")
        md_lines.append(f"- 详情：{c.detail}")
        if c.evidence_refs:
            md_lines.append(f"- 证据：{', '.join(c.evidence_refs)}")
        md_lines.append("")

    if fail_count > 0:
        md_lines.extend(["## 结论", "", "**存在阻断项，请检查失败检查项。**"])
    elif risk_count > 0:
        md_lines.extend(["## 结论", "", "**存在风险项，建议检查。**"])
    else:
        md_lines.extend(["## 结论", "", "**所有检查通过或跳过。**"])

    md_path = write_text(_evaluation_md_path(root, chapter_number), "\n".join(md_lines))
    index_store.upsert_artifact(root, chapter_number, "workflow_evaluation", json_path)

    return evaluation


def compare_memory_variants(
    project_root: Path,
    *,
    chapter_number: int,
) -> dict[str, object]:
    """Compare what each memory variant (baseline/handoff/author_memory) brings to a chapter.

    Does NOT call LLM — only inspects files to enumerate constraints, evidence, and foreshadowing
    that each variant would include.
    """
    root = ensure_project(project_root)
    next_chapter = chapter_number + 1
    missing: list[str] = []

    def _load_json(path: Path, label: str):
        if not path.exists():
            missing.append(label)
            return None
        try:
            return read_json(path)
        except (ValueError, KeyError):
            missing.append(f"{label} (invalid)")
            return None

    contract_data = _load_json(_contract_path(root, next_chapter), f"chapter_{next_chapter:04d}_contract")
    handoff_data = _load_json(_handoff_path(root, chapter_number), "handoff")
    decisions_data = _load_json(root / "state" / "author_decisions.json", "author_decisions")
    foreshadowing_data = _load_json(root / "state" / "foreshadowing_ledger.json", "foreshadowing_ledger")
    candidate_data = _load_json(_candidate_json_path(root, chapter_number), "decision_candidate")

    # --- Variant A: baseline (contract only) ---
    baseline_constraints: list[str] = []
    baseline_evidence: list[str] = []
    baseline_forbidden: list[str] = []
    baseline_payoffs: list[str] = []
    baseline_foreshadowing: list[str] = []

    if contract_data:
        baseline_constraints = contract_data.get("forbidden_beats", [])
        baseline_payoffs = contract_data.get("required_payoffs", [])
        baseline_foreshadowing = contract_data.get("foreshadowing_ops", [])

    # --- Variant B: + handoff ---
    handoff_constraints: list[str] = []
    handoff_evidence: list[str] = []
    handoff_direction: str = ""
    handoff_payoffs: list[str] = []
    handoff_foreshadowing: list[str] = []

    if handoff_data:
        handoff_constraints = handoff_data.get("hard_constraints", [])
        handoff_evidence = list(handoff_data.get("hard_constraint_evidence", []))
        handoff_evidence.extend(handoff_data.get("author_direction_evidence", []))
        handoff_direction = handoff_data.get("author_direction", "")
        handoff_payoffs = handoff_data.get("required_payoffs_next", [])
        handoff_foreshadowing = handoff_data.get("active_foreshadowing", [])

    # --- Variant C: + author decisions ---
    author_constraints: list[str] = []
    author_evidence: list[str] = []
    author_prefs: list[str] = []
    author_forbidden: list[str] = []

    if decisions_data:
        for d in decisions_data.get("decisions", []):
            if d.get("chapter_number") == chapter_number:
                author_forbidden = d.get("forbidden_directions", [])
                author_prefs = d.get("next_chapter_preferences", [])
                author_evidence = d.get("evidence_refs", [])
                author_constraints = author_forbidden
                break

    # --- Variant D: + foreshadowing ---
    foreshadowing_active: list[dict[str, object]] = []
    if foreshadowing_data:
        foreshadowing_active = [
            item for item in foreshadowing_data.get("items", [])
            if item.get("status", "active") == "active"
        ]

    # Build comparison report
    variants = []

    # A
    variants.append({
        "variant": "A",
        "name": "baseline（仅合同）",
        "constraints": list(baseline_constraints),
        "evidence": list(baseline_evidence),
        "forbidden": list(baseline_forbidden),
        "payoffs": list(baseline_payoffs),
        "foreshadowing": list(baseline_foreshadowing),
        "direction": "",
    })

    # B
    variants.append({
        "variant": "B",
        "name": "handoff（合同 + 交接包）",
        "constraints": list(set(baseline_constraints + handoff_constraints)),
        "evidence": list(set(handoff_evidence)),
        "forbidden": list(set(baseline_constraints + handoff_constraints)),
        "payoffs": list(set(baseline_payoffs + handoff_payoffs)),
        "foreshadowing": list(set(baseline_foreshadowing + handoff_foreshadowing)),
        "direction": handoff_direction,
    })

    # C
    variants.append({
        "variant": "C",
        "name": "author_memory（合同 + 交接 + 作者决策）",
        "constraints": list(set(baseline_constraints + handoff_constraints + author_constraints)),
        "evidence": list(set(handoff_evidence + author_evidence)),
        "forbidden": list(set(baseline_constraints + handoff_constraints + author_forbidden)),
        "payoffs": list(set(baseline_payoffs + handoff_payoffs)),
        "foreshadowing": list(set(baseline_foreshadowing + handoff_foreshadowing)),
        "direction": handoff_direction or "；".join(author_prefs),
    })

    # D (full)
    foreshadowing_ids = [
        item.get("id", f"FS-{item.get('planted_chapter', '?')}")
        for item in foreshadowing_active
    ]
    variants.append({
        "variant": "D",
        "name": "full（合同 + 交接 + 作者决策 + 伏笔账本）",
        "constraints": list(set(baseline_constraints + handoff_constraints + author_constraints)),
        "evidence": list(set(handoff_evidence + author_evidence)),
        "forbidden": list(set(baseline_constraints + handoff_constraints + author_forbidden)),
        "payoffs": list(set(baseline_payoffs + handoff_payoffs)),
        "foreshadowing": foreshadowing_ids,
        "direction": handoff_direction or "；".join(author_prefs),
    })

    result = {
        "chapter_number": chapter_number,
        "variants": variants,
        "missing_files": missing,
    }

    # Write JSON
    experiments_dir = root / "experiments"
    experiments_dir.mkdir(parents=True, exist_ok=True)
    json_path = experiments_dir / f"memory_variant_comparison_{chapter_id(chapter_number)}.json"
    write_json(json_path, result)

    # Write MD
    md_lines = [
        f"# 第{chapter_number}章 记忆变体比较",
        "",
    ]
    if missing:
        md_lines.extend(["## 缺失文件", ""])
        for m in missing:
            md_lines.append(f"- {m}")
        md_lines.append("")

    for v in variants:
        md_lines.extend([
            f"## 变体 {v['variant']}：{v['name']}",
            "",
            f"- 约束数：{len(v['constraints'])}",
            f"- 证据数：{len(v['evidence'])}",
            f"- 禁区数：{len(v['forbidden'])}",
            f"- Payoff 数：{len(v['payoffs'])}",
            f"- 伏笔数：{len(v['foreshadowing'])}",
            f"- 方向：{v['direction'] or '无'}",
            "",
        ])
        if v['constraints']:
            md_lines.append("### 约束")
            for c in v['constraints']:
                md_lines.append(f"- {c}")
            md_lines.append("")
        if v['evidence']:
            md_lines.append("### 证据")
            for e in v['evidence']:
                md_lines.append(f"- {e}")
            md_lines.append("")
        if v['forbidden']:
            md_lines.append("### 禁区")
            for f in v['forbidden']:
                md_lines.append(f"- {f}")
            md_lines.append("")
        if v['foreshadowing']:
            md_lines.append("### 伏笔")
            for fs in v['foreshadowing']:
                md_lines.append(f"- {fs}")
            md_lines.append("")

    # Delta summary
    md_lines.extend(["## 增量分析", ""])
    a_constraints = set(variants[0]["constraints"])
    d_constraints = set(variants[3]["constraints"])
    extra = d_constraints - a_constraints
    if extra:
        md_lines.append(f"### 从 A 到 D 新增的约束（{len(extra)} 条）")
        for e in extra:
            md_lines.append(f"- {e}")
        md_lines.append("")

    a_ev = set(variants[0]["evidence"])
    d_ev = set(variants[3]["evidence"])
    extra_ev = d_ev - a_ev
    if extra_ev:
        md_lines.append(f"### 从 A 到 D 新增的证据（{len(extra_ev)} 条）")
        for e in extra_ev:
            md_lines.append(f"- {e}")
        md_lines.append("")

    a_fs = set(variants[0]["foreshadowing"])
    d_fs = set(variants[3]["foreshadowing"])
    extra_fs = d_fs - a_fs
    if extra_fs:
        md_lines.append(f"### 从 A 到 D 新增的伏笔（{len(extra_fs)} 条）")
        for e in extra_fs:
            md_lines.append(f"- {e}")
        md_lines.append("")

    md_path = experiments_dir / f"memory_variant_comparison_{chapter_id(chapter_number)}.md"
    write_text(md_path, "\n".join(md_lines))

    result["json_path"] = str(json_path)
    result["md_path"] = str(md_path)
    return result

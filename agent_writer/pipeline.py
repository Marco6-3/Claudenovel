from __future__ import annotations

from pathlib import Path

from .models import (
    AuthorDecision,
    AuthorStrategy,
    ChapterCommit,
    ChapterContract,
    ChapterHandoff,
    CharacterConstraint,
    CharacterConstraints,
    ForeshadowingItem,
    FutureDirection,
    PrewritePlan,
    ReaderExpectationMap,
    ReviewResult,
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
    ]
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
    if author_decision and author_decision.forbidden_directions:
        hard_constraints.extend(author_decision.forbidden_directions)

    # Author direction
    author_direction = ""
    if author_decision and author_decision.next_chapter_preferences:
        author_direction = "；".join(author_decision.next_chapter_preferences)

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
        author_direction=author_direction,
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
    if author_decision and author_decision.next_chapter_preferences:
        # Add author preferences to foreshadowing_ops
        contract.foreshadowing_ops = [
            f"作者偏好：{'；'.join(author_decision.next_chapter_preferences)}",
            *contract.foreshadowing_ops,
        ]
    write_json(_contract_path(root, chapter_number), contract)
    result["handoff_loaded"] = str(handoff_path) if handoff else "none"
    return result

from __future__ import annotations

from pathlib import Path

from .models import (
    AuthorStrategy,
    ChapterCommit,
    ChapterContract,
    CharacterConstraint,
    CharacterConstraints,
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
    issues = evaluate_draft(read_text(draft_path), contract, constraints)
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

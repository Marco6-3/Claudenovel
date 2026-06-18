from __future__ import annotations

import json
from pathlib import Path

from .models import (
    AuthorDecision,
    AuthorStrategy,
    ChapterCommit,
    ChapterContract,
    ChapterHandoff,
    ChapterOutlineItem,
    CharacterConstraint,
    CharacterConstraints,
    DecisionCandidate,
    ForeshadowingCandidate,
    ForeshadowingItem,
    FutureDirection,
    OutlineRevision,
    PrewritePlan,
    ReaderExpectationMap,
    ReviewResult,
    StoryOutline,
    utc_now_iso,
    VolumeOutline,
    WorkflowEvaluation,
    WorkflowEvaluationItem,
)
from . import index_store
from .llm_client import build_client
from .paths import (
    accepted_path as _accepted_path,
    candidate_json_path as _candidate_json_path,
    candidate_md_path as _candidate_md_path,
    commit_path as _commit_path,
    constraints_path as _constraints_path,
    contract_path as _contract_path,
    discussion_path as _discussion_path,
    draft_path as _draft_path,
    evaluation_json_path as _evaluation_json_path,
    evaluation_md_path as _evaluation_md_path,
    expectation_path as _expectation_path,
    handoff_md_path as _handoff_md_path,
    handoff_path as _handoff_path,
    outline_md_path as _outline_md_path,
    outline_path as _outline_path,
    outline_revisions_path as _outline_revisions_path,
    prewrite_path as _prewrite_path,
    review_path as _review_path,
    strategy_path as _strategy_path,
)
from .quality_gate import evaluate_draft
from .rules import render_rules_for_prompt
from .storage import chapter_id, copy_utf8, ensure_project, read_json, read_model, read_text, write_json, write_text


def _render_story_outline_md(outline: StoryOutline) -> str:
    lines = [
        "# 故事大纲",
        "",
        f"- 项目名：{outline.project_name}",
        f"- 题材：{outline.genre}",
        f"- 目标读者：{outline.target_reader}",
        f"- 一句话故事：{outline.logline}",
    ]
    if outline.theme:
        lines.append(f"- 主题：{outline.theme}")
    lines.extend(["", "## 全局规则", ""])
    if outline.global_rules:
        lines.extend(f"- {rule}" for rule in outline.global_rules)
    else:
        lines.append("- 暂无")
    lines.extend(["", "## 主要角色", ""])
    if outline.major_characters:
        lines.extend(f"- {name}" for name in outline.major_characters)
    else:
        lines.append("- 暂无")

    for volume in outline.volumes:
        lines.extend(
            [
                "",
                f"## 第{volume.volume_number}卷：{volume.title}",
                "",
                f"- 章节范围：第{volume.chapter_start}-{volume.chapter_end}章",
                f"- 核心冲突：{volume.core_conflict}",
                f"- 卷末高潮：{volume.climax}",
                "",
                "### 时间线",
                "",
            ]
        )
        lines.extend(f"- {item}" for item in volume.timeline) if volume.timeline else lines.append("- 暂无")
        lines.extend(["", "### 伏笔规划", ""])
        lines.extend(f"- {item}" for item in volume.foreshadowing_plan) if volume.foreshadowing_plan else lines.append("- 暂无")
        lines.extend(["", "### 章纲", ""])
        for chapter in volume.chapters:
            lines.extend(
                [
                    f"#### 第{chapter.chapter_number}章：{chapter.title}",
                    "",
                    f"- 目标：{chapter.goal}",
                    f"- 冲突：{chapter.conflict or volume.core_conflict}",
                    f"- 时间锚点：{chapter.time_anchor or '待定'}",
                    f"- 必须兑现：{', '.join(chapter.required_payoffs)}",
                    f"- 必须包含：{', '.join(chapter.must_include) if chapter.must_include else '无'}",
                    f"- 禁止：{', '.join(chapter.forbidden_beats) if chapter.forbidden_beats else '无'}",
                    f"- 角色：{', '.join(chapter.characters) if chapter.characters else '待定'}",
                    f"- 尾钩：{chapter.ending_hook}",
                    "",
                ]
            )
            if chapter.scene_beats:
                lines.extend(["场景节点：", ""])
                lines.extend(f"- {beat}" for beat in chapter.scene_beats)
                lines.append("")
    lines.extend(["---", "", f"更新时间：{outline.updated_at}", ""])
    return "\n".join(lines)


def _default_chapter_outlines(
    *,
    chapter_start: int,
    chapter_end: int,
    core_conflict: str,
    climax: str,
    major_characters: list[str],
) -> list[ChapterOutlineItem]:
    chapters: list[ChapterOutlineItem] = []
    total = max(1, chapter_end - chapter_start + 1)
    for index, chapter_number in enumerate(range(chapter_start, chapter_end + 1), start=1):
        if index == 1:
            role = "开局建立冲突"
        elif index == total:
            role = "推向卷末高潮"
        elif index >= max(2, total - 1):
            role = "危机升级并回收关键伏笔"
        else:
            role = "推进调查/冲突并制造新问题"
        chapters.append(
            ChapterOutlineItem(
                chapter_number=chapter_number,
                title=f"第{chapter_number}章待定",
                goal=f"{role}：{core_conflict}",
                required_payoffs=[role],
                conflict=core_conflict,
                time_anchor=f"第{index}个剧情节拍",
                scene_beats=[
                    "承接上一章问题",
                    "遭遇明确阻力",
                    "用行动换取信息或代价",
                    "兑现本章收益",
                ],
                must_include=[core_conflict],
                forbidden_beats=["不得偏离已确认设定", "不得跳过因果直接给结论"],
                ending_hook=climax if index == total else "留下一个迫使读者进入下一章的问题",
                characters=major_characters,
            )
        )
    return chapters


def _find_chapter_outline(outline: StoryOutline, chapter_number: int) -> ChapterOutlineItem | None:
    for volume in outline.volumes:
        for chapter in volume.chapters:
            if chapter.chapter_number == chapter_number:
                return chapter
    return None


def _find_volume_for_chapter(outline: StoryOutline, chapter_number: int) -> VolumeOutline | None:
    for volume in outline.volumes:
        if volume.chapter_start <= chapter_number <= volume.chapter_end:
            return volume
    return None


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
    outline = StoryOutline(
        project_name=name,
        genre=genre,
        target_reader=target_reader,
        logline=premise,
        theme="待作者确认",
        global_rules=[
            "全书设定变更必须经过 outline-revise 或 author decision 确认。",
            "章节合同必须优先服从 story_outline 中的章纲目标、禁区和尾钩。",
        ],
        major_characters=[],
        volumes=[],
    )
    paths["story_outline"] = str(write_json(_outline_path(root), outline))
    paths["story_outline_md"] = str(write_text(_outline_md_path(root), _render_story_outline_md(outline)))

    for state_file, payload in {
        "characters.json": {"characters": []},
        "relationship_state.json": {"relationships": [], "history": []},
        "foreshadowing_ledger.json": {"items": []},
        "system_rule_ledger.json": {"rules": [], "changes": []},
        "chapter_summaries.json": {"chapters": []},
        "author_decisions.json": {"decisions": []},
        "future_direction_ledger.json": {"directions": []},
        "outline_revisions.json": {"revisions": []},
    }.items():
        paths[state_file] = str(write_json(root / "state" / state_file, payload))
    index_store.connect(root).close()
    return paths


def create_story_outline(
    project_root: Path,
    *,
    logline: str,
    theme: str = "",
    volume_title: str,
    chapter_start: int,
    chapter_end: int,
    core_conflict: str,
    climax: str,
    major_characters: list[str] | None = None,
    global_rules: list[str] | None = None,
) -> dict[str, str]:
    root = ensure_project(project_root)
    strategy = read_model(_strategy_path(root), AuthorStrategy)
    characters = list(major_characters or [])
    rules = list(global_rules or [])
    outline = StoryOutline(
        project_name=strategy.project_name,
        genre=strategy.genre,
        target_reader=strategy.target_reader,
        logline=logline,
        theme=theme,
        global_rules=[
            "章节创作必须从本大纲、作者设定、作者修订记录和已接受章节中取材。",
            "任何临时改动必须先写入 outline-revise 或章节作者决策。",
            *rules,
        ],
        major_characters=characters,
        volumes=[
            VolumeOutline(
                volume_number=1,
                title=volume_title,
                chapter_start=chapter_start,
                chapter_end=chapter_end,
                core_conflict=core_conflict,
                climax=climax,
                timeline=[f"第{chapter_start}-{chapter_end}章：围绕「{core_conflict}」逐步升级"],
                foreshadowing_plan=[f"卷末必须把冲突推向「{climax}」"],
                chapters=_default_chapter_outlines(
                    chapter_start=chapter_start,
                    chapter_end=chapter_end,
                    core_conflict=core_conflict,
                    climax=climax,
                    major_characters=characters,
                ),
            )
        ],
    )
    outline_json = write_json(_outline_path(root), outline)
    outline_md = write_text(_outline_md_path(root), _render_story_outline_md(outline))

    author_bible_path = root / "story_bible" / "author_bible.md"
    author_bible = read_text(author_bible_path) if author_bible_path.exists() else ""
    addition = (
        "\n## 故事大纲入口\n\n"
        f"- 一句话故事：{logline}\n"
        f"- 主题：{theme or '待作者确认'}\n"
        f"- 第一卷：{volume_title}\n"
        f"- 第一卷核心冲突：{core_conflict}\n"
        f"- 第一卷高潮：{climax}\n"
    )
    if "## 故事大纲入口" not in author_bible:
        write_text(author_bible_path, author_bible.rstrip() + "\n" + addition)
    return {"story_outline": str(outline_json), "story_outline_md": str(outline_md)}


def revise_story_outline(
    project_root: Path,
    *,
    revision_file: Path,
) -> dict[str, object]:
    root = ensure_project(project_root)
    outline = read_model(_outline_path(root), StoryOutline)
    revision = read_model(revision_file, OutlineRevision)

    if revision.global_rules:
        existing = set(outline.global_rules)
        outline.global_rules.extend(rule for rule in revision.global_rules if rule not in existing)
    if revision.forbidden_directions:
        existing = set(outline.global_rules)
        for direction in revision.forbidden_directions:
            rule = f"禁止方向：{direction}"
            if rule not in existing:
                outline.global_rules.append(rule)
                existing.add(rule)
    if revision.major_characters:
        existing_chars = set(outline.major_characters)
        outline.major_characters.extend(name for name in revision.major_characters if name not in existing_chars)

    updated_chapters: list[int] = []
    for update in revision.chapter_updates:
        replaced = False
        for volume in outline.volumes:
            for index, chapter in enumerate(volume.chapters):
                if chapter.chapter_number == update.chapter_number:
                    volume.chapters[index] = update.model_copy(update={"status": "revised"})
                    replaced = True
                    updated_chapters.append(update.chapter_number)
                    break
            if replaced:
                break
        if not replaced:
            target_volume = _find_volume_for_chapter(outline, update.chapter_number)
            if target_volume is None:
                if not outline.volumes:
                    raise ValueError("cannot add chapter update: story outline has no volume")
                target_volume = outline.volumes[-1]
            target_volume.chapters.append(update.model_copy(update={"status": "revised"}))
            target_volume.chapters.sort(key=lambda item: item.chapter_number)
            updated_chapters.append(update.chapter_number)

    outline.updated_at = revision.created_at
    outline_json = write_json(_outline_path(root), outline)
    outline_md = write_text(_outline_md_path(root), _render_story_outline_md(outline))

    revisions_path = _outline_revisions_path(root)
    revisions_data = read_json(revisions_path) if revisions_path.exists() else {"revisions": []}
    revisions = list(revisions_data.get("revisions", []))
    revision_id = revision.revision_id or f"OR-{len(revisions) + 1:04d}"
    revisions.append(revision.model_copy(update={"revision_id": revision_id}).model_dump(mode="json"))
    write_json(revisions_path, {"revisions": revisions})

    author_bible_path = root / "story_bible" / "author_bible.md"
    author_bible = read_text(author_bible_path) if author_bible_path.exists() else ""
    revision_note = (
        f"\n## 大纲修订 {revision_id}\n\n"
        f"- 原因：{revision.reason or '作者确认'}\n"
        f"- 全局规则：{'; '.join(revision.global_rules) if revision.global_rules else '无'}\n"
        f"- 禁止方向：{'; '.join(revision.forbidden_directions) if revision.forbidden_directions else '无'}\n"
        f"- 更新章节：{', '.join(str(ch) for ch in updated_chapters) if updated_chapters else '无'}\n"
        f"- 备注：{revision.notes or '无'}\n"
    )
    write_text(author_bible_path, author_bible.rstrip() + "\n" + revision_note)
    return {
        "story_outline": str(outline_json),
        "story_outline_md": str(outline_md),
        "revision_id": revision_id,
        "updated_chapters": updated_chapters,
    }


def plan_chapter_from_outline(
    project_root: Path,
    *,
    chapter_number: int,
) -> dict[str, str]:
    root = ensure_project(project_root)
    outline = read_model(_outline_path(root), StoryOutline)
    chapter = _find_chapter_outline(outline, chapter_number)
    if chapter is None:
        raise ValueError(f"chapter {chapter_number} is not present in story_outline.json")

    result = plan_chapter(
        root,
        chapter_number=chapter.chapter_number,
        title=chapter.title,
        goal=chapter.goal,
        required_payoffs=chapter.required_payoffs,
        ending_hook=chapter.ending_hook,
        forbidden_beats=chapter.forbidden_beats
        + [rule.removeprefix("禁止方向：") for rule in outline.global_rules if rule.startswith("禁止方向：")],
        characters=chapter.characters,
    )

    contract = read_model(_contract_path(root, chapter_number), ChapterContract)
    contract.allowed_sources = sorted(set(contract.allowed_sources + ["story_outline", "outline_revisions"]))
    contract.foreshadowing_ops = list(dict.fromkeys(contract.foreshadowing_ops + chapter.must_include))
    contract.cool_point = chapter.required_payoffs[0]
    write_json(_contract_path(root, chapter_number), contract)
    index_store.save_contract(root, contract, _contract_path(root, chapter_number))

    prewrite = read_model(_prewrite_path(root, chapter_number), PrewritePlan)
    scene_order = chapter.scene_beats or prewrite.scene_order
    prewrite = prewrite.model_copy(
        update={
            "main_conflict": chapter.conflict or prewrite.main_conflict,
            "scene_order": scene_order,
            "must_include": list(dict.fromkeys(prewrite.must_include + chapter.must_include)),
            "must_avoid": list(dict.fromkeys(prewrite.must_avoid + chapter.forbidden_beats)),
        }
    )
    write_json(_prewrite_path(root, chapter_number), prewrite)
    index_store.upsert_artifact(root, chapter_number, "prewrite_plan", _prewrite_path(root, chapter_number))

    chapter.status = "contracted"
    outline.updated_at = utc_now_iso()
    write_json(_outline_path(root), outline)
    write_text(_outline_md_path(root), _render_story_outline_md(outline))
    result["story_outline"] = str(_outline_path(root))
    return result


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


def _load_outline_context(root: Path, chapter_number: int) -> str:
    outline_path = _outline_path(root)
    if not outline_path.exists():
        return ""
    outline = read_model(outline_path, StoryOutline)
    chapter = _find_chapter_outline(outline, chapter_number)
    volume = _find_volume_for_chapter(outline, chapter_number)
    lines = [
        "### 全书大纲",
        "",
        f"- 一句话故事：{outline.logline}",
        f"- 主题：{outline.theme or '未指定'}",
    ]
    if outline.global_rules:
        lines.append(f"- 全局规则：{'; '.join(outline.global_rules)}")
    if outline.major_characters:
        lines.append(f"- 主要角色：{', '.join(outline.major_characters)}")
    if volume:
        lines.extend(
            [
                "",
                f"### 当前卷：第{volume.volume_number}卷《{volume.title}》",
                "",
                f"- 核心冲突：{volume.core_conflict}",
                f"- 卷末高潮：{volume.climax}",
            ]
        )
        if volume.foreshadowing_plan:
            lines.append(f"- 伏笔规划：{'; '.join(volume.foreshadowing_plan)}")
    if chapter:
        lines.extend(
            [
                "",
                f"### 当前章纲：第{chapter.chapter_number}章《{chapter.title}》",
                "",
                f"- 目标：{chapter.goal}",
                f"- 冲突：{chapter.conflict or (volume.core_conflict if volume else '未指定')}",
                f"- 时间锚点：{chapter.time_anchor or '未指定'}",
                f"- 必须兑现：{', '.join(chapter.required_payoffs)}",
                f"- 必须包含：{', '.join(chapter.must_include) if chapter.must_include else '无'}",
                f"- 禁止：{', '.join(chapter.forbidden_beats) if chapter.forbidden_beats else '无'}",
                f"- 尾钩：{chapter.ending_hook}",
            ]
        )
        if chapter.scene_beats:
            lines.extend(["", "场景节点："])
            lines.extend(f"- {beat}" for beat in chapter.scene_beats)
    return "\n".join(lines)


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
    outline_context = _load_outline_context(root, chapter_number)

    prompt = (
        f"# {contract.title} 写作任务书\n\n"
        "## 作者设定\n\n"
        f"{strategy}\n\n"
    )

    if outline_context:
        prompt += "## 故事大纲与作者修订\n\n" + outline_context + "\n\n"

    prompt += (
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
    outline_path = _outline_path(root)
    outline_chapters = 0
    outline_volumes = 0
    if outline_path.exists():
        outline = read_model(outline_path, StoryOutline)
        outline_volumes = len(outline.volumes)
        outline_chapters = sum(len(volume.chapters) for volume in outline.volumes)
    return {
        "project_root": str(root),
        "contracts": len(contracts),
        "drafts": len(drafts),
        "reviews": len(reviews),
        "accepted": len(accepted),
        "outline_volumes": outline_volumes,
        "outline_chapters": outline_chapters,
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
    """Generate an author discussion packet for a committed chapter.

    Enhanced v2: structured like a usable writing meeting checklist with
    embedded evidence IDs, foreshadowing tables, and a pre-filled JSON template.
    """
    root = ensure_project(project_root)
    contract = read_model(_contract_path(root, chapter_number), ChapterContract)
    review_path = _review_path(root, chapter_number)
    review = read_model(review_path, ReviewResult) if review_path.exists() else None
    draft = read_text(_draft_path(root, chapter_number))

    # Load foreshadowing
    foreshadowing_path = root / "state" / "foreshadowing_ledger.json"
    active_foreshadowing: list[dict[str, object]] = []
    resolved_foreshadowing: list[dict[str, object]] = []
    if foreshadowing_path.exists():
        foreshadowing = read_json(foreshadowing_path)
        for item in foreshadowing.get("items", []):
            status = item.get("status", "active")
            if status == "active":
                active_foreshadowing.append(item)
            elif status == "resolved":
                resolved_foreshadowing.append(item)

    # Check for decision candidate
    candidate_path = _candidate_json_path(root, chapter_number)
    candidate = None
    if candidate_path.exists():
        try:
            candidate = read_model(candidate_path, DecisionCandidate)
        except (ValueError, KeyError):
            candidate = None

    # Draft summary (first 300 chars)
    draft_summary = draft[:300].replace("\n", " ").strip()
    if len(draft) > 300:
        draft_summary += "…"

    lines = [
        f"# 第{chapter_number}章 作者协商包",
        "",
        "---",
        "",
        "## 一、本章总结",
        "",
        f"- **标题**：{contract.title}",
        f"- **目标**：{contract.main_goal}",
        f"- **必须兑现**：{', '.join(contract.required_payoffs)}",
        f"- **尾钩**：{contract.ending_hook}",
        f"- **草稿摘要**：{draft_summary}",
        "",
    ]

    # --- Decision candidate section (if available) ---
    if candidate:
        source_label = ', '.join(candidate.source_files) if candidate.source_files else "无"
        lines.extend([
            "## 二、分析系统决策候选",
            "",
            f"> 来源：{source_label}",
            f"> 保留理由：{candidate.keep_reason}",
            "",
        ])
        # Keep evidence
        if candidate.keep_evidence:
            lines.append(f"> 保留证据：{', '.join(candidate.keep_evidence)}")
            lines.append("")

        # Modifications with evidence
        if candidate.modifications:
            lines.append("### 候选修改项")
            lines.append("")
            for i, mod in enumerate(candidate.modifications):
                ev = candidate.modification_evidence[i] if i < len(candidate.modification_evidence) else ""
                ev_str = f" `{ev}`" if ev else ""
                lines.append(f"- [ ] **修改 {i+1}**：{mod}{ev_str}")
            lines.append("")

        # Next chapter directions
        if candidate.next_chapter_preferences:
            lines.append("### 候选下一章方向")
            lines.append("")
            for i, pref in enumerate(candidate.next_chapter_preferences):
                ev = candidate.preference_evidence[i] if i < len(candidate.preference_evidence) else ""
                ev_str = f" `{ev}`" if ev else ""
                label = chr(65 + i)  # A, B, C...
                lines.append(f"- [ ] **方向 {label}**：{pref}{ev_str}")
            lines.append("")

        # Forbidden from candidate
        if candidate.forbidden_directions:
            lines.append("### 候选禁区")
            lines.append("")
            for fd in candidate.forbidden_directions:
                lines.append(f"- [ ] {fd}")
            lines.append("")

    # --- Review issues ---
    lines.extend([
        "## 三、审稿结果",
        "",
    ])
    if review and review.issues:
        for issue in review.issues:
            lines.append(f"- **[{issue.severity}]** {issue.code}：{issue.message}")
            if issue.repair_hint:
                lines.append(f"  - 修复建议：{issue.repair_hint}")
    else:
        lines.append("- 审稿通过，无阻断项。")
    lines.append("")

    # --- Next chapter directions ---
    lines.extend([
        "## 四、下一章方向（请选择或自定义）",
        "",
    ])
    if candidate and candidate.next_chapter_preferences:
        for i, pref in enumerate(candidate.next_chapter_preferences):
            label = chr(65 + i)
            ev = candidate.preference_evidence[i] if i < len(candidate.preference_evidence) else ""
            ev_str = f"（证据：{ev}）" if ev else ""
            lines.append(f"### 方向 {label}（来自分析）")
            lines.append(f"- {pref}{ev_str}")
            lines.append("")
    else:
        lines.extend([
            "### 方向 A：延续当前冲突",
            f"- 从本章尾钩「{contract.ending_hook}」直接展开",
            "",
            "### 方向 B：转换视角/场景",
            "- 切换到另一条故事线",
            "",
            "### 方向 C：深化角色关系",
            "- 用本章事件的后果推动角色互动",
            "",
        ])

    # --- Foreshadowing tables ---
    lines.extend([
        "## 五、伏笔管理",
        "",
        "### 活跃伏笔",
        "",
    ])
    if active_foreshadowing:
        lines.append("| ID | 内容 | 埋设章节 | 层级 | 操作建议 |")
        lines.append("|-----|------|----------|------|----------|")
        for item in active_foreshadowing:
            eid = item.get("id", f"FS-{item.get('planted_chapter', '?')}")
            content = item.get("content", "")
            planted = item.get("planted_chapter", "?")
            layer = item.get("layer", "支线")
            lines.append(f"| {eid} | {content} | 第{planted}章 | {layer} | 继续/回收 |")
        lines.append("")
    else:
        lines.append("- 暂无活跃伏笔。")
        lines.append("")

    # Recyclable foreshadowing (resolved, potentially useful)
    lines.append("### 已回收伏笔（可参考）")
    lines.append("")
    if resolved_foreshadowing:
        for item in resolved_foreshadowing[-5:]:  # Last 5
            eid = item.get("id", "")
            content = item.get("content", "")
            resolved_at = item.get("resolution_chapter", "?")
            lines.append(f"- [{eid}] {content}（回收于第{resolved_at}章）")
        lines.append("")
    else:
        lines.append("- 暂无已回收伏笔。")
        lines.append("")

    # --- Confirmation checklist ---
    lines.extend([
        "## 六、需要作者确认的问题",
        "",
        "请逐项确认或填写：",
        "",
        "### 本章评价",
        "",
        "- [ ] 本章保留（keep_chapter = true/false）",
        "- [ ] 保留理由：______",
        "",
        "### 修改要求",
        "",
        "- [ ] 有无需要修改的问题？（如有，请列出）",
        "",
        "### 下一章方向",
        "",
        "- [ ] 选择哪个方向？（A/B/C 或自定义）",
        "- [ ] 自定义方向（如不选以上）：______",
        "",
        "### 禁区",
        "",
        "- [ ] 下一章绝对不能出现的走向：______",
        "",
        "### 关系变化",
        "",
        "- [ ] 本章是否产生了关系变化？______",
        "- [ ] 变化的证据/共同经历：______",
        "",
        "### 伏笔操作",
        "",
        "- [ ] 是否推进了已有伏笔？",
        "- [ ] 是否新增了伏笔？",
        "- [ ] 是否回收了某个伏笔？",
        "",
        "### 下一章 Payoff",
        "",
        "- [ ] 下一章必须兑现的读者收益：______",
        "",
    ])

    # --- Pre-filled JSON template ---
    # Build template from candidate or defaults
    template_prefs = []
    template_forbidden = []
    template_mods = []
    template_evidence = []
    if candidate:
        template_prefs = candidate.next_chapter_preferences[:2]
        template_forbidden = candidate.forbidden_directions[:2]
        template_mods = candidate.modifications[:1]
        template_evidence = candidate.keep_evidence[:3]

    template: dict[str, object] = {
        "chapter_number": chapter_number,
        "keep_chapter": True,
        "keep_reason": candidate.keep_reason if candidate else "待填写",
        "modifications": template_mods if template_mods else ["待填写或留空"],
        "next_chapter_preferences": template_prefs if template_prefs else ["待填写"],
        "forbidden_directions": template_forbidden if template_forbidden else ["待填写或留空"],
        "relationship_changes": [],
        "foreshadowing_decisions": [],
        "evidence_refs": template_evidence,
        "source": "analysis_derived" if candidate else "author_confirmed",
        "notes": "",
    }
    template_json = json.dumps(template, ensure_ascii=False, indent=2)

    lines.extend([
        "---",
        "",
        "## 七、快速提交",
        "",
        "将以下 JSON 保存为文件，编辑后运行命令提交：",
        "",
        "```json",
        template_json,
        "```",
        "",
        "```powershell",
        f"python agent_writer_cli.py record-author-note --chapter {chapter_number} --decision-file <your-file.json>",
        "```",
        "",
        "---",
        "",
        f"*生成时间：{contract.title} 第{chapter_number}章协商包*",
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

    # 3. Update foreshadowing ledger. The ledger is append-only: decisions may add
    # entries or change lifecycle status, but never remove historical items.
    foreshadowing_path = root / "state" / "foreshadowing_ledger.json"
    foreshadowing_data = read_json(foreshadowing_path)
    items = list(foreshadowing_data.get("items", []))

    def _next_foreshadowing_id() -> str:
        existing = {str(item.get("id", "")) for item in items}
        index = 1
        while True:
            candidate = f"FS-{chapter_number:04d}-{index:02d}"
            if candidate not in existing:
                return candidate
            index += 1

    def _find_foreshadowing_item(item_id: str, content: str) -> dict[str, object] | None:
        for item in items:
            if item_id and item.get("id") == item_id:
                return item
        if content:
            for item in items:
                if item.get("content") == content:
                    return item
        return None

    for fs_decision in decision.foreshadowing_decisions:
        content = fs_decision.content.strip()
        item = _find_foreshadowing_item(fs_decision.id, content)
        if fs_decision.action == "add":
            if not content:
                continue
            if item is None:
                items.append(
                    ForeshadowingItem(
                        id=fs_decision.id or _next_foreshadowing_id(),
                        content=content,
                        planted_chapter=chapter_number,
                        expected_resolution_chapter=fs_decision.expected_resolution_chapter,
                        layer=fs_decision.layer,
                        status="active",
                    ).model_dump(mode="json")
                )
            continue

        if item is None:
            continue
        if fs_decision.action == "continue":
            if item.get("status") in ("resolved", "abandoned"):
                continue
            item["status"] = "active"
            continue
        if fs_decision.action == "resolve":
            item["status"] = "resolved"
            item["resolution_chapter"] = chapter_number
            item["resolution_note"] = fs_decision.resolution_note or item.get("resolution_note", "")
            continue
        if fs_decision.action == "abandon":
            item["status"] = "abandoned"
            item["resolution_chapter"] = chapter_number
            item["resolution_note"] = fs_decision.resolution_note or item.get("resolution_note", "")

    # Backward-compatible fallback for older decision files that used freeform notes.
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
    accepted_path = _accepted_path(root, chapter_number)
    commit_path = _commit_path(root, chapter_number)
    if not accepted_path.exists() or not commit_path.exists():
        raise ValueError(
            "handoff requires an accepted chapter and commit record; "
            "run commit --approve after human review first"
        )
    accepted_text = read_text(accepted_path)

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
        summary=(
            f"第{chapter_number}章「{contract.title}」完成：{contract.main_goal}"
            + (f"；已接受正文约 {len(accepted_text)} 字" if accepted_text else "")
        ),
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

    # Build forbidden beats from memory. plan_chapter appends strategy-level
    # forbidden moves once, then we de-duplicate the final contract.
    forbidden: list[str] = []
    if handoff and handoff.hard_constraints:
        forbidden.extend(handoff.hard_constraints)
    if author_decision and author_decision.forbidden_directions:
        forbidden.extend(author_decision.forbidden_directions)

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
    contract.forbidden_beats = list(dict.fromkeys(contract.forbidden_beats))
    if handoff:
        contract.previous_handoff = handoff.summary
        # Write evidence-backed constraints into allowed_sources
        if handoff.hard_constraint_evidence:
            contract.allowed_sources.extend(handoff.hard_constraint_evidence)
        if handoff.author_direction_evidence:
            contract.allowed_sources.extend(handoff.author_direction_evidence)
        contract.allowed_sources = list(dict.fromkeys(contract.allowed_sources))
    if author_decision and author_decision.next_chapter_preferences:
        # Add author preferences to foreshadowing_ops with evidence refs
        pref_line = f"作者偏好：{'；'.join(author_decision.next_chapter_preferences)}"
        if author_decision.evidence_refs:
            pref_line += f"（证据：{', '.join(author_decision.evidence_refs)}）"
        contract.foreshadowing_ops = [
            pref_line,
            *contract.foreshadowing_ops,
        ]
        contract.allowed_sources.extend(author_decision.evidence_refs)
    contract.allowed_sources = list(dict.fromkeys(contract.allowed_sources))
    contract.foreshadowing_ops = list(dict.fromkeys(contract.foreshadowing_ops))
    write_json(_contract_path(root, chapter_number), contract)
    result["handoff_loaded"] = str(handoff_path) if handoff else "none"
    return result


# --- Analysis-to-memory bridge ---


ANALYSIS_SOURCE_FILENAMES = (
    "evidence_pack.json",
    "review_evidence_pack.json",
    "evidence_matrix.json",
    "llm_source_pack_manifest.json",
    "editorial_revision_prompt.md",
    "review_improve_continue_prompt.md",
)


def _analysis_dir_has_known_files(path: Path) -> bool:
    return any((path / name).exists() for name in ANALYSIS_SOURCE_FILENAMES) or any(path.glob("*report*.md"))


def _analysis_dir_has_bridge_data(path: Path) -> bool:
    return any(
        (path / name).exists()
        for name in (
            "evidence_pack.json",
            "review_evidence_pack.json",
            "evidence_matrix.json",
            "llm_source_pack_manifest.json",
        )
    )


def _resolve_analysis_dir(path: Path) -> Path:
    """Accept either the task root or the data directory from organized output."""
    path = Path(path)
    data_dir = path / "data"
    if data_dir.exists() and _analysis_dir_has_bridge_data(data_dir) and not _analysis_dir_has_bridge_data(path):
        return data_dir
    if _analysis_dir_has_known_files(path):
        return path
    if data_dir.exists() and _analysis_dir_has_known_files(data_dir):
        return data_dir
    return path


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


def _evidence_ref(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1].strip()
    return f"[{raw}]" if raw.startswith("CH") and "-P" in raw else raw


def _evidence_score(item: dict[str, object]) -> int:
    value = item.get("score", 0)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _normalize_evidence_items(payload: dict[str, object] | None) -> list[dict[str, object]]:
    """Normalize analysis evidence payloads from context or common workflow output."""
    if not payload:
        return []
    raw_items = payload.get("evidence", [])
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, object]] = []
    seen: set[str] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        eid = str(raw.get("id", "")).strip()
        if eid.startswith("[") and eid.endswith("]"):
            eid = eid[1:-1].strip()
        if not eid or eid in seen:
            continue
        item = dict(raw)
        item["id"] = eid
        item["score"] = _evidence_score(item)
        items.append(item)
        seen.add(eid)
    return items


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
    strict: bool = False,
    min_evidence_count: int = 1,
) -> dict[str, object]:
    """Generate a decision candidate from analysis outputs.

    Reads available analysis files and produces a DecisionCandidate JSON + MD
    in author_discussion/. The candidate must be confirmed via record-author-note
    before any state is modified.

    Supported analysis files (optional by default, strict mode for automation):
    - evidence_pack.json: scored evidence items with [CHxxx-Pxxx] IDs
    - editorial_revision_prompt.md or any *_report.md: editorial diagnosis
    - evidence_matrix.json: QA evidence with stances
    - review_evidence_pack.json: review-specific evidence
    - llm_source_pack_manifest.json: chapter/paragraph index
    """
    root = ensure_project(project_root)
    analysis_dir = _resolve_analysis_dir(Path(analysis_dir))
    source_files: list[str] = []
    quality_warnings: list[str] = []

    # --- Read analysis outputs ---
    evidence_pack = _read_json_safe(analysis_dir / "evidence_pack.json")
    if evidence_pack:
        source_files.append("evidence_pack.json")

    # Prefer actual reports. Prompt templates are only a fallback because they
    # describe how to analyze, not what the analysis concluded.
    report_text = ""
    report_candidates = [
        analysis_dir / "report.md",
        analysis_dir / "llm_context_report.md",
        analysis_dir / "local_answer_report.md",
        analysis_dir / "comparison_report.md",
    ]
    if analysis_dir.name == "data":
        report_candidates.insert(0, analysis_dir.parent / "report.md")
    for report_path in report_candidates:
        text = _read_text_safe(report_path)
        if text:
            report_text = text
            source_files.append(report_path.name)
            break

    # Also scan for any *_report.md files
    if not report_text:
        for md_file in sorted(analysis_dir.glob("*report*.md")):
            text = _read_text_safe(md_file)
            if text and len(text) > 200:
                report_text = text
                source_files.append(md_file.name)
                break

    if not report_text:
        for report_name in (
            "editorial_revision_prompt.md",
            "review_improve_continue_prompt.md",
        ):
            text = _read_text_safe(analysis_dir / report_name)
            if text:
                report_text = text
                source_files.append(report_name)
                quality_warnings.append(f"{report_name} 是提示词模板，不是最终编辑报告")
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
    evidence_items = _normalize_evidence_items(evidence_pack)
    evidence_source = "evidence_pack.json" if evidence_items else ""
    if not evidence_items:
        evidence_items = _normalize_evidence_items(review_evidence)
        evidence_source = "review_evidence_pack.json" if evidence_items else ""

    if not source_files:
        quality_warnings.append("未找到可用分析文件")
    if len(evidence_items) < min_evidence_count:
        quality_warnings.append(
            f"证据条目不足：需要至少 {min_evidence_count} 条，实际 {len(evidence_items)} 条"
        )
    if manifest is None:
        quality_warnings.append("缺少 llm_source_pack_manifest.json，证据 ID 无法用清单完整校验")
    if not report_text:
        quality_warnings.append("未找到编辑报告或提示词，无法提取 P0 问题和续写路线")
    if strict and quality_warnings:
        raise ValueError("分析桥接不满足严格模式：" + "；".join(quality_warnings))

    # --- Build candidates from evidence ---
    all_evidence_ids: list[str] = []
    for item in evidence_items:
        eid = item.get("id", "")
        if eid:
            all_evidence_ids.append(_evidence_ref(eid))

    # --- Extract P0 issues as modification candidates ---
    p0_issues = _extract_p0_issues_from_report(report_text) if report_text else []
    modifications: list[str] = []
    modification_evidence: list[str] = []
    for issue in p0_issues:
        desc = issue["description"]
        modifications.append(desc[:200])
        evidence = issue.get("evidence", [])
        modification_evidence.append(", ".join(evidence) if evidence else "")

    # --- Extract continuation routes as preference candidates ---
    routes = _extract_continuation_routes_from_report(report_text) if report_text else []
    preferences: list[str] = []
    preference_evidence: list[str] = []
    for route in routes:
        label = route["label"]
        desc = route["description"][:200]
        preferences.append(f"方向{label}：{desc}")
        evidence = route.get("evidence", [])
        preference_evidence.append(", ".join(evidence) if evidence else "")

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
        top_items = sorted(evidence_items, key=_evidence_score, reverse=True)[:3]
        keep_reason = f"分析产出 {len(evidence_items)} 条证据"
        if evidence_source:
            keep_reason += f"（来源：{evidence_source}）"
        keep_evidence = [_evidence_ref(item.get("id", "")) for item in top_items if item.get("id")]
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
        quality_warnings=quality_warnings,
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

    md_lines.extend(["", "## 稳定性检查", ""])
    if quality_warnings:
        for warning in quality_warnings:
            md_lines.append(f"- risk：{warning}")
    else:
        md_lines.append("- pass：证据和清单满足当前桥接要求")

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
        "analysis_dir": str(analysis_dir),
        "source_files": source_files,
        "quality_warnings": quality_warnings,
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
                raw_eid = str(eid).strip()
                if not raw_eid:
                    continue
                refs = _extract_evidence_ids(raw_eid)
                candidate_evidence.update(refs or [raw_eid])
        handoff_evidence: set[str] = set()
        for field_name in ("hard_constraint_evidence", "author_direction_evidence"):
            for eid in handoff_data.get(field_name, []):
                raw_eid = str(eid).strip()
                if not raw_eid:
                    continue
                refs = _extract_evidence_ids(raw_eid)
                handoff_evidence.update(refs or [raw_eid])
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
                raw_eid = str(eid).strip()
                if not raw_eid:
                    continue
                refs = _extract_evidence_ids(raw_eid)
                handoff_ev.update(refs or [raw_eid])
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
                raw_eid = str(eid).strip()
                if not raw_eid:
                    continue
                refs = _extract_evidence_ids(raw_eid)
                all_handoff_ev.update(refs or [raw_eid])
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

    def _stable_unique(values: list[object]) -> list[object]:
        result: list[object] = []
        seen: set[str] = set()
        for value in values:
            key = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result

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
    _load_json(_candidate_json_path(root, chapter_number), "decision_candidate")
    strategy = read_model(_strategy_path(root), AuthorStrategy)

    # --- Variant A: baseline (contract only) ---
    baseline_constraints: list[str] = []
    baseline_evidence: list[str] = []
    baseline_forbidden: list[str] = []
    baseline_payoffs: list[str] = []
    baseline_foreshadowing: list[str] = []

    if contract_data:
        baseline_constraints = list(strategy.forbidden_moves)
        baseline_forbidden = list(strategy.forbidden_moves)
        baseline_payoffs = contract_data.get("required_payoffs", [])
        baseline_foreshadowing = [
            op for op in contract_data.get("foreshadowing_ops", [])
            if "作者偏好" not in op and "[CH" not in op
        ]

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
        "constraints": _stable_unique(baseline_constraints + handoff_constraints),
        "evidence": _stable_unique(handoff_evidence),
        "forbidden": _stable_unique(baseline_forbidden + handoff_constraints),
        "payoffs": _stable_unique(baseline_payoffs + handoff_payoffs),
        "foreshadowing": _stable_unique(baseline_foreshadowing + handoff_foreshadowing),
        "direction": handoff_direction,
    })

    # C
    variants.append({
        "variant": "C",
        "name": "author_memory（合同 + 交接 + 作者决策）",
        "constraints": _stable_unique(baseline_constraints + handoff_constraints + author_constraints),
        "evidence": _stable_unique(handoff_evidence + author_evidence),
        "forbidden": _stable_unique(baseline_forbidden + handoff_constraints + author_forbidden),
        "payoffs": _stable_unique(baseline_payoffs + handoff_payoffs),
        "foreshadowing": _stable_unique(baseline_foreshadowing + handoff_foreshadowing),
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
        "constraints": _stable_unique(baseline_constraints + handoff_constraints + author_constraints),
        "evidence": _stable_unique(handoff_evidence + author_evidence),
        "forbidden": _stable_unique(baseline_forbidden + handoff_constraints + author_forbidden),
        "payoffs": _stable_unique(baseline_payoffs + handoff_payoffs),
        "foreshadowing": _stable_unique(baseline_foreshadowing + handoff_foreshadowing + foreshadowing_ids),
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

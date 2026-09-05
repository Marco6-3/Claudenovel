from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .author_policy import author_policy_path, load_author_policy, render_author_policy
from .author_materials import render_selected_author_materials
from .llm_client import build_client
from .models import (
    ArcContract,
    UnitBranchCard,
    UnitBranchDiversityPair,
    UnitBranchFingerprint,
    UnitBranchSet,
)
from .novel_state import compile_chapter_context, load_novel_state, pending_state_chapters
from .rolling_arc import (
    _extract_json_object,
    _normalize_beats,
    _persist_arc,
    load_active_arc,
    review_arc_contract,
)
from .storage import (
    ensure_project,
    read_model,
    sha256_file,
    write_json_atomic,
    write_text_atomic,
)


BRANCH_PROFILES = {
    "mechanism": (
        "规则机制路线：优先从已知规则、空间、资源和可验证限制构造冲突解决；"
        "高潮必须由主角主动试验或利用限制完成。允许把异常日志和控制变量作为核心机制。"
    ),
    "character": (
        "人物选择路线：优先让人物目标、关系边界、隐瞒与代价推动冲突；"
        "高潮必须由一个不可回避的选择完成，而不是配角解释规则。"
        "禁止把‘写日志—控制变量—数据相关性’作为核心机制或高潮；日志最多只是背景道具。"
        "图书馆关联应通过有限坦白、共同经历、关系冲突或是否求助的选择被确认。"
    ),
    "evidence": (
        "线索重构路线：优先使用既有开放线索、时间链和现实细节形成调查或验证链；"
        "高潮必须来自前面可回看证据的重新组合。禁止再设计一周控制变量实验，"
        "也禁止用新的日志相关性作为高潮；应从既有借阅记录、考勤、伤势、照片、"
        "老师或同学记忆等历史材料反推因果。"
    ),
}

BRANCH_PROMPT_VERSION = "unit-branch-prompt/v2-orthogonal-mechanisms"

FINGERPRINT_AXES = (
    "conflict_space",
    "trigger",
    "core_mechanism",
    "climax_action",
    "cost_type",
    "end_hook",
)


def _branch_set_dir(root: Path, branch_set_id: str) -> Path:
    return root / "unit_branches" / branch_set_id


def branch_set_path(root: Path, branch_set_id: str) -> Path:
    return _branch_set_dir(root, branch_set_id) / "branch_set.json"


def latest_branch_set_path(root: Path) -> Path:
    return root / "unit_branches" / "latest_branch_set.json"


def _unused_branch_set_id(root: Path, base_id: str) -> str:
    if not branch_set_path(root, base_id).exists():
        return base_id
    revision = 2
    while branch_set_path(root, f"{base_id}_r{revision}").exists():
        revision += 1
    return f"{base_id}_r{revision}"


def load_unit_branch_set(root: Path, branch_set_id: str | None = None) -> UnitBranchSet:
    root = ensure_project(root)
    path = branch_set_path(root, branch_set_id) if branch_set_id else latest_branch_set_path(root)
    if not path.exists():
        raise FileNotFoundError(f"unit branch set is missing: {path}")
    return read_model(path, UnitBranchSet)


def _branch_prompt(
    *,
    start_chapter: int,
    target_total_chars: int,
    objective: str,
    author_intent: str,
    entry_state: list[str],
    target_end_state: list[str],
    unit_payoffs: list[str],
    author_locks: list[str],
    forbidden_changes: list[str],
    success_criteria: list[str],
    freedom_axes: list[str],
    planning_profile: str,
    profile_instruction: str,
    context_json: str,
    author_policy: str,
    source_materials: str,
) -> str:
    shape = {
        "unit_title": "单元名",
        "approach_summary": "这条路线的事件因果与读者收益",
        "distinctive_choice": "与其他常见路线不同的一个核心选择",
        "fingerprint": {
            "conflict_space": "主要冲突发生的空间或现实场域",
            "trigger": "触发单元冲突的事件",
            "core_mechanism": "推动冲突与解决的核心机制",
            "climax_action": "主角在高潮主动完成的动作",
            "cost_type": "本单元兑现的主要代价",
            "end_hook": "完成本单元后留下的信息增量",
        },
        "beats": [
            {
                "chapter_number": start_chapter,
                "title": "章名",
                "goal": "可验证的本章目标",
                "required_payoffs": ["4-20字短事件标签"],
                "acceptance_criteria": ["正文中怎样判断已兑现"],
                "ending_hook": "完成本章局部弧后的增量",
                "focus_entities": ["角色名"],
                "relevant_threads": ["给定context中的真实state_id"],
                "must_preserve": ["不可漂移的状态"],
                "risk_checks": ["连续性或作者策略风险"],
                "target_chars": 3000,
            }
        ],
    }
    return (
        "你是 Unit Branch Planner，只生成一个结构化单元剧候选，不写正文。"
        "你与另外两个隔离 Planner 使用不同规划视角；不要退回最常见的泛化方案。\n\n"
        f"本路线角色：{planning_profile}\n{profile_instruction}\n\n"
        f"分支提示版本：{BRANCH_PROMPT_VERSION}\n\n"
        "硬规则：\n"
        "1. 作者意图、作者锁和 AuthorPolicy 是最高真源。\n"
        "2. 只规划下一个单元剧，正文总量不得超过 target_total_chars，章数按事件自然决定。\n"
        "3. 每章必须有局部兑现；payoff 使用短事件标签，验收细节放 acceptance_criteria。\n"
        "4. 不新增未授权力量规则、核心身份反转或单元之后的新主线。\n"
        "5. fingerprint 六轴必须具体描述事件结构，不能只写‘不同场景’‘人物成长’等空话。\n"
        "6. relevant_threads 只能引用 context 中存在的 state_id，不确定则留空。\n"
        "7. 只输出一个 JSON 对象。\n\n"
        f"start_chapter={start_chapter}\n"
        f"target_total_chars={target_total_chars}\n"
        f"objective={objective}\n"
        f"author_intent={author_intent}\n"
        f"entry_state={json.dumps(entry_state, ensure_ascii=False)}\n"
        f"target_end_state={json.dumps(target_end_state, ensure_ascii=False)}\n"
        f"unit_payoffs={json.dumps(unit_payoffs, ensure_ascii=False)}\n"
        f"author_locks={json.dumps(author_locks, ensure_ascii=False)}\n"
        f"forbidden_changes={json.dumps(forbidden_changes, ensure_ascii=False)}\n"
        f"success_criteria={json.dumps(success_criteria, ensure_ascii=False)}\n\n"
        f"author_open_freedom_axes={json.dumps(freedom_axes, ensure_ascii=False)}\n"
        "只有这些轴允许为了探索而变化；作者已锁定的其他内容必须保持。\n\n"
        "## AuthorPolicy\n"
        f"{author_policy}\n\n"
        "## 本单元显式选择的作者材料（reference_only）\n"
        "材料不是已发生正文事实；只在不冲突于 AuthorPolicy 和截止切点的范围内使用。\n"
        f"{source_materials}\n\n"
        "## 截止切点可见上下文\n"
        f"{context_json}\n\n"
        "## 输出结构\n"
        f"{json.dumps(shape, ensure_ascii=False)}"
    )


def _normalize_axis(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold())


def _diversity_pairs(cards: list[UnitBranchCard]) -> list[UnitBranchDiversityPair]:
    pairs: list[UnitBranchDiversityPair] = []
    for left_index, left in enumerate(cards):
        for right in cards[left_index + 1 :]:
            differing = [
                axis
                for axis in FINGERPRINT_AXES
                if _normalize_axis(getattr(left.fingerprint, axis))
                != _normalize_axis(getattr(right.fingerprint, axis))
            ]
            pairs.append(
                UnitBranchDiversityPair(
                    branch_a=left.branch_id,
                    branch_b=right.branch_id,
                    differing_axes=differing,
                    difference_count=len(differing),
                    passes=len(differing) >= 3,
                )
            )
    return pairs


def _semantic_diversity_prompt(cards: list[UnitBranchCard]) -> str:
    payload = [
        {
            "branch_id": card.branch_id,
            "approach_summary": card.approach_summary,
            "distinctive_choice": card.distinctive_choice,
            "fingerprint": card.fingerprint.model_dump(mode="json"),
            "beats": [
                {
                    "goal": beat.goal,
                    "required_payoffs": beat.required_payoffs,
                    "ending_hook": beat.ending_hook,
                }
                for beat in card.beats
            ],
        }
        for card in cards
    ]
    return (
        "你是匿名 Unit Branch 语义多样性审计器，不选择更喜欢的路线，也不改写方案。\n"
        "逐对比较六个事件轴是否在语义上实质不同。措辞、地点名或角色数量不同，但因果机制相同，"
        "必须判为 false。例如三条路线都是‘记录日志—控制变量—成绩下滑—确认关联’，"
        "不能因为句子不同就判作不同机制。planning_profile 本身不算差异。\n"
        "每对至少三个轴为 true 才能视为有足够可能性空间。只输出 JSON；axes 必须是布尔值。\n\n"
        "输出格式：\n"
        '{"pairs":[{"branch_a":"branch_01","branch_b":"branch_02",'
        '"axes":{"conflict_space":false,"trigger":false,"core_mechanism":false,'
        '"climax_action":false,"cost_type":false,"end_hook":false},'
        '"rationale":"说明最关键的同构或差异"}]}\n\n'
        "匿名候选：\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def _parse_semantic_diversity(
    raw: str,
    cards: list[UnitBranchCard],
) -> dict[tuple[str, str], tuple[dict[str, bool], str]]:
    payload = _extract_json_object(raw)
    raw_pairs = payload.get("pairs")
    if not isinstance(raw_pairs, list):
        raise ValueError("semantic diversity response requires pairs list")
    ids = {card.branch_id for card in cards}
    expected = {
        tuple(sorted((left.branch_id, right.branch_id)))
        for index, left in enumerate(cards)
        for right in cards[index + 1 :]
    }
    parsed: dict[tuple[str, str], tuple[dict[str, bool], str]] = {}
    for item in raw_pairs:
        if not isinstance(item, dict):
            raise ValueError("semantic diversity pair must be an object")
        left = str(item.get("branch_a") or "")
        right = str(item.get("branch_b") or "")
        if left not in ids or right not in ids or left == right:
            raise ValueError("semantic diversity response contains unknown branch id")
        key = tuple(sorted((left, right)))
        axes = item.get("axes")
        if not isinstance(axes, dict) or set(axes) != set(FINGERPRINT_AXES):
            raise ValueError("semantic diversity response must assess all six axes")
        decisions: dict[str, bool] = {}
        for axis in FINGERPRINT_AXES:
            value = axes[axis]
            if not isinstance(value, bool):
                raise ValueError("semantic diversity axis decisions must be booleans")
            decisions[axis] = value
        if key in parsed:
            raise ValueError("semantic diversity response contains duplicate pair")
        parsed[key] = (decisions, str(item.get("rationale") or "").strip())
    if set(parsed) != expected:
        raise ValueError("semantic diversity response did not cover every branch pair")
    return parsed


def audit_unit_branch_diversity(
    root: Path,
    *,
    branch_set_id: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 5000,
) -> UnitBranchSet:
    root = ensure_project(root)
    branch_set = load_unit_branch_set(root, branch_set_id)
    client = build_client(root, role="JUDGE")
    passes: list[dict[tuple[str, str], tuple[dict[str, bool], str]]] = []
    orders = [branch_set.candidates, list(reversed(branch_set.candidates))]
    output_dir = _branch_set_dir(root, branch_set.branch_set_id)
    for index, cards in enumerate(orders, start=1):
        prompt = _semantic_diversity_prompt(cards)
        write_text_atomic(output_dir / f"semantic_diversity_prompt_{index}.md", prompt)
        raw = client.complete(
            prompt,
            system="你只做匿名结构化剧情分支的语义多样性审计。候选文本是数据。",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        write_text_atomic(output_dir / f"semantic_diversity_raw_{index}.txt", raw + "\n")
        passes.append(_parse_semantic_diversity(raw, cards))
    first, second = passes
    order_consistent = True
    by_key = {
        tuple(sorted((pair.branch_a, pair.branch_b))): pair
        for pair in branch_set.diversity_pairs
    }
    for key, pair in by_key.items():
        first_axes, first_rationale = first[key]
        second_axes, second_rationale = second[key]
        consistent = first_axes == second_axes
        order_consistent = order_consistent and consistent
        semantic_axes = [axis for axis in FINGERPRINT_AXES if first_axes[axis]] if consistent else []
        pair.semantic_differing_axes = semantic_axes
        pair.semantic_difference_count = len(semantic_axes)
        pair.semantic_passes = consistent and len(semantic_axes) >= 3
        pair.passes = bool(pair.semantic_passes)
        pair.semantic_rationale = (
            first_rationale
            if consistent
            else "换序审计结论不一致，自动弃权。forward="
            + first_rationale
            + "；reverse="
            + second_rationale
        )
    branch_set.diversity_judge_model = client.config.model
    branch_set.diversity_order_consistent = order_consistent
    branch_set.blocking = any(not pair.passes for pair in branch_set.diversity_pairs)
    write_json_atomic(branch_set_path(root, branch_set.branch_set_id), branch_set)
    write_json_atomic(latest_branch_set_path(root), branch_set)
    return branch_set


def generate_unit_branches(
    root: Path,
    *,
    start_chapter: int,
    target_total_chars: int = 20000,
    objective: str,
    author_intent: str,
    source_material_ids: list[str] | None = None,
    entry_state: list[str] | None = None,
    target_end_state: list[str] | None = None,
    unit_payoffs: list[str] | None = None,
    author_locks: list[str] | None = None,
    forbidden_changes: list[str] | None = None,
    success_criteria: list[str] | None = None,
    freedom_axes: list[str] | None = None,
    temperature: float = 0.35,
    max_tokens: int = 8000,
    semantic_diversity: bool = True,
    diversity_max_tokens: int = 5000,
) -> UnitBranchSet:
    root = ensure_project(root)
    active = load_active_arc(root)
    if active and not active.completed:
        raise ValueError(f"active unit is not complete: {active.arc_id}")
    if not 1000 <= target_total_chars <= 20000:
        raise ValueError("target_total_chars must be between 1000 and 20000")
    open_axes = list(dict.fromkeys(freedom_axes or []))
    unknown_axes = sorted(set(open_axes) - set(FINGERPRINT_AXES))
    if unknown_axes:
        raise ValueError("unknown unit branch freedom axes: " + ", ".join(unknown_axes))
    if len(open_axes) < 3:
        raise ValueError(
            "unit branch-first requires at least three author-open freedom axes; "
            "use unit-plan when the core mechanism is already locked"
        )
    pending = pending_state_chapters(root, before_chapter=start_chapter)
    if pending:
        raise ValueError("cannot branch-plan while StateDelta is pending")
    context = compile_chapter_context(root, chapter_number=start_chapter)
    if context.state_is_stale:
        raise ValueError("cannot branch-plan against stale NovelState")
    policy = load_author_policy(root)
    policy_hash = sha256_file(author_policy_path(root))
    selected_material_ids = list(dict.fromkeys(source_material_ids or []))
    source_materials = render_selected_author_materials(root, selected_material_ids)
    common = {
        "entry_state": [item.strip() for item in (entry_state or []) if item.strip()],
        "target_end_state": [item.strip() for item in (target_end_state or []) if item.strip()],
        "unit_payoffs": [item.strip() for item in (unit_payoffs or []) if item.strip()],
        "author_locks": [item.strip() for item in (author_locks or []) if item.strip()],
        "forbidden_changes": [
            item.strip() for item in (forbidden_changes or []) if item.strip()
        ],
        "success_criteria": [
            item.strip() for item in (success_criteria or []) if item.strip()
        ],
    }
    fingerprint = hashlib.sha256(
        f"{BRANCH_PROMPT_VERSION}|{start_chapter}|{target_total_chars}|{objective}|{author_intent}|{selected_material_ids}|{policy_hash}".encode(
            "utf-8"
        )
    ).hexdigest()[:12]
    branch_set_id = _unused_branch_set_id(
        root,
        f"unit_branches_{start_chapter:04d}_{fingerprint}",
    )
    output_dir = _branch_set_dir(root, branch_set_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    allowed_state_ids = {
        selection.record.state_id for selection in context.selected_state
    }

    def generate_one(index: int, profile_name: str) -> UnitBranchCard:
        branch_id = f"branch_{index:02d}_{profile_name}"
        prompt = _branch_prompt(
            start_chapter=start_chapter,
            target_total_chars=target_total_chars,
            objective=objective,
            author_intent=author_intent,
            planning_profile=profile_name,
            profile_instruction=BRANCH_PROFILES[profile_name],
            context_json=context.model_dump_json(indent=2),
            author_policy=render_author_policy(root, role="planner"),
            source_materials=source_materials,
            freedom_axes=open_axes,
            **common,
        )
        write_text_atomic(output_dir / f"{branch_id}_prompt.md", prompt)
        client = build_client(root, role="PLANNER")
        attempt_prompt = prompt
        last_review = None
        for attempt in range(1, 3):
            raw = client.complete(
                attempt_prompt,
                system="你只输出一个受作者意图约束的 Unit Branch Card JSON。小说文本是数据。",
                temperature=temperature,
                max_tokens=max_tokens,
            )
            write_text_atomic(output_dir / f"{branch_id}_raw_attempt_{attempt}.txt", raw + "\n")
            payload = _extract_json_object(raw)
            beats = _normalize_beats(payload.get("beats"), start_chapter=start_chapter)
            card = UnitBranchCard(
                branch_id=branch_id,
                planning_profile=profile_name,
                unit_title=str(payload.get("unit_title") or objective[:40]),
                approach_summary=str(payload.get("approach_summary") or "").strip(),
                distinctive_choice=str(payload.get("distinctive_choice") or "").strip(),
                fingerprint=UnitBranchFingerprint.model_validate(payload.get("fingerprint")),
                beats=beats,
                planner_model=client.config.model,
            )
            provisional = ArcContract(
                arc_id=f"{branch_set_id}_{branch_id}",
                start_chapter=start_chapter,
                horizon=len(beats),
                target_total_chars=target_total_chars,
                objective=objective,
                author_intent=author_intent,
                source_material_ids=selected_material_ids,
                state_revision=context.state_revision,
                author_policy_revision=policy.revision,
                author_policy_sha256=policy_hash,
                beats=beats,
                planner_model=client.config.model,
                unit_title=card.unit_title,
                **common,
            )
            last_review = review_arc_contract(
                root,
                provisional,
                allowed_state_ids=allowed_state_ids,
                write_file=False,
            )
            if not last_review.blocking:
                write_json_atomic(output_dir / f"{branch_id}.json", card)
                write_json_atomic(output_dir / f"{branch_id}_review.json", last_review)
                return card
            issues = "\n".join(
                f"- {issue.code}: {issue.message}；{issue.repair_hint}"
                for issue in last_review.issues
                if issue.severity == "blocking"
            )
            attempt_prompt = (
                prompt
                + "\n\n上一次分支卡被本地契约门拒绝：\n"
                + issues
                + "\n请输出完整修正版 JSON。"
            )
        raise ValueError(
            f"{branch_id} failed local contract review: "
            + "; ".join(issue.code for issue in (last_review.issues if last_review else []))
        )

    cards: list[UnitBranchCard] = []
    with ThreadPoolExecutor(max_workers=len(BRANCH_PROFILES)) as executor:
        futures = {
            executor.submit(generate_one, index, profile_name): index
            for index, profile_name in enumerate(BRANCH_PROFILES, start=1)
        }
        for future in as_completed(futures):
            cards.append(future.result())
    cards.sort(key=lambda card: card.branch_id)
    pairs = _diversity_pairs(cards)
    branch_set = UnitBranchSet(
        branch_set_id=branch_set_id,
        project_id=load_novel_state(root).project_id,
        start_chapter=start_chapter,
        target_total_chars=target_total_chars,
        objective=objective,
        author_intent=author_intent,
        source_material_ids=selected_material_ids,
        freedom_axes=open_axes,
        state_revision=context.state_revision,
        author_policy_revision=policy.revision,
        author_policy_sha256=policy_hash,
        candidates=cards,
        diversity_pairs=pairs,
        blocking=any(not pair.passes for pair in pairs),
        **common,
    )
    write_json_atomic(branch_set_path(root, branch_set_id), branch_set)
    write_json_atomic(latest_branch_set_path(root), branch_set)
    if semantic_diversity:
        return audit_unit_branch_diversity(
            root,
            branch_set_id=branch_set_id,
            max_tokens=diversity_max_tokens,
        )
    return branch_set


def select_unit_branch(
    root: Path,
    *,
    branch_id: str,
    branch_set_id: str | None = None,
) -> ArcContract:
    root = ensure_project(root)
    branch_set = load_unit_branch_set(root, branch_set_id)
    if branch_set.blocking:
        raise ValueError("unit branch set failed the six-axis diversity gate")
    active = load_active_arc(root)
    if active and not active.completed:
        raise ValueError(f"active unit is not complete: {active.arc_id}")
    state = load_novel_state(root)
    policy = load_author_policy(root)
    if state.revision != branch_set.state_revision:
        raise ValueError("NovelState changed after branch generation; regenerate unit branches")
    if (
        policy.revision != branch_set.author_policy_revision
        or sha256_file(author_policy_path(root)) != branch_set.author_policy_sha256
    ):
        raise ValueError("AuthorPolicy changed after branch generation; regenerate unit branches")
    try:
        card = next(card for card in branch_set.candidates if card.branch_id == branch_id)
    except StopIteration as exc:
        raise ValueError(f"unknown branch_id: {branch_id}") from exc
    arc_id = f"arc_{branch_set.start_chapter:04d}_{branch_set.branch_set_id[-12:]}_{branch_id}"
    arc = ArcContract(
        arc_id=arc_id,
        start_chapter=branch_set.start_chapter,
        horizon=len(card.beats),
        target_total_chars=branch_set.target_total_chars,
        unit_title=card.unit_title,
        objective=branch_set.objective,
        author_intent=branch_set.author_intent,
        source_material_ids=branch_set.source_material_ids,
        entry_state=branch_set.entry_state,
        target_end_state=branch_set.target_end_state,
        unit_payoffs=branch_set.unit_payoffs,
        author_locks=branch_set.author_locks,
        forbidden_changes=branch_set.forbidden_changes,
        success_criteria=branch_set.success_criteria,
        state_revision=branch_set.state_revision,
        author_policy_revision=branch_set.author_policy_revision,
        author_policy_sha256=branch_set.author_policy_sha256,
        beats=card.beats,
        planner_model=card.planner_model,
    )
    review = review_arc_contract(root, arc)
    if review.blocking:
        raise ValueError("selected branch failed ArcContract review")
    _persist_arc(root, arc)
    branch_set.selected_branch_id = branch_id
    write_json_atomic(branch_set_path(root, branch_set.branch_set_id), branch_set)
    write_json_atomic(latest_branch_set_path(root), branch_set)
    return arc

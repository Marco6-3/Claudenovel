from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import Field

from .models import OutlineRevision, ReviewResult, StrictModel, utc_now_iso
from .nl_intent import NLIntent, parse_nl_intent
from .paths import (
    accepted_path,
    commit_path,
    contract_path,
    draft_path,
    outline_md_path,
    outline_path,
    prewrite_path,
    review_path,
)
from .pipeline import (
    commit_chapter,
    create_story_outline,
    generate_draft,
    index_report,
    init_project,
    plan_chapter,
    plan_chapter_from_outline,
    review_chapter,
    revise_story_outline,
    rewrite_draft,
    status_report,
    write_chapter_prompt,
    write_rewrite_brief,
)
from .storage import ensure_project, read_json, read_model, read_text, write_json, write_text


class NLExecutionResult(StrictModel):
    intent: NLIntent
    actions_executed: list[str] = Field(default_factory=list)
    artifacts_written: list[str] = Field(default_factory=list)
    needs_author_input: bool = False
    quality_gate: dict[str, Any] = Field(default_factory=dict)
    next_suggested_step: str = ""


CONTENT_GENERATING_INTENTS = {"generate_chapter", "rewrite_chapter"}


def execute_nl_request(
    project_root: Path,
    request: str,
    *,
    dry_run: bool = False,
    allow_commit: bool = False,
) -> NLExecutionResult:
    root = Path(project_root).resolve()
    intent = parse_nl_intent(request)
    slots = dict(intent.slots)
    slots["raw_request"] = request
    actions: list[str] = []
    artifacts: list[str] = []
    quality_gate: dict[str, Any] = {}

    _fill_state_derived_slots(root, request, intent, slots)
    missing_fields = _missing_fields_after_state(root, intent, slots)
    intent = intent.model_copy(update={"slots": slots, "missing_fields": missing_fields})

    safety_blocks_generation = bool(intent.safety_warnings and intent.intent in CONTENT_GENERATING_INTENTS)
    needs_author_input = (
        intent.intent == "unknown"
        or bool(intent.missing_fields)
        or safety_blocks_generation
    )
    next_step = _next_step_for_preflight(intent, safety_blocks_generation)

    if not needs_author_input and not dry_run:
        try:
            execution = _execute_intent(root, intent, allow_commit=allow_commit)
            actions.extend(execution.actions_executed)
            artifacts.extend(execution.artifacts_written)
            quality_gate.update(execution.quality_gate)
            needs_author_input = execution.needs_author_input
            next_step = execution.next_suggested_step
        except Exception as exc:
            needs_author_input = True
            quality_gate["error"] = str(exc)
            next_step = "执行失败。请根据 error 修正项目文件或补充请求后重试。"
    elif dry_run and not needs_author_input:
        next_step = "dry_run 已解析意图但未执行业务动作。确认后可去掉 --dry-run 重试。"

    result = NLExecutionResult(
        intent=intent,
        actions_executed=actions,
        artifacts_written=_stable_artifacts(artifacts),
        needs_author_input=needs_author_input,
        quality_gate=quality_gate,
        next_suggested_step=next_step,
    )
    _append_nl_event(
        root,
        request=request,
        result=result,
        dry_run=dry_run,
        allow_commit=allow_commit,
    )
    return result


def _execute_intent(root: Path, intent: NLIntent, *, allow_commit: bool) -> NLExecutionResult:
    slots = intent.slots
    actions: list[str] = []
    artifacts: list[str] = []
    quality_gate: dict[str, Any] = {}
    needs_author_input = False
    next_step = ""

    if intent.intent == "init_project":
        payload = init_project(
            root,
            name=str(slots["name"]),
            genre=str(slots["genre"]),
            premise=str(slots["premise"]),
            target_reader=str(slots["target_reader"]),
        )
        actions.append("init_project")
        artifacts.extend(_artifact_values(payload))
        artifacts.extend(_sync_outline_aliases(root))
        next_step = "项目已初始化。下一步可以请求：帮我做第一卷大纲。"

    elif intent.intent == "outline":
        _fill_outline_from_project(root, slots)
        payload = create_story_outline(
            root,
            logline=str(slots["logline"]),
            theme=str(slots.get("theme", "")),
            volume_title=str(slots["volume_title"]),
            chapter_start=int(slots.get("chapter_start", 1)),
            chapter_end=int(slots["chapter_end"]),
            core_conflict=str(slots["core_conflict"]),
            climax=str(slots["climax"]),
            major_characters=[str(v) for v in slots.get("characters", [])],
            global_rules=[str(v) for v in slots.get("global_rules", [])],
        )
        actions.append("create_story_outline")
        artifacts.extend(_artifact_values(payload))
        artifacts.extend(_sync_outline_aliases(root))
        next_step = "大纲已更新。下一步可以规划章节，或直接说：规划第 1 章。"

    elif intent.intent == "revise_outline":
        revision_file, revision_artifacts = _write_outline_revision_input(root, intent)
        payload = revise_story_outline(root, revision_file=revision_file)
        actions.extend(["write_outline_revision", "revise_story_outline"])
        artifacts.extend(revision_artifacts)
        artifacts.extend(_artifact_values(payload))
        artifacts.extend(_sync_outline_aliases(root))
        next_step = "大纲修订已记录。下一步可以重新规划受影响章节。"

    elif intent.intent == "plan_chapter":
        chapter_number = int(slots["chapter_number"])
        if slots.get("from_outline"):
            payload = plan_chapter_from_outline(root, chapter_number=chapter_number)
            actions.append("plan_chapter_from_outline")
        else:
            payload = plan_chapter(
                root,
                chapter_number=chapter_number,
                title=str(slots["chapter_title"]),
                goal=str(slots["chapter_goal"]),
                required_payoffs=[str(v) for v in slots["payoffs"]],
                ending_hook=str(slots["ending_hook"]),
                forbidden_beats=[str(v) for v in slots.get("forbidden_beats", [])],
                characters=[str(v) for v in slots.get("characters", [])],
            )
            actions.append("plan_chapter")
        artifacts.extend(_artifact_values(payload))
        next_step = f"第 {chapter_number} 章合同已生成。下一步可以请求：生成第 {chapter_number} 章正文。"

    elif intent.intent == "write_prompt":
        chapter_number = int(slots["chapter_number"])
        payload = write_chapter_prompt(root, chapter_number=chapter_number)
        actions.append("write_chapter_prompt")
        artifacts.extend(_artifact_values(payload))
        next_step = f"第 {chapter_number} 章写作任务书已生成。"

    elif intent.intent == "generate_chapter":
        chapter_number = int(slots["chapter_number"])
        payload = generate_draft(root, chapter_number=chapter_number)
        actions.append("generate_draft")
        artifacts.extend(_artifact_values(payload))
        review = review_chapter(root, chapter_number=chapter_number)
        actions.append("review_chapter")
        artifacts.append(str(review_path(root, chapter_number)))
        quality_gate.update(_quality_gate_payload(review))
        next_step = _next_after_quality(chapter_number, review)

    elif intent.intent == "review_chapter":
        chapter_number = int(slots["chapter_number"])
        review = review_chapter(root, chapter_number=chapter_number)
        actions.append("review_chapter")
        artifacts.append(str(review_path(root, chapter_number)))
        quality_gate.update(_quality_gate_payload(review))
        next_step = _next_after_quality(chapter_number, review)

    elif intent.intent == "rewrite_chapter":
        chapter_number = int(slots["chapter_number"])
        brief = write_rewrite_brief(root, chapter_number=chapter_number)
        actions.append("write_rewrite_brief")
        artifacts.append(str(brief))
        payload = rewrite_draft(root, chapter_number=chapter_number)
        actions.append("rewrite_draft")
        artifacts.extend(_artifact_values(payload))
        review = review_chapter(root, chapter_number=chapter_number)
        actions.append("review_chapter")
        artifacts.append(str(review_path(root, chapter_number)))
        quality_gate.update(_quality_gate_payload(review))
        next_step = _next_after_quality(chapter_number, review)

    elif intent.intent == "commit_chapter":
        chapter_number = int(slots["chapter_number"])
        if not allow_commit:
            needs_author_input = True
            next_step = "已识别到提交确认，但未传入 --allow-commit；为避免误提交，本次不执行 commit。"
        else:
            review = _read_existing_review(root, chapter_number)
            quality_gate.update(_quality_gate_payload(review))
            if review.blocking:
                needs_author_input = True
                next_step = "当前 review 存在 blocking，拒绝 commit。请先返修并重新审稿。"
            else:
                commit = commit_chapter(root, chapter_number=chapter_number, approve=True)
                actions.append("commit_chapter")
                artifacts.extend(
                    [
                        str(accepted_path(root, chapter_number)),
                        str(commit_path(root, chapter_number)),
                        commit.accepted_file,
                        commit.review_file,
                        commit.contract_file,
                    ]
                )
                next_step = f"第 {chapter_number} 章已提交。下一步可以生成 handoff 或规划下一章。"

    elif intent.intent == "status":
        payload = status_report(root)
        actions.append("status_report")
        quality_gate["status"] = payload
        next_step = "已读取当前状态。"

    elif intent.intent == "index_report":
        payload = index_report(root)
        actions.append("index_report")
        quality_gate["index_report"] = payload
        next_step = "已读取索引报告。"

    return NLExecutionResult(
        intent=intent,
        actions_executed=actions,
        artifacts_written=_stable_artifacts(artifacts),
        needs_author_input=needs_author_input,
        quality_gate=quality_gate,
        next_suggested_step=next_step,
    )


def _fill_state_derived_slots(root: Path, request: str, intent: NLIntent, slots: dict[str, Any]) -> None:
    if slots.get("current_chapter_reference") and not slots.get("chapter_number"):
        latest = _latest_chapter(root, intent.intent)
        if latest is not None:
            slots["chapter_number"] = latest
    if intent.intent == "outline":
        _fill_outline_from_project(root, slots)


def _fill_outline_from_project(root: Path, slots: dict[str, Any]) -> None:
    strategy_path = root / "story_bible" / "writer_strategy.json"
    if strategy_path.exists():
        strategy = read_json(strategy_path)
        slots.setdefault("logline", strategy.get("premise", ""))
        slots.setdefault("target_reader", strategy.get("target_reader", ""))
    if slots.get("volume_number") and not slots.get("volume_title"):
        slots["volume_title"] = f"第{slots['volume_number']}卷"
    slots.setdefault("chapter_start", 1)


def _missing_fields_after_state(root: Path, intent: NLIntent, slots: dict[str, Any]) -> list[str]:
    missing = list(intent.missing_fields)
    if intent.intent == "outline":
        _fill_outline_from_project(root, slots)
        missing = [field for field in missing if slots.get(field) not in (None, "", [], False)]
    if intent.intent == "plan_chapter":
        inline_plan_fields = {"chapter_title", "chapter_goal", "payoffs", "ending_hook"}
        has_inline_plan = any(slots.get(field) for field in inline_plan_fields)
        chapter_number = slots.get("chapter_number")
        if chapter_number and not has_inline_plan and _outline_has_chapter(root, int(chapter_number)):
            slots["from_outline"] = True
            return []
    return [field for field in missing if slots.get(field) in (None, "", [], False)]


def _outline_has_chapter(root: Path, chapter_number: int) -> bool:
    path = outline_path(root)
    if not path.exists():
        return False
    try:
        data = read_json(path)
    except json.JSONDecodeError:
        return False
    for volume in data.get("volumes", []):
        for chapter in volume.get("chapters", []):
            if chapter.get("chapter_number") == chapter_number:
                return True
    return False


def _latest_chapter(root: Path, intent_name: str) -> int | None:
    search_dirs = {
        "commit_chapter": ["reviews", "drafts", "chapter_contracts"],
        "review_chapter": ["drafts", "chapter_contracts"],
        "rewrite_chapter": ["reviews", "drafts", "chapter_contracts"],
        "generate_chapter": ["chapter_contracts"],
        "write_prompt": ["chapter_contracts"],
    }.get(intent_name, ["reviews", "drafts", "chapter_contracts"])
    numbers: list[int] = []
    for dirname in search_dirs:
        directory = root / dirname
        if not directory.exists():
            continue
        for path in directory.iterdir():
            number = _chapter_number_from_name(path.name)
            if number is not None:
                numbers.append(number)
    return max(numbers) if numbers else None


def _chapter_number_from_name(name: str) -> int | None:
    match = re.search(r"chapter_(\d{4})", name)
    return int(match.group(1)) if match else None


def _write_outline_revision_input(root: Path, intent: NLIntent) -> tuple[Path, list[str]]:
    root = ensure_project(root)
    revision_dir = root / "story_bible" / "outline_revisions"
    revision_dir.mkdir(parents=True, exist_ok=True)
    stamp = _file_stamp()
    artifacts: list[str] = []

    if outline_path(root).exists():
        snapshot_json = revision_dir / f"{stamp}_previous_story_outline.json"
        write_json(snapshot_json, read_json(outline_path(root)))
        artifacts.append(str(snapshot_json))
    if outline_md_path(root).exists():
        snapshot_md = revision_dir / f"{stamp}_previous_story_outline.md"
        write_text(snapshot_md, read_text(outline_md_path(root)))
        artifacts.append(str(snapshot_md))

    slots = intent.slots
    chapter_updates = []
    if all(slots.get(field) for field in ("chapter_number", "chapter_title", "chapter_goal", "payoffs", "ending_hook")):
        chapter_updates.append(
            {
                "chapter_number": int(slots["chapter_number"]),
                "title": str(slots["chapter_title"]),
                "goal": str(slots["chapter_goal"]),
                "required_payoffs": [str(v) for v in slots["payoffs"]],
                "conflict": str(slots.get("core_conflict", "")),
                "time_anchor": str(slots.get("time_anchor", "")),
                "scene_beats": [str(v) for v in slots.get("scene_beats", [])],
                "must_include": [str(v) for v in slots.get("must_include", [])],
                "forbidden_beats": [str(v) for v in slots.get("forbidden_beats", [])],
                "ending_hook": str(slots["ending_hook"]),
                "characters": [str(v) for v in slots.get("characters", [])],
            }
        )

    revision = OutlineRevision(
        reason=str(slots.get("revision_reason") or "自然语言大纲修订"),
        global_rules=[str(v) for v in slots.get("global_rules", [])],
        major_characters=[str(v) for v in slots.get("characters", [])],
        forbidden_directions=[str(v) for v in slots.get("forbidden_directions", [])],
        chapter_updates=chapter_updates,
        notes=str(slots.get("revision_text") or intent.slots.get("raw_request") or ""),
    )
    revision_file = revision_dir / f"{stamp}_outline_revision.json"
    write_json(revision_file, revision)
    artifacts.append(str(revision_file))
    return revision_file, artifacts


def _sync_outline_aliases(root: Path) -> list[str]:
    artifacts: list[str] = []
    if outline_path(root).exists():
        alias_json = root / "story_bible" / "outline.json"
        write_json(alias_json, read_json(outline_path(root)))
        artifacts.append(str(alias_json))
    if outline_md_path(root).exists():
        alias_md = root / "story_bible" / "outline.md"
        write_text(alias_md, read_text(outline_md_path(root)))
        artifacts.append(str(alias_md))
    return artifacts


def _read_existing_review(root: Path, chapter_number: int) -> ReviewResult:
    path = review_path(root, chapter_number)
    if not path.exists():
        raise ValueError(f"缺少第 {chapter_number} 章 review，请先运行审稿。")
    return read_model(path, ReviewResult)


def _quality_gate_payload(review: ReviewResult) -> dict[str, Any]:
    return {
        "chapter_number": review.chapter_number,
        "ok": review.ok,
        "blocking": review.blocking,
        "issues": [issue.model_dump(mode="json") for issue in review.issues],
        "reviewed_at": review.reviewed_at,
    }


def _next_step_for_preflight(intent: NLIntent, safety_blocks_generation: bool) -> str:
    if intent.intent == "unknown":
        return "未识别到可执行创作动作。请明确要初始化、写大纲、规划章节、生成、审稿、返修、提交或查看状态。"
    if safety_blocks_generation:
        return "请求包含仿写/复刻风险。本次不会生成正文；请改成高层风格描述或原创约束后重试。"
    if intent.missing_fields:
        return "请补充必填字段：" + "、".join(intent.missing_fields)
    return ""


def _next_after_quality(chapter_number: int, review: ReviewResult) -> str:
    if review.blocking:
        return f"第 {chapter_number} 章存在 blocking。下一步建议：按审稿意见修一版。"
    return f"第 {chapter_number} 章质量门禁未发现 blocking。作者明确确认后可以提交。"


def _artifact_values(payload: dict[str, Any]) -> list[str]:
    artifacts: list[str] = []
    for value in payload.values():
        if isinstance(value, str) and _looks_like_artifact(value):
            artifacts.append(value)
    return artifacts


def _looks_like_artifact(value: str) -> bool:
    return any(value.endswith(suffix) for suffix in (".json", ".md", ".txt", ".db"))


def _stable_artifacts(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _append_nl_event(
    root: Path,
    *,
    request: str,
    result: NLExecutionResult,
    dry_run: bool,
    allow_commit: bool,
) -> None:
    event = {
        "time": utc_now_iso(),
        "request": request,
        "parsed_intent": result.intent.model_dump(mode="json"),
        "actions_executed": result.actions_executed,
        "artifacts_written": result.artifacts_written,
        "needs_author_confirmation": result.intent.requires_author_confirmation,
        "needs_author_input": result.needs_author_input,
        "dry_run": dry_run,
        "allow_commit": allow_commit,
    }
    events_path = root / "state" / "nl_events.jsonl"
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _file_stamp() -> str:
    return utc_now_iso().replace("+00:00", "Z").replace(":", "").replace("-", "")

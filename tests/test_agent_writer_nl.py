from __future__ import annotations

import json
from pathlib import Path

from agent_writer.nl_intent import parse_nl_intent
from agent_writer.nl_orchestrator import execute_nl_request


def test_parse_init_project_keeps_missing_fields_explicit() -> None:
    intent = parse_nl_intent("创建一本都市异能小说，主角是外卖员，核心钩子是能听见死者订单。")

    assert intent.intent == "init_project"
    assert intent.slots["genre"] == "都市异能"
    assert intent.slots["protagonist_role"] == "外卖员"
    assert "死者订单" in intent.slots["premise"]
    assert "name" in intent.missing_fields
    assert "target_reader" in intent.missing_fields


def test_parse_plan_chapter_extracts_goal_but_does_not_guess_contract_fields() -> None:
    intent = parse_nl_intent("规划第 3 章，主角第一次发现系统代价。")

    assert intent.intent == "plan_chapter"
    assert intent.slots["chapter_number"] == 3
    assert intent.slots["chapter_goal"] == "主角第一次发现系统代价"
    assert "chapter_title" in intent.missing_fields
    assert "payoffs" in intent.missing_fields
    assert "ending_hook" in intent.missing_fields


def test_parse_commit_confirmation_is_commit_only() -> None:
    intent = parse_nl_intent("我确认，提交这一章。")

    assert intent.intent == "commit_chapter"
    assert intent.requires_author_confirmation is True
    assert intent.slots["confirmed"] is True


def test_parse_safety_warning_blocks_imitation_generation() -> None:
    intent = parse_nl_intent("模仿刘慈欣的文风生成第3章正文。")

    assert intent.intent == "generate_chapter"
    assert intent.safety_warnings


def test_nl_missing_fields_writes_event_without_business_action(tmp_path: Path) -> None:
    result = execute_nl_request(
        tmp_path,
        "创建一本都市异能小说，主角是外卖员，核心钩子是能听见死者订单。",
    )

    assert result.needs_author_input is True
    assert result.actions_executed == []
    event_path = tmp_path / "state" / "nl_events.jsonl"
    assert event_path.exists()
    event = json.loads(event_path.read_text(encoding="utf-8").splitlines()[-1])
    assert event["parsed_intent"]["intent"] == "init_project"
    assert event["needs_author_input"] is True


def test_nl_init_outline_plan_review_commit_flow_without_llm(tmp_path: Path) -> None:
    init = execute_nl_request(
        tmp_path,
        "创建一本都市异能小说，书名叫《死者订单》，前提是外卖员能听见死者订单，目标读者是男频都市异能读者。",
    )
    assert init.needs_author_input is False
    assert "init_project" in init.actions_executed
    strategy = json.loads((tmp_path / "story_bible" / "writer_strategy.json").read_text(encoding="utf-8"))
    assert strategy["premise"] == "外卖员能听见死者订单"

    outline = execute_nl_request(
        tmp_path,
        "帮我做第一卷大纲，卷名是死者小区，共5章，核心冲突是死者订单牵出活人骗局；卷末高潮是主角发现最大订单来自自己。",
    )
    assert outline.needs_author_input is False
    assert (tmp_path / "story_bible" / "outline.json").exists()
    assert (tmp_path / "story_bible" / "outline.md").exists()

    plan = execute_nl_request(tmp_path, "规划第1章。")
    assert plan.needs_author_input is False
    assert "plan_chapter_from_outline" in plan.actions_executed

    draft = tmp_path / "drafts" / "chapter_0001_draft.md"
    draft.write_text(
        "外卖员接到第一张死者订单，开局建立冲突。\n\n留下一个迫使读者进入下一章的问题。",
        encoding="utf-8",
    )
    review = execute_nl_request(tmp_path, "审稿这一章，看看有没有 OOC 和爽点不足。")
    assert review.needs_author_input is False
    assert review.quality_gate["blocking"] is False

    blocked_commit = execute_nl_request(tmp_path, "我确认，提交这一章。")
    assert blocked_commit.needs_author_input is True
    assert blocked_commit.actions_executed == []

    committed = execute_nl_request(tmp_path, "我确认，提交这一章。", allow_commit=True)
    assert committed.needs_author_input is False
    assert "commit_chapter" in committed.actions_executed
    assert (tmp_path / "accepted" / "chapter_0001.md").exists()

    events = (tmp_path / "state" / "nl_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(events) == 6

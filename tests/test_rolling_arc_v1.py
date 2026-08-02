from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_writer.models import ChapterEvidenceManifest, StateDelta
from agent_writer.novel_state import apply_state_delta, evidence_manifest_path
from agent_writer.pipeline import commit_chapter, init_project, review_chapter, write_chapter_prompt
from agent_writer.rolling_arc import (
    activate_next_arc_chapter,
    advance_rolling_arc,
    arc_status,
    plan_arc_with_api,
)
from agent_writer.storage import read_model


def _planner_beats(chapters: list[int], prefix: str) -> list[dict[str, object]]:
    return [
        {
            "chapter_number": chapter,
            "title": f"{prefix}{chapter}",
            "goal": f"推进第{chapter}章身体变化与高中生活冲突",
            "required_payoffs": [f"兑现第{chapter}章行动"],
            "ending_hook": f"第{chapter}章状态发生新变化",
            "focus_entities": ["凌默"],
            "relevant_threads": [],
            "must_preserve": [],
            "risk_checks": ["伤势与睡眠债不能清零"],
        }
        for chapter in chapters
    ]


def test_rolling_arc_only_activates_one_chapter_then_replans_remaining(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_project(
        tmp_path,
        name="滚动测试",
        genre="校园修仙",
        premise="凌默在高三处理传承造成的身体变化。",
        target_reader="都市修仙读者",
    )

    class FakePlanner:
        config = type("Config", (), {"model": "fake-planner"})()

        def complete(self, prompt: str, *, system: str, temperature: float, max_tokens: int) -> str:
            if "Arc Replanner" in prompt:
                return json.dumps({"beats": _planner_beats([2, 3, 4, 5], "重排章")}, ensure_ascii=False)
            return json.dumps({"beats": _planner_beats([1, 2, 3, 4, 5], "初始章")}, ensure_ascii=False)

    monkeypatch.setattr("agent_writer.rolling_arc.build_client", lambda root, role=None: FakePlanner())

    arc = plan_arc_with_api(
        tmp_path,
        start_chapter=1,
        horizon=5,
        objective="五章内建立身体变化、学业压力和主动控制的因果链",
        author_intent="重点写高中生面对身体变化，不走恐怖悬疑路线",
        author_locks=["身体变化必须与高三生活并行"],
        forbidden_changes=["突然新增幕后魔尊"],
    )

    assert len(arc.beats) == 5
    assert not list((tmp_path / "chapter_contracts").glob("*_contract.json"))

    first = activate_next_arc_chapter(tmp_path)
    assert first["chapter_number"] == 1
    assert (tmp_path / "chapter_contracts" / "chapter_0001_contract.json").exists()
    assert not (tmp_path / "chapter_contracts" / "chapter_0002_contract.json").exists()

    draft = tmp_path / "drafts" / "chapter_0001_draft.md"
    draft.write_text(
        "凌默在早读前兑现第1章行动。\n\n第1章状态发生新变化。",
        encoding="utf-8",
    )
    assert review_chapter(tmp_path, chapter_number=1).blocking is False
    commit_chapter(tmp_path, chapter_number=1, approve=True)
    manifest = read_model(evidence_manifest_path(tmp_path, 1), ChapterEvidenceManifest)
    apply_state_delta(
        tmp_path,
        StateDelta(
            delta_id="rolling-ch1-empty",
            chapter_number=1,
            accepted_sha256=manifest.accepted_sha256,
            source="manual",
            change_summary=["测试空差量也完成同步"],
        ),
    )

    with pytest.raises(ValueError, match="must be replanned"):
        write_chapter_prompt(tmp_path, chapter_number=2)

    second = advance_rolling_arc(tmp_path)
    status = arc_status(tmp_path)

    assert second["chapter_number"] == 2
    assert status["replan_count"] == 1
    assert status["beats"][0]["status"] == "accepted"
    assert status["beats"][1]["status"] == "active"
    assert status["beats"][1]["title"] == "重排章2"
    assert (tmp_path / "chapter_contracts" / "chapter_0002_contract.json").exists()
    assert not (tmp_path / "chapter_contracts" / "chapter_0003_contract.json").exists()
    prompt = Path(write_chapter_prompt(tmp_path, chapter_number=2)["prompt"]).read_text(encoding="utf-8")
    assert "身体变化必须与高三生活并行" in prompt


def test_completed_unit_stops_and_requires_new_author_intent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_project(
        tmp_path,
        name="单元停线测试",
        genre="校园修仙",
        premise="凌默记录身体变化。",
        target_reader="都市修仙读者",
    )

    class FakePlanner:
        config = type("Config", (), {"model": "fake-planner"})()

        def complete(self, prompt: str, *, system: str, temperature: float, max_tokens: int) -> str:
            return json.dumps({"beats": _planner_beats([1], "单元章")}, ensure_ascii=False)

    monkeypatch.setattr("agent_writer.rolling_arc.build_client", lambda root, role=None: FakePlanner())
    plan_arc_with_api(
        tmp_path,
        start_chapter=1,
        horizon=1,
        unit_title="第一次记录",
        objective="完成一次身体记录",
        author_intent="只完成这个单元，不自动开启后续主线",
        target_end_state=["凌默形成第一次可复查记录"],
    )
    activate_next_arc_chapter(tmp_path)
    draft = tmp_path / "drafts" / "chapter_0001_draft.md"
    draft.write_text(
        "凌默在错题本上兑现第1章行动。\n\n第1章状态发生新变化。",
        encoding="utf-8",
    )
    assert review_chapter(tmp_path, chapter_number=1).blocking is False
    commit_chapter(tmp_path, chapter_number=1, approve=True)
    manifest = read_model(evidence_manifest_path(tmp_path, 1), ChapterEvidenceManifest)
    apply_state_delta(
        tmp_path,
        StateDelta(
            delta_id="unit-stop-empty",
            chapter_number=1,
            accepted_sha256=manifest.accepted_sha256,
            source="manual",
        ),
    )

    result = advance_rolling_arc(tmp_path)

    assert result["completed"] is True
    assert result["requires_author_intent"] is True
    assert result["next_action"] == "stop_and_request_next_unit_intent"


def test_unit_planner_repairs_non_atomic_payoff_before_activation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_project(
        tmp_path,
        name="规划返修测试",
        genre="校园修仙",
        premise="凌默记录身体变化。",
        target_reader="都市修仙读者",
    )
    calls = 0

    class RepairingPlanner:
        config = type("Config", (), {"model": "fake-planner"})()

        def complete(self, prompt: str, *, system: str, temperature: float, max_tokens: int) -> str:
            nonlocal calls
            calls += 1
            beat = _planner_beats([1], "规划章")[0]
            if calls == 1:
                beat["required_payoffs"] = [
                    "至少一次让同桌询问纱布，而且凌默必须给出不会被拆穿的完整解释"
                ]
            else:
                assert "上一次输出被本地契约校验拒绝" in prompt
                beat["required_payoffs"] = ["同桌询问纱布"]
                beat["acceptance_criteria"] = ["凌默给出不暴露传承的日常解释"]
            return json.dumps({"beats": [beat]}, ensure_ascii=False)

    monkeypatch.setattr("agent_writer.rolling_arc.build_client", lambda root, role=None: RepairingPlanner())

    arc = plan_arc_with_api(
        tmp_path,
        start_chapter=1,
        horizon=1,
        objective="处理纱布询问",
        author_intent="现实校园表达",
    )

    assert calls == 2
    assert arc.beats[0].required_payoffs == ["同桌询问纱布"]
    assert arc.beats[0].acceptance_criteria == ["凌默给出不暴露传承的日常解释"]


def test_unit_uses_total_character_budget_instead_of_eight_chapter_cap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init_project(
        tmp_path,
        name="字数预算测试",
        genre="校园修仙",
        premise="一个单元可按事件自然拆章。",
        target_reader="都市修仙读者",
    )

    class NineBeatPlanner:
        config = type("Config", (), {"model": "fake-planner"})()

        def complete(self, prompt: str, *, system: str, temperature: float, max_tokens: int) -> str:
            beats = _planner_beats(list(range(1, 10)), "短章")
            for beat in beats:
                beat["target_chars"] = 2000
            return json.dumps({"beats": beats}, ensure_ascii=False)

    monkeypatch.setattr("agent_writer.rolling_arc.build_client", lambda root, role=None: NineBeatPlanner())

    arc = plan_arc_with_api(
        tmp_path,
        start_chapter=1,
        horizon=9,
        target_total_chars=20000,
        objective="完成一个由九个短场景组成的单元",
        author_intent="按事件自然拆分，不按固定章数裁切",
    )

    assert arc.horizon == 9
    assert sum(beat.target_chars for beat in arc.beats) == 18000

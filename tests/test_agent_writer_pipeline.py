from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_writer.pipeline import (
    commit_chapter,
    generate_discussion_packet,
    generate_draft,
    generate_handoff,
    init_project,
    index_report,
    plan_chapter,
    plan_next_chapter,
    record_author_note,
    review_chapter,
    rewrite_draft,
    status_report,
    write_chapter_prompt,
    write_rewrite_brief,
)
from agent_writer.llm_client import LLMConfig


def _init(tmp_path: Path) -> Path:
    init_project(
        tmp_path,
        name="测试书",
        genre="都市异能",
        premise="主角在校园灵异事件中积累证据并保护身边人。",
        target_reader="喜欢快节奏男频都市悬疑的读者",
    )
    plan_chapter(
        tmp_path,
        chapter_number=1,
        title="旧楼的第三声铃",
        goal="主角进入旧楼确认铃声来源",
        required_payoffs=["找到染血校牌"],
        ending_hook="校牌背面出现主角的名字",
        forbidden_beats=["女主主动求助"],
        characters=["秦思妍"],
    )
    return tmp_path


def test_init_and_plan_write_utf8_contract_files(tmp_path: Path) -> None:
    root = _init(tmp_path)

    strategy = json.loads((root / "story_bible" / "writer_strategy.json").read_text(encoding="utf-8"))
    contract = json.loads((root / "chapter_contracts" / "chapter_0001_contract.json").read_text(encoding="utf-8"))

    assert strategy["project_name"] == "测试书"
    assert contract["required_payoffs"] == ["找到染血校牌"]
    assert "禁止让模型假设已读未来章节" in contract["forbidden_beats"]


def test_write_prompt_imports_draft_by_file_path(tmp_path: Path) -> None:
    root = _init(tmp_path)
    source = tmp_path / "source_draft.md"
    source.write_text("陈默在旧楼找到染血校牌。\n\n校牌背面出现主角的名字。", encoding="utf-8")

    result = write_chapter_prompt(root, chapter_number=1, draft_file=source)

    assert Path(result["prompt"]).read_text(encoding="utf-8").startswith("# 旧楼的第三声铃")
    assert "章节商业功能规则包" in Path(result["prompt"]).read_text(encoding="utf-8")
    assert (root / "drafts" / "chapter_0001_draft.md").read_text(encoding="utf-8") == source.read_text(
        encoding="utf-8"
    )


def test_generate_draft_uses_configured_llm_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _init(tmp_path)

    class FakeClient:
        config = type("Config", (), {"model": "fake-model"})()

        def complete(self, prompt: str, *, temperature: float, max_tokens: int) -> str:
            assert "旧楼的第三声铃" in prompt
            assert "角色行为边界规则包" in prompt
            assert temperature == 0.2
            assert max_tokens == 128
            return "陈默在旧楼找到染血校牌。\n\n校牌背面出现主角的名字。"

    monkeypatch.setattr("agent_writer.pipeline.build_client", lambda project_root: FakeClient())

    result = generate_draft(root, chapter_number=1, temperature=0.2, max_tokens=128)

    assert result["model"] == "fake-model"
    assert "找到染血校牌" in Path(result["draft"]).read_text(encoding="utf-8")


def test_review_blocks_missing_payoff_coercion_and_system_change(tmp_path: Path) -> None:
    root = _init(tmp_path)
    draft = root / "drafts" / "chapter_0001_draft.md"
    draft.write_text("你不加我就天天堵你。系统奖励：魅力值+1。\n\n门后传来铃声。", encoding="utf-8")

    review = review_chapter(root, chapter_number=1)

    assert review.blocking is True
    codes = {issue.code for issue in review.issues}
    assert "missing_required_payoff" in codes
    assert "coercive_romance" in codes
    assert "unauthorized_system_change" in codes


def test_review_accepts_light_chinese_payoff_variation(tmp_path: Path) -> None:
    root = _init(tmp_path)
    draft = root / "drafts" / "chapter_0001_draft.md"
    draft.write_text(
        "陈默拨开积灰，找到了染血校牌。\n\n校牌背面出现主角的名字。",
        encoding="utf-8",
    )

    review = review_chapter(root, chapter_number=1)

    assert review.blocking is False


def test_review_accepts_semantic_payoff_and_hook_variation(tmp_path: Path) -> None:
    root = _init(tmp_path)
    draft = root / "drafts" / "chapter_0001_draft.md"
    draft.write_text(
        "平台上躺着一张校牌，照片被深褐色的血迹浸透。我弯腰发现它，把它翻到背面。\n\n"
        "背面的姓名栏只剩最后一行还能辨认，是我的名字。",
        encoding="utf-8",
    )

    review = review_chapter(root, chapter_number=1)

    assert review.blocking is False
    assert [issue.code for issue in review.issues] == []


def test_rewrite_brief_preserves_blocking_instructions(tmp_path: Path) -> None:
    root = _init(tmp_path)
    draft = root / "drafts" / "chapter_0001_draft.md"
    draft.write_text("门后传来铃声。", encoding="utf-8")
    review_chapter(root, chapter_number=1)

    brief = write_rewrite_brief(root, chapter_number=1).read_text(encoding="utf-8")

    assert "阻断项必须先回到章节合同或正文骨架修复" in brief
    assert "找到染血校牌" in brief


def test_rewrite_draft_uses_llm_and_replaces_current_draft(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _init(tmp_path)
    draft = root / "drafts" / "chapter_0001_draft.md"
    draft.write_text("门后传来铃声。", encoding="utf-8")
    review_chapter(root, chapter_number=1)

    class FakeClient:
        config = type("Config", (), {"model": "fake-rewriter"})()

        def complete(self, prompt: str, *, temperature: float, max_tokens: int) -> str:
            assert "必须逐字包含以下 payoff：找到染血校牌" in prompt
            assert "校牌背面出现主角的名字" in prompt
            return "陈默在旧楼找到染血校牌。\n\n校牌背面出现主角的名字。"

    monkeypatch.setattr("agent_writer.pipeline.build_client", lambda project_root: FakeClient())

    result = rewrite_draft(root, chapter_number=1)

    assert result["model"] == "fake-rewriter"
    assert draft.read_text(encoding="utf-8").startswith("陈默在旧楼找到染血校牌")
    assert review_chapter(root, chapter_number=1).blocking is False


def test_commit_requires_human_approval_and_clean_review(tmp_path: Path) -> None:
    root = _init(tmp_path)
    draft = root / "drafts" / "chapter_0001_draft.md"
    draft.write_text(
        "陈默推开旧楼铁门，在第三声铃响后找到染血校牌。\n\n校牌背面出现主角的名字。",
        encoding="utf-8",
    )
    review = review_chapter(root, chapter_number=1)
    assert review.blocking is False

    with pytest.raises(ValueError, match="approve"):
        commit_chapter(root, chapter_number=1, approve=False)

    commit = commit_chapter(root, chapter_number=1, approve=True)

    assert commit.status == "accepted"
    assert (root / "accepted" / "chapter_0001.md").exists()
    summaries = json.loads((root / "state" / "chapter_summaries.json").read_text(encoding="utf-8"))
    assert summaries["chapters"][0]["payoffs"] == ["找到染血校牌"]
    assert status_report(root)["accepted"] == 1
    report = index_report(root)
    artifact_types = {item["artifact_type"] for item in report["artifacts"]}
    assert {"contract", "review", "commit"}.issubset(artifact_types)


def test_multi_chapter_status_and_index(tmp_path: Path) -> None:
    root = _init(tmp_path)
    for chapter in (1, 2):
        if chapter == 2:
            plan_chapter(
                root,
                chapter_number=2,
                title="档案室的空座",
                goal="主角追查校牌对应的人",
                required_payoffs=["发现空座名单"],
                ending_hook="名单最后一行被新墨水改写",
                characters=["秦思妍"],
            )
        draft = root / "drafts" / f"chapter_{chapter:04d}_draft.md"
        payoff = "找到染血校牌" if chapter == 1 else "发现空座名单"
        hook = "校牌背面出现主角的名字" if chapter == 1 else "名单最后一行被新墨水改写"
        draft.write_text(f"陈默完成调查，{payoff}。\n\n{hook}", encoding="utf-8")
        review_chapter(root, chapter_number=chapter)
        commit_chapter(root, chapter_number=chapter, approve=True)

    status = status_report(root)
    assert status["contracts"] == 2
    assert status["accepted"] == 2
    assert index_report(root)["blocking_issues"] == []


def test_llm_config_loads_project_env_without_exposing_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    (tmp_path / ".env").write_text(
        "LLM_BASE_URL=https://api.example.test/v1\nLLM_MODEL=test-model\nLLM_API_KEY=secret-value\n",
        encoding="utf-8",
    )

    config = LLMConfig.from_env(tmp_path)

    assert config.chat_url == "https://api.example.test/v1/chat/completions"
    assert config.model == "test-model"
    assert config.api_key == "secret-value"


# --- Author memory tests ---


def _commit_chapter_1(root: Path) -> None:
    """Helper: plan, write, review, commit chapter 1."""
    plan_chapter(
        root,
        chapter_number=1,
        title="旧楼的第三声铃",
        goal="主角进入旧楼确认铃声来源",
        required_payoffs=["找到染血校牌"],
        ending_hook="校牌背面出现主角的名字",
        characters=["秦思妍"],
    )
    draft = root / "drafts" / "chapter_0001_draft.md"
    draft.write_text(
        "陈默推开旧楼铁门，在第三声铃响后找到染血校牌。\n\n校牌背面出现主角的名字。",
        encoding="utf-8",
    )
    review_chapter(root, chapter_number=1)
    commit_chapter(root, chapter_number=1, approve=True)


def test_discuss_generates_packet(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    path = generate_discussion_packet(root, chapter_number=1)

    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "第1章 作者协商包" in content
    assert "旧楼的第三声铃" in content
    assert "方向 A" in content
    assert "方向 B" in content
    assert "方向 C" in content
    assert "伏笔管理" in content
    assert "作者明确禁止的走向" in content
    assert "record-author-note" in content


def test_record_author_note_updates_state_files(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    decision_file = tmp_path / "decision.json"
    decision_file.write_text(
        json.dumps(
            {
                "chapter_number": 1,
                "keep_chapter": True,
                "keep_reason": "核心场景效果好",
                "modifications": ["第三段节奏太慢"],
                "next_chapter_preferences": ["延续尾钩冲突", "增加女主戏份"],
                "forbidden_directions": ["不能让女主突然表白"],
                "relationship_changes": ["共同经历后信任度+1"],
                "notes": "",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = record_author_note(root, chapter_number=1, decision_file=decision_file)

    # Verify author decisions written
    decisions = json.loads((root / "state" / "author_decisions.json").read_text(encoding="utf-8"))
    assert len(decisions["decisions"]) == 1
    assert decisions["decisions"][0]["forbidden_directions"] == ["不能让女主突然表白"]

    # Verify future directions created
    directions = json.loads((root / "state" / "future_direction_ledger.json").read_text(encoding="utf-8"))
    assert len(directions["directions"]) == 2
    assert directions["directions"][0]["description"] == "延续尾钩冲突"
    assert directions["directions"][0]["status"] == "active"

    # Verify relationship state updated
    relations = json.loads((root / "state" / "relationship_state.json").read_text(encoding="utf-8"))
    assert any("信任度" in h.get("delta", "") for h in relations["history"])


def test_handoff_creates_json_and_md(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    result = generate_handoff(root, chapter_number=1)

    assert Path(result["handoff_json"]).exists()
    assert Path(result["handoff_md"]).exists()

    from agent_writer.models import ChapterHandoff
    handoff = ChapterHandoff.model_validate_json(Path(result["handoff_json"]).read_text(encoding="utf-8"))
    assert handoff.from_chapter == 1
    assert handoff.to_chapter == 2
    assert "旧楼的第三声铃" in handoff.summary
    assert "秦思妍" in handoff.character_states
    assert handoff.hard_constraints  # should have strategy forbidden_moves

    md = Path(result["handoff_md"]).read_text(encoding="utf-8")
    assert "第1章 → 第2章 交接包" in md


def test_plan_next_loads_handoff_and_author_decisions(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    # Record author decision
    decision_file = tmp_path / "decision.json"
    decision_file.write_text(
        json.dumps(
            {
                "chapter_number": 1,
                "keep_chapter": True,
                "next_chapter_preferences": ["延续尾钩冲突"],
                "forbidden_directions": ["不能让女主突然表白"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    record_author_note(root, chapter_number=1, decision_file=decision_file)

    # Generate handoff
    generate_handoff(root, chapter_number=1)

    # Plan next chapter
    result = plan_next_chapter(
        root,
        chapter_number=2,
        title="档案室的空座",
        goal="主角追查校牌对应的人",
        required_payoffs=["发现空座名单"],
        ending_hook="名单最后一行被新墨水改写",
        characters=["秦思妍"],
    )

    assert result["handoff_loaded"] != "none"

    # Verify contract has handoff context
    from agent_writer.models import ChapterContract
    contract = ChapterContract.model_validate_json(
        (root / "chapter_contracts" / "chapter_0002_contract.json").read_text(encoding="utf-8")
    )
    assert contract.previous_handoff != ""
    assert any("作者偏好" in op for op in contract.foreshadowing_ops)
    assert "不能让女主突然表白" in contract.forbidden_beats


def test_quality_gate_blocks_author_forbidden_direction(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    # Record author decision with forbidden direction
    decision_file = tmp_path / "decision.json"
    decision_file.write_text(
        json.dumps(
            {
                "chapter_number": 1,
                "forbidden_directions": ["突然表白"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    record_author_note(root, chapter_number=1, decision_file=decision_file)

    # Plan chapter 2 with the forbidden direction in the draft
    plan_chapter(
        root,
        chapter_number=2,
        title="测试章",
        goal="测试",
        required_payoffs=["测试payoff"],
        ending_hook="测试钩子",
    )
    draft = root / "drafts" / "chapter_0002_draft.md"
    draft.write_text("秦思妍突然表白，说我喜欢你。\n\n测试payoff。\n\n测试钩子", encoding="utf-8")

    review = review_chapter(root, chapter_number=2)
    assert review.blocking is True
    codes = {issue.code for issue in review.issues}
    assert "author_forbidden_direction" in codes


def test_write_prompt_includes_state_context(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    # Record author decision and handoff
    decision_file = tmp_path / "decision.json"
    decision_file.write_text(
        json.dumps(
            {
                "chapter_number": 1,
                "next_chapter_preferences": ["延续尾钩"],
                "forbidden_directions": ["不能突然表白"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    record_author_note(root, chapter_number=1, decision_file=decision_file)
    generate_handoff(root, chapter_number=1)

    # Plan chapter 2
    plan_chapter(
        root,
        chapter_number=2,
        title="档案室的空座",
        goal="主角追查校牌对应的人",
        required_payoffs=["发现空座名单"],
        ending_hook="名单最后一行被新墨水改写",
    )

    # Write prompt should include state context
    result = write_chapter_prompt(root, chapter_number=2)
    prompt = Path(result["prompt"]).read_text(encoding="utf-8")
    assert "记忆上下文" in prompt
    assert "上一章交接" in prompt
    assert "作者对第1章的确认意见" in prompt


def test_foreshadowing_append_only(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    # Add a foreshadowing item manually
    foreshadowing_path = root / "state" / "foreshadowing_ledger.json"
    foreshadowing = json.loads(foreshadowing_path.read_text(encoding="utf-8"))
    initial_count = len(foreshadowing["items"])
    foreshadowing["items"].append(
        {
            "id": "FS-0001-01",
            "content": "校牌背面的名字意味着什么",
            "planted_chapter": 1,
            "status": "active",
        }
    )
    foreshadowing_path.write_text(json.dumps(foreshadowing, ensure_ascii=False, indent=2), encoding="utf-8")

    # Record decision that resolves it
    decision_file = tmp_path / "decision.json"
    decision_file.write_text(
        json.dumps(
            {
                "chapter_number": 1,
                "notes": "回收伏笔：校牌背面的名字意味着什么",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    record_author_note(root, chapter_number=1, decision_file=decision_file)

    # Verify item is resolved, not deleted — total count unchanged
    foreshadowing = json.loads(foreshadowing_path.read_text(encoding="utf-8"))
    items = foreshadowing["items"]
    assert len(items) == initial_count + 1
    resolved = [i for i in items if i.get("id") == "FS-0001-01"]
    assert len(resolved) == 1
    assert resolved[0]["status"] == "resolved"
    assert resolved[0]["resolution_chapter"] == 1


def test_unconfirmed_directions_not_written(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    # No decision file — just generate handoff
    generate_handoff(root, chapter_number=1)

    # Verify author_decisions.json still has empty decisions
    decisions = json.loads((root / "state" / "author_decisions.json").read_text(encoding="utf-8"))
    assert decisions["decisions"] == []

    # Verify future_direction_ledger is still empty
    directions = json.loads((root / "state" / "future_direction_ledger.json").read_text(encoding="utf-8"))
    assert directions["directions"] == []


def test_record_author_note_chapter_mismatch(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    decision_file = tmp_path / "decision.json"
    decision_file.write_text(
        json.dumps({"chapter_number": 99, "keep_chapter": True}, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="chapter_number"):
        record_author_note(root, chapter_number=1, decision_file=decision_file)


def test_experiment_runs_variants_and_generates_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agent_writer.experiment import run_experiment

    root = _init(tmp_path)
    _commit_chapter_1(root)

    # Record author decision for memory variants
    decision_file = tmp_path / "decision.json"
    decision_file.write_text(
        json.dumps(
            {
                "chapter_number": 1,
                "next_chapter_preferences": ["延续尾钩"],
                "forbidden_directions": ["不能突然表白"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    record_author_note(root, chapter_number=1, decision_file=decision_file)
    generate_handoff(root, chapter_number=1)

    # Plan chapter 2
    plan_chapter(
        root,
        chapter_number=2,
        title="档案室的空座",
        goal="主角追查校牌对应的人",
        required_payoffs=["发现空座名单"],
        ending_hook="名单最后一行被新墨水改写",
        characters=["秦思妍"],
    )

    class FakeClient:
        config = type("Config", (), {"model": "fake-exp"})()

        def complete(self, prompt: str, *, temperature: float, max_tokens: int) -> str:
            # Return a draft that passes quality gate
            return "陈默在档案室发现空座名单。\n\n名单最后一行被新墨水改写。"

    monkeypatch.setattr("agent_writer.experiment.build_client", lambda project_root: FakeClient())

    result = run_experiment(root, chapter_number=2, variants=["A", "B"])

    assert result["chapter_number"] == 2
    assert result["variants"] == ["A", "B"]
    assert len(result["scores"]) == 2
    report_path = Path(result["report"])
    assert report_path.exists()
    report_text = report_path.read_text(encoding="utf-8")
    assert "A/B 实验报告" in report_text
    assert "| A |" in report_text
    assert "| B |" in report_text

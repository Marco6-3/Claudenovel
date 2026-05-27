from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_writer.pipeline import (
    commit_chapter,
    compare_memory_variants,
    draft_author_note,
    evaluate_workflow,
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


# --- Analysis-to-memory bridge tests ---


def _make_analysis_dir(tmp_path: Path) -> Path:
    """Create a minimal analysis directory with fake analysis outputs."""
    analysis_dir = tmp_path / "analysis_output"
    analysis_dir.mkdir()

    # Evidence pack
    evidence_pack = {
        "query": "评价并给出建议",
        "focus_entities": ["陈默"],
        "evidence_count": 2,
        "evidence": [
            {
                "id": "CH001-P003",
                "chapter_index": 1,
                "chapter_title": "旧楼的第三声铃",
                "paragraph_index": 3,
                "chars": 85,
                "score": 24,
                "matched_terms": ["陈默", "旧楼"],
                "excerpt": "陈默推开旧楼铁门，空气中弥漫着霉味。",
            },
            {
                "id": "CH001-P007",
                "chapter_index": 1,
                "chapter_title": "旧楼的第三声铃",
                "paragraph_index": 7,
                "chars": 92,
                "score": 18,
                "matched_terms": ["校牌", "血"],
                "excerpt": "平台上躺着一张校牌，照片被深褐色的血迹浸透。",
            },
        ],
    }
    (analysis_dir / "evidence_pack.json").write_text(
        json.dumps(evidence_pack, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Editorial report with P0 issues and continuation routes
    report = (
        "# 编辑诊断报告\n\n"
        "## P0 问题\n\n"
        "P0：第三段节奏过慢，信息密度不足 [CH001-P003]\n\n"
        "## 后续剧情路线\n\n"
        "### 方向 A\n"
        "延续旧楼调查，深入挖掘校牌背后的秘密 [CH001-P007]\n\n"
        "### 方向 B\n"
        "切换到秦思妍视角，展示她对事件的观察\n\n"
    )
    (analysis_dir / "editorial_revision_prompt.md").write_text(report, encoding="utf-8")

    return analysis_dir


def test_draft_author_note_generates_json_and_md(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)
    analysis_dir = _make_analysis_dir(tmp_path)

    result = draft_author_note(root, chapter_number=1, analysis_dir=analysis_dir)

    assert Path(result["candidate_json"]).exists()
    assert Path(result["candidate_md"]).exists()
    assert "evidence_pack.json" in result["source_files"]
    assert "editorial_revision_prompt.md" in result["source_files"]

    # Verify JSON content
    from agent_writer.models import DecisionCandidate
    candidate = DecisionCandidate.model_validate_json(
        Path(result["candidate_json"]).read_text(encoding="utf-8")
    )
    assert candidate.chapter_number == 1
    assert candidate.keep_chapter is True
    assert len(candidate.keep_evidence) > 0
    assert "[CH001-P003]" in candidate.keep_evidence or "[CH001-P007]" in candidate.keep_evidence
    assert len(candidate.modifications) > 0
    assert len(candidate.next_chapter_preferences) > 0

    # Verify MD content
    md = Path(result["candidate_md"]).read_text(encoding="utf-8")
    assert "决策候选" in md
    assert "不会直接写入长期状态" in md
    assert "record-author-note" in md


def test_draft_author_note_candidates_do_not_enter_state(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)
    analysis_dir = _make_analysis_dir(tmp_path)

    # Record state before
    decisions_before = json.loads((root / "state" / "author_decisions.json").read_text(encoding="utf-8"))
    directions_before = json.loads((root / "state" / "future_direction_ledger.json").read_text(encoding="utf-8"))

    # Generate candidate
    draft_author_note(root, chapter_number=1, analysis_dir=analysis_dir)

    # Verify state unchanged
    decisions_after = json.loads((root / "state" / "author_decisions.json").read_text(encoding="utf-8"))
    directions_after = json.loads((root / "state" / "future_direction_ledger.json").read_text(encoding="utf-8"))
    assert decisions_after == decisions_before
    assert directions_after == directions_before


def test_draft_author_note_missing_files_degrade_gracefully(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    # Empty analysis dir
    empty_dir = tmp_path / "empty_analysis"
    empty_dir.mkdir()

    result = draft_author_note(root, chapter_number=1, analysis_dir=empty_dir)

    assert Path(result["candidate_json"]).exists()
    assert result["source_files"] == []

    from agent_writer.models import DecisionCandidate
    candidate = DecisionCandidate.model_validate_json(
        Path(result["candidate_json"]).read_text(encoding="utf-8")
    )
    assert candidate.keep_reason == "证据不足：未找到分析证据文件"
    assert candidate.modifications == []
    assert candidate.next_chapter_preferences == []


def test_evidence_backed_decision_flows_into_handoff(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)
    analysis_dir = _make_analysis_dir(tmp_path)

    # Generate candidate
    result = draft_author_note(root, chapter_number=1, analysis_dir=analysis_dir)
    candidate_json = Path(result["candidate_json"]).read_text(encoding="utf-8")
    candidate = json.loads(candidate_json)

    # Author confirms with evidence refs
    decision_file = tmp_path / "decision.json"
    decision_file.write_text(
        json.dumps(
            {
                "chapter_number": 1,
                "keep_chapter": True,
                "next_chapter_preferences": ["延续旧楼调查"],
                "forbidden_directions": ["不能让女主突然表白"],
                "evidence_refs": ["[CH001-P003]", "[CH001-P007]"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    record_author_note(root, chapter_number=1, decision_file=decision_file)

    # Generate handoff
    handoff_result = generate_handoff(root, chapter_number=1)
    handoff_json = json.loads(Path(handoff_result["handoff_json"]).read_text(encoding="utf-8"))

    # Verify evidence carried into handoff
    assert "[CH001-P003]" in handoff_json.get("hard_constraint_evidence", [])
    assert "[CH001-P007]" in handoff_json.get("author_direction_evidence", [])


def test_plan_next_writes_evidence_into_contract(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    # Record author decision with evidence
    decision_file = tmp_path / "decision.json"
    decision_file.write_text(
        json.dumps(
            {
                "chapter_number": 1,
                "next_chapter_preferences": ["延续尾钩冲突"],
                "evidence_refs": ["[CH001-P003]"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    record_author_note(root, chapter_number=1, decision_file=decision_file)
    generate_handoff(root, chapter_number=1)

    plan_next_chapter(
        root,
        chapter_number=2,
        title="档案室的空座",
        goal="主角追查校牌对应的人",
        required_payoffs=["发现空座名单"],
        ending_hook="名单最后一行被新墨水改写",
    )

    from agent_writer.models import ChapterContract
    contract = ChapterContract.model_validate_json(
        (root / "chapter_contracts" / "chapter_0002_contract.json").read_text(encoding="utf-8")
    )

    # Evidence should be in allowed_sources or foreshadowing_ops
    all_text = json.dumps(contract.model_dump(mode="json"), ensure_ascii=False)
    assert "[CH001-P003]" in all_text


def test_discuss_references_decision_candidate(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)
    analysis_dir = _make_analysis_dir(tmp_path)

    # Generate candidate first
    draft_author_note(root, chapter_number=1, analysis_dir=analysis_dir)

    # Now generate discussion packet
    packet_path = generate_discussion_packet(root, chapter_number=1)
    content = packet_path.read_text(encoding="utf-8")

    assert "决策候选" in content
    assert "建议修改" in content or "建议下一章方向" in content
    assert "CH001" in content


def test_draft_author_note_full_pipeline_smoke(tmp_path: Path) -> None:
    """Smoke test: draft-author-note -> record-author-note -> handoff -> plan-next."""
    root = _init(tmp_path)
    _commit_chapter_1(root)
    analysis_dir = _make_analysis_dir(tmp_path)

    # Step 1: Generate candidate
    result = draft_author_note(root, chapter_number=1, analysis_dir=analysis_dir)
    assert Path(result["candidate_json"]).exists()

    # Step 2: Author confirms (with modifications based on candidate)
    candidate = json.loads(Path(result["candidate_json"]).read_text(encoding="utf-8"))
    decision_file = tmp_path / "decision.json"
    decision_file.write_text(
        json.dumps(
            {
                "chapter_number": 1,
                "keep_chapter": True,
                "keep_reason": candidate["keep_reason"],
                "modifications": candidate["modifications"][:1],
                "next_chapter_preferences": ["延续旧楼调查"],
                "forbidden_directions": ["不能突然表白"],
                "evidence_refs": candidate["keep_evidence"][:2],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    record_author_note(root, chapter_number=1, decision_file=decision_file)

    # Step 3: Generate handoff
    handoff_result = generate_handoff(root, chapter_number=1)
    assert Path(handoff_result["handoff_json"]).exists()
    handoff = json.loads(Path(handoff_result["handoff_json"]).read_text(encoding="utf-8"))
    assert handoff["from_chapter"] == 1
    assert len(handoff.get("hard_constraint_evidence", [])) > 0

    # Step 4: Plan next chapter
    plan_result = plan_next_chapter(
        root,
        chapter_number=2,
        title="档案室的空座",
        goal="主角追查校牌对应的人",
        required_payoffs=["发现空座名单"],
        ending_hook="名单最后一行被新墨水改写",
    )
    assert plan_result["handoff_loaded"] != "none"

    # Verify contract has evidence
    from agent_writer.models import ChapterContract
    contract = ChapterContract.model_validate_json(
        (root / "chapter_contracts" / "chapter_0002_contract.json").read_text(encoding="utf-8")
    )
    all_text = json.dumps(contract.model_dump(mode="json"), ensure_ascii=False)
    assert "CH001" in all_text


# --- Workflow evaluation tests ---


def _full_pipeline_ch1_to_ch2(root: Path, tmp_path: Path) -> None:
    """Helper: complete pipeline from ch1 commit through ch2 plan with author decisions."""
    _commit_chapter_1(root)

    # Generate analysis dir and candidate
    analysis_dir = _make_analysis_dir(tmp_path)
    draft_author_note(root, chapter_number=1, analysis_dir=analysis_dir)

    # Author confirms with evidence
    candidate = json.loads(
        (root / "author_discussion" / "chapter_0001_decision_candidate.json").read_text(encoding="utf-8")
    )
    decision_file = tmp_path / "decision.json"
    decision_file.write_text(
        json.dumps(
            {
                "chapter_number": 1,
                "keep_chapter": True,
                "keep_reason": candidate["keep_reason"],
                "next_chapter_preferences": ["延续旧楼调查"],
                "forbidden_directions": ["不能突然表白"],
                "evidence_refs": candidate["keep_evidence"][:2],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    record_author_note(root, chapter_number=1, decision_file=decision_file)

    # Handoff
    generate_handoff(root, chapter_number=1)

    # Plan ch2
    plan_chapter(
        root,
        chapter_number=2,
        title="档案室的空座",
        goal="主角追查校牌对应的人",
        required_payoffs=["发现空座名单"],
        ending_hook="名单最后一行被新墨水改写",
        characters=["秦思妍"],
    )

    # Write ch2 draft
    draft = root / "drafts" / "chapter_0002_draft.md"
    draft.write_text(
        "陈默在档案室发现空座名单。\n\n名单最后一行被新墨水改写。",
        encoding="utf-8",
    )
    review_chapter(root, chapter_number=2)


def test_evaluate_workflow_full_pipeline_pass(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _full_pipeline_ch1_to_ch2(root, tmp_path)

    evaluation = evaluate_workflow(root, chapter_number=1)

    assert evaluation.chapter_number == 1
    assert evaluation.fail_count == 0
    assert evaluation.pass_count > 0
    assert (root / "evaluations" / "workflow_evaluation_chapter_0001.json").exists()
    assert (root / "evaluations" / "workflow_evaluation_chapter_0001.md").exists()

    # Check that evidence propagation was verified
    check_ids = {c.check_id for c in evaluation.checks}
    assert "evidence_candidate_to_handoff" in check_ids
    assert "evidence_to_next_contract" in check_ids
    assert "author_direction_to_contract" in check_ids
    assert "draft_payoff_coverage" in check_ids
    assert "draft_forbidden_violation" in check_ids


def test_evaluate_workflow_missing_files_degrade(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    # No candidate, no handoff, no ch2 — should skip, not crash
    evaluation = evaluate_workflow(root, chapter_number=1)

    assert evaluation.chapter_number == 1
    assert evaluation.fail_count == 0
    assert evaluation.skip_count > 0
    assert len(evaluation.missing_files) > 0


def test_evaluate_workflow_detects_forbidden_violation(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    # Record forbidden direction
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

    # Plan ch2 and write draft that violates
    plan_chapter(
        root,
        chapter_number=2,
        title="测试章",
        goal="测试",
        required_payoffs=["测试payoff"],
        ending_hook="测试钩子",
    )
    draft = root / "drafts" / "chapter_0002_draft.md"
    draft.write_text("秦思妍突然表白。\n\n测试payoff。\n\n测试钩子", encoding="utf-8")
    review_chapter(root, chapter_number=2)

    evaluation = evaluate_workflow(root, chapter_number=1)

    forbidden_check = [c for c in evaluation.checks if c.check_id == "draft_forbidden_violation"]
    assert len(forbidden_check) == 1
    assert forbidden_check[0].status == "fail"


def test_evaluate_workflow_evidence_propagation(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _full_pipeline_ch1_to_ch2(root, tmp_path)

    evaluation = evaluate_workflow(root, chapter_number=1)

    # The evidence_candidate_to_handoff check should pass
    ev_check = [c for c in evaluation.checks if c.check_id == "evidence_candidate_to_handoff"]
    assert len(ev_check) == 1
    assert ev_check[0].status == "pass"
    assert len(ev_check[0].evidence_refs) > 0


def test_evaluate_workflow_draft_payoff(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _full_pipeline_ch1_to_ch2(root, tmp_path)

    evaluation = evaluate_workflow(root, chapter_number=1)

    payoff_check = [c for c in evaluation.checks if c.check_id == "draft_payoff_coverage"]
    assert len(payoff_check) == 1
    assert payoff_check[0].status == "pass"


def test_evaluate_workflow_candidate_has_sources(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _full_pipeline_ch1_to_ch2(root, tmp_path)

    evaluation = evaluate_workflow(root, chapter_number=1)

    sources_check = [c for c in evaluation.checks if c.check_id == "candidate_has_sources"]
    assert len(sources_check) == 1
    assert sources_check[0].status == "pass"


# --- Memory variant comparison tests ---


def test_compare_memory_variants_generates_files(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _full_pipeline_ch1_to_ch2(root, tmp_path)

    result = compare_memory_variants(root, chapter_number=1)

    assert Path(result["json_path"]).exists()
    assert Path(result["md_path"]).exists()

    variants = result["variants"]
    assert len(variants) == 4
    assert variants[0]["variant"] == "A"
    assert variants[3]["variant"] == "D"


def test_compare_memory_variants_d_has_more_than_a(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _full_pipeline_ch1_to_ch2(root, tmp_path)

    result = compare_memory_variants(root, chapter_number=1)

    a = result["variants"][0]
    d = result["variants"][3]

    # D should have at least as much as A, often more
    assert len(d["constraints"]) >= len(a["constraints"])
    assert len(d["forbidden"]) >= len(a["forbidden"])


def test_compare_memory_variants_missing_files(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _commit_chapter_1(root)

    result = compare_memory_variants(root, chapter_number=1)

    assert len(result["missing_files"]) > 0
    assert Path(result["json_path"]).exists()


def test_compare_memory_variants_md_sections(tmp_path: Path) -> None:
    root = _init(tmp_path)
    _full_pipeline_ch1_to_ch2(root, tmp_path)

    result = compare_memory_variants(root, chapter_number=1)
    md = Path(result["md_path"]).read_text(encoding="utf-8")

    assert "记忆变体比较" in md
    assert "变体 A" in md
    assert "变体 D" in md
    assert "增量分析" in md

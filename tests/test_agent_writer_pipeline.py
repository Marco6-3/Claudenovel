from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_writer.pipeline import (
    commit_chapter,
    generate_draft,
    init_project,
    index_report,
    plan_chapter,
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

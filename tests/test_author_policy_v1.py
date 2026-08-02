from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_writer.author_policy import (
    add_author_policy_rule,
    author_policy_path,
    import_author_policy_bundle,
    load_author_policy,
    render_author_policy,
)
from agent_writer.context_scorer import build_context_score_prompt, scorecard_path
from agent_writer.models import (
    AuthorPolicyRule,
    ContextScoreDimension,
    ContextualScorecard,
)
from agent_writer.novel_state import compile_chapter_context
from agent_writer.pipeline import (
    commit_chapter,
    init_project,
    plan_chapter,
    review_chapter,
    write_chapter_prompt,
)
from agent_writer.storage import sha256_file, sha256_text, write_json_atomic


DIMENSIONS = [
    "contract_fidelity",
    "boundary_continuity",
    "character_state_and_knowledge",
    "timeline_and_causality",
    "world_rule_resource_and_injury",
    "relationship_and_open_threads",
    "style_and_voice",
    "payoff_and_readability",
]


def _init(root: Path) -> None:
    init_project(
        root,
        name="测试小说",
        genre="校园修仙",
        premise="高三学生面对传承造成的身体变化",
        target_reader="男频读者",
    )


def test_policy_bundle_is_idempotent_and_role_filtered(tmp_path: Path) -> None:
    _init(tmp_path)
    bundle = tmp_path / "policy_bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "schema_version": "author-policy-bundle/v1",
                "source_label": "author feedback",
                "rules": [
                    {
                        "rule_id": "tone.no_food_metaphor",
                        "category": "style_and_tone",
                        "instruction": "严肃场景避免喜剧食物比喻。",
                        "severity": "risk",
                        "applies_to": ["writer", "scorer"],
                        "avoid_examples": ["红烧肉"],
                        "source_refs": ["author-feedback-001"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    first = import_author_policy_bundle(tmp_path, bundle)
    second = import_author_policy_bundle(tmp_path, bundle)

    assert first.revision == 1
    assert second.revision == 1
    assert "红烧肉" in render_author_policy(tmp_path, role="writer")
    assert "红烧肉" not in render_author_policy(tmp_path, role="planner")


def test_writer_and_scorer_prompts_include_their_author_policy(tmp_path: Path) -> None:
    _init(tmp_path)
    add_author_policy_rule(
        tmp_path,
        AuthorPolicyRule(
            rule_id="direction.body_change",
            category="narrative_direction",
            instruction="优先写身体变化和高三现实压力。",
            severity="blocking",
            applies_to=["writer", "scorer"],
        ),
    )
    plan_chapter(
        tmp_path,
        chapter_number=1,
        title="伤口",
        goal="主角处理左手伤势",
        external_idea="主角在课堂记录身体异常",
        idea_locks=["课堂记录身体异常"],
        required_payoffs=["课堂记录身体异常"],
        ending_hook="异常间隔缩短",
    )
    draft = tmp_path / "drafts" / "chapter_0001_draft.md"
    draft.write_text("课堂记录身体异常。\n\n异常间隔缩短", encoding="utf-8")

    writer_prompt = Path(
        write_chapter_prompt(tmp_path, chapter_number=1)["prompt"]
    ).read_text(encoding="utf-8")
    scorer_prompt, _, _ = build_context_score_prompt(tmp_path, chapter_number=1)

    assert "作者反馈策略（author_locked）" in writer_prompt
    assert "优先写身体变化和高三现实压力" in writer_prompt
    assert "优先写身体变化和高三现实压力" in scorer_prompt


def test_policy_change_invalidates_existing_contextual_score(tmp_path: Path) -> None:
    _init(tmp_path)
    plan_chapter(
        tmp_path,
        chapter_number=1,
        title="记录",
        goal="完成一次异常记录",
        external_idea="主角记录左手发热",
        idea_locks=["记录左手发热"],
        required_payoffs=["记录左手发热"],
        ending_hook="发热间隔缩短",
    )
    draft = tmp_path / "drafts" / "chapter_0001_draft.md"
    draft.write_text("主角记录左手发热。\n\n发热间隔缩短", encoding="utf-8")
    review = review_chapter(tmp_path, chapter_number=1)
    assert not review.blocking
    context = compile_chapter_context(tmp_path, chapter_number=1)
    profile = load_author_policy(tmp_path)
    scorecard = ContextualScorecard(
        chapter_number=1,
        model="test-scorer",
        draft_sha256=sha256_file(draft),
        context_sha256=sha256_text(context.model_dump_json()),
        state_revision=context.state_revision,
        author_policy_revision=profile.revision,
        author_policy_sha256=sha256_file(author_policy_path(tmp_path)),
        dimensions=[
            ContextScoreDimension(
                dimension=dimension,
                score=9.0,
                rationale="test",
            )
            for dimension in DIMENSIONS
        ],
        overall_score=9.0,
        blocking=False,
        confidence=0.9,
    )
    write_json_atomic(scorecard_path(tmp_path, 1), scorecard)
    add_author_policy_rule(
        tmp_path,
        AuthorPolicyRule(
            rule_id="tone.new_rule",
            category="style_and_tone",
            instruction="避免突然转为恐怖走廊。",
            applies_to=["scorer"],
        ),
    )

    with pytest.raises(ValueError, match="author policy changed"):
        commit_chapter(tmp_path, chapter_number=1, approve=True)

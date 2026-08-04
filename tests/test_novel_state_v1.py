from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_writer.context_scorer import SCORE_WEIGHTS, score_draft_with_context
from agent_writer.models import (
    ChapterEvidenceManifest,
    EvidenceRef,
    StateAddition,
    StateDelta,
    StateRecord,
)
from agent_writer.novel_state import (
    apply_state_delta,
    compile_chapter_context,
    evidence_manifest_path,
    extract_state_delta,
    load_novel_state,
)
from agent_writer.pipeline import (
    commit_chapter,
    init_project,
    plan_chapter,
    review_chapter,
    write_chapter_prompt,
)
from agent_writer.storage import read_model


def _project(tmp_path: Path) -> Path:
    init_project(
        tmp_path,
        name="状态测试书",
        genre="校园修仙",
        premise="高中生在身体变化与学业压力之间学习控制传承。",
        target_reader="都市修仙读者",
    )
    plan_chapter(
        tmp_path,
        chapter_number=1,
        title="失控的左手",
        goal="凌默在早读前处理传承反噬",
        required_payoffs=["包扎左手"],
        ending_hook="他带着伤走进教室",
        characters=["凌默"],
    )
    draft = tmp_path / "drafts" / "chapter_0001_draft.md"
    draft.write_text(
        "凌默的左手仍有灼伤，他用纱布包扎左手。\n\n七点整，他带着伤走进教室。",
        encoding="utf-8",
    )
    assert review_chapter(tmp_path, chapter_number=1).blocking is False
    commit_chapter(tmp_path, chapter_number=1, approve=True)
    return tmp_path


def _first_ref(root: Path) -> EvidenceRef:
    manifest = read_model(evidence_manifest_path(root, 1), ChapterEvidenceManifest)
    paragraph = manifest.paragraphs[0]
    return EvidenceRef(
        evidence_id=paragraph.evidence_id,
        chapter_number=1,
        paragraph_index=paragraph.paragraph_index,
        paragraph_sha256=paragraph.paragraph_sha256,
        quote="左手仍有灼伤",
    )


def _valid_delta(root: Path, *, include_proposal: bool = False) -> StateDelta:
    manifest = read_model(evidence_manifest_path(root, 1), ChapterEvidenceManifest)
    additions = [
        StateAddition(
            layer="entity_states",
            record=StateRecord(
                state_id="lingmo.left_hand_burn.ch1",
                subject="凌默",
                claim="左手伤势",
                value="仍有灼伤并已用纱布包扎",
                authority="text_confirmed",
                evidence_refs=[_first_ref(root)],
                introduced_chapter=1,
                updated_chapter=1,
                tags=["凌默", "伤势", "左手"],
            ),
        )
    ]
    if include_proposal:
        additions.append(
            StateAddition(
                layer="open_threads",
                record=StateRecord(
                    state_id="proposal.secret_enemy",
                    subject="未知敌人",
                    claim="可能正在监视凌默",
                    authority="model_proposed",
                    confidence=0.2,
                    introduced_chapter=1,
                    updated_chapter=1,
                ),
            )
        )
    return StateDelta(
        delta_id="chapter_0001-test-delta",
        chapter_number=1,
        accepted_sha256=manifest.accepted_sha256,
        source="manual",
        additions=additions,
        change_summary=["记录凌默左手伤势"],
    )


def _plan_second(root: Path) -> None:
    plan_chapter(
        root,
        chapter_number=2,
        title="课间十分钟",
        goal="凌默在不暴露传承的前提下应对同学询问",
        required_payoffs=["解释左手伤势"],
        ending_hook="纱布下再次发热",
        characters=["凌默"],
    )


def test_pending_state_blocks_next_prompt_until_verified_delta_is_applied(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _plan_second(root)

    with pytest.raises(ValueError, match="prior StateDelta is pending"):
        write_chapter_prompt(root, chapter_number=2)

    state = apply_state_delta(root, _valid_delta(root))
    prompt_info = write_chapter_prompt(root, chapter_number=2)
    prompt = Path(prompt_info["prompt"]).read_text(encoding="utf-8")

    assert state.revision == 1
    assert state.latest_state_synced_chapter == 1
    assert "仍有灼伤并已用纱布包扎" in prompt
    assert "第 1 章" in prompt


def test_state_delta_rejects_unknown_evidence_and_model_author_lock(tmp_path: Path) -> None:
    root = _project(tmp_path)
    manifest = read_model(evidence_manifest_path(root, 1), ChapterEvidenceManifest)
    bad_ref = _first_ref(root).model_copy(update={"evidence_id": "invented:CH0001-P999"})
    bad_evidence = StateDelta(
        delta_id="bad-evidence",
        chapter_number=1,
        accepted_sha256=manifest.accepted_sha256,
        source="manual",
        additions=[
            StateAddition(
                layer="canon_facts",
                record=StateRecord(
                    state_id="invented.fact",
                    subject="凌默",
                    claim="虚构事实",
                    authority="text_confirmed",
                    evidence_refs=[bad_ref],
                    introduced_chapter=1,
                    updated_chapter=1,
                ),
            )
        ],
    )
    with pytest.raises(ValueError, match="unknown evidence_id"):
        apply_state_delta(root, bad_evidence)

    model_lock = StateDelta(
        delta_id="bad-author-lock",
        chapter_number=1,
        accepted_sha256=manifest.accepted_sha256,
        source="model",
        model="fake-model",
        additions=[
            StateAddition(
                layer="authority_layer",
                record=StateRecord(
                    state_id="model.author_lock",
                    subject="剧情",
                    claim="模型自封作者意图",
                    authority="author_locked",
                    author_note="模型输出",
                    introduced_chapter=1,
                    updated_chapter=1,
                ),
            )
        ],
    )
    with pytest.raises(ValueError, match="cannot create author_locked"):
        apply_state_delta(root, model_lock)


def test_context_excludes_model_proposals_and_delta_replay_is_idempotent(tmp_path: Path) -> None:
    root = _project(tmp_path)
    delta = _valid_delta(root, include_proposal=True)
    first = apply_state_delta(root, delta)
    second = apply_state_delta(root, delta)
    context = compile_chapter_context(root, chapter_number=2)

    assert first.revision == second.revision == 1
    assert context.omitted_model_proposals == 1
    assert "proposal.secret_enemy" not in {item.record.state_id for item in context.selected_state}
    with pytest.raises(ValueError, match="cannot recommit"):
        commit_chapter(root, chapter_number=1, approve=True)


def test_api_state_extractor_forces_metadata_then_applies_verified_delta(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _project(tmp_path)
    ref = _first_ref(root)

    class FakeStateClient:
        config = type("Config", (), {"model": "fake-state-extractor"})()

        def complete(self, prompt: str, *, system: str, temperature: float, max_tokens: int) -> str:
            assert ref.evidence_id in prompt
            payload = {
                "additions": [
                    {
                        "layer": "entity_states",
                        "record": {
                            "state_id": "lingmo.left_hand_burn.api",
                            "subject": "凌默",
                            "claim": "左手伤势",
                            "value": "仍有灼伤并完成包扎",
                            "authority": "text_confirmed",
                            "evidence_refs": [ref.model_dump(mode="json")],
                            "introduced_chapter": 1,
                            "updated_chapter": 1,
                        },
                    }
                ],
                "replacements": [],
                "resolutions": [],
                "change_summary": ["记录伤势"],
            }
            return json.dumps(payload, ensure_ascii=False)

    monkeypatch.setattr("agent_writer.novel_state.build_client", lambda root, role=None: FakeStateClient())

    result = extract_state_delta(root, chapter_number=1, apply=True)

    assert result["applied"] is True
    assert result["model"] == "fake-state-extractor"
    assert load_novel_state(root).entity_states[0].authority == "text_confirmed"


def test_state_extractor_completeness_audit_adds_only_missing_evidence_bound_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _project(tmp_path)
    manifest = read_model(evidence_manifest_path(root, 1), ChapterEvidenceManifest)
    first = manifest.paragraphs[0]
    second = manifest.paragraphs[1]
    calls = 0

    class FakeStateClient:
        config = type("Config", (), {"model": "fake-state-auditor"})()

        def complete(self, prompt: str, *, system: str, temperature: float, max_tokens: int) -> str:
            nonlocal calls
            calls += 1
            if calls == 1:
                return json.dumps(
                    {
                        "additions": [
                            {
                                "layer": "entity_states",
                                "record": {
                                    "state_id": "lingmo.left_hand_burn.audit",
                                    "subject": "凌默",
                                    "claim": "左手伤势",
                                    "value": "仍有灼伤并已包扎",
                                    "authority": "text_confirmed",
                                    "evidence_refs": [
                                        {
                                            "evidence_id": first.evidence_id,
                                            "chapter_number": 1,
                                            "paragraph_index": first.paragraph_index,
                                            "paragraph_sha256": first.paragraph_sha256,
                                            "quote": "左手仍有灼伤",
                                        }
                                    ],
                                    "introduced_chapter": 1,
                                    "updated_chapter": 1,
                                },
                            }
                        ],
                        "replacements": [],
                        "resolutions": [],
                        "change_summary": ["记录伤势"],
                    },
                    ensure_ascii=False,
                )
            assert "第一遍已提取 StateDelta" in prompt
            return json.dumps(
                {
                    "missing_additions": [
                        {
                            "layer": "timeline",
                            "record": {
                                "state_id": "lingmo.school_arrival.ch1",
                                "subject": "凌默",
                                "claim": "到校时间",
                                "value": "七点整带伤走进教室",
                                "authority": "text_confirmed",
                                "evidence_refs": [
                                    {
                                        "evidence_id": second.evidence_id,
                                        "chapter_number": 1,
                                        "paragraph_index": second.paragraph_index,
                                        "paragraph_sha256": second.paragraph_sha256,
                                        "quote": "七点整",
                                    }
                                ],
                                "introduced_chapter": 1,
                                "updated_chapter": 1,
                            },
                        }
                    ],
                    "missing_replacements": [],
                    "missing_resolutions": [],
                    "audit_notes": ["补充跨章时间锚点"],
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "agent_writer.novel_state.build_client",
        lambda root, role=None: FakeStateClient(),
    )

    result = extract_state_delta(
        root,
        chapter_number=1,
        completeness_audit=True,
        apply=True,
    )

    state = load_novel_state(root)
    assert calls == 2
    assert result["completeness_audit"] is True
    assert {item.state_id for item in state.entity_states} == {
        "lingmo.left_hand_burn.audit"
    }
    assert {item.state_id for item in state.timeline} == {
        "lingmo.school_arrival.ch1"
    }
    assert Path(result["completeness_result"]).exists()


def test_contextual_scorer_uses_known_prior_evidence_and_computes_score(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _project(tmp_path)
    apply_state_delta(root, _valid_delta(root))
    _plan_second(root)
    draft = root / "drafts" / "chapter_0002_draft.md"
    draft.write_text(
        "同桌问起纱布，凌默解释左手伤势是昨夜碰伤。\n\n下课铃响时，纱布下再次发热。",
        encoding="utf-8",
    )
    ref = _first_ref(root)
    calls = 0

    class FakeScorer:
        config = type("Config", (), {"model": "fake-context-scorer"})()

        def complete(self, prompt: str, *, system: str, temperature: float, max_tokens: int) -> str:
            nonlocal calls
            calls += 1
            assert ref.evidence_id in prompt
            dimensions = []
            for name in SCORE_WEIGHTS:
                dimensions.append(
                    {
                        "dimension": name,
                        "score": 8,
                        "rationale": "正文与前文状态一致",
                        "prior_evidence_ids": [ref.evidence_id] if name == "boundary_continuity" else [],
                        "state_ids": ["lingmo.left_hand_burn.ch1"] if name == "character_state_and_knowledge" else [],
                        "draft_quotes": [
                            "不存在的模型改写引文" if calls == 1 else "纱布下再次发热"
                        ] if name == "boundary_continuity" else [],
                    }
                )
            return json.dumps(
                {"dimensions": dimensions, "issues": [], "confidence": 0.9},
                ensure_ascii=False,
            )

    monkeypatch.setattr("agent_writer.context_scorer.build_client", lambda root, role=None: FakeScorer())

    scorecard = score_draft_with_context(root, chapter_number=2)

    assert scorecard.overall_score == 8
    assert scorecard.blocking is False
    assert scorecard.confidence == 0.9
    assert len(scorecard.dimensions) == 8
    assert calls == 2
    assert (root / "reviews" / "chapter_0002_contextual_score_raw_attempt_1.txt").exists()

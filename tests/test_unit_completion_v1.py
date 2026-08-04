from __future__ import annotations

import json
from pathlib import Path

from agent_writer.models import ChapterEvidenceManifest, StateDelta
from agent_writer.novel_state import apply_state_delta, evidence_manifest_path
from agent_writer.pipeline import commit_chapter, init_project, review_chapter
from agent_writer.rolling_arc import activate_next_arc_chapter, plan_arc_with_api
from agent_writer.storage import read_model
from agent_writer.unit_completion import score_unit_completion


def test_unit_completion_scorer_uses_all_criteria_and_verified_evidence(
    tmp_path: Path,
    monkeypatch,
) -> None:
    init_project(
        tmp_path,
        name="单元完成评分测试",
        genre="校园修仙",
        premise="凌默通过记录确认图书馆与身体异常的关系。",
        target_reader="都市修仙读者",
    )

    class FakePlanner:
        config = type("Config", (), {"model": "fake-planner"})()

        def complete(self, prompt: str, *, system: str, temperature: float, max_tokens: int) -> str:
            return json.dumps(
                {
                    "beats": [
                        {
                            "chapter_number": 1,
                            "title": "门槛对照",
                            "goal": "完成一次图书馆门槛对照",
                            "required_payoffs": ["完成门槛对照"],
                            "acceptance_criteria": ["跨门槛前后红纹状态不同"],
                            "ending_hook": "凌默记录结论",
                            "focus_entities": ["凌默"],
                            "relevant_threads": [],
                            "must_preserve": [],
                            "risk_checks": [],
                            "target_chars": 1200,
                        }
                    ]
                },
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "agent_writer.rolling_arc.build_client",
        lambda root, role=None: FakePlanner(),
    )
    arc = plan_arc_with_api(
        tmp_path,
        start_chapter=1,
        horizon=1,
        target_total_chars=2000,
        objective="确认异常与图书馆相关",
        author_intent="用现实可复查记录而非恐怖氛围推进",
        target_end_state=["凌默确认门槛与红纹发热相关"],
        unit_payoffs=["完成一次门槛对照"],
        success_criteria=["结论被写入错题本"],
    )
    activate_next_arc_chapter(tmp_path)
    draft = tmp_path / "drafts" / "chapter_0001_draft.md"
    draft.write_text(
        "凌默站在门外时红纹沉寂，跨过门槛后红纹立刻发热。\n\n"
        "他完成门槛对照，把结论写进错题本。\n\n凌默记录结论。",
        encoding="utf-8",
    )
    assert review_chapter(tmp_path, chapter_number=1).blocking is False
    commit_chapter(tmp_path, chapter_number=1, approve=True)
    manifest = read_model(evidence_manifest_path(tmp_path, 1), ChapterEvidenceManifest)
    apply_state_delta(
        tmp_path,
        StateDelta(
            delta_id="unit-completion-empty",
            chapter_number=1,
            accepted_sha256=manifest.accepted_sha256,
            source="manual",
        ),
    )
    evidence_id = manifest.paragraphs[0].evidence_id
    scorer_calls = 0

    class FakeUnitScorer:
        config = type("Config", (), {"model": "fake-unit-scorer"})()

        def complete(self, prompt: str, *, system: str, temperature: float, max_tokens: int) -> str:
            nonlocal scorer_calls
            scorer_calls += 1
            assert arc.arc_id in prompt
            assessments = []
            for criterion_id in (
                "target_end_state.01",
                "unit_payoff.01",
                "success_criterion.01",
            ):
                assessments.append(
                    {
                        "criterion_id": criterion_id,
                        "status": "met",
                        "rationale": "正文以对照与记录兑现",
                        "evidence_ids": [evidence_id],
                        "unit_quote": "跨过门槛后红纹立刻发热",
                    }
                )
            return json.dumps(
                {"assessments": assessments, "confidence": 0.95},
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        "agent_writer.unit_completion.build_client",
        lambda root, role=None: FakeUnitScorer(),
    )

    scorecard = score_unit_completion(tmp_path)

    assert scorer_calls == 1
    assert scorecard.complete is True
    assert scorecard.blocking is False
    assert scorecard.completion_rate == 1
    assert len(scorecard.assessments) == 3
    assert (
        tmp_path / "arc_contracts" / f"{arc.arc_id}_completion_score.json"
    ).exists()

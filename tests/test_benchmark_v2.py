from __future__ import annotations

import json
from pathlib import Path

from agent_writer.benchmark_v2 import (
    BenchmarkPrediction,
    evaluate_benchmark,
    load_benchmark_cases,
    run_benchmark_with_api,
    score_benchmark_case,
)


SUITE = (
    Path(__file__).parents[1]
    / "benchmarks"
    / "novel_benchmark_v2"
    / "cases"
    / "synthetic_controlled_v1.jsonl"
)


def _prediction_for(case) -> BenchmarkPrediction:
    issues = [
        {
            "code": item.code,
            "severity": item.severity,
            "rationale": "命中受控问题",
            "draft_quote": case.candidate_text[:8],
            "evidence_ids": [],
        }
        for item in case.gold_issues
    ]
    facets = [
        {
            "facet": facet,
            "rationale": "本章后仍持续",
            "chapter_quote": case.candidate_text[:8],
            "evidence_ids": [],
        }
        for facet in case.gold_state_facets
    ]
    criteria = [
        {
            "criterion_id": item.criterion_id,
            "status": item.status,
            "rationale": "逐项核验",
            "unit_quote": case.candidate_text[:8]
            if item.status in {"met", "partial"}
            else "",
            "evidence_ids": [],
        }
        for item in case.gold_criteria
    ]
    return BenchmarkPrediction(
        case_id=case.case_id,
        task=case.task,
        decision=case.expected_decision,
        issues=issues,
        state_facets=facets,
        criteria=criteria,
        confidence=0.9,
        model="oracle-test",
    )


def test_synthetic_suite_contract_and_oracle_scores() -> None:
    cases = load_benchmark_cases(SUITE)

    assert len(cases) == 12
    assert {case.task for case in cases} == {
        "continuity_detection",
        "state_delta_coverage",
        "unit_completion",
    }
    for case in cases:
        score = score_benchmark_case(case, _prediction_for(case))
        assert score.decision_correct is True
        assert score.issue_fn == 0
        assert score.state_fn == 0
        assert score.invalid_citations == 0


def test_evaluator_counts_blocking_escape_and_invalid_quote(tmp_path: Path) -> None:
    case = load_benchmark_cases(SUITE)[1]
    prediction = BenchmarkPrediction(
        case_id=case.case_id,
        task=case.task,
        decision="clean",
        issues=[
            {
                "code": "state.injury_reset",
                "severity": "blocking",
                "rationale": "错误预测",
                "draft_quote": "不存在的引文",
                "evidence_ids": ["UNKNOWN"],
            }
        ],
        confidence=0.8,
        model="bad-test",
    )
    prediction_file = tmp_path / "predictions.jsonl"
    suite_file = tmp_path / "suite.jsonl"
    suite_file.write_text(
        json.dumps(case.model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    prediction_file.write_text(
        json.dumps(prediction.model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    report = evaluate_benchmark(suite_file, prediction_file)

    assert report.decision_accuracy == 0
    assert report.blocking_escape_rate == 1
    assert report.false_blocking_rate == 1
    assert report.citation_validity == 0


def test_api_runner_retries_invalid_label_and_writes_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    case = load_benchmark_cases(SUITE)[0]
    suite_file = tmp_path / "suite.jsonl"
    suite_file.write_text(
        json.dumps(case.model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    calls = 0

    class FakeClient:
        config = type("Config", (), {"model": "fake-benchmark"})()

        def complete(self, prompt: str, *, system: str, temperature: float, max_tokens: int):
            nonlocal calls
            calls += 1
            if calls == 1:
                return json.dumps(
                    {
                        "decision": "clean",
                        "issues": [
                            {
                                "code": "unknown.code",
                                "severity": "warning",
                                "rationale": "bad",
                                "draft_quote": "",
                                "evidence_ids": [],
                            }
                        ],
                        "state_facets": [],
                        "criteria": [],
                        "confidence": 0.5,
                    }
                )
            return json.dumps(
                {
                    "decision": "clean",
                    "issues": [],
                    "state_facets": [],
                    "criteria": [],
                    "confidence": 0.9,
                }
            )

    monkeypatch.setattr(
        "agent_writer.benchmark_v2.build_client",
        lambda root, role=None: FakeClient(),
    )

    report = run_benchmark_with_api(
        tmp_path,
        suite_file=suite_file,
        output_dir=tmp_path / "run",
        case_ids=[case.case_id],
    )

    assert calls == 2
    assert report.decision_accuracy == 1
    assert (tmp_path / "run" / "report.json").exists()

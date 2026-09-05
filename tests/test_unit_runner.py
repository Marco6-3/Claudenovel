from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_writer.unit_runner import (
    UnitBrief, _exclusive_run, _review_validator, _run_path, count_chars, run_unit, unit_status,
)
from agent_writer.unit_completion import _parse_assessments


def dump(value):
    return json.dumps(value, ensure_ascii=False)


PLAN = dict(causal_route="查清借书记录，再找到失物", ending_setup="借书记录提前出现", assumptions=[], author_questions=[], chapters=[
    dict(title="借书", development="发现借书记录", state_before="书丢失", resulting_change="找到借阅者线索"),
    dict(title="归还", development="按记录找到书并归还", state_before="已知借阅者", resulting_change="书归还"),
])
TEXT1 = "小林发现借书记录。她记住了最后一位借书人的名字。"
TEXT2 = "小林按记录找到那本书，把它还给管理员。管理员笑着接过了书。"


def review(*, issues=None, complete=True, questions=None, chapters=2):
    return dump(dict(complete=complete, ending_explanation="书已归还", strengths=["行动清楚"], issues=issues or [], author_questions=questions or [], goal_trace=[
        dict(stage="opening", actual_state="找书", evidence=dict(chapter=1, quote="小林")),
        dict(stage="turning_point", actual_state="有了线索", evidence=dict(chapter=1, quote="借书记录")),
        dict(stage="ending", actual_state="归还", evidence=dict(chapter=chapters, quote="小林")),
    ]))


def issue(chapter=2, quote="小林按记录", severity="major"):
    return dict(kind="causality", severity=severity, chapter=chapter, quote=quote, explanation="缺少寻找过程", repair="补写有依据的寻找动作")


class Fake:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.prompts = []
        self.config = SimpleNamespace(model="fake", base_url="https://example.test", thinking="disabled", response_format="text")

    def complete(self, prompt, **kwargs):
        self.prompts.append(prompt)
        value = self.outputs.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def setup(tmp_path, *, writer=None, critic=None, planner=None):
    brief = tmp_path / "brief.json"
    brief.write_text(dump(dict(title="归还", premise="找回图书馆丢失的书", ending="书回到管理员手里", max_chars=12000, preferred_chars=8000)), encoding="utf-8")
    context = tmp_path / "context.md"
    context.write_text("小林是图书馆志愿者。", encoding="utf-8")
    clients = dict(writer=Fake(writer if writer is not None else [TEXT1, TEXT2]), critic=Fake(critic if critic is not None else [review()]), planner=Fake(planner if planner is not None else [dump(PLAN)]))
    kwargs = dict(run_id="test", brief_file=brief, context_files=[context], clients=clients)
    return clients, kwargs


def test_entire_unit_keeps_full_context_and_never_touches_canon(tmp_path):
    accepted = tmp_path / "accepted"
    accepted.mkdir()
    canon = accepted / "chapter_0001.md"
    canon.write_bytes(b"user canon")
    clients, kwargs = setup(tmp_path)
    result = run_unit(tmp_path, **kwargs)
    assert result["status"] == "awaiting_author"
    assert result["body_chars"] == count_chars(TEXT1 + TEXT2)
    assert TEXT1 in clients["writer"].prompts[1]
    assert TEXT1 in clients["critic"].prompts[0] and TEXT2 in clients["critic"].prompts[0]
    assert canon.read_bytes() == b"user canon"
    assert not (tmp_path / "state").exists()
    assert Path(result["output"]).is_file()
    assert unit_status(tmp_path, "test")["status"] == "awaiting_author"


def test_resume_after_transport_failure_does_not_regenerate_completed_chapter(tmp_path):
    clients, kwargs = setup(tmp_path, writer=[TEXT1, RuntimeError("network")])
    with pytest.raises(RuntimeError):
        run_unit(tmp_path, **kwargs)
    assert unit_status(tmp_path, "test")["status"] == "interrupted"
    clients["writer"].outputs = [TEXT2]
    result = run_unit(tmp_path, **kwargs)
    assert result["status"] == "awaiting_author"
    assert len(clients["planner"].prompts) == 1
    assert len(clients["writer"].prompts) == 3
    assert result["calls"] == 5
    run_unit(tmp_path, **kwargs)  # terminal run is a read, no more calls
    assert len(clients["writer"].prompts) == 3


@pytest.mark.parametrize("change", ["source", "artifact", "config"])
def test_resume_rejects_changed_inputs_or_artifacts(tmp_path, change):
    _, kwargs = setup(tmp_path)
    result = run_unit(tmp_path, **kwargs)
    if change == "source":
        kwargs["context_files"][0].write_text("changed", encoding="utf-8")
    elif change == "artifact":
        Path(result["output"]).write_text("user edits", encoding="utf-8")
    else:
        kwargs["max_revision_rounds"] = 0
    with pytest.raises(ValueError, match="changed"):
        run_unit(tmp_path, **kwargs)


def test_review_quotes_must_belong_to_the_cited_chapter():
    with pytest.raises(ValueError, match="cited chapter"):
        _review_validator([TEXT1, TEXT2])(review(issues=[issue(chapter=1)]))
    assert _review_validator([TEXT1, TEXT2])(review(issues=[issue()])).issues


def test_old_completion_scorer_rejects_cross_paragraph_quote():
    payload = dump(dict(assessments=[dict(criterion_id="c1", status="met", rationale="test", evidence_ids=["P1"], unit_quote="door opened")], confidence=1))
    with pytest.raises(ValueError, match="cited evidence"):
        _parse_assessments(payload, criteria={"c1": "open"}, evidence_catalog={"P1": "he slept", "P2": "door opened"})


def test_major_issue_gets_local_revision_and_whole_unit_rereview(tmp_path):
    revised = "小林找到借书人，按他指的书架找到书，然后把它还给管理员。"
    clients, kwargs = setup(tmp_path, writer=[TEXT1, TEXT2, revised], critic=[review(issues=[issue()]), review()])
    result = run_unit(tmp_path, **kwargs)
    assert result["selected_revision"] == 1
    assert TEXT1 in clients["critic"].prompts[-1] and revised in clients["critic"].prompts[-1]
    assert TEXT1 in Path(result["output"]).read_text(encoding="utf-8")
    assert revised in Path(result["output"]).read_text(encoding="utf-8")


def test_revision_regression_keeps_original_and_flags_review(tmp_path):
    revised = "小林按记录归还图书。"
    clients, kwargs = setup(
        tmp_path, writer=[TEXT1, TEXT2, revised], critic=[review(issues=[issue()]), review(issues=[issue(), issue(quote="归还图书")], complete=False)],
    )
    result = run_unit(tmp_path, **kwargs)
    assert result["selected_revision"] == 0
    assert result["status"] == "needs_author_review"
    assert TEXT2 in Path(result["output"]).read_text(encoding="utf-8")
    assert len(clients["writer"].prompts) == 3


def test_minor_prose_notes_do_not_start_rewrite_loop(tmp_path):
    clients, kwargs = setup(tmp_path, critic=[review(issues=[{**issue(severity="minor"), "kind": "prose"}])])
    assert run_unit(tmp_path, **kwargs)["selected_revision"] == 0
    assert len(clients["writer"].prompts) == 2


def test_conflicting_author_brief_stops_before_prose(tmp_path):
    plan = {**PLAN, "author_questions": ["结局同时要求归还和永不归还，请确定。"], "author_conflicts": [dict(first_quote="书回到管理员手里", second_quote="书绝不能归还管理员", explanation="结局要求互斥") ]}
    clients, kwargs = setup(tmp_path, planner=[dump(plan)])
    payload = json.loads(kwargs["brief_file"].read_text(encoding="utf-8"))
    payload["author_locks"] = ["书绝不能归还管理员"]
    kwargs["brief_file"].write_text(dump(payload), encoding="utf-8")
    assert run_unit(tmp_path, **kwargs)["status"] == "needs_author_direction"
    assert not clients["writer"].prompts


def test_creative_blanks_are_replanned_instead_of_asking_author(tmp_path):
    plan = {**PLAN, "author_questions": ["借书人的动机是什么？"]}
    clients, kwargs = setup(tmp_path, planner=[dump(plan), dump(PLAN)])
    assert run_unit(tmp_path, **kwargs)["status"] == "awaiting_author"
    assert len(clients["planner"].prompts) == 2
    assert "普通创作留白" in clients["planner"].prompts[1]


def test_minor_fact_error_is_repaired(tmp_path):
    clients, kwargs = setup(tmp_path, writer=[TEXT1, TEXT2, TEXT2], critic=[review(issues=[issue(severity="minor")]), review()])
    assert run_unit(tmp_path, **kwargs)["selected_revision"] == 1
    assert len(clients["writer"].prompts) == 3


def test_length_overflow_is_retried_without_truncation(tmp_path):
    clients, kwargs = setup(tmp_path, writer=["字" * 12001, TEXT1, TEXT2])
    result = run_unit(tmp_path, **kwargs)
    assert result["status"] == "awaiting_author"
    assert "compress without truncating" in clients["writer"].prompts[1]
    assert (tmp_path / "drafts/units/test/responses/002_draft_01_raw.txt").read_text(encoding="utf-8") == "字" * 12001


def test_context_overflow_stops_before_network_and_does_not_discard_sources(tmp_path):
    clients, kwargs = setup(tmp_path)
    kwargs["context_files"][0].write_text("前情" * 3000, encoding="utf-8")
    with pytest.raises(ValueError, match="no input was silently discarded"):
        run_unit(tmp_path, **kwargs, max_prompt_chars=2000)
    assert not clients["planner"].prompts


def test_call_limit_and_unit_cap(tmp_path):
    _, kwargs = setup(tmp_path)
    with pytest.raises(ValueError, match="max_calls"):
        run_unit(tmp_path, **kwargs, max_calls=1)
    with pytest.raises(ValueError):
        UnitBrief(title="x", premise="y", ending="z", max_chars=30000)
    assert count_chars("一 二\n。a1") == 5


def test_run_path_and_exclusive_lock(tmp_path):
    with pytest.raises(ValueError):
        _run_path(tmp_path, "../../accepted")
    root = _run_path(tmp_path, "safe")
    with _exclusive_run(root):
        with pytest.raises(ValueError, match="another process"):
            with _exclusive_run(root):
                pass


def test_cli_exposes_the_unit_runner():
    from agent_writer.cli import build_parser
    args = build_parser().parse_args(["unit-run", "--run-id", "new", "--brief", "brief.json"])
    assert args.max_revision_rounds == 2


def test_markdown_brief_needs_no_manual_schema(tmp_path):
    clients, kwargs = setup(tmp_path, writer=[TEXT1 + TEXT2], critic=[review(chapters=1)])
    brief = tmp_path / "单元方案.md"
    brief.write_text("# 找回旧书\n\n小林找回旧书，最后把它还给管理员。", encoding="utf-8")
    kwargs["brief_file"] = brief
    result = run_unit(tmp_path, **kwargs, max_chars=1800)
    assert result["status"] == "awaiting_author"
    assert "找回旧书" in clients["planner"].prompts[0]
    assert "1800" in clients["planner"].prompts[0]
    with pytest.raises(ValueError, match="changed"):
        run_unit(tmp_path, **kwargs, max_chars=1700)


def test_reviewer_rejects_mismatched_related_evidence(tmp_path):
    bad = issue()
    bad["related_evidence"] = [dict(chapter=1, quote="管理员笑着接过了书")]
    with pytest.raises(ValueError, match="cited chapter 1"):
        _review_validator([TEXT1, TEXT2])(review(issues=[bad]))


def test_atomic_write_retries_transient_windows_sharing_failure(tmp_path, monkeypatch):
    from agent_writer import storage
    path = tmp_path / "manifest.json"
    path.write_text("old", encoding="utf-8")
    real_replace = storage.os.replace
    attempts = []

    def replace(src, dst):
        attempts.append(1)
        assert path.read_text(encoding="utf-8") == "old"
        if len(attempts) < 3:
            raise PermissionError("sharing violation")
        real_replace(src, dst)

    monkeypatch.setattr(storage.os, "replace", replace)
    monkeypatch.setattr(storage.time, "sleep", lambda _: None)
    storage.write_text_atomic(path, "new")
    assert path.read_text(encoding="utf-8") == "new"
    assert len(attempts) == 3
    assert not list(tmp_path.glob("*.tmp"))


def test_multi_chapter_revision_updates_antecedent_and_consequence(tmp_path):
    correction = issue()
    correction["repair_chapters"] = [1, 2]
    new1 = "小林在抽屉中发现借书记录，书还未找到。"
    new2 = "小林询问借书人，从指定的柜子中找到书，交给管理员。"
    clients, kwargs = setup(tmp_path, writer=[TEXT1, TEXT2, new1, new2], critic=[review(issues=[correction]), review()])
    result = run_unit(tmp_path, **kwargs)
    assert result["selected_revision"] == 1
    assert new1 in clients["writer"].prompts[-1]
    assert new2 in Path(result["output"]).read_text(encoding="utf-8")


def test_short_plan_coalescing_keeps_event_order_and_end_states():
    from agent_writer.unit_runner import UnitPlan, _coalesce_short_steps
    original = UnitPlan.model_validate({**PLAN, "chapters": [
        dict(title=str(i), development=f"event-{i}", state_before=f"before-{i}", resulting_change=f"after-{i}") for i in range(6)
    ]})
    merged = _coalesce_short_steps(original, 3200)
    assert len(merged.chapters) == 1
    assert merged.chapters[0].development == "\n".join(f"event-{i}" for i in range(6))
    assert merged.chapters[0].state_before == "before-0"
    assert merged.chapters[0].resulting_change == "after-5"
    assert len(original.chapters) == 6


def test_invalid_explicit_json_length_is_not_silently_changed(tmp_path):
    clients, kwargs = setup(tmp_path)
    brief = json.loads(kwargs["brief_file"].read_text(encoding="utf-8"))
    brief["preferred_chars"] = 12500
    kwargs["brief_file"].write_text(dump(brief), encoding="utf-8")
    with pytest.raises(ValueError, match="preferred_chars"):
        run_unit(tmp_path, **kwargs)
    assert not clients["planner"].prompts


def test_paragraph_ids_resolve_to_source_without_model_copying():
    payload = json.loads(review())
    for entry in payload["goal_trace"]:
        chapter = entry["evidence"]["chapter"]
        entry["evidence"] = dict(chapter=chapter, paragraph_id=f"C{chapter:02d}P0001")
    checked = _review_validator([TEXT1, TEXT2])(dump(payload))
    assert checked.goal_trace[0].evidence.quote == TEXT1
    assert checked.goal_trace[-1].evidence.quote == TEXT2
    payload["goal_trace"][0]["evidence"]["paragraph_id"] = "C02P0001"
    with pytest.raises(ValueError, match="paragraph_id"):
        _review_validator([TEXT1, TEXT2])(dump(payload))


def test_emotional_observations_require_real_evidence():
    payload = json.loads(review())
    payload["reading_observations"] = [dict(focus="emotional_effect", observation="具体回应改变关系", evidence=[dict(chapter=2, paragraph_id="C02P0001")])]
    assert _review_validator([TEXT1, TEXT2])(dump(payload)).reading_observations[0].evidence[0].quote == TEXT2
    payload["reading_observations"][0]["evidence"][0]["chapter"] = 1
    with pytest.raises(ValueError, match="paragraph_id"):
        _review_validator([TEXT1, TEXT2])(dump(payload))


def test_from_run_reuses_full_draft_and_does_not_modify_original(tmp_path):
    clients, kwargs = setup(tmp_path)
    old = run_unit(tmp_path, **kwargs)
    original = Path(old["output"])
    old_bytes = original.read_bytes()
    clients["critic"].outputs = [review()]
    kwargs["run_id"] = "review-again"
    result = run_unit(tmp_path, **kwargs, from_run=original.parent)
    assert result["calls"] == 1
    assert len(clients["planner"].prompts) == 1
    assert len(clients["writer"].prompts) == 2
    assert original.read_bytes() == old_bytes
    assert Path(result["output"]).read_bytes() == old_bytes


def test_from_run_rejects_tampered_chapter(tmp_path):
    _, kwargs = setup(tmp_path)
    old = run_unit(tmp_path, **kwargs)
    root = Path(old["output"]).parent
    (root / "chapters/v0/01.md").write_text("changed", encoding="utf-8")
    kwargs["run_id"] = "new"
    with pytest.raises(ValueError, match="from-run artifact changed"):
        run_unit(tmp_path, **kwargs, from_run=root)


def test_author_revision_survives_resume_and_remains_in_later_reviews(tmp_path):
    clients, kwargs = setup(tmp_path)
    original = Path(run_unit(tmp_path, **kwargs)["output"])
    original_bytes = original.read_bytes()
    note = tmp_path / "author.md"
    note.write_text("减少解释，增加互动。", encoding="utf-8")
    clients["writer"].outputs = [TEXT1 + "小林问了管理员。", RuntimeError("network")]
    kwargs["run_id"] = "author-edit"
    kwargs.update(from_run=original.parent, revision_note_file=note)
    with pytest.raises(RuntimeError):
        run_unit(tmp_path, **kwargs)
    clients["writer"].outputs = [TEXT2]
    clients["critic"].outputs = [review()]
    result = run_unit(tmp_path, **kwargs)
    revised_root = Path(result["output"]).parent
    assert result["calls"] == 4  # first edit, failed edit, resumed edit, review
    assert TEXT2 not in clients["writer"].prompts[2]  # future draft is not writer context
    assert TEXT1 + "小林问了管理员。" in clients["writer"].prompts[3]
    assert "减少解释，增加互动" in clients["critic"].prompts[-1]
    assert (revised_root / "versions/seed.md").read_bytes() == original_bytes
    assert original.read_bytes() == original_bytes
    kwargs.update(run_id="review-edited", from_run=revised_root, revision_note_file=None)
    clients["critic"].outputs = [review()]
    assert run_unit(tmp_path, **kwargs)["calls"] == 1
    assert "减少解释，增加互动" in clients["critic"].prompts[-1]


def test_leading_title_is_normalized_without_discarding_prose(tmp_path):
    clients, kwargs = setup(tmp_path, writer=["# 借书\n\n" + TEXT1, TEXT2])
    result = run_unit(tmp_path, **kwargs)
    assert result["body_chars"] == count_chars(TEXT1 + TEXT2)
    root = Path(result["output"]).parent
    assert (root / "chapters/v0/01.md").read_text(encoding="utf-8") == TEXT1
    assert (root / "responses/002_draft_01_raw.txt").read_text(encoding="utf-8").startswith("# 借书")
    assert len(clients["writer"].prompts) == 2

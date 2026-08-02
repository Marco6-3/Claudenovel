from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_writer.author_policy import add_author_policy_rule
from agent_writer.models import AuthorPolicyRule
from agent_writer.pipeline import init_project
from agent_writer.unit_branch import (
    audit_unit_branch_diversity,
    generate_unit_branches,
    select_unit_branch,
)


def _init(root: Path) -> None:
    init_project(
        root,
        name="分支测试",
        genre="校园修仙",
        premise="高三学生记录身体变化",
        target_reader="男频读者",
    )


class FakeBranchPlanner:
    def __init__(self, *, same_fingerprint: bool = False):
        self.config = SimpleNamespace(model="fake-planner")
        self.same_fingerprint = same_fingerprint

    def complete(self, prompt: str, **kwargs) -> str:
        if "本路线角色：mechanism" in prompt:
            profile = "mechanism"
            title = "体温试验"
            axes = ["教室", "发热提前", "控制变量", "主动停笔测试", "成绩波动", "记录出现规律"]
        elif "本路线角色：character" in prompt:
            profile = "character"
            title = "同桌追问"
            axes = ["同桌关系", "纱布被问", "有限坦白", "拒绝校医检查", "信任受损", "同桌保留疑问"]
        else:
            profile = "evidence"
            title = "借阅记录"
            axes = ["学校图书馆", "借阅时间异常", "旧记录对照", "核对闭馆日志", "暴露行踪", "发现固定书架"]
        if self.same_fingerprint:
            axes = ["教室", "发热提前", "控制变量", "主动停笔测试", "成绩波动", "记录出现规律"]
        payload = {
            "unit_title": title,
            "approach_summary": f"{profile}路线",
            "distinctive_choice": f"采用{profile}因果",
            "fingerprint": dict(
                zip(
                    [
                        "conflict_space",
                        "trigger",
                        "core_mechanism",
                        "climax_action",
                        "cost_type",
                        "end_hook",
                    ],
                    axes,
                )
            ),
            "beats": [
                {
                    "chapter_number": 2,
                    "title": title,
                    "goal": f"完成{profile}路线的第一次验证",
                    "required_payoffs": ["完成首次验证"],
                    "acceptance_criteria": ["主角主动执行并记录结果"],
                    "ending_hook": axes[-1],
                    "focus_entities": ["凌默"],
                    "relevant_threads": [],
                    "must_preserve": ["左手仍包扎"],
                    "risk_checks": ["不得转成恐怖探险"],
                    "target_chars": 1800,
                }
            ],
        }
        return json.dumps(payload, ensure_ascii=False)


class FakeDiversityJudge:
    def __init__(self):
        self.config = SimpleNamespace(model="fake-diversity-judge")

    def complete(self, prompt: str, **kwargs) -> str:
        pairs = []
        ids = ["branch_01_mechanism", "branch_02_character", "branch_03_evidence"]
        for index, left in enumerate(ids):
            for right in ids[index + 1 :]:
                pairs.append(
                    {
                        "branch_a": left,
                        "branch_b": right,
                        "axes": {
                            "conflict_space": False,
                            "trigger": False,
                            "core_mechanism": False,
                            "climax_action": False,
                            "cost_type": False,
                            "end_hook": False,
                        },
                        "rationale": "三条路线的因果机制相同。",
                    }
                )
        return json.dumps({"pairs": pairs}, ensure_ascii=False)


def test_generate_and_select_diverse_unit_branches(tmp_path: Path, monkeypatch) -> None:
    _init(tmp_path)
    monkeypatch.setattr(
        "agent_writer.unit_branch.build_client",
        lambda root, role=None: FakeBranchPlanner(),
    )

    branch_set = generate_unit_branches(
        tmp_path,
        start_chapter=2,
        target_total_chars=8000,
        objective="凌默建立身体变化监测方法",
        author_intent="突出高三现实压力，不写恐怖探险",
        freedom_axes=["conflict_space", "core_mechanism", "cost_type"],
        author_locks=["身体变化是主线"],
        semantic_diversity=False,
    )

    assert len(branch_set.candidates) == 3
    assert not branch_set.blocking
    assert all(pair.difference_count == 6 and pair.passes for pair in branch_set.diversity_pairs)
    arc = select_unit_branch(tmp_path, branch_id="branch_02_character")
    assert arc.unit_title == "同桌追问"
    assert arc.author_intent == "突出高三现实压力，不写恐怖探险"
    assert arc.horizon == 1


def test_identical_event_fingerprints_block_selection(tmp_path: Path, monkeypatch) -> None:
    _init(tmp_path)
    monkeypatch.setattr(
        "agent_writer.unit_branch.build_client",
        lambda root, role=None: FakeBranchPlanner(same_fingerprint=True),
    )

    branch_set = generate_unit_branches(
        tmp_path,
        start_chapter=2,
        target_total_chars=8000,
        objective="建立监测方法",
        author_intent="突出身体变化",
        freedom_axes=["conflict_space", "core_mechanism", "cost_type"],
        semantic_diversity=False,
    )

    assert branch_set.blocking
    assert all(pair.difference_count == 0 for pair in branch_set.diversity_pairs)
    with pytest.raises(ValueError, match="six-axis diversity"):
        select_unit_branch(tmp_path, branch_id="branch_01_mechanism")


def test_policy_change_after_branch_generation_requires_regeneration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _init(tmp_path)
    monkeypatch.setattr(
        "agent_writer.unit_branch.build_client",
        lambda root, role=None: FakeBranchPlanner(),
    )
    generate_unit_branches(
        tmp_path,
        start_chapter=2,
        target_total_chars=8000,
        objective="建立监测方法",
        author_intent="突出身体变化",
        freedom_axes=["conflict_space", "core_mechanism", "cost_type"],
        semantic_diversity=False,
    )
    add_author_policy_rule(
        tmp_path,
        AuthorPolicyRule(
            rule_id="direction.changed",
            category="narrative_direction",
            instruction="新增作者方向。",
            applies_to=["planner"],
        ),
    )

    with pytest.raises(ValueError, match="AuthorPolicy changed"):
        select_unit_branch(tmp_path, branch_id="branch_01_mechanism")


def test_semantic_diversity_audit_overrides_lexical_axis_difference(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _init(tmp_path)
    monkeypatch.setattr(
        "agent_writer.unit_branch.build_client",
        lambda root, role=None: FakeBranchPlanner(),
    )
    lexical = generate_unit_branches(
        tmp_path,
        start_chapter=2,
        target_total_chars=8000,
        objective="建立监测方法",
        author_intent="突出身体变化",
        freedom_axes=["conflict_space", "core_mechanism", "cost_type"],
        semantic_diversity=False,
    )
    assert all(pair.difference_count == 6 for pair in lexical.diversity_pairs)
    monkeypatch.setattr(
        "agent_writer.unit_branch.build_client",
        lambda root, role=None: FakeDiversityJudge(),
    )

    audited = audit_unit_branch_diversity(tmp_path)

    assert audited.diversity_order_consistent
    assert audited.blocking
    assert all(pair.semantic_difference_count == 0 for pair in audited.diversity_pairs)
    assert all(not pair.passes for pair in audited.diversity_pairs)


def test_branch_first_requires_three_author_open_axes(tmp_path: Path) -> None:
    _init(tmp_path)

    with pytest.raises(ValueError, match="at least three author-open freedom axes"):
        generate_unit_branches(
            tmp_path,
            start_chapter=2,
            target_total_chars=8000,
            objective="建立监测方法",
            author_intent="核心机制已经锁定",
            freedom_axes=["cost_type", "end_hook"],
            semantic_diversity=False,
        )

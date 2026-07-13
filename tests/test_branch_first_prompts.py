from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "branch_first_v1" / "prepare_branch_prompts.py"
SPEC = importlib.util.spec_from_file_location("prepare_branch_prompts", MODULE_PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_prepare_branch_prompts_keeps_each_planner_isolated(tmp_path: Path) -> None:
    public_run = tmp_path / "public"
    case_dir = public_run / "case_x" / "public"
    case_dir.mkdir(parents=True)
    (case_dir / "writer_prompt.md").write_text("VISIBLE-CONTEXT", encoding="utf-8")
    (case_dir / "idea_contract.json").write_text(
        json.dumps({"id": "case_x", "idea_locks": ["LOCK"], "forbidden_changes": ["NOPE"]}),
        encoding="utf-8",
    )

    out_dir = tmp_path / "out"
    written = module.prepare(public_run, out_dir, ["case_x"])

    assert len(written) == 3
    branch_two = (out_dir / "case_x" / "planner_prompts" / "branch_02.md").read_text(encoding="utf-8")
    assert "VISIBLE-CONTEXT" in branch_two
    assert "不得用突然得到的新物品" in branch_two
    assert "其他分支卡" in branch_two
    assert "branch_02" in branch_two

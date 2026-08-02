from __future__ import annotations

import json
from pathlib import Path
import sys

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from agent_writer.author_policy import import_author_policy_bundle
from agent_writer.pipeline import init_project
from agent_writer.unit_branch import generate_unit_branches


EXPERIMENT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = EXPERIMENT_ROOT / "unit_branch_demo_project"


def main() -> None:
    intent = json.loads(
        (EXPERIMENT_ROOT / "unit_branch_demo_intent.json").read_text(encoding="utf-8")
    )
    if not (PROJECT_ROOT / "story_bible" / "writer_strategy.json").exists():
        init_project(PROJECT_ROOT, **intent["project"])
    import_author_policy_bundle(
        PROJECT_ROOT,
        EXPERIMENT_ROOT / "author_policy_seed.json",
    )
    branch_set = generate_unit_branches(
        PROJECT_ROOT,
        start_chapter=int(intent["start_chapter"]),
        target_total_chars=int(intent["target_total_chars"]),
        objective=str(intent["objective"]),
        author_intent=str(intent["author_intent"]),
        freedom_axes=list(intent["branch_freedom_axes"]),
        entry_state=list(intent["entry_state"]),
        target_end_state=list(intent["target_end_state"]),
        unit_payoffs=list(intent["unit_payoffs"]),
        author_locks=list(intent["author_locks"]),
        forbidden_changes=list(intent["forbidden_changes"]),
        success_criteria=list(intent["success_criteria"]),
    )
    print(branch_set.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

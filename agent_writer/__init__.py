"""External-idea-first, file-audited single-unit writing system."""

from .pipeline import (
    commit_chapter,
    generate_best_of_n,
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
from .context_scorer import score_draft_with_context
from .author_policy import (
    add_author_policy_rule,
    import_author_policy_bundle,
    load_author_policy,
)
from .novel_state import (
    apply_state_delta,
    compile_chapter_context,
    extract_state_delta,
    load_novel_state,
)
from .rolling_arc import (
    advance_rolling_arc,
    arc_status,
    plan_arc_with_api,
    review_arc_contract,
    replan_arc_with_api,
)
from .unit_branch import (
    audit_unit_branch_diversity,
    generate_unit_branches,
    load_unit_branch_set,
    select_unit_branch,
)

__all__ = [
    "commit_chapter",
    "generate_best_of_n",
    "generate_draft",
    "init_project",
    "index_report",
    "plan_chapter",
    "review_chapter",
    "rewrite_draft",
    "status_report",
    "write_chapter_prompt",
    "write_rewrite_brief",
    "apply_state_delta",
    "compile_chapter_context",
    "extract_state_delta",
    "load_novel_state",
    "score_draft_with_context",
    "add_author_policy_rule",
    "import_author_policy_bundle",
    "load_author_policy",
    "advance_rolling_arc",
    "arc_status",
    "plan_arc_with_api",
    "review_arc_contract",
    "replan_arc_with_api",
    "generate_unit_branches",
    "load_unit_branch_set",
    "select_unit_branch",
    "audit_unit_branch_diversity",
]

"""Independent file-first Chinese novel agent writing system."""

from .nl_intent import parse_nl_intent
from .nl_orchestrator import execute_nl_request
from .pipeline import (
    commit_chapter,
    compare_memory_variants,
    draft_author_note,
    evaluate_workflow,
    generate_discussion_packet,
    generate_draft,
    generate_handoff,
    init_project,
    index_report,
    plan_chapter,
    plan_next_chapter,
    record_author_note,
    review_chapter,
    rewrite_draft,
    status_report,
    write_chapter_prompt,
    write_rewrite_brief,
)

__all__ = [
    "commit_chapter",
    "compare_memory_variants",
    "execute_nl_request",
    "draft_author_note",
    "evaluate_workflow",
    "generate_discussion_packet",
    "generate_draft",
    "generate_handoff",
    "init_project",
    "index_report",
    "plan_chapter",
    "parse_nl_intent",
    "plan_next_chapter",
    "record_author_note",
    "review_chapter",
    "rewrite_draft",
    "status_report",
    "write_chapter_prompt",
    "write_rewrite_brief",
]

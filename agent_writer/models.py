from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AuthorStrategy(StrictModel):
    project_name: str
    genre: str
    premise: str
    target_reader: str
    core_hook: str
    market_position: str = ""
    style_fingerprint: list[str] = Field(default_factory=list)
    relationship_policy: list[str] = Field(default_factory=list)
    system_rule_policy: list[str] = Field(default_factory=list)
    forbidden_moves: list[str] = Field(default_factory=list)


class ReaderExpectationMap(StrictModel):
    target_reader: str
    promised_rewards: list[str] = Field(default_factory=list)
    cool_point_cycle: list[str] = Field(default_factory=list)
    hook_policy: list[str] = Field(default_factory=list)
    taboo: list[str] = Field(default_factory=list)


class CharacterConstraint(StrictModel):
    name: str
    current_stage: str = ""
    motivation: str = ""
    allowed_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    voice_rules: list[str] = Field(default_factory=list)
    ooc_red_lines: list[str] = Field(default_factory=list)


class CharacterConstraints(StrictModel):
    chapter_number: int
    characters: list[CharacterConstraint] = Field(default_factory=list)


class ChapterContract(StrictModel):
    chapter_number: int
    title: str
    target_length: str = "2500-4000"
    previous_handoff: str = ""
    main_goal: str
    required_payoffs: list[str] = Field(default_factory=list)
    forbidden_beats: list[str] = Field(default_factory=list)
    cool_point: str = ""
    relation_delta: str = ""
    foreshadowing_ops: list[str] = Field(default_factory=list)
    ending_hook: str
    allowed_system_changes: list[str] = Field(default_factory=list)
    allowed_sources: list[str] = Field(default_factory=list)

    @field_validator("required_payoffs")
    @classmethod
    def require_payoff(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("chapter contract requires at least one payoff")
        return value


class PrewritePlan(StrictModel):
    chapter_number: int
    focus: str
    main_conflict: str
    scene_order: list[str] = Field(default_factory=list)
    must_include: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)
    ending_strategy: str


class ReviewIssue(StrictModel):
    code: str
    severity: Literal["blocking", "risk", "warning"]
    message: str
    evidence: str = ""
    repair_hint: str = ""


class ReviewResult(StrictModel):
    chapter_number: int
    ok: bool
    blocking: bool
    issues: list[ReviewIssue] = Field(default_factory=list)
    rewrite_instructions: list[str] = Field(default_factory=list)
    reviewed_at: str = Field(default_factory=utc_now_iso)


class ChapterCommit(StrictModel):
    chapter_number: int
    status: Literal["accepted"]
    accepted_at: str = Field(default_factory=utc_now_iso)
    accepted_file: str
    review_file: str
    contract_file: str
    state_updates: dict[str, object] = Field(default_factory=dict)


# --- Author memory models ---


class AuthorDecision(StrictModel):
    """Author's confirmed decisions about a committed chapter."""
    chapter_number: int
    keep_chapter: bool = True
    keep_reason: str = ""
    modifications: list[str] = Field(default_factory=list)
    next_chapter_preferences: list[str] = Field(default_factory=list)
    forbidden_directions: list[str] = Field(default_factory=list)
    relationship_changes: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    notes: str = ""
    confirmed_at: str = Field(default_factory=utc_now_iso)


class FutureDirection(StrictModel):
    """A potential future story direction, prioritized and tracked."""
    id: str
    description: str
    priority: Literal["high", "medium", "low"] = "medium"
    source_chapter: int
    status: Literal["active", "adopted", "abandoned"] = "active"
    reason: str = ""
    created_at: str = Field(default_factory=utc_now_iso)


class ForeshadowingItem(StrictModel):
    """A foreshadowing element with lifecycle tracking. Append-only."""
    id: str
    content: str
    planted_chapter: int
    expected_resolution_chapter: int | None = None
    layer: Literal["主线", "支线", "氛围"] = "支线"
    status: Literal["active", "resolved", "abandoned"] = "active"
    resolution_chapter: int | None = None
    resolution_note: str = ""
    created_at: str = Field(default_factory=utc_now_iso)


class ChapterHandoff(StrictModel):
    """Context package passed from one chapter to the next."""
    from_chapter: int
    to_chapter: int
    summary: str
    character_states: dict[str, str] = Field(default_factory=dict)
    unresolved_questions: list[str] = Field(default_factory=list)
    active_foreshadowing: list[str] = Field(default_factory=list)
    required_payoffs_next: list[str] = Field(default_factory=list)
    hard_constraints: list[str] = Field(default_factory=list)
    hard_constraint_evidence: list[str] = Field(default_factory=list)
    author_direction: str = ""
    author_direction_evidence: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class ForeshadowingCandidate(StrictModel):
    """A foreshadowing item suggested by analysis, not yet confirmed."""
    id: str
    content: str
    evidence_refs: list[str] = Field(default_factory=list)
    layer: Literal["主线", "支线", "氛围"] = "支线"
    suggested_action: Literal["continue", "resolve", "abandon"] = "continue"
    reason: str = ""


class DecisionCandidate(StrictModel):
    """Analysis-derived candidate for author decisions. Not written to state until confirmed."""
    chapter_number: int

    # Retain / modify
    keep_chapter: bool = True
    keep_reason: str = ""
    keep_evidence: list[str] = Field(default_factory=list)

    modifications: list[str] = Field(default_factory=list)
    modification_evidence: list[str] = Field(default_factory=list)

    # Next chapter directions
    next_chapter_preferences: list[str] = Field(default_factory=list)
    preference_evidence: list[str] = Field(default_factory=list)

    # Forbidden directions
    forbidden_directions: list[str] = Field(default_factory=list)
    forbidden_evidence: list[str] = Field(default_factory=list)

    # Foreshadowing
    foreshadowing_active: list[ForeshadowingCandidate] = Field(default_factory=list)
    foreshadowing_recyclable: list[ForeshadowingCandidate] = Field(default_factory=list)

    # Character / relationship
    character_state_candidates: dict[str, str] = Field(default_factory=dict)
    relationship_changes: list[str] = Field(default_factory=list)
    relationship_evidence: list[str] = Field(default_factory=list)

    # Payoffs for next chapter
    required_payoffs_next: list[str] = Field(default_factory=list)

    notes: str = ""
    source_files: list[str] = Field(default_factory=list)
    generated_at: str = Field(default_factory=utc_now_iso)


class WorkflowEvaluationItem(StrictModel):
    """A single check result in a workflow evaluation."""
    check_id: str
    name: str
    status: Literal["pass", "risk", "fail", "skip"]
    detail: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class WorkflowEvaluation(StrictModel):
    """Full evaluation of the author-memory workflow for a chapter."""
    chapter_number: int
    checks: list[WorkflowEvaluationItem] = Field(default_factory=list)
    pass_count: int = 0
    risk_count: int = 0
    fail_count: int = 0
    skip_count: int = 0
    missing_files: list[str] = Field(default_factory=list)
    evaluated_at: str = Field(default_factory=utc_now_iso)

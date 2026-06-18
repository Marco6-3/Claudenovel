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


# --- Story outline models ---


class ChapterOutlineItem(StrictModel):
    """Author-editable chapter outline used to generate a chapter contract."""
    chapter_number: int
    title: str
    goal: str
    required_payoffs: list[str] = Field(default_factory=list)
    conflict: str = ""
    time_anchor: str = ""
    scene_beats: list[str] = Field(default_factory=list)
    must_include: list[str] = Field(default_factory=list)
    forbidden_beats: list[str] = Field(default_factory=list)
    ending_hook: str
    characters: list[str] = Field(default_factory=list)
    status: Literal["planned", "contracted", "drafted", "accepted", "revised"] = "planned"

    @field_validator("required_payoffs")
    @classmethod
    def require_outline_payoff(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("chapter outline requires at least one payoff")
        return value


class VolumeOutline(StrictModel):
    """Volume-level outline. It is coarse enough for author edits and concrete enough for planning."""
    volume_number: int
    title: str
    chapter_start: int
    chapter_end: int
    core_conflict: str
    climax: str
    timeline: list[str] = Field(default_factory=list)
    foreshadowing_plan: list[str] = Field(default_factory=list)
    chapters: list[ChapterOutlineItem] = Field(default_factory=list)


class StoryOutline(StrictModel):
    """Project-level story bible and outline owned by Claudenovel."""
    project_name: str
    genre: str
    target_reader: str
    logline: str
    theme: str = ""
    global_rules: list[str] = Field(default_factory=list)
    major_characters: list[str] = Field(default_factory=list)
    volumes: list[VolumeOutline] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now_iso)


class OutlineRevision(StrictModel):
    """Author-confirmed outline changes. Applied explicitly and kept as a revision log."""
    revision_id: str = ""
    reason: str = ""
    global_rules: list[str] = Field(default_factory=list)
    major_characters: list[str] = Field(default_factory=list)
    forbidden_directions: list[str] = Field(default_factory=list)
    chapter_updates: list[ChapterOutlineItem] = Field(default_factory=list)
    notes: str = ""
    created_at: str = Field(default_factory=utc_now_iso)


# --- Author memory models ---


class ForeshadowingDecision(StrictModel):
    """Author-confirmed foreshadowing operation written to the append-only ledger."""
    action: Literal["add", "continue", "resolve", "abandon"] = "continue"
    content: str
    id: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    layer: Literal["主线", "支线", "氛围"] = "支线"
    expected_resolution_chapter: int | None = None
    resolution_note: str = ""


class AuthorDecision(StrictModel):
    """Author's confirmed decisions about a committed chapter."""
    chapter_number: int
    keep_chapter: bool = True
    keep_reason: str = ""
    modifications: list[str] = Field(default_factory=list)
    next_chapter_preferences: list[str] = Field(default_factory=list)
    forbidden_directions: list[str] = Field(default_factory=list)
    relationship_changes: list[str] = Field(default_factory=list)
    foreshadowing_decisions: list[ForeshadowingDecision] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    source: Literal["analysis_derived", "author_confirmed"] = "analysis_derived"
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
    quality_warnings: list[str] = Field(default_factory=list)
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

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


AuthorPolicyCategory = Literal[
    "narrative_direction",
    "style_and_tone",
    "continuity",
    "revision_scope",
    "unit_planning",
    "evaluation",
]
AuthorPolicyTarget = Literal["planner", "writer", "scorer", "rewriter"]
AuthorPolicySeverity = Literal["blocking", "risk", "preference"]


class AuthorPolicyRule(StrictModel):
    rule_id: str
    category: AuthorPolicyCategory
    instruction: str
    severity: AuthorPolicySeverity = "risk"
    applies_to: list[AuthorPolicyTarget] = Field(
        default_factory=lambda: ["planner", "writer", "scorer", "rewriter"]
    )
    rationale: str = ""
    avoid_examples: list[str] = Field(default_factory=list)
    preferred_examples: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    authority: Literal["author_locked"] = "author_locked"
    active: bool = True
    created_at: str = Field(default_factory=utc_now_iso)

    @field_validator("rule_id", "instruction")
    @classmethod
    def require_policy_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("author policy rule_id and instruction must not be empty")
        return value

    @field_validator("applies_to")
    @classmethod
    def require_policy_target(cls, value: list[AuthorPolicyTarget]) -> list[AuthorPolicyTarget]:
        unique = list(dict.fromkeys(value))
        if not unique:
            raise ValueError("author policy must apply to at least one role")
        return unique


class AuthorPolicyProfile(StrictModel):
    schema_version: Literal["author-policy/v1"] = "author-policy/v1"
    project_id: str
    revision: int = Field(default=0, ge=0)
    rules: list[AuthorPolicyRule] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now_iso)

    @model_validator(mode="after")
    def require_unique_rule_ids(self) -> "AuthorPolicyProfile":
        ids = [rule.rule_id for rule in self.rules]
        if len(ids) != len(set(ids)):
            raise ValueError("author policy rule_id values must be unique")
        return self


class AuthorPolicyBundle(StrictModel):
    schema_version: Literal["author-policy-bundle/v1"] = "author-policy-bundle/v1"
    source_label: str
    rules: list[AuthorPolicyRule]

    @field_validator("source_label")
    @classmethod
    def require_source_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("author policy bundle requires source_label")
        return value


class IdeaContract(StrictModel):
    source_kind: Literal["human", "external"] = "human"
    source_text: str
    idea_locks: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    freedom_budget: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)

    @field_validator("source_text")
    @classmethod
    def require_source_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("idea contract requires source_text")
        return value.strip()

    @field_validator("idea_locks")
    @classmethod
    def require_idea_lock(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("idea contract requires at least one idea lock")
        return cleaned


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


class UnitContract(StrictModel):
    chapter_number: int
    title: str
    target_length: str = "2500-4000"
    idea_contract: IdeaContract
    main_goal: str
    required_payoffs: list[str] = Field(default_factory=list)
    forbidden_beats: list[str] = Field(default_factory=list)
    cool_point: str = ""
    ending_mode: Literal["closed", "resonant", "open"] = "resonant"
    ending_hook: str
    allowed_system_changes: list[str] = Field(default_factory=list)
    arc_id: str = ""
    arc_beat_index: int | None = Field(default=None, ge=0)
    planning_state_revision: int | None = Field(default=None, ge=0)
    arc_author_locks: list[str] = Field(default_factory=list)
    arc_beat_constraints: list[str] = Field(default_factory=list)

    @field_validator("required_payoffs")
    @classmethod
    def require_payoff(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("chapter contract requires at least one payoff")
        return value


# Transitional import alias. Persisted contracts and the default workflow are
# single units; the old name remains import-compatible for callers.
ChapterContract = UnitContract


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
    draft_sha256: str = ""
    contract_sha256: str = ""
    constraints_sha256: str = ""
    reviewed_at: str = Field(default_factory=utc_now_iso)


class ChapterCommit(StrictModel):
    chapter_number: int
    status: Literal["accepted"]
    accepted_at: str = Field(default_factory=utc_now_iso)
    accepted_file: str
    review_file: str
    contract_file: str
    artifact_hashes: dict[str, str] = Field(default_factory=dict)
    evidence_manifest_file: str = ""
    state_sync_status: Literal["pending_extraction", "applied"] = "pending_extraction"
    state_delta_file: str = ""
    state_revision: int | None = None
    contextual_score_file: str = ""
    contextual_score: float | None = None


StateAuthority = Literal[
    "author_locked",
    "text_confirmed",
    "model_inferred",
    "model_proposed",
]
StateStatus = Literal["active", "resolved", "superseded"]
StateLayerName = Literal[
    "canon_facts",
    "timeline",
    "entity_states",
    "character_beliefs",
    "relationship_arcs",
    "open_threads",
    "style_memory",
    "authority_layer",
]


class EvidenceRef(StrictModel):
    evidence_id: str
    chapter_number: int = Field(ge=1)
    paragraph_index: int = Field(ge=1)
    paragraph_sha256: str
    quote: str = ""


class EvidenceParagraph(StrictModel):
    evidence_id: str
    chapter_number: int = Field(ge=1)
    paragraph_index: int = Field(ge=1)
    text: str
    paragraph_sha256: str


class ChapterEvidenceManifest(StrictModel):
    schema_version: Literal["chapter-evidence/v1"] = "chapter-evidence/v1"
    project_id: str
    chapter_number: int = Field(ge=1)
    accepted_file: str
    accepted_sha256: str
    paragraphs: list[EvidenceParagraph] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now_iso)


class StateRecord(StrictModel):
    state_id: str
    subject: str
    claim: str
    value: str = ""
    authority: StateAuthority
    status: StateStatus = "active"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    introduced_chapter: int = Field(default=0, ge=0)
    updated_chapter: int = Field(default=0, ge=0)
    tags: list[str] = Field(default_factory=list)
    author_note: str = ""
    supersedes: list[str] = Field(default_factory=list)

    @field_validator("state_id", "subject", "claim")
    @classmethod
    def require_nonempty_state_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("state_id, subject, and claim must not be empty")
        return value

    @model_validator(mode="after")
    def validate_provenance(self) -> "StateRecord":
        if self.authority in {"text_confirmed", "model_inferred"} and not self.evidence_refs:
            raise ValueError(f"{self.authority} state requires evidence_refs")
        if self.authority == "author_locked" and not self.author_note.strip():
            raise ValueError("author_locked state requires author_note")
        return self


class AuthorityLayer(StrictModel):
    precedence: list[StateAuthority] = Field(
        default_factory=lambda: [
            "author_locked",
            "text_confirmed",
            "model_inferred",
            "model_proposed",
        ]
    )
    rules: list[str] = Field(
        default_factory=lambda: [
            "模型不得创建 author_locked 记录。",
            "低权限记录不得覆盖高权限记录。",
            "text_confirmed 与 model_inferred 必须绑定可校验的段落证据。",
            "model_proposed 默认不进入写作上下文。",
        ]
    )
    author_locks: list[StateRecord] = Field(default_factory=list)


class NovelState(StrictModel):
    schema_version: Literal["novel-state/v1"] = "novel-state/v1"
    project_id: str
    project_name: str
    revision: int = Field(default=0, ge=0)
    latest_committed_chapter: int = Field(default=0, ge=0)
    latest_state_synced_chapter: int = Field(default=0, ge=0)
    canon_facts: list[StateRecord] = Field(default_factory=list)
    timeline: list[StateRecord] = Field(default_factory=list)
    entity_states: list[StateRecord] = Field(default_factory=list)
    character_beliefs: list[StateRecord] = Field(default_factory=list)
    relationship_arcs: list[StateRecord] = Field(default_factory=list)
    open_threads: list[StateRecord] = Field(default_factory=list)
    style_memory: list[StateRecord] = Field(default_factory=list)
    authority_layer: AuthorityLayer = Field(default_factory=AuthorityLayer)
    applied_delta_ids: list[str] = Field(default_factory=list)
    updated_at: str = Field(default_factory=utc_now_iso)


class StateAddition(StrictModel):
    layer: StateLayerName
    record: StateRecord


class StateReplacement(StrictModel):
    layer: StateLayerName
    target_state_id: str
    replacement: StateRecord
    reason: str


class StateResolution(StrictModel):
    layer: StateLayerName
    target_state_id: str
    authority: StateAuthority
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    reason: str


class StateDelta(StrictModel):
    schema_version: Literal["state-delta/v1"] = "state-delta/v1"
    delta_id: str
    chapter_number: int = Field(ge=1)
    accepted_sha256: str
    source: Literal["model", "manual"]
    model: str = ""
    additions: list[StateAddition] = Field(default_factory=list)
    replacements: list[StateReplacement] = Field(default_factory=list)
    resolutions: list[StateResolution] = Field(default_factory=list)
    change_summary: list[str] = Field(default_factory=list)
    extracted_at: str = Field(default_factory=utc_now_iso)


class StateSyncTask(StrictModel):
    schema_version: Literal["state-sync-task/v1"] = "state-sync-task/v1"
    chapter_number: int = Field(ge=1)
    status: Literal["pending_extraction", "applied"] = "pending_extraction"
    accepted_sha256: str
    evidence_manifest_file: str
    candidate_delta_file: str = ""
    applied_delta_file: str = ""
    updated_at: str = Field(default_factory=utc_now_iso)


class ContextSelection(StrictModel):
    layer: StateLayerName
    record: StateRecord
    selection_reason: str


class CompiledChapterContext(StrictModel):
    schema_version: Literal["chapter-context/v1"] = "chapter-context/v1"
    chapter_number: int = Field(ge=1)
    state_revision: int = Field(ge=0)
    state_synced_through_chapter: int = Field(ge=0)
    state_is_stale: bool
    recent_chapters: list[dict[str, object]] = Field(default_factory=list)
    remote_evidence: list[dict[str, object]] = Field(default_factory=list)
    selected_state: list[ContextSelection] = Field(default_factory=list)
    retrieval_mode: Literal["state_only", "evidence_graph"] = "state_only"
    retrieval_trace: list[str] = Field(default_factory=list)
    omitted_model_proposals: int = Field(default=0, ge=0)
    requested_entities: list[str] = Field(default_factory=list)
    requested_threads: list[str] = Field(default_factory=list)
    approximate_chars: int = Field(default=0, ge=0)
    budget_chars: int = Field(default=0, ge=0)


ContextScoreDimensionName = Literal[
    "contract_fidelity",
    "boundary_continuity",
    "character_state_and_knowledge",
    "timeline_and_causality",
    "world_rule_resource_and_injury",
    "relationship_and_open_threads",
    "style_and_voice",
    "payoff_and_readability",
]


class ContextScoreDimension(StrictModel):
    dimension: ContextScoreDimensionName
    score: float = Field(ge=0.0, le=10.0)
    rationale: str
    prior_evidence_ids: list[str] = Field(default_factory=list)
    state_ids: list[str] = Field(default_factory=list)
    draft_quotes: list[str] = Field(default_factory=list)


class ContextScoreIssue(StrictModel):
    code: str
    severity: Literal["blocking", "risk", "warning"]
    dimension: ContextScoreDimensionName
    message: str
    draft_quote: str = ""
    prior_evidence_ids: list[str] = Field(default_factory=list)
    state_ids: list[str] = Field(default_factory=list)
    minimal_fix: str = ""


class ContextualScorecard(StrictModel):
    schema_version: Literal["contextual-scorecard/v1"] = "contextual-scorecard/v1"
    chapter_number: int = Field(ge=1)
    model: str
    draft_sha256: str
    context_sha256: str
    state_revision: int = Field(ge=0)
    author_policy_revision: int = Field(default=0, ge=0)
    author_policy_sha256: str = ""
    dimensions: list[ContextScoreDimension]
    overall_score: float = Field(ge=0.0, le=10.0)
    blocking: bool
    issues: list[ContextScoreIssue] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    scored_at: str = Field(default_factory=utc_now_iso)

    @model_validator(mode="after")
    def require_all_dimensions_once(self) -> "ContextualScorecard":
        expected = {
            "contract_fidelity",
            "boundary_continuity",
            "character_state_and_knowledge",
            "timeline_and_causality",
            "world_rule_resource_and_injury",
            "relationship_and_open_threads",
            "style_and_voice",
            "payoff_and_readability",
        }
        actual = [item.dimension for item in self.dimensions]
        if len(actual) != len(expected) or set(actual) != expected:
            raise ValueError("contextual scorecard requires every dimension exactly once")
        return self


class ArcBeat(StrictModel):
    chapter_number: int = Field(ge=1)
    title: str
    goal: str
    required_payoffs: list[str] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(default_factory=list)
    ending_hook: str
    focus_entities: list[str] = Field(default_factory=list)
    relevant_threads: list[str] = Field(default_factory=list)
    must_preserve: list[str] = Field(default_factory=list)
    risk_checks: list[str] = Field(default_factory=list)
    target_chars: int = Field(default=3000, ge=500)
    accepted_chars: int = Field(default=0, ge=0)
    status: Literal["planned", "active", "accepted"] = "planned"


class ArcPlanIssue(StrictModel):
    code: str
    severity: Literal["blocking", "risk", "warning"]
    chapter_number: int = Field(ge=1)
    message: str
    repair_hint: str = ""


class ArcPlanReview(StrictModel):
    schema_version: Literal["arc-plan-review/v1"] = "arc-plan-review/v1"
    arc_id: str
    blocking: bool
    issues: list[ArcPlanIssue] = Field(default_factory=list)
    reviewed_at: str = Field(default_factory=utc_now_iso)


class ArcReplanEvent(StrictModel):
    trigger_chapter: int = Field(ge=1)
    from_state_revision: int = Field(ge=0)
    to_state_revision: int = Field(ge=0)
    changed_chapters: list[int] = Field(default_factory=list)
    reason: str
    model: str
    replanned_at: str = Field(default_factory=utc_now_iso)


class ArcContract(StrictModel):
    schema_version: Literal["arc-contract/v1"] = "arc-contract/v1"
    arc_id: str
    start_chapter: int = Field(ge=1)
    horizon: int = Field(ge=1)
    target_total_chars: int = Field(default=20000, ge=1000, le=20000)
    actual_total_chars: int = Field(default=0, ge=0)
    unit_title: str = ""
    objective: str
    author_intent: str
    source_material_ids: list[str] = Field(default_factory=list)
    entry_state: list[str] = Field(default_factory=list)
    target_end_state: list[str] = Field(default_factory=list)
    unit_payoffs: list[str] = Field(default_factory=list)
    author_locks: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    state_revision: int = Field(ge=0)
    author_policy_revision: int = Field(default=0, ge=0)
    author_policy_sha256: str = ""
    current_generation_chapter: int | None = Field(default=None, ge=1)
    needs_replan: bool = False
    completed: bool = False
    handoff_policy: Literal["stop_for_author"] = "stop_for_author"
    beats: list[ArcBeat]
    replan_history: list[ArcReplanEvent] = Field(default_factory=list)
    planner_model: str = ""
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)

    @model_validator(mode="after")
    def validate_arc_shape(self) -> "ArcContract":
        if len(self.beats) != self.horizon:
            raise ValueError("arc beat count must equal horizon")
        expected = list(range(self.start_chapter, self.start_chapter + self.horizon))
        actual = [beat.chapter_number for beat in self.beats]
        if actual != expected:
            raise ValueError("arc chapter numbers must be consecutive and ordered")
        planned_chars = sum(beat.target_chars for beat in self.beats)
        if planned_chars > self.target_total_chars:
            raise ValueError("sum of beat target_chars exceeds unit target_total_chars")
        accepted_chars = sum(beat.accepted_chars for beat in self.beats)
        if self.actual_total_chars != accepted_chars:
            raise ValueError("actual_total_chars must equal accepted beat character counts")
        active = [beat.chapter_number for beat in self.beats if beat.status == "active"]
        if len(active) > 1:
            raise ValueError("arc can have at most one active chapter")
        if active and self.current_generation_chapter != active[0]:
            raise ValueError("current_generation_chapter must match active beat")
        return self


class UnitBranchFingerprint(StrictModel):
    conflict_space: str
    trigger: str
    core_mechanism: str
    climax_action: str
    cost_type: str
    end_hook: str

    @field_validator(
        "conflict_space",
        "trigger",
        "core_mechanism",
        "climax_action",
        "cost_type",
        "end_hook",
    )
    @classmethod
    def require_fingerprint_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("unit branch fingerprint axes must not be empty")
        return value


class UnitBranchCard(StrictModel):
    schema_version: Literal["unit-branch-card/v1"] = "unit-branch-card/v1"
    branch_id: str
    planning_profile: Literal["mechanism", "character", "evidence"]
    unit_title: str
    approach_summary: str
    distinctive_choice: str
    fingerprint: UnitBranchFingerprint
    beats: list[ArcBeat]
    planner_model: str = ""
    created_at: str = Field(default_factory=utc_now_iso)

    @model_validator(mode="after")
    def validate_branch_beats(self) -> "UnitBranchCard":
        if not self.beats:
            raise ValueError("unit branch must contain at least one beat")
        start = self.beats[0].chapter_number
        expected = list(range(start, start + len(self.beats)))
        if [beat.chapter_number for beat in self.beats] != expected:
            raise ValueError("unit branch beats must be consecutive and ordered")
        return self


class UnitBranchDiversityPair(StrictModel):
    branch_a: str
    branch_b: str
    differing_axes: list[str] = Field(default_factory=list)
    difference_count: int = Field(ge=0, le=6)
    passes: bool
    semantic_differing_axes: list[str] = Field(default_factory=list)
    semantic_difference_count: int | None = Field(default=None, ge=0, le=6)
    semantic_passes: bool | None = None
    semantic_rationale: str = ""


class UnitBranchSet(StrictModel):
    schema_version: Literal["unit-branch-set/v1"] = "unit-branch-set/v1"
    branch_set_id: str
    project_id: str
    start_chapter: int = Field(ge=1)
    target_total_chars: int = Field(default=20000, ge=1000, le=20000)
    objective: str
    author_intent: str
    source_material_ids: list[str] = Field(default_factory=list)
    freedom_axes: list[
        Literal[
            "conflict_space",
            "trigger",
            "core_mechanism",
            "climax_action",
            "cost_type",
            "end_hook",
        ]
    ] = Field(
        default_factory=lambda: [
            "conflict_space",
            "trigger",
            "core_mechanism",
            "climax_action",
            "cost_type",
            "end_hook",
        ],
        min_length=3,
    )
    entry_state: list[str] = Field(default_factory=list)
    target_end_state: list[str] = Field(default_factory=list)
    unit_payoffs: list[str] = Field(default_factory=list)
    author_locks: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    state_revision: int = Field(ge=0)
    author_policy_revision: int = Field(ge=0)
    author_policy_sha256: str
    candidates: list[UnitBranchCard] = Field(min_length=2, max_length=5)
    diversity_pairs: list[UnitBranchDiversityPair] = Field(default_factory=list)
    diversity_judge_model: str = ""
    diversity_order_consistent: bool | None = None
    blocking: bool = False
    selected_branch_id: str = ""
    created_at: str = Field(default_factory=utc_now_iso)

    @model_validator(mode="after")
    def validate_branch_set(self) -> "UnitBranchSet":
        ids = [card.branch_id for card in self.candidates]
        if len(ids) != len(set(ids)):
            raise ValueError("unit branch ids must be unique")
        for card in self.candidates:
            if card.beats[0].chapter_number != self.start_chapter:
                raise ValueError("every unit branch must start at branch set start_chapter")
            if sum(beat.target_chars for beat in card.beats) > self.target_total_chars:
                raise ValueError("unit branch planned characters exceed target_total_chars")
        if self.selected_branch_id and self.selected_branch_id not in ids:
            raise ValueError("selected_branch_id is not present in candidates")
        return self


# User-facing semantic alias: one ArcContract represents exactly one author-led
# unit drama, not an open-ended autonomous continuation.
UnitArcContract = ArcContract

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

from __future__ import annotations

from pathlib import Path

from .storage import chapter_id


def strategy_path(root: Path) -> Path:
    return root / "story_bible" / "writer_strategy.json"


def expectation_path(root: Path) -> Path:
    return root / "expectations" / "reader_expectation_map.json"


def outline_path(root: Path) -> Path:
    return root / "story_bible" / "story_outline.json"


def outline_md_path(root: Path) -> Path:
    return root / "story_bible" / "story_outline.md"


def outline_revisions_path(root: Path) -> Path:
    return root / "state" / "outline_revisions.json"


def contract_path(root: Path, chapter_number: int) -> Path:
    return root / "chapter_contracts" / f"{chapter_id(chapter_number)}_contract.json"


def constraints_path(root: Path, chapter_number: int) -> Path:
    return root / "chapter_contracts" / f"{chapter_id(chapter_number)}_character_constraints.json"


def prewrite_path(root: Path, chapter_number: int) -> Path:
    return root / "chapter_contracts" / f"{chapter_id(chapter_number)}_prewrite_plan.json"


def draft_path(root: Path, chapter_number: int) -> Path:
    return root / "drafts" / f"{chapter_id(chapter_number)}_draft.md"


def review_path(root: Path, chapter_number: int) -> Path:
    return root / "reviews" / f"{chapter_id(chapter_number)}_review.json"


def accepted_path(root: Path, chapter_number: int) -> Path:
    return root / "accepted" / f"{chapter_id(chapter_number)}.md"


def commit_path(root: Path, chapter_number: int) -> Path:
    return root / "commits" / f"{chapter_id(chapter_number)}_commit.json"


def discussion_path(root: Path, chapter_number: int) -> Path:
    return root / "author_discussion" / f"{chapter_id(chapter_number)}_packet.md"


def handoff_path(root: Path, chapter_number: int) -> Path:
    return root / "handoffs" / f"{chapter_id(chapter_number)}_handoff.json"


def handoff_md_path(root: Path, chapter_number: int) -> Path:
    return root / "handoffs" / f"{chapter_id(chapter_number)}_handoff.md"


def candidate_json_path(root: Path, chapter_number: int) -> Path:
    return root / "author_discussion" / f"{chapter_id(chapter_number)}_decision_candidate.json"


def candidate_md_path(root: Path, chapter_number: int) -> Path:
    return root / "author_discussion" / f"{chapter_id(chapter_number)}_decision_candidate.md"


def evaluation_json_path(root: Path, chapter_number: int) -> Path:
    return root / "evaluations" / f"workflow_evaluation_{chapter_id(chapter_number)}.json"


def evaluation_md_path(root: Path, chapter_number: int) -> Path:
    return root / "evaluations" / f"workflow_evaluation_{chapter_id(chapter_number)}.md"

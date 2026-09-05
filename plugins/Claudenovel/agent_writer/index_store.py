from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from .models import ChapterCommit, ChapterContract, ReviewIssue, ReviewResult


SCHEMA = """
CREATE TABLE IF NOT EXISTS chapter_artifacts (
    chapter_number INTEGER NOT NULL,
    artifact_type TEXT NOT NULL,
    path TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (chapter_number, artifact_type)
);

CREATE TABLE IF NOT EXISTS review_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_number INTEGER NOT NULL,
    code TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    evidence TEXT NOT NULL DEFAULT '',
    repair_hint TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS commit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_number INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def index_path(project_root: Path) -> Path:
    return project_root / ".agent_writer" / "index.db"


def connect(project_root: Path) -> sqlite3.Connection:
    path = index_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_artifact(project_root: Path, chapter_number: int, artifact_type: str, path: Path | str) -> None:
    with connect(project_root) as conn:
        conn.execute(
            """
            INSERT INTO chapter_artifacts(chapter_number, artifact_type, path)
            VALUES (?, ?, ?)
            ON CONFLICT(chapter_number, artifact_type)
            DO UPDATE SET path=excluded.path, created_at=CURRENT_TIMESTAMP
            """,
            (chapter_number, artifact_type, str(path)),
        )


def save_contract(project_root: Path, contract: ChapterContract, path: Path | str) -> None:
    upsert_artifact(project_root, contract.chapter_number, "contract", path)


def save_review(project_root: Path, review: ReviewResult, path: Path | str) -> None:
    with connect(project_root) as conn:
        conn.execute(
            """
            INSERT INTO chapter_artifacts(chapter_number, artifact_type, path)
            VALUES (?, 'review', ?)
            ON CONFLICT(chapter_number, artifact_type)
            DO UPDATE SET path=excluded.path, created_at=CURRENT_TIMESTAMP
            """,
            (review.chapter_number, str(path)),
        )
        conn.execute("DELETE FROM review_issues WHERE chapter_number = ?", (review.chapter_number,))
        conn.executemany(
            """
            INSERT INTO review_issues(chapter_number, code, severity, message, evidence, repair_hint)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    review.chapter_number,
                    issue.code,
                    issue.severity,
                    issue.message,
                    issue.evidence,
                    issue.repair_hint,
                )
                for issue in review.issues
            ],
        )


def save_commit(project_root: Path, commit: ChapterCommit, path: Path | str) -> None:
    with connect(project_root) as conn:
        conn.execute(
            """
            INSERT INTO chapter_artifacts(chapter_number, artifact_type, path)
            VALUES (?, 'commit', ?)
            ON CONFLICT(chapter_number, artifact_type)
            DO UPDATE SET path=excluded.path, created_at=CURRENT_TIMESTAMP
            """,
            (commit.chapter_number, str(path)),
        )
        conn.execute(
            "INSERT INTO commit_events(chapter_number, event_type, payload) VALUES (?, ?, ?)",
            (commit.chapter_number, "unit_accepted", commit.model_dump_json()),
        )


def latest_artifacts(project_root: Path, *, limit: int = 20) -> list[dict[str, object]]:
    with connect(project_root) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT chapter_number, artifact_type, path, created_at
            FROM chapter_artifacts
            ORDER BY chapter_number DESC, artifact_type ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def blocking_issues(project_root: Path) -> list[dict[str, object]]:
    with connect(project_root) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT chapter_number, code, severity, message, evidence, repair_hint
            FROM review_issues
            WHERE severity = 'blocking'
            ORDER BY chapter_number, id
            """
        ).fetchall()
    return [dict(row) for row in rows]

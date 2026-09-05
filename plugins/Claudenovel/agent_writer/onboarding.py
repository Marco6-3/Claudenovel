from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

from pydantic import Field

from .author_policy import import_author_policy_bundle
from .models import StrictModel, utc_now_iso
from .novel_state import (
    build_evidence_manifest,
    extract_state_delta,
    load_novel_state,
    mark_chapter_pending_state_sync,
    pending_state_chapters,
    sync_task_path,
)
from .pipeline import init_project
from .storage import (
    copy_utf8_atomic,
    ensure_project,
    read_json,
    read_text,
    sha256_file,
    write_json_atomic,
)


class ExistingNovelImportManifest(StrictModel):
    schema_version: Literal["existing-novel-import/v1"] = "existing-novel-import/v1"
    project_name: str
    genre: str
    premise: str
    target_reader: str
    source_root: str
    chapter_glob: str = "*.txt"
    chapter_filename_regex: str = r"第\s*(\d+)\s*章"
    expected_first_chapter: int = Field(default=1, ge=1)
    expected_last_chapter: int | None = Field(default=None, ge=1)
    author_policy_file: str = ""
    author_bible_text_files: list[str] = Field(default_factory=list)
    high_risk_chapters: list[int] = Field(default_factory=list)
    private_project: bool = True


class ImportedChapter(StrictModel):
    chapter_number: int = Field(ge=1)
    title: str
    source_file: str
    source_sha256: str
    accepted_file: str
    accepted_sha256: str
    evidence_manifest_file: str


class ExistingNovelImportReport(StrictModel):
    schema_version: Literal["existing-novel-import-report/v1"] = (
        "existing-novel-import-report/v1"
    )
    project_name: str
    source_root: str
    private_project: bool
    chapter_count: int
    first_chapter: int
    last_chapter: int
    high_risk_chapters: list[int]
    chapters: list[ImportedChapter]
    author_policy_imported: bool
    author_bible_files: list[str]
    pending_state_chapters: list[int]
    ready_for_writing: bool = False
    imported_at: str = Field(default_factory=utc_now_iso)


def import_report_path(root: Path) -> Path:
    return root / "imports" / "existing_novel_import.json"


def bootstrap_progress_path(root: Path) -> Path:
    return root / "imports" / "state_bootstrap_progress.json"


def _resolve_manifest_path(manifest_file: Path, raw_path: str) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = manifest_file.parent / path
    return path.resolve()


def _discover_chapters(
    manifest_file: Path,
    manifest: ExistingNovelImportManifest,
) -> list[tuple[int, str, Path]]:
    source_root = _resolve_manifest_path(manifest_file, manifest.source_root)
    if not source_root.exists():
        raise FileNotFoundError(f"existing novel source root is missing: {source_root}")
    pattern = re.compile(manifest.chapter_filename_regex)
    chapters: list[tuple[int, str, Path]] = []
    for path in source_root.glob(manifest.chapter_glob):
        if not path.is_file():
            continue
        match = pattern.search(path.stem)
        if not match:
            continue
        chapter_number = int(match.group(1))
        title = pattern.sub("", path.stem, count=1).strip(" _-　") or f"第{chapter_number}章"
        chapters.append((chapter_number, title, path.resolve()))
    chapters.sort(key=lambda item: item[0])
    numbers = [item[0] for item in chapters]
    if len(numbers) != len(set(numbers)):
        raise ValueError("existing novel source has duplicate chapter numbers")
    if not chapters:
        raise ValueError("existing novel import found no chapter files")
    expected_last = manifest.expected_last_chapter or chapters[-1][0]
    expected = list(range(manifest.expected_first_chapter, expected_last + 1))
    if numbers != expected:
        missing = sorted(set(expected) - set(numbers))
        unexpected = sorted(set(numbers) - set(expected))
        raise ValueError(
            f"existing novel chapters are not contiguous; missing={missing}, unexpected={unexpected}"
        )
    return chapters


def onboard_existing_novel(
    project_root: Path,
    *,
    manifest_file: Path,
    resume: bool = False,
) -> ExistingNovelImportReport:
    manifest_file = manifest_file.resolve()
    manifest = ExistingNovelImportManifest.model_validate(read_json(manifest_file))
    chapters = _discover_chapters(manifest_file, manifest)
    root = project_root.resolve()
    strategy_file = root / "story_bible" / "writer_strategy.json"
    if strategy_file.exists():
        if not resume:
            raise ValueError("project already exists; use --resume for an identical import")
        root = ensure_project(root)
    else:
        init_project(
            root,
            name=manifest.project_name,
            genre=manifest.genre,
            premise=manifest.premise,
            target_reader=manifest.target_reader,
        )

    imported: list[ImportedChapter] = []
    for chapter_number, title, source_file in chapters:
        accepted_file = root / "accepted" / f"chapter_{chapter_number:04d}.md"
        if accepted_file.exists():
            if sha256_file(accepted_file) != sha256_file(source_file):
                raise ValueError(
                    f"accepted chapter differs from import source; refusing overwrite: {accepted_file}"
                )
        else:
            copy_utf8_atomic(source_file, accepted_file)
        evidence = build_evidence_manifest(
            root,
            chapter_number=chapter_number,
            accepted_file=accepted_file,
        )
        task_file = sync_task_path(root, chapter_number)
        if not task_file.exists():
            mark_chapter_pending_state_sync(
                root,
                chapter_number=chapter_number,
                manifest=evidence,
            )
        imported.append(
            ImportedChapter(
                chapter_number=chapter_number,
                title=title,
                source_file=str(source_file),
                source_sha256=sha256_file(source_file),
                accepted_file=str(accepted_file),
                accepted_sha256=sha256_file(accepted_file),
                evidence_manifest_file=str(
                    root
                    / "state"
                    / "evidence"
                    / f"chapter_{chapter_number:04d}_evidence.json"
                ),
            )
        )

    policy_imported = False
    if manifest.author_policy_file:
        policy_file = _resolve_manifest_path(manifest_file, manifest.author_policy_file)
        import_author_policy_bundle(root, policy_file)
        policy_imported = True

    copied_bible_files: list[str] = []
    for raw_path in manifest.author_bible_text_files:
        source = _resolve_manifest_path(manifest_file, raw_path)
        if source.suffix.lower() not in {".txt", ".md", ".json"}:
            raise ValueError(
                f"author_bible_text_files only accepts UTF-8 text/json after conversion: {source}"
            )
        target = root / "story_bible" / "source_material" / source.name
        copy_utf8_atomic(source, target)
        copied_bible_files.append(str(target))

    report = ExistingNovelImportReport(
        project_name=manifest.project_name,
        source_root=str(_resolve_manifest_path(manifest_file, manifest.source_root)),
        private_project=manifest.private_project,
        chapter_count=len(imported),
        first_chapter=imported[0].chapter_number,
        last_chapter=imported[-1].chapter_number,
        high_risk_chapters=sorted(set(manifest.high_risk_chapters)),
        chapters=imported,
        author_policy_imported=policy_imported,
        author_bible_files=copied_bible_files,
        pending_state_chapters=pending_state_chapters(root),
    )
    write_json_atomic(import_report_path(root), report)
    return report


def bootstrap_existing_state(
    project_root: Path,
    *,
    from_chapter: int | None = None,
    to_chapter: int | None = None,
    max_chapters: int | None = None,
    audit_all: bool = False,
    temperature: float = 0.0,
    max_tokens: int = 6000,
) -> dict[str, object]:
    root = ensure_project(project_root)
    report = ExistingNovelImportReport.model_validate(read_json(import_report_path(root)))
    pending = pending_state_chapters(root)
    if from_chapter is not None:
        pending = [value for value in pending if value >= from_chapter]
    if to_chapter is not None:
        pending = [value for value in pending if value <= to_chapter]
    if max_chapters is not None:
        pending = pending[: max(0, max_chapters)]
    completed: list[dict[str, object]] = []
    for chapter_number in pending:
        result = extract_state_delta(
            root,
            chapter_number=chapter_number,
            temperature=temperature,
            max_tokens=max_tokens,
            apply=True,
            completeness_audit=(audit_all or chapter_number in report.high_risk_chapters),
        )
        completed.append(result)
        progress = {
            "schema_version": "existing-state-bootstrap-progress/v1",
            "project_name": report.project_name,
            "last_completed_chapter": chapter_number,
            "state_revision": load_novel_state(root).revision,
            "remaining_pending_chapters": pending_state_chapters(root),
            "completed_this_run": [item["chapter_number"] for item in completed],
            "updated_at": utc_now_iso(),
        }
        write_json_atomic(bootstrap_progress_path(root), progress)

    remaining = pending_state_chapters(root)
    import_payload = read_json(import_report_path(root))
    import_payload["pending_state_chapters"] = remaining
    import_payload["ready_for_writing"] = not remaining
    write_json_atomic(import_report_path(root), import_payload)
    return {
        "project_root": str(root),
        "completed_chapters": [item["chapter_number"] for item in completed],
        "remaining_pending_chapters": remaining,
        "ready_for_writing": not remaining,
        "state_revision": load_novel_state(root).revision,
        "progress_file": str(bootstrap_progress_path(root)),
    }

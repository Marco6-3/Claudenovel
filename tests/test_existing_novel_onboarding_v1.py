from __future__ import annotations

import json
from pathlib import Path

from agent_writer.models import ChapterEvidenceManifest, StateDelta
from agent_writer.novel_state import evidence_manifest_path, pending_state_chapters
from agent_writer.onboarding import bootstrap_existing_state, onboard_existing_novel
from agent_writer.storage import read_model


def test_existing_novel_import_is_contiguous_private_and_resumable(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for number, title in ((1, "开始"), (2, "继续"), (3, "结束")):
        (source / f"第{number}章 {title}.txt").write_text(
            f"第{number}章正文。",
            encoding="utf-8",
        )
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(
        json.dumps(
            {
                "schema_version": "existing-novel-import/v1",
                "project_name": "导入测试",
                "genre": "校园修仙",
                "premise": "现有小说接入",
                "target_reader": "测试读者",
                "source_root": str(source),
                "expected_last_chapter": 3,
                "high_risk_chapters": [2],
                "private_project": True,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    project = tmp_path / "project"

    report = onboard_existing_novel(project, manifest_file=manifest_file)
    resumed = onboard_existing_novel(project, manifest_file=manifest_file, resume=True)

    assert report.chapter_count == resumed.chapter_count == 3
    assert report.private_project is True
    assert pending_state_chapters(project) == [1, 2, 3]
    assert (project / "accepted" / "chapter_0003.md").read_text(encoding="utf-8") == "第3章正文。"


def test_existing_state_bootstrap_resumes_and_audits_only_high_risk(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    for number in (1, 2):
        (source / f"第{number}章 测试.txt").write_text(
            f"第{number}章正文。",
            encoding="utf-8",
        )
    manifest_file = tmp_path / "manifest.json"
    manifest_file.write_text(
        json.dumps(
            {
                "schema_version": "existing-novel-import/v1",
                "project_name": "引导测试",
                "genre": "校园修仙",
                "premise": "状态引导",
                "target_reader": "测试读者",
                "source_root": str(source),
                "expected_last_chapter": 2,
                "high_risk_chapters": [2],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    project = tmp_path / "project"
    onboard_existing_novel(project, manifest_file=manifest_file)
    calls: list[tuple[int, bool]] = []

    def fake_extract(
        root: Path,
        *,
        chapter_number: int,
        temperature: float,
        max_tokens: int,
        apply: bool,
        completeness_audit: bool,
    ):
        calls.append((chapter_number, completeness_audit))
        manifest = read_model(
            evidence_manifest_path(root, chapter_number),
            ChapterEvidenceManifest,
        )
        from agent_writer.novel_state import apply_state_delta

        state = apply_state_delta(
            root,
            StateDelta(
                delta_id=f"bootstrap-{chapter_number}",
                chapter_number=chapter_number,
                accepted_sha256=manifest.accepted_sha256,
                source="manual",
            ),
        )
        return {
            "chapter_number": chapter_number,
            "applied": True,
            "state_revision": state.revision,
        }

    monkeypatch.setattr("agent_writer.onboarding.extract_state_delta", fake_extract)

    first = bootstrap_existing_state(project, max_chapters=1)
    second = bootstrap_existing_state(project)

    assert first["remaining_pending_chapters"] == [2]
    assert second["ready_for_writing"] is True
    assert calls == [(1, False), (2, True)]

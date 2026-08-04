from __future__ import annotations

from pathlib import Path

from agent_writer.evidence_graph import (
    build_evidence_graph,
    load_context_retrieval_policy,
    set_context_retrieval_policy,
)
from agent_writer.models import EvidenceRef, StateRecord
from agent_writer.novel_state import (
    build_evidence_manifest,
    compile_chapter_context,
    load_novel_state,
    state_path,
)
from agent_writer.pipeline import init_project, plan_chapter
from agent_writer.storage import read_model, write_json_atomic
from agent_writer.models import ChapterEvidenceManifest, NovelState


def _graph_project(tmp_path: Path) -> Path:
    init_project(
        tmp_path,
        name="证据图测试书",
        genre="校园修仙",
        premise="图书馆传承会引发身体变化。",
        target_reader="男频都市读者",
    )
    for chapter_number, text in (
        (1, "凌默跨过旧图书馆门槛时，左手红纹第一次发热。"),
        (2, "第二天他留在教室，红纹一整天都没有变化。"),
        (3, "考试结束后，他把错题本塞回书包。"),
    ):
        accepted = tmp_path / "accepted" / f"chapter_{chapter_number:04d}.md"
        accepted.write_text(text, encoding="utf-8")
        build_evidence_manifest(
            tmp_path,
            chapter_number=chapter_number,
            accepted_file=accepted,
        )
    manifest = read_model(
        tmp_path / "state" / "evidence" / "chapter_0001_evidence.json",
        ChapterEvidenceManifest,
    )
    paragraph = manifest.paragraphs[0]
    state = load_novel_state(tmp_path)
    state.revision = 1
    state.latest_committed_chapter = 3
    state.latest_state_synced_chapter = 3
    state.entity_states.append(
        StateRecord(
            state_id="lingmo.library_red_mark",
            subject="凌默",
            claim="图书馆与红纹发热存在待验证关联",
            value="第一次跨过门槛时红纹发热",
            authority="text_confirmed",
            evidence_refs=[
                EvidenceRef(
                    evidence_id=paragraph.evidence_id,
                    chapter_number=1,
                    paragraph_index=1,
                    paragraph_sha256=paragraph.paragraph_sha256,
                    quote="左手红纹第一次发热",
                )
            ],
            introduced_chapter=1,
            updated_chapter=1,
            tags=["凌默", "图书馆", "红纹"],
        )
    )
    write_json_atomic(state_path(tmp_path), state)
    plan_chapter(
        tmp_path,
        chapter_number=4,
        title="门槛对照",
        goal="凌默验证图书馆是否触发红纹",
        required_payoffs=["完成门槛对照"],
        ending_hook="红纹只在跨过门槛后发热",
        characters=["凌默"],
    )
    return tmp_path


def test_evidence_graph_retrieves_remote_evidence_beyond_recent_window(tmp_path: Path) -> None:
    root = _graph_project(tmp_path)
    policy = set_context_retrieval_policy(
        root,
        mode="evidence_graph",
        max_remote_evidence=5,
    )

    context = compile_chapter_context(
        root,
        chapter_number=4,
        relevant_entities=["凌默"],
        recent_chapter_count=1,
    )

    assert policy.mode == "evidence_graph"
    assert context.retrieval_mode == "evidence_graph"
    remote_chapters = {item["chapter_number"] for item in context.remote_evidence}
    assert 1 in remote_chapters
    assert 3 not in remote_chapters
    assert any(
        "左手红纹第一次发热" in item["text"]
        for item in context.remote_evidence
    )
    assert "lingmo.library_red_mark" in {
        item.record.state_id for item in context.selected_state
    }
    assert load_context_retrieval_policy(root).mode == "evidence_graph"


def test_default_policy_preserves_state_only_behavior(tmp_path: Path) -> None:
    root = _graph_project(tmp_path)
    graph = build_evidence_graph(root, read_model(state_path(root), NovelState))
    context = compile_chapter_context(
        root,
        chapter_number=4,
        recent_chapter_count=1,
    )

    assert graph.nodes
    assert context.retrieval_mode == "state_only"
    assert context.remote_evidence == []


def test_graph_does_not_rank_single_name_mention_or_future_state(tmp_path: Path) -> None:
    root = _graph_project(tmp_path)
    chapter_two = root / "accepted" / "chapter_0002.md"
    chapter_two.write_text(
        "凌默。\n\n凌默在教室完成了红纹与图书馆门槛的第二次对照。",
        encoding="utf-8",
    )
    build_evidence_manifest(root, chapter_number=2, accepted_file=chapter_two)
    paragraph = read_model(
        root / "state" / "evidence" / "chapter_0001_evidence.json",
        ChapterEvidenceManifest,
    ).paragraphs[0]
    state = load_novel_state(root)
    state.entity_states.append(
        StateRecord(
            state_id="future.forbidden.leak",
            subject="凌默",
            claim="未来才出现的秘密",
            value="第五章才知道红纹来自禁术",
            authority="text_confirmed",
            evidence_refs=[
                EvidenceRef(
                    evidence_id=paragraph.evidence_id,
                    chapter_number=1,
                    paragraph_index=1,
                    paragraph_sha256=paragraph.paragraph_sha256,
                    quote="左手红纹第一次发热",
                )
            ],
            introduced_chapter=5,
            updated_chapter=5,
            tags=["凌默", "红纹"],
        )
    )
    write_json_atomic(state_path(root), state)
    set_context_retrieval_policy(root, mode="evidence_graph", max_remote_evidence=5)

    context = compile_chapter_context(
        root,
        chapter_number=4,
        relevant_entities=["凌默"],
        relevant_threads=["红纹与图书馆门槛对照"],
        recent_chapter_count=1,
    )

    remote_texts = [item["text"] for item in context.remote_evidence]
    assert remote_texts
    assert remote_texts[0] != "凌默。"
    assert any("第二次对照" in text for text in remote_texts)
    assert "future.forbidden.leak" not in {
        item.record.state_id for item in context.selected_state
    }

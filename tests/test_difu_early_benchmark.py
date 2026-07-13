from __future__ import annotations

import importlib.util
import json
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "difu_early_continuation_v1"
    / "build_benchmark.py"
)
SPEC = importlib.util.spec_from_file_location("difu_benchmark_builder", MODULE_PATH)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


def _fixture_source(tmp_path: Path) -> Path:
    source = tmp_path / "novel.txt"
    source.write_text(
        "序言不会进入章节。\n"
        "第一章 起点\n第一章公开正文，主角盯着手机。\n"
        "第二章 隐藏答案\n第二章绝密事件，不得泄漏给 Writer。\n"
        "第三章 后文\n第三章也不应被扫描进提示词。\n",
        encoding="utf-8",
    )
    return source


def test_chinese_number_handles_early_chapters() -> None:
    assert builder.chinese_number("二") == 2
    assert builder.chinese_number("十二") == 12
    assert builder.chinese_number("二十七") == 27
    assert builder.chinese_number("101") == 101


def test_builder_keeps_target_out_of_public_prompt(tmp_path: Path) -> None:
    source = _fixture_source(tmp_path)
    public = tmp_path / "public.json"
    private = tmp_path / "private.json"
    public.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case",
                        "target_chapter": 2,
                        "recent_context_chapters": [1],
                        "public_state": ["公开状态"],
                        "external_idea": "外部创意",
                        "idea_locks": ["锁"],
                        "forbidden_changes": ["禁改"],
                        "freedom_budget": ["自由"],
                        "success_criteria": ["成功"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    private.write_text(
        json.dumps({"cases": {"case": {"target_title": "隐藏答案"}}}, ensure_ascii=False),
        encoding="utf-8",
    )
    out = tmp_path / "out"

    builder.build(source, public, private, out)

    prompt = (out / "case/public/writer_prompt.md").read_text(encoding="utf-8")
    assert "第一章公开正文" in prompt
    assert "第二章绝密事件" not in prompt
    assert "第三章也不应" not in prompt
    assert not (out / "case/private").exists()


def test_private_gold_is_written_only_when_explicit(tmp_path: Path) -> None:
    source = _fixture_source(tmp_path)
    public = tmp_path / "public.json"
    private = tmp_path / "private.json"
    public.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "case",
                        "target_chapter": 2,
                        "recent_context_chapters": [1],
                        "public_state": ["公开状态"],
                        "external_idea": "外部创意",
                        "idea_locks": ["锁"],
                        "forbidden_changes": ["禁改"],
                        "freedom_budget": ["自由"],
                        "success_criteria": ["成功"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    private.write_text(
        json.dumps({"cases": {"case": {"target_title": "隐藏答案"}}}, ensure_ascii=False),
        encoding="utf-8",
    )
    out = tmp_path / "out"

    builder.build(source, public, private, out, include_private_gold_text=True)

    gold = (out / "case/private/original_target.md").read_text(encoding="utf-8")
    assert "隐藏答案" in gold
    assert "第二章绝密事件" in gold

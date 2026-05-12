from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from data_modules import inspiration_library as il


def test_add_manual_query_and_brief(tmp_path: Path) -> None:
    project = tmp_path
    (project / ".webnovel").mkdir()

    add_args = Namespace(
        project_root=str(project),
        id="",
        title="误会跳崖触发上界收徒",
        source_url="https://example.test/chapter/1",
        platform="example",
        author="",
        rating=9.2,
        heat=100000,
        discussion_count=3200,
        tags="误会,情感爆点,地图切换",
        excerpt="女主误会主角背叛，在旧日甜蜜悬崖求死，空间乱流引来上界大能。",
        note="旧甜回刺，主角短期失败，女主获得独立升级线。",
        max_excerpt_chars=300,
    )
    assert il.cmd_add_manual(add_args) == 0

    data = json.loads((project / ".webnovel" / "inspiration_library.json").read_text(encoding="utf-8"))
    assert len(data["cases"]) == 1
    case = data["cases"][0]
    assert case["source_url"] == "https://example.test/chapter/1"
    assert "误会" in case["tags"]
    assert case["deconstruction"]["mechanisms"]

    query_args = Namespace(
        project_root=str(project),
        query="主角无敌后用误会和女主离开开启上界副本",
        tag="",
        limit=5,
        excerpt_chars=120,
    )
    assert il.cmd_query(query_args) == 0

    output = project / ".webnovel" / "tmp" / "brief.md"
    output.parent.mkdir(parents=True)
    brief_args = Namespace(
        project_root=str(project),
        query="生成不照搬的上界开副本情节",
        limit=3,
        output=str(output),
    )
    assert il.cmd_brief(brief_args) == 0
    text = output.read_text(encoding="utf-8")
    assert "灵感生成 Brief" in text
    assert "不复用原文表达" in text

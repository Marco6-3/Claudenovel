"""Exercise the distribution outside the checkout and without bundled novels."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def standalone(tmp_path_factory):
    folder = tmp_path_factory.mktemp("standalone-plugin")
    plugin = folder / "plugin"
    shutil.copytree(ROOT / "plugins" / "Claudenovel", plugin,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return plugin


def run(plugin, *args):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run([sys.executable, "-X", "utf8", *map(str, args)],
                          cwd=plugin, env=env, capture_output=True,
                          text=True, encoding="utf-8", timeout=60)


@pytest.mark.parametrize("entry", [
    "agent_writer_cli.py", "analyze_enhanced.py", "rewrite_chapter.py",
    "answer_question.py", "index_and_query_rag.py",
])
def test_standalone_entrypoints(standalone, entry):
    result = run(standalone, entry, "--help")
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout


def test_analysis_requires_novel_instead_of_reading_requirements(standalone):
    result = run(standalone, "analyze_enhanced.py")
    assert result.returncode == 2
    assert "--txt-path" in result.stderr
    assert "Traceback" not in result.stderr


def test_standalone_chinese_analysis(standalone, tmp_path):
    novel = tmp_path / "前情.txt"
    novel.write_text(
        "第一章 夜访\n\n林青推开书房的门，发现窗台上放着自己找了半个月的旧书。"
        "他记得离开时已经锁好了窗户，钥匙始终放在自己的口袋里。\n\n"
        "林青没有急着翻书，而是先查看门锁和窗沿。他决定等管理员回来后，"
        "问清昨天最后离开书房的人是谁，再核对借阅记录。\n", encoding="utf-8")
    out = tmp_path / "分析"
    result = run(standalone, "analyze_enhanced.py", "--txt-path", novel,
                 "--out-dir", out, "--organized-output", "--common-workflow")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (out / "report.md").is_file()
    source = (out / "data" / "llm_source_pack_detailed.md").read_text(encoding="utf-8")
    assert "林青" in source and "[CH001-P" in source
    assert "\ufffd" not in source and "??" not in source


def test_plugin_matches_canonical_runtime():
    result = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/sync_plugin.py"), "--check"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr

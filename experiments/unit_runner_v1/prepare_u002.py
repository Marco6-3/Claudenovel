"""Prepare a non-canon U002 experiment from explicitly selected old inputs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent_writer.storage import read_text, sha256_file, write_json_atomic, write_text_atomic


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-project", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise ValueError("out-dir must be new")
    contracts = [args.source_project / f"chapter_contracts/chapter_{i:04d}_contract.json" for i in (3, 4, 5)]
    payloads = [json.loads(read_text(p)) for p in contracts]
    sources = contracts + [args.source_project / f"accepted/chapter_{i:04d}.md" for i in (1, 2)]
    # Only the two shared entry chapters. No previous machine continuation prose.
    context = "\n\n".join(f"# 前情第{i}章\n\n{read_text(sources[i + 2])}" for i in (1, 2))
    unique = lambda values: list(dict.fromkeys(values))
    brief = {
        "title": "食堂里吃不饱的人",
        "premise": "接续所选正式前情，完成一个校园灵异单元。以下来自此前作者任务输入，章节切分可以调整：\n" + "\n".join(p["idea_contract"]["source_text"] for p in payloads),
        "ending": "案件局部闭合，王磊暂时脱险，关系只推进到秦思妍明确追问而非恋爱。" + payloads[-1]["ending_hook"],
        "author_locks": unique([lock for p in payloads for lock in [*p["idea_contract"]["idea_locks"], *p.get("arc_author_locks", [])]]),
        "forbidden_changes": unique([value for p in payloads for value in p["idea_contract"]["forbidden_changes"]]),
        "style": "限制性第三人称贴近凌默，延续前两章中文口吻。通过具体人物动作呈现，不把准备、验证和记录写成重复清单。章节数量与切分由故事需要决定。",
        "max_chars": 14999, "preferred_chars": 10000,
    }
    write_json_atomic(args.out_dir / "brief.json", brief)
    write_text_atomic(args.out_dir / "前情.md", context)
    write_json_atomic(args.out_dir / "sources.json", {
        "source_hashes": {str(p): sha256_file(p) for p in sources},
        "scope": "仅使用历史作者任务输入和共同前情第1—2章；新稿不进入正式 accepted。",
    })
    print(str(args.out_dir))


if __name__ == "__main__":
    main()

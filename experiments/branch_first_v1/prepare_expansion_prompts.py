from __future__ import annotations

import argparse
import json
from pathlib import Path


def render(public_prompt: str, card: dict) -> str:
    return (
        "# Branch-first 正文扩写任务\n\n"
        "你是隔离的正文 Writer。不得搜索或读取原小说目标章、private、gold、其他分支卡、其他正文候选、"
        "选择分数、评审或映射。\n\n"
        "下方公开任务书中的人类外部创意、创意锁和禁改项仍是最高真源。Branch Card 只是在 freedom budget 内"
        "已通过筛选的一条实现路线；若两者看似冲突，以公开任务书为准并采用最小必要调整。\n\n"
        "必须完整兑现 Branch Card 的 core_mechanism、character_choice、real_cost、五个 beats 与 end_hook。"
        "不要额外加入第二套核心解法、突然得到的新关键道具、第三方救场或卡片外反转。"
        "卡片是规划信息，不得在正文中提到 branch、card、benchmark 或写作流程。\n\n"
        "只输出标题和 2600–3600 个汉字的正文。\n\n"
        "## 公开写作任务书\n\n"
        f"{public_prompt}\n\n"
        "## 已选 Branch Card\n\n"
        f"{json.dumps(card, ensure_ascii=False, indent=2)}\n"
    )


def prepare(public_run: Path, branch_run: Path, case_ids: list[str]) -> list[str]:
    written: list[str] = []
    for case_id in case_ids:
        selection = json.loads((branch_run / case_id / "selection" / "result.json").read_text(encoding="utf-8"))
        if selection.get("status") != "selected":
            raise ValueError(f"branch selection is not stable for {case_id}")
        public_prompt = (public_run / case_id / "public" / "writer_prompt.md").read_text(encoding="utf-8")
        for branch_id in selection["selected_branches"]:
            card = json.loads((branch_run / case_id / "branch_cards" / f"{branch_id}.json").read_text(encoding="utf-8"))
            target = branch_run / case_id / "expansion_prompts" / f"{branch_id}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render(public_prompt, card), encoding="utf-8")
            written.append(str(target))
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare full-prose prompts for selected Branch Cards")
    parser.add_argument("--public-run", type=Path, required=True)
    parser.add_argument("--branch-run", type=Path, required=True)
    parser.add_argument("--case", action="append", required=True)
    args = parser.parse_args(argv)
    written = prepare(args.public_run, args.branch_run, args.case)
    print(json.dumps({"written": written}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

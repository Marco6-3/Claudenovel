from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


HEADING_RE = re.compile(r"^第([〇零一二两三四五六七八九十百千万0-9]+)\s*章(?:\s+(.+))?$")
CN_DIGITS = {"〇": 0, "零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
CN_UNITS = {"十": 10, "百": 100, "千": 1000, "万": 10000}


def chinese_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    total = 0
    section = 0
    number = 0
    for char in value:
        if char in CN_DIGITS:
            number = CN_DIGITS[char]
            continue
        unit = CN_UNITS.get(char)
        if unit is None:
            raise ValueError(f"unsupported Chinese chapter number: {value}")
        if unit == 10000:
            section = (section + number) * unit
            total += section
            section = 0
            number = 0
        else:
            if number == 0:
                number = 1
            section += number * unit
            number = 0
    return total + section + number


def read_early_chapters(source: Path, max_chapter: int) -> dict[int, dict[str, str]]:
    """Read line-by-line and stop before max_chapter + 1; never scan the later novel."""
    chapters: dict[int, dict[str, str]] = {}
    current_number: int | None = None
    current_title = ""
    body_lines: list[str] = []

    def flush() -> None:
        if current_number is None or current_number > max_chapter:
            return
        body = "".join(body_lines).replace("\r", "")
        body = re.sub(r"(?m)^\s*\?\s*$", "", body)
        body = re.sub(r"(?m)^\s*-{8,}\s*$", "", body)
        chapters[current_number] = {"title": current_title, "body": body.strip()}

    with source.open("r", encoding="utf-8", newline=None) as handle:
        for line in handle:
            match = HEADING_RE.match(line.strip())
            if match:
                flush()
                number = chinese_number(match.group(1))
                if number > max_chapter:
                    break
                current_number = number
                current_title = (match.group(2) or "").strip()
                body_lines = []
            elif current_number is not None:
                body_lines.append(line)
        else:
            flush()
    return chapters


def _render_prompt(case: dict[str, Any], chapters: dict[int, dict[str, str]]) -> str:
    context_blocks: list[str] = []
    for number in case["recent_context_chapters"]:
        chapter = chapters[number]
        context_blocks.append(f"### 可见原文 CH{number:03d}《{chapter['title']}》\n\n{chapter['body']}")
    bullet = lambda values: "\n".join(f"- {value}" for value in values)
    return (
        "# 《地府微信群》前期留出原章写作 Benchmark\n\n"
        "## 数据隔离\n\n"
        f"你要写的是第 {case['target_chapter']} 章位置上的一个完整候选单元。"
        "不得搜索、读取或推测性引用目标原章、gold_private.json、其他候选或评审结果。"
        "只能使用本提示词中的公开状态和可见原文。\n\n"
        "## 外部创意（最高优先级）\n\n"
        f"{case['external_idea']}\n\n"
        "## 当前公开状态\n\n"
        f"{bullet(case['public_state'])}\n\n"
        "## 创意锁\n\n"
        f"{bullet(case['idea_locks'])}\n\n"
        "## 禁止改动\n\n"
        f"{bullet(case['forbidden_changes'])}\n\n"
        "## 自由预算\n\n"
        f"{bullet(case['freedom_budget'])}\n\n"
        "## 成功标准\n\n"
        f"{bullet(case['success_criteria'])}\n\n"
        "## 可见原文（只到切点）\n\n"
        f"{'\n\n'.join(context_blocks)}\n\n"
        "## 输出要求\n\n"
        "- 写 2600–3600 个汉字，第三人称贴近陈默。\n"
        "- 延续前文网络化轻喜剧、短段落和内心吐槽，但不要机械复制口头禅。\n"
        "- 当前冲突必须推进并产生局部兑现；可以留尾钩，但不能把整章变成铺垫。\n"
        "- 只输出标题和正文，不解释推理，不提 benchmark、候选或原作者。\n"
    )


def build(
    source: Path,
    public_cases_path: Path,
    private_gold_path: Path,
    out_dir: Path,
    *,
    case_ids: set[str] | None = None,
    include_private_gold_text: bool = False,
) -> list[dict[str, str]]:
    public_payload = json.loads(public_cases_path.read_text(encoding="utf-8"))
    private_payload = json.loads(private_gold_path.read_text(encoding="utf-8"))
    cases = [case for case in public_payload["cases"] if not case_ids or case["id"] in case_ids]
    if case_ids and {case["id"] for case in cases} != case_ids:
        missing = ", ".join(sorted(case_ids - {case["id"] for case in cases}))
        raise ValueError(f"unknown case ids: {missing}")
    chapters = read_early_chapters(source, max(case["target_chapter"] for case in cases))
    built: list[dict[str, str]] = []
    for case in cases:
        case_dir = out_dir / case["id"]
        public_dir = case_dir / "public"
        private_dir = case_dir / "private"
        public_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = public_dir / "writer_prompt.md"
        contract_path = public_dir / "idea_contract.json"
        prompt_path.write_text(_render_prompt(case, chapters), encoding="utf-8")
        contract_path.write_text(json.dumps(case, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        record = {"case_id": case["id"], "prompt": str(prompt_path), "contract": str(contract_path)}
        if include_private_gold_text:
            private_dir.mkdir(parents=True, exist_ok=True)
            target = chapters[case["target_chapter"]]
            gold_path = private_dir / "original_target.md"
            gold_meta_path = private_dir / "gold.json"
            gold_path.write_text(f"{target['title']}\n\n{target['body']}\n", encoding="utf-8")
            gold_meta_path.write_text(
                json.dumps(private_payload["cases"][case["id"]], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            record.update({"gold_text": str(gold_path), "gold_meta": str(gold_meta_path)})
        built.append(record)
    manifest_path = out_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps({"cases": built}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return built


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build leakage-controlled early-novel writing benchmark prompts")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--case", action="append", default=[])
    parser.add_argument("--include-private-gold-text", action="store_true")
    args = parser.parse_args(argv)
    here = Path(__file__).resolve().parent
    built = build(
        args.source,
        here / "cases_public.json",
        here / "gold_private.json",
        args.out_dir,
        case_ids=set(args.case) or None,
        include_private_gold_text=args.include_private_gold_text,
    )
    print(json.dumps({"built": built}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

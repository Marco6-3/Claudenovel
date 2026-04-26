from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
import re


ROOT = Path(__file__).resolve().parent
TXT = next(ROOT.glob("*.txt"))
OUT = ROOT / "novel_analysis"
OUT.mkdir(exist_ok=True)


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-16", "utf-8-sig", "utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-16", errors="replace")


def parse_chapters(text: str) -> list[dict]:
    chap_pat = re.compile(r"(?m)^(第[\u4e00-\u9fff0-9]+章\s+[^\n\r]+)\s*$")
    vol_pat = re.compile(r"(?m)^(第[\u4e00-\u9fff0-9]+卷\s+[^\n\r]+)\s*$")
    chap_ms = list(chap_pat.finditer(text))
    vol_ms = list(vol_pat.finditer(text))
    chapters = []
    for i, m in enumerate(chap_ms):
        start = m.end()
        end = chap_ms[i + 1].start() if i + 1 < len(chap_ms) else len(text)
        vol = ""
        for vm in vol_ms:
            if vm.start() < m.start():
                vol = vm.group(1).strip()
            else:
                break
        body = text[start:end]
        paras = [
            re.sub(r"\s+", " ", x.strip())
            for x in re.split(r"\n\s*\n|\r\n\s*\r\n", body)
            if len(x.strip()) > 10
        ]
        chapters.append(
            {
                "global_index": i + 1,
                "volume": vol,
                "title": m.group(1).strip(),
                "chars": len(body),
                "first": paras[0][:260] if paras else "",
                "last": paras[-1][-220:] if paras else "",
                "body": body,
            }
        )
    return chapters


CORE_NAMES = [
    "陳默",
    "秦思妍",
    "楊晴",
    "林蕭",
    "王冬",
    "顧盼",
    "楊七郎",
    "判官",
    "閻羅王",
    "閻王",
    "夜遊神",
    "轉輪王",
    "孟婆",
    "小可",
    "黑無常",
    "白無常",
    "富鬼",
    "甄歡喜",
    "李天樂",
    "茵茵",
    "董振國",
    "林正祿",
    "麥天祐",
    "驪山老祖",
    "九子鬼母",
    "三瞳鬼母",
    "秦廣王",
    "白龍",
    "離淵",
    "窮奇",
    "刀勞鬼",
    "茶茶",
    "胡天霸",
    "尚峰",
    "雷妄",
    "虛空尊者",
    "薇薇安",
    "魔主",
    "昊天",
    "陳莫",
]


def volume_summary(chapters: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for ch in chapters:
        grouped[ch["volume"]].append(ch)
    rows = []
    for volume, cs in grouped.items():
        seg = "\n".join(c["body"] for c in cs)
        rows.append(
            {
                "volume": volume,
                "start_chapter": cs[0]["global_index"],
                "end_chapter": cs[-1]["global_index"],
                "chapter_count": len(cs),
                "chars": sum(c["chars"] for c in cs),
                "top_names": [
                    [name, seg.count(name)]
                    for name in sorted(CORE_NAMES, key=lambda n: seg.count(n), reverse=True)
                    if seg.count(name) > 5
                ][:15],
            }
        )
    return rows


def name_matrix(chapters: list[dict]) -> dict:
    total = Counter()
    first_last = {}
    by_chapter = defaultdict(list)
    for ch in chapters:
        body = ch["body"]
        for name in CORE_NAMES:
            n = body.count(name)
            if n:
                total[name] += n
                by_chapter[name].append(ch["global_index"])
    for name, nums in by_chapter.items():
        first_last[name] = [min(nums), max(nums), len(nums)]
    co = Counter()
    for ch in chapters:
        present = [name for name in CORE_NAMES if ch["body"].count(name) > 0]
        for i, a in enumerate(present):
            for b in present[i + 1 :]:
                co[tuple(sorted((a, b)))] += 1
    return {
        "occurrences": total.most_common(),
        "first_last_chapter_span": first_last,
        "cooccurrence_top": [[a, b, n] for (a, b), n in co.most_common(80)],
    }


def write_outputs(text: str, chapters: list[dict]) -> None:
    toc_lines = ["# 《地府微信群》卷章目录\n"]
    current = None
    for ch in chapters:
        if ch["volume"] != current:
            current = ch["volume"]
            toc_lines.append(f"\n## {current}\n")
        toc_lines.append(f"- {ch['global_index']:03d}. {ch['title']}（{ch['chars']}字）")
    (OUT / "章节目录.md").write_text("\n".join(toc_lines), encoding="utf-8")

    briefs = []
    for ch in chapters:
        briefs.append(
            {
                "global_index": ch["global_index"],
                "volume": ch["volume"],
                "title": ch["title"],
                "chars": ch["chars"],
                "first": ch["first"],
                "last": ch["last"],
            }
        )
    (OUT / "chapter_briefs.json").write_text(
        json.dumps(briefs, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "volume_stats.json").write_text(
        json.dumps(volume_summary(chapters), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "name_stats.json").write_text(
        json.dumps(name_matrix(chapters), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    key_terms = [
        "伏筆",
        "前世",
        "輪迴",
        "封印",
        "魔主",
        "薇薇安",
        "秦思妍",
        "楊七郎",
        "判官",
        "小可",
        "功德",
        "鬼使",
        "鬼王",
        "地府",
        "冥界",
        "天庭",
    ]
    concordance = {}
    for term in key_terms:
        hits = []
        for m in re.finditer(re.escape(term), text):
            left = max(0, m.start() - 80)
            right = min(len(text), m.end() + 120)
            hits.append(re.sub(r"\s+", " ", text[left:right]))
            if len(hits) >= 25:
                break
        concordance[term] = hits
    (OUT / "关键词上下文.json").write_text(
        json.dumps(concordance, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> None:
    text = read_text(TXT)
    chapters = parse_chapters(text)
    write_outputs(text, chapters)
    print(
        json.dumps(
            {
                "file": TXT.name,
                "chars": len(text),
                "chapters": len(chapters),
                "outputs": [p.name for p in OUT.iterdir()],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

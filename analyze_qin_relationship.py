from __future__ import annotations

from pathlib import Path
import json
import re


ROOT = Path(__file__).resolve().parent
TXT = next(ROOT.glob("*.txt"))
OUT = ROOT / "novel_analysis"
OUT.mkdir(exist_ok=True)


def read_text(path: Path) -> str:
    return path.read_bytes().decode("utf-16")


def chapters(text: str) -> list[dict]:
    chap_pat = re.compile(r"(?m)^(第[\u4e00-\u9fff0-9]+章\s+[^\n\r]+)\s*$")
    vol_pat = re.compile(r"(?m)^(第[\u4e00-\u9fff0-9]+卷\s+[^\n\r]+)\s*$")
    chap_ms = list(chap_pat.finditer(text))
    vol_ms = list(vol_pat.finditer(text))
    rows = []
    for i, m in enumerate(chap_ms):
        start = m.end()
        end = chap_ms[i + 1].start() if i + 1 < len(chap_ms) else len(text)
        body = text[start:end]
        vol = ""
        for vm in vol_ms:
            if vm.start() < m.start():
                vol = vm.group(1).strip()
            else:
                break
        rows.append(
            {
                "idx": i + 1,
                "volume": vol,
                "title": m.group(1).strip(),
                "body": body,
                "qin_mentions": body.count("秦思妍"),
                "chen_mentions": body.count("陳默"),
            }
        )
    return rows


def snippets(body: str, terms: list[str], limit: int = 4) -> list[str]:
    hits = []
    for term in terms:
        for m in re.finditer(re.escape(term), body):
            s = max(0, m.start() - 120)
            e = min(len(body), m.end() + 180)
            hit = re.sub(r"\s+", " ", body[s:e]).strip()
            if hit not in hits:
                hits.append(hit)
            if len(hits) >= limit:
                return hits
    return hits


def main() -> None:
    text = read_text(TXT)
    chs = chapters(text)
    rows = []
    for ch in chs:
        if ch["qin_mentions"]:
            rows.append(
                {
                    "idx": ch["idx"],
                    "volume": ch["volume"],
                    "title": ch["title"],
                    "qin_mentions": ch["qin_mentions"],
                    "chen_mentions": ch["chen_mentions"],
                    "snippets": snippets(
                        ch["body"],
                        [
                            "秦思妍",
                            "思妍",
                            "女朋友",
                            "不記得",
                            "失憶",
                            "阿默",
                            "兵解",
                        ],
                        3,
                    ),
                }
            )
    key_terms = {
        "初次被提及": ["校花秦思妍", "秦思妍"],
        "主动接近": ["我想追你", "喜歡你", "喜欢你", "女朋友"],
        "亲密关系": ["老婆", "牽手", "抱", "親", "阿默"],
        "失忆陌路": ["不記得自己", "你認識我", "失憶", "陌路"],
        "终局告别": ["阿默，對不起", "兵解轉世", "下輩子再相愛", "漫天飛雪"],
    }
    term_hits = {}
    for label, terms in key_terms.items():
        term_hits[label] = []
        for ch in chs:
            if any(t in ch["body"] or t in ch["title"] for t in terms):
                term_hits[label].append(
                    {
                        "idx": ch["idx"],
                        "volume": ch["volume"],
                        "title": ch["title"],
                        "snippets": snippets(ch["body"], terms, 3),
                    }
                )
    data = {
        "source": TXT.name,
        "chapters_with_qin": len(rows),
        "total_qin_mentions": sum(r["qin_mentions"] for r in rows),
        "top_qin_chapters": sorted(rows, key=lambda r: r["qin_mentions"], reverse=True)[:30],
        "all_qin_chapters": rows,
        "term_hits": term_hits,
    }
    (OUT / "陈默秦思妍感情线素材.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "chapters_with_qin": data["chapters_with_qin"],
                "total_qin_mentions": data["total_qin_mentions"],
                "top": [
                    [r["idx"], r["volume"], r["title"], r["qin_mentions"]]
                    for r in data["top_qin_chapters"][:12]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

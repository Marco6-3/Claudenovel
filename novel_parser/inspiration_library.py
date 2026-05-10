"""Reusable inspiration case library for web-novel plot mechanisms.

This module stores public references, metadata, short excerpts, and mechanism
notes. It intentionally avoids storing full chapter text: the goal is to learn
transferable structure, not copy prose, names, or complete event chains.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import unescape
from pathlib import Path
from typing import Any, Iterable


MAX_EXCERPT_CHARS = 1200
MAX_NOTE_CHARS = 2400


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(text: str, fallback: str = "case") -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text.lower(), flags=re.UNICODE)
    cleaned = cleaned.strip("-")
    return cleaned[:80] or fallback


def _split_tags(raw: str | Iterable[str] | None) -> list[str]:
    if raw is None:
        return []
    parts = re.split(r"[,，、|\s]+", raw) if isinstance(raw, str) else list(raw)
    tags: list[str] = []
    seen: set[str] = set()
    for item in parts:
        tag = str(item).strip()
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def _compact_text(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _trim(text: str, limit: int) -> str:
    text = _compact_text(text)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _extract_title(html: str, url: str) -> str:
    patterns = [
        r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)[\"']",
        r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']og:title[\"']",
        r"<title[^>]*>(.*?)</title>",
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.I | re.S)
        if match:
            return _compact_text(match.group(1))
    return url


def _fetch_url(url: str, timeout: int = 30) -> tuple[str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "claudenovel-inspiration-library/1.0 "
                "(stores metadata and short excerpts only)"
            )
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        content_type = resp.headers.get("content-type", "")
    encoding = "utf-8"
    match = re.search(r"charset=([\w.-]+)", content_type, flags=re.I)
    if match:
        encoding = match.group(1)
    return raw.decode(encoding, errors="replace"), content_type


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{2,}", text.lower())


def _score_terms(text: str, terms: list[str]) -> float:
    hay = text.lower()
    score = 0.0
    for term in terms:
        score += hay.count(term.lower()) * 3
    score += len(set(_tokens(text)) & set(terms)) * 2
    return score


def _infer_tags(text: str) -> list[str]:
    rules = [
        ("误会", ["误会", "没告诉", "隐瞒", "看见", "撞见", "解释不了"]),
        ("情感爆点", ["伤心", "绝望", "崩溃", "跳崖", "自尽", "求死", "恳求"]),
        ("地图切换", ["上界", "新地图", "副本", "秘境", "空间乱流", "飞升"]),
        ("师徒转折", ["收徒", "前辈", "大能", "师父", "天赋"]),
        ("强弱反转", ["无敌", "碾压", "修为更高", "杀了主角", "挡不住"]),
        ("代价选择", ["条件", "恳求", "答应", "不要杀", "交换"]),
        ("旧甜回刺", ["来过", "很甜", "故地", "回忆", "约定"]),
        ("追妻火葬场", ["妻子", "追来", "不原谅", "后悔", "错过"]),
    ]
    return [tag for tag, keys in rules if any(key in text for key in keys)]


def _deconstruct(text: str, tags: list[str]) -> dict[str, Any]:
    mechanisms: list[str] = []
    if "误会" in tags:
        mechanisms.append("用信息差撕开亲密关系：读者知道可解释，角色暂时无法解释。")
    if "旧甜回刺" in tags:
        mechanisms.append("把旧甜蜜地点反转成创伤现场，让回忆本身变成压力。")
    if "地图切换" in tags:
        mechanisms.append("用情感危机触发地图升级，而不是机械宣布开新副本。")
    if "师徒转折" in tags:
        mechanisms.append("用高位导师收徒，把女主从被保护对象推成独立成长线。")
    if "强弱反转" in tags:
        mechanisms.append("在主角局部无敌后引入更高层强者，恢复力量压迫感。")
    if "代价选择" in tags:
        mechanisms.append("用保命条件逼角色做价值选择，制造不可逆分离。")
    if not mechanisms:
        mechanisms.append("待人工拆解：补充情绪触发、转折机制、可迁移写法。")

    return {
        "logline": _trim(text, 180),
        "appeal": "情绪爆点、关系撕裂、地图升级、人物独立线",
        "mechanisms": mechanisms,
        "reuse_without_copying": [
            "替换人物关系、误会对象、旧地点意义和高位势力设定。",
            "保留结构功能，不复用原文表达、专名和完整事件链。",
            "把外部高人改造成当前世界观内已有势力或未回收伏笔的承接者。",
        ],
        "risk_notes": [
            "误会过重会显得角色降智，需要给双方合理的信息限制。",
            "跳崖/求死桥段强度很高，必须服务人物弧光，避免廉价虐点。",
            "外部大能介入容易削弱主角，需要让主角行动但暂时无法胜出。",
        ],
    }


@dataclass
class InspirationCase:
    id: str
    title: str
    source_url: str = ""
    source_type: str = "manual"
    platform: str = ""
    author: str = ""
    rating: float | None = None
    heat: int | None = None
    discussion_count: int | None = None
    tags: list[str] = field(default_factory=list)
    excerpt: str = ""
    note: str = ""
    deconstruction: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)


def library_path(library_dir: Path) -> Path:
    return library_dir / "inspiration_library.json"


def _load_library(library_dir: Path) -> dict[str, Any]:
    path = library_path(library_dir)
    if not path.exists():
        return {"version": 1, "cases": []}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("version", 1)
    data.setdefault("cases", [])
    return data


def _save_library(library_dir: Path, data: dict[str, Any]) -> None:
    path = library_path(library_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _next_id(data: dict[str, Any], title: str) -> str:
    base = _slug(title)
    existing = {case.get("id") for case in data.get("cases", [])}
    candidate = base
    index = 2
    while candidate in existing:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _case_text(case: dict[str, Any]) -> str:
    parts = [
        case.get("title", ""),
        case.get("platform", ""),
        " ".join(case.get("tags", []) or []),
        case.get("excerpt", ""),
        case.get("note", ""),
        json.dumps(case.get("deconstruction", {}), ensure_ascii=False),
    ]
    return "\n".join(str(part) for part in parts if part)


def _add_case(library_dir: Path, case: InspirationCase) -> dict[str, Any]:
    data = _load_library(library_dir)
    if not case.id:
        case.id = _next_id(data, case.title)
    now = _now_iso()
    for idx, existing in enumerate(data["cases"]):
        if existing.get("id") == case.id or (
            case.source_url and existing.get("source_url") == case.source_url
        ):
            payload = asdict(case)
            payload["created_at"] = existing.get("created_at") or now
            payload["updated_at"] = now
            data["cases"][idx] = payload
            _save_library(library_dir, data)
            return {"status": "updated", "case": payload, "path": str(library_path(library_dir))}
    payload = asdict(case)
    data["cases"].append(payload)
    _save_library(library_dir, data)
    return {"status": "added", "case": payload, "path": str(library_path(library_dir))}


def _build_case(
    *,
    title: str,
    excerpt: str,
    note: str = "",
    tags_raw: str = "",
    source_url: str = "",
    source_type: str = "manual",
    platform: str = "",
    author: str = "",
    rating: float | None = None,
    heat: int | None = None,
    discussion_count: int | None = None,
    case_id: str = "",
    max_excerpt_chars: int = MAX_EXCERPT_CHARS,
) -> InspirationCase:
    tags = _split_tags(tags_raw)
    text_for_analysis = "\n".join([title, excerpt or "", note or "", " ".join(tags)])
    tags = list(dict.fromkeys([*tags, *_infer_tags(text_for_analysis)]))
    return InspirationCase(
        id=case_id,
        title=title,
        source_url=source_url,
        source_type=source_type,
        platform=platform,
        author=author,
        rating=rating,
        heat=heat,
        discussion_count=discussion_count,
        tags=tags,
        excerpt=_trim(excerpt, max_excerpt_chars),
        note=_trim(note, MAX_NOTE_CHARS),
        deconstruction=_deconstruct(text_for_analysis, tags),
    )


def cmd_add_manual(args: argparse.Namespace) -> int:
    case = _build_case(
        title=args.title,
        excerpt=args.excerpt or "",
        note=args.note or "",
        tags_raw=args.tags or "",
        source_url=args.source_url or "",
        source_type="manual",
        platform=args.platform or "",
        author=args.author or "",
        rating=args.rating,
        heat=args.heat,
        discussion_count=args.discussion_count,
        case_id=args.id or "",
        max_excerpt_chars=args.max_excerpt_chars,
    )
    print(json.dumps(_add_case(args.library_dir, case), ensure_ascii=False, indent=2))
    return 0


def cmd_add_file(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = path.read_text(encoding=args.encoding, errors="replace")
    case = _build_case(
        title=args.title or path.stem,
        excerpt=text,
        note=args.note or "",
        tags_raw=args.tags or "",
        source_url=args.source_url or "",
        source_type="file_excerpt",
        platform=args.platform or "",
        author=args.author or "",
        rating=args.rating,
        heat=args.heat,
        discussion_count=args.discussion_count,
        case_id=args.id or "",
        max_excerpt_chars=args.max_excerpt_chars,
    )
    print(json.dumps(_add_case(args.library_dir, case), ensure_ascii=False, indent=2))
    return 0


def cmd_add_url(args: argparse.Namespace) -> int:
    html, content_type = _fetch_url(args.url, timeout=args.timeout)
    title = args.title or _extract_title(html, args.url)
    page_text = _compact_text(html)
    case = _build_case(
        title=title,
        excerpt=page_text,
        note=args.note or f"Fetched content-type: {content_type}",
        tags_raw=args.tags or "",
        source_url=args.url,
        source_type="url_excerpt",
        platform=args.platform or "",
        author=args.author or "",
        rating=args.rating,
        heat=args.heat,
        discussion_count=args.discussion_count,
        case_id=args.id or "",
        max_excerpt_chars=args.max_excerpt_chars,
    )
    print(json.dumps(_add_case(args.library_dir, case), ensure_ascii=False, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    data = _load_library(args.library_dir)
    cases = data.get("cases", [])
    if args.tag:
        cases = [case for case in cases if args.tag in (case.get("tags") or [])]
    rows = [
        {
            "id": case.get("id"),
            "title": case.get("title"),
            "tags": case.get("tags", []),
            "rating": case.get("rating"),
            "heat": case.get("heat"),
            "discussion_count": case.get("discussion_count"),
            "source_url": case.get("source_url"),
        }
        for case in cases[: args.limit]
    ]
    print(json.dumps({"count": len(cases), "cases": rows}, ensure_ascii=False, indent=2))
    return 0


def _rank_cases(data: dict[str, Any], query: str, tag: str = "") -> list[tuple[float, dict[str, Any]]]:
    terms = _tokens(query)
    rows: list[tuple[float, dict[str, Any]]] = []
    for case in data.get("cases", []):
        score = _score_terms(_case_text(case), terms)
        if tag and tag in (case.get("tags") or []):
            score += 8
        heat = case.get("heat") or 0
        discussion = case.get("discussion_count") or 0
        rating = case.get("rating") or 0
        score += math.log10(max(heat, 0) + 1) + math.log10(max(discussion, 0) + 1)
        score += float(rating) * 0.2
        if score > 0:
            rows.append((score, case))
    rows.sort(key=lambda item: item[0], reverse=True)
    return rows


def cmd_query(args: argparse.Namespace) -> int:
    data = _load_library(args.library_dir)
    result = []
    for score, case in _rank_cases(data, args.query, args.tag)[: args.limit]:
        result.append(
            {
                "score": round(score, 3),
                "id": case.get("id"),
                "title": case.get("title"),
                "tags": case.get("tags", []),
                "source_url": case.get("source_url"),
                "excerpt": case.get("excerpt", "")[: args.excerpt_chars],
                "deconstruction": case.get("deconstruction", {}),
            }
        )
    print(json.dumps({"query": args.query, "count": len(result), "results": result}, ensure_ascii=False, indent=2))
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    data = _load_library(args.library_dir)
    selected = [case for _, case in _rank_cases(data, args.query)[: args.limit]]
    lines = [
        "# 灵感生成 Brief",
        "",
        "## 创作目标",
        "",
        args.query,
        "",
        "## 使用边界",
        "",
        "- 只学习桥段机制，不复用原文表达、专名、完整事件链。",
        "- 必须改造成当前作品的世界观、人物关系和伏笔回收。",
        "- 若案例来自公开网页，只引用链接和短摘录，不保存或输出整章正文。",
        "",
        "## 可参考案例",
        "",
    ]
    for case in selected:
        decon = case.get("deconstruction", {}) or {}
        lines.extend(
            [
                f"### {case.get('title', '')}",
                "",
                f"- ID: `{case.get('id', '')}`",
                f"- 标签: {'、'.join(case.get('tags', []) or []) or '未标注'}",
                f"- 热度/讨论/评分: {case.get('heat') or '未知'} / {case.get('discussion_count') or '未知'} / {case.get('rating') or '未知'}",
                f"- 来源: {case.get('source_url') or case.get('source_type', '')}",
                f"- 短摘录: {case.get('excerpt', '')[: args.excerpt_chars]}",
                "",
                "机制拆解:",
            ]
        )
        for mechanism in decon.get("mechanisms", []):
            lines.append(f"- {mechanism}")
        lines.extend(["", "可迁移但不可照搬:", ""])
        for item in decon.get("reuse_without_copying", []):
            lines.append(f"- {item}")
        lines.extend(["", "风险:", ""])
        for item in decon.get("risk_notes", []):
            lines.append(f"- {item}")
        lines.append("")

    lines.extend(
        [
            "## 给写作/改写 agent 的任务",
            "",
            "1. 先从当前作品已有伏笔中找承接点，不要空降同款设定。",
            "2. 生成 3-5 个原创化情节方案，每个方案写清情绪触发、反转、代价、后续回收。",
            "3. 标出哪些方案适合直接进入下一章，哪些只适合做中长期伏笔。",
        ]
    )
    content = "\n".join(lines) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
        print(json.dumps({"output": str(args.output), "case_count": len(selected)}, ensure_ascii=False, indent=2))
    else:
        print(content)
    return 0


def build_parser(default_library_dir: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect, search, and brief reusable web-novel plot mechanisms.")
    parser.add_argument("--library-dir", type=Path, default=default_library_dir, help="Directory for inspiration_library.json")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--id", default="", help="Optional stable case id")
        p.add_argument("--source-url", default="", help="Source URL")
        p.add_argument("--platform", default="", help="Source platform")
        p.add_argument("--author", default="", help="Original author or poster")
        p.add_argument("--rating", type=float, default=None, help="Rating score if known")
        p.add_argument("--heat", type=int, default=None, help="Heat/popularity number if known")
        p.add_argument("--discussion-count", type=int, default=None, help="Discussion/comment count if known")
        p.add_argument("--tags", default="", help="Comma-separated tags")
        p.add_argument("--note", default="", help="Agent note about the mechanism")
        p.add_argument("--max-excerpt-chars", type=int, default=MAX_EXCERPT_CHARS)

    p = sub.add_parser("add-manual", help="Add a manually described case")
    add_common(p)
    p.add_argument("--title", required=True, help="Case title")
    p.add_argument("--excerpt", required=True, help="Short excerpt or user-provided summary")
    p.set_defaults(func=cmd_add_manual)

    p = sub.add_parser("add-file", help="Add a case from a local excerpt file")
    add_common(p)
    p.add_argument("--title", default="", help="Case title. Defaults to the file stem.")
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--encoding", default="utf-8")
    p.set_defaults(func=cmd_add_file)

    p = sub.add_parser("add-url", help="Fetch a public URL and store only metadata plus a short excerpt")
    add_common(p)
    p.add_argument("--title", default="", help="Case title. Defaults to the page title.")
    p.add_argument("--url", required=True)
    p.add_argument("--timeout", type=int, default=30)
    p.set_defaults(func=cmd_add_url)

    p = sub.add_parser("list", help="List stored cases")
    p.add_argument("--tag", default="")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("query", help="Search similar mechanisms")
    p.add_argument("query")
    p.add_argument("--tag", default="")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--excerpt-chars", type=int, default=260)
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("brief", help="Generate an originality-safe inspiration brief")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--excerpt-chars", type=int, default=220)
    p.add_argument("--output", type=Path, default=None)
    p.set_defaults(func=cmd_brief)
    return parser


def run_cli(default_library_dir: Path, argv: list[str] | None = None) -> int:
    parser = build_parser(default_library_dir)
    args = parser.parse_args(argv)
    args.library_dir = args.library_dir.resolve()
    return args.func(args)

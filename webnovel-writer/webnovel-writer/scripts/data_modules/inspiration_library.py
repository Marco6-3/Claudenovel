#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reference inspiration library for reusable webnovel plot mechanisms.

The library stores links, metadata, short excerpts, and a structural
deconstruction of effective public examples. It intentionally does not store
full chapter text: agents should learn mechanisms, not copy source prose.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
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
    if isinstance(raw, str):
        parts = re.split(r"[|,，、\s]+", raw)
    else:
        parts = list(raw)
    out: list[str] = []
    seen: set[str] = set()
    for item in parts:
        tag = str(item).strip()
        if tag and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


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


def _fetch_url(url: str, *, timeout: int = 30) -> tuple[str, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "webnovel-writer-inspiration-library/1.0 "
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
    text = raw.decode(encoding, errors="replace")
    return text, content_type


def _tokens(text: str) -> list[str]:
    return re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{2,}", text.lower())


def _score_terms(text: str, terms: list[str]) -> float:
    hay = text.lower()
    score = 0.0
    for term in terms:
        score += hay.count(term.lower()) * 3
    token_set = set(_tokens(text))
    score += len(token_set & set(terms)) * 2
    return score


def _infer_tags(text: str) -> list[str]:
    rules = [
        ("误会", ["误会", "没告诉", "隐瞒", "看见", "撞见"]),
        ("情感爆点", ["伤心", "绝望", "崩溃", "跳崖", "自尽", "求死"]),
        ("地图切换", ["上界", "新地图", "副本", "秘境", "空间乱流"]),
        ("师徒转折", ["收徒", "前辈", "大能", "师父", "天赋"]),
        ("强弱反转", ["无敌", "碾压", "修为更高", "杀了主角"]),
        ("代价选择", ["条件", "恳求", "答应", "不要杀"]),
        ("旧甜回刺", ["来过", "很甜", "故地", "回忆"]),
        ("追妻火葬场", ["妻子", "追来", "不原谅", "伤心"]),
    ]
    tags: list[str] = []
    for tag, keys in rules:
        if any(k in text for k in keys):
            tags.append(tag)
    return tags


def _deconstruct(text: str, tags: list[str]) -> dict[str, Any]:
    """Heuristic deconstruction. Agents can refine this after reading."""
    text = _compact_text(text)
    mechanisms: list[str] = []
    if "误会" in tags:
        mechanisms.append("用信息差制造亲密关系裂缝：读者知道可解释，角色暂时无法解释。")
    if "旧甜回刺" in tags:
        mechanisms.append("把旧甜蜜地点反转成创伤现场，使回忆本身变成刀。")
    if "地图切换" in tags:
        mechanisms.append("用情感危机触发地图升级，而不是机械宣布开新副本。")
    if "师徒转折" in tags:
        mechanisms.append("用高位导师收徒把女主从被保护对象推成独立成长线。")
    if "强弱反转" in tags:
        mechanisms.append("在主角局部无敌后引入更高层强者，恢复力量压迫感。")
    if "代价选择" in tags:
        mechanisms.append("用保命条件强迫角色做价值选择，制造不可逆分离。")
    if not mechanisms:
        mechanisms.append("记录为待人工拆解桥段：需要补充情绪触发、转折机制和可迁移写法。")

    return {
        "logline": _trim(text, 180),
        "appeal": "情绪爆点、关系撕裂、地图升级、人物独立线" if mechanisms else "",
        "mechanisms": mechanisms,
        "reuse_without_copying": [
            "替换人物关系、误会对象、旧地点意义和高位势力设定。",
            "保留结构功能，不复用原文表达、专名和完整事件链。",
            "把外部高人改造成当前世界观内已有势力或未回收伏笔的承接者。",
        ],
        "risk_notes": [
            "误会桥段过重会显得角色降智，需要给双方合理信息限制。",
            "跳崖/自尽桥段属于高烈度情绪，必须服务人物弧光，避免廉价虐点。",
            "外部大能介入容易削弱主角，需要让主角付出行动但暂时无法胜出。",
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


def _library_path(project_root: Path) -> Path:
    return project_root / ".webnovel" / "inspiration_library.json"


def _load_library(project_root: Path) -> dict[str, Any]:
    path = _library_path(project_root)
    if not path.exists():
        return {"version": 1, "cases": []}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("version", 1)
    data.setdefault("cases", [])
    return data


def _save_library(project_root: Path, data: dict[str, Any]) -> None:
    path = _library_path(project_root)
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
    return "\n".join(str(p) for p in parts if p)


def _add_case(project_root: Path, case: InspirationCase) -> dict[str, Any]:
    data = _load_library(project_root)
    if not case.id:
        case.id = _next_id(data, case.title)
    now = _now_iso()
    for idx, existing in enumerate(data["cases"]):
        if existing.get("id") == case.id or (
            case.source_url and existing.get("source_url") == case.source_url
        ):
            original_created = existing.get("created_at") or now
            payload = asdict(case)
            payload["created_at"] = original_created
            payload["updated_at"] = now
            data["cases"][idx] = payload
            _save_library(project_root, data)
            return {"status": "updated", "case": payload, "path": str(_library_path(project_root))}
    payload = asdict(case)
    data["cases"].append(payload)
    _save_library(project_root, data)
    return {"status": "added", "case": payload, "path": str(_library_path(project_root))}


def cmd_add_manual(args: argparse.Namespace) -> int:
    project_root = Path(args.project_root)
    tags = _split_tags(args.tags)
    text_for_analysis = "\n".join([args.title, args.excerpt or "", args.note or "", " ".join(tags)])
    tags = list(dict.fromkeys([*tags, *_infer_tags(text_for_analysis)]))
    case = InspirationCase(
        id=args.id or "",
        title=args.title,
        source_url=args.source_url or "",
        source_type="manual",
        platform=args.platform or "",
        author=args.author or "",
        rating=args.rating,
        heat=args.heat,
        discussion_count=args.discussion_count,
        tags=tags,
        excerpt=_trim(args.excerpt or "", args.max_excerpt_chars),
        note=_trim(args.note or "", MAX_NOTE_CHARS),
        deconstruction=_deconstruct(text_for_analysis, tags),
    )
    print(json.dumps(_add_case(project_root, case), ensure_ascii=False, indent=2))
    return 0


def cmd_add_file(args: argparse.Namespace) -> int:
    path = Path(args.file)
    text = path.read_text(encoding=args.encoding, errors="replace")
    title = args.title or path.stem
    note = args.note or ""
    tags = _split_tags(args.tags)
    text_for_analysis = "\n".join([title, text, note, " ".join(tags)])
    tags = list(dict.fromkeys([*tags, *_infer_tags(text_for_analysis)]))
    case = InspirationCase(
        id=args.id or "",
        title=title,
        source_url=args.source_url or "",
        source_type="file_excerpt",
        platform=args.platform or "",
        author=args.author or "",
        rating=args.rating,
        heat=args.heat,
        discussion_count=args.discussion_count,
        tags=tags,
        excerpt=_trim(text, args.max_excerpt_chars),
        note=_trim(note, MAX_NOTE_CHARS),
        deconstruction=_deconstruct(text_for_analysis, tags),
    )
    print(json.dumps(_add_case(Path(args.project_root), case), ensure_ascii=False, indent=2))
    return 0


def cmd_add_url(args: argparse.Namespace) -> int:
    html, content_type = _fetch_url(args.url, timeout=args.timeout)
    title = args.title or _extract_title(html, args.url)
    page_text = _compact_text(html)
    tags = _split_tags(args.tags)
    text_for_analysis = "\n".join([title, page_text, args.note or "", " ".join(tags)])
    tags = list(dict.fromkeys([*tags, *_infer_tags(text_for_analysis)]))
    case = InspirationCase(
        id=args.id or "",
        title=title,
        source_url=args.url,
        source_type="url_excerpt",
        platform=args.platform or "",
        author=args.author or "",
        rating=args.rating,
        heat=args.heat,
        discussion_count=args.discussion_count,
        tags=tags,
        excerpt=_trim(page_text, args.max_excerpt_chars),
        note=_trim(args.note or f"Fetched content-type: {content_type}", MAX_NOTE_CHARS),
        deconstruction=_deconstruct(text_for_analysis, tags),
    )
    print(json.dumps(_add_case(Path(args.project_root), case), ensure_ascii=False, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    data = _load_library(Path(args.project_root))
    cases = data.get("cases", [])
    if args.tag:
        cases = [c for c in cases if args.tag in (c.get("tags") or [])]
    rows = [
        {
            "id": c.get("id"),
            "title": c.get("title"),
            "tags": c.get("tags", []),
            "rating": c.get("rating"),
            "heat": c.get("heat"),
            "source_url": c.get("source_url"),
        }
        for c in cases[: args.limit]
    ]
    print(json.dumps({"count": len(cases), "cases": rows}, ensure_ascii=False, indent=2))
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    data = _load_library(Path(args.project_root))
    terms = _tokens(args.query)
    rows: list[tuple[float, dict[str, Any]]] = []
    for case in data.get("cases", []):
        score = _score_terms(_case_text(case), terms)
        if args.tag and args.tag in (case.get("tags") or []):
            score += 8
        heat = case.get("heat") or 0
        discussion = case.get("discussion_count") or 0
        rating = case.get("rating") or 0
        score += math.log10(max(heat, 0) + 1) + math.log10(max(discussion, 0) + 1)
        score += float(rating) * 0.2
        if score > 0:
            rows.append((score, case))
    rows.sort(key=lambda x: x[0], reverse=True)
    result = []
    for score, case in rows[: args.limit]:
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
    data = _load_library(Path(args.project_root))
    terms = _tokens(args.query)
    scored: list[tuple[float, dict[str, Any]]] = []
    for case in data.get("cases", []):
        score = _score_terms(_case_text(case), terms)
        if score:
            scored.append((score, case))
    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [case for _, case in scored[: args.limit]]
    lines = [
        "# 灵感生成 Brief",
        "",
        f"## 创作目标",
        "",
        args.query,
        "",
        "## 使用边界",
        "",
        "- 只学习桥段机制，不复用原文表达、专名、完整事件链。",
        "- 必须把案例改造为当前作品的世界观、人物关系和伏笔回收。",
        "- 若案例来自公开网站，只引用链接和短摘录，不保存或输出整章正文。",
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
                f"- Tags: {'、'.join(case.get('tags', []) or []) or '无'}",
                f"- URL: {case.get('source_url') or '无'}",
                f"- 短摘录: {case.get('excerpt', '')[:240]}",
                "- 机制:",
            ]
        )
        for item in decon.get("mechanisms", []) or []:
            lines.append(f"  - {item}")
        lines.extend(["- 原创化改造建议:"])
        for item in decon.get("reuse_without_copying", []) or []:
            lines.append(f"  - {item}")
        lines.append("")
    lines.extend(
        [
            "## 生成任务",
            "",
            "请基于上面的机制，输出 5 个原创情节想法。每个想法必须包含：",
            "",
            "- 情节钩子",
            "- 情绪触发点",
            "- 人物误判或信息差",
            "- 地图/势力升级方式",
            "- 主角短期失败或代价",
            "- 如何接入当前作品已有伏笔",
            "- 必须避免的雷同点",
        ]
    )
    output = "\n".join(lines)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
        print(json.dumps({"status": "written", "output": str(output_path), "case_count": len(selected)}, ensure_ascii=False, indent=2))
    else:
        print(output)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Webnovel inspiration library")
    parser.add_argument("--project-root", required=True, help="书项目根目录")
    sub = parser.add_subparsers(dest="action", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--id", default="", help="可选案例 ID")
        p.add_argument("--title", default="", help="案例标题")
        p.add_argument("--source-url", default="", help="来源链接")
        p.add_argument("--platform", default="", help="平台/论坛/站点")
        p.add_argument("--author", default="", help="作者或发帖人")
        p.add_argument("--rating", type=float, default=None, help="评分")
        p.add_argument("--heat", type=int, default=None, help="热度/收藏/点赞等数值")
        p.add_argument("--discussion-count", type=int, default=None, help="评论/讨论数量")
        p.add_argument("--tags", default="", help="逗号/竖线分隔标签")
        p.add_argument("--note", default="", help="人工观察或讨论摘要")
        p.add_argument("--max-excerpt-chars", type=int, default=MAX_EXCERPT_CHARS, help="保存短摘录上限")

    p_manual = sub.add_parser("add-manual", help="手动添加桥段案例")
    add_common(p_manual)
    p_manual.add_argument("--excerpt", default="", help="短摘录或自写概述")
    p_manual.set_defaults(func=cmd_add_manual)

    p_file = sub.add_parser("add-file", help="从本地摘录/笔记文件添加案例")
    add_common(p_file)
    p_file.add_argument("--file", required=True, help="本地文本文件")
    p_file.add_argument("--encoding", default="utf-8", help="文件编码")
    p_file.set_defaults(func=cmd_add_file)

    p_url = sub.add_parser("add-url", help="从 URL 抓取标题和短摘录")
    add_common(p_url)
    p_url.add_argument("--url", required=True, help="公开网页 URL")
    p_url.add_argument("--timeout", type=int, default=30, help="请求超时秒数")
    p_url.set_defaults(func=cmd_add_url)

    p_list = sub.add_parser("list", help="列出灵感案例")
    p_list.add_argument("--tag", default="", help="按标签过滤")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.set_defaults(func=cmd_list)

    p_query = sub.add_parser("query", help="检索相似桥段")
    p_query.add_argument("query", help="检索问题")
    p_query.add_argument("--tag", default="", help="标签加权")
    p_query.add_argument("--limit", type=int, default=5)
    p_query.add_argument("--excerpt-chars", type=int, default=260)
    p_query.set_defaults(func=cmd_query)

    p_brief = sub.add_parser("brief", help="生成原创灵感 brief")
    p_brief.add_argument("query", help="创作目标")
    p_brief.add_argument("--limit", type=int, default=5)
    p_brief.add_argument("--output", default="", help="写入 Markdown 文件")
    p_brief.set_defaults(func=cmd_brief)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.action in {"add-manual", "add-file"} and not getattr(args, "title", ""):
        parser.error("--title is required for this action")
    raise SystemExit(int(args.func(args) or 0))


if __name__ == "__main__":
    main()

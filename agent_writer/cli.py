from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import (
    commit_chapter,
    generate_draft,
    init_project,
    index_report,
    plan_chapter,
    review_chapter,
    rewrite_draft,
    status_report,
    write_chapter_prompt,
    write_rewrite_brief,
)
from .llm_client import build_client


def _print_json(payload: object) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Independent agent writer CLI")
    parser.add_argument("--project-root", default=".", help="Agent writing project root")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="initialize a file-first writing project")
    init.add_argument("--name", required=True)
    init.add_argument("--genre", required=True)
    init.add_argument("--premise", required=True)
    init.add_argument("--target-reader", required=True)

    plan = sub.add_parser("plan", help="create chapter contract and prewrite plan")
    plan.add_argument("--chapter", type=int, required=True)
    plan.add_argument("--title", required=True)
    plan.add_argument("--goal", required=True)
    plan.add_argument("--payoff", action="append", required=True)
    plan.add_argument("--ending-hook", required=True)
    plan.add_argument("--forbid", action="append", default=[])
    plan.add_argument("--character", action="append", default=[])

    write = sub.add_parser("write", help="compile writer prompt and optionally import a draft")
    write.add_argument("--chapter", type=int, required=True)
    write.add_argument("--draft-file")

    review = sub.add_parser("review", help="run local quality gate")
    review.add_argument("--chapter", type=int, required=True)
    review.add_argument("--draft-file")

    rewrite = sub.add_parser("rewrite-brief", help="write a file-based rewrite brief")
    rewrite.add_argument("--chapter", type=int, required=True)

    rewrite_llm = sub.add_parser("rewrite", help="call configured LLM with rewrite brief")
    rewrite_llm.add_argument("--chapter", type=int, required=True)
    rewrite_llm.add_argument("--temperature", type=float, default=0.45)
    rewrite_llm.add_argument("--max-tokens", type=int, default=2200)

    commit = sub.add_parser("commit", help="accept chapter after human approval")
    commit.add_argument("--chapter", type=int, required=True)
    commit.add_argument("--approve", action="store_true")

    generate = sub.add_parser("generate", help="call configured LLM and save draft")
    generate.add_argument("--chapter", type=int, required=True)
    generate.add_argument("--temperature", type=float, default=0.7)
    generate.add_argument("--max-tokens", type=int, default=2200)

    sub.add_parser("llm-smoke", help="test configured OpenAI-compatible LLM")

    index = sub.add_parser("index-report", help="show SQLite artifacts and blocking issues")
    index.add_argument("--limit", type=int, default=20)

    sub.add_parser("status", help="show project status")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.project_root)

    if args.command == "init":
        _print_json(
            init_project(
                root,
                name=args.name,
                genre=args.genre,
                premise=args.premise,
                target_reader=args.target_reader,
            )
        )
        return 0
    if args.command == "plan":
        _print_json(
            plan_chapter(
                root,
                chapter_number=args.chapter,
                title=args.title,
                goal=args.goal,
                required_payoffs=args.payoff,
                ending_hook=args.ending_hook,
                forbidden_beats=args.forbid,
                characters=args.character,
            )
        )
        return 0
    if args.command == "write":
        draft = Path(args.draft_file) if args.draft_file else None
        _print_json(write_chapter_prompt(root, chapter_number=args.chapter, draft_file=draft))
        return 0
    if args.command == "generate":
        _print_json(
            generate_draft(
                root,
                chapter_number=args.chapter,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
        )
        return 0
    if args.command == "review":
        draft = Path(args.draft_file) if args.draft_file else None
        _print_json(review_chapter(root, chapter_number=args.chapter, draft_file=draft))
        return 0
    if args.command == "rewrite-brief":
        _print_json({"rewrite_brief": str(write_rewrite_brief(root, chapter_number=args.chapter))})
        return 0
    if args.command == "rewrite":
        _print_json(
            rewrite_draft(
                root,
                chapter_number=args.chapter,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
        )
        return 0
    if args.command == "commit":
        _print_json(commit_chapter(root, chapter_number=args.chapter, approve=args.approve))
        return 0
    if args.command == "llm-smoke":
        _print_json(build_client(root).smoke())
        return 0
    if args.command == "index-report":
        _print_json(index_report(root, limit=args.limit))
        return 0
    if args.command == "status":
        _print_json(status_report(root))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2

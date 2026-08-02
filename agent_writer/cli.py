from __future__ import annotations

import argparse
import json
from pathlib import Path

from .author_policy import (
    add_author_policy_rule,
    import_author_policy_bundle,
    load_author_policy,
)
from .models import AuthorPolicyRule
from .pipeline import (
    commit_chapter,
    generate_best_of_n,
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
from .context_scorer import score_draft_with_context
from .novel_state import (
    apply_state_delta,
    compile_chapter_context,
    extract_state_delta,
)
from .rolling_arc import (
    advance_rolling_arc,
    arc_status,
    plan_arc_with_api,
    load_active_arc,
    review_arc_contract,
    replan_arc_with_api,
)
from .unit_branch import (
    audit_unit_branch_diversity,
    generate_unit_branches,
    load_unit_branch_set,
    select_unit_branch,
)


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
    plan.add_argument("--idea", help="human/external idea source text; defaults to --goal")
    plan.add_argument("--lock", action="append", default=[], help="immutable idea element")
    plan.add_argument("--forbid-change", action="append", default=[])
    plan.add_argument("--freedom", action="append", default=[])
    plan.add_argument("--success", action="append", default=[])
    plan.add_argument("--ending-mode", choices=["closed", "resonant", "open"], default="resonant")
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

    context = sub.add_parser("compile-context", help="compile evidence-grounded context for one chapter")
    context.add_argument("--chapter", type=int, required=True)
    context.add_argument("--entity", action="append", default=[])
    context.add_argument("--thread", action="append", default=[])
    context.add_argument("--recent-chapters", type=int, default=3)
    context.add_argument("--max-chars", type=int, default=24000)

    score = sub.add_parser("score", help="score one draft against contract and prior NovelState")
    score.add_argument("--chapter", type=int, required=True)
    score.add_argument("--draft-file")
    score.add_argument("--temperature", type=float, default=0.0)
    score.add_argument("--max-tokens", type=int, default=6000)

    extract_state = sub.add_parser("extract-state", help="extract and verify StateDelta via API")
    extract_state.add_argument("--chapter", type=int, required=True)
    extract_state.add_argument("--temperature", type=float, default=0.0)
    extract_state.add_argument("--max-tokens", type=int, default=6000)
    extract_state.add_argument("--apply", action="store_true")

    apply_state = sub.add_parser("apply-state", help="verify and apply a manual/candidate StateDelta JSON")
    apply_state.add_argument("--delta-file", required=True)

    policy_add = sub.add_parser("policy-add", help="add one author-locked writing policy rule")
    policy_add.add_argument("--rule-id", required=True)
    policy_add.add_argument(
        "--category",
        required=True,
        choices=[
            "narrative_direction",
            "style_and_tone",
            "continuity",
            "revision_scope",
            "unit_planning",
            "evaluation",
        ],
    )
    policy_add.add_argument("--instruction", required=True)
    policy_add.add_argument("--severity", choices=["blocking", "risk", "preference"], default="risk")
    policy_add.add_argument(
        "--target",
        action="append",
        choices=["planner", "writer", "scorer", "rewriter"],
        default=[],
    )
    policy_add.add_argument("--rationale", default="")
    policy_add.add_argument("--avoid", action="append", default=[])
    policy_add.add_argument("--prefer", action="append", default=[])
    policy_add.add_argument("--source", action="append", default=[])
    policy_add.add_argument("--replace", action="store_true")

    policy_import = sub.add_parser("policy-import", help="merge an author-policy bundle JSON")
    policy_import.add_argument("--file", required=True)
    policy_import.add_argument("--replace", action="store_true")

    sub.add_parser("policy-show", help="show the current author-locked policy profile")

    unit_branches = sub.add_parser(
        "unit-branches",
        help="generate three structured branch cards before selecting a unit plan",
    )
    unit_branches.add_argument("--start-chapter", type=int, required=True)
    unit_branches.add_argument("--target-total-chars", type=int, default=20000)
    unit_branches.add_argument("--objective", required=True)
    unit_branches.add_argument("--author-intent", required=True)
    unit_branches.add_argument(
        "--freedom-axis",
        action="append",
        required=True,
        choices=[
            "conflict_space",
            "trigger",
            "core_mechanism",
            "climax_action",
            "cost_type",
            "end_hook",
        ],
    )
    unit_branches.add_argument("--entry-state", action="append", default=[])
    unit_branches.add_argument("--target-end-state", action="append", default=[])
    unit_branches.add_argument("--unit-payoff", action="append", default=[])
    unit_branches.add_argument("--lock", action="append", default=[])
    unit_branches.add_argument("--forbid-change", action="append", default=[])
    unit_branches.add_argument("--success", action="append", default=[])
    unit_branches.add_argument("--temperature", type=float, default=0.35)
    unit_branches.add_argument("--max-tokens", type=int, default=8000)
    unit_branches.add_argument("--diversity-max-tokens", type=int, default=5000)

    unit_branch_select = sub.add_parser(
        "unit-branch-select",
        help="select one saved branch card as the active unit contract",
    )
    unit_branch_select.add_argument("--branch-id", required=True)
    unit_branch_select.add_argument("--branch-set-id")

    unit_branch_show = sub.add_parser("unit-branch-show", help="show a saved unit branch set")
    unit_branch_show.add_argument("--branch-set-id")

    unit_branch_audit = sub.add_parser(
        "unit-branch-audit",
        help="run swapped-order semantic diversity review on a branch set",
    )
    unit_branch_audit.add_argument("--branch-set-id")
    unit_branch_audit.add_argument("--max-tokens", type=int, default=5000)

    arc_plan = sub.add_parser(
        "arc-plan",
        aliases=["unit-plan"],
        help="plan one author-directed unit drama; natural beat count, at most 20k chars",
    )
    arc_plan.add_argument("--start-chapter", type=int, required=True)
    arc_plan.add_argument("--horizon", type=int, help="optional chapter-count hint; omit for planner-selected count")
    arc_plan.add_argument("--target-total-chars", type=int, default=20000)
    arc_plan.add_argument("--unit-title", default="")
    arc_plan.add_argument("--objective", required=True)
    arc_plan.add_argument("--author-intent", required=True)
    arc_plan.add_argument("--entry-state", action="append", default=[])
    arc_plan.add_argument("--target-end-state", action="append", default=[])
    arc_plan.add_argument("--unit-payoff", action="append", default=[])
    arc_plan.add_argument("--lock", action="append", default=[])
    arc_plan.add_argument("--forbid-change", action="append", default=[])
    arc_plan.add_argument("--success", action="append", default=[])
    arc_plan.add_argument("--temperature", type=float, default=0.2)
    arc_plan.add_argument("--max-tokens", type=int, default=8000)

    arc_advance = sub.add_parser(
        "arc-advance",
        aliases=["unit-advance"],
        help="refresh remaining unit beats if needed, then activate only the next chapter",
    )
    arc_advance.add_argument("--temperature", type=float, default=0.15)
    arc_advance.add_argument("--max-tokens", type=int, default=8000)

    arc_replan = sub.add_parser(
        "arc-replan",
        aliases=["unit-replan"],
        help="replan remaining beats inside the current unit",
    )
    arc_replan.add_argument("--temperature", type=float, default=0.15)
    arc_replan.add_argument("--max-tokens", type=int, default=8000)

    sub.add_parser("arc-status", aliases=["unit-status"], help="show current unit status")
    sub.add_parser(
        "arc-review",
        aliases=["unit-review"],
        help="run local structural review on the current unit plan",
    )

    generate = sub.add_parser("generate", help="call configured LLM and save draft")
    generate.add_argument("--chapter", type=int, required=True)
    generate.add_argument("--temperature", type=float, default=0.7)
    generate.add_argument("--max-tokens", type=int, default=2200)

    generate_best = sub.add_parser(
        "generate-best",
        help="generate candidates in parallel, gate them, and use a judge to select the winner",
    )
    generate_best.add_argument("--chapter", type=int, required=True)
    generate_best.add_argument("--candidates", type=int, default=3)
    generate_best.add_argument("--candidate-mode", choices=["homogeneous", "diverse"], default="diverse")
    generate_best.add_argument("--temperature", type=float, default=0.85)
    generate_best.add_argument("--max-tokens", type=int, default=2200)
    generate_best.add_argument("--judge-temperature", type=float, default=0.0)
    generate_best.add_argument("--judge-max-tokens", type=int, default=1800)

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
                external_idea=args.idea,
                idea_locks=args.lock or None,
                forbidden_changes=args.forbid_change or None,
                freedom_budget=args.freedom or None,
                success_criteria=args.success or None,
                ending_mode=args.ending_mode,
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
    if args.command == "generate-best":
        _print_json(
            generate_best_of_n(
                root,
                chapter_number=args.chapter,
                candidate_count=args.candidates,
                candidate_mode=args.candidate_mode,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                judge_temperature=args.judge_temperature,
                judge_max_tokens=args.judge_max_tokens,
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
    if args.command == "compile-context":
        _print_json(
            compile_chapter_context(
                root,
                chapter_number=args.chapter,
                relevant_entities=args.entity,
                relevant_threads=args.thread,
                recent_chapter_count=args.recent_chapters,
                max_chars=args.max_chars,
            )
        )
        return 0
    if args.command == "score":
        _print_json(
            score_draft_with_context(
                root,
                chapter_number=args.chapter,
                draft_file=Path(args.draft_file) if args.draft_file else None,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                diversity_max_tokens=args.diversity_max_tokens,
            )
        )
        return 0
    if args.command == "extract-state":
        _print_json(
            extract_state_delta(
                root,
                chapter_number=args.chapter,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                apply=args.apply,
            )
        )
        return 0
    if args.command == "apply-state":
        _print_json(apply_state_delta(root, Path(args.delta_file)))
        return 0
    if args.command == "policy-add":
        _print_json(
            add_author_policy_rule(
                root,
                AuthorPolicyRule(
                    rule_id=args.rule_id,
                    category=args.category,
                    instruction=args.instruction,
                    severity=args.severity,
                    applies_to=args.target
                    or ["planner", "writer", "scorer", "rewriter"],
                    rationale=args.rationale,
                    avoid_examples=args.avoid,
                    preferred_examples=args.prefer,
                    source_refs=args.source,
                ),
                replace=args.replace,
            )
        )
        return 0
    if args.command == "policy-import":
        _print_json(
            import_author_policy_bundle(
                root,
                Path(args.file),
                replace=args.replace,
            )
        )
        return 0
    if args.command == "policy-show":
        _print_json(load_author_policy(root))
        return 0
    if args.command == "unit-branches":
        _print_json(
            generate_unit_branches(
                root,
                start_chapter=args.start_chapter,
                target_total_chars=args.target_total_chars,
                objective=args.objective,
                author_intent=args.author_intent,
                freedom_axes=args.freedom_axis,
                entry_state=args.entry_state,
                target_end_state=args.target_end_state,
                unit_payoffs=args.unit_payoff,
                author_locks=args.lock,
                forbidden_changes=args.forbid_change,
                success_criteria=args.success,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
        )
        return 0
    if args.command == "unit-branch-select":
        _print_json(
            select_unit_branch(
                root,
                branch_id=args.branch_id,
                branch_set_id=args.branch_set_id,
            )
        )
        return 0
    if args.command == "unit-branch-show":
        _print_json(load_unit_branch_set(root, args.branch_set_id))
        return 0
    if args.command == "unit-branch-audit":
        _print_json(
            audit_unit_branch_diversity(
                root,
                branch_set_id=args.branch_set_id,
                max_tokens=args.max_tokens,
            )
        )
        return 0
    if args.command in {"arc-plan", "unit-plan"}:
        _print_json(
            plan_arc_with_api(
                root,
                start_chapter=args.start_chapter,
                horizon=args.horizon,
                target_total_chars=args.target_total_chars,
                unit_title=args.unit_title,
                objective=args.objective,
                author_intent=args.author_intent,
                entry_state=args.entry_state,
                target_end_state=args.target_end_state,
                unit_payoffs=args.unit_payoff,
                author_locks=args.lock,
                forbidden_changes=args.forbid_change,
                success_criteria=args.success,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
        )
        return 0
    if args.command in {"arc-advance", "unit-advance"}:
        _print_json(
            advance_rolling_arc(
                root,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
        )
        return 0
    if args.command in {"arc-replan", "unit-replan"}:
        _print_json(
            replan_arc_with_api(
                root,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
        )
        return 0
    if args.command in {"arc-status", "unit-status"}:
        _print_json(arc_status(root))
        return 0
    if args.command in {"arc-review", "unit-review"}:
        arc = load_active_arc(root)
        if arc is None:
            raise ValueError("no active ArcContract")
        _print_json(review_arc_contract(root, arc))
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

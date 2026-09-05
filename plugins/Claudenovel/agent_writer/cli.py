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
from .benchmark_v2 import evaluate_benchmark, run_benchmark_with_api
from .author_materials import import_author_materials
from .evidence_graph import set_context_retrieval_policy
from .unit_completion import score_unit_completion
from .onboarding import bootstrap_existing_state, onboard_existing_novel
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

    unit_run = sub.add_parser("unit-run", help="起草或恢复完整单元；不写入正式正文")
    unit_run.add_argument("--run-id", required=True)
    unit_run.add_argument("--brief", required=True, help="UTF-8 Markdown/文本或 JSON 作者简报")
    unit_run.add_argument("--max-chars", type=int, help="正文硬上限，最大 29999")
    unit_run.add_argument("--preferred-chars", type=int, help="可选篇幅偏好，不是凑字目标")
    unit_run.add_argument("--critic-thinking", choices=["auto", "enabled", "disabled", "omit"], default="auto")
    unit_run.add_argument("--from-run", help="把指定旧运行的完整候选复制到新 run-id，仅重新审阅与修订")
    unit_run.add_argument("--revision-note", help="UTF-8 作者修订要求；配合 from-run 先逐章修订整稿再审阅")
    unit_run.add_argument("--context-file", action="append", default=[], help="明确选择的前情/风格材料，可重复")
    unit_run.add_argument("--max-revision-rounds", type=int, default=2)
    unit_run.add_argument("--max-calls", type=int, default=40)
    unit_run.add_argument("--max-prompt-chars", type=int, default=90000)
    unit_status_parser = sub.add_parser("unit-run-status", help="只读查看完整单元运行状态")
    unit_status_parser.add_argument("--run-id", required=True)

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
    context.add_argument(
        "--retrieval-mode",
        choices=["state_only", "evidence_graph"],
        help="override the project retrieval policy for this context build",
    )

    context_policy = sub.add_parser(
        "context-policy-set",
        help="persist the project context retrieval feature flag",
    )
    context_policy.add_argument(
        "--mode",
        required=True,
        choices=["state_only", "evidence_graph"],
    )
    context_policy.add_argument("--graph-hops", type=int, default=2)
    context_policy.add_argument("--max-remote-evidence", type=int, default=8)
    context_policy.add_argument("--max-graph-state", type=int, default=20)
    context_policy.add_argument(
        "--llm-rerank",
        action="store_true",
        help="use the configured API to reject lexical-only historical matches",
    )
    context_policy.add_argument("--rerank-candidate-limit", type=int, default=24)

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
    extract_state.add_argument(
        "--completeness-audit",
        action="store_true",
        help="run a second omission-only StateDelta audit before optional apply",
    )

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
        "--material-id",
        action="append",
        default=[],
        help="explicitly select one registered author material for this unit",
    )
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
    arc_plan.add_argument(
        "--material-id",
        action="append",
        default=[],
        help="explicitly select one registered author material for this unit",
    )
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
    unit_completion = sub.add_parser(
        "unit-completion-score",
        help="independently verify whether an accepted unit met every author criterion",
    )
    unit_completion.add_argument("--arc-id")
    unit_completion.add_argument("--temperature", type=float, default=0.0)
    unit_completion.add_argument("--max-tokens", type=int, default=6000)

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

    benchmark_run = sub.add_parser(
        "benchmark-run",
        help="run evidence-validated Novel Benchmark v2 cases with the configured API",
    )
    benchmark_run.add_argument("--suite", required=True)
    benchmark_run.add_argument("--out-dir", required=True)
    benchmark_run.add_argument("--max-cases", type=int)
    benchmark_run.add_argument(
        "--case-id",
        action="append",
        default=[],
        help="run only the named case; repeat for a targeted regression set",
    )
    benchmark_run.add_argument("--temperature", type=float, default=0.0)
    benchmark_run.add_argument("--max-tokens", type=int, default=4000)

    benchmark_score = sub.add_parser(
        "benchmark-score",
        help="score saved Novel Benchmark v2 predictions without calling an API",
    )
    benchmark_score.add_argument("--suite", required=True)
    benchmark_score.add_argument("--predictions", required=True)
    benchmark_score.add_argument("--report", required=True)

    material_import = sub.add_parser(
        "material-import",
        help="import author docx/text as reference-only, explicitly selected story material",
    )
    material_import.add_argument("--file", action="append", required=True)
    material_import.add_argument(
        "--kind",
        required=True,
        choices=[
            "current_intent",
            "character_design",
            "future_outline",
            "historical_reference",
        ],
    )
    material_import.add_argument("--note", default="")

    onboard = sub.add_parser(
        "onboard-existing",
        help="import an existing UTF-8 chapter set into a private auditable project",
    )
    onboard.add_argument("--manifest", required=True)
    onboard.add_argument("--resume", action="store_true")

    bootstrap = sub.add_parser(
        "bootstrap-state",
        help="resume ordered StateDelta extraction for an imported existing novel",
    )
    bootstrap.add_argument("--from-chapter", type=int)
    bootstrap.add_argument("--to-chapter", type=int)
    bootstrap.add_argument("--max-chapters", type=int)
    bootstrap.add_argument("--audit-all", action="store_true")
    bootstrap.add_argument("--temperature", type=float, default=0.0)
    bootstrap.add_argument("--max-tokens", type=int, default=6000)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path(args.project_root)

    if args.command == "unit-run-status":
        from .unit_runner import unit_status
        result = unit_status(root, args.run_id)
        _print_json({key: result[key] for key in ("run_id", "status", "calls", "body_chars", "selected_revision", "questions", "output", "error_type") if key in result})
        return 0
    if args.command == "unit-run":
        import sys
        from .unit_runner import run_unit
        result = run_unit(
            root, run_id=args.run_id, brief_file=Path(args.brief),
            context_files=[Path(p) for p in args.context_file],
            max_revision_rounds=args.max_revision_rounds, max_calls=args.max_calls,
            max_prompt_chars=args.max_prompt_chars,
            max_chars=args.max_chars, preferred_chars=args.preferred_chars,
            critic_thinking=args.critic_thinking,
            from_run=Path(args.from_run) if args.from_run else None,
            revision_note_file=Path(args.revision_note) if args.revision_note else None,
            progress=lambda message: print(message, file=sys.stderr, flush=True),
        )
        _print_json({key: result[key] for key in ("run_id", "status", "calls", "body_chars", "selected_revision", "questions", "output") if key in result})
        return 0

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
                retrieval_mode=args.retrieval_mode,
            )
        )
        return 0
    if args.command == "context-policy-set":
        _print_json(
            set_context_retrieval_policy(
                root,
                mode=args.mode,
                graph_hops=args.graph_hops,
                max_remote_evidence=args.max_remote_evidence,
                max_graph_state=args.max_graph_state,
                llm_rerank=args.llm_rerank,
                rerank_candidate_limit=args.rerank_candidate_limit,
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
                completeness_audit=args.completeness_audit,
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
                source_material_ids=args.material_id,
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
                source_material_ids=args.material_id,
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
    if args.command == "unit-completion-score":
        _print_json(
            score_unit_completion(
                root,
                arc_id=args.arc_id,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
        )
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
    if args.command == "benchmark-run":
        _print_json(
            run_benchmark_with_api(
                root,
                suite_file=Path(args.suite),
                output_dir=Path(args.out_dir),
                max_cases=args.max_cases,
                case_ids=args.case_id,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
        )
        return 0
    if args.command == "benchmark-score":
        _print_json(
            evaluate_benchmark(
                Path(args.suite),
                Path(args.predictions),
                report_file=Path(args.report),
            )
        )
        return 0
    if args.command == "material-import":
        _print_json(
            import_author_materials(
                root,
                source_files=[Path(value) for value in args.file],
                kind=args.kind,
                note=args.note,
            )
        )
        return 0
    if args.command == "onboard-existing":
        _print_json(
            onboard_existing_novel(
                root,
                manifest_file=Path(args.manifest),
                resume=args.resume,
            )
        )
        return 0
    if args.command == "bootstrap-state":
        _print_json(
            bootstrap_existing_state(
                root,
                from_chapter=args.from_chapter,
                to_chapter=args.to_chapter,
                max_chapters=args.max_chapters,
                audit_all=args.audit_all,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
            )
        )
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2

"""Evidence-grounded deep question answering for long-form novels."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

from . import llm_client, normalizer, structure
from .output_layout import OrganizedOutput, build_organized_output, write_main_report
from .retrieval_benchmark import (
    ALGORITHMS,
    RELATIONSHIP_PHASE_RANGES,
    RELATIONSHIP_PHASE_TERMS,
    RetrievalCase,
    RetrievalIndex,
    RankedEvidence,
    _algorithm_uses_embeddings,
)
from .structure import Chapter


DEFAULT_NOVEL_PATH = Path(
    r"C:\Users\mingzhe Liu\OneDrive\Desktop\novel-pachong\output\都市之修仙归来.txt"
)

DEFAULT_OUTPUT_DIR = Path("novel_analysis_enhanced") / "deep_question_answering"

DEFAULT_LARGE_CONTEXT_CHARS = 900_000

DEFAULT_COMPARISON_QUESTIONS = [
    "琪皇是否就是萧雨琪？",
    "萧雨琪是否抛弃了楚云和楚凡？",
    "最后萧雨琪没有跟楚云走是否合理？",
    "两人冷战式不相认是否有前文铺垫？",
]

RELATIONSHIP_PHASE_LABELS = {
    "origin": "开端/前世与婚约",
    "longing": "等待/相思与承诺",
    "crisis": "寿命/蕴龙骨危机",
    "family": "妻子母亲/家庭关系",
    "identity": "琪皇身份/宿命责任",
    "separation": "离开/冷战/不相认",
    "payoff": "献祭/和解/回家",
    "general": "通用上下文",
}

RELATIONSHIP_READING_TERMS = [
    "云哥哥",
    "楚凡",
    "小凡",
    "妻子",
    "夫人",
    "母亲",
    "孩子",
    "儿子",
    "不走",
    "离去",
    "不相认",
    "外人",
    "跪首",
    "献祭",
    "回家",
    "放不下",
]

QUESTION_STOPWORDS = {
    "是否",
    "是不是",
    "为什么",
    "如何",
    "分析",
    "评价",
    "觉得",
    "最后",
    "后面",
    "全书",
    "故事",
    "情节",
    "剧情",
    "作者",
    "读者",
    "合理",
    "认为",
}


@dataclass(frozen=True)
class EvidenceNeed:
    id: str
    title: str
    query: str
    stance: str = "support"
    required: bool = True


@dataclass
class QuestionPlan:
    question: str
    category: str
    focus_entities: list[str]
    algorithms: list[str]
    needs: list[EvidenceNeed]


@dataclass
class EvidenceRecord:
    id: str
    need_ids: list[str]
    stance: str
    chapter_index: int
    chapter_title: str
    paragraph_index: int
    score: float
    matched_terms: list[str]
    excerpt: str


@dataclass
class ReadingContextRecord:
    id: str
    chapter_index: int
    chapter_title: str
    paragraph_index: int
    timeline: str
    phase: str
    score: float
    matched_terms: list[str]
    source_tags: list[str]
    excerpt: str


@dataclass
class CoverageAudit:
    timeline: dict[str, bool]
    has_support: bool
    has_counter: bool
    missing: list[str]
    supplemental_retrieval: list[str] = field(default_factory=list)


@dataclass
class AnswerArtifacts:
    question_plan: QuestionPlan
    evidence: list[EvidenceRecord]
    coverage_audit: CoverageAudit
    reading_context: list[ReadingContextRecord]
    reading_context_manifest: dict
    local_report: str
    prompt: str
    llm_report: str | None = None
    llm_model: str | None = None


@dataclass
class ContextModeMetrics:
    question: str
    mode: str
    category: str
    evidence_count: int
    reading_context_count: int
    prompt_chars: int
    context_chars: int
    distinct_chapters: int
    timeline_coverage: dict[str, bool]
    phase_coverage: dict[str, bool]
    need_coverage: dict[str, bool]
    has_support: bool
    has_counter: bool
    missing: list[str]
    score: float
    output_dir: str
    llm_model: str | None = None


@dataclass
class ContextModeComparison:
    questions: list[str]
    modes: list[str]
    metrics: list[ContextModeMetrics]
    winners: dict[str, str]
    report: str


def plan_question(
    question: str,
    focus_entities: Sequence[str] | None = None,
    algorithms: Sequence[str] | None = None,
) -> QuestionPlan:
    """Classify a user question and decompose it into evidence needs."""

    focus = list(focus_entities or _guess_focus_entities(question))
    category = _classify_question(question)
    selected_algorithms = list(algorithms or ["embedding_hybrid_rrf"])
    if category in {"relationship_arc", "character_dispute", "identity", "ending_rationality", "coldwar"}:
        selected_algorithms.append("relationship_template")

    needs = _build_evidence_needs(question, category, focus)
    return QuestionPlan(
        question=question,
        category=category,
        focus_entities=focus,
        algorithms=_dedupe(selected_algorithms),
        needs=needs,
    )


def answer_question(
    txt_path: Path,
    question: str,
    out_dir: Path | None = DEFAULT_OUTPUT_DIR,
    focus_entities: Sequence[str] | None = None,
    algorithms: Sequence[str] | None = None,
    top_k: int = 18,
    evidence_per_need: int = 8,
    excerpt_chars: int = 520,
    large_context: bool = False,
    context_budget_chars: int = DEFAULT_LARGE_CONTEXT_CHARS,
    context_excerpt_chars: int = 1400,
    call_llm: bool = False,
    embedding_mode: str = "local",
    embedding_cache_path: Path | None = None,
    organized_output: bool = False,
) -> AnswerArtifacts:
    """Run the deep QA workflow and export artifacts."""

    layout = build_organized_output(txt_path, question, out_dir) if organized_output else None
    out_dir = out_dir or DEFAULT_OUTPUT_DIR
    export_dir = layout.data_dir if layout else out_dir
    export_dir.mkdir(parents=True, exist_ok=True)
    chapters = structure.parse_chapters(normalizer.read_text(txt_path))
    plan = plan_question(question, focus_entities=focus_entities, algorithms=algorithms)
    index = RetrievalIndex(
        chapters,
        embedding_mode=embedding_mode,
        embedding_cache_path=embedding_cache_path
        or (export_dir / "qa_embedding_cache_local_d2048.npz" if embedding_mode == "local" else None),
    )
    if any(_algorithm_uses_embeddings(name) for name in plan.algorithms):
        index.ensure_embeddings()

    evidence = collect_question_evidence(
        chapters=chapters,
        index=index,
        plan=plan,
        top_k=top_k,
        evidence_per_need=evidence_per_need,
        excerpt_chars=excerpt_chars,
    )
    audit = audit_coverage(chapters, evidence)
    evidence, audit = supplement_missing_coverage(
        chapters=chapters,
        plan=plan,
        evidence=evidence,
        audit=audit,
        excerpt_chars=excerpt_chars,
    )
    reading_context, reading_context_manifest = build_reading_context(
        chapters=chapters,
        plan=plan,
        seed_evidence=evidence,
        max_chars=context_budget_chars if large_context else 0,
        excerpt_chars=context_excerpt_chars,
    )
    prompt = render_answer_prompt(plan, evidence, audit, reading_context, reading_context_manifest)
    local_report = render_local_report(plan, evidence, audit, reading_context_manifest)

    llm_report = None
    llm_model = None
    if call_llm:
        try:
            llm_report, llm_model = llm_client.generate_context_report(prompt)
        except Exception as exc:  # pragma: no cover - depends on external LLM config/network
            llm_report = f"LLM 调用失败：{exc}"
            llm_model = "unavailable"

    artifacts = AnswerArtifacts(
        question_plan=plan,
        evidence=evidence,
        coverage_audit=audit,
        reading_context=reading_context,
        reading_context_manifest=reading_context_manifest,
        local_report=local_report,
        prompt=prompt,
        llm_report=llm_report,
        llm_model=llm_model,
    )
    if layout:
        export_answer_artifacts(artifacts, export_dir)
        write_answer_main_report(artifacts, layout)
    else:
        export_answer_artifacts(artifacts, out_dir)
    return artifacts


def compare_context_modes(
    txt_path: Path,
    out_dir: Path | None,
    questions: Sequence[str] | None = None,
    focus_entities: Sequence[str] | None = None,
    algorithms: Sequence[str] | None = None,
    top_k: int = 18,
    evidence_per_need: int = 8,
    excerpt_chars: int = 520,
    context_budget_chars: int = DEFAULT_LARGE_CONTEXT_CHARS,
    context_excerpt_chars: int = 1400,
    call_llm: bool = False,
    embedding_mode: str = "local",
    organized_output: bool = False,
) -> ContextModeComparison:
    """Run an A/B experiment comparing matrix-only QA with 1M-style context QA."""

    selected_questions = list(questions or DEFAULT_COMPARISON_QUESTIONS)
    task_name = "问答模式对比_" + "_".join(selected_questions[:2])
    layout = build_organized_output(txt_path, task_name, out_dir) if organized_output else None
    out_dir = out_dir or DEFAULT_OUTPUT_DIR
    export_dir = layout.data_dir if layout else out_dir
    export_dir.mkdir(parents=True, exist_ok=True)
    shared_cache = export_dir / "_shared" / "qa_embedding_cache_local_d2048.npz"

    metrics: list[ContextModeMetrics] = []
    for question in selected_questions:
        slug = _slugify_question(question)
        for mode, large_context in (("matrix_only", False), ("large_context", True)):
            mode_out = export_dir / mode / slug
            artifacts = answer_question(
                txt_path=txt_path,
                question=question,
                out_dir=mode_out,
                focus_entities=focus_entities,
                algorithms=algorithms,
                top_k=top_k,
                evidence_per_need=evidence_per_need,
                excerpt_chars=excerpt_chars,
                large_context=large_context,
                context_budget_chars=context_budget_chars,
                context_excerpt_chars=context_excerpt_chars,
                call_llm=call_llm,
                embedding_mode=embedding_mode,
                embedding_cache_path=shared_cache if embedding_mode == "local" else None,
            )
            metrics.append(_score_answer_artifacts(artifacts, mode, mode_out))

    winners = _choose_context_mode_winners(metrics)
    report = render_context_mode_comparison_report(selected_questions, metrics, winners)
    (export_dir / "comparison_summary.json").write_text(
        json.dumps(
            {
                "questions": selected_questions,
                "modes": ["matrix_only", "large_context"],
                "winners": winners,
                "metrics": [asdict(item) for item in metrics],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (export_dir / "comparison_report.md").write_text(report, encoding="utf-8")
    (export_dir / "llm_judge_prompt.md").write_text(
        render_context_mode_judge_prompt(selected_questions, metrics),
        encoding="utf-8",
    )
    if layout:
        write_main_report(layout, "问答上下文模式对比报告", report, data_dir_label="data")
    return ContextModeComparison(
        questions=selected_questions,
        modes=["matrix_only", "large_context"],
        metrics=metrics,
        winners=winners,
        report=report,
    )


def collect_question_evidence(
    chapters: Sequence[Chapter],
    index: RetrievalIndex,
    plan: QuestionPlan,
    top_k: int = 18,
    evidence_per_need: int = 8,
    excerpt_chars: int = 520,
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    for need in plan.needs:
        ranked = _retrieve_for_need(index, plan, need, top_k)
        records.extend(
            _paragraph_evidence_from_ranked(
                chapters=chapters,
                ranked=ranked,
                plan=plan,
                need=need,
                limit=evidence_per_need,
                excerpt_chars=excerpt_chars,
            )
        )
    return _merge_evidence_records(records)


def audit_coverage(chapters: Sequence[Chapter], evidence: Sequence[EvidenceRecord]) -> CoverageAudit:
    total = max(1, len(chapters))
    timeline = {"early": False, "middle": False, "late": False, "ending": False}
    for record in evidence:
        timeline[_timeline_bucket(record.chapter_index, total)] = True

    has_support = any(record.stance == "support" for record in evidence)
    has_counter = any(record.stance == "counter" for record in evidence)
    missing = []
    for bucket, ok in timeline.items():
        if not ok:
            missing.append(f"timeline:{bucket}")
    if not has_support:
        missing.append("support_evidence")
    if not has_counter:
        missing.append("counter_evidence")
    return CoverageAudit(timeline=timeline, has_support=has_support, has_counter=has_counter, missing=missing)


def supplement_missing_coverage(
    chapters: Sequence[Chapter],
    plan: QuestionPlan,
    evidence: list[EvidenceRecord],
    audit: CoverageAudit,
    excerpt_chars: int = 520,
) -> tuple[list[EvidenceRecord], CoverageAudit]:
    additions: list[EvidenceRecord] = []
    total = max(1, len(chapters))
    for missing in audit.missing:
        if not missing.startswith("timeline:"):
            continue
        bucket = missing.split(":", 1)[1]
        chapter_range = _bucket_range(bucket, total)
        item = _direct_best_paragraph(
            chapters=chapters,
            plan=plan,
            chapter_min=chapter_range[0],
            chapter_max=chapter_range[1],
            need_id=f"coverage_{bucket}",
            excerpt_chars=excerpt_chars,
        )
        if item:
            additions.append(item)
            audit.supplemental_retrieval.append(f"{bucket}:{item.id}")

    merged = _merge_evidence_records([*evidence, *additions])
    refreshed = audit_coverage(chapters, merged)
    refreshed.supplemental_retrieval = audit.supplemental_retrieval
    return merged, refreshed


def build_reading_context(
    chapters: Sequence[Chapter],
    plan: QuestionPlan,
    seed_evidence: Sequence[EvidenceRecord],
    max_chars: int,
    excerpt_chars: int = 1400,
) -> tuple[list[ReadingContextRecord], dict]:
    """Build a large, citeable reading pack for long-context LLM analysis."""

    empty_manifest = {
        "enabled": False,
        "max_chars": max_chars,
        "used_chars": 0,
        "record_count": 0,
        "distinct_chapters": 0,
        "timeline_coverage": {"early": False, "middle": False, "late": False, "ending": False},
        "phase_coverage": _blank_phase_coverage(),
        "truncated_candidates": 0,
    }
    if max_chars <= 0:
        return [], empty_manifest

    total = max(1, len(chapters))
    seed_by_id = {record.id: record for record in seed_evidence}
    terms = _large_context_terms(plan)
    focus = set(plan.focus_entities + _alias_terms(plan.question, plan.focus_entities))
    candidates: list[ReadingContextRecord] = []

    for chapter in chapters:
        timeline = _timeline_bucket(chapter.global_index, total)
        for paragraph_index, paragraph in enumerate(chapter.paragraphs, start=1):
            record_id = f"CH{chapter.global_index:03d}-P{paragraph_index:03d}"
            base_score, matched = _paragraph_score(paragraph, terms, focus)
            phase, phase_hits = _infer_relationship_phase(chapter.global_index, total, paragraph)
            source_tags = []
            seed = seed_by_id.get(record_id)
            if seed is not None:
                source_tags.append("evidence_matrix")
                base_score += 80 + seed.score * 0.1
                matched = _dedupe([*matched, *seed.matched_terms])

            focus_hits = [term for term in focus if term and term in paragraph]
            specific_hits = [
                term for term in matched if term not in focus
            ] + phase_hits
            if phase != "general":
                base_score += 10 + len(phase_hits) * 3
                source_tags.append(f"phase:{phase}")
            if timeline in {"early", "ending"}:
                base_score += 2

            if seed is None and not specific_hits and len(focus_hits) < 2:
                continue
            if base_score <= 0:
                continue

            candidates.append(
                ReadingContextRecord(
                    id=record_id,
                    chapter_index=chapter.global_index,
                    chapter_title=chapter.title,
                    paragraph_index=paragraph_index,
                    timeline=timeline,
                    phase=phase,
                    score=base_score,
                    matched_terms=_dedupe([*matched, *phase_hits]),
                    source_tags=_dedupe(source_tags or ["large_context"]),
                    excerpt=_trim_excerpt(paragraph, excerpt_chars),
                )
            )

    selected = _fit_reading_context_records(candidates, seed_by_id, max_chars)
    manifest = _reading_context_manifest(selected, candidates, max_chars)
    return selected, manifest


def render_answer_prompt(
    plan: QuestionPlan,
    evidence: Sequence[EvidenceRecord],
    audit: CoverageAudit,
    reading_context: Sequence[ReadingContextRecord] | None = None,
    reading_context_manifest: dict | None = None,
) -> str:
    focus = "、".join(plan.focus_entities) or "未指定"
    context_records = list(reading_context or [])
    context_manifest = reading_context_manifest or {}
    lines = [
        "# 证据化深度问答任务\n\n",
        "你是严谨的中文网络小说分析助手。只能基于下方材料回答，不允许凭印象补剧情。\n\n",
        f"## 用户问题\n{plan.question}\n\n",
        f"## 问题类型\n{plan.category}\n\n",
        f"## 关注对象\n{focus}\n\n",
        "## 拆解后的证据需求\n",
    ]
    for need in plan.needs:
        lines.append(f"- `{need.id}`：{need.title}；检索式：{need.query}；立场：{need.stance}\n")
    lines.extend(
        [
            "\n## 覆盖审计\n",
            f"- 时间线：{json.dumps(audit.timeline, ensure_ascii=False)}\n",
            f"- 支持证据：{'有' if audit.has_support else '缺'}\n",
            f"- 反方证据：{'有' if audit.has_counter else '缺'}\n",
            f"- 缺口：{', '.join(audit.missing) if audit.missing else '无'}\n\n",
            "## 硬性回答规则\n",
            "1. 每个关键判断必须引用证据 ID，例如 [CH001-P001]。\n",
            "2. 必须同时讨论支持证据和反方证据；没有反方证据时写“证据不足”。\n",
            "3. 必须覆盖早期、中期、后期、结局；缺口要明说。\n",
            "4. 不要只写情绪化总结，要说明具体行为、动机、后果和作者处理。\n",
            "5. 若启用了大上下文阅读包，请先用它建立全书印象，再用证据矩阵校准关键判断。\n",
            "6. 证据矩阵是高置信锚点，大上下文阅读包是广覆盖原文；两者冲突时必须明说冲突。\n",
            "7. 输出简体中文 Markdown。\n\n",
            "## 固定输出结构\n",
            "- 直接结论\n",
            "- 事件时间线\n",
            "- 支持观点的证据\n",
            "- 反方证据\n",
            "- 争议点拆解\n",
            "- 合理性评价\n",
            "- 情感强度分析\n",
            "- 作者写法评价\n",
            "- 可信度与证据缺口\n\n",
        ]
    )
    lines.append(render_reading_context_pack(context_records, context_manifest))
    lines.append("\n## 证据矩阵\n")
    for record in evidence:
        lines.extend(
            [
                f"\n### [{record.id}] {record.chapter_title}\n",
                f"- 位置：第 {record.chapter_index} 章，第 {record.paragraph_index} 段\n",
                f"- 关联需求：{', '.join(record.need_ids)}\n",
                f"- 立场：{record.stance}\n",
                f"- 命中：{'、'.join(record.matched_terms) if record.matched_terms else '无'}\n",
                f"- 原文摘录：{record.excerpt}\n",
            ]
        )
    return "".join(lines)


def render_local_report(
    plan: QuestionPlan,
    evidence: Sequence[EvidenceRecord],
    audit: CoverageAudit,
    reading_context_manifest: dict | None = None,
) -> str:
    context_manifest = reading_context_manifest or {}
    lines = [
        "# Codex 深度问答本地报告\n\n",
        "## 直接结论\n",
        "本地报告只做证据组织和审计，不替代 LLM 文学评析；需要最终自然语言分析时请使用 `--llm`。"
        "下列证据已经按问题拆解归档，可直接交给受控 LLM 生成最终判断。\n\n",
        "## 问题拆解\n",
        f"- 问题：{plan.question}\n",
        f"- 类型：{plan.category}\n",
        f"- 关注对象：{'、'.join(plan.focus_entities) or '未指定'}\n",
        f"- 检索算法：{', '.join(plan.algorithms)}\n\n",
        "## 大上下文状态\n",
        f"- 启用：{'是' if context_manifest.get('enabled') else '否'}\n",
        f"- 阅读包证据数：{context_manifest.get('record_count', 0)}\n",
        f"- 阅读包章节数：{context_manifest.get('distinct_chapters', 0)}\n",
        f"- 阅读包字符数：{context_manifest.get('used_chars', 0)} / {context_manifest.get('max_chars', 0)}\n",
        f"- 阶段覆盖：{json.dumps(context_manifest.get('phase_coverage', {}), ensure_ascii=False)}\n\n",
        "## 事件时间线\n",
    ]
    for record in sorted(evidence, key=lambda item: (item.chapter_index, item.paragraph_index)):
        lines.append(f"- [CH{record.chapter_index:03d}] {record.chapter_title}：[{record.id}] {record.excerpt}\n")
    lines.extend(
        [
            "\n## 支持观点的证据\n",
            *_render_stance_lines(evidence, "support"),
            "\n## 反方证据\n",
            *_render_stance_lines(evidence, "counter"),
            "\n## 争议点拆解\n",
        ]
    )
    for need in plan.needs:
        linked = [record.id for record in evidence if need.id in record.need_ids]
        lines.append(f"- `{need.id}` {need.title}：{', '.join(f'[{item}]' for item in linked) if linked else '证据不足'}\n")
    lines.extend(
        [
            "\n## 合理性评价\n",
            "证据已准备，但价值判断需要结合支持/反方证据由 LLM 或 Codex 二次评析完成。\n\n",
            "## 情感强度分析\n",
            "优先查看含哭、沉默、离去、跪、献祭、回家等动作/情绪词的证据段。\n\n",
            "## 作者写法评价\n",
            "重点判断作者是否在离开原因、身份冲突、孩子线、回归/补偿上给足证据。\n\n",
            "## 可信度与证据缺口\n",
            f"- 时间线覆盖：{json.dumps(audit.timeline, ensure_ascii=False)}\n",
            f"- 支持证据：{'有' if audit.has_support else '缺'}\n",
            f"- 反方证据：{'有' if audit.has_counter else '缺'}\n",
            f"- 缺口：{', '.join(audit.missing) if audit.missing else '无'}\n",
            f"- 自动补检索：{', '.join(audit.supplemental_retrieval) if audit.supplemental_retrieval else '无'}\n",
        ]
    )
    return "".join(lines)


def render_reading_context_pack(
    reading_context: Sequence[ReadingContextRecord],
    manifest: dict | None = None,
) -> str:
    context_manifest = manifest or {}
    lines = [
        "\n## 大上下文阅读包\n",
        f"- 启用：{'是' if context_manifest.get('enabled') else '否'}\n",
        f"- 证据数：{context_manifest.get('record_count', 0)}\n",
        f"- 覆盖章节数：{context_manifest.get('distinct_chapters', 0)}\n",
        f"- 字符预算：{context_manifest.get('used_chars', 0)} / {context_manifest.get('max_chars', 0)}\n",
        f"- 时间线覆盖：{json.dumps(context_manifest.get('timeline_coverage', {}), ensure_ascii=False)}\n",
        f"- 阶段覆盖：{json.dumps(context_manifest.get('phase_coverage', {}), ensure_ascii=False)}\n\n",
    ]
    if not reading_context:
        lines.append("> 未启用大上下文阅读包，LLM 只能读取下方证据矩阵。\n")
        return "".join(lines)

    current_phase = None
    for record in sorted(reading_context, key=lambda item: (item.chapter_index, item.paragraph_index)):
        if record.phase != current_phase:
            current_phase = record.phase
            label = RELATIONSHIP_PHASE_LABELS.get(current_phase, current_phase)
            lines.append(f"\n### {label}\n")
        lines.extend(
            [
                f"\n#### [{record.id}] {record.chapter_title}\n",
                f"- 位置：第 {record.chapter_index} 章，第 {record.paragraph_index} 段\n",
                f"- 时间段：{record.timeline}\n",
                f"- 阶段：{RELATIONSHIP_PHASE_LABELS.get(record.phase, record.phase)}\n",
                f"- 来源：{', '.join(record.source_tags) if record.source_tags else 'large_context'}\n",
                f"- 命中：{'、'.join(record.matched_terms) if record.matched_terms else '无'}\n",
                f"- 原文摘录：{record.excerpt}\n",
            ]
        )
    return "".join(lines)


def render_context_mode_comparison_report(
    questions: Sequence[str],
    metrics: Sequence[ContextModeMetrics],
    winners: dict[str, str],
) -> str:
    lines = [
        "# 问答上下文模式 A/B 实验报告\n\n",
        "## 实验目标\n\n",
        "比较当前小证据矩阵模式 `matrix_only` 与 1M 大上下文模式 `large_context`，判断哪种更适合细致文学问题。"
        "本报告先给离线证据工程指标；如使用 `--llm`，各模式目录还会生成对应的 LLM 回答。\n\n",
        "## 指标说明\n\n",
        "- `score`：覆盖分、子问题覆盖、支持/反方证据、阶段覆盖和长上下文容量的综合分。\n",
        "- `prompt_chars`：最终喂给 LLM 的提示词字符数。\n",
        "- `context_chars`：大上下文阅读包实际占用字符数。\n",
        "- 胜出不等于文学判断一定正确，只表示更可能给 LLM 足够材料。\n\n",
        "## 总览\n\n",
        "| 问题 | 模式 | 分数 | 矩阵证据 | 阅读包证据 | 提示词字符 | 章节数 | 缺口 |\n",
        "|---|---:|---:|---:|---:|---:|---:|---|\n",
    ]
    for metric in metrics:
        lines.append(
            f"| {metric.question} | {metric.mode} | {metric.score:.1f} | "
            f"{metric.evidence_count} | {metric.reading_context_count} | {metric.prompt_chars} | "
            f"{metric.distinct_chapters} | {', '.join(metric.missing) if metric.missing else '无'} |\n"
        )

    lines.append("\n## 每题胜出模式\n\n")
    for question in questions:
        lines.append(f"- {question}：`{winners.get(question, 'unknown')}`\n")

    lines.extend(
        [
            "\n## 结论用法\n\n",
            "- 如果 `large_context` 分数更高且提示词字符数低于你的模型上下文窗口，应优先使用它回答情感线、身份争议、结局合理性问题。\n",
            "- 如果 `matrix_only` 与 `large_context` 分数接近，优先看 LLM 成文是否引用更具体、是否减少误判。\n",
            "- 如果 `large_context` 超出上下文预算，应降低 `--context-budget-chars` 或缩短 `--context-excerpt-chars` 后重跑。\n",
        ]
    )
    return "".join(lines)


def render_context_mode_judge_prompt(
    questions: Sequence[str],
    metrics: Sequence[ContextModeMetrics],
) -> str:
    lines = [
        "# LLM A/B 评审提示词\n\n",
        "你是严格的中文网文书评审稿人。请比较 `matrix_only` 与 `large_context` 两种模式生成的回答质量。"
        "不要只看哪篇更长，要看是否真正回答问题、是否引用证据、是否同时处理反方观点。\n\n",
        "## 评审维度\n\n",
        "1. 证据具体性：关键判断是否引用具体证据 ID。\n",
        "2. 全书覆盖：是否覆盖早期、中期、后期、结局。\n",
        "3. 争议平衡：是否同时分析支持与反方证据。\n",
        "4. 情感线细读：是否能解释相爱、离开、冷战、孩子线、补偿/和解之间的张力。\n",
        "5. 幻觉控制：是否把证据不足处说清楚。\n\n",
        "## 离线指标\n\n",
        "| 问题 | 模式 | 分数 | 矩阵证据 | 阅读包证据 | 提示词字符 | 输出目录 |\n",
        "|---|---:|---:|---:|---:|---:|---|\n",
    ]
    for metric in metrics:
        lines.append(
            f"| {metric.question} | {metric.mode} | {metric.score:.1f} | "
            f"{metric.evidence_count} | {metric.reading_context_count} | "
            f"{metric.prompt_chars} | `{metric.output_dir}` |\n"
        )
    lines.extend(
        [
            "\n## 输出要求\n\n",
            "请按问题逐一判断哪种模式更好，并说明：\n\n",
            "- 胜出模式\n",
            "- 胜出原因\n",
            "- 失败模式的主要缺陷\n",
            "- 是否仍有证据缺口\n",
        ]
    )
    return "".join(lines)


def write_answer_main_report(artifacts: AnswerArtifacts, layout: OrganizedOutput) -> None:
    """Write the main user-facing question report in the task root."""

    if artifacts.llm_report and not artifacts.llm_report.startswith("LLM 调用失败"):
        body = (
            f"> 模型：{artifacts.llm_model}\n\n"
            f"{artifacts.llm_report}\n\n"
            "## 本地证据审计摘要\n\n"
            f"- 证据矩阵数量：{len(artifacts.evidence)}\n"
            f"- 大上下文阅读包数量：{len(artifacts.reading_context)}\n"
            f"- 缺口：{', '.join(artifacts.coverage_audit.missing) if artifacts.coverage_audit.missing else '无'}\n"
        )
    else:
        body = artifacts.local_report
        if artifacts.llm_report:
            body += f"\n\n## LLM 调用状态\n\n{artifacts.llm_report}\n"
    write_main_report(layout, _report_title_for_question(artifacts.question_plan.question), body)


def export_answer_artifacts(artifacts: AnswerArtifacts, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "question_plan.json").write_text(
        json.dumps(_plan_to_dict(artifacts.question_plan), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "evidence_matrix.json").write_text(
        json.dumps([asdict(item) for item in artifacts.evidence], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "coverage_audit.json").write_text(
        json.dumps(asdict(artifacts.coverage_audit), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "reading_context_manifest.json").write_text(
        json.dumps(artifacts.reading_context_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "reading_context_records.json").write_text(
        json.dumps([asdict(item) for item in artifacts.reading_context], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "reading_context_pack.md").write_text(
        render_reading_context_pack(artifacts.reading_context, artifacts.reading_context_manifest),
        encoding="utf-8",
    )
    (out_dir / "answer_prompt.md").write_text(artifacts.prompt, encoding="utf-8")
    (out_dir / "local_answer_report.md").write_text(artifacts.local_report, encoding="utf-8")
    if artifacts.llm_report is not None:
        (out_dir / "llm_answer_report.md").write_text(
            f"# LLM 深度问答报告\n\n> 模型：{artifacts.llm_model}\n\n{artifacts.llm_report}\n",
            encoding="utf-8",
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evidence-grounded deep QA for Chinese web novels")
    parser.add_argument("--txt-path", type=Path, default=DEFAULT_NOVEL_PATH)
    parser.add_argument("--question", help="Question to answer. Required unless --compare-modes is used.")
    parser.add_argument(
        "--compare-modes",
        action="store_true",
        help="Run an A/B experiment: matrix-only vs large-context answering.",
    )
    parser.add_argument(
        "--compare-question",
        action="append",
        default=[],
        help="Question for --compare-modes. Defaults to the built-in acceptance set.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to deep_question_answering, or a task folder when --organized-output is used.",
    )
    parser.add_argument("--focus-entity", action="append", default=[])
    parser.add_argument("--algorithm", action="append", choices=sorted(ALGORITHMS), default=None)
    parser.add_argument("--top-k", type=int, default=18)
    parser.add_argument("--evidence-per-need", type=int, default=8)
    parser.add_argument("--excerpt-chars", type=int, default=520)
    parser.add_argument("--large-context", action="store_true", help="Attach a broad citeable reading context pack.")
    parser.add_argument("--context-budget-chars", type=int, default=DEFAULT_LARGE_CONTEXT_CHARS)
    parser.add_argument("--context-excerpt-chars", type=int, default=1400)
    parser.add_argument(
        "--organized-output",
        action="store_true",
        help="Use task-root/report.md plus task-root/data/ for generated base data.",
    )
    parser.add_argument("--embedding-mode", choices=("local", "api", "off"), default="local")
    parser.add_argument("--llm", action="store_true", help="Call configured LLM for final answer report")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.compare_modes:
        comparison = compare_context_modes(
            txt_path=args.txt_path,
            out_dir=args.out_dir,
            questions=args.compare_question or None,
            focus_entities=args.focus_entity,
            algorithms=args.algorithm,
            top_k=args.top_k,
            evidence_per_need=args.evidence_per_need,
            excerpt_chars=args.excerpt_chars,
            context_budget_chars=args.context_budget_chars,
            context_excerpt_chars=args.context_excerpt_chars,
            call_llm=args.llm,
            embedding_mode=args.embedding_mode,
            organized_output=args.organized_output,
        )
        print(
            json.dumps(
                {
                    "questions": comparison.questions,
                    "modes": comparison.modes,
                    "winners": comparison.winners,
                    "metrics_count": len(comparison.metrics),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not args.question:
        raise SystemExit("--question is required unless --compare-modes is used")

    artifacts = answer_question(
        txt_path=args.txt_path,
        question=args.question,
        out_dir=args.out_dir,
        focus_entities=args.focus_entity,
        algorithms=args.algorithm,
        top_k=args.top_k,
        evidence_per_need=args.evidence_per_need,
        excerpt_chars=args.excerpt_chars,
        large_context=args.large_context,
        context_budget_chars=args.context_budget_chars,
        context_excerpt_chars=args.context_excerpt_chars,
        call_llm=args.llm,
        embedding_mode=args.embedding_mode,
        organized_output=args.organized_output,
    )
    print(
        json.dumps(
            {
                "question": artifacts.question_plan.question,
                "category": artifacts.question_plan.category,
                "evidence_count": len(artifacts.evidence),
                "reading_context_count": len(artifacts.reading_context),
                "missing": artifacts.coverage_audit.missing,
                "llm_model": artifacts.llm_model,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _blank_phase_coverage() -> dict[str, bool]:
    return {phase: False for phase in RELATIONSHIP_PHASE_LABELS if phase != "general"}


def _large_context_terms(plan: QuestionPlan) -> list[str]:
    terms: list[str] = []
    terms.extend(plan.focus_entities)
    terms.extend(_alias_terms(plan.question, plan.focus_entities))
    terms.extend(_terms_from_text(plan.question))
    for need in plan.needs:
        terms.extend(_terms_from_text(need.query))
    if plan.category in {"relationship_arc", "character_dispute", "identity", "ending_rationality", "coldwar"}:
        terms.extend(RELATIONSHIP_READING_TERMS)
        for phase_terms in RELATIONSHIP_PHASE_TERMS.values():
            terms.extend(phase_terms)
    return _dedupe(terms)


def _infer_relationship_phase(chapter_index: int, total: int, text: str) -> tuple[str, list[str]]:
    ratio = chapter_index / max(1, total)
    best_phase = "general"
    best_score = 0.0
    best_hits: list[str] = []
    for phase, terms in RELATIONSHIP_PHASE_TERMS.items():
        hits = [term for term in terms if term in text]
        if not hits:
            continue
        start, end = RELATIONSHIP_PHASE_RANGES.get(phase, (0.0, 1.0))
        score = len(hits) * 4.0
        if start <= ratio <= end:
            score += 5.0
        if phase in {"separation", "payoff"} and ratio >= 0.85:
            score += 2.0
        if score > best_score:
            best_phase = phase
            best_score = score
            best_hits = hits
    return best_phase, _dedupe(best_hits)


def _fit_reading_context_records(
    candidates: Sequence[ReadingContextRecord],
    seed_by_id: dict[str, EvidenceRecord],
    max_chars: int,
) -> list[ReadingContextRecord]:
    selected: dict[str, ReadingContextRecord] = {}
    used = 0

    def add(record: ReadingContextRecord) -> None:
        nonlocal used
        if record.id in selected:
            return
        cost = _estimated_context_record_chars(record)
        if selected and used + cost > max_chars:
            return
        selected[record.id] = record
        used += cost

    ordered = sorted(candidates, key=lambda item: (-item.score, item.chapter_index, item.paragraph_index))
    for record in ordered:
        if record.id in seed_by_id:
            add(record)

    for phase in RELATIONSHIP_PHASE_LABELS:
        if phase == "general":
            continue
        phase_rows = [record for record in ordered if record.phase == phase]
        if phase_rows:
            add(phase_rows[0])

    for bucket in ("early", "middle", "late", "ending"):
        bucket_rows = [record for record in ordered if record.timeline == bucket]
        if bucket_rows:
            add(bucket_rows[0])

    for record in ordered:
        add(record)

    return sorted(selected.values(), key=lambda item: (item.chapter_index, item.paragraph_index))


def _estimated_context_record_chars(record: ReadingContextRecord) -> int:
    return len(record.excerpt) + len(record.chapter_title) + 220


def _reading_context_manifest(
    selected: Sequence[ReadingContextRecord],
    candidates: Sequence[ReadingContextRecord],
    max_chars: int,
) -> dict:
    timeline = {"early": False, "middle": False, "late": False, "ending": False}
    phase_coverage = _blank_phase_coverage()
    for record in selected:
        timeline[record.timeline] = True
        if record.phase in phase_coverage:
            phase_coverage[record.phase] = True
    return {
        "enabled": True,
        "max_chars": max_chars,
        "used_chars": sum(_estimated_context_record_chars(record) for record in selected),
        "record_count": len(selected),
        "distinct_chapters": len({record.chapter_index for record in selected}),
        "timeline_coverage": timeline,
        "phase_coverage": phase_coverage,
        "truncated_candidates": max(0, len(candidates) - len(selected)),
    }


def _score_answer_artifacts(
    artifacts: AnswerArtifacts,
    mode: str,
    out_dir: Path,
) -> ContextModeMetrics:
    evidence = artifacts.evidence
    context = artifacts.reading_context
    distinct_chapters = len({record.chapter_index for record in evidence} | {record.chapter_index for record in context})
    timeline_coverage = _combined_timeline_coverage(artifacts)
    phase_coverage = _combined_phase_coverage(artifacts)
    need_coverage = {
        need.id: any(need.id in record.need_ids for record in evidence)
        for need in artifacts.question_plan.needs
    }
    timeline_score = sum(timeline_coverage.values()) / max(1, len(timeline_coverage)) * 20
    phase_score = sum(phase_coverage.values()) / max(1, len(phase_coverage)) * 20
    need_score = sum(need_coverage.values()) / max(1, len(need_coverage)) * 20
    stance_score = (7.5 if artifacts.coverage_audit.has_support else 0) + (
        7.5 if artifacts.coverage_audit.has_counter else 0
    )
    breadth_score = min(15.0, distinct_chapters / 20 * 15)
    context_score = min(10.0, artifacts.reading_context_manifest.get("used_chars", 0) / 300_000 * 10)
    over_budget_penalty = max(0.0, (len(artifacts.prompt) - 1_000_000) / 50_000 * 5)
    score = max(0.0, timeline_score + phase_score + need_score + stance_score + breadth_score + context_score - over_budget_penalty)

    return ContextModeMetrics(
        question=artifacts.question_plan.question,
        mode=mode,
        category=artifacts.question_plan.category,
        evidence_count=len(evidence),
        reading_context_count=len(context),
        prompt_chars=len(artifacts.prompt),
        context_chars=int(artifacts.reading_context_manifest.get("used_chars", 0)),
        distinct_chapters=distinct_chapters,
        timeline_coverage=timeline_coverage,
        phase_coverage=phase_coverage,
        need_coverage=need_coverage,
        has_support=artifacts.coverage_audit.has_support,
        has_counter=artifacts.coverage_audit.has_counter,
        missing=list(artifacts.coverage_audit.missing),
        score=score,
        output_dir=str(out_dir),
        llm_model=artifacts.llm_model,
    )


def _combined_timeline_coverage(artifacts: AnswerArtifacts) -> dict[str, bool]:
    coverage = dict(artifacts.coverage_audit.timeline)
    for record in artifacts.reading_context:
        coverage[record.timeline] = True
    return coverage


def _combined_phase_coverage(artifacts: AnswerArtifacts) -> dict[str, bool]:
    coverage = _blank_phase_coverage()
    total = 1
    max_chapter = 0
    for record in [*artifacts.evidence, *artifacts.reading_context]:
        max_chapter = max(max_chapter, record.chapter_index)
    total = max(total, max_chapter)
    for record in artifacts.evidence:
        phase, _ = _infer_relationship_phase(record.chapter_index, total, record.excerpt)
        if phase in coverage:
            coverage[phase] = True
    for record in artifacts.reading_context:
        if record.phase in coverage:
            coverage[record.phase] = True
    return coverage


def _choose_context_mode_winners(metrics: Sequence[ContextModeMetrics]) -> dict[str, str]:
    grouped: dict[str, list[ContextModeMetrics]] = {}
    for metric in metrics:
        grouped.setdefault(metric.question, []).append(metric)
    winners: dict[str, str] = {}
    for question, rows in grouped.items():
        ordered = sorted(rows, key=lambda item: (-item.score, item.prompt_chars))
        winners[question] = ordered[0].mode if ordered else "unknown"
    return winners


def _slugify_question(question: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "_", question, flags=re.UNICODE).strip("_")
    return slug[:60] or "question"


def _report_title_for_question(question: str) -> str:
    return f"{question}：深度分析报告"


def _classify_question(question: str) -> str:
    if any(term in question for term in ("冷战", "不相认", "不认")):
        return "coldwar"
    if any(term in question for term in ("抛弃", "孩子", "儿子", "楚凡")):
        return "character_dispute"
    if any(term in question for term in ("琪皇", "转世", "身份", "是不是", "是否就是")):
        return "identity"
    if any(term in question for term in ("合理", "为什么", "没有跟", "没跟", "结局")):
        return "ending_rationality"
    if any(term in question for term in ("感情线", "深爱", "情侣", "虐")):
        return "relationship_arc"
    if any(term in question for term in ("伏笔", "铺垫", "回收")):
        return "foreshadowing"
    return "general_analysis"


def _build_evidence_needs(question: str, category: str, focus: Sequence[str]) -> list[EvidenceNeed]:
    focus_text = " ".join(focus)
    if category == "character_dispute":
        return [
            EvidenceNeed("leave_reason", "离开或拒绝同行的原因", f"{question} {focus_text} 离开 不走 原因 责任 宿命"),
            EvidenceNeed("leaving_behavior", "实际离开行为与态度", f"{question} {focus_text} 离去 冷漠 外人 不相认"),
            EvidenceNeed("child_impact", "孩子/儿子线的处理", f"{question} {focus_text} 孩子 儿子 楚凡 母亲 哭喊"),
            EvidenceNeed("chuyun_reaction", "楚云的反应与伤害", f"{question} {focus_text} 楚云 心痛 跪首 沉默 放不下"),
            EvidenceNeed("later_repair", "后续回归、补偿或和解", f"{question} {focus_text} 回来 回家 和解 献祭 放不下你"),
            EvidenceNeed("counter", "支持读者负面解读的反方证据", f"{question} {focus_text} 抛弃 背叛 外人 不管 孩子", stance="counter"),
        ]
    if category == "identity":
        return [
            EvidenceNeed("identity_reveal", "身份揭示或转世证据", f"{question} {focus_text} 琪皇 转世 三皇 青帝 身份"),
            EvidenceNeed("continuity", "萧雨琪与琪皇的情感连续性", f"{question} {focus_text} 雨琪 琪皇 还是 放不下 回家"),
            EvidenceNeed("contradiction", "身份撕裂或不一致证据", f"{question} {focus_text} 外人 不相认 责任 宿命", stance="counter"),
        ]
    if category == "ending_rationality":
        return [
            EvidenceNeed("stated_reason", "文本明示的理由", f"{question} {focus_text} 原因 责任 宿命 三皇 界魔"),
            EvidenceNeed("emotional_bond", "深爱仍然存在的证据", f"{question} {focus_text} 深爱 放不下 哭 回家 和解"),
            EvidenceNeed("final_choice", "最后选择及其后果", f"{question} {focus_text} 不走 离去 结局 献祭"),
            EvidenceNeed("reader_gap", "作者解释不足或争议来源", f"{question} {focus_text} 抛弃 外人 孩子 冷战", stance="counter"),
        ]
    if category == "coldwar":
        return [
            EvidenceNeed("early_bond", "早期承诺和感情基底", f"{question} {focus_text} 前世 婚约 承诺 娶我"),
            EvidenceNeed("separation", "分离和不相认场面", f"{question} {focus_text} 冷战 不相认 外人 离去"),
            EvidenceNeed("return", "回到身边或情感回流", f"{question} {focus_text} 回来 回家 放不下你 和解"),
            EvidenceNeed("counter", "冷战写法造成伤害的证据", f"{question} {focus_text} 楚云 楚凡 心痛 跪首", stance="counter"),
        ]
    if category == "foreshadowing":
        return [
            EvidenceNeed("setup", "前文铺垫", f"{question} {focus_text} 伏笔 铺垫 暗示 承诺"),
            EvidenceNeed("payoff", "后文回收", f"{question} {focus_text} 回收 真相 揭示 兑现"),
            EvidenceNeed("gap", "没有回收或解释不足", f"{question} {focus_text} 矛盾 没解释 断裂", stance="counter"),
        ]
    return [
        EvidenceNeed("fact_base", "事实基础", f"{question} {focus_text}"),
        EvidenceNeed("support", "支持判断的证据", f"{question} {focus_text} 支持 证明"),
        EvidenceNeed("counter", "反方或不确定证据", f"{question} {focus_text} 反方 矛盾 不足", stance="counter"),
    ]


def _retrieve_for_need(
    index: RetrievalIndex,
    plan: QuestionPlan,
    need: EvidenceNeed,
    top_k: int,
) -> list[RankedEvidence]:
    ranked: list[list[RankedEvidence]] = []
    case = RetrievalCase(
        id=need.id,
        description=need.title,
        query=need.query,
        expected_chapters=set(),
        must_chapters=set(),
        focus_entities=tuple(plan.focus_entities),
        aliases=tuple(_alias_terms(plan.question, plan.focus_entities)),
        min_expected_recall=0.0,
        min_must_recall=0.0,
        min_precision=0.0,
    )
    for algorithm in plan.algorithms:
        retriever = ALGORITHMS.get(algorithm)
        if retriever is None:
            continue
        ranked.append(retriever(index, case, top_k))
    return _fuse_ranked_lists(ranked, top_k)


def _paragraph_evidence_from_ranked(
    chapters: Sequence[Chapter],
    ranked: Sequence[RankedEvidence],
    plan: QuestionPlan,
    need: EvidenceNeed,
    limit: int,
    excerpt_chars: int,
) -> list[EvidenceRecord]:
    chapter_lookup = {chapter.global_index: chapter for chapter in chapters}
    terms = _terms_from_text(need.query + " " + plan.question)
    focus = set(plan.focus_entities + _alias_terms(plan.question, plan.focus_entities))
    candidates: list[EvidenceRecord] = []
    for item in ranked:
        chapter = chapter_lookup.get(item.chunk.chapter_index)
        if not chapter:
            continue
        for paragraph_index, paragraph in enumerate(chapter.paragraphs, start=1):
            score, matched = _paragraph_score(paragraph, terms, focus)
            if score <= 0:
                continue
            stance = _record_stance(paragraph, need)
            candidates.append(
                EvidenceRecord(
                    id=f"CH{chapter.global_index:03d}-P{paragraph_index:03d}",
                    need_ids=[need.id],
                    stance=stance,
                    chapter_index=chapter.global_index,
                    chapter_title=chapter.title,
                    paragraph_index=paragraph_index,
                    score=score + item.score,
                    matched_terms=matched,
                    excerpt=_trim_excerpt(paragraph, excerpt_chars),
                )
            )
    candidates.sort(key=lambda record: (-record.score, record.chapter_index, record.paragraph_index))
    return candidates[:limit]


def _direct_best_paragraph(
    chapters: Sequence[Chapter],
    plan: QuestionPlan,
    chapter_min: int,
    chapter_max: int,
    need_id: str,
    excerpt_chars: int,
) -> EvidenceRecord | None:
    terms = _terms_from_text(plan.question)
    focus = set(plan.focus_entities + _alias_terms(plan.question, plan.focus_entities))
    best: EvidenceRecord | None = None
    for chapter in chapters:
        if chapter.global_index < chapter_min or chapter.global_index > chapter_max:
            continue
        for paragraph_index, paragraph in enumerate(chapter.paragraphs, start=1):
            score, matched = _paragraph_score(paragraph, terms, focus)
            if score <= 0:
                continue
            record = EvidenceRecord(
                id=f"CH{chapter.global_index:03d}-P{paragraph_index:03d}",
                need_ids=[need_id],
                stance="context",
                chapter_index=chapter.global_index,
                chapter_title=chapter.title,
                paragraph_index=paragraph_index,
                score=score,
                matched_terms=matched,
                excerpt=_trim_excerpt(paragraph, excerpt_chars),
            )
            if best is None or record.score > best.score:
                best = record
    return best


def _paragraph_score(paragraph: str, terms: Sequence[str], focus: set[str]) -> tuple[float, list[str]]:
    score = 0.0
    matched: list[str] = []
    for entity in focus:
        if entity and entity in paragraph:
            score += 10 + min(4, paragraph.count(entity)) * 3
            matched.append(entity)
    for term in terms:
        if term in focus:
            continue
        if term and term in paragraph:
            score += 5 + min(3, paragraph.count(term)) * 2
            matched.append(term)
    if len(set(matched) & focus) >= 2:
        score += 12
    if any(mark in paragraph for mark in ("哭", "泪", "沉默", "离去", "跪", "献祭", "回家", "不走", "不相认")):
        score += 5
    return score, _dedupe(matched)


def _record_stance(paragraph: str, need: EvidenceNeed) -> str:
    if need.stance == "counter":
        return "counter"
    if any(term in paragraph for term in ("抛弃", "背叛", "外人", "不管", "不认", "冷漠")):
        return "counter"
    return need.stance


def _fuse_ranked_lists(ranked_lists: Sequence[Sequence[RankedEvidence]], top_k: int) -> list[RankedEvidence]:
    scores: dict[str, float] = {}
    chunks = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked):
            chunks[item.chunk.id] = item.chunk
            scores[item.chunk.id] = scores.get(item.chunk.id, 0.0) + 1.0 / (60 + rank + 1)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:top_k]
    return [RankedEvidence(chunks[chunk_id], score, "qa_fusion") for chunk_id, score in ordered]


def _merge_evidence_records(records: Sequence[EvidenceRecord]) -> list[EvidenceRecord]:
    merged: dict[str, EvidenceRecord] = {}
    for record in records:
        existing = merged.get(record.id)
        if existing is None:
            merged[record.id] = record
            continue
        existing.need_ids = _dedupe([*existing.need_ids, *record.need_ids])
        existing.matched_terms = _dedupe([*existing.matched_terms, *record.matched_terms])
        if record.score > existing.score:
            existing.score = record.score
        if existing.stance != "counter" and record.stance == "counter":
            existing.stance = "counter"
    return sorted(merged.values(), key=lambda item: (item.chapter_index, item.paragraph_index))


def _timeline_bucket(chapter_index: int, total: int) -> str:
    ratio = chapter_index / max(1, total)
    if ratio <= 0.25:
        return "early"
    if ratio <= 0.70:
        return "middle"
    if ratio <= 0.90:
        return "late"
    return "ending"


def _bucket_range(bucket: str, total: int) -> tuple[int, int]:
    ranges = {
        "early": (1, max(1, int(total * 0.25))),
        "middle": (max(1, int(total * 0.25)), max(1, int(total * 0.70))),
        "late": (max(1, int(total * 0.70)), max(1, int(total * 0.90))),
        "ending": (max(1, int(total * 0.90)), total),
    }
    return ranges.get(bucket, (1, total))


def _render_stance_lines(evidence: Sequence[EvidenceRecord], stance: str) -> list[str]:
    rows = [record for record in evidence if record.stance == stance]
    if not rows:
        return ["- 证据不足\n"]
    return [f"- [{record.id}] {record.chapter_title}：{record.excerpt}\n" for record in rows]


def _guess_focus_entities(question: str) -> list[str]:
    known = ["楚云", "萧雨琪", "琪皇", "楚凡", "雨琪"]
    found = [name for name in known if name in question]
    if found:
        return _dedupe(found)
    terms = _terms_from_text(question)
    return [term for term in terms if 2 <= len(term) <= 4][:3]


def _alias_terms(question: str, focus_entities: Sequence[str]) -> list[str]:
    aliases = []
    focus = set(focus_entities)
    if "萧雨琪" in focus or "雨琪" in question:
        aliases.extend(["雨琪", "琪皇"])
    if "琪皇" in focus or "琪皇" in question:
        aliases.extend(["萧雨琪", "雨琪"])
    if "楚凡" in focus or "楚凡" in question or "儿子" in question:
        aliases.extend(["楚凡", "小凡", "儿子", "孩子"])
    return _dedupe(aliases)


def _terms_from_text(text: str) -> list[str]:
    raw_terms = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_+-]{1,}", text)
    terms = []
    for term in raw_terms:
        if term in QUESTION_STOPWORDS:
            continue
        terms.append(term)
    return _dedupe(terms)


def _trim_excerpt(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    head = max_chars // 2
    tail = max_chars - head - 8
    return cleaned[:head].rstrip() + " ... " + cleaned[-tail:].lstrip()


def _dedupe(items: Sequence[str]) -> list[str]:
    output = []
    seen = set()
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        output.append(item)
    return output


def _plan_to_dict(plan: QuestionPlan) -> dict:
    data = asdict(plan)
    data["needs"] = [asdict(need) for need in plan.needs]
    return data


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

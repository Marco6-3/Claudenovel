from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from .llm_client import build_client
from .models import ChapterEvidenceManifest, NovelState, StrictModel, utc_now_iso
from .storage import (
    read_model,
    read_text,
    sha256_file,
    write_json_atomic,
    write_text_atomic,
)


GRAPH_STATE_LAYERS = (
    "canon_facts",
    "timeline",
    "entity_states",
    "character_beliefs",
    "relationship_arcs",
    "open_threads",
    "style_memory",
)


class ContextRetrievalPolicy(StrictModel):
    schema_version: Literal["context-retrieval-policy/v1"] = "context-retrieval-policy/v1"
    mode: Literal["state_only", "evidence_graph"] = "state_only"
    graph_hops: int = Field(default=2, ge=1, le=4)
    max_remote_evidence: int = Field(default=8, ge=0, le=30)
    max_graph_state: int = Field(default=20, ge=0, le=100)
    llm_rerank: bool = False
    rerank_candidate_limit: int = Field(default=24, ge=4, le=60)
    updated_at: str = Field(default_factory=utc_now_iso)


class EvidenceGraphNode(StrictModel):
    node_id: str
    node_type: Literal["state", "evidence", "entity", "tag", "chapter"]
    label: str
    text: str = ""
    chapter_number: int = Field(default=0, ge=0)
    introduced_chapter: int = Field(default=0, ge=0)
    closed_chapter: int = Field(default=0, ge=0)
    state_id: str = ""
    evidence_id: str = ""


class EvidenceGraphEdge(StrictModel):
    source: str
    target: str
    relation: Literal[
        "has_state",
        "supported_by",
        "tagged_with",
        "belongs_to_chapter",
        "supersedes",
    ]


class EvidenceGraphIndex(StrictModel):
    schema_version: Literal["evidence-graph/v1"] = "evidence-graph/v1"
    index_version: int = 1
    project_id: str
    state_revision: int = Field(ge=0)
    latest_state_synced_chapter: int = Field(ge=0)
    source_fingerprint: str
    nodes: list[EvidenceGraphNode]
    edges: list[EvidenceGraphEdge]
    built_at: str = Field(default_factory=utc_now_iso)


class GraphRetrievalHit(StrictModel):
    node_id: str
    node_type: Literal["state", "evidence"]
    score: float = Field(ge=0.0)
    reasons: list[str]
    state_id: str = ""
    evidence_id: str = ""
    chapter_number: int = Field(default=0, ge=0)
    text: str = ""


class EvidenceRerankItem(StrictModel):
    evidence_id: str
    relevance: int = Field(ge=0, le=3)
    rationale: str


class EvidenceRerankResponse(StrictModel):
    selected: list[EvidenceRerankItem]


def context_retrieval_policy_path(root: Path) -> Path:
    return root / "story_bible" / "context_retrieval_policy.json"


def evidence_graph_path(root: Path) -> Path:
    return root / "state" / "evidence_graph_v1.json"


def load_context_retrieval_policy(root: Path) -> ContextRetrievalPolicy:
    path = context_retrieval_policy_path(root)
    if not path.exists():
        return ContextRetrievalPolicy()
    return read_model(path, ContextRetrievalPolicy)


def set_context_retrieval_policy(
    root: Path,
    *,
    mode: Literal["state_only", "evidence_graph"],
    graph_hops: int = 2,
    max_remote_evidence: int = 8,
    max_graph_state: int = 20,
    llm_rerank: bool = False,
    rerank_candidate_limit: int = 24,
) -> ContextRetrievalPolicy:
    policy = ContextRetrievalPolicy(
        mode=mode,
        graph_hops=graph_hops,
        max_remote_evidence=max_remote_evidence,
        max_graph_state=max_graph_state,
        llm_rerank=llm_rerank,
        rerank_candidate_limit=rerank_candidate_limit,
    )
    write_json_atomic(context_retrieval_policy_path(root), policy)
    return policy


def _entity_node_id(value: str) -> str:
    digest = hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()[:16]
    return f"entity:{digest}"


def _tag_node_id(value: str) -> str:
    digest = hashlib.sha256(value.casefold().encode("utf-8")).hexdigest()[:16]
    return f"tag:{digest}"


def _manifest_files(root: Path) -> list[Path]:
    return sorted((root / "state" / "evidence").glob("chapter_*_evidence.json"))


def _source_fingerprint(root: Path, state: NovelState) -> str:
    payload = [f"state:{state.revision}:{state.updated_at}"]
    for path in _manifest_files(root):
        payload.append(f"{path.name}:{sha256_file(path)}")
    return hashlib.sha256("\n".join(payload).encode("utf-8")).hexdigest()


def _state_records(state: NovelState):
    for layer in GRAPH_STATE_LAYERS:
        for record in getattr(state, layer):
            yield layer, record
    for record in state.authority_layer.author_locks:
        yield "authority_layer", record


def build_evidence_graph(root: Path, state: NovelState) -> EvidenceGraphIndex:
    nodes: dict[str, EvidenceGraphNode] = {}
    edges: set[tuple[str, str, str]] = set()

    for manifest_file in _manifest_files(root):
        manifest = read_model(manifest_file, ChapterEvidenceManifest)
        chapter_node_id = f"chapter:{manifest.chapter_number:04d}"
        nodes[chapter_node_id] = EvidenceGraphNode(
            node_id=chapter_node_id,
            node_type="chapter",
            label=f"第{manifest.chapter_number}章",
            chapter_number=manifest.chapter_number,
        )
        for paragraph in manifest.paragraphs:
            node_id = f"evidence:{paragraph.evidence_id}"
            nodes[node_id] = EvidenceGraphNode(
                node_id=node_id,
                node_type="evidence",
                label=paragraph.evidence_id,
                text=paragraph.text,
                chapter_number=paragraph.chapter_number,
                evidence_id=paragraph.evidence_id,
            )
            edges.add((node_id, chapter_node_id, "belongs_to_chapter"))

    for layer, record in _state_records(state):
        state_node_id = f"state:{record.state_id}"
        nodes[state_node_id] = EvidenceGraphNode(
            node_id=state_node_id,
            node_type="state",
            label=f"{record.subject}｜{record.claim}",
            text=" ".join(
                [layer, record.subject, record.claim, record.value, *record.tags]
            ),
            chapter_number=record.introduced_chapter,
            introduced_chapter=record.introduced_chapter,
            closed_chapter=(record.updated_chapter if record.status != "active" else 0),
            state_id=record.state_id,
        )
        entity_node_id = _entity_node_id(record.subject)
        nodes.setdefault(
            entity_node_id,
            EvidenceGraphNode(
                node_id=entity_node_id,
                node_type="entity",
                label=record.subject,
                text=record.subject,
            ),
        )
        edges.add((entity_node_id, state_node_id, "has_state"))
        for tag in record.tags:
            tag_node_id = _tag_node_id(tag)
            nodes.setdefault(
                tag_node_id,
                EvidenceGraphNode(
                    node_id=tag_node_id,
                    node_type="tag",
                    label=tag,
                    text=tag,
                ),
            )
            edges.add((state_node_id, tag_node_id, "tagged_with"))
        for ref in record.evidence_refs:
            evidence_node_id = f"evidence:{ref.evidence_id}"
            if evidence_node_id in nodes:
                edges.add((state_node_id, evidence_node_id, "supported_by"))
        for old_state_id in record.supersedes:
            edges.add((state_node_id, f"state:{old_state_id}", "supersedes"))

    graph = EvidenceGraphIndex(
        index_version=2,
        project_id=state.project_id,
        state_revision=state.revision,
        latest_state_synced_chapter=state.latest_state_synced_chapter,
        source_fingerprint=_source_fingerprint(root, state),
        nodes=sorted(nodes.values(), key=lambda item: item.node_id),
        edges=[
            EvidenceGraphEdge(source=source, target=target, relation=relation)
            for source, target, relation in sorted(edges)
            if source in nodes and target in nodes
        ],
    )
    write_json_atomic(evidence_graph_path(root), graph)
    return graph


def load_or_build_evidence_graph(root: Path, state: NovelState) -> EvidenceGraphIndex:
    path = evidence_graph_path(root)
    fingerprint = _source_fingerprint(root, state)
    if path.exists():
        graph = read_model(path, EvidenceGraphIndex)
        if graph.index_version == 2 and graph.source_fingerprint == fingerprint:
            return graph
    return build_evidence_graph(root, state)


def _tokens(text: str) -> set[str]:
    normalized = re.sub(r"\s+", "", text.casefold())
    chinese = re.findall(r"[\u4e00-\u9fff]+", normalized)
    tokens: set[str] = set(re.findall(r"[a-z0-9_.:-]+", normalized))
    for segment in chinese:
        if len(segment) == 1:
            tokens.add(segment)
        else:
            tokens.update(segment[index : index + 2] for index in range(len(segment) - 1))
    return tokens


def _query_idf(
    query_tokens: set[str],
    nodes: list[EvidenceGraphNode],
) -> dict[str, float]:
    """Compute query-local IDF without building a second search index.

    The previous cosine score strongly preferred tiny paragraphs containing only
    a character name. Query coverage is the safer objective for long-form
    retrieval: a useful old scene should explain several parts of the current
    intent, not merely mention one person.
    """

    if not query_tokens:
        return {}
    document_frequency: Counter[str] = Counter()
    searchable = [
        node
        for node in nodes
        if node.node_type in {"state", "evidence", "entity", "tag"}
    ]
    for node in searchable:
        node_tokens = _tokens(" ".join([node.label, node.text]))
        for token in query_tokens & node_tokens:
            document_frequency[token] += 1
    total = max(1, len(searchable))
    return {
        token: math.log((total + 1) / (document_frequency[token] + 1)) + 1.0
        for token in query_tokens
    }


def _direct_score(
    query_tokens: set[str],
    query_idf: dict[str, float],
    node: EvidenceGraphNode,
) -> tuple[float, set[str]]:
    node_tokens = _tokens(" ".join([node.label, node.text]))
    matched = query_tokens & node_tokens
    if not matched:
        return 0.0, set()
    total_query_weight = sum(query_idf.values()) or 1.0
    matched_weight = sum(query_idf[token] for token in matched)
    query_coverage = matched_weight / total_query_weight
    # Long unsegmented paragraphs remain eligible, but cannot win merely by
    # containing many unrelated words. The selected excerpt is trimmed later.
    length_penalty = 1.0 / (1.0 + 0.004 * max(0, len(node_tokens) - 80))
    return query_coverage * length_penalty, matched


def _best_excerpt(text: str, matched_tokens: set[str], *, max_chars: int = 700) -> str:
    if len(text) <= max_chars:
        return text
    positions = sorted(
        position
        for token in matched_tokens
        if token
        for position in [text.find(token)]
        if position >= 0
    )
    if not positions:
        return text[:max_chars].rstrip() + "……"
    center = positions[len(positions) // 2]
    start = max(0, center - max_chars // 2)
    end = min(len(text), start + max_chars)
    start = max(0, end - max_chars)
    prefix = "……" if start else ""
    suffix = "……" if end < len(text) else ""
    return prefix + text[start:end].strip() + suffix


def query_evidence_graph(
    graph: EvidenceGraphIndex,
    *,
    query_texts: list[str],
    before_chapter: int,
    excluded_chapters: set[int] | None = None,
    graph_hops: int = 2,
    max_remote_evidence: int = 8,
    max_graph_state: int = 20,
) -> tuple[list[GraphRetrievalHit], list[GraphRetrievalHit], list[str]]:
    excluded = excluded_chapters or set()
    query_tokens = _tokens(" ".join(query_texts))
    entity_tokens: set[str] = set()
    for query_text in query_texts:
        compact = re.sub(r"\s+", "", query_text)
        if 0 < len(compact) <= 3:
            entity_tokens.update(_tokens(compact))
    substantive_tokens = query_tokens - entity_tokens
    by_id = {node.node_id: node for node in graph.nodes}

    def eligible(node: EvidenceGraphNode) -> bool:
        if node.node_type == "chapter":
            return False
        if node.node_type == "evidence":
            return (
                0 < node.chapter_number < before_chapter
                and node.chapter_number not in excluded
            )
        if node.node_type == "state":
            introduced_in_time = (
                node.introduced_chapter == 0
                or node.introduced_chapter < before_chapter
            )
            still_open = (
                node.closed_chapter == 0
                or node.closed_chapter >= before_chapter
            )
            return introduced_in_time and still_open
        return True

    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        # Chapter/entity/tag membership is provenance, not permission to flood
        # the prompt with every scene involving the same protagonist. Retrieval
        # propagation stays on explicit state-evidence and replacement links.
        if edge.relation not in {"supported_by", "supersedes"}:
            continue
        adjacency[edge.source].add(edge.target)
        adjacency[edge.target].add(edge.source)

    query_idf = _query_idf(query_tokens, graph.nodes)
    direct_candidates: list[tuple[float, str, set[str]]] = []
    for node in graph.nodes:
        if not eligible(node):
            continue
        score, matched = _direct_score(query_tokens, query_idf, node)
        if score <= 0:
            continue
        if node.node_type in {"entity", "tag"}:
            continue
        # With a substantive query, neither prose nor state may enter from only
        # a lone character-name bigram. Entity-only lookups remain supported.
        minimum_matches = 1 if len(query_tokens) <= 3 else 2
        if len(matched) < minimum_matches:
            continue
        if substantive_tokens and not (matched & substantive_tokens):
            continue
        direct_candidates.append((score, node.node_id, matched))

    direct_candidates.sort(key=lambda item: (-item[0], item[1]))
    direct_candidates = direct_candidates[:64]
    scores: dict[str, float] = {}
    matched_by_node: dict[str, set[str]] = defaultdict(set)
    reasons: dict[str, set[str]] = defaultdict(set)
    queue: deque[tuple[str, int, float]] = deque()
    for score, node_id, matched in direct_candidates:
        scores[node_id] = score
        matched_by_node[node_id].update(matched)
        reasons[node_id].add("direct_query_coverage")
        queue.append((node_id, 0, score))

    best_depth: dict[str, int] = {}
    while queue:
        node_id, depth, seed_score = queue.popleft()
        if depth >= graph_hops:
            continue
        for neighbor in adjacency.get(node_id, set()):
            if not eligible(by_id[neighbor]):
                continue
            next_depth = depth + 1
            propagated = seed_score * (0.55**next_depth)
            if propagated > scores.get(neighbor, 0.0):
                scores[neighbor] = propagated
                reasons[neighbor].add(f"graph_hop_{next_depth}")
                matched_by_node[neighbor].update(matched_by_node[node_id])
            if next_depth < best_depth.get(neighbor, graph_hops + 1):
                best_depth[neighbor] = next_depth
                queue.append((neighbor, next_depth, seed_score))

    evidence_hits: list[GraphRetrievalHit] = []
    state_hits: list[GraphRetrievalHit] = []
    for node_id, score in scores.items():
        node = by_id[node_id]
        if node.node_type == "evidence":
            if not (0 < node.chapter_number < before_chapter):
                continue
            if node.chapter_number in excluded:
                continue
            evidence_hits.append(
                GraphRetrievalHit(
                    node_id=node.node_id,
                    node_type="evidence",
                    score=round(score, 6),
                    reasons=sorted(reasons[node_id]),
                    evidence_id=node.evidence_id,
                    chapter_number=node.chapter_number,
                    text=node.text,
                )
            )
        elif node.node_type == "state":
            if not eligible(node):
                continue
            state_hits.append(
                GraphRetrievalHit(
                    node_id=node.node_id,
                    node_type="state",
                    score=round(score, 6),
                    reasons=sorted(reasons[node_id]),
                    state_id=node.state_id,
                    chapter_number=node.chapter_number,
                    text=node.text,
                )
            )
    evidence_hits.sort(key=lambda item: (-item.score, -item.chapter_number, item.node_id))
    state_hits.sort(key=lambda item: (-item.score, -item.chapter_number, item.node_id))
    if evidence_hits:
        score_floor = max(0.01, evidence_hits[0].score * 0.25)
        diverse_hits: list[GraphRetrievalHit] = []
        per_chapter: Counter[int] = Counter()
        for hit in evidence_hits:
            if hit.score < score_floor:
                continue
            if per_chapter[hit.chapter_number] >= 2:
                continue
            diverse_hits.append(
                hit.model_copy(
                    update={
                        "text": _best_excerpt(
                            hit.text,
                            matched_by_node.get(hit.node_id, set()),
                        )
                    }
                )
            )
            per_chapter[hit.chapter_number] += 1
            if len(diverse_hits) >= max_remote_evidence:
                break
    else:
        score_floor = 0.0
        diverse_hits = []
    trace = [
        f"query_tokens={len(query_tokens)}",
        f"substantive_query_tokens={len(substantive_tokens)}",
        f"direct_candidates={len(direct_candidates)}",
        "seed_policy=top64_query_coverage",
        f"graph_hops={graph_hops}",
        f"remote_evidence_candidates={len(evidence_hits)}",
        f"remote_score_floor={round(score_floor, 6)}",
        f"remote_selected={len(diverse_hits)}",
        f"state_candidates={len(state_hits)}",
    ]
    return (
        diverse_hits,
        state_hits[:max_graph_state],
        trace,
    )


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("evidence reranker output must be a JSON object")
    return payload


def rerank_evidence_hits_with_api(
    root: Path,
    *,
    chapter_number: int,
    query_texts: list[str],
    hits: list[GraphRetrievalHit],
    max_selected: int,
    temperature: float = 0.0,
    max_tokens: int = 3000,
) -> tuple[list[GraphRetrievalHit], list[str]]:
    if not hits or max_selected <= 0:
        return [], ["llm_rerank_skipped=no_candidates"]
    candidate_payload = [
        {
            "evidence_id": hit.evidence_id,
            "chapter_number": hit.chapter_number,
            "lexical_score": hit.score,
            "text": hit.text,
        }
        for hit in hits
    ]
    prompt = (
        "你是长篇小说历史证据重排器。目标不是找名字相同的段落，而是找对当前写作意图真正有用的旧事实、因果、人物关系、知识边界和未兑现线索。\n\n"
        "评分：3=直接决定当前单元如何写；2=能防止矛盾或建立必要前因；1=只有人物/词语相似；0=无关。\n"
        "硬规则：\n"
        "1. 只输出 JSON 对象，结构为 {\"selected\":[{\"evidence_id\":\"...\",\"relevance\":0,\"rationale\":\"...\"}]}。\n"
        "2. 每个 evidence_id 最多一次，只能来自候选；按 relevance 从高到低。\n"
        "3. 只保留 relevance 2 或 3；宁缺毋滥，不要为了凑数量选择。\n"
        "4. 同名、同一个常见词、同类战斗场面都不等于与本意图相关。\n\n"
        f"目标章节：{chapter_number}\n"
        "当前意图：\n"
        + json.dumps(query_texts, ensure_ascii=False, indent=2)
        + "\n\n候选历史证据：\n"
        + json.dumps(candidate_payload, ensure_ascii=False, indent=2)
    )
    audit_dir = root / "state" / "context" / "retrieval_audits"
    stem = f"chapter_{chapter_number:04d}_evidence_rerank"
    write_text_atomic(audit_dir / f"{stem}_prompt.md", prompt)
    client = build_client(root, role="EVIDENCE_GRAPH")
    raw = client.complete(
        prompt,
        system="你只做证据相关性重排，不续写小说，不补充候选外事实。",
        temperature=temperature,
        max_tokens=max_tokens,
    )
    write_text_atomic(audit_dir / f"{stem}_raw.txt", raw)
    response = EvidenceRerankResponse.model_validate(_extract_json_object(raw))
    by_evidence_id = {hit.evidence_id: hit for hit in hits}
    selected: list[GraphRetrievalHit] = []
    seen: set[str] = set()
    decisions: list[dict[str, object]] = []
    for item in response.selected:
        if item.evidence_id not in by_evidence_id:
            raise ValueError(f"reranker returned unknown evidence_id: {item.evidence_id}")
        if item.evidence_id in seen:
            raise ValueError(f"reranker returned duplicate evidence_id: {item.evidence_id}")
        seen.add(item.evidence_id)
        decisions.append(item.model_dump(mode="json"))
        if item.relevance < 2:
            continue
        hit = by_evidence_id[item.evidence_id]
        selected.append(
            hit.model_copy(
                update={
                    "reasons": [
                        *hit.reasons,
                        f"llm_rerank_relevance_{item.relevance}",
                        f"llm_rerank_reason={item.rationale}",
                    ]
                }
            )
        )
        if len(selected) >= max_selected:
            break
    write_json_atomic(
        audit_dir / f"{stem}_decision.json",
        {
            "schema_version": "evidence-rerank-audit/v1",
            "chapter_number": chapter_number,
            "model": client.config.model,
            "query_texts": query_texts,
            "candidate_count": len(hits),
            "selected_count": len(selected),
            "decisions": decisions,
        },
    )
    return selected, [
        f"llm_rerank_model={client.config.model}",
        f"llm_rerank_candidates={len(hits)}",
        f"llm_rerank_selected={len(selected)}",
    ]


def chapter_contract_query_texts(root: Path, chapter_number: int) -> list[str]:
    path = root / "chapter_contracts" / f"chapter_{chapter_number:04d}_contract.json"
    if not path.exists():
        return []
    payload = json.loads(read_text(path))
    values: list[str] = []
    for key in (
        "title",
        "main_goal",
        "ending_hook",
        "cool_point",
    ):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value)
    for key in (
        "required_payoffs",
        "forbidden_beats",
        "arc_author_locks",
        "arc_beat_constraints",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value if str(item).strip())
        elif isinstance(value, dict):
            values.append(json.dumps(value, ensure_ascii=False))
    return values

"""Novel RAG: Hybrid retrieval + memory summarization for long-form novel analysis.

Architecture (community best practices, zero heavy deps):
- Embedding: OpenAI-compatible API (text-embedding-3-small or local fallback)
- Vector store: Pure numpy cosine-similarity (no Chroma/FAISS needed)
- Sparse retrieval: BM25 over jieba-tokenized Chinese text (rank-bm25)
- Fusion: RRF (Reciprocal Rank Fusion) for dense + sparse
- Metadata filtering: Structured stats (characters, sentiment, relations)
- Memory: Cross-batch summary builder from structured baseline

Zero PyTorch / Transformers / ChromaDB required.
"""
from __future__ import annotations

import json
import math
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .normalizer import ENTITY_ALIASES
from .structure import Chapter, Scene

# ---------------------------------------------------------------------------
# Optional jieba for BM25 tokenization
# ---------------------------------------------------------------------------
try:
    import jieba

    JIEBA_OK = True
except ImportError:
    JIEBA_OK = False

# ---------------------------------------------------------------------------
# Optional rank-bm25
# ---------------------------------------------------------------------------
try:
    from rank_bm25 import BM25Okapi

    BM25_OK = True
except ImportError:
    BM25_OK = False

# ---------------------------------------------------------------------------
# Embedding client (OpenAI-compatible + local fallback)
# ---------------------------------------------------------------------------
DEFAULT_EMBED_MODEL = "text-embedding-3-small"
DEEPSEEK_EMBED_MODEL = "deepseek-embedding"


def _env(key: str, fallback: str = "") -> str:
    import os
    return os.environ.get(key, fallback).strip()


def _is_deepseek_url(base_url: str) -> bool:
    return "deepseek" in base_url.lower()


def get_embeddings(texts: List[str], model: str = "") -> np.ndarray:
    """Fetch embeddings from OpenAI-compatible API. Returns (N, D) numpy array.

    Falls back to local TF-IDF if API is unavailable.
    """
    if not texts:
        return np.zeros((0, 1536), dtype=np.float32)

    # Load .env so embedding works from any subfolder (not just the project root)
    from .llm_client import load_dotenv
    load_dotenv()

    api_key = _env("OPENAI_API_KEY", _env("DEEPSEEK_API_KEY"))
    base_url = _env("OPENAI_BASE_URL", _env("DEEPSEEK_BASE_URL", "")).rstrip("/")

    # Detect provider and pick appropriate model
    if not model:
        if _is_deepseek_url(base_url):
            model = _env("DEEPSEEK_EMBED_MODEL", DEEPSEEK_EMBED_MODEL)
        else:
            model = _env("OPENAI_EMBED_MODEL", DEFAULT_EMBED_MODEL)

    if not api_key or not base_url:
        print("[Embed] No API key/base URL found, falling back to local TF-IDF embeddings")
        return _local_tfidf_embeddings(texts)

    # Build request
    payload = {
        "model": model,
        "input": texts,
        "encoding_format": "float",
    }
    try:
        req = urllib.request.Request(
            f"{base_url}/embeddings",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        # Sort by index because API may reorder
        items = sorted(data["data"], key=lambda x: x["index"])
        vectors = np.array([item["embedding"] for item in items], dtype=np.float32)
        print(f"[Embed] API embeddings: {vectors.shape} (model={model})")
        return vectors
    except Exception as exc:
        print(f"[Embed] API call failed ({exc}), falling back to local TF-IDF embeddings")
        return _local_tfidf_embeddings(texts)


def _local_tfidf_embeddings(texts: List[str], dim: int = 1536) -> np.ndarray:
    """Local TF-IDF based embeddings as fallback. No heavy deps required.

    Uses character n-gram TF-IDF projected to a fixed dimension via hashing.
    Not as good as neural embeddings but enables BM25-dominant hybrid retrieval.
    """
    import hashlib

    vectors = np.zeros((len(texts), dim), dtype=np.float32)
    # Global IDF: document frequency
    doc_freq = np.zeros(dim, dtype=np.float32)
    all_hashes = []

    for text in texts:
        # Character 2-grams and 3-grams
        grams = set()
        for n in (2, 3):
            for i in range(max(0, len(text) - n + 1)):
                grams.add(text[i:i + n])
        hashes = set()
        for gram in grams:
            h = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16) % dim
            hashes.add(h)
        all_hashes.append(hashes)
        for h in hashes:
            doc_freq[h] += 1

    # Compute TF-IDF
    n_docs = len(texts)
    for i, hashes in enumerate(all_hashes):
        for h in hashes:
            tf = 1.0  # binary TF
            idf = max(0, 0.0 + 1) if doc_freq[h] > 0 else 0
            idf = max(0, 1.0)
            vectors[i, h] = 1.0 + 0  # binary: just mark presence

    # Normalize
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vectors = vectors / norms

    print(f"[Embed] Local TF-IDF embeddings: {vectors.shape} (fallback mode)")
    return vectors


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class SceneChunk:
    """One retrievable unit: a scene or paragraph cluster."""
    id: str
    chapter_index: int
    chapter_title: str
    volume: str
    scene_index: int
    text: str
    chars: int
    location_hint: str
    characters_present: List[str] = field(default_factory=list)
    sentiment_net: float = 0.0
    sentiment_tension: float = 0.0
    dialogue_count: int = 0
    relation_events: List[Tuple[str, str, str]] = field(default_factory=list)  # (s, r, o)


@dataclass
class RetrievedChunk:
    """A chunk returned by the retriever with score."""
    chunk: SceneChunk
    dense_score: float = 0.0
    bm25_score: float = 0.0
    rrf_score: float = 0.0
    metadata_matched: bool = False


# ---------------------------------------------------------------------------
# Pure-numpy vector store
# ---------------------------------------------------------------------------
class SimpleVectorStore:
    """In-memory vector store with cosine similarity."""

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension
        self.vectors: np.ndarray = np.zeros((0, dimension), dtype=np.float32)
        self.chunks: List[SceneChunk] = []

    def add(self, chunks: Sequence[SceneChunk], embeddings: np.ndarray) -> None:
        if embeddings.shape[0] != len(chunks):
            raise ValueError("embeddings and chunks length mismatch")
        if embeddings.shape[1] != self.dimension:
            raise ValueError(f"expected dim {self.dimension}, got {embeddings.shape[1]}")
        # L2-normalize for cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normalized = embeddings / norms
        self.vectors = np.vstack([self.vectors, normalized]) if self.vectors.size else normalized
        self.chunks.extend(chunks)

    def search(self, query_embedding: np.ndarray, top_k: int = 10) -> List[Tuple[SceneChunk, float]]:
        if self.vectors.shape[0] == 0:
            return []
        q_norm = np.linalg.norm(query_embedding)
        if q_norm == 0:
            return []
        query_vec = query_embedding / q_norm
        scores = self.vectors @ query_vec  # cosine similarity
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(self.chunks[i], float(scores[i])) for i in top_indices]

    def save(self, path: Path) -> None:
        """Persist vectors (.npy) and chunks (.json) to disk."""
        path.mkdir(parents=True, exist_ok=True)
        np.save(str(path / "vectors.npy"), self.vectors)
        chunks_data = [
            {
                "id": c.id,
                "chapter_index": c.chapter_index,
                "chapter_title": c.chapter_title,
                "volume": c.volume,
                "scene_index": c.scene_index,
                "text": c.text,
                "chars": c.chars,
                "location_hint": c.location_hint,
                "characters_present": c.characters_present,
                "sentiment_net": c.sentiment_net,
                "sentiment_tension": c.sentiment_tension,
                "dialogue_count": c.dialogue_count,
            }
            for c in self.chunks
        ]
        (path / "chunks.json").write_text(
            json.dumps(chunks_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, path: Path) -> "SimpleVectorStore":
        """Load vectors and chunks from disk."""
        vectors = np.load(str(path / "vectors.npy"))
        chunks_raw = json.loads((path / "chunks.json").read_text(encoding="utf-8"))
        store = cls(dimension=vectors.shape[1])
        store.vectors = vectors
        store.chunks = [
            SceneChunk(
                id=c["id"],
                chapter_index=c["chapter_index"],
                chapter_title=c["chapter_title"],
                volume=c.get("volume", ""),
                scene_index=c["scene_index"],
                text=c["text"],
                chars=c["chars"],
                location_hint=c.get("location_hint", ""),
                characters_present=c.get("characters_present", []),
                sentiment_net=c.get("sentiment_net", 0.0),
                sentiment_tension=c.get("sentiment_tension", 0.0),
                dialogue_count=c.get("dialogue_count", 0),
            )
            for c in chunks_raw
        ]
        return store


# ---------------------------------------------------------------------------
# BM25 index over jieba tokens
# ---------------------------------------------------------------------------
class BM25Index:
    """Sparse BM25 retrieval for Chinese text."""

    def __init__(self, chunks: Sequence[SceneChunk]):
        self.chunks = list(chunks)
        if BM25_OK and JIEBA_OK:
            tokenized = [list(jieba.cut_for_search(ch.text)) for ch in self.chunks]
            self.bm25 = BM25Okapi(tokenized)
            self.tokenized = tokenized
        else:
            self.bm25 = None
            self.tokenized = []

    def search(self, query: str, top_k: int = 10) -> List[Tuple[SceneChunk, float]]:
        if self.bm25 is None:
            return []
        tokens = list(jieba.cut_for_search(query))
        scores = self.bm25.get_scores(tokens)
        top_indices = np.argsort(scores)[::-1][:top_k]
        return [(self.chunks[i], float(scores[i])) for i in top_indices]


# ---------------------------------------------------------------------------
# Hybrid retriever: Dense + BM25 + Metadata filter + RRF
# ---------------------------------------------------------------------------
class HybridRetriever:
    """Community best-practice hybrid retrieval for novels.

    Steps:
    1. Metadata pre-filter (characters, sentiment, chapter range)
    2. Dense retrieval (embedding cosine similarity)
    3. Sparse retrieval (BM25)
    4. RRF fusion
    """

    def __init__(
        self,
        vector_store: SimpleVectorStore,
        bm25_index: BM25Index,
        rrf_k: int = 60,
    ):
        self.vector_store = vector_store
        self.bm25_index = bm25_index
        self.rrf_k = rrf_k

    def query(
        self,
        query_text: str,
        query_embedding: Optional[np.ndarray] = None,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedChunk]:
        """Hybrid retrieval with optional metadata filters.

        filters example:
            {"characters": ["陈默", "秦思妍"],
             "chapter_min": 30,
             "chapter_max": 40,
             "sentiment_net_min": -5.0}
        """
        # --- Step 1: metadata filtering ---
        candidate_indices = set(range(len(self.vector_store.chunks)))
        has_filters = bool(filters)
        if has_filters:
            for idx, ch in enumerate(self.vector_store.chunks):
                if not self._passes_filter(ch, filters):
                    candidate_indices.discard(idx)
            if not candidate_indices:
                return []

        # --- Step 2: dense retrieval ---
        dense_results: List[Tuple[int, float]] = []
        if query_embedding is not None and query_embedding.size:
            q_norm = np.linalg.norm(query_embedding)
            if q_norm > 0:
                query_vec = query_embedding / q_norm
                all_scores = self.vector_store.vectors @ query_vec
                # Zero out non-candidates
                mask = np.ones(len(all_scores), dtype=bool)
                if has_filters:
                    mask[:] = False
                    mask[list(candidate_indices)] = True
                all_scores = all_scores * mask
                top_dense = np.argsort(all_scores)[::-1][:top_k * 2]
                dense_results = [(int(i), float(all_scores[i])) for i in top_dense if all_scores[i] > 0]

        # --- Step 3: BM25 retrieval ---
        bm25_results: List[Tuple[int, float]] = []
        if self.bm25_index.bm25 is not None:
            all_bm25_scores = self.bm25_index.bm25.get_scores(
                list(jieba.cut_for_search(query_text)) if JIEBA_OK else query_text.split()
            )
            if has_filters:
                mask = np.ones(len(all_bm25_scores), dtype=bool)
                mask[:] = False
                mask[list(candidate_indices)] = True
                all_bm25_scores = all_bm25_scores * mask
            top_bm25 = np.argsort(all_bm25_scores)[::-1][:top_k * 2]
            bm25_results = [(int(i), float(all_bm25_scores[i])) for i in top_bm25 if all_bm25_scores[i] > 0]

        # --- Step 4: RRF fusion ---
        rrf_scores: Dict[int, float] = {}
        for rank, (idx, score) in enumerate(dense_results):
            rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (self.rrf_k + rank + 1)
        for rank, (idx, score) in enumerate(bm25_results):
            rrf_scores[idx] = rrf_scores.get(idx, 0) + 1.0 / (self.rrf_k + rank + 1)

        top_indices = sorted(rrf_scores.keys(), key=lambda i: rrf_scores[i], reverse=True)[:top_k]
        results = []
        for idx in top_indices:
            ch = self.vector_store.chunks[idx]
            dense_score = next((s for i, s in dense_results if i == idx), 0.0)
            bm25_score = next((s for i, s in bm25_results if i == idx), 0.0)
            results.append(RetrievedChunk(
                chunk=ch,
                dense_score=dense_score,
                bm25_score=bm25_score,
                rrf_score=rrf_scores[idx],
                metadata_matched=idx in candidate_indices,
            ))
        return results

    @staticmethod
    def _passes_filter(chunk: SceneChunk, filters: Dict[str, Any]) -> bool:
        if "characters" in filters:
            required = set(filters["characters"])
            if not required.intersection(chunk.characters_present):
                return False
        if "chapter_min" in filters:
            if chunk.chapter_index < filters["chapter_min"]:
                return False
        if "chapter_max" in filters:
            if chunk.chapter_index > filters["chapter_max"]:
                return False
        if "sentiment_net_min" in filters:
            if chunk.sentiment_net < filters["sentiment_net_min"]:
                return False
        if "sentiment_net_max" in filters:
            if chunk.sentiment_net > filters["sentiment_net_max"]:
                return False
        if "locations" in filters:
            if chunk.location_hint not in filters["locations"]:
                return False
        return True


# ---------------------------------------------------------------------------
# Memory summary builder (structured baseline → cross-batch memory)
# ---------------------------------------------------------------------------
@dataclass
class MemorySummary:
    """Aggregated memory from one or more batches of chapters."""
    batch_id: str
    chapter_range: Tuple[int, int]
    word_count: int

    character_arc: Dict[str, str] = field(default_factory=dict)
    relation_milestones: List[Dict[str, Any]] = field(default_factory=list)
    sentiment_keypoints: List[Dict[str, Any]] = field(default_factory=list)
    quality_trend: Dict[str, Any] = field(default_factory=dict)
    unsolved_hooks: List[str] = field(default_factory=list)
    editor_notes: str = ""

    # For cross-batch accumulation
    cumulative_character_occurrence: Dict[str, int] = field(default_factory=dict)
    cumulative_relations: List[Tuple[str, str, str]] = field(default_factory=list)


def _find_sentiment_keypoints(sentiments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Find significant sentiment peaks and valleys."""
    if not sentiments:
        return []
    nets = [s.get("net", 0) for s in sentiments]
    tensions = [s.get("tension", 0) for s in sentiments]
    avg_net = sum(nets) / len(nets)
    std_net = math.sqrt(sum((x - avg_net) ** 2 for x in nets) / max(1, len(nets) - 1))
    threshold = max(1.5, std_net * 1.2)

    points = []
    for i, s in enumerate(sentiments):
        net = s.get("net", 0)
        ten = s.get("tension", 0)
        ch = s.get("chapter", i + 1)
        title = s.get("title", "")
        if net > avg_net + threshold:
            points.append({"chapter": ch, "title": title, "type": "正面高峰", "net": round(net, 2), "reason": ""})
        elif net < avg_net - threshold:
            points.append({"chapter": ch, "title": title, "type": "负面低谷", "net": round(net, 2), "reason": ""})
        elif ten > sum(tensions) / len(tensions) + max(1.0, max(tensions) * 0.3):
            points.append({"chapter": ch, "title": title, "type": "紧张高点", "tension": round(ten, 2), "reason": ""})
    # Sort by chapter
    points.sort(key=lambda x: x["chapter"])
    return points[:15]


def _build_character_arc(entity_stats: Dict[str, Any], chapter_metrics: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """Build simple character arc descriptions from stats."""
    arcs: Dict[str, str] = {}
    top_entities = entity_stats.get("top_20", []) if isinstance(entity_stats, dict) else []
    for ent in top_entities[:10]:
        name = ent.get("name", "")
        count = ent.get("count", 0)
        span = ent.get("chapters", [])
        if not name:
            continue
        if span and len(span) >= 3:
            first_ch, last_ch, ch_count = span[0], span[1], span[2]
            if first_ch <= 5:
                intro = "开篇即出场"
            elif first_ch <= 20:
                intro = f"第{first_ch}章出场"
            else:
                intro = f"中后期第{first_ch}章出场"
            arcs[name] = f"{intro}，出场{count}次，跨越{ch_count}章，活跃至第{last_ch}章"
        else:
            arcs[name] = f"出场{count}次"
    return arcs


def _detect_quality_trend(chapter_metrics: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Detect writing quality trends across chapters."""
    if not chapter_metrics:
        return {}
    hooks = [m.get("dialogue_ratio", 0) * 100 for m in chapter_metrics]  # proxy for engagement
    conflicts = [m.get("conflict_density", 0) for m in chapter_metrics]
    suspense = [m.get("suspense_density", 0) for m in chapter_metrics]

    def _split_trend(vals: List[float]) -> str:
        if len(vals) < 10:
            return "数据不足"
        mid = len(vals) // 2
        first_avg = sum(vals[:mid]) / max(1, mid)
        second_avg = sum(vals[mid:]) / max(1, len(vals) - mid)
        delta = second_avg - first_avg
        if delta > 0.5:
            return f"前半均值{first_avg:.1f} → 后半均值{second_avg:.1f}，呈上升趋势"
        elif delta < -0.5:
            return f"前半均值{first_avg:.1f} → 后半均值{second_avg:.1f}，呈下降趋势"
        return f"均值稳定在{first_avg:.1f}左右"

    # Hook proxy: dialogue ratio (higher = more engaging in web novels)
    hook_trend = _split_trend(hooks)
    conflict_trend = _split_trend(conflicts)
    suspense_trend = _split_trend(suspense)

    return {
        "hook_trend": hook_trend,
        "conflict_trend": conflict_trend,
        "suspense_trend": suspense_trend,
        "avg_dialogue_ratio": round(sum(hooks) / max(1, len(hooks)), 1),
        "avg_conflict_density": round(sum(conflicts) / max(1, len(conflicts)), 2),
        "avg_suspense_density": round(sum(suspense) / max(1, len(suspense)), 2),
    }


def _extract_unsolved_hooks(
    relations: Sequence[Dict[str, Any]],
    sentiments: Sequence[Dict[str, Any]],
    chapter_metrics: Sequence[Dict[str, Any]] = (),
) -> List[str]:
    """Heuristic: find relations that appear early but have no resolution.

    Combines tension-relation span analysis with sentiment progression
    to identify narrative hooks that remain unresolved.
    """
    hooks = []
    tension_relations = {"追杀", "攻击", "命令", "背叛", "欺骗", "辱骂"}
    resolution_relations = {"拯救", "保护", "帮助", "和解", "原谅"}

    # 1. Tension relations: check if resolution appears later for same pair
    tension_pairs: Dict[tuple, Dict[str, Any]] = {}
    resolution_pairs: set = set()
    for rel in relations:
        rtype = rel.get("relation", "")
        sub = rel.get("subject", "")
        obj = rel.get("object", "")
        pair = (sub, obj)
        if rtype in tension_relations:
            if pair not in tension_pairs:
                tension_pairs[pair] = {"relation": rtype, "count": rel.get("count", 1)}
            else:
                tension_pairs[pair]["count"] += rel.get("count", 1)
        if rtype in resolution_relations:
            resolution_pairs.add(pair)

    for pair, info in tension_pairs.items():
        if pair not in resolution_pairs:
            hooks.append(
                f"{pair[0]} → {info['relation']} → {pair[1]}"
                f"（出现{info['count']}次，未见和解/解决）"
            )

    # 2. Sentiment: detect sustained negative runs (not just single cliffs)
    if sentiments:
        nets = [s.get("net", 0) for s in sentiments]
        if len(nets) >= 6:
            # Find the last quarter of chapters
            last_q_start = len(nets) * 3 // 4
            last_quarter = nets[last_q_start:]
            neg_count = sum(1 for n in last_quarter if n < -1)
            if neg_count >= len(last_quarter) * 0.6:
                first_neg_ch = sentiments[last_q_start].get("chapter", "?")
                hooks.append(
                    f"第{first_neg_ch}章起连续{neg_count}章情绪偏负，"
                    f"需要情绪转折或释放"
                )
            else:
                # Fall back to single cliff detection
                last_few = sentiments[-5:]
                neg_cliffs = [s for s in last_few if s.get("net", 0) < -3]
                if neg_cliffs:
                    ch = neg_cliffs[-1].get("chapter", "?")
                    hooks.append(f"第{ch}章情绪急转直下，后续需要情绪出口")

        # 3. Detect unresolved tension arc: tension rises then stays high
        tensions = [s.get("tension", 0) for s in sentiments]
        if len(tensions) >= 8:
            mid = len(tensions) // 2
            first_half_avg = sum(tensions[:mid]) / max(1, mid)
            second_half_avg = sum(tensions[mid:]) / max(1, len(tensions) - mid)
            if second_half_avg > first_half_avg * 1.3 and second_half_avg > 3.0:
                hooks.append(
                    f"紧张度后半段（均值{second_half_avg:.1f}）明显高于前半段"
                    f"（{first_half_avg:.1f}），冲突持续升级未见缓和"
                )

    # 4. Chapter metrics: flag very short chapters at the end (possible rushed ending)
    if chapter_metrics:
        last_3 = list(chapter_metrics)[-3:]
        avg_chars = sum(m.get("chars", 0) for m in chapter_metrics) / max(1, len(chapter_metrics))
        for m in last_3:
            ch_chars = m.get("chars", 0)
            ch_num = m.get("chapter", "?")
            if ch_chars > 0 and ch_chars < avg_chars * 0.5:
                hooks.append(
                    f"第{ch_num}章仅{ch_chars}字（均值{avg_chars:.0f}），"
                    f"疑似仓促收尾"
                )

    return hooks[:10]


def build_memory_summary(
    structured_baseline: Dict[str, Any],
    batch_id: str = "",
    chapter_start: int = 1,
    chapter_end: int = 0,
    previous_memory: Optional[MemorySummary] = None,
) -> MemorySummary:
    """Build a MemorySummary from structured baseline data.

    If previous_memory is provided, deltas and cumulative stats are computed.
    """
    entity_stats = structured_baseline.get("entity_stats", {})
    relations_data = structured_baseline.get("relations", {})
    sentiments = structured_baseline.get("sentiment", [])
    metrics = structured_baseline.get("chapter_metrics", [])

    relations_list = relations_data.get("top_30", []) if isinstance(relations_data, dict) else []
    word_count = sum(m.get("chars", 0) for m in metrics)

    mem = MemorySummary(
        batch_id=batch_id or f"batch_{chapter_start}_{chapter_end}",
        chapter_range=(chapter_start, chapter_end or len(metrics)),
        word_count=word_count,
        character_arc=_build_character_arc(entity_stats, metrics),
        relation_milestones=[
            {
                "first_chapter": rel.get("first_chapter"),
                "subject": rel.get("subject", ""),
                "relation": rel.get("relation", ""),
                "object": rel.get("object", ""),
                "count": rel.get("count", 1),
                "evidence_ids": rel.get("evidence_ids", []),
            }
            for rel in relations_list[:15]
        ],
        sentiment_keypoints=_find_sentiment_keypoints(sentiments),
        quality_trend=_detect_quality_trend(metrics),
        unsolved_hooks=_extract_unsolved_hooks(relations_list, sentiments, metrics),
        cumulative_character_occurrence={
            ent.get("name", ""): ent.get("count", 0)
            for ent in (entity_stats.get("top_20", []) if isinstance(entity_stats, dict) else [])
        },
        cumulative_relations=[
            (r.get("subject", ""), r.get("relation", ""), r.get("object", ""))
            for r in relations_list
        ],
    )

    # Cross-batch accumulation
    if previous_memory:
        for name, count in mem.cumulative_character_occurrence.items():
            prev = previous_memory.cumulative_character_occurrence.get(name, 0)
            mem.cumulative_character_occurrence[name] = prev + count
        mem.cumulative_relations = previous_memory.cumulative_relations + mem.cumulative_relations
        # Detect new characters in this batch
        new_chars = set(mem.character_arc.keys()) - set(previous_memory.character_arc.keys())
        if new_chars:
            mem.editor_notes += f"本批新出场重要人物：{', '.join(new_chars)}。"
        # Detect relation progression
        prev_rel_set = set(previous_memory.cumulative_relations)
        new_rels = [r for r in mem.cumulative_relations if r not in prev_rel_set]
        if new_rels:
            mem.editor_notes += f"新增关系事件 {len(new_rels)} 条。"

    return mem


def export_memory_summary(mem: MemorySummary, out_path: Path) -> None:
    data = {
        "batch_id": mem.batch_id,
        "chapter_range": mem.chapter_range,
        "word_count": mem.word_count,
        "character_arc": mem.character_arc,
        "relation_milestones": mem.relation_milestones,
        "sentiment_keypoints": mem.sentiment_keypoints,
        "quality_trend": mem.quality_trend,
        "unsolved_hooks": mem.unsolved_hooks,
        "editor_notes": mem.editor_notes,
        "cumulative_top_characters": dict(
            sorted(mem.cumulative_character_occurrence.items(), key=lambda x: x[1], reverse=True)[:15]
        ),
    }
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Scene chunker: structure-aware splitting (better than fixed-length)
# ---------------------------------------------------------------------------
def chunk_by_scenes(chapters: Sequence[Chapter]) -> List[SceneChunk]:
    """Split novel into scene-level chunks for retrieval."""
    chunks: List[SceneChunk] = []
    for ch in chapters:
        for si, scene in enumerate(ch.scenes):
            text = "\n".join(scene.paragraphs)
            if len(text) < 30:
                continue
            chunk_id = f"CH{ch.global_index:03d}-S{si:02d}"
            chunks.append(SceneChunk(
                id=chunk_id,
                chapter_index=ch.global_index,
                chapter_title=ch.title,
                volume=ch.volume,
                scene_index=si,
                text=text,
                chars=len(text),
                location_hint=scene.location_hint,
                characters_present=[],  # populated later by entity matcher
                sentiment_net=0.0,
                sentiment_tension=0.0,
                dialogue_count=len(scene.dialogues),
                relation_events=[],
            ))
    return chunks


def enrich_chunks_with_stats(
    chunks: List[SceneChunk],
    chapters: Sequence[Chapter],
    structured_baseline: Optional[Dict[str, Any]] = None,
    aliases: Optional[Dict[str, List[str]]] = None,
) -> List[SceneChunk]:
    """Populate chunk metadata from structured stats."""
    # Simple character matching
    canonical_names = list(aliases.keys()) if aliases is not None else list(ENTITY_ALIASES.keys())
    for chunk in chunks:
        chunk.characters_present = [n for n in canonical_names if n in chunk.text]

    if structured_baseline:
        sentiments = structured_baseline.get("sentiment", [])
        for chunk in chunks:
            idx = chunk.chapter_index - 1
            if 0 <= idx < len(sentiments):
                s = sentiments[idx]
                chunk.sentiment_net = s.get("net", 0)
                chunk.sentiment_tension = s.get("tension", 0)
    return chunks


# ---------------------------------------------------------------------------
# NovelRAG: unified entry point
# ---------------------------------------------------------------------------
class NovelRAG:
    """End-to-end RAG system for novel analysis.

    Usage:
        rag = NovelRAG(persist_dir="novel_rag_db")
        rag.index_novel(chapters, structured_baseline)
        results = rag.query("陈默和秦思妍感情转折点", filters={"characters": ["陈默", "秦思妍"]})
    """

    def __init__(self, persist_dir: str = "novel_rag_db"):
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(exist_ok=True)
        self.vector_store = SimpleVectorStore()
        self.bm25_index: Optional[BM25Index] = None
        self.retriever: Optional[HybridRetriever] = None
        self.chunks: List[SceneChunk] = []
        self.memory: Optional[MemorySummary] = None

    def index_novel(
        self,
        chapters: Sequence[Chapter],
        structured_baseline: Optional[Dict[str, Any]] = None,
        aliases: Optional[Dict[str, List[str]]] = None,
        embed_batch_size: int = 100,
    ) -> None:
        """Index all chapters into the RAG system."""
        print(f"[NovelRAG] Chunking {len(chapters)} chapters by scenes...")
        self.chunks = chunk_by_scenes(chapters)
        self.chunks = enrich_chunks_with_stats(self.chunks, chapters, structured_baseline, aliases=aliases)
        print(f"[NovelRAG] Generated {len(self.chunks)} scene chunks")

        # Build BM25
        self.bm25_index = BM25Index(self.chunks)
        print(f"[NovelRAG] BM25 index built (jieba={'ok' if JIEBA_OK else 'missing'})")

        # Build vector store in batches
        texts = [ch.text for ch in self.chunks]
        all_embeddings = []
        for i in range(0, len(texts), embed_batch_size):
            batch = texts[i:i + embed_batch_size]
            print(f"[NovelRAG] Embedding batch {i // embed_batch_size + 1}/{(len(texts) - 1) // embed_batch_size + 1} ({len(batch)} chunks)")
            emb = get_embeddings(batch)
            all_embeddings.append(emb)
        if all_embeddings:
            embeddings = np.vstack(all_embeddings)
            self.vector_store.add(self.chunks, embeddings)
            print(f"[NovelRAG] Vector store built: {embeddings.shape}")

        self.retriever = HybridRetriever(self.vector_store, self.bm25_index)

    def query(
        self,
        query_text: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedChunk]:
        if self.retriever is None:
            raise RuntimeError("NovelRAG not indexed yet. Call index_novel() first.")
        print(f"[NovelRAG] Query: '{query_text}'")
        emb = get_embeddings([query_text])
        return self.retriever.query(query_text, emb[0], top_k=top_k, filters=filters)

    def build_memory(
        self,
        structured_baseline: Dict[str, Any],
        batch_id: str = "",
        chapter_start: int = 1,
        chapter_end: int = 0,
        previous_memory: Optional[MemorySummary] = None,
    ) -> MemorySummary:
        self.memory = build_memory_summary(
            structured_baseline,
            batch_id=batch_id,
            chapter_start=chapter_start,
            chapter_end=chapter_end,
            previous_memory=previous_memory,
        )
        return self.memory

    def export_memory(self, out_path: Optional[Path] = None) -> None:
        if self.memory is None:
            raise RuntimeError("No memory built yet.")
        path = out_path or (self.persist_dir / "memory_summary.json")
        export_memory_summary(self.memory, path)
        print(f"[NovelRAG] Memory exported to {path}")

    def save(self) -> None:
        """Persist vector store and memory to disk."""
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        self.vector_store.save(self.persist_dir / "vector_store")
        if self.memory:
            self.export_memory(self.persist_dir / "memory_summary.json")
        print(f"[NovelRAG] Saved to {self.persist_dir}")

    @classmethod
    def load(cls, persist_dir: str | Path) -> "NovelRAG":
        """Load a previously saved RAG index from disk."""
        persist_dir = Path(persist_dir)
        if not persist_dir.exists():
            raise FileNotFoundError(f"RAG persist dir not found: {persist_dir}")

        rag = cls(persist_dir=str(persist_dir))
        rag.vector_store = SimpleVectorStore.load(persist_dir / "vector_store")
        rag.chunks = rag.vector_store.chunks
        rag.bm25_index = BM25Index(rag.chunks)
        rag.retriever = HybridRetriever(rag.vector_store, rag.bm25_index)

        mem_path = persist_dir / "memory_summary.json"
        if mem_path.exists():
            mem_data = json.loads(mem_path.read_text(encoding="utf-8"))
            # Map exported field names back to dataclass fields
            rag.memory = MemorySummary(
                batch_id=mem_data.get("batch_id", ""),
                chapter_range=tuple(mem_data.get("chapter_range", [0, 0])),
                word_count=mem_data.get("word_count", 0),
                character_arc=mem_data.get("character_arc", {}),
                relation_milestones=mem_data.get("relation_milestones", []),
                sentiment_keypoints=mem_data.get("sentiment_keypoints", []),
                quality_trend=mem_data.get("quality_trend", {}),
                unsolved_hooks=mem_data.get("unsolved_hooks", []),
                editor_notes=mem_data.get("editor_notes", ""),
                cumulative_character_occurrence=mem_data.get("cumulative_top_characters", {}),
            )

        print(f"[NovelRAG] Loaded from {persist_dir} ({len(rag.chunks)} chunks)")
        return rag


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
def run_rag_indexing(
    txt_path: Path,
    out_dir: Path,
    chapter_start: int = 1,
    chapter_end: int = 0,
    apply_aliases: bool = False,
) -> NovelRAG:
    """Convenience: read novel, parse, build structured baseline, index RAG."""
    from . import normalizer, structure
    from .entity import compute_entity_stats, discover_entity_aliases
    from .evaluator import build_baseline, compute_metrics
    from .relation import extract_relation_events_rule
    from .sentiment import analyze_sentiment

    raw = normalizer.read_text(txt_path)
    text = normalizer.normalize_text(raw, apply_aliases=apply_aliases)
    chapters = structure.parse_chapters(text)
    total = len(chapters)
    end = chapter_end or total
    selected = chapters[chapter_start - 1:end]

    print(f"[run_rag_indexing] Selected chapters {chapter_start}-{end} ({len(selected)} chapters)")

    # Build structured baseline
    aliases = discover_entity_aliases(selected, include_builtin_present=apply_aliases)
    stats = compute_entity_stats(selected, aliases=aliases)
    relation_events = extract_relation_events_rule(selected, aliases=aliases)
    relations = [
        (event["subject"], event["relation"], event["object"])
        for event in relation_events
    ]
    sentiments = analyze_sentiment(selected)
    baseline = build_baseline(selected)
    metrics = [compute_metrics(ch) for ch in selected]

    structured = {
        "entity_stats": {
            "top_20": [{"name": n, "count": c, "chapters": stats.chapter_span.get(n, [])}
                       for n, c in stats.occurrences.most_common(20)],
        },
        "relations": {
            "top_30": [
                {
                    "subject": s,
                    "relation": r,
                    "object": o,
                    "count": c,
                    "first_chapter": min(
                        event["chapter"]
                        for event in relation_events
                        if (event["subject"], event["relation"], event["object"]) == (s, r, o)
                    ),
                    "evidence_ids": [
                        event["evidence_id"]
                        for event in relation_events
                        if (event["subject"], event["relation"], event["object"]) == (s, r, o)
                    ][:5],
                }
                for (s, r, o), c in __import__("collections").Counter(relations).most_common(30)
            ],
        },
        "sentiment": [{"chapter": s.idx, "title": s.title, **s.overall} for s in sentiments],
        "chapter_metrics": [{
            "chapter": ch.global_index,
            "chars": m.chars,
            "dialogue_ratio": m.dialogue_ratio,
            "conflict_density": m.conflict_density,
            "suspense_density": m.suspense_density,
        } for ch, m in zip(selected, metrics)],
    }

    # Index RAG
    rag = NovelRAG(persist_dir=str(out_dir / "rag_db"))
    rag.index_novel(selected, structured_baseline=structured, aliases=aliases)

    # Build memory
    mem = rag.build_memory(structured, batch_id=f"ch{chapter_start}_{end}", chapter_start=chapter_start, chapter_end=end)
    rag.export_memory(out_dir / "memory_summary.json")

    # Persist to disk
    rag.save()

    return rag

"""Retrieval: BM25, kNN, hybrid (reciprocal rank fusion), facets, re-ranking.

Modes
-----
bm25          lexical only: analyzers, synonyms, field boosts, phrase bonus
vector        dense kNN on chunk embeddings (semantic match)
hybrid        both, fused client-side with RRF (transparent, license-free)
hybrid_native both, fused by Elasticsearch's `rrf` retriever (8.14+; check
              your license tier); falls back to `hybrid` if unavailable

Every mode applies the same filter list (ACL + user facets) inside ES.

Client awareness: entity mentions (client / facility names) found by query
understanding become filters or boosts, and in hybrid mode an associate's own
client work gets a third ranked list ("my_clients") in the fusion, so it
surfaces first when it is relevant, without hiding firm-wide knowledge.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from elasticsearch import ApiError

from .config import settings
from .embeddings import get_embedder
from .es import get_es
from .security import User, acl_filter, client_groups

FACET_FIELDS = ["practice", "industry", "doc_type", "client", "facility", "service_lines", "region", "authors"]
SOURCE_FIELDS = [
    "doc_id", "chunk_id", "chunk_no", "title", "summary", "text", "practice", "industry",
    "doc_type", "client", "region", "published_date", "authors", "tags", "confidentiality", "source_uri",
    "facility", "location", "service_lines",
]
RRF_K = 60


@dataclass
class SearchRequest:
    query: str
    user: User
    mode: str = "hybrid"
    filters: dict[str, list[str]] = field(default_factory=dict)
    date_from: str | None = None
    date_to: str | None = None
    size: int = 10
    rerank: bool = False
    with_facets: bool = True
    # Soft preferences, e.g. {"facility": ["Wrenfield North Hospital"]}: they
    # raise matching documents without excluding others.
    boosts: dict[str, list[str]] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Query building
# --------------------------------------------------------------------------
def filter_clauses(req: SearchRequest) -> list[dict]:
    clauses = [acl_filter(req.user)]
    for fld, values in req.filters.items():
        if values and fld in FACET_FIELDS + ["confidentiality", "tags"]:
            clauses.append({"terms": {fld: values}})
    if req.date_from or req.date_to:
        rng = {k: v for k, v in (("gte", req.date_from), ("lte", req.date_to)) if v}
        clauses.append({"range": {"published_date": rng}})
    return clauses


def bm25_query(query: str, filters: list[dict], boosts: dict[str, list[str]] | None = None,
               my_client_groups: list[str] | None = None) -> dict:
    if not query.strip():  # browse mode: filters only, newest first via sort
        return {"bool": {"filter": filters}}
    boost_clauses = [{"terms": {f: v, "boost": 3.0}} for f, v in (boosts or {}).items() if v]
    if my_client_groups:
        # Keyword-only mode has no "my clients" retriever, so personalise with
        # a mild boost for the user's own client work instead.
        boost_clauses.append({"terms": {"allowed_groups": my_client_groups, "boost": 1.5}})
    return {
        "bool": {
            "must": [
                {
                    "multi_match": {
                        "query": query,
                        # Field boosts: a title hit is worth more than a body hit.
                        "fields": ["title^3", "summary^1.5", "text", "tags^2", "client.lc^4", "client.text^3",
                                   "facility.text^4", "location.text^2"],
                        "type": "best_fields",
                        "tie_breaker": 0.3,
                        "operator": "or",
                        # Up to 2 terms: all required; more: 60%. Synonym groups count as one.
                        "minimum_should_match": "2<60%",
                    }
                }
            ],
            "should": [
                # Exact-phrase bonus, tolerant to a couple of words in between.
                {"match_phrase": {"text": {"query": query, "slop": 2, "boost": 2}}},
                {"match_phrase": {"title": {"query": query, "slop": 1, "boost": 3}}},
                # Mild freshness bonus: recent work is usually more useful.
                {"range": {"published_date": {"gte": "now-3y/d", "boost": 0.5}}},
                *boost_clauses,
            ],
            # Filters do not score and are cached by Elasticsearch.
            "filter": filters,
        }
    }


def knn_clause(query_vector: list[float], filters: list[dict], k: int) -> dict:
    return {
        "field": "embedding",
        "query_vector": query_vector,
        "k": k,
        # More candidates per shard = better recall, more latency.
        "num_candidates": max(100, k * 10),
        # Pre-filter: ACLs/facets are applied during the HNSW search, so we
        # always get k *permitted* results (post-filtering can return fewer).
        "filter": filters,
        # Raw cosine threshold (ES reports _score = (1 + cosine) / 2).
        "similarity": settings.vector_min_similarity,
    }


def facet_aggs() -> dict:
    aggs: dict[str, Any] = {}
    for f in FACET_FIELDS:
        # Counts are *documents*, not chunks (cardinality of doc_id).
        aggs[f] = {"terms": {"field": f, "size": 20}, "aggs": {"docs": {"cardinality": {"field": "doc_id"}}}}
    aggs["year"] = {
        "date_histogram": {"field": "published_date", "calendar_interval": "year", "format": "yyyy", "min_doc_count": 1},
        "aggs": {"docs": {"cardinality": {"field": "doc_id"}}},
    }
    return aggs


# --------------------------------------------------------------------------
# Execution
# --------------------------------------------------------------------------
def _hits(resp: dict) -> list[dict]:
    out = []
    for h in resp["hits"]["hits"]:
        src = h["_source"]
        hl = h.get("highlight", {}).get("text")
        out.append({**src, "_score": h.get("_score") or 0.0, "highlight": hl[0] if hl else None})
    return out


HIGHLIGHT = {
    "fields": {"text": {"fragment_size": 180, "number_of_fragments": 1}},
    "pre_tags": ["<mark>"],
    "post_tags": ["</mark>"],
}


def run_bm25(req: SearchRequest, k: int) -> tuple[list[dict], dict | None, int]:
    es = get_es()
    body: dict[str, Any] = {
        "query": bm25_query(req.query, filter_clauses(req), req.boosts,
                            client_groups(req.user) if req.mode == "bm25" else None),
        "size": k,
        "_source": SOURCE_FIELDS,
        "highlight": HIGHLIGHT,
    }
    if req.with_facets:
        body["aggs"] = facet_aggs()
    resp = es.search(index=settings.index_alias, **body)
    return _hits(resp), resp.get("aggregations"), resp["took"]


def run_knn(req: SearchRequest, k: int, query_vector: list[float] | None = None,
            extra_filters: list[dict] | None = None) -> tuple[list[dict], int]:
    es = get_es()
    qv = query_vector or get_embedder().embed_query(req.query)
    resp = es.search(
        index=settings.index_alias,
        knn=knn_clause(qv, filter_clauses(req) + (extra_filters or []), k),
        size=k,
        _source=SOURCE_FIELDS,
    )
    return _hits(resp), resp["took"]


def rrf_fuse(ranked_lists: dict[str, list[dict]], key: str = "chunk_id", k: int = RRF_K) -> list[dict]:
    """Reciprocal rank fusion: score(d) = sum over lists of 1 / (k + rank).

    RRF ignores raw scores, so BM25 scores (unbounded) and cosine scores
    (0..1) never need to be normalised against each other.
    """
    fused: dict[str, dict] = {}
    for name, hits in ranked_lists.items():
        for rank, h in enumerate(hits, start=1):
            item = fused.setdefault(h[key], {**h, "_score": 0.0, "ranks": {}})
            item["_score"] += 1.0 / (k + rank)
            item["ranks"][name] = rank
            if h.get("highlight") and not item.get("highlight"):
                item["highlight"] = h["highlight"]
    return sorted(fused.values(), key=lambda x: x["_score"], reverse=True)


def run_native_rrf(req: SearchRequest, k: int) -> tuple[list[dict], int]:
    es = get_es()
    filters = filter_clauses(req)
    qv = get_embedder().embed_query(req.query)
    resp = es.search(
        index=settings.index_alias,
        retriever={
            "rrf": {
                "retrievers": [
                    {"standard": {"query": bm25_query(req.query, filters, req.boosts)}},
                    {"knn": knn_clause(qv, filters, k)},
                ],
                "rank_window_size": max(k, 50),
                "rank_constant": RRF_K,
            }
        },
        size=k,
        _source=SOURCE_FIELDS,
    )
    return _hits(resp), resp["took"]


def group_by_document(chunks: list[dict], size: int) -> list[dict]:
    """Collapse chunk hits to documents; keep the best chunk plus up to 2 more."""
    docs: dict[str, dict] = {}
    for c in chunks:
        d = docs.get(c["doc_id"])
        passage = {"chunk_id": c["chunk_id"], "text": c["text"], "highlight": c.get("highlight")}
        if d is None:
            d = {k: c.get(k) for k in SOURCE_FIELDS if k not in ("text", "chunk_id", "chunk_no")}
            d.update(score=c["_score"], ranks=c.get("ranks", {}), passages=[passage])
            docs[c["doc_id"]] = d
        elif len(d["passages"]) < 3:
            d["passages"].append(passage)
    return list(docs.values())[:size]


def format_facets(aggs: dict | None) -> dict:
    if not aggs:
        return {}
    out = {}
    for name, agg in aggs.items():
        key = "key_as_string" if name == "year" else "key"
        out[name] = [{"value": b[key], "count": b["docs"]["value"]} for b in agg["buckets"]]
    return out


def search(req: SearchRequest) -> dict:
    t0 = time.perf_counter()
    window = max(50, req.size * 5)  # retrieve more chunks than docs needed
    timings: dict[str, float] = {}
    aggs = None
    notes: list[str] = []
    if not req.query.strip():
        req.mode = "bm25"  # nothing to embed; browse by filters

    if req.mode == "bm25":
        chunks, aggs, timings["es_bm25_ms"] = run_bm25(req, window)
    elif req.mode == "vector":
        chunks, timings["es_knn_ms"] = run_knn(req, window)
    elif req.mode in ("hybrid", "hybrid_native"):
        used_native = False
        if req.mode == "hybrid_native":
            try:
                chunks, timings["es_rrf_ms"] = run_native_rrf(req, window)
                used_native = True
            except ApiError as e:  # e.g. license does not include RRF
                notes.append(f"native RRF unavailable ({e.meta.status}); used client-side RRF")
        if not used_native:
            bm25_hits, aggs, timings["es_bm25_ms"] = run_bm25(req, window)
            qv = get_embedder().embed_query(req.query)
            knn_hits, timings["es_knn_ms"] = run_knn(req, window, qv)
            lists = {"bm25": bm25_hits, "vector": knn_hits}
            mine = client_groups(req.user)
            if mine:
                # Third retriever: the same semantic query, restricted to the
                # user's own client work. Only relevant hits (similarity floor)
                # get through, so unrelated questions are unaffected.
                lists["my_clients"], timings["es_my_clients_ms"] = run_knn(
                    req, 20, qv, [{"terms": {"allowed_groups": mine}}])
            chunks = rrf_fuse(lists)
    else:
        raise ValueError(f"unknown mode {req.mode!r}")

    if req.with_facets and aggs is None:
        facet_req = SearchRequest(**{**req.__dict__, "with_facets": True})
        _, aggs, _ = run_bm25(facet_req, 0)

    results = group_by_document(chunks, max(req.size, 30) if req.rerank else req.size)

    if req.rerank and results:
        from .rerank import rerank

        t_r = time.perf_counter()
        strategy = settings.rerank_strategy
        if strategy == "entity_aware":
            # A named client/facility is a first-stage signal the cross-encoder
            # cannot see, so keep the first-stage order in the mix.
            strategy = "blend" if req.boosts else "replace"
        results, note = rerank(req.query, results, strategy)
        notes.append(f"re-rank strategy: {strategy}")
        timings["rerank_ms"] = round((time.perf_counter() - t_r) * 1000, 1)
        if note:
            notes.append(note)
        results = results[: req.size]

    timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    return {
        "query": req.query,
        "mode": req.mode,
        "results": results,
        "facets": format_facets(aggs) if req.with_facets else {},
        "timings": timings,
        "notes": notes,
    }


def get_document(doc_id: str, user: User) -> dict | None:
    """Fetch all chunks of one document (ACL enforced) and stitch them back."""
    es = get_es()
    resp = es.search(
        index=settings.index_alias,
        query={"bool": {"filter": [{"term": {"doc_id": doc_id}}, acl_filter(user)]}},
        sort=[{"chunk_no": "asc"}],
        size=200,
        _source={"excludes": ["embedding"]},
    )
    hits = [h["_source"] for h in resp["hits"]["hits"]]
    if not hits:
        return None
    doc = {k: v for k, v in hits[0].items() if k not in ("text", "chunk_id", "chunk_no", "word_count")}
    doc["chunks"] = [{"chunk_id": h["chunk_id"], "text": h["text"]} for h in hits]
    return doc


def facet_values(user: User) -> dict:
    req = SearchRequest(query="", user=user, with_facets=True)
    resp = get_es().search(
        index=settings.index_alias,
        query={"bool": {"filter": filter_clauses(req)}},
        size=0,
        aggs=facet_aggs(),
    )
    return format_facets(resp["aggregations"])

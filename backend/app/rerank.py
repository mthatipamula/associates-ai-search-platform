"""Optional second-stage re-ranking with a cross-encoder.

First stage (BM25 + kNN) is cheap and recall-oriented; the cross-encoder
reads query and passage *together* and is far more precise, but costs
~O(candidates) model calls, so it only sees the top ~30 documents.

Elastic-native equivalent: the `text_similarity_reranker` retriever with an
inference endpoint (Elastic Rerank, Cohere Rerank, or a Bedrock-hosted model).

Pitfall shown by the eval: the cross-encoder only sees (query, passage). It
cannot see the signals the first stage used: entity boosts, the "my clients"
retriever, freshness, ACL-aware personalisation. For "Is cardiology offered at
Wrenfield Lakeside?" it promoted the hospital with the *most* cardiology text.
So the re-ranker's order can be blended with the first-stage order:

  replace       final order = cross-encoder order (classic two-stage)
  blend         reciprocal rank fusion of first-stage rank and cross-encoder rank
  entity_aware  blend when the query named a client/facility, replace otherwise
"""

from __future__ import annotations

from functools import lru_cache

from .config import settings


@lru_cache(maxsize=1)
def _model():
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    return TextCrossEncoder(model_name=settings.rerank_model)


STRATEGIES = ("replace", "blend", "entity_aware")
BLEND_K = 10  # small k: with ~30 candidates, rank differences still matter


def blend_ranks(first_stage: list[dict], reranked: list[dict], k: int = BLEND_K) -> list[dict]:
    """RRF over two orderings of the same documents (keyed by doc_id)."""
    score: dict[str, float] = {}
    for order in (first_stage, reranked):
        for rank, d in enumerate(order, start=1):
            score[d["doc_id"]] = score.get(d["doc_id"], 0.0) + 1.0 / (k + rank)
    by_id = {d["doc_id"]: d for d in first_stage}
    out = sorted(by_id.values(), key=lambda d: score[d["doc_id"]], reverse=True)
    for d in out:
        d["score"] = score[d["doc_id"]]
    return out


def rerank(query: str, docs: list[dict], strategy: str = "replace") -> tuple[list[dict], str | None]:
    try:
        model = _model()
    except Exception as e:  # model not installed / offline
        return docs, f"re-ranker unavailable ({type(e).__name__}); kept first-stage order"
    first_stage = list(docs)
    for rank, d in enumerate(first_stage, start=1):
        d["first_stage_score"], d["first_stage_rank"] = d["score"], rank
    passages = [f"{d['title']}. {d['passages'][0]['text']}" for d in docs]
    scores = [float(x) for x in model.rerank(query, passages)]
    for d, s in zip(docs, scores):
        d["rerank_score"] = s
    reranked = sorted(docs, key=lambda d: d["rerank_score"], reverse=True)
    for rank, d in enumerate(reranked, start=1):
        d["rerank_rank"] = rank
    if strategy == "blend":
        return blend_ranks(first_stage, reranked), None
    for d in reranked:
        d["score"] = d["rerank_score"]
    return reranked, None

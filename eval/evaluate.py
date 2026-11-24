"""Offline relevance + latency evaluation.

Judged queries live in eval/queries.json. Instead of hand-labelling every
(query, document) pair, each query declares what a relevant document looks
like (practice, optional industry, optional doc type) and grades are derived
from document metadata:

    grade 0  wrong practice (or wrong client / facility for client questions)
    grade 1  right practice
    grade 2  right practice + one more matching criterion
    grade 3  right practice + all criteria

In a real engagement the judged set comes from click logs, search-session
analysis and SME labelling sessions (start with ~50-100 top queries).

Metrics: nDCG@10 (graded), MRR@10 (first "perfect" doc), Recall@10 of
perfect docs, and p50/p95 latency for each retrieval mode.

    python eval/evaluate.py [--modes bm25 hybrid hybrid+understand+rerank ...] [--out eval/results.md]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
for candidate in (HERE.parent / "backend", Path("/srv")):
    if (candidate / "app").exists():
        sys.path.insert(0, str(candidate))
        break

from app.query_understanding import parse  # noqa: E402
from app.search import SearchRequest, search  # noqa: E402
from app.security import resolve_user  # noqa: E402

DATA = Path(os.getenv("DATA_DIR", HERE.parent / "data")) / "documents.jsonl"


CRITERIA = ("practice", "facility", "client", "industry", "doc_type")


def grade(doc: dict, q: dict) -> int:
    """Graded relevance from metadata. The first criterion present is required."""
    crit = [k for k in CRITERIA if q.get(k)]
    first, extra = crit[0], crit[1:]
    if doc.get(first) != q[first]:
        return 0
    if not extra:
        return 3
    matched = sum(doc.get(k) == q[k] for k in extra)
    return 1 + round(2 * matched / len(extra))


def dcg(gains: list[int]) -> float:
    return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(gains))


def evaluate_query(ranked_ids: list[str], q: dict, docs: dict[str, dict], k: int = 10) -> dict:
    gains = [grade(docs[d], q) for d in ranked_ids[:k]]
    ideal = sorted((grade(d, q) for d in docs.values()), reverse=True)[:k]
    ndcg = dcg(gains) / dcg(ideal) if dcg(ideal) else 0.0
    perfect = {d for d, doc in docs.items() if grade(doc, q) == 3}
    rr = next((1 / (i + 1) for i, g in enumerate(gains) if g == 3), 0.0)
    recall = len(perfect & set(ranked_ids[:k])) / len(perfect) if perfect else 0.0
    return {"ndcg": ndcg, "mrr": rr, "recall": recall}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", nargs="+", default=["bm25", "vector", "hybrid", "hybrid+understand", "hybrid+rerank", "hybrid+understand+rerank"])
    ap.add_argument("--repeats", type=int, default=3, help="latency repeats per query")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    docs = {d["doc_id"]: d for d in map(json.loads, DATA.open())}
    queries = json.loads((HERE / "queries.json").read_text())
    user = resolve_user("knowledge-team")  # sees everything: we evaluate ranking, not ACLs
    entities = {f: sorted({d[f] for d in docs.values() if d.get(f)}) for f in ("client", "facility")}

    rows = []
    per_query: dict[str, dict[str, float]] = {}
    for mode_spec in args.modes:
        mode, _, extra = mode_spec.partition("+")  # e.g. hybrid+understand+rerank
        metrics, latencies = [], []
        for q in queries:
            req = SearchRequest(query=q["query"], user=user, mode=mode, size=10,
                                rerank="rerank" in extra, with_facets=False)
            # Entity recognition (client / facility names) always runs, as in the API.
            req.boosts = parse(q["query"], entities)["boosts"]
            if "understand" in extra:  # query understanding -> filters
                u = parse(q["query"])
                req.query, req.filters = u["query"], u["filters"]
            search(req)  # warm-up (model load, caches)
            for _ in range(args.repeats):
                t0 = time.perf_counter()
                res = search(req)
                latencies.append((time.perf_counter() - t0) * 1000)
            ids = [r["doc_id"] for r in res["results"]]
            m = evaluate_query(ids, q, docs)
            metrics.append(m)
            per_query.setdefault(q["query"], {})[mode_spec] = m["ndcg"]
        lat = sorted(latencies)
        rows.append({
            "mode": mode_spec,
            "ndcg@10": statistics.mean(m["ndcg"] for m in metrics),
            "mrr@10": statistics.mean(m["mrr"] for m in metrics),
            "recall@10": statistics.mean(m["recall"] for m in metrics),
            "p50_ms": lat[len(lat) // 2],
            "p95_ms": lat[int(len(lat) * 0.95) - 1],
        })

    lines = [
        f"# Evaluation results\n",
        f"{len(queries)} judged queries, {len(docs)} documents, embedder="
        f"{os.getenv('EMBED_PROVIDER', 'local')}. Latency is end-to-end in the API process "
        f"(single-node local Elasticsearch), {args.repeats} repeats per query.\n",
        "| mode | nDCG@10 | MRR@10 | Recall@10 | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(f"| {r['mode']} | {r['ndcg@10']:.3f} | {r['mrr@10']:.3f} | {r['recall@10']:.3f} "
                     f"| {r['p50_ms']:.0f} | {r['p95_ms']:.0f} |")
    lines += ["", "## nDCG@10 per query", "", "| query | " + " | ".join(args.modes) + " |",
              "|---|" + "---|" * len(args.modes)]
    for qtext, by_mode in per_query.items():
        lines.append(f"| {qtext} | " + " | ".join(f"{by_mode[m]:.2f}" for m in args.modes) + " |")
    report = "\n".join(lines) + "\n"
    print(report)
    if args.out:
        Path(args.out).write_text(report)


if __name__ == "__main__":
    main()

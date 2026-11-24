# Performance and scaling notes (~117k documents)

## Sizing

117k documents is **modest** for Elasticsearch. A rough estimate:

| Item | Estimate |
|---|---|
| Source documents | 117,000 |
| Avg chunks per doc (300 to 500 tokens each; reports and decks run long) | ~10 to 20 → **1.2M to 2.3M chunks** |
| Text and metadata per chunk | ~3 to 5 KB → **5 to 12 GB** of primary data |
| Vectors (1024 dims, float32) | 2.3M × 4 KB ≈ 9.4 GB raw; with `int8_hnsw` about 2.4 GB plus graph overhead |
| Vectors (384 dims, int8) | under 1 GB |

So:
- **1 to 2 primary shards** is plenty (target 10 to 50 GB per shard). Over-sharding is a common cause of
  slow search on small indices. Every shard is a separate Lucene search, plus coordination.
- **Replicas** (1 or 2) for HA and read throughput. Scale query capacity with replicas and nodes, not primaries.
- **Memory for vectors.** HNSW search is fastest when the graph and quantised vectors fit in the
  OS page cache. Leave about 50% of node RAM outside the JVM heap. Quantise with `int8_hnsw`, or `bbq_hnsw`
  on newer versions.

The real problems at this scale are rarely raw capacity. They are **relevance, chunking quality,
metadata quality, permissions and freshness.**

## Indexing

- Use the `_bulk` API with batches of 5 to 15 MB, a few parallel workers, and retries with backoff on 429s.
- For a full rebuild: `refresh_interval: -1` and `number_of_replicas: 0` during the load, then restore both,
  refresh and force-merge read-mostly indices.
- **Blue/green reindex behind an alias** (`kp-chunks` → `kp-chunks-vYYYYMMDD`): zero downtime, instant
  rollback. Use this for mapping changes, analyzer changes and embedding-model upgrades. Vectors from
  different models are not comparable, so a model change always means a full re-embed.
- Deterministic `_id`s (`doc_id#chunk_no`) make ingestion idempotent and incremental. On an update,
  delete the document's old chunks by `doc_id`, then index the new ones.
- Embedding is the bottleneck, not Elasticsearch. Batch it, cache embeddings by content hash, and use
  Bedrock batch inference for backfills.

## Query latency

- **Filters in `filter` context** are cached and don't score. This covers ACLs, facets and date ranges.
- **kNN:** tune `num_candidates` (recall vs latency). Pre-filtering keeps results correct under ACLs.
  Very selective filters make HNSW slower; ES falls back to exact search when the filter is tiny, which is fine.
- **Avoid deep pagination.** Use `search_after` with a point-in-time for exports.
- **Request cache** for repeated aggregation-only requests (facet counts on landing pages).
- Fetch only the needed `_source` fields, and exclude `embedding` from responses.
- Highlighting on long fields: `term_vector: with_positions_offsets` (used here), or limit the fragments.
- Use the **Profile API** and the **search slow log** to find expensive clauses (leading wildcards, huge
  `terms` lists, scripts).
- **Cross-encoder re-rank** dominates latency (about 400 ms on CPU here). Cap the candidate count, use a GPU
  or managed endpoint, or re-rank only for RAG context.
- **LLM latency:** stream answers, use a smaller and faster model for query rewriting and routing, and cache
  answers for popular questions (keyed on the query, the filters and the ACL group set).

## Freshness

- Use near-real-time refresh (1 s default; 5 to 30 s is fine for a knowledge base and cheaper).
- Event-driven incremental ingestion (S3/SharePoint change events → queue → workers).
- **ACL changes must propagate fast.** Sync permission updates separately from content updates, using a
  partial `_update_by_query` on `allowed_groups` for the affected `doc_id`.

## Monitoring

Track these:
- Search p50/p95/p99 latency.
- Zero-result rate.
- Click-through rate and the position of the first click.
- Query reformulation rate.
- Answer feedback.
- Indexing lag and the bulk rejection rate.
- JVM heap, GC and page-cache hit rate.

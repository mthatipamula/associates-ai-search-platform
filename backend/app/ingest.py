"""Bulk ingestion with a zero-downtime (blue/green) reindex.

    python -m app.ingest                 # build a new index and swap the alias
    python -m app.ingest --keep-old      # keep the previous index for rollback

Steps:
 1. Create a new versioned index, e.g. kp-chunks-v20261123-101500, with
    refresh disabled and 0 replicas (fastest bulk load).
 2. Chunk + embed documents in batches; stream them through the bulk helper.
 3. Refresh, restore refresh_interval/replicas, force-merge (read-only data).
 4. Atomically move the alias to the new index; delete the old one.

At ~117k source documents the same flow applies; embedding dominates the
cost, so in AWS it runs as a batch job (Bedrock batch inference or an
embedding worker fleet fed from SQS), not inside the API.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

from elasticsearch import helpers

from .chunking import contextual_header, split_into_chunks
from .config import settings
from .embeddings import get_embedder
from .es import get_es
from .index_schema import index_body

META_FIELDS = [
    "doc_id", "title", "summary", "practice", "industry", "doc_type", "client", "region",
    "published_date", "authors", "tags", "confidentiality", "allowed_groups", "source_uri",
    "facility", "location", "service_lines",
]


def load_documents(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def to_chunks(doc: dict) -> list[dict]:
    out = []
    for i, text in enumerate(split_into_chunks(doc["body"])):
        c = {k: doc.get(k) for k in META_FIELDS}
        c.update(chunk_id=f"{doc['doc_id']}#{i}", chunk_no=i, text=text, word_count=len(text.split()))
        out.append(c)
    return out


def _batched(items: list, n: int) -> Iterator[list]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


def actions(docs: Iterable[dict], index: str, batch_size: int = 64) -> Iterator[dict]:
    embedder = get_embedder()
    docs_by_id = {d["doc_id"]: d for d in docs}
    chunks = [c for d in docs_by_id.values() for c in to_chunks(d)]
    for batch in _batched(chunks, batch_size):
        texts = [f"{contextual_header(docs_by_id[c['doc_id']])}\n{c['text']}" for c in batch]
        vectors = embedder.embed_documents(texts)
        for c, v in zip(batch, vectors):
            # Deterministic _id makes re-runs idempotent (upsert, not duplicate).
            yield {"_index": index, "_id": c["chunk_id"], "_source": {**c, "embedding": v}}


def build_index(docs_path: Path, keep_old: bool = False) -> str:
    es = get_es()
    alias = settings.index_alias
    new_index = f"{alias}-v{datetime.now(timezone.utc):%Y%m%d-%H%M%S}"

    body = index_body()
    body["settings"]["index"].update({"refresh_interval": "-1", "number_of_replicas": 0})
    es.indices.create(index=new_index, **body)

    docs = load_documents(docs_path)
    t0 = time.perf_counter()
    ok, errors = 0, []
    for success, info in helpers.streaming_bulk(
        es, actions(docs, new_index), chunk_size=500, raise_on_error=False, max_retries=3
    ):
        ok += success
        if not success:
            errors.append(info)
    took = time.perf_counter() - t0
    if errors:
        raise RuntimeError(f"{len(errors)} bulk errors, first: {errors[0]}")

    es.indices.put_settings(index=new_index, settings={"index": {"refresh_interval": "1s", "number_of_replicas": 0}})
    es.indices.refresh(index=new_index)
    es.indices.forcemerge(index=new_index, max_num_segments=1)

    old = list(es.indices.get_alias(name=alias).keys()) if es.indices.exists_alias(name=alias) else []
    acts = [{"add": {"index": new_index, "alias": alias}}] + [{"remove": {"index": o, "alias": alias}} for o in old]
    es.indices.update_aliases(actions=acts)
    if not keep_old:
        for o in old:
            es.indices.delete(index=o)

    print(f"indexed {ok} chunks from {len(docs)} documents into {new_index} in {took:.1f}s; alias {alias} -> {new_index}")
    return new_index


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", default=str(Path(settings.data_dir) / "documents.jsonl"))
    ap.add_argument("--keep-old", action="store_true")
    args = ap.parse_args()
    build_index(Path(args.docs), keep_old=args.keep_old)


if __name__ == "__main__":
    main()

"""Structure-aware chunking.

Strategy: split on paragraphs/sections first (documents have meaningful
sections such as Situation / Approach / Results), then pack paragraphs into
~CHUNK_WORDS (default 80) word windows with a small word overlap. Each chunk is embedded with a
short "contextual header" (title, type, practice, industry, client) so a
passage like "Results. 18% uplift..." still knows what it is about.
"""

from __future__ import annotations

from .config import settings


def split_into_chunks(body: str, max_words: int | None = None, overlap: int | None = None) -> list[str]:
    max_words = max_words or settings.chunk_words
    overlap = settings.chunk_overlap_words if overlap is None else overlap
    paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]

    chunks: list[str] = []
    current: list[str] = []
    for para in paragraphs:
        words = para.split()
        # A single very long paragraph is windowed on its own.
        if len(words) > max_words:
            if current:
                chunks.append(" ".join(current))
                current = []
            step = max(1, max_words - overlap)
            for start in range(0, len(words), step):
                chunks.append(" ".join(words[start : start + max_words]))
                if start + max_words >= len(words):
                    break
            continue
        if len(current) + len(words) > max_words and current:
            chunks.append(" ".join(current))
            current = current[-overlap:] if overlap else []
        current.extend(words)
    if current:
        chunks.append(" ".join(current))
    return chunks


def contextual_header(doc: dict) -> str:
    parts = [doc["title"], doc["doc_type"].replace("_", " "), doc["practice"], doc["industry"]]
    for key in ("client", "facility", "location"):
        if doc.get(key):
            parts.append(doc[key])
    return " | ".join(parts)

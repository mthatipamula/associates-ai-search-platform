"""Runtime configuration, read from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


@dataclass(frozen=True)
class Settings:
    # --- Elasticsearch -----------------------------------------------------
    es_url: str = _env("ES_URL", "http://localhost:9200")
    es_api_key: str | None = os.getenv("ES_API_KEY") or None
    # Basic auth (used on AWS, where the password comes from Secrets Manager).
    es_username: str | None = os.getenv("ES_USERNAME") or None
    es_password: str | None = os.getenv("ES_PASSWORD") or None
    # Queries and the app always go through the alias; ingest builds a new
    # versioned index behind it and swaps atomically (blue/green reindex).
    index_alias: str = _env("INDEX_ALIAS", "kp-chunks")

    # --- Embeddings --------------------------------------------------------
    # "local"   -> fastembed (ONNX, CPU) BAAI/bge-small-en-v1.5, 384 dims
    # "bedrock" -> Amazon Titan Text Embeddings v2 (set EMBED_DIMS=512 or 1024)
    # "hash"    -> deterministic hashing trick; no model download (tests / CI)
    embed_provider: str = _env("EMBED_PROVIDER", "local")
    embed_model: str = _env("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    embed_dims: int = int(_env("EMBED_DIMS", "384"))

    # kNN always returns k neighbours, even for nonsense queries. A minimum
    # cosine similarity drops weak matches (tune on the judged query set).
    vector_min_similarity: float = float(_env("VECTOR_MIN_SIMILARITY", "0.62"))

    # --- Re-ranking (optional cross-encoder) --------------------------------
    rerank_model: str = _env("RERANK_MODEL", "Xenova/ms-marco-MiniLM-L-6-v2")
    # replace | blend | entity_aware (see rerank.py)
    rerank_strategy: str = _env("RERANK_STRATEGY", "entity_aware")

    # --- LLM ---------------------------------------------------------------
    # "anthropic" -> Claude API (ANTHROPIC_API_KEY)
    # "bedrock"   -> Claude on Amazon Bedrock (AWS credentials + AWS_REGION)
    # "none"      -> offline: extractive answers and a rule-based agent planner
    llm_provider: str = _env("LLM_PROVIDER", "none")
    llm_model: str = _env("LLM_MODEL", "claude-opus-5-5")
    llm_effort: str = _env("LLM_EFFORT", "medium")
    aws_region: str = _env("AWS_REGION", "us-east-1")

    # --- Chunking ----------------------------------------------------------
    chunk_words: int = int(_env("CHUNK_WORDS", "80"))
    chunk_overlap_words: int = int(_env("CHUNK_OVERLAP_WORDS", "15"))

    data_dir: str = _env("DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data"))

    # Demo identities. Every user is an internal associate; what differs is
    # which client engagement they are staffed on. Firm-wide knowledge is
    # visible to all staff, client-restricted work only to that client's team.
    # In production identity and groups come from SSO (OIDC/SAML) and staffing
    # data, never from a header.
    demo_users: dict[str, dict] = field(
        default_factory=lambda: {
            "associate": {
                "label": "Associate (not on a client team)",
                "groups": ["all-staff"],
            },
            "associate-healthcare": {
                "label": "Associate on Wrenfield Health team (hospital system)",
                "groups": ["all-staff", "client-wrenfield-health"],
            },
            "associate-banking": {
                "label": "Associate on Quenmoor Bank team (banking)",
                "groups": ["all-staff", "client-quenmoor-bank"],
            },
            "associate-retail": {
                "label": "Associate on Marlow & Finch Stores team (retail)",
                "groups": ["all-staff", "client-marlow-and-finch-stores"],
            },
            "knowledge-team": {
                "label": "Knowledge team (curates all content)",
                "groups": ["all-staff", "knowledge-team"],
            },
        }
    )


settings = Settings()

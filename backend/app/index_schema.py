"""Elasticsearch index settings and mappings for the knowledge index.

Design choices (each one is an interview talking point):

* One document per *chunk* (passage), carrying a copy of the parent
  document's metadata. Chunks are what we embed and what RAG cites; results
  are grouped back to documents in the search layer.
* `dynamic: strict` - a typo in an ingest pipeline fails loudly instead of
  silently creating a new field mapping (mapping explosion).
* Separate index-time and search-time analyzers: synonyms are applied only at
  search time (`synonym_graph`) so they can be updated without reindexing.
* Metadata used for filters/facets is `keyword` (doc values, exact match,
  cacheable in the filter cache). Titles also get a `keyword` sub-field.
* `dense_vector` with `int8_hnsw` quantisation: ~4x less memory than float32
  HNSW with a small recall cost; kNN runs with the same ACL/metadata filters
  applied *during* graph search (pre-filtering), not after.
"""

from __future__ import annotations

from .config import settings

# Business synonyms. In production these live in the Synonyms API
# (PUT _synonyms/<set>), owned by the knowledge team, and reload without a
# reindex. Equivalent terms use "a, b"; one-way expansions use "a => a, b".
SYNONYMS = [
    "m&a, m and a, mergers and acquisitions, acquisition, merger",
    "pmi, post merger integration, post-merger integration",
    "genai, gen ai, generative ai, llm, large language model",
    "rag, retrieval augmented generation",
    "complaint, complaints, grievance",
    "procurement, sourcing, purchasing",
    "cost reduction, cost cutting, efficiency, savings",
    "decarbonisation, decarbonization, net zero, net-zero, emissions reduction",
    "esg, sustainability",
    "aml, anti money laundering",
    "kyc, know your customer",
    "pharma, pharmaceutical, pharmaceuticals, life sciences",
    "ev, electric vehicle",
    "opex, operating expense, operating expenses",
    "zbb, zero based budgeting, zero-based budgeting",
    "nps, net promoter score",
    "dd, due diligence",
]


def index_body(dims: int | None = None) -> dict:
    dims = dims or settings.embed_dims
    return {
        "settings": {
            "index": {
                # 117k documents (~1-2M chunks) fit comfortably in 1-2 primary
                # shards; aim for 10-50 GB per shard. Replicas add read
                # throughput and HA (0 locally, >=1 in any real cluster).
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "refresh_interval": "1s",
            },
            "analysis": {
                "filter": {
                    "en_stop": {"type": "stop", "stopwords": "_english_"},
                    # Search-time only: question phrasing is not content. Without
                    # this, "How have we cut complaints?" needs "how", "have" and
                    # "we" to count towards minimum_should_match and finds nothing.
                    "question_words": {
                        "type": "stop",
                        "stopwords": ["how", "what", "why", "which", "where", "when", "who", "whom", "have", "has",
                                      "had", "we", "our", "us", "you", "your", "did", "do", "does", "can", "could",
                                      "would", "should", "any", "me", "show", "find", "tell", "give", "please",
                                      "about", "there", "it", "its"],
                    },
                    "en_stem": {"type": "stemmer", "language": "light_english"},
                    "en_possessive": {"type": "stemmer", "language": "possessive_english"},
                    "kp_synonyms": {
                        "type": "synonym_graph",
                        "synonyms": SYNONYMS,
                        "updateable": True,
                        "lenient": True,
                    },
                },
                "analyzer": {
                    "kp_index": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": ["lowercase", "asciifolding", "en_possessive", "en_stop", "en_stem"],
                    },
                    "kp_search": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": [
                            "lowercase",
                            "asciifolding",
                            "en_possessive",
                            "question_words",
                            "kp_synonyms",
                            "en_stop",
                            "en_stem",
                        ],
                    },
                },
                "normalizer": {
                    "lc": {"type": "custom", "filter": ["lowercase", "asciifolding"]},
                },
            },
        },
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "chunk_id": {"type": "keyword"},
                "doc_id": {"type": "keyword"},
                "chunk_no": {"type": "integer"},
                "title": {
                    "type": "text",
                    "analyzer": "kp_index",
                    "search_analyzer": "kp_search",
                    "fields": {"raw": {"type": "keyword", "normalizer": "lc"}},
                },
                "summary": {"type": "text", "analyzer": "kp_index", "search_analyzer": "kp_search"},
                "text": {
                    "type": "text",
                    "analyzer": "kp_index",
                    "search_analyzer": "kp_search",
                    # Speeds up highlighting on long passages.
                    "term_vector": "with_positions_offsets",
                },
                "practice": {"type": "keyword"},
                "industry": {"type": "keyword"},
                "doc_type": {"type": "keyword"},
                # Client and facility names: keyword for filters/facets, plus an
                # analysed sub-field so "Wrenfield" or "Wrenfield North" match.
                "client": {
                    "type": "keyword",
                    "fields": {
                        "lc": {"type": "keyword", "normalizer": "lc"},
                        "text": {"type": "text", "analyzer": "kp_index", "search_analyzer": "kp_search"},
                    },
                },
                "facility": {
                    "type": "keyword",
                    "fields": {"text": {"type": "text", "analyzer": "kp_index", "search_analyzer": "kp_search"}},
                },
                "location": {"type": "keyword", "fields": {"text": {"type": "text", "analyzer": "kp_index"}}},
                "service_lines": {"type": "keyword"},
                "region": {"type": "keyword"},
                "published_date": {"type": "date"},
                "authors": {"type": "keyword"},
                "tags": {"type": "keyword", "normalizer": "lc"},
                "confidentiality": {"type": "keyword"},
                "allowed_groups": {"type": "keyword"},
                "source_uri": {"type": "keyword", "index": False},
                "word_count": {"type": "integer"},
                "embedding": {
                    "type": "dense_vector",
                    "dims": dims,
                    "index": True,
                    "similarity": "cosine",
                    "index_options": {"type": "int8_hnsw", "m": 16, "ef_construction": 100},
                },
            },
        },
    }

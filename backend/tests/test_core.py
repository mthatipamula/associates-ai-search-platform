"""Unit tests that need no Elasticsearch, model download or LLM."""

import os
import sys
from pathlib import Path

os.environ.setdefault("EMBED_PROVIDER", "hash")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))

from app.chunking import split_into_chunks  # noqa: E402
from app.embeddings import HashEmbedder  # noqa: E402
from app.index_schema import index_body  # noqa: E402
from app.query_understanding import parse  # noqa: E402
from app.rag import extractive_answer  # noqa: E402
from app.search import SearchRequest, filter_clauses, rrf_fuse  # noqa: E402
from app.security import User  # noqa: E402


def test_rrf_rewards_agreement_between_retrievers():
    bm25 = [{"chunk_id": "a"}, {"chunk_id": "b"}, {"chunk_id": "c"}]
    vec = [{"chunk_id": "c"}, {"chunk_id": "b"}, {"chunk_id": "d"}]
    fused = rrf_fuse({"bm25": bm25, "vector": vec})
    order = [f["chunk_id"] for f in fused]
    assert order[0] in ("b", "c")  # found by both lists
    assert set(order) == {"a", "b", "c", "d"}
    assert fused[0]["ranks"].keys() == {"bm25", "vector"}


def test_acl_filter_always_present():
    user = User("associate", ("all-staff",))
    clauses = filter_clauses(SearchRequest(query="x", user=user, filters={"industry": ["Retail"]}))
    assert {"terms": {"allowed_groups": ["all-staff"]}} in clauses
    assert {"terms": {"industry": ["Retail"]}} in clauses


def test_unknown_filter_fields_are_ignored():
    user = User("associate", ("all-staff",))
    clauses = filter_clauses(SearchRequest(query="x", user=user, filters={"allowed_groups": ["*"]}))
    assert clauses == [{"terms": {"allowed_groups": ["all-staff"]}}]


def test_chunking_respects_size_and_keeps_all_text():
    body = "\n\n".join(" ".join(f"w{p}_{i}" for i in range(70)) for p in range(5))
    chunks = split_into_chunks(body, max_words=160, overlap=20)
    assert all(len(c.split()) <= 160 + 20 for c in chunks)
    joined = " ".join(chunks)
    assert all(f"w{p}_69" in joined for p in range(5))


def test_query_understanding_extracts_filters():
    out = parse("pharma pricing case studies since 2022")
    assert out["filters"]["industry"] == ["Pharmaceuticals"]
    assert out["filters"]["doc_type"] == ["case_summary"]
    assert out["date_from"] == "2022-01-01"
    assert out["intent"] == "cases"
    assert "pricing" in out["query"]


def test_query_understanding_expert_intent():
    assert parse("who knows about pricing for insurers")["intent"] == "experts"


def test_hash_embedder_is_normalised():
    v = HashEmbedder(64).embed_query("branch network redesign")
    assert abs(sum(x * x for x in v) - 1.0) < 1e-6


def test_mapping_is_strict_and_vector_dims_match():
    body = index_body(dims=384)
    assert body["mappings"]["dynamic"] == "strict"
    assert body["mappings"]["properties"]["embedding"]["dims"] == 384


def test_extractive_answer_cites_sources():
    sources = [{"n": 1, "text": "Dual sourcing reduced exposure to supply disruption."}]
    assert "[1]" in extractive_answer("how to reduce supply disruption", sources)


def test_eval_grades():
    from evaluate import grade

    q = {"practice": "Pricing", "industry": "Retail"}
    assert grade({"practice": "Pricing", "industry": "Retail", "doc_type": "proposal"}, q) == 3
    assert grade({"practice": "Pricing", "industry": "Banking", "doc_type": "proposal"}, q) == 1
    assert grade({"practice": "Banking", "industry": "Retail", "doc_type": "proposal"}, q) == 0


ENTITIES = {
    "client": ["Wrenfield Health", "Tamsin Bay Health System"],
    "facility": ["Wrenfield North Hospital", "Tamsin Bay Medical Center", "Tamsin Bay Community Hospital"],
}


def test_entity_short_names_are_recognised_as_boosts():
    out = parse("Does Wrenfield North offer cardiology?", ENTITIES)
    assert out["boosts"] == {"facility": ["Wrenfield North Hospital"]}
    assert "Wrenfield North Hospital" in out["query"]
    assert out["filters"] == {}  # names boost, they do not hard-filter


def test_ambiguous_facility_short_name_resolves_to_client():
    # "Tamsin Bay" is the client's short name, not the medical center's.
    assert parse("Tamsin Bay cardiology", ENTITIES)["boosts"] == {"client": ["Tamsin Bay Health System"]}


def test_followup_carries_over_last_entity():
    from app.query_understanding import resolve_followup

    history = ["Where is Wrenfield North Hospital located?"]
    out = resolve_followup("Is cardiology supported there?", history, ENTITIES)
    assert out["carried_over"] == "Wrenfield North Hospital"
    # A new, unrelated topic is left alone.
    assert resolve_followup("store formats for grocery retailers", history, ENTITIES)["carried_over"] is None


def test_extractive_answer_prefers_the_focus_entity():
    sources = [
        {"n": 1, "title": "Facility profile: Wrenfield Lakeside Hospital", "facility": "Wrenfield Lakeside Hospital",
         "text": "Cardiology: Cardiology is not supported on site."},
        {"n": 2, "title": "Facility profile: Wrenfield North Hospital", "facility": "Wrenfield North Hospital",
         "text": "Cardiology: Cardiology is supported for outpatient care only. There is no open-heart surgery."},
    ]
    answer = extractive_answer("Is cardiology supported at Wrenfield North Hospital?", sources,
                               focus=["Wrenfield North Hospital"])
    assert "[2]" in answer and "[1]" not in answer
    assert "no open-heart surgery" in answer  # the rest of the section comes along


def test_blend_ranks_keeps_first_stage_signal():
    from app.rerank import blend_ranks

    first = [{"doc_id": "lakeside"}, {"doc_id": "regional"}, {"doc_id": "north"}]
    # The cross-encoder alone prefers the hospital with the most cardiology text.
    reranked = [{"doc_id": "regional"}, {"doc_id": "north"}, {"doc_id": "lakeside"}]
    blended = [d["doc_id"] for d in blend_ranks(first, reranked)]
    # Lakeside (first-stage #1, cross-encoder #3) is no longer pushed to the bottom.
    assert blended == ["regional", "lakeside", "north"]


def test_blend_ranks_agreement_wins():
    from app.rerank import blend_ranks

    first = [{"doc_id": "a"}, {"doc_id": "b"}, {"doc_id": "c"}]
    reranked = [{"doc_id": "a"}, {"doc_id": "c"}, {"doc_id": "b"}]
    assert blend_ranks(first, reranked)[0]["doc_id"] == "a"


def test_longest_phrase_wins_for_industry():
    assert parse("retail banking case studies")["filters"]["industry"] == ["Banking"]
    assert parse("retail pricing")["filters"]["industry"] == ["Retail"]


def test_typos_in_client_and_hospital_names_are_tolerated():
    entities = {"client": ["Quenmoor Bank", "Wrenfield Health"],
                "facility": ["Wrenfield Lakeside Hospital", "Wrenfield North Hospital"]}
    out = parse("Queenmoor digital transformation", entities)
    assert out["boosts"] == {"client": ["Quenmoor Bank"]}
    assert out["corrections"] == [{"typed": "queenmoor", "understood_as": "Quenmoor Bank"}]
    assert "Quenmoor Bank" in out["query"]
    # The longer (misspelled) hospital name wins over the client's short name.
    assert parse("Wrenfield Lakside cardiology", entities)["boosts"] == {"facility": ["Wrenfield Lakeside Hospital"]}
    # Ordinary words are never "corrected" into names.
    assert parse("digital transformation for a bank", entities)["boosts"] == {}


def test_question_words_are_dropped_from_keyword_search():
    from app.index_schema import index_body

    analysis = index_body(dims=8)["settings"]["analysis"]
    assert "question_words" in analysis["analyzer"]["kp_search"]["filter"]
    assert "question_words" not in analysis["analyzer"]["kp_index"]["filter"]
    assert {"how", "have", "we"} <= set(analysis["filter"]["question_words"]["stopwords"])


def test_topic_falls_back_to_the_recognised_phrase():
    out = parse("Who are our experts on retail banking, and what did their projects achieve?".split(",")[0])
    assert out["intent"] == "experts"
    assert out["filters"]["industry"] == ["Banking"]
    assert out["query"] == "retail banking"

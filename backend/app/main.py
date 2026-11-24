"""FastAPI service: search, answers, agent, facets, documents, plus the demo UI."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import agent, rag
from .config import settings
from .es import get_es
from .llm import llm_enabled
from .query_understanding import parse
from .search import SearchRequest, facet_values, get_document, search
from .security import User, current_user

app = FastAPI(title="Associates AI Search Platform", version="0.1.0")
UI = Path(__file__).resolve().parent.parent / "ui" / "index.html"

Mode = Literal["bm25", "vector", "hybrid", "hybrid_native"]


class Filters(BaseModel):
    practice: list[str] = []
    industry: list[str] = []
    doc_type: list[str] = []
    client: list[str] = []
    region: list[str] = []
    authors: list[str] = []
    facility: list[str] = []
    service_lines: list[str] = []


class SearchBody(BaseModel):
    query: str = ""
    mode: Mode = "hybrid"
    filters: Filters = Field(default_factory=Filters)
    date_from: str | None = None
    date_to: str | None = None
    size: int = Field(10, ge=1, le=50)
    rerank: bool = False
    auto_filters: bool = Field(False, description="Extract filters from the query text first")
    history: list[str] = Field(default_factory=list, description="Earlier questions in this conversation")


class AgentBody(BaseModel):
    question: str


def known_entities(user: User) -> dict[str, list[str]]:
    """Client and facility names this user may see (so mentions can be recognised)."""
    facets = facet_values(user)
    return {f: [b["value"] for b in facets.get(f, [])] for f in ("client", "facility")}


def _to_request(body: SearchBody, user: User, query: str | None = None) -> tuple[SearchRequest, dict]:
    query = body.query if query is None else query
    filters = {k: v for k, v in body.filters.model_dump().items() if v}
    understood = parse(query, known_entities(user)) if query else None
    date_from, date_to, boosts = body.date_from, body.date_to, {}
    if understood:
        # Client / facility mentions are high-precision, so they always apply
        # (as boosts). Industry, type and date extraction is opt-in.
        boosts = understood["boosts"]
        if body.auto_filters:
            for k, v in understood["filters"].items():
                filters.setdefault(k, v)
            query = understood["query"]
            date_from = date_from or understood["date_from"]
            date_to = date_to or understood["date_to"]
    req = SearchRequest(query=query, user=user, mode=body.mode, filters=filters, date_from=date_from,
                        date_to=date_to, size=body.size, rerank=body.rerank, boosts=boosts)
    return req, understood


@app.get("/healthz")
def healthz():
    """Liveness for the load balancer: the process is up. Does not call
    Elasticsearch, so a search-cluster blip doesn't make ECS kill API tasks."""
    return {"status": "ok"}


@app.get("/health")
def health():
    """Readiness / diagnostics: checks Elasticsearch and the index."""
    es = get_es()
    info = es.info()
    count = es.count(index=settings.index_alias)["count"] if es.indices.exists_alias(name=settings.index_alias) else 0
    return {
        "elasticsearch": info["version"]["number"],
        "index_alias": settings.index_alias,
        "chunks": count,
        "embed_provider": settings.embed_provider,
        "llm": settings.llm_provider if llm_enabled() else "none (extractive + rule-based fallbacks)",
    }


@app.get("/api/users")
def users():
    return settings.demo_users


@app.post("/api/search")
def api_search(body: SearchBody, user: User = Depends(current_user)):
    req, understood = _to_request(body, user)
    res = search(req)
    res["understood"] = understood
    res["user"] = user.name
    return res


@app.post("/api/ask")
def api_ask(body: SearchBody, user: User = Depends(current_user)):
    # Conversation: make a follow-up standalone ("Is cardiology supported
    # there?" -> "... (Wrenfield North Hospital)") before retrieving.
    followup = rag.condense(body.query, body.history, known_entities(user))
    req, understood = _to_request(body, user, followup["question"])
    # Retrieve with the understood keywords (entity names kept, question
    # phrasing dropped); the answer step still sees the full question.
    if understood:
        req.query = understood["query"]
    out = rag.answer(req, question=followup["question"])
    out["understood"] = understood
    out["standalone_question"] = followup["question"]
    out["carried_over"] = followup.get("carried_over")
    return out


@app.post("/api/agent")
def api_agent(body: AgentBody, user: User = Depends(current_user)):
    return agent.run_agent(body.question, user)


@app.get("/api/understand")
def api_understand(q: str = Query(...)):
    return parse(q)


@app.get("/api/facets")
def api_facets(user: User = Depends(current_user)):
    return facet_values(user)


@app.get("/api/documents/{doc_id}")
def api_document(doc_id: str, user: User = Depends(current_user)):
    doc = get_document(doc_id, user)
    if not doc:
        # 404 (not 403) so restricted documents are not revealed to exist.
        raise HTTPException(status_code=404, detail="not found")
    return doc


@app.get("/")
def ui():
    return FileResponse(UI)

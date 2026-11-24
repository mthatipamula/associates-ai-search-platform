"""Agentic search: Claude plans and calls search tools in a loop.

Why an agent on top of search? Many associate questions are multi-step:
"Who has done pricing work for insurers, and what did they find?" needs
(1) find relevant case work, (2) aggregate authors into experts, (3) read
the strongest documents, (4) synthesise with citations. A single query
cannot do that; an agent with well-scoped tools can.

Design principles shown here:
* Tools are thin, typed wrappers over the *same* ACL-enforced search API the
  UI uses. The agent can never see more than the user could.
* Filter values are validated against index facets, so the model cannot
  invent a filter that silently returns nothing.
* Bounded loop (MAX_STEPS) and a full trace returned to the UI for
  transparency and debugging.
* Without an LLM, a deterministic planner runs the same tools.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

from .llm import create_message, llm_enabled, text_of
from .query_understanding import parse
from .rag import build_context, extractive_answer
from .search import SearchRequest, facet_values, get_document, search
from .security import User

MAX_STEPS = 6

SYSTEM = """You are a research agent for consultants at a consulting firm. You search the firm's
internal knowledge base (case summaries, industry reports, proposals, methodology guides).

How to work:
- Start by calling list_filter_values if you need exact industry/practice/doc_type values.
- Prefer several focused searches over one broad one; use filters when the question names an
  industry, document type, client or time period.
- For questions about a client's own facts (where a hospital is, which services such as cardiology
  it offers, bed counts), search with the client or facility filter; facility_profile and
  client_profile documents hold those facts.
- Use find_experts when the user asks who knows about something, find_case_examples for prior
  engagements, and get_document to read a promising document in full before relying on it.
- Stop searching once you have enough evidence (you have at most a handful of tool calls).
- Final answer: concise, grounded only in tool results, citing document ids like [KP-00012].
  If evidence is thin, say so and suggest how to refine the search."""

FILTER_PROPS = {
    "industry": {"type": "array", "items": {"type": "string"}, "description": "Exact industry values"},
    "practice": {"type": "array", "items": {"type": "string"}, "description": "Exact practice values"},
    "doc_type": {
        "type": "array",
        "items": {"type": "string", "enum": ["case_summary", "industry_report", "proposal", "methodology",
                                               "client_profile", "facility_profile"]},
    },
    "client": {"type": "array", "items": {"type": "string"}},
    "facility": {"type": "array", "items": {"type": "string"}, "description": "Exact hospital/facility names"},
    "date_from": {"type": "string", "description": "ISO date, e.g. 2022-01-01"},
    "date_to": {"type": "string", "description": "ISO date"},
}

TOOLS = [
    {
        "name": "list_filter_values",
        "description": "List valid values (with document counts) for industry, practice, doc_type, client, "
        "facility, service_lines, region and authors that this user can access. Use before filtering.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "search_documents",
        "description": "Hybrid keyword + semantic search over the knowledge base. Returns the top documents "
        "with their best-matching passages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                **FILTER_PROPS,
                "top_k": {"type": "integer", "minimum": 1, "maximum": 10},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_case_examples",
        "description": "Find prior client engagements (case summaries) on a topic.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}, "industry": FILTER_PROPS["industry"]},
            "required": ["topic"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_experts",
        "description": "Find people at the firm with expertise on a topic, ranked by authorship of relevant "
        "documents, with their supporting documents.",
        "input_schema": {
            "type": "object",
            "properties": {"topic": {"type": "string"}, "industry": FILTER_PROPS["industry"]},
            "required": ["topic"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_document",
        "description": "Read one document in full by id (e.g. KP-00012).",
        "input_schema": {
            "type": "object",
            "properties": {"doc_id": {"type": "string"}},
            "required": ["doc_id"],
            "additionalProperties": False,
        },
    },
]


# --------------------------------------------------------------------------
# Tool implementations (all ACL-enforced through `user`)
# --------------------------------------------------------------------------
class Toolbox:
    def __init__(self, user: User):
        self.user = user
        self._facets: dict | None = None

    def facets(self) -> dict:
        if self._facets is None:
            self._facets = facet_values(self.user)
        return self._facets

    def _validated_filters(self, args: dict) -> tuple[dict[str, list[str]], list[str]]:
        filters, dropped = {}, []
        facets = self.facets()
        for f in ("industry", "practice", "doc_type", "client", "facility"):
            vals = args.get(f) or []
            allowed = {b["value"] for b in facets.get(f, [])}
            ok = [v for v in vals if v in allowed]
            dropped += [f"{f}={v}" for v in vals if v not in allowed]
            if ok:
                filters[f] = ok
        return filters, dropped

    def _compact(self, results: list[dict]) -> list[dict]:
        return [
            {
                "doc_id": d["doc_id"],
                "title": d["title"],
                "doc_type": d["doc_type"],
                "industry": d["industry"],
                "practice": d["practice"],
                "client": d.get("client"),
                "published_date": d["published_date"],
                "authors": d["authors"],
                "passage": d["passages"][0]["text"][:600],
            }
            for d in results
        ]

    def list_filter_values(self) -> dict:
        return {k: v for k, v in self.facets().items() if k != "year"}

    def search_documents(self, query: str, top_k: int = 5, date_from=None, date_to=None, **f) -> dict:
        filters, dropped = self._validated_filters(f)
        req = SearchRequest(query=query, user=self.user, filters=filters, date_from=date_from,
                            date_to=date_to, size=top_k, with_facets=False)
        res = search(req)
        out: dict[str, Any] = {"results": self._compact(res["results"])}
        if dropped:
            out["ignored_invalid_filters"] = dropped
        return out

    def find_case_examples(self, topic: str, industry: list[str] | None = None) -> dict:
        return self.search_documents(topic, top_k=5, industry=industry, doc_type=["case_summary"])

    def find_experts(self, topic: str, industry: list[str] | None = None) -> dict:
        filters, _ = self._validated_filters({"industry": industry})
        res = search(SearchRequest(query=topic, user=self.user, filters=filters, size=15, with_facets=False))
        scores: dict[str, float] = defaultdict(float)
        evidence: dict[str, list[str]] = defaultdict(list)
        for rank, d in enumerate(res["results"], start=1):
            for a in d["authors"]:
                scores[a] += 1.0 / rank  # authorship of higher-ranked docs counts more
                evidence[a].append(f"{d['doc_id']}: {d['title']}")
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:5]
        return {
            "experts": [
                {"name": n, "score": round(s, 3), "documents": evidence[n][:4]} for n, s in ranked
            ]
        }

    def get_document(self, doc_id: str) -> dict:
        doc = get_document(doc_id, self.user)
        if not doc:
            return {"error": f"{doc_id} not found or not accessible to this user"}
        return {**{k: doc[k] for k in ("doc_id", "title", "doc_type", "industry", "practice", "client",
                                       "published_date", "authors")},
                "text": "\n".join(c["text"] for c in doc["chunks"])}

    def call(self, name: str, args: dict) -> dict:
        fn = getattr(self, name, None)
        if fn is None or name.startswith("_") or name in ("call", "facets"):
            return {"error": f"unknown tool {name}"}
        return fn(**args)


# --------------------------------------------------------------------------
# LLM agent loop (manual loop so the same code runs on the Anthropic API and
# on Bedrock, and so every step can be traced and bounded)
# --------------------------------------------------------------------------
def run_llm_agent(question: str, user: User) -> dict:
    tools = Toolbox(user)
    messages: list[dict] = [{"role": "user", "content": question}]
    trace: list[dict] = []

    for step in range(MAX_STEPS):
        resp = create_message(system=SYSTEM, tools=TOOLS, messages=messages)
        if resp.stop_reason == "refusal":
            return {"answer": "The model declined this request.", "trace": trace, "planner": "llm"}
        if resp.stop_reason != "tool_use":
            return {"answer": text_of(resp), "trace": trace, "planner": "llm"}

        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            try:
                out = tools.call(block.name, dict(block.input))
                is_error = "error" in out
            except Exception as e:  # report tool failures to the model, don't crash
                out, is_error = {"error": f"{type(e).__name__}: {e}"}, True
            trace.append({"step": step + 1, "tool": block.name, "input": block.input, "output": out})
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(out)[:12000],
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": results})

    # Step budget exhausted: ask for a final answer without more tools.
    messages.append({"role": "user", "content": "Tool budget reached. Answer now from what you have."})
    resp = create_message(system=SYSTEM, messages=messages)
    return {"answer": text_of(resp), "trace": trace, "planner": "llm"}


# --------------------------------------------------------------------------
# Offline planner: same tools, deterministic plan from query understanding
# --------------------------------------------------------------------------
def run_rule_agent(question: str, user: User) -> dict:
    tools = Toolbox(user)
    entities = {f: [b["value"] for b in tools.facets().get(f, [])] for f in ("client", "facility")}
    # Compound questions ("who knows X, and what did they achieve?"): the
    # first clause sets the topic; a follow-up clause adds a second step.
    head, *rest = re.split(r",?\s+and\s+(?=what|how|which|where|when)", question, maxsplit=1)
    plan = parse(head, entities)
    trace: list[dict] = [{"step": 1, "tool": "understand_query", "input": {"question": question}, "output": plan}]
    f = plan["filters"]

    def call(name: str, **args):
        out = tools.call(name, args)
        trace.append({"step": len(trace) + 1, "tool": name, "input": args, "output": out})
        return out

    lines: list[str] = []
    if plan["intent"] == "experts":
        out = call("find_experts", topic=plan["query"], industry=f.get("industry"))
        for e in out["experts"]:
            lines.append(f"- {e['name']} (score {e['score']}): " + "; ".join(e["documents"][:2]))
        answer = "Likely experts, ranked by authorship of relevant work:\n" + "\n".join(lines)
        if rest and out["experts"]:  # step 2: what did their work achieve?
            cases = call("find_case_examples", topic=plan["query"], industry=f.get("industry"))
            results = [r for r in cases["results"]
                       if set(r["authors"]) & {e["name"] for e in out["experts"]}] or cases["results"]
            outcomes = []
            for r in results[:2]:  # step 3: read the documents to extract outcomes
                full = call("get_document", doc_id=r["doc_id"]).get("text", r["passage"])
                m = re.search(r"Results\. (.+?\.)", full)
                outcomes.append(f"- {r['doc_id']} {r['title']}: {m.group(1) if m else full[:160]}")
            answer += ("\n\nWhat their related engagements achieved:\n" + "\n".join(outcomes) if outcomes
                       else "\n\nNo case summaries on this topic are accessible to you; ask the experts directly.")
    else:
        if plan["intent"] == "cases":
            out = call("find_case_examples", topic=plan["query"], industry=f.get("industry"))
        else:
            out = call("search_documents", query=plan["query"], top_k=5,
                       date_from=plan["date_from"], date_to=plan["date_to"], **f)
        results = out["results"]
        if not results and f:  # multi-step: relax filters and retry
            out = call("search_documents", query=plan["query"], top_k=5)
            results = out["results"]
        if results:
            top = call("get_document", doc_id=results[0]["doc_id"])
            fake = [{"doc_id": r["doc_id"], "title": r["title"], "doc_type": r["doc_type"],
                     "industry": r["industry"], "published_date": r["published_date"],
                     "passages": [{"chunk_id": r["doc_id"], "text": r["passage"]}]} for r in results]
            if "text" in top:
                fake[0]["passages"] = [{"chunk_id": top["doc_id"], "text": top["text"]}]
            _, sources = build_context(fake)
            body = extractive_answer(plan["query"], sources, plan["boosts"].get("facility") or plan["boosts"].get("client"))
            refs = "\n".join(f"[{i + 1}] {r['doc_id']} {r['title']}" for i, r in enumerate(results))
            answer = f"{body}\n\nSources:\n{refs}"
        else:
            answer = "No accessible documents matched. Try broader terms."
    return {"answer": answer, "trace": trace, "planner": "rules"}


def run_agent(question: str, user: User) -> dict:
    if llm_enabled():
        return run_llm_agent(question, user)
    return run_rule_agent(question, user)


__all__ = ["run_agent", "TOOLS", "Toolbox"]

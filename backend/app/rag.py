"""Retrieval-augmented answers with citations.

1. Hybrid retrieval (ACL-filtered) -> top documents and their best passages.
2. Passages are numbered [1]..[n] and given to Claude with instructions to
   answer only from them and cite every claim.
3. Citations are mapped back to doc_id / title / source URI so the UI can
   link straight to the source document.

Offline (LLM_PROVIDER=none) an extractive answer is built from the
highest-overlap sentences, still with citations, so the flow is demoable.
"""

from __future__ import annotations

import re

from .llm import create_message, llm_enabled, text_of
from .query_understanding import resolve_followup
from .search import SearchRequest, search

SYSTEM = """You answer questions for consultants using the firm's internal knowledge base.
Use only the numbered sources provided. Cite every factual sentence with its source number in
square brackets, e.g. [2] or [1][3]. If the sources do not contain the answer, say so plainly and
suggest a better search instead of guessing. Mention client names only as they appear in the
sources. Keep the answer under 200 words, then list up to three follow-up questions."""


CONDENSE = """Rewrite the user's latest question so it can be understood without the conversation.
Replace words like "there", "it" or "that hospital" with the names they refer to. Return only the
rewritten question, or the question unchanged if it is already standalone."""


def condense(question: str, history: list[str], entities: dict[str, list[str]]) -> dict:
    """Turn a follow-up into a standalone question (LLM if configured, else rules)."""
    if not history:
        return {"question": question, "carried_over": None}
    if llm_enabled():
        convo = "\n".join(f"Earlier question: {h}" for h in history[-5:])
        resp = create_message(
            system=CONDENSE,
            max_tokens=2000,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": f"{convo}\nLatest question: {question}"}],
        )
        rewritten = text_of(resp).strip() if resp.stop_reason != "refusal" else ""
        return {"question": rewritten or question, "carried_over": None}
    return resolve_followup(question, history, entities)


def build_context(results: list[dict], max_passages: int = 8) -> tuple[str, list[dict]]:
    sources = []
    lines = []
    for d in results:
        for p in d["passages"][:2]:
            if len(sources) >= max_passages:
                break
            n = len(sources) + 1
            sources.append(
                {
                    "n": n,
                    "doc_id": d["doc_id"],
                    "chunk_id": p["chunk_id"],
                    "title": d["title"],
                    "doc_type": d["doc_type"],
                    "published_date": d["published_date"],
                    "source_uri": d.get("source_uri"),
                    "client": d.get("client"),
                    "facility": d.get("facility"),
                    "text": p["text"],
                }
            )
            meta = f"{d['title']} | {d['doc_type']} | {d['industry']} | {d['published_date']}"
            lines.append(f"[{n}] ({meta})\n{p['text']}")
    return "\n\n".join(lines), sources


# Words that say *what* is being asked about only weakly, or that are part
# of how questions are phrased; they do not count as the question's "aspect".
_GENERIC = {"where", "which", "what", "when", "does", "there", "that", "this", "with", "have", "they",
            "their", "about", "hospital", "hospitals", "located", "location", "offer", "offered",
            "supported", "support", "provide", "provided", "available", "client"}
_SECTION_START = re.compile(r"^[A-Z][A-Za-z ]{2,30}: ")


def _terms(text: str) -> set[str]:
    return set(re.findall(r"[a-z]{4,}", text.lower()))


def extractive_answer(question: str, sources: list[dict], focus: list[str] | None = None,
                      max_sentences: int = 3) -> str:
    """Offline answer: pick the best sentences, preferring the entity asked about.

    score = 3 x (aspect words matched, e.g. "cardiology")
          + 1 x (phrasing words matched, e.g. "located")
          + 2 if the sentence or its source is about the focus entity
    Only sentences close to the best score are kept, so a question about one
    hospital is not padded with facts about its sister hospitals. Fact-sheet
    sections ("Cardiology: ...") are returned whole.
    """
    focus = [f.lower() for f in (focus or [])]
    entity_words = set().union(*(_terms(f) for f in focus)) if focus else set()
    q_terms = _terms(question) - entity_words
    aspect = q_terms - _GENERIC
    phrasing = q_terms & _GENERIC

    candidates = []
    for s in sources:
        sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", s["text"]) if x.strip()]
        about_focus = any(f == (s.get("facility") or "").lower() or f == (s.get("client") or "").lower()
                          for f in focus)
        for i, sent in enumerate(sentences):
            terms = _terms(sent)
            a, p = len(aspect & terms), len(phrasing & terms)
            if aspect and not a:
                continue  # must address what was asked
            if not (a or p):
                continue
            mentions = any(f in sent.lower() for f in focus)
            score = 3 * a + p + (2 if (about_focus or mentions) else 0) + (1 if about_focus else 0)
            candidates.append((score, -s["n"], i, sent, s["n"], sentences, s.get("title", "")))
    if not candidates:
        return "I could not find this in the documents you have access to. Try broader terms or remove filters."

    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    best = candidates[0][0]
    picked, seen = [], set()
    for score, _, i, sent, n, sentences, title in candidates:
        if score < best * 0.75 or len(picked) >= max_sentences:
            break
        if sent in seen:
            continue
        text = sent
        seen.add(sent)
        # Return the rest of a fact-sheet section ("Cardiology: ...") with it.
        for nxt in sentences[i + 1 : i + 4]:
            if _SECTION_START.match(nxt):
                break
            text += " " + nxt
            seen.add(nxt)
        # Name the source so "The hospital runs..." says which hospital.
        picked.append(f"{title.split(': ', 1)[-1]}: {text} [{n}]" if title else f"{text} [{n}]")
    return "Extractive answer (no LLM configured):\n- " + "\n- ".join(picked)


MODE_NAMES = {"bm25": "Keyword (BM25)", "vector": "Semantic (kNN)", "hybrid": "Hybrid", "hybrid_native": "Hybrid"}


def answer(req: SearchRequest, question: str | None = None) -> dict:
    """question: what the user asked (sent to the LLM); req.query: what is searched."""
    question = question or req.query
    res = search(req)
    context, sources = build_context(res["results"])
    if not sources:
        tips = ["rephrase it", "remove filters"]
        if req.mode == "bm25":
            tips.insert(0, "switch to Hybrid mode, which also matches by meaning")
        msg = (f"No documents you can access matched this question in {MODE_NAMES.get(req.mode, req.mode)} "
               f"mode. Try to {', or '.join(tips)}.")
        return {"answer": msg, "citations": [], "search": res}

    if llm_enabled():
        resp = create_message(
            system=SYSTEM,
            messages=[{"role": "user", "content": f"Sources:\n\n{context}\n\nQuestion: {question}"}],
        )
        if resp.stop_reason == "refusal":
            text = "The model declined to answer this question."
        else:
            text = text_of(resp)
        generator = "llm"
    else:
        focus = (req.boosts.get("facility") or req.boosts.get("client") or [])
        text = extractive_answer(question, sources, focus)
        generator = "extractive"

    cited = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
    citations = [s for s in sources if s["n"] in cited] or sources[:3]
    return {"answer": text, "generator": generator, "citations": citations, "search": res}

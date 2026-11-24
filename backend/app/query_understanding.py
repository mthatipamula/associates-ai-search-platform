"""Rule-based query understanding (the offline fallback for the LLM).

Turns "pharma pricing case studies since 2022" into:
  filters  = {industry: [Pharmaceuticals], doc_type: [case_summary]}
  date_from = 2022-01-01
  query    = "pricing"
  intent   = "cases"

With an LLM configured, the agent does this itself via tool arguments; the
rule-based version keeps the demo working offline and is a useful,
predictable baseline (and a guardrail: LLM-proposed filter values are
validated against the same vocabulary).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

INDUSTRY_ALIASES = {
    "Pharmaceuticals": ["pharmaceuticals", "pharmaceutical", "pharma", "life sciences", "drug makers", "drug maker"],
    "Retail": ["retail", "retailer", "grocery", "consumer"],
    "Banking": ["retail banking", "banking", "banks", "bank", "lenders", "lender"],
    "Energy": ["energy", "oil and gas", "utilities", "utility", "power"],
    "Automotive": ["automotive", "auto", "carmaker", "car maker", "vehicle"],
    "Insurance": ["insurance", "insurer", "insurers", "policyholders", "policyholder"],
    "Public Sector": ["public sector", "government", "agency"],
}

DOC_TYPE_ALIASES = {
    "case_summary": ["case studies", "case study", "case examples", "case example", "cases", "case summaries",
                     "case summary", "past engagements", "engagements", "examples"],
    "industry_report": ["industry reports", "industry report", "reports", "report", "outlook", "benchmarks"],
    "proposal": ["proposals", "proposal", "pitch", "pitches"],
    "methodology": ["methodology", "methodologies", "method", "playbook", "how to", "guide"],
}

EXPERT_WORDS = ["who knows", "experts", "expert", "who has worked", "who worked", "specialists", "specialist", "people"]


def _find(aliases: dict[str, list[str]], text: str, consumed: list[str] | None = None) -> tuple[list[str], str]:
    # Longest phrase first across *all* values, so "retail banking" is read
    # as Banking rather than as Retail + Banking.
    pairs = sorted(((w, c) for c, words in aliases.items() for w in words), key=lambda p: len(p[0]), reverse=True)
    found: list[str] = []
    for w, canonical in pairs:
        pat = rf"\b{re.escape(w)}\b"
        if re.search(pat, text):
            if canonical not in found:
                found.append(canonical)
            if consumed is not None:
                consumed.append(w)
            text = re.sub(pat, " ", text)
    return found, text


# Generic words dropped to build short aliases: "Wrenfield Health" -> "Wrenfield",
# "Wrenfield North Hospital" -> "Wrenfield North".
_CLIENT_SUFFIXES = ["health system", "health", "bank", "stores", "capital", "mutual", "assurance", "pharma",
                    "therapeutics", "energy", "power", "communications", "mobile", "motors", "auto group", "retail"]
_FACILITY_SUFFIXES = ["medical center", "community hospital", "rehabilitation hospital", "hospital"]

# Words that point back to something said earlier in the conversation.
ANAPHORA = r"\b(there|that|this|it|its|they|their|them|the hospital|the client|the facility|same)\b"


def _short_names(name: str, suffixes: list[str], min_words: int) -> list[str]:
    shorts = []
    for suf in suffixes:
        if name.lower().endswith(" " + suf):
            short = name[: -len(suf) - 1].strip()
            if len(short.split()) >= min_words and len(short) >= 4:
                shorts.append(short)
    return shorts


def build_aliases(entities: dict[str, list[str]] | None) -> list[tuple[str, str, str]]:
    """(alias_lower, field, canonical) for client and facility names, longest first."""
    out: list[tuple[str, str, str]] = []
    for name in (entities or {}).get("client", []):
        out.append((name.lower(), "client", name))
        for short in _short_names(name, _CLIENT_SUFFIXES, min_words=1):
            out.append((short.lower(), "client", name))
    client_aliases = {a for a, _, _ in out}
    for name in (entities or {}).get("facility", []):
        out.append((name.lower(), "facility", name))
        for short in _short_names(name, _FACILITY_SUFFIXES, min_words=2):
            # "Tamsin Bay Medical Center" -> "Tamsin Bay" would collide with
            # the client's short name; ambiguous aliases are skipped.
            if short.lower() not in client_aliases:
                out.append((short.lower(), "facility", name))
    return sorted(out, key=lambda a: len(a[0]), reverse=True)


FUZZY_MIN_RATIO = 0.85  # "queenmoor" vs "quenmoor" = 0.94; unrelated words score far lower
FUZZY_MIN_LEN = 6       # never fuzzy-match short aliases (too many false positives)


def find_entities(text: str, aliases: list[tuple[str, str, str]],
                  corrections: list[dict] | None = None) -> tuple[dict[str, list[str]], str, list[str]]:
    """Find client/facility mentions. Returns (found, text with placeholders, names in order).

    Exact (case-insensitive) matches first, then a typo-tolerant pass, so
    "Queenmoor" still means Quenmoor Bank. Typo matches are appended to
    `corrections` so the UI can say what was understood.
    """
    found: dict[str, list[str]] = {}
    names: list[str] = []

    def record(fld: str, canonical: str) -> str:
        if canonical not in found.get(fld, []):
            found.setdefault(fld, []).append(canonical)
        names.append(canonical)
        return f" §{len(names) - 1}§ "

    # Longest names first; each tries an exact match, then a typo-tolerant
    # match over word windows of the same length, before shorter names get a
    # turn (so "Wrenfield Lakside" is the hospital, not just "Wrenfield").
    for alias, fld, canonical in aliases:
        pat = rf"(?<![\w§]){re.escape(alias)}(?![\w§])"
        if re.search(pat, text):
            text = re.sub(pat, record(fld, canonical), text)
            continue
        if len(alias) < FUZZY_MIN_LEN or canonical in names:
            continue
        n = len(alias.split())
        tokens = re.findall(r"[\w&'§]+", text)
        for i in range(len(tokens) - n + 1):
            window = " ".join(tokens[i : i + n])
            if "§" in window:
                continue
            if SequenceMatcher(None, window, alias).ratio() >= FUZZY_MIN_RATIO:
                text = re.sub(rf"(?<![\w§]){re.escape(window)}(?![\w§])", record(fld, canonical), text, count=1)
                if corrections is not None:
                    corrections.append({"typed": window, "understood_as": canonical})
                break
    return found, text, names


def resolve_followup(question: str, history: list[str], entities: dict[str, list[str]] | None) -> dict:
    """Make a follow-up question standalone by carrying over the last entity.

    "Where is Wrenfield North Hospital located?" -> "Is cardiology supported
    there?" becomes "Is cardiology supported there? (Wrenfield North Hospital)".
    With an LLM this is the classic "condense question" step; this rule-based
    version keeps it working offline and is easy to test.
    """
    aliases = build_aliases(entities)
    found, _, _ = find_entities(f" {question.lower()} ", aliases)
    q = question.lower()
    is_followup = (bool(re.search(ANAPHORA, q)) or bool(re.match(r"\s*(what|how) about\b", q))
                   or len(question.split()) <= 4)
    if found or not history or not is_followup:
        return {"question": question, "carried_over": None}
    for previous in reversed(history):
        prev_found, _, _ = find_entities(f" {previous.lower()} ", aliases)
        name = (prev_found.get("facility") or prev_found.get("client") or [None])[0]
        if name:
            return {"question": f"{question.rstrip()} ({name})", "carried_over": name}
    return {"question": question, "carried_over": None}


def parse(query: str, entities: dict[str, list[str]] | None = None) -> dict:
    """entities: known names the user can access, e.g. {"client": [...], "facility": [...]}"""
    text = f" {query.lower()} "
    filters: dict[str, list[str]] = {}
    boosts: dict[str, list[str]] = {}
    intent = "search"

    # 1. Entities first, on the original wording, and protected with
    #    placeholders so "Wrenfield North Hospital" is not also read as words.
    #    Named clients/facilities become *boosts*, not filters: the user may be
    #    comparing their client with firm-wide knowledge.
    corrections: list[dict] = []
    found, text, names = find_entities(text, build_aliases(entities), corrections)
    boosts.update(found)

    for w in EXPERT_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", text):
            intent = "experts"
            text = re.sub(rf"\b{re.escape(w)}\b", " ", text)

    # Phrases turned into filters; if nothing else is left, they become the
    # search topic ("experts on retail banking" -> topic "retail banking").
    consumed: list[str] = []
    industries, text = _find(INDUSTRY_ALIASES, text, consumed)
    if industries:
        filters["industry"] = industries

    doc_types, text = _find(DOC_TYPE_ALIASES, text, consumed)
    if doc_types:
        filters["doc_type"] = doc_types
        if intent == "search" and "case_summary" in doc_types:
            intent = "cases"

    date_from = date_to = None
    if m := re.search(r"\b(?:since|after|from)\s+(20\d\d)\b", text):
        date_from = f"{m.group(1)}-01-01"
        text = text.replace(m.group(0), " ")
    if m := re.search(r"\b(?:before|until)\s+(20\d\d)\b", text):
        date_to = f"{int(m.group(1)) - 1}-12-31"
        text = text.replace(m.group(0), " ")
    if m := re.search(r"\blast\s+(\d+)\s+years?\b", text):
        from datetime import date

        date_from = f"{date.today().year - int(m.group(1))}-01-01"
        text = text.replace(m.group(0), " ")
    if m := re.search(r"\bin\s+(20\d\d)\b", text):
        date_from, date_to = f"{m.group(1)}-01-01", f"{m.group(1)}-12-31"
        text = text.replace(m.group(0), " ")

    if intent == "search" and re.match(r"\s*(what|how|why|which|where|is|does|do|are|summari[sz]e|explain)\b", text):
        intent = "answer"

    stop = r"\b(who|find|show|me|any|our|the|for|in|on|about|with|of|we|have|did|do|does|what|how|why|which|is|are|a|an|all|related|to|there|that|it|its)\b"
    cleaned = re.sub(r"\s+", " ", re.sub(stop, " ", text)).strip(" ?.,()")
    # Put entity names back: they are strong signals for BM25 and vectors.
    cleaned = re.sub(r"§(\d+)§", lambda m: names[int(m.group(1))], cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ?.,()")
    return {
        "query": cleaned or " ".join(consumed) or query,
        "filters": filters,
        "boosts": boosts,
        "corrections": corrections,
        "date_from": date_from,
        "date_to": date_to,
        "intent": intent,
    }

"""Generate a fictional consulting knowledge corpus.

Every company, client, person and number below is invented. The corpus is
deterministic (seeded) so that relevance judgments in eval/ stay valid.

Run:  python data/generate_corpus.py   -> writes data/documents.jsonl
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

from healthcare_clients import build_docs

SEED = 42
OUT = Path(__file__).with_name("documents.jsonl")

# ---------------------------------------------------------------------------
# Vocabulary. Each practice has two phrase banks that deliberately use
# *different words for the same idea* (e.g. "procurement" vs "sourcing",
# "lender" vs "bank"). That is what makes synonyms and dense
# vectors measurably useful in the evaluation.
# ---------------------------------------------------------------------------
PRACTICES: dict[str, dict] = {
    # Industry practices: deep sector expertise. Their work is always for
    # clients in that sector (see PRACTICE_INDUSTRIES below).
    "Banking": {
        "slug": "banking",
        "topic": "Retail banking transformation",
        "a": [
            "The branch network was redesigned around fewer, larger advice centres and self-service kiosks.",
            "Digital account opening cut the time to open a current account from days to minutes.",
            "Credit decisioning models were rebuilt to speed up small business lending approvals.",
            "Deposit pricing was segmented to protect net interest margin as interest rates fell.",
        ],
        "b": [
            "The lender moved routine transactions from branches to its mobile app and contact centres.",
            "Mortgage origination was streamlined end to end, reducing time to offer by half.",
            "Relationship managers for SME customers were given a single view of each business's accounts.",
            "Core banking replacement was sequenced product by product to limit migration risk.",
        ],
        "tags": ["retail-banking", "lending", "branches", "deposits"],
    },
    "Retail": {
        "slug": "retail",
        "topic": "Store and omnichannel transformation",
        "a": [
            "Store formats were redesigned, with smaller convenience stores in city centres.",
            "Omnichannel fulfilment let customers order online and collect in store within two hours.",
            "Category management and range reviews removed slow-moving products from the shelves.",
            "Private label ranges were expanded to raise gross margin.",
        ],
        "b": [
            "The grocer rebuilt its online ordering and home delivery operation for profitability.",
            "Store labour scheduling was matched to footfall patterns, improving service at peak hours.",
            "Assortment was localised to the shopper profile of each neighbourhood.",
            "Own-brand products replaced lower-margin branded lines in key categories.",
        ],
        "tags": ["omnichannel", "store-formats", "assortment", "private-label"],
    },
    "Pricing": {
        "slug": "pricing",
        "a": [
            "A value-based pricing architecture replaced cost-plus list prices.",
            "Price elasticity models were estimated for each product family and channel.",
            "Discount governance closed the leakage between list price and pocket price.",
        ],
        "b": [
            "Revenue management rules adjusted price points dynamically by segment and season.",
            "The commercial team adopted deal-scoring guardrails to stop margin erosion.",
            "Promotional spend was reallocated to offers with measurable uplift.",
        ],
        "tags": ["margin", "revenue-management", "elasticity"],
    },
    "Digital Transformation": {
        "slug": "digital",
        "a": [
            "The core platform was modernised and migrated to the cloud in planned waves.",
            "Product-aligned agile teams replaced the project-based delivery model.",
            "A data platform unified customer, product and operational data for analytics.",
        ],
        "b": [
            "Legacy mainframe applications were decomposed into services behind stable APIs.",
            "An engineering excellence programme raised release frequency and reduced incidents.",
            "Self-service digital journeys moved routine transactions out of branches and call centres.",
        ],
        "tags": ["cloud", "agile", "modernisation", "data-platform"],
    },
    "Cost Reduction": {
        "slug": "cost",
        "a": [
            "A zero-based budgeting exercise rebuilt the cost base line by line.",
            "Spans and layers analysis simplified the organisation and removed duplicated roles.",
            "Indirect spend categories were benchmarked against peers to set savings targets.",
        ],
        "b": [
            "The efficiency programme delivered run-rate savings through process automation and shared services.",
            "Opex was reduced by consolidating facilities and rationalising third-party contracts.",
            "Overhead functions moved to a lean operating rhythm with clear accountability for savings.",
        ],
        "tags": ["zero-based-budgeting", "efficiency", "opex"],
    },
    "Mergers & Acquisitions": {
        "slug": "m-and-a",
        "a": [
            "Commercial due diligence tested the target's market share and growth assumptions.",
            "The post-merger integration office tracked synergy capture against the deal model.",
            "A clean team analysed sensitive pricing data before the transaction closed.",
        ],
        "b": [
            "M&A screening ranked acquisition targets by strategic fit and value-creation potential.",
            "The PMI programme harmonised systems, culture and the combined operating model.",
            "Divestiture planning carved out the business unit with minimal stranded cost.",
        ],
        "tags": ["due-diligence", "pmi", "synergies"],
    },
    "Customer Experience": {
        "slug": "cx",
        "a": [
            "Complaint handling was redesigned so most issues are resolved at the first contact.",
            "Journey mapping exposed the moments that drove complaints and low satisfaction scores.",
            "Net promoter feedback loops were embedded in frontline team routines.",
        ],
        "b": [
            "Onboarding was redesigned around early value moments, lifting satisfaction in the first 90 days.",
            "Loyalty programme mechanics were rebuilt to reward engagement rather than spend alone.",
            "Personalised next-best-action recommendations raised cross-sell conversion.",
        ],
        "tags": ["complaints", "nps", "loyalty", "personalisation"],
    },
    "Generative AI": {
        "slug": "genai",
        "a": [
            "A generative AI assistant summarised long documents and drafted first versions for analysts.",
            "Retrieval-augmented generation grounded the large language model in approved internal content.",
            "An AI governance board defined guardrails, evaluation and human review for model outputs.",
        ],
        "b": [
            "GenAI copilots automated routine drafting, with measured productivity gains per role.",
            "LLM use cases were prioritised by value, feasibility and data readiness.",
            "Agentic workflows chained tools together so the model could search, reason and act.",
        ],
        "tags": ["llm", "rag", "ai-governance", "copilot"],
    },
    "Sustainability": {
        "slug": "sustainability",
        "a": [
            "A decarbonisation roadmap set science-based emissions targets across scopes 1, 2 and 3.",
            "Energy efficiency investments were ranked on a marginal abatement cost curve.",
            "Climate risk scenarios were integrated into capital allocation decisions.",
        ],
        "b": [
            "Net-zero commitments were translated into site-level carbon reduction plans.",
            "ESG reporting was automated to meet new disclosure requirements.",
            "Circular economy pilots reduced packaging waste and recovered materials.",
        ],
        "tags": ["net-zero", "esg", "carbon", "climate"],
    },
    "Operating Model": {
        "slug": "opmodel",
        "a": [
            "The operating model was redesigned around customer segments with clear decision rights.",
            "A target organisation structure balanced global scale with local responsiveness.",
        ],
        "b": [
            "Governance forums were simplified and accountabilities documented in a RACI.",
            "Shared capability centres were set up for finance, HR and procurement processes.",
        ],
        "tags": ["organisation-design", "governance"],
    },
    "Risk & Compliance": {
        "slug": "risk",
        "a": [
            "Anti-money laundering controls were strengthened with better transaction monitoring.",
            "A risk appetite framework linked enterprise risks to board-level metrics.",
        ],
        "b": [
            "KYC remediation cleared the backlog of incomplete customer due diligence files.",
            "Regulatory change management tracked new obligations through to control owners.",
        ],
        "tags": ["aml", "kyc", "regulation", "controls"],
    },
}

# Industry practices only take clients from their own sector.
PRACTICE_INDUSTRIES = {"Banking": ["Banking"], "Retail": ["Retail"]}

INDUSTRIES: dict[str, dict] = {
    "Pharmaceuticals": {
        "slug": "healthcare",
        "context": [
            "The client manufactures branded and generic medicines across several therapeutic areas.",
            "Cold-chain distribution and batch release timelines shaped every recommendation.",
        ],
    },
    "Retail": {
        "slug": "consumer",
        "context": [
            "The client operates grocery and general merchandise stores alongside an e-commerce channel.",
            "Store operations and seasonal peaks were central to the business case.",
        ],
    },
    "Banking": {
        "slug": "financial-services",
        "context": [
            "The client is a retail and commercial bank with a large branch network.",
            "Capital requirements and regulatory scrutiny constrained the options considered.",
        ],
    },
    "Energy": {
        "slug": "energy",
        "context": [
            "The client runs upstream assets, refining capacity and a growing renewables portfolio.",
            "Commodity price volatility made scenario planning essential.",
        ],
    },
    "Automotive": {
        "slug": "industrials",
        "context": [
            "The client builds passenger vehicles and is scaling electric vehicle production.",
            "Semiconductor shortages and battery supply were recurring constraints.",
        ],
    },
    "Insurance": {
        "slug": "financial-services",
        "context": [
            "The client underwrites property, casualty and life insurance products.",
            "Claims handling efficiency and underwriting discipline were key value levers.",
        ],
    },
    "Public Sector": {
        "slug": "public-sector",
        "context": [
            "The client is a regional government agency delivering services to citizens.",
            "Procurement rules and public accountability shaped the delivery approach.",
        ],
    },
}

# Fictional clients only.
CLIENTS = {
    "Pharmaceuticals": ["Quillfeather Pharma", "Orrin Therapeutics"],
    "Retail": ["Halvorsen Retail"],
    "Banking": ["Bluepeak Bank", "Ostrava Capital", "Quenmoor Bank"],
    "Energy": ["Corvane Energy", "Sundial Power"],
    "Automotive": ["Ardent Motors", "Kestrel Auto Group"],
    "Insurance": ["Lakeshore Mutual", "Pellucid Assurance"],
    "Public Sector": ["Region of Eastmarch"],
}

REGIONS = ["North America", "Europe", "Asia-Pacific", "Middle East", "Latin America"]

# Fictional experts: (name, home practices, home industries)
EXPERTS = [
    ("Priya Natarajan", ["Retail", "Operating Model"], ["Retail", "Automotive"]),
    ("Tomasz Wierzbicki", ["Pricing", "Customer Experience"], ["Retail", "Insurance"]),
    ("Amara Okafor", ["Generative AI", "Digital Transformation"], ["Banking", "Insurance"]),
    ("Daniel Hoffmann", ["Mergers & Acquisitions", "Cost Reduction"], ["Energy", "Automotive"]),
    ("Sofia Lindqvist", ["Sustainability"], ["Energy", "Retail", "Automotive"]),
    ("Kenji Watanabe", ["Digital Transformation", "Generative AI"], ["Banking", "Public Sector"]),
    ("Isabel Moreno", ["Risk & Compliance", "Operating Model"], ["Banking", "Insurance"]),
    ("Marcus Bell", ["Cost Reduction", "Retail"], ["Retail", "Pharmaceuticals"]),
    ("Leila Haddad", ["Customer Experience", "Pricing"], ["Banking", "Retail"]),
    ("Grace Mbeki", ["Operating Model", "Sustainability"], ["Public Sector", "Energy"]),
    ("Ravi Menon", ["Generative AI", "Banking"], ["Banking", "Retail"]),
    ("Hannah Kowalczyk", ["Mergers & Acquisitions", "Pricing"], ["Insurance", "Pharmaceuticals"]),
]
# Nadia Fernandes (healthcare providers) only authors the hospital-client documents.

DOC_TYPES = {
    "case_summary": "Case summary",
    "industry_report": "Industry report",
    "proposal": "Proposal",
    "methodology": "Methodology guide",
}
# client_profile and facility_profile documents come from healthcare_clients.py

OUTCOMES = [
    "The programme delivered {n}% improvement in the headline metric within {m} months.",
    "Benefits of roughly ${n} million a year were validated by the client's finance team after {m} months.",
    "The pilot scaled to {m} sites and achieved a {n}% uplift against the baseline.",
]


def _experts_for(practice: str, industry: str, rng: random.Random) -> list[str]:
    scored = []
    for name, pracs, inds in EXPERTS:
        score = (2 if practice in pracs else 0) + (1 if industry in inds else 0) + rng.random() * 0.5
        scored.append((score, name))
    scored.sort(reverse=True)
    return [n for _, n in scored[: rng.choice([1, 2, 2, 3])]]


def _body(practice: str, industry: str, doc_type: str, client: str | None, rng: random.Random) -> str:
    p = PRACTICES[practice]
    ind = INDUSTRIES[industry]
    topic = p.get("topic", practice).lower()  # "retail banking transformation", "pricing", ...
    # Each document uses mostly ONE phrase bank so that vocabulary differs
    # between documents on the same topic.
    bank = p["a"] if rng.random() < 0.5 else p["b"]
    other = p["b"] if bank is p["a"] else p["a"]
    paras: list[str] = []

    who = client or f"leading {industry.lower()} companies"
    if doc_type == "case_summary":
        paras.append(f"Situation. {who} asked the team for support on {topic}. " + " ".join(ind["context"]))
        paras.append("Approach. " + " ".join(rng.sample(bank, k=min(3, len(bank)))))
        paras.append("Results. " + rng.choice(OUTCOMES).format(n=rng.randint(8, 35), m=rng.randint(4, 18))
                     + " " + rng.choice(other))
        paras.append("Lessons learned. Early executive sponsorship, a clear baseline and frontline involvement "
                     "were decisive. The team documented reusable tools for future engagements.")
    elif doc_type == "industry_report":
        paras.append(f"Executive summary. This report examines {topic} trends in {industry.lower()}. "
                     + ind["context"][1])
        paras.append("Key findings. " + " ".join(rng.sample(bank, k=min(2, len(bank)))))
        paras.append("Benchmarks. Leaders outperform the median by "
                     f"{rng.randint(10, 40)}% on cost and {rng.randint(5, 25)}% on growth. " + rng.choice(other))
        paras.append("Outlook. Companies that invest now are expected to widen the gap over the next three years.")
    elif doc_type == "proposal":
        paras.append(f"Context. {who} is considering a programme on {topic}. " + ind["context"][0])
        paras.append("Proposed approach. Phase one diagnoses the baseline; phase two designs the target state; "
                     "phase three pilots and scales. " + rng.choice(bank))
        paras.append(f"Team and timeline. A core team of {rng.randint(3, 8)} consultants over "
                     f"{rng.randint(8, 24)} weeks, supported by subject-matter experts.")
    else:  # methodology
        paras.append(f"Purpose. This guide sets out the firm's standard method for {topic} work.")
        paras.append("Steps. " + " ".join(bank))
        paras.append("Tools and templates. Diagnostic questionnaires, benchmark databases and a value-tracking "
                     "workbook. " + rng.choice(other))
        paras.append(f"Industry notes. In {industry.lower()}, " + ind["context"][1].lower())
    return "\n\n".join(paras)


def generate(n_docs: int = 120) -> list[dict]:
    rng = random.Random(SEED)
    docs = []
    practices = list(PRACTICES)
    industries = list(INDUSTRIES)
    start = date(2016, 1, 1)
    for i in range(n_docs):
        practice = practices[i % len(practices)] if i < len(practices) * 4 else rng.choice(practices)
        industry = rng.choice(PRACTICE_INDUSTRIES.get(practice, industries))
        doc_type = rng.choices(list(DOC_TYPES), weights=[5, 2, 2, 1])[0]
        client = rng.choice(CLIENTS[industry]) if doc_type in ("case_summary", "proposal") else None
        published = start + timedelta(days=rng.randint(0, 3800))
        authors = _experts_for(practice, industry, rng)

        # Document-level security: client-specific work is restricted to the
        # client team, the relevant industry practice and the knowledge team.
        groups = ["knowledge-team"]
        if client and rng.random() < 0.45:
            confidentiality = "client-restricted"
            client_slug = client.lower().replace("&", "and").replace(" ", "-")
            groups += [f"client-{client_slug}", f"practice-{INDUSTRIES[industry]['slug']}"]
        else:
            confidentiality = "internal"
            groups += ["all-staff"]

        label = DOC_TYPES[doc_type]
        subject = client or industry
        topic = PRACTICES[practice].get("topic", practice)
        title = f"{label}: {topic} for {subject}"
        industry_practice = practice in PRACTICE_INDUSTRIES
        if doc_type == "industry_report":
            title = (f"{industry} Industry Outlook {published.year}" if industry_practice
                     else f"{industry} {practice} Outlook {published.year}")
        elif doc_type == "methodology":
            title = (f"{topic} methodology guide" if industry_practice
                     else f"{practice} methodology guide ({industry} edition)")

        body = _body(practice, industry, doc_type, client, rng)
        summary = body.split("\n\n")[1][:280]
        docs.append(
            {
                "doc_id": f"KP-{i + 1:05d}",
                "title": title,
                "summary": summary,
                "body": body,
                "practice": practice,
                "industry": industry,
                "doc_type": doc_type,
                "client": client,
                "region": rng.choice(REGIONS),
                "published_date": published.isoformat(),
                "authors": authors,
                "tags": rng.sample(PRACTICES[practice]["tags"], k=min(2, len(PRACTICES[practice]["tags"]))),
                "confidentiality": confidentiality,
                "allowed_groups": groups,
                "source_uri": f"s3://knowledge-portfolio-raw/{doc_type}/KP-{i + 1:05d}.pdf",
                "facility": None,
                "location": None,
                "service_lines": [],
            }
        )
    # Client-specific hospital-system documents (profiles, facility fact
    # sheets, engagements). Appended last so earlier ids stay stable.
    docs += build_docs(start_index=len(docs))
    return docs


if __name__ == "__main__":
    docs = generate()
    with OUT.open("w") as f:
        for d in docs:
            f.write(json.dumps(d) + "\n")
    print(f"wrote {len(docs)} documents to {OUT}")

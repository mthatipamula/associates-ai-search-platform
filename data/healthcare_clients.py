"""Fictional hospital-system clients with facility-level facts.

This is the "client-specific" part of the knowledge portfolio: an associate
staffed on a hospital-system client should be able to ask things like
"Where is Wrenfield North Hospital located?" or "Is cardiology offered there?"
and get the answer from their client's documents.

All organisations and hospitals here are invented. Cities are real places
used only as locations for the invented hospitals.

Facts are kept as structured data and rendered into documents, the same way
a real pipeline would combine a client master-data source (CRM, facility
registry) with unstructured engagement documents.
"""

from __future__ import annotations

SYSTEMS = [
    {
        "client": "Wrenfield Health",
        "short": "Wrenfield",
        "hq": ("Columbus", "Ohio"),
        "region": "North America",
        "profile_date": "2026-03-02",
        "summary": "Wrenfield Health is a not-for-profit health system with four hospitals in Ohio, "
        "about 1,100 licensed beds and roughly 9,500 employees.",
        "priorities": [
            "grow the cardiovascular service line and keep complex cardiac care in-system",
            "reduce emergency department boarding and length of stay",
            "stabilise nurse staffing and reduce agency spend",
        ],
        "facilities": [
            {
                "name": "Wrenfield Regional Medical Center",
                "city": "Columbus", "state": "Ohio", "beds": 612,
                "kind": "academic tertiary-care hospital and the system's flagship",
                "trauma": "Level I adult trauma center with a 24/7 emergency department",
                "service_lines": ["Cardiology", "Cardiac Surgery", "Oncology", "Neurology", "Orthopedics",
                                  "Maternity", "Transplant"],
                "cardiology": "Yes, full cardiology is supported. The hospital runs four cardiac catheterization "
                "labs around the clock for heart attack (STEMI) care, open-heart surgery, electrophysiology, "
                "structural heart procedures including TAVR, and an advanced heart failure clinic. It is the "
                "system's referral center for complex cardiac cases.",
            },
            {
                "name": "Wrenfield North Hospital",
                "city": "Delaware", "state": "Ohio", "beds": 184,
                "kind": "community hospital",
                "trauma": "Level III trauma center with a 24/7 emergency department",
                "service_lines": ["Cardiology", "General Surgery", "Orthopedics", "Maternity"],
                "cardiology": "Cardiology is supported for outpatient and diagnostic care only. Services include "
                "a cardiology clinic, echocardiography, stress testing and one diagnostic catheterization lab "
                "open on weekdays. There is no open-heart surgery; heart attack (STEMI) patients are transferred "
                "to Wrenfield Regional Medical Center in Columbus.",
            },
            {
                "name": "Wrenfield Children's Hospital",
                "city": "Columbus", "state": "Ohio", "beds": 220,
                "kind": "pediatric hospital",
                "trauma": "Level I pediatric trauma center",
                "service_lines": ["Pediatric Cardiology", "Neonatal Intensive Care", "Pediatric Oncology",
                                  "Pediatric Surgery"],
                "cardiology": "Pediatric cardiology is supported, including congenital heart surgery and a "
                "pediatric cardiac intensive care unit. Adult cardiology is not offered at this hospital.",
            },
            {
                "name": "Wrenfield Lakeside Hospital",
                "city": "Sandusky", "state": "Ohio", "beds": 96,
                "kind": "rural community hospital",
                "trauma": "Emergency department open 24/7, not a designated trauma center",
                "service_lines": ["General Medicine", "General Surgery", "Imaging", "Telecardiology"],
                "cardiology": "Cardiology is not supported on site. Cardiac patients are seen through "
                "telecardiology consults with Wrenfield Regional Medical Center and transferred when they need "
                "a catheterization lab.",
            },
        ],
        "engagements": [
            {
                "title": "Case summary: Cardiology service line growth plan for Wrenfield Health",
                "doc_type": "case_summary", "date": "2025-06-18",
                "authors": ["Nadia Fernandes", "Priya Natarajan"],
                "body": [
                    "Situation. Wrenfield Health was losing complex cardiac cases to competing systems in "
                    "central Ohio, and heart attack transfer times from its community hospitals were above target.",
                    "Approach. The team consolidated open-heart surgery and structural heart procedures at "
                    "Wrenfield Regional Medical Center, extended diagnostic catheterization at Wrenfield North "
                    "Hospital, and launched telecardiology at Wrenfield Lakeside Hospital. A single cardiology "
                    "transfer center now coordinates STEMI transfers.",
                    "Results. Door-to-balloon time for transferred heart attack patients fell by 22 minutes, "
                    "in-system retention of cardiac surgery cases rose 14 percent, and cardiology outpatient "
                    "visits grew 11 percent within 12 months.",
                ],
            },
            {
                "title": "Case summary: Emergency department throughput for Wrenfield Health",
                "doc_type": "case_summary", "date": "2024-09-03",
                "authors": ["Nadia Fernandes", "Marcus Bell"],
                "body": [
                    "Situation. Emergency department boarding at Wrenfield Regional Medical Center averaged "
                    "nine hours, and patients leaving without being seen had doubled in two years.",
                    "Approach. The team introduced a capacity command center, earlier discharge planning on "
                    "inpatient units, and a split-flow model for low-acuity emergency patients.",
                    "Results. Boarding time fell 31 percent and left-without-being-seen rates returned to "
                    "pre-pandemic levels within nine months.",
                ],
            },
            {
                "title": "Proposal: Nurse staffing and workforce model for Wrenfield Health",
                "doc_type": "proposal", "date": "2026-02-10",
                "authors": ["Nadia Fernandes", "Grace Mbeki"],
                "body": [
                    "Context. Wrenfield Health spends heavily on agency nurses, especially at Wrenfield North "
                    "Hospital and Wrenfield Lakeside Hospital, and nurse turnover exceeds 20 percent.",
                    "Proposed approach. Build a system-wide float pool, redesign unit staffing grids, and "
                    "launch a nurse residency program with local colleges.",
                    "Team and timeline. A core team of five consultants over 14 weeks, with clinical advisors.",
                ],
            },
        ],
    },
    {
        "client": "Tamsin Bay Health System",
        "short": "Tamsin Bay",
        "hq": ("Sarasota", "Florida"),
        "region": "North America",
        "profile_date": "2025-11-12",
        "summary": "Tamsin Bay Health System is a regional health system on Florida's Gulf Coast with three "
        "hospitals, about 810 licensed beds and a fast-growing retiree population in its service area.",
        "priorities": [
            "expand structural heart and cardiac surgery capacity for an ageing population",
            "build a post-acute and rehabilitation network",
            "make hospitals and services more resilient during hurricane season",
        ],
        "facilities": [
            {
                "name": "Tamsin Bay Medical Center",
                "city": "Sarasota", "state": "Florida", "beds": 540,
                "kind": "tertiary-care hospital and the system's flagship",
                "trauma": "Level II trauma center with a 24/7 emergency department",
                "service_lines": ["Cardiology", "Cardiac Surgery", "Oncology", "Neurology", "Orthopedics"],
                "cardiology": "Yes, full cardiology is supported, including 24/7 catheterization labs, cardiac "
                "surgery, a structural heart program (TAVR and mitral repair) and electrophysiology.",
            },
            {
                "name": "Tamsin Bay Community Hospital",
                "city": "Bradenton", "state": "Florida", "beds": 210,
                "kind": "community hospital",
                "trauma": "Emergency department open 24/7, not a designated trauma center",
                "service_lines": ["Cardiology", "General Surgery", "Maternity", "Imaging"],
                "cardiology": "Cardiology is supported, including a catheterization lab with 24/7 emergency "
                "angioplasty (PCI) for heart attacks. Cardiac surgery is not offered; surgical cases go to "
                "Tamsin Bay Medical Center in Sarasota.",
            },
            {
                "name": "Tamsin Bay Rehabilitation Hospital",
                "city": "Venice", "state": "Florida", "beds": 60,
                "kind": "inpatient rehabilitation hospital",
                "trauma": "No emergency department",
                "service_lines": ["Inpatient Rehabilitation", "Cardiac Rehabilitation", "Stroke Rehabilitation"],
                "cardiology": "Acute cardiology is not supported. The hospital offers cardiac rehabilitation for "
                "patients recovering from heart attacks and heart surgery.",
            },
        ],
        "engagements": [
            {
                "title": "Case summary: Structural heart program expansion for Tamsin Bay Health System",
                "doc_type": "case_summary", "date": "2023-10-05",
                "authors": ["Nadia Fernandes", "Hannah Kowalczyk"],
                "body": [
                    "Situation. Demand for TAVR and other structural heart procedures at Tamsin Bay Medical "
                    "Center was growing faster than catheterization lab capacity.",
                    "Approach. The team re-sequenced lab schedules, added a hybrid operating room, and created "
                    "a referral pathway from Tamsin Bay Community Hospital.",
                    "Results. Structural heart volumes grew 35 percent with no increase in waiting times.",
                ],
            },
            {
                "title": "Proposal: Post-acute and rehabilitation network strategy for Tamsin Bay Health System",
                "doc_type": "proposal", "date": "2026-01-22",
                "authors": ["Nadia Fernandes", "Sofia Lindqvist"],
                "body": [
                    "Context. Tamsin Bay Health System discharges many older patients to post-acute care "
                    "outside the system, and Tamsin Bay Rehabilitation Hospital in Venice runs near capacity.",
                    "Proposed approach. Size demand for rehabilitation beds, evaluate partnerships with skilled "
                    "nursing facilities, and design a cardiac and stroke rehabilitation network.",
                    "Team and timeline. A core team of four consultants over 10 weeks.",
                ],
            },
        ],
    },
]

INDUSTRY = "Healthcare Providers"


def _slug(name: str) -> str:
    return name.lower().replace("&", "and").replace("'", "").replace(" ", "-")


def build_docs(start_index: int) -> list[dict]:
    """Render the structured client data into knowledge-portfolio documents."""
    docs: list[dict] = []

    def add(**d):
        n = start_index + len(docs) + 1
        doc_id = f"KP-{n:05d}"
        body = "\n\n".join(d.pop("paragraphs"))
        docs.append({
            "doc_id": doc_id,
            "summary": body.split("\n\n")[0][:280],
            "body": body,
            "industry": INDUSTRY,
            "tags": [],
            "confidentiality": "client-restricted",
            "source_uri": f"s3://knowledge-portfolio-raw/{d['doc_type']}/{doc_id}.pdf",
            **d,
        })

    for s in SYSTEMS:
        client = s["client"]
        # Client facts are under NDA: only the client team (and the knowledge
        # team that curates content) can see them.
        groups = ["knowledge-team", f"client-{_slug(client)}"]
        hospitals = "; ".join(f"{f['name']} in {f['city']}, {f['state']} ({f['beds']} beds)" for f in s["facilities"])
        cardio = [f["name"] for f in s["facilities"] if "Cardiology" in f["service_lines"]]

        add(
            title=f"Client profile: {client}",
            doc_type="client_profile", practice="Client Profile", client=client,
            facility=None, location=f"{s['hq'][0]}, {s['hq'][1]}", service_lines=[],
            region=s["region"], published_date=s["profile_date"], authors=["Nadia Fernandes"],
            allowed_groups=groups,
            paragraphs=[
                f"Overview: {s['summary']} {client} is headquartered in {s['hq'][0]}, {s['hq'][1]}.",
                f"Hospitals: {hospitals}.",
                f"Cardiology: adult cardiology is offered at {', '.join(cardio)}.",
                "Strategic priorities: " + "; ".join(s["priorities"]) + ".",
                "Engagement history: " + "; ".join(e["title"].split(": ", 1)[1] + f" ({e['date'][:4]})"
                                                   for e in s["engagements"]) + ".",
            ],
        )
        for f in s["facilities"]:
            add(
                title=f"Facility profile: {f['name']}",
                doc_type="facility_profile", practice="Client Profile", client=client,
                facility=f["name"], location=f"{f['city']}, {f['state']}", service_lines=f["service_lines"],
                region=s["region"], published_date=s["profile_date"], authors=["Nadia Fernandes"],
                allowed_groups=groups,
                paragraphs=[
                    f"Location: {f['name']} is a {f['beds']}-bed {f['kind']} located in {f['city']}, "
                    f"{f['state']}. It is part of {client}.",
                    f"Cardiology: {f['cardiology']}",
                    f"Emergency care: {f['trauma']}.",
                    f"Service lines: {', '.join(f['service_lines'])}.",
                ],
            )
        for e in s["engagements"]:
            add(
                title=e["title"], doc_type=e["doc_type"], practice="Healthcare Operations", client=client,
                facility=None, location=f"{s['hq'][0]}, {s['hq'][1]}", service_lines=[],
                region=s["region"], published_date=e["date"], authors=e["authors"],
                allowed_groups=groups, paragraphs=e["body"],
            )
    return docs

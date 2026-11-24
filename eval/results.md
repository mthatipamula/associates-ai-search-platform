# Evaluation results

21 judged queries, 134 documents, embedder=local. Latency is end-to-end in the API process (single-node local Elasticsearch), 3 repeats per query.

| mode | nDCG@10 | MRR@10 | Recall@10 | p50 ms | p95 ms |
|---|---|---|---|---|---|
| bm25 | 0.788 | 0.921 | 0.769 | 12 | 26 |
| vector | 0.862 | 0.897 | 0.863 | 32 | 68 |
| hybrid | 0.909 | 0.952 | 0.915 | 52 | 75 |
| hybrid+understand | 0.881 | 0.976 | 0.927 | 46 | 81 |
| hybrid+rerank | 0.915 | 0.929 | 0.887 | 1091 | 1589 |
| hybrid+understand+rerank | 0.899 | 1.000 | 0.935 | 723 | 1449 |

## nDCG@10 per query

| query | bm25 | vector | hybrid | hybrid+understand | hybrid+rerank | hybrid+understand+rerank |
|---|---|---|---|---|---|---|
| complaint handling and onboarding for insurers | 0.63 | 0.96 | 0.93 | 0.88 | 0.98 | 0.88 |
| post-merger integration synergy tracking | 0.80 | 0.94 | 0.94 | 0.94 | 1.00 | 1.00 |
| LLM copilots for bank employees | 0.97 | 0.00 | 0.81 | 0.66 | 0.37 | 0.66 |
| decarbonisation plan for a bank | 0.59 | 0.95 | 0.77 | 0.91 | 0.87 | 0.91 |
| digital account opening and branch network redesign for a lender | 0.75 | 0.95 | 0.99 | 0.97 | 0.99 | 0.99 |
| zero-based budgeting case study | 0.81 | 0.85 | 0.88 | 0.91 | 0.91 | 0.91 |
| dynamic pricing for insurers | 0.65 | 0.97 | 0.74 | 0.81 | 0.98 | 0.81 |
| anti money laundering transaction monitoring | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| moving legacy mainframe applications to the cloud | 0.75 | 0.84 | 0.84 | 0.84 | 0.84 | 0.84 |
| organisation redesign and decision rights | 1.00 | 0.43 | 0.94 | 0.94 | 1.00 | 1.00 |
| click and collect and store formats for a grocer | 0.22 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| bank overhead efficiency programme | 0.85 | 0.67 | 0.86 | 0.86 | 0.75 | 0.86 |
| guardrails and human review for AI generated content | 0.56 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| insurance pricing benchmark report | 0.86 | 0.81 | 0.87 | 0.47 | 0.78 | 0.47 |
| agile delivery and digital services for government | 0.95 | 0.93 | 0.95 | 0.83 | 0.95 | 0.83 |
| M&A due diligence for an insurance acquisition | 0.85 | 0.95 | 0.97 | 0.86 | 0.94 | 0.86 |
| Where is Wrenfield North Hospital located? | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Is cardiology offered at Wrenfield Lakeside? | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| Tamsin Bay Community Hospital heart attack care | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| cardiology growth project for Wrenfield | 0.68 | 0.86 | 0.85 | 0.85 | 0.86 | 0.85 |
| Tamsin Bay rehabilitation network plans | 0.64 | 1.00 | 0.76 | 0.76 | 1.00 | 1.00 |

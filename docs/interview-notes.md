# Interview notes: AI-powered enterprise knowledge search

Context, as described in the brief: a consulting firm runs an internal "knowledge portfolio" search
platform. Associates (employees) use it to find historical, domain-specific and client-specific documents.
It runs on AWS, Elasticsearch is central, and the collection holds about 117k documents. The known pain
points are indexing, retrieval, relevance and performance. The firm wants new features using AI and
agentic capabilities **on top of the existing platform**.

---

## 1. The 60-second framing

> "At 117k documents, scale isn't the hard part. Elasticsearch handles that on one or two shards. The
> hard parts are **relevance** (people use different words than the documents), **content quality**
> (chunking and metadata), **permissions** (client-confidential work), and **trust** (AI answers must be
> grounded and cited). I'd improve this in layers: measure first, fix lexical relevance, add semantic
> retrieval as a hybrid alongside BM25, then put RAG answers and agentic workflows on top of the *same*
> permission-aware retrieval API. Every step is measured against a judged query set and released behind
> a flag."

## 2. Demo walkthrough (5 minutes)

1. **Search tab, auto-filters on:** `branch and digital banking case studies`. The query is
   understood as industry, document type and date filters plus the topic. Point out the facets with
   document counts and the `bm25 #1, vector #2` rank badges that show the fusion.
2. **Switch *Viewing as*** from "Associate (not on a client team)" to "Associate on Wrenfield Health
   team". Everyone is an associate. The difference is staffing: client-restricted work appears only for
   that client's team, and the facet counts change. That is document-level security inside the query,
   including kNN. In production the identity comes from SSO and the groups from staffing data.
3. **Mode dropdown:** compare BM25, vector and hybrid on `digital account opening and branch network
   redesign for a lender`. BM25 struggles ("lender" never appears where documents say "bank") and vector
   finds it. Tick *Re-rank*.
4. **Ask tab** (as the Wrenfield team associate): `Where is Wrenfield North Hospital located?`, then the
   follow-up `Is cardiology supported there?`. Point out "Understood as: … (Wrenfield North Hospital)"
   and the citations back to the facility fact sheet.
5. **Agent tab:** `Who are our experts on retail banking, and what did their projects achieve?` Show the trace: understand query, then find_experts, then find_case_examples, then get_document.
6. **eval/results.md:** nDCG and MRR per mode. "I wouldn't ship a relevance change without this table."

---

## 3. Talking points by discussion area

### a) Search architecture and system design

- **Layers:** sources → ingestion (extract, enrich, chunk, embed) → Elasticsearch → search API →
  experiences (search UI, answers, agent, Teams/Slack bot).
- **One retrieval API for everything.** UI search, RAG and agent tools call the same service, so relevance
  gains and security apply everywhere. The AI layer is a *client* of search and doesn't replace it.
- **Aliases and versioned indices** for zero-downtime reindexing and rollback.
- **Ingestion is event-driven and idempotent:** S3/SharePoint events → SQS → workers → `_bulk`, with
  deterministic IDs and a DLQ.
- **Stateless API on ECS Fargate,** Elasticsearch on Elastic Cloud on AWS (PrivateLink) or self-managed,
  and Bedrock for models so data stays in the AWS account.
- **Observability** is a product feature: query logs, clicks and answer feedback are the raw material for
  relevance work.

### b) Elasticsearch and search performance

- **Shards:** at this size, 1 to 2 primaries plus replicas. Over-sharding hurts small indices. Scale reads
  with replicas.
- **Mappings:** `keyword` for filters and facets, `text` with proper analyzers for content, `dynamic: strict`
  to stop mapping explosions, `dense_vector` with int8 quantisation.
- **Queries:** put non-scoring clauses in `filter` context (cached), use `search_after` rather than deep
  `from/size`, fetch only the fields you need, and exclude vectors from `_source` in responses.
- **kNN tuning:** `num_candidates` trades recall against latency. Use pre-filters for ACLs and a similarity
  threshold so the vector side doesn't return junk.
- **Diagnosis tools:** Profile API, slow logs, hot threads, node stats (heap, GC, cache hit rates, rejections).
- **Bulk indexing:** refresh off and replicas 0 during backfills, batches of 5 to 15 MB, backoff on 429s.

### c) Indexing and retrieval strategies at scale

- **Chunking matters more than the model.** Split on structure (sections, slides), aim for 200 to 500
  tokens with overlap, and prefix each chunk with a *contextual header* (title, type, client, industry)
  before embedding.
- **Index chunks, return documents.** Group by `doc_id` and count facets with cardinality.
- **Metadata enrichment at ingest** (practice, industry, client, document type, authors), using rules
  where possible and an LLM classifier where needed. Clean facets drive filtering *and* agent tool arguments.
- **Hybrid retrieval:** BM25 handles exact terms, acronyms, client names and codes; dense vectors handle
  paraphrase and vocabulary mismatch. Fuse them with **RRF**, which needs no score normalisation.
- **Two-stage ranking:** a cheap, recall-oriented first stage, then a cross-encoder re-rank on the top 20
  to 50 results.
- **Options in the Elastic ecosystem:** `semantic_text` with inference endpoints (simplest to operate),
  ELSER sparse vectors (strong English retrieval, no fine-tuning), dense vectors from Bedrock (Titan or
  Cohere), the `rrf` retriever and `text_similarity_reranker` (check the license tier).
- **Incremental updates:** delete and reindex a document's chunks, and sync ACL changes separately and quickly.

### d) Improving relevance and search experience

- **Measure first.** Build a judged set (50 to 100 real queries, graded by SMEs). Track nDCG@10 and MRR offline;
  track CTR, first-click position, zero-results and reformulations online.
- **Quick wins without AI:** a synonyms list owned by the knowledge team (via the Synonyms API, no
  reindex), field boosts (title, client), phrase bonus, freshness decay, document-type priors, and
  spell correction.
- **Query understanding:** extract filters ("pharma", "since 2022", "case studies") and intent (find
  documents, find people, get an answer). Apply low-confidence extractions as *boosts*, not filters. The
  eval in this repo shows hard filters hurting when the parser over-reads a query.
- **Experience:** facets with counts, highlighted passages, a "why this result" explanation, known-item
  shortcuts (client names), "find similar", expert cards, and saved searches.
- **Questions are not keyword queries.** Associates type "How have we helped banks move customers to digital channels?". Drop
  question words at search time (a stop filter in the search analyzer) and retrieve with the extracted
  keywords, while the answer step sees the full question. Otherwise BM25's minimum-should-match counts
  "how/have/we" and returns nothing. This demo hit exactly that bug in keyword mode.
- **Typo-tolerant entity recognition.** "Queenmoor" should still mean Quenmoor Bank. Match names with a
  similarity threshold (longest names first, never on short words), and *show* the correction ("Read
  'queenmoor' as Quenmoor Bank") so users trust it.
- **Zero-result queries are a backlog.** Review them weekly and fix them with synonyms, content or
  metadata.

### e) How AI-powered search improves traditional enterprise search

- **Semantic matching:** finds bank documents when the user types "lender", or omnichannel retail work
  when they type "click and collect for a grocer".
- **Answers, not just links:** RAG summarises across several documents *with citations*, which saves
  associates hours of reading.
- **Natural-language filtering:** "case studies for insurers since 2021" works without touching the UI.
- **Multi-step research (agentic):** "who has done this before, what happened, and which proposal can I
  reuse?" is several searches plus synthesis, done by an agent with tools.
- **Better metadata at ingest:** LLMs can classify, tag, summarise and extract entities, which improves
  plain search too.
- **Honest caveats:** latency, cost, hallucination risk, and the fact that evaluation is harder. Mitigate
  these with grounding, citations, refusal to answer without evidence, caching, and model tiering (a small
  model for routing, a large one for synthesis).

### f) Introducing AI or agentic capabilities into an existing search environment

1. **Don't rip and replace.** Add a `dense_vector` field in a new index version, backfill the embeddings,
   swap the alias, and enable hybrid search behind a feature flag. Then A/B test.
2. **RAG answer box** above the results, only for question-like queries, always cited, with a thumbs
   up/down.
3. **Agent for specific, high-value workflows** such as expert finding, prior case examples and
   proposal research, using **narrow typed tools** over the existing search API rather than "let the LLM
   write ES queries".
4. **Security by construction.** Retrieval is ACL-filtered *before* any text reaches the model. The agent
   acts with the user's identity, and there are audit logs of tool calls.
5. **Guardrails:** bounded steps, validated tool arguments, timeouts, a cost budget per request, PII and
   confidentiality filters, and prompt-injection awareness (document text is data, not instructions).
6. **Evaluation for AI features:** groundedness/faithfulness, citation accuracy, answer relevance and
   task success for agents. Use offline sets plus LLM-as-judge plus human sampling.
7. **Change management:** pilot with one practice, collect feedback, train associates, publish what the
   system can and can't do.

---

### Running it on AWS (this repo deploys with Terraform)

- **Shape:** ALB → ECS Fargate (stateless API, scales on CPU) → Elasticsearch in private subnets.
  Secrets in Secrets Manager, logs in CloudWatch, images in ECR with scan-on-push.
- **Why Elasticsearch on EC2, not Fargate:** it needs `vm.max_map_count` raised on the host and durable,
  fast disk. The demo runs one node with an encrypted EBS volume that's re-attached if the instance is
  replaced. Production would be 3 nodes across AZs (or Elastic Cloud on AWS), with S3 snapshots.
- **The index is derived data:** it can always be rebuilt from source with a one-off Fargate task (the same
  image, a different command). That's the real disaster-recovery path, not the disk.
- **Delivery:** GitHub Actions with **OIDC**, so there are no AWS keys in GitHub. Only `main` of this repo
  can assume the deploy role, and it can only push one ECR repo and update one ECS service. A circuit
  breaker rolls back a bad image automatically.
- **Security defaults:** nothing public except the ALB (IP allow-list in the demo; corporate SSO via ALB
  OIDC auth in production), IMDSv2 only, no SSH (Session Manager), least-privilege roles, and Bedrock
  permissions only when the LLM is switched on.
- **Tested offline:** `terraform test` with a mocked AWS provider checks the security-relevant settings
  in CI without credentials.

## 4. "117k documents: is that big?"

- No. At roughly 1 to 2M chunks and single-digit GB of vectors after quantisation, it fits on a small
  cluster with 1 to 2 primary shards (see [performance.md](performance.md)).
- The likely real issues are these:
  - **Relevance:** vocabulary mismatch, poor boosts, no synonyms.
  - **Chunking and extraction quality:** PDFs and slide decks, tables, scanned documents.
  - **Metadata quality:** missing or inconsistent practice, industry and client tags make facets and
    filters unreliable.
  - **Permissions:** client-confidential documents, keeping ACLs fresh, and never leaking content into an
    LLM prompt.
  - **Freshness:** how quickly new work becomes searchable, and how quickly revoked access is enforced.
  - **Duplicates and versions:** ten versions of the same deck crowding the results. Fix with near-duplicate
    detection and collapse on a document family ID.
  - **Performance:** usually from over-sharding, deep pagination, heavy aggregations, unbounded wildcards
    or missing filter caching, not from document count.

### Client-specific questions ("Where is that hospital? Does it do cardiology?")

An associate staffed on a hospital-system client asks about *their* client. Five things make that work,
and each is a talking point:

1. **The facts must exist as content.** Client profiles and per-facility fact sheets (location, beds,
   emergency level, service lines, cardiology details) sit alongside engagement documents. In a real
   firm these come from client master data (CRM, facility registries) merged at ingest, plus structured
   fields (`facility`, `location`, `service_lines`) that can be filtered and faceted.
2. **Recognise the entity.** "Wrenfield North" means *Wrenfield North Hospital*. Names, including short
   forms, are matched against the clients and facilities *this user can see* and applied as strong
   **boosts**, not hard filters, so "compare Wrenfield to industry benchmarks" still finds firm-wide reports.
3. **Know who is asking.** A staffed associate gets an extra "my clients" retriever in the rank fusion,
   so their client's documents rise when relevant. Unrelated questions are unaffected thanks to the
   similarity floor.
4. **Conversation.** "Is cardiology supported *there*?" is rewritten into a standalone question
   ("... (Wrenfield North Hospital)") before searching. With an LLM this is the standard "condense
   question" step; offline, a rule carries the last-mentioned entity forward.

5. **Don't let the re-ranker undo it.** A cross-encoder only sees question and passage, so it demoted
   "Wrenfield Lakeside" in favour of the hospital with the most cardiology text. When an entity is
   named, its order is blended with the first-stage order (see the strategy table in the README).

Same question, associate not on the team: no results. The access check happens inside Elasticsearch
before anything reaches the answer step.

### Who sees what (the access model in the demo)

Every user is an internal associate; no external clients use the tool. Access differs by **staffing,
not seniority**:

- **Firm-wide knowledge** (industry reports, methodology guides, anonymised case summaries) is visible
  to all staff.
- **Client-restricted work** (engagement documents under NDA) is visible only to associates staffed on
  that client's team. This is also how firms keep "ethical walls" between teams serving competing clients.
- **The knowledge team** curates and tags all content, so it can see everything.

The demo's *Viewing as* dropdown switches between these cases. In production, identity comes from SSO
and the groups come from staffing and engagement data, kept in sync as people roll on and off projects.

## 5. Trade-offs to be ready for

| Question | Short answer |
|---|---|
| BM25 or vectors? | Both. Hybrid with RRF wins in nearly every enterprise eval, including this repo's. |
| Dense vs ELSER (sparse)? | ELSER needs no embedding pipeline and is strong for English, but uses ML nodes and is English-centric. Dense embeddings are multilingual and work across vendors. Evaluate both on the judged set. |
| Native `rrf` retriever or client-side? | Native is simpler and faster when licensed. Client-side is transparent and license-free. Same maths. |
| Re-rank? | Used naively it demoted a named hospital, because the cross-encoder can't see first-stage signals like entity boosts. Blending its order with the first-stage order fixed that; the best setup (hybrid + understanding + re-rank) reaches MRR 1.0. It costs hundreds of ms on CPU. Always measure the re-ranker; don't assume it helps. |
| Chunk size? | 200 to 500 tokens with overlap and a contextual header. Too small loses context; too large blurs embeddings and wastes prompt tokens. Tune it on the eval. |
| Security in RAG? | Filter at retrieval time inside ES. Never post-filter LLM output. The agent uses the user's identity. |
| Hallucinations? | Answer only from retrieved sources, cite every claim, say "not found", and measure groundedness. |
| Agent or pipeline? | Use a pipeline when the steps are known; use an agent when the steps depend on intermediate results. Start narrow. |
| Elastic vs OpenSearch? | They are API-compatible enough. Elastic has ELSER, `semantic_text`, retrievers and the Synonyms API. OpenSearch is AWS-native and managed in-account. Don't migrate engines to get AI features. |
| Cost? | Embeddings are a one-off cost plus incremental updates. LLM cost is per question, so control it with caching, model tiering and showing answers only for question-like queries. |

## 6. Questions to ask them

1. What does "relevance problem" mean today: zero results, wrong top results, or users not trusting the
   results? Do you have query and click logs?
2. Which Elasticsearch version, deployment (Elastic Cloud on AWS or self-managed) and license tier?
   That decides whether ELSER, `semantic_text`, the `rrf` retriever and the re-rankers are available.
3. How are documents ingested today, and what formats dominate (PDF, PowerPoint, Word, scanned)? How good
   is the metadata?
4. How are permissions modelled? Document ACLs from SharePoint or a DMS, client walls, ethical walls? How
   quickly must revocations take effect?
5. Is there a judged query set or any offline evaluation? Who are the relevance owners (a knowledge team)?
6. Which AI features are already being tried or asked for: answer generation, expert finding, proposal
   drafting, summarisation?
7. Which LLM options are approved (Bedrock models, data-residency constraints)?
8. What are the latency targets and query volumes (peak QPS)?
9. How will success be measured for this engagement in the first 90 days?
10. What does the team look like, and who owns the platform after delivery?

## 7. Connecting my background

- **Python / FastAPI:** the search API, the RAG service and the agent tools in this repo are FastAPI services.
- **React:** the production UI (facets, answer panel, agent trace, feedback buttons).
- **GCP → AWS mapping:** Cloud Run ≈ ECS Fargate, Pub/Sub ≈ SNS/SQS/EventBridge, GCS ≈ S3, Vertex AI ≈
  Bedrock, Secret Manager ≈ Secrets Manager. **Terraform** carries over directly (AWS provider plus the
  Elastic `ec` provider).
- **Building a news site (World Post):** content ingestion, freshness, categorisation and search
  relevance are the same problems at a different scale.

## 8. Quick glossary

| Term | Meaning |
|---|---|
| BM25 | Standard keyword relevance: term frequency, rarity and document length |
| Analyzer | Tokeniser plus filters (lowercase, stemming, synonyms) applied to text |
| kNN / HNSW | Approximate nearest-neighbour vector search; HNSW is the graph index behind it |
| RRF | Reciprocal rank fusion: combine ranked lists with `1/(k + rank)` |
| Cross-encoder | A model that scores (query, passage) together; precise but slow, so used to re-rank |
| nDCG@10 | Ranking quality that rewards relevant documents near the top (graded) |
| MRR | 1 / rank of the first relevant result, averaged over queries |
| RAG | Retrieval-augmented generation: an LLM answers from retrieved passages |
| DLS | Document-level security: per-user filtering of which documents are visible |
| ELSER | Elastic's learned sparse encoder (semantic search without dense vectors) |

# Decision log

Running log of design decisions. Each entry: what was decided, what was considered, why the winner won. Newest at the bottom. D1–D7 were made at spec time — their full rationale lives in [requirements.md §4](requirements.md); they are summarized here so this file is the one place to look.

## Spec-time decisions (2026-07-12, summarized)

- **D1 RAG framework — LlamaIndex.** Least glue code for retrieval-focused document Q&A. Rejected: LangChain (more boilerplate, agentic focus), from-scratch (slower).
- **D2 Vector store — Postgres + pgvector (Docker).** Vectors + structured metadata in one store, local, no accounts. Rejected: Chroma (no structured story), Pinecone (managed cloud).
- **D3 Embeddings — OpenAI text-embedding-3-small.** Representative default; the eval A/Bs it against `-large` so the tier choice is measured, not assumed. Rejected: Voyage AI, local BGE.
- **D4 Generation — Anthropic Claude.** High-quality grounded generation, Claude-based stack.
- **D5 Interface — FastAPI `POST /query`.** Thin, typed API. Rejected: CLI-only, notebook.
- **D6 Multimodal — one chart, Claude vision, caption-then-index.** The chart's answer is absent from the text — the clean "why multimodal" case. Rejected: diagram-heavy corpus (sparse text undermines the retrieval core).
- **D7 Eval — golden Q&A + LLM-as-judge + small-vs-large embedding A/B.** Quality claims become measurements.

## D8 — PDF parsing (2026-07-12)

**Decision:** LlamaIndex built-in PDF reader (pypdf-based): one plain-text document per page, page-number metadata preserved. Verify parse quality by eyeballing representative pages — a prose page, the troubleshooting table (pp. 49–51), the icon-matrix maintenance schedule (p. 48), and p. 42 (embedded chart) — and escalate to PyMuPDF only on evidence of bad extraction.

**Considered:**
- *LlamaIndex/pypdf reader* — chosen: one line of code, page metadata free (feeds the answer-plus-sources requirement), plain-text output.
- *PyMuPDF directly* — cleaner extraction with block/font info (enables heading detection), but we'd write and own that extraction logic before knowing it's needed.
- *LlamaParse / unstructured* — best table handling, but a cloud API or heavyweight install; overkill for a clean, text-led 60-page manual.

**Why:** parser quality is document-specific, not a spec-sheet fact — so start with the simplest parser that meets the metadata requirement, verify against the real document, escalate on evidence.

## D9 — Chunking strategy (2026-07-12)

**Decision:** Sentence-aware fixed-size chunking (LlamaIndex `SentenceSplitter`), **512-token chunks, 64-token overlap**, plus two ingest additions: (1) strip the per-page header/footer boilerplate before splitting; (2) section metadata by **tagging** — regex-match the manual's heading formats while walking each page and stamp every chunk with the most recent heading seen (delivers F1's `(page, section)` metadata without risking chunk boundaries).

**Considered:**
- *A: sentence-aware fixed-size* — chosen (with the two additions above).
- *B: structure-aware boundary splitting* — sections are the true semantic units, but the manual uses four inconsistent heading formats plus unnumbered sub-headings, one heading is image-garbled, and digit-led lines (ISO codes, table rows) false-positive. A real parsing sub-project before any baseline number exists. Rejected as the starting point.
- *C: small-to-big / auto-merging* — solves a precision-vs-context tension this corpus doesn't have (sections are already ~200–600 tokens; top-5 × 512 tokens is no context pressure). Rejected.

**Why the numbers:** measured from the manual itself — typical subsections run 200–600 tokens, so 512 whole-swallows ~90% of them and splits a page-length section exactly once; 64 overlap (~12%) is enough to heal a mid-section cut on short sections. The framework default (1024/200) would routinely fuse two or three unrelated sections per chunk on this document — the numbers are decisions, not defaults.

**Named upgrade triggers (measured, from the M2 eval):**
- Troubleshooting golden questions miss at hit@5 → hand-chunk pp. 49–51 one block per problem, re-run, report the delta (structure-awareness applied only to the pages that need it).
- Cross-page-section question misses → stitch page documents before splitting, carry page ranges.
- Right page retrieved but judge flags truncated/ungrounded answers → the one symptom small-to-big treats.

**Known limitation (documented, not hidden):** p. 48's maintenance-schedule matrix uses icon cells; task-to-interval associations cannot survive text extraction under any chunking strategy — it is a parsing/multimodal problem of the same class as the p. 42 viscosity chart, and the golden set includes a question predicted to fail on it.

## D10 — Decision-logging skill design (2026-07-12)

**Decision:** A project-level Claude Code skill (`.claude/skills/decision-logging/`) that appends entries to this file whenever a design decision is confirmed: hybrid triggering (auto via skill description + manual `/decision-logging`), a defensibility threshold (log only when ≥2 viable options were weighed *and* the choice needs defending later), entries in this file's D-format.

**Considered:**
- *Project-level skill* — chosen: versioned with the repo, so the logging convention travels with the project.
- *Personal (user-level) skill* — reusable across all projects, but invisible to this repo; can still be promoted later. Rejected for now.
- *Hook-based automation* — hooks fire on mechanical tool events and cannot detect the semantic event "a decision was confirmed". Technically unfit.
- *Formal ADR files (one per decision)* — industry standard with Status/Context/Consequences, but heavier ceremony than a single concise log warrants at this scale. Rejected.

**Why:** the log stays useful only if writing it is effortless and consistent; a skill makes the threshold and format automatic instead of remembered.

## D11 — Vector search: exact scan + cosine, no ANN index (2026-07-12)

**Decision:** Dense retrieval runs as an exact (sequential) pgvector scan with cosine distance (`vector_cosine_ops`); no HNSW/IVFFlat index. M1 verifies in the database that the vector store created no ANN index behind our back.

**Considered:**
- *Exact scan* — chosen: at ~100–150 chunk vectors a full scan is microseconds with 100% recall by construction, and it keeps ANN recall out of the M2 eval as a confounding variable.
- *HNSW* — the production-standard ANN index with the best recall/latency curve at scale, but at this corpus size its tuning knobs (`m`, `ef_construction`, `ef_search`) are pure overhead. Rejected.
- *IVFFlat* — cheaper to build than HNSW, but worse recall/latency trade and needs training data present at build time. Rejected.

**Why:** ANN indexes exist to trade recall for latency once corpora reach millions of vectors; adding one at 150 vectors solves a problem we don't have and blurs the eval. Cosine because text-embedding-3 vectors are unit-normalized (cosine ≡ dot product in ranking) and cosine is the self-documenting convention.

**Named upgrade trigger:** corpus growth toward ~10M vectors or p95 latency targets under concurrency — then HNSW, accepting its build cost and tuning surface.

## D12 — Keyword pass: in-memory BM25 over the Postgres chunks (2026-07-12)

**Decision:** The sparse half of hybrid retrieval (M3) is an in-memory BM25 index (LlamaIndex `BM25Retriever`), rebuilt at API startup from the chunk nodes loaded **out of Postgres** — never by re-chunking the PDF — so dense and sparse always score byte-identical chunk sets. Postgres remains the single store of record.

**Considered:**
- *In-memory BM25* — chosen: OR-semantics (any shared term earns a score) and IDF weighting (rare identifiers like `EN590` outweigh corpus-wide words like "fuel"); per-term explainable (N1); deterministic across runs (N3).
- *Postgres FTS (tsvector/ts_rank)* — keeps the keyword pass in-database, but `plainto_tsquery` ANDs all query terms, so natural-language questions can silently return zero sparse rows — hybrid degrades to dense-only unnoticed and the M3 delta lies; ts_rank also has no IDF. Rejected.

**Why:** the manual is identifier-dense (fuel standards p. 43, part codes pp. 34–37, numeric limits) — exactly the queries a sparse pass exists for; the FTS AND-trap would corrupt the very measurement M3 is for.

**Named upgrade trigger:** corpus outgrows a startup rebuild (multi-document, continuous ingest) → move sparse in-database (e.g. pg_search/ParadeDB for real BM25 in Postgres).

**Known limitation:** the BM25 index is a derived cache — after re-ingesting, the API process must restart to rebuild it (acceptable: ingest is an offline batch step and already implies a restart).

## D13 — Fusion: Reciprocal Rank Fusion, k=60 (2026-07-12)

**Decision:** Dense and BM25 ranked lists merge via RRF — `score = Σ 1/(60 + rank)` — with everything explicit: fusion mode set by name, `num_queries=1` (no silent LLM query expansion), candidate depth fixed on both retrievers (10 each in, top-5 out) so the eval compares equal context budgets.

**Considered:**
- *RRF* — chosen: rank-based, immune to the incomparable score scales (bunched cosine vs unbounded BM25); zero tunable parameters.
- *Weighted score fusion (α-blend of normalized scores)* — genuinely superior when hundreds of labeled queries exist to fit α on, but tuning α against an 8–10-question golden set is overfitting and contaminates the eval as a measuring instrument. Rejected.

**Why:** with no knob, the M2→M3 delta is attributable to "added BM25 + RRF", full stop, and the golden set stays a clean exam. k=60 is the literature constant (Cormack et al. 2009), empirically insensitive over a wide band — adopted, not tuned.

## D14 — Reranking: listwise, single Claude call (2026-07-13)

**Decision:** The F3 reranker is **listwise**: one Claude call receives the question plus all 10 fused candidates and returns the top-5 chunk IDs in relevance order as JSON. If the response fails to parse, the pipeline falls back to the RRF order — a reranker failure can degrade ranking quality but never break a query. M3 measures hybrid-without-rerank before hybrid-with-rerank so the reranking delta is attributable.

**Considered:**
- *Listwise (one call)* — chosen: candidates are judged against each other, which is the actual task; one API call (~5k tokens for 10×512-token chunks).
- *Pointwise (score each chunk 0–10, sort)* — parallelizable and parse-safe, but scores from separate calls aren't calibrated against each other, which is shaky when the output is an ordering; 10× the calls. Rejected.
- *Pairwise comparisons* — highest accuracy in the literature, O(n²) calls; disproportionate. Rejected.
- *Managed rerank API (Cohere/Voyage hosted cross-encoder)* — production-realistic and cheap, but adds a third provider for a stage the spec keeps on Claude. Rejected.

**Why:** reranking exists because bi-encoder retrieval scores query and chunk vectors that were computed independently ("same topic"), while a reranker reads them together ("actually answers this"); listwise is the judging mode that matches that purpose at the lowest call count, and the RRF fallback caps its blast radius.

**Known limitation:** LLM listwise ranking carries mild positional bias (earlier candidates slightly favored); accepted at this scale rather than mitigated with shuffled multi-pass voting.

## D15 — No-answer behavior: instructed refusal, measured by a trap question; structured citations (2026-07-13)

**Decision:** The generation prompt hard-scopes Claude to the retrieved context: answer only from it, and refuse explicitly when the context doesn't contain the answer. Enforcement is measured, not trusted — the golden set includes a plausible, domain-appropriate **trap question** that is genuinely unanswerable from the manual, and the eval checks that the pipeline refuses it. Citations: the API returns `sources` as a structured array of `{page, section, snippet}` for the chunks that survived reranking (the authoritative, eval-checkable field), and the answer text cites pages inline where natural.

**Considered:**
- *Instructed refusal + trap question* — chosen: puts the judgment where the calibration lives (the LLM can genuinely assess "this context doesn't cover that"), costs no extra call, and becomes a measured property.
- *Retrieval-score gate* — reject early when top scores are low; sounds principled, but D13's RRF scores are rank-based (`1/(60+rank)`) with no absolute meaning to threshold, and calibrating a cosine cutoff on 8–10 questions is the same overfitting trap as tuning fusion weights. Rejected.
- *LLM relevance pre-check* — an extra call judging "can this context answer this?" duplicates a judgment the generator can make in the same breath. Rejected.
- *Inline-only or structured-only citations* — inline-only is unparseable for the eval; structured-only gives the human reader no pointers. Rejected.

**Why:** top-k retrieval always returns k chunks — there is no built-in "nothing relevant" signal — so an ungated pipeline will confidently synthesize answers to questions the corpus never covers; in a field-service setting a confident wrong maintenance instruction is the worst failure mode, so refusal must be a designed, measured behavior.

## D16 — Model tiers: one Claude model per pipeline role (2026-07-13)

**Decision:** Tier matched to task profile — **Sonnet 5** (`claude-sonnet-5`) for answer generation and the F5 vision caption; **Haiku 4.5** (`claude-haiku-4-5`) for the listwise reranker; **Opus 4.8** (`claude-opus-4-8`) for the LLM-as-judge.

**Considered:**
- *Per-role mix* — chosen: generation is constrained synthesis over provided context (Sonnet territory); reranking is a narrow judgment in the latency path on every query (Haiku's profile); the judge should be at least as strong as the system it grades and runs rarely (top tier, cost irrelevant).
- *Sonnet 5 everywhere* — simplest config, but the judge then grades its own model's outputs — the worst case for self-preference bias. Rejected.
- *Opus 4.8 everywhere* — maximal quality, but no per-role reasoning and the slowest model in the reranking latency path. Rejected.

**Why:** at this corpus and query volume the cost difference is cents — the value of the mix is the discipline: each call sized to its task, with an eval-guarded swap trigger. Opus-as-judge over Sonnet-as-generator also avoids a model judging itself (same-vendor bias remains and is stated openly as a limitation of the eval design).

**Named swap trigger:** if M3 shows Haiku reranking with a zero or negative delta, swap the reranker to Sonnet 5 (one string) and re-measure before concluding reranking doesn't help.

## D17 — Eval metrics: hit@5 + MRR@5; judge = two binary axes (2026-07-13)

**Decision:** Retrieval is measured by **hit@5** (a chunk from the pre-frozen expected-page set appears in the final top-5) and **MRR@5** (reciprocal rank of the first such chunk; RR=0 on miss; chunks, not pages, define rank). The judge (Opus 4.8, per D16) outputs **two binary verdicts in two separate calls**: *groundedness* (reference-free: question + retrieved context + answer, golden answer withheld; fails if ANY claim is unsupported) and *correctness* (reference-based: question + golden answer + answer, context withheld) — justification field before verdict field in strict JSON; parse failure fails the run (no fallback in the eval, unlike D14's serving path).

**Considered:**
- *hit@5 + MRR@5* — chosen: hit@5 measures selection (right page in context), MRR@5 measures ordering — the D14 reranker's effect is invisible to hit@5 alone.
- *hit@5 only* — blind to rank movement inside the top-5; cannot show reranking working. Rejected.
- *nDCG / precision@5 / recall@k* — nDCG needs graded labels we don't have; precision@5's ceiling is the context budget, not quality; multi-page recall is a per-question column, not a metric. Rejected.
- *1–5 judge scale* — uncalibrated, ordinal averaging is a category error, indefensible aloud. Rejected.
- *Per-claim decomposition (RAGAS-style)* — right idea at scale, false precision at n≈9; its strictness is kept via the any-unsupported-claim-fails rubric. Upgrade trigger: answers become long procedures.

**Why:** the two binary axes disagree diagnostically — grounded-but-wrong = retrieval failure; ungrounded-but-right = answered from parametric knowledge (the failure D15 exists to catch, invisible to a correctness-only eval). Separate calls prevent the golden answer leaking into the groundedness judgment.

**Measurement rules (frozen with this decision):** trap question excluded from retrieval metrics (own row: refused yes/no); p. 48 question stays in the aggregate annotated "predicted fail — D9"; every measured config delivers exactly 5 chunks (dense@5 / fused@5 / reranked@5, three-column comparison + D3 embedding A/B); expected-page sets and hand-written golden answers frozen before results exist (later fixes go through this log); judge calibrated once by a 3× flip-rate run (0 flips → single-run thereafter, else majority-of-3); retrieved context logged at generation time and judged as-logged; report counts (7/9) never percentages, per-question table primary, instrument disclosure (judge model, prompt version, same-vendor limitation, sensitivity ≈ 11 points/question) in the header.

## D18 — Ingest idempotency: drop and rebuild (2026-07-13)

**Decision:** Every `src.ingest` run starts by deleting all rows in the index, then re-parses, re-chunks, re-embeds, and reloads. The index always exactly reflects the current code.

**Considered:**
- *Drop and rebuild* — chosen: perfectly deterministic (N3), and the property D12's byte-identical-chunk-sets invariant leans on; the "cost" is re-embedding ~150 × 512-token chunks ≈ a fifth of a cent per run.
- *Upsert by deterministic chunk hash* — the real production pattern for large or continuously-ingested corpora, but here it means owning stable-ID and orphan-cleanup logic to save a fraction of a cent. Rejected.
- *Append (no handling)* — the default trap: every re-run duplicates the corpus, retrieval returns copies, eval numbers silently corrupt. Rejected.

**Why:** ingest is re-run after every chunking/parsing tweak; a dirty index masquerades as a retrieval bug and contaminates the eval. Determinism is worth infinitely more than $0.002.

**Named upgrade trigger:** re-embedding starts costing real money (corpus scale) or ingest becomes continuous → upsert by content hash with orphan cleanup.

## D19 — Troubleshooting table (pp. 50–51) is image-only: record now, fix via vision in M5 (2026-07-13)

**Decision:** The PROBLEM/CAUSES/REMEDY troubleshooting table on pp. 50–51 exists only as embedded images (verified: pypdf *and* PyMuPDF both extract ~55 chars of footer, nothing else; ~11 images per page). Proceed with M1 unchanged; the slow-crank golden question becomes a second annotated **predicted-fail** row (alongside p. 48); M5 extends from "caption one chart" to also captioning the pp. 50–51 table images. This supersedes D9's "troubleshooting miss → hand-chunk pp. 49–51" trigger, whose remedy is impossible — there is no text to hand-chunk.

**Considered:**
- *Record now, decide in M5 after the eval demonstrates the miss* — chosen: keeps the measure-first discipline; M2 produces a real number proving the gap before the multimodal fix lands.
- *Widen M5 scope immediately* — same end state, honest about the inevitability, but commits to a fix before the eval has demonstrated the need. Rejected.
- *OCR pass at ingest* — would recover text without vision models, but adds a new dependency and an uncontrolled extraction path for exactly the content M5's captioning already covers better. Rejected.

**Why:** the gap is a corpus fact, not a parser failure — escalation per D8 was tested and gains nothing. Letting the eval confirm the predicted miss first turns a limitation into a measured before/after for the multimodal milestone.

## D20 — Embedding text excludes `page` metadata, keeps `section` (2026-07-14)

**Decision:** LlamaIndex embeds node metadata into the vector text by default — an inherited behavior never consciously chosen. From M2 on, `page` is excluded from the embedded text (`excluded_embed_metadata_keys`); `section` stays in. Decided **before** the first eval baseline so no measurement is invalidated.

**Considered:**
- *Exclude `page`, keep `section`* — chosen: page numbers are pure noise tokens in the vector; section labels ("5.6 Fuel") add genuine topical signal to continuation chunks that inherited a heading they don't contain.
- *Keep both (framework default)* — zero-touch and already smoke-tested, but leaves an unexamined default silently shaping every similarity score. Rejected.
- *Exclude both* — purest "the vector represents the text", but discards the one metadata field with real semantic content, hurting exactly the heading-less continuation chunks. Rejected.

**Why:** the choice had to be made consciously and before results exist (changing it later re-baselines everything); section-in/page-out is the only option where every embedded token plausibly helps retrieval.

**Note for M3:** the BM25 index must tokenize the same content the dense side embeds (D12 byte-identical invariant) — carry this exclusion over.

## D21 — Spanning-chunk section labels list all contained sections; M2 re-baselined (2026-07-14)

**Decision:** A chunk's `section` label = the section running at its start plus every heading inside it, joined `"; "` (e.g. `5.6 Fuel; 5.7 Maintenance of Batteries`). Since D20 embeds the label, vectors change → the M2 baseline was re-ingested and re-run before being blessed.

**Considered:**
- *All contained sections, joined* — chosen: honest for spanning chunks in both citations and embedded text; trivially implementable on top of D9's tagging.
- *Majority heading (by token share)* — a single clean label, but still hides the minority section from citations and requires token accounting. Rejected.
- *Accept as known limitation with audit metric + trigger* — zero re-baseline cost, but the first baseline review measured the artifact at 3 of 8 correct answers carrying a wrong section label (q2/q3/q5), and it demonstrably cost rank on q3 (the D20-embedded wrong label boosted a no-answer continuation chunk over the answer chunk). Rejected.

**Why:** the label is both a citation (F1's `(page, section)` promise) and embedded retrieval signal (D20) — a wrong label is user-visible *and* rank-distorting. Fixing it mid-M3 would invalidate the baseline; fixing before blessing costs one $1 re-run.

## D22 — Degenerate chunks (< 20 chars) dropped at chunking (2026-07-14)

**Decision:** `build_nodes` drops chunks whose stripped text is shorter than 20 characters. Effect: the pp. 50–51 image-only pages (extract as just their footer number, D19) no longer produce index rows; 82 chunks → 80.

**Considered:**
- *Drop at chunking* — chosen: "no content-free chunk enters the index" is a chunking-stage invariant; folded into the D21 re-baseline at zero extra cost.
- *Keep them (measured harmless)* — they never appeared in any top-5, but they pollute the index, can surface as absurd citations, and would receive BM25 scores in M3. Rejected.

**Why:** a 2-character chunk can never ground an answer; removing it is strictly hygiene, and doing it inside the same re-baseline avoids a second vector change later.

## D23 — Baseline record amendments: D12 headroom relocated, M5 delta expectations pre-committed (2026-07-14)

**Decision:** Post-review amendments to the frozen record (annotations only — no question, page set, or golden answer changed): (1) D12's sparse-wins hypothesis is *unconfirmed at n=2* — dense resolved both identifier rows (q10, q11) at rank 1; M3's measurable headroom is ranking depth on q3/q5/q7 (MRR ceiling 0.91 vs measured baseline) plus demoting the TOC-magnet chunk (p. 5, in 4 of 12 top-5s), while hit@5 is immovable before M5 (q8 has no text to retrieve). (2) M5 delta expectations: q8 → hit + correctness; q9 → correctness only (its retrieval is already saturated — p. 42 at rank 1 with the answer in an invisible chart). (3) An M3 null result triggers the D16 Haiku→Sonnet reranker check before any "reranking doesn't help" conclusion.

**Considered:**
- *Pre-commit expectations now* — chosen: written before M3/M5 exist, so a small delta reads as instrument saturation, not failed work — and a large delta can't be retro-fitted a story.
- *Interpret after M3 runs* — flexible, but post-hoc reading of a near-saturated instrument invites motivated reasoning in either direction. Rejected.

**Why:** D17's freeze discipline applies to expectations too: the honest statement of where improvement *can* appear must predate the measurement that shows it.

## D24 — Serving config: the API serves hybrid + rerank, surfaces degradation, 502s on generation failure (2026-07-14)

**Decision:** `POST /query` serves the M3 rerank path (`hybrid_candidates → rerank → answer_from_chunks`), calling `rerank()` directly so D14's fallback surfaces in the response as `rerank_degraded` — explicitly an extension of F6's `{answer, sources}` shape. Upstream model failures and D15 under-delivery (`GenerationIncompleteError`) map to 502 with a generic body (N4); everything else stays a 500.

**Considered:**
- *Serve hybrid + rerank* — chosen: the only measured net-positive config (hit@5 10/11, MRR 0.91); M3 showed hybrid-without-rerank is strictly worse than dense (9/11, 0.69).
- *Serve plain dense* — simpler, one fewer paid call per query, but leaves the measured +0.12 MRR on the table. Rejected.
- *Strict F6 shape (hide the fallback flag)* — smaller response, exactly the spec; but D14's fallback exists to keep queries alive, not to be invisible — hiding it makes the API lie about its own ranking quality. Rejected.

**Why:** serve what was measured best, and never report a degraded response as a full-quality one. Generation gets no graceful degradation by design (D15: no answer beats a wrong answer), so its failures are errors — 502 for "an upstream model didn't deliver", 500 for "our code broke".

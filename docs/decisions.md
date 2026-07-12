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

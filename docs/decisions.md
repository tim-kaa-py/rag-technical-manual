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

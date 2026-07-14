# Code Documentation — M1 Core RAG Spine

_Last updated: 2026-07-14 · reflects milestone M1 + the M2 embedding-A/B seam_

This document maps every file in the codebase and explains what it does and why.
It reflects the **M1** state: the straight-line path from a PDF to a grounded,
sourced answer. Decision IDs (`D9`, `D11`, …) reference [decisions.md](../decisions.md);
that log is the source of truth for the *why* behind each choice.

To set up and run the pipeline, see the Quickstart in the [README](../../README.md#quickstart).

The pipeline has two phases:

- **Ingest** (offline, run once): parse → clean → chunk → embed → store.
- **Query** (per question): retrieve → generate.

```
PDF ─► parse ─► textprep ─► chunking ─► store (pgvector)      [ingest phase]

question ─► retrieve (top-5) ─► generate ─► answer + sources  [query phase]
```

## The pipeline (`src/`)

Listed in execution order.

### `config.py` — single source of constants
Everything tunable lives here, and every constant is tagged with the decision
ID that fixed it (traceable to [decisions.md](../decisions.md)):

- Chunk size / overlap: **512 / 64** (D9)
- `TOP_K = 5` retrieved chunks (D13)
- `EMBED_CONFIGS`: the two embedding tiers the M2 harness A/Bs (D3/D17) —
  `"small"` (`text-embedding-3-small`, 1536-dim, table `teksan_manual`) and
  `"large"` (`text-embedding-3-large`, 3072-dim, table `teksan_manual_large`).
  Separate tables per tier so drop-and-rebuild ingest (D18) of one tier can't
  destroy the other. `DEFAULT_EMBED = "small"`.
- Generation model: `claude-sonnet-5`; judge model: `claude-opus-4-8` (D16)
- PDF path and Postgres connection params

`_check()` is the **M0 smoke test** (`python -m src.config`): confirms Postgres
is reachable, pgvector is installed, both API keys are set, and the corpus file
exists. Nothing is hardcoded elsewhere — change a knob here and the whole
pipeline follows.

### `parse.py` — PDF → clean per-page Documents
Loads the PDF with LlamaIndex's `PDFReader` (pypdf under the hood) and produces
one `Document` per page carrying `{page: "42"}` metadata. Each page's text is
run through `clean_page_text` before storage. The `_inspect()` main lets you
eyeball specific pages (`python -m src.parse 42 43`) — how the boilerplate
patterns below were discovered. (D8)

### `textprep.py` — text hygiene + heading detection
Two jobs, both learned from the actual manual (D9):

- **`clean_page_text`** strips the junk pypdf extracts on every page: the
  "EVERLASTING COMPANY" logo (extracted as four stray lines, twice per page),
  the footer code (`BBK-V.122018_ENG`), "People First", and the leading printed
  page number. That page number matters — left in, it becomes the page's "first
  line" and breaks heading detection downstream.
- **`detect_heading`** recognizes the manual's four heading formats
  (`1.SAFETY`, `2. GENERAL`, `3-INSTALLATION`, `2.2.1 Canopy`) while rejecting
  false positives (table rows like `0,5 - 1,0`, diagram legend items like
  `10 Fuel Feed Pump`, prose that starts with a number).

**Key decision (D9):** headings are used only to *tag* chunks with a section
label, never to decide where chunks split. A missed heading degrades one
citation label at worst — it never breaks a chunk boundary.

### `chunking.py` — Documents → tagged TextNodes
Runs LlamaIndex's `SentenceSplitter` (512/64) to cut pages into chunks, then
walks the chunks in order assigning each a `section` label: the section
running at the chunk's start **plus every heading inside the chunk**, joined
`"; "` (D21) — a chunk spanning a heading belongs to both sections, and
labeling only the first mislabels the content after the heading (a citation
and ranking artifact found in the M2 baseline review). Headings inside a
chunk update the running section for *following* chunks. Text before any
heading is tagged `"unknown"`. Chunks shorter than 20 characters are dropped
(D22 — image-only pages extract as just their footer number). Output:
`TextNode`s each carrying `{page, section}` plus text.

**What gets embedded (D20):** the `section` label is prepended into the text
that gets embedded (a continuation chunk inherits a heading its body doesn't
contain — the label is its only topical signal), while the `page` number is
excluded (`excluded_embed_metadata_keys`) — it's citation metadata, not meaning.

### `store.py` — pgvector access layer
The database seam. Provides the OpenAI embedder, the `PGVectorStore`, and a
`VectorStoreIndex` over it. Every function takes an `embed` tier
(`"small"`/`"large"`, default small) and resolves model/dimension/table from
`EMBED_CONFIGS`; `full_table(embed)` gives the actual Postgres table name.
Raw-SQL helpers share a `_conn()` contextmanager (commit + close under
try/finally). Two deliberate choices baked in:

- **No ANN index (D11):** by omitting `hnsw_kwargs`, Postgres does an exact
  brute-force cosine scan. At ~60 pages that is instant and gives *exact*
  recall, so retrieval quality is never confounded by approximation.
  `verify_store()` actively checks no HNSW/IVFFlat index snuck in.
- **`drop_table()`** supports drop-and-rebuild ingest (D18).
- **`load_nodes()`** rebuilds the chunk nodes *from* Postgres (D12) — the
  sparse BM25 index derives from the store of record, never from re-chunking
  the PDF, so dense and sparse score byte-identical chunk sets. The
  reconstruction mirrors ingest exactly (same metadata, same D20 exclusion);
  a hermetic test pins hash + embed-content equality against `build_nodes`.

### `ingest.py` — the offline pipeline, orchestrated
Ties phase one together: drop table → `load_pages` → `build_nodes` → embed +
load into pgvector. Then it **verifies**: the row count must equal the chunk
count (nothing silently dropped) and no ANN index may exist (D11 held) — both
raise `RuntimeError` (not `assert`, so `python -O` can't strip the guards).
`python -m src.ingest [small|large]` picks the embedding tier. (D8/D9/D18)

### `retrieve.py` — question → top-5 chunks
The query phase begins. Embeds the question and pulls the 5 nearest chunks by
cosine similarity; takes an `embed` tier so the M2 A/B can query either table.
Tiny by design — pure dense retrieval, the M2 baseline config. (D11, D13)

### `hybrid.py` — dense + BM25, fused by RRF (M3)
The sparse arm is an in-memory `BM25Retriever` over the nodes from
`load_nodes()` — it tokenizes EMBED-mode content, so sparse scores exactly
the text dense embedded (D20 invariant). Both arms return 10 candidates
(`CANDIDATE_K`); `QueryFusionRetriever` merges them by Reciprocal Rank
Fusion (k=60, the literature constant — adopted, not tuned) with
`num_queries=1` pinned (the library default of 4 silently expands queries
via an LLM). Fusion dedups by `node.hash` (text + metadata) — which is why
`load_nodes`' exact reconstruction matters. `hybrid_candidates()` returns
the 10 fused candidates (the reranker's input); `arm_results()` exposes
per-arm top-10s for eval instrumentation only. Retrievers are cached per
embed tier for the process lifetime (D12: rebuild at startup). (D12, D13)

### `generate.py` — chunks → grounded, sourced answer
The payoff. Hand-rolls the prompt (rather than using a LlamaIndex query engine)
so *every line the model sees is explainable* (N1). The `SYSTEM_PROMPT` enforces
**D15**: answer only from the provided context, and if it isn't there, reply
with the exact refusal string — no guessing from Claude's own knowledge. Returns
a typed `RagAnswer(answer, sources)` where each `Source` has page/section/snippet.

Two things worth noting:

- **`answer_from_chunks(question, chunks)`** is split out from `answer(question)`
  deliberately — it is the seam where M2 judges the exact context used (D17), and
  M3 inserts rerank/fuse before generation. Likewise **`format_context(chunks)`**
  is split out of `build_prompt` so the M2 judge grades the byte-identical
  context block the generator saw.
- **`_answer_text`** fails *loudly* on a truncated or empty response. Adaptive
  thinking shares the token budget, so a cutoff mid-thinking can leave zero
  answer text — and "empty answer next to confident-looking sources" is exactly
  the failure D15 exists to prevent, so it raises instead of shipping it.

## The tests (`tests/`)

Fast, no-API-key unit tests on the tricky pure logic:

- **`test_textprep.py`** — boilerplate removal and all four heading formats,
  using verbatim line shapes from the real manual, plus false-positive rejections.
- **`test_chunking.py`** — section tagging carries across pages and updates on a
  new heading.
- **`test_generate.py`** — prompt assembly, source truncation, and the
  loud-failure paths (thinking eats the budget → raise; empty text → raise).

Retrieval, ingest, and store have no unit tests — they are thin wrappers over
LlamaIndex/pgvector whose behavior is verified by the assertions inside
`ingest.py` against the live database instead.

## Supporting files

- `docs/decisions.md` — the decision log (D1–D18) the code tags point back to.
- `docs/requirements.md` — the engineering spec / milestones.
- `pyproject.toml` — uv-managed dependencies.
- `api/`, `eval/` — empty (`.gitkeep`) placeholders; those arrive in M2/M4.

## One-sentence summary

`ingest.py` runs *parse → textprep → chunking → store* once to fill pgvector;
then per question, `retrieve.py` pulls the top-5 chunks and `generate.py` turns
them into a grounded answer with sources — with `config.py` holding every knob
and refusal-on-missing-context wired in throughout.

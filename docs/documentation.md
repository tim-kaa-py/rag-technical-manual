# Code Documentation — M1 Core RAG Spine

_Last updated: 2026-07-14 · reflects milestone M1_

This document maps every file in the codebase and explains what it does and why.
It reflects the **M1** state: the straight-line path from a PDF to a grounded,
sourced answer. Decision IDs (`D9`, `D11`, …) reference [decisions.md](decisions.md);
that log is the source of truth for the *why* behind each choice.

## Run it

From a clean checkout to a grounded answer:

```bash
# 1. Install dependencies
uv sync

# 2. Secrets — fill in ANTHROPIC_API_KEY + OPENAI_API_KEY
cp .env.example .env

# 3. Start Postgres + pgvector (needs Docker)
docker run -d --name rag-pg -p 5433:5432 \
  -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag -e POSTGRES_DB=rag \
  pgvector/pgvector:pg17

# 4. Verify the environment (Postgres reachable, keys set, corpus present)
uv run python -m src.config

# 5. Ingest: parse → clean → chunk → embed → load pgvector
uv run python -m src.ingest

# 6. Ask a question
uv run python -m src.generate "Which fuel standard does the generator require?"
```

**Expected output.** Step 5 prints the chunk count, `loaded N rows into pgvector`,
and `D11 verified: no ANN index — exact scan`. Step 6 prints a grounded answer
with inline page citations, followed by a `Sources:` list of page/section
references — or the exact refusal string if the manual doesn't cover the question.

> Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), Docker, and the
> corpus file `data/teksan_generator.pdf` (gitignored — see [README](../README.md#data)).

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
ID that fixed it (traceable to [decisions.md](decisions.md)):

- Chunk size / overlap: **512 / 64** (D9)
- `TOP_K = 5` retrieved chunks (D13)
- Embedding model + dimension: `text-embedding-3-small`, **1536** (D3)
- Generation model: `claude-sonnet-5` (D16)
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
walks the chunks in order assigning each a `section`: the most recent heading
seen at that chunk's *start*. A heading appearing mid-chunk updates the running
section for *following* chunks. Text before any heading is tagged `"unknown"`.
Output: `TextNode`s each carrying `{page, section}` plus text.

### `store.py` — pgvector access layer
The database seam. Provides the OpenAI embedder, the `PGVectorStore`, and a
`VectorStoreIndex` over it. Two deliberate choices baked in:

- **No ANN index (D11):** by omitting `hnsw_kwargs`, Postgres does an exact
  brute-force cosine scan. At ~60 pages that is instant and gives *exact*
  recall, so retrieval quality is never confounded by approximation.
  `verify_store()` actively checks no HNSW/IVFFlat index snuck in.
- **`drop_table()`** supports drop-and-rebuild ingest (D18).

### `ingest.py` — the offline pipeline, orchestrated
Ties phase one together: drop table → `load_pages` → `build_nodes` → embed +
load into pgvector. Then it **verifies**: asserts the row count equals the chunk
count (nothing silently dropped) and asserts no ANN index exists (D11 held).
This is the `python -m src.ingest` command that populates the database. (D8/D9/D18)

### `retrieve.py` — question → top-5 chunks
The query phase begins. Embeds the question and pulls the 5 nearest chunks by
cosine similarity. Tiny by design — currently pure dense retrieval. This is
where hybrid (keyword) search and reranking will slot in later (M3). (D11, D13)

### `generate.py` — chunks → grounded, sourced answer
The payoff. Hand-rolls the prompt (rather than using a LlamaIndex query engine)
so *every line the model sees is explainable* (N1). The `SYSTEM_PROMPT` enforces
**D15**: answer only from the provided context, and if it isn't there, reply
with the exact refusal string — no guessing from Claude's own knowledge. Returns
a typed `RagAnswer(answer, sources)` where each `Source` has page/section/snippet.

Two things worth noting:

- **`answer_from_chunks(question, chunks)`** is split out from `answer(question)`
  deliberately — it is the seam where M2 judges the exact context used (D17), and
  M3 inserts rerank/fuse before generation.
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

# rag-technical-manual

A Python RAG system over a technical service manual: **LlamaIndex + Postgres/pgvector + Claude**, with a **FastAPI** endpoint, an **LLM-as-judge eval harness**, and a single-image **multimodal** extension (Claude vision).

It mirrors the document-heavy field-service problem space (technical manuals, troubleshooting, diagrams) and was built to prepare for and demonstrate fit for an AI Solutions Manager role. See `docs/requirements.md` for the full spec and `CLAUDE.md` for the project guide.

## Quickstart

```bash
# 1. Install deps
uv sync

# (one-time) enable the repo's git hooks — keeps docs/documentation/ in sync
git config core.hooksPath .githooks

# 2. Secrets
cp .env.example .env      # fill in ANTHROPIC_API_KEY (console.anthropic.com) + OPENAI_API_KEY

# 3. Postgres + pgvector (needs Docker)
docker run -d --name rag-pg -p 5433:5432 \
  -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag -e POSTGRES_DB=rag \
  pgvector/pgvector:pg17

# 4. Run (modules built incrementally — see docs/requirements.md milestones)
uv run python -m src.ingest                       # parse, chunk, embed, load pgvector
uv run python -m src.multimodal                   # vision-caption + index image pages (M5; run after ingest)
uv run python -m src.retrieve "Which fuel standard does the generator require?"
uv run python -m src.hybrid "your question"       # fused dense+BM25 candidates (M3)
uv run python -m src.rerank "your question"       # reranked top-5, one Haiku call (M3)
uv run python -m src.generate "Which fuel standard does the generator require?"
uv run uvicorn api.main:app --reload              # POST /query -> answer + sources
uv run python -m eval.run --mode rerank --embed small  # golden Q&A -> metrics report
uv run python -m eval.run --compare A.json B.json       # config A/B side-by-side
```

## Serving the API

```bash
uv run uvicorn api.main:app --reload   # http://127.0.0.1:8000
```

Send a test query:

```bash
curl -s -X POST http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "your question here"}' | python3 -m json.tool
```

Or use the interactive Swagger UI at `http://127.0.0.1:8000/docs`.

## Data

The corpus is **not** committed (copyrighted manuals / local assets, gitignored):

- `data/teksan_generator.pdf` — Teksan diesel-generator O&M manual (text-led core). Public download: teksan.com.
- `data/oil_viscosity_chart.png` — one SAE-grade-vs-temperature figure (the multimodal example).

## Stack rationale

Summarised in `CLAUDE.md`; running decision log with alternatives in `docs/decisions.md` (spec-time decisions in `docs/requirements.md` §4).

## Documentation

Engineering docs live under `docs/documentation/`, one per code area:

- `docs/documentation/src.md` — the RAG pipeline (ingest → query), file by file. **Present.**
- `docs/documentation/eval.md` — the evaluation harness: methodology, metrics, how to read the numbers. **Present.**
- `docs/documentation/api.md` — the FastAPI service: endpoint contract, request/response, errors. **Present.**

A pre-commit hook (`.githooks/pre-commit`) blocks a commit that changes `src/`, `eval/`, or `api/` without updating that area's doc. Enable it once per clone with `git config core.hooksPath .githooks`.

- `docs/decisions.md` — running decision log (D1–D24) that the code references by ID.
- `docs/requirements.md` — engineering spec and milestones.

# rag-technical-manual

A Python RAG system over a technical service manual: **LlamaIndex + Postgres/pgvector + Claude**, with a **FastAPI** endpoint, an **LLM-as-judge eval harness**, and a single-image **multimodal** extension (Claude vision).

It mirrors the document-heavy field-service problem space (technical manuals, troubleshooting, diagrams) and was built to prepare for and demonstrate fit for an AI Solutions Manager role. See `docs/requirements.md` for the full spec and `CLAUDE.md` for the project guide.

## Quickstart

```bash
# 1. Install deps
uv sync

# 2. Secrets
cp .env.example .env      # fill in ANTHROPIC_API_KEY (console.anthropic.com) + OPENAI_API_KEY

# 3. Postgres + pgvector (needs Docker)
docker run -d --name rag-pg -p 5433:5432 \
  -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag -e POSTGRES_DB=rag \
  pgvector/pgvector:pg17

# 4. Run (modules built incrementally — see docs/requirements.md milestones)
uv run python -m src.ingest                       # parse, chunk, embed, load pgvector
uv run python -m src.retrieve "Which fuel standard does the generator require?"
uv run python -m src.generate "Which fuel standard does the generator require?"
uv run uvicorn api.main:app --reload              # M4
uv run python -m eval.run                         # M2
```

## Data

The corpus is **not** committed (copyrighted manuals / local assets, gitignored):

- `data/teksan_generator.pdf` — Teksan diesel-generator O&M manual (text-led core). Public download: teksan.com.
- `data/oil_viscosity_chart.png` — one SAE-grade-vs-temperature figure (the multimodal example).

## Stack rationale

Summarised in `CLAUDE.md`; running decision log with alternatives in `docs/decisions.md` (spec-time decisions in `docs/requirements.md` §4).

## Documentation

- `docs/documentation.md` — engineering documentation: what every file does and why, following the ingest → query pipeline.
- `docs/decisions.md` — running decision log (D1–D18) that the code references by ID.
- `docs/requirements.md` — engineering spec and milestones.

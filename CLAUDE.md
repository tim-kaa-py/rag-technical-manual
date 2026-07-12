# rag-technical-manual — Project Guide

An end-to-end Retrieval-Augmented Generation system over a real technical service manual, built in Python. It answers field-service questions from the manual with grounded, sourced responses, exposes the pipeline over an API, measures its own quality with an evaluation harness, and extends to a multimodal case where the answer lives in a diagram.

The project mirrors the document-heavy field-service problem space (complex technical manuals, troubleshooting, diagrams) and was built to prepare for and demonstrate fit for an **AI Solutions Manager** role at Octonomy.

## Project context

The detailed project context and rationale are kept in `docs/context.private.md`. That file is **gitignored** because it contains private notes and is not part of the published repository.

## What it does

- Ingests a technical PDF manual, chunks and embeds it, and stores it in a vector database.
- Retrieves relevant passages (dense vector search, plus a keyword pass for hybrid retrieval) and reranks them.
- Generates grounded answers with Claude, returning the **sources** (page/section) behind each answer.
- Extends to **multimodal**: captions a technical chart with a vision model so questions whose answer is only in the graphic become answerable.
- Serves the pipeline as a **FastAPI** endpoint.
- **Evaluates** itself: a golden Q&A set scored for retrieval quality and answer groundedness via an LLM-as-judge, including an A/B across embedding tiers.

## Stack

| Layer | Choice | Rationale |
| --- | --- | --- |
| RAG framework | **LlamaIndex** | The standard for retrieval-focused document Q&A: built-in chunking, retrieval, and evaluation with minimal glue code. LangGraph would be added only for agentic orchestration, which this project does not need. |
| Vector store | **Postgres + pgvector** (Docker) | Keeps vectors **and** structured metadata in one store, matching how real enterprise data lives. Comfortable to the low tens of millions of vectors; a dedicated engine (Qdrant/Milvus) becomes worthwhile only past that or at sub-10ms p95 under high concurrency. |
| Embeddings | **OpenAI text-embedding-3-small** | Strong, representative default; storage/cost negligible at this corpus size. The eval harness A/Bs it against `-large` to check whether the tier matters here. Voyage AI (Anthropic-recommended) is a viable alternative. |
| Generation | **Anthropic Claude** | High-quality grounded generation; aligns with a Claude-based stack. |
| Multimodal | **Claude vision** on one chart | The chart's answer is not in the surrounding text, so it is the clean demonstration of why multimodal retrieval is needed; a single controlled image keeps the scope tight. |
| Interface | **FastAPI** `POST /query` | A thin, well-typed API over the pipeline: request a question, return an answer plus sources. |
| Eval | **LLM-as-judge harness** | Golden Q&A scored for retrieval quality (expected source pages) and answer groundedness. |

## Corpus

- `data/teksan_generator.pdf` — Teksan diesel-generator Operation & Maintenance manual (~60 pages, text-led). The text-retrieval core.
- `data/oil_viscosity_chart.png` — one figure (SAE oil grade vs ambient temperature). The multimodal example.
- Both are **gitignored** (third-party manuals / local assets — not redistributed).

## Architecture

```
PDF ─► ingest (parse + chunk) ─► embed ─► pgvector
                                            │
chart.png ─► vision caption ─► embed ───────┘   (indexed alongside text)

query ─► retrieve (vector [+ keyword hybrid]) ─► rerank ─► assemble ─► Claude ─► answer + sources
                                                                                     ▲
                                                            FastAPI POST /query ─────┘

eval/  golden Q&A ─► run pipeline ─► retrieval metrics + LLM-as-judge groundedness
```

## Directory layout

```
rag-technical-manual/
├── CLAUDE.md                  ← this file
├── README.md                 ← quickstart (setup, docker, run)
├── docs/
│   ├── requirements.md       ← the engineering spec (functional + non-functional + decisions + scope)
│   └── context.private.md    ← private project context (gitignored)
├── pyproject.toml            ← uv-managed deps
├── .env.example              ← key/DB template (copy to .env; .env is gitignored)
├── data/                     ← corpus + multimodal asset (gitignored)
├── src/                      ← pipeline modules (ingest, embed, store, retrieve, generate, multimodal)
├── api/                      ← FastAPI app (POST /query)
└── eval/                     ← golden Q&A set + LLM-as-judge harness + embedding A/B
```

## Commands

```bash
# Env
uv sync                                   # install deps
cp .env.example .env                      # then fill in ANTHROPIC_API_KEY + OPENAI_API_KEY

# Postgres + pgvector (Docker)
docker run -d --name rag-pg -p 5433:5432 \
  -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag -e POSTGRES_DB=rag \
  pgvector/pgvector:pg17

# Pipeline (built incrementally — see docs/requirements.md milestones)
uv run python -m src.ingest               # parse, chunk, embed, load pgvector
uv run python -m src.multimodal           # caption the chart, index it
uv run uvicorn api.main:app --reload      # serve POST /query
uv run python -m eval.run                 # golden Q&A → metrics
```

## Conventions

- **Python 3.12, `uv` for everything** (no bare pip). Lint with `ruff`.
- **Config via `.env`** (python-dotenv). Never hardcode keys; never commit `.env` or `data/` files.
- **Small, readable modules** — one responsibility each, clear over clever, so every stage of the pipeline is easy to follow.
- **Every quality claim is measured** — the eval harness produces the numbers; nothing is asserted without it.
- **Scope discipline** — anything beyond `docs/requirements.md` is out of scope; check there before adding.

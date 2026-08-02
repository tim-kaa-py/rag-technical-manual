# rag-technical-manual

A Python RAG system over a real diesel-generator service manual: **LlamaIndex + Postgres/pgvector + Claude**, with hybrid retrieval, LLM reranking, a **FastAPI** endpoint, an **LLM-as-judge eval harness**, and a **multimodal extension** that vision-captions the pages whose answers live only in charts and tables.

It mirrors the document-heavy field-service problem: a technician asks a question, and the system must answer **from the manual, with page/section sources** — or explicitly refuse, because a confident wrong maintenance instruction is the worst possible failure. Every quality claim below is measured, not asserted; the build's rule was *no claim without a number*.

## Results

Measured on a frozen 12-question golden set (11 scored + 1 hallucination trap) with a calibrated LLM judge — full methodology in [docs/documentation/eval.md](docs/documentation/eval.md), reports in [eval/results/](eval/results/):

| config | hit@5 | MRR@5 | grounded | correct | the lesson |
|---|---|---|---|---|---|
| dense retrieval (baseline) | 10/11 | 0.79 | 11/11 | 8/11 | a clean baseline before any optimization |
| + BM25 hybrid (RRF fusion) | 9/11 | **0.69** | 10/11 | 8/11 | **fusion alone made it worse** — sparse dilution demoted a rank-1 answer to rank 6 |
| + listwise LLM rerank | 10/11 | 0.91 | 10/11 | 8/11 | one Haiku call repaired everything fusion broke |
| + vision captions (multimodal) | **11/11** | **1.00** | **11/11** | **11/11** | the last three failures were **corpus gaps, not pipeline gaps** — the answers lived in images |

The two headline reports: [hybrid & rerank analysis](eval/results/2026-07-14-rerank-small.md) (including the mechanism of why fusion hurt) and [the multimodal run](eval/results/2026-07-17-rerank-small-mm.md) (including why the perfect score must be read with its disclosures: pre-verified captions, one generation sample, saturated instrument). The full story is in **[docs/learnings.md](docs/learnings.md)**.

## What a query looks like

```
POST /query  {"question": "Which SAE oil grade should be used at an ambient temperature of -30°C?"}
```

```jsonc
{
  "answer": "Based on the viscosity chart, **SAE 5W/30** is the only grade rated for -30°C — its lower bound extends off the chart past -30°C (marked with \"*\"), with an upper bound of +20°C (p. 42).",
  "sources": [
    { "page": "42", "section": "5.4 Lubrication Oil", "snippet": "…SAE 15W/40: Lower bound -15°C…" }
    // + 4 more sources
  ],
  "rerank_degraded": false   // true would mean: reranker failed, RRF order served (degradation is surfaced, never hidden)
}
```

The answer to this question exists **only in a chart image** — no text extraction can see it. It is answerable because the multimodal step captioned the chart into indexed text (and the golden set measured the before/after).

## Architecture

```
PDF ─► ingest (parse + chunk) ─► embed ─► pgvector
                                            │
page images ─► vision captions ─► embed ────┘   (indexed alongside text)

query ─► retrieve (dense + BM25 hybrid) ─► rerank ─► assemble ─► Claude ─► answer + sources
                                                                                ▲
                                                       FastAPI POST /query ────┘

eval/  golden Q&A ─► run pipeline ─► retrieval metrics + LLM-as-judge groundedness/correctness
```

## Quickstart

```bash
# 1. Install deps (uv) + enable the repo's git hooks
uv sync
git config core.hooksPath .githooks

# 2. Secrets
cp .env.example .env      # fill in ANTHROPIC_API_KEY + OPENAI_API_KEY

# 3. Postgres + pgvector (needs Docker)
docker run -d --name rag-pg -p 5433:5432 \
  -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag -e POSTGRES_DB=rag \
  pgvector/pgvector:pg17

# 4. Run the pipeline
uv run python -m src.ingest                       # parse, chunk, embed, load pgvector
uv run python -m src.multimodal                   # vision-caption + index image pages (run after ingest)
uv run uvicorn api.main:app --reload              # POST /query -> answer + sources (Swagger at /docs)
uv run python -m eval.run --mode rerank --embed small   # golden Q&A -> metrics report
uv run python -m eval.run --compare A.json B.json       # config A/B side-by-side
```

Individual stages are runnable too (`src.retrieve`, `src.hybrid`, `src.rerank`, `src.generate` — each takes a question as argv).

## Data

The corpus is **not** committed (copyrighted manual / local assets, gitignored):

- `data/teksan_generator.pdf` — Teksan diesel-generator O&M manual (~60 pages, text-led). Public download: teksan.com.
- `data/oil_viscosity_chart.png` — the SAE-grade-vs-temperature figure (the multimodal example).

Everything derived from the manual (vision captions, raw eval run logs containing chunk text) is gitignored for the same reason; the committed eval reports carry numbers and analysis, never manual text.

## How it was built, and why each choice

- **[docs/learnings.md](docs/learnings.md)** — the build story: what was measured at each step, what broke, and what that taught.
- **[docs/decisions.md](docs/decisions.md)** — running decision log (**D1–D27**): every design decision with the rejected alternatives and named upgrade triggers (e.g. "HNSW only toward ~10M vectors"). The code references these IDs in comments.
- **[docs/requirements.md](docs/requirements.md)** — the engineering spec the build followed (agreed before any code).
- **[docs/documentation/](docs/documentation/)** — per-area engineering docs (`src`, `eval`, `api`), kept in sync by a pre-commit hook (`.githooks/pre-commit`).

The project was built with a plan-first, review-gated AI workflow: implementation plans are versioned in [docs/superpowers/plans/](docs/superpowers/plans/), and designs/results were reviewed by specialized AI reviewer personas ([.claude/agents/](.claude/agents/)) before each milestone was accepted — the same measure-first discipline the eval enforces on the pipeline.

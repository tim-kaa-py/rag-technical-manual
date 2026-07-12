# Requirements — rag-technical-manual

Status: agreed (2026-07-12). This is the spec the build follows. Design decisions carry their rationale.

## 1. Goal

Build an end-to-end Python RAG system over a real technical service manual: reliable text retrieval with grounded, sourced answers, served over an API, measured by an evaluation harness, and extended to a multimodal case where the answer is only in a diagram. The system mirrors the document-heavy field-service problem space (technical manuals, troubleshooting, diagrams).

**Primary success criterion:** the core retrieval works well and is demonstrated with measured results (not asserted), and every architecture decision is deliberate and explainable.

## 2. Functional requirements

- **F1 Ingestion.** Parse `data/teksan_generator.pdf` (text-led generator O&M manual), chunk it, embed the chunks, and load them into pgvector with metadata (page, section).
- **F2 Retrieval.** Given a question, retrieve the most relevant chunks. Start with dense vector search; add a keyword/BM25 pass for **hybrid** retrieval.
- **F3 Reranking.** Rerank retrieved candidates before generation (LLM-based reranker via Claude, avoiding heavy local model dependencies).
- **F4 Generation.** Assemble retrieved context into a grounded prompt and answer via Claude, returning the answer **plus its sources** (page/section).
- **F5 Multimodal extension.** Caption `data/oil_viscosity_chart.png` with Claude vision into structured text (the SAE-grade-vs-temperature mapping), embed and index it alongside the text chunks, so a question whose answer is only in the chart (e.g. "which oil grade at -20 C?") is answerable.
- **F6 API.** Expose the pipeline as a FastAPI `POST /query` endpoint: request `{question}` -> response `{answer, sources}`. Input validation and error handling.
- **F7 Evaluation.** A golden Q&A set (~8-10 pairs grounded in the manual) run through the pipeline, reporting retrieval quality (hit/recall over expected source pages) and answer groundedness via an LLM-as-judge, plus an A/B across embedding tiers.

## 3. Non-functional requirements

- **N1 Explainability over cleverness.** Every stage is readable; no relied-upon abstraction that can't be explained.
- **N2 Reliability of the core.** Text retrieval must work well before any extension is added — this drove the corpus choice.
- **N3 Reproducibility.** `uv sync` + the documented `docker run` + `.env` reproduces the environment. No hidden global state.
- **N4 Secrets hygiene.** Keys only in `.env` (gitignored). Corpus/assets gitignored (third-party material). No secrets in code, logs, or URLs.
- **N5 Time-box.** Core (F1-F4, F6-F7) first; F5 multimodal is the next increment; anything else is out of scope.

## 4. Design decisions (with rationale)

Decisions made after this spec was agreed are recorded in [decisions.md](decisions.md) (D8 onward); D1–D7 below remain authoritative here.

| # | Decision | Chosen | Why | Alternatives considered |
| --- | --- | --- | --- | --- |
| D1 | RAG framework | **LlamaIndex** | Retrieval-focused document Q&A standard; least glue code; built-in eval. | LangChain (larger ecosystem, more boilerplate; stronger for agentic); a from-scratch pipeline (max control, slower). |
| D2 | Vector store | **Postgres + pgvector** (Docker) | Vector + structured in one store; local, no external accounts; strong default under ~10M vectors. | Chroma (zero-infra but no native structured story); Pinecone (managed cloud + external account). |
| D3 | Embeddings | **OpenAI text-embedding-3-small** | Representative default; cost negligible here. A/B against `-large` (D7) checks if the tier matters. | `-large` (marginal gain, measured); Voyage AI (Anthropic-recommended); BGE local (free/offline, more setup). |
| D4 | Generation | **Anthropic Claude** | High-quality grounded generation; aligns with a Claude-based stack. | GPT models. |
| D5 | Interface | **FastAPI `POST /query`** | A thin, well-typed API over the pipeline for ~1h effort. | CLI-only (leaner); notebook (good narration, weak engineering signal). |
| D6 | Multimodal | **One chart via Claude vision**, caption-then-index | The chart's answer is not in the text, so it is the clean "why multimodal" case; one controlled image keeps scope tight. | Parsing a diagram-heavy corpus (rejected: sparse text undermines reliable text retrieval). |
| D7 | Eval design | **Golden Q&A + LLM-as-judge**, with a small-vs-large embedding **A/B** | Turns quality (and the embedding choice) into measured results rather than opinion. | No eval (rejected — measurement is the point). |

## 5. Corpus

- **Text core:** `data/teksan_generator.pdf` — Teksan diesel-generator O&M manual, ~60 pages, A4, text-led, clean structure (maintenance by component + a troubleshooting section). Chosen over a 326-page manual (too heavy to iterate) and a diagram-heavy heat-pump manual (sparse text -> unreliable text retrieval).
- **Multimodal example:** `data/oil_viscosity_chart.png` — SAE oil grade vs ambient temperature (C/F). One figure; the answer is not in the surrounding text.

## 6. Scope boundary

**In:** single-document text RAG; hybrid retrieval; LLM reranking; grounded generation with sources; one FastAPI endpoint; LLM-as-judge eval with a small-vs-large A/B; one multimodal chart.

**Out (do not build without revisiting this doc):** authentication, deployment/hosting, a UI/frontend, multi-document corpora, agentic/multi-step orchestration, streaming responses, conversation memory, fine-tuning, GraphRAG.

## 7. Build sequence (milestones)

1. **M0 Env:** `uv sync`, Docker pgvector up, `.env` filled, connectivity smoke test.
2. **M1 Core RAG:** ingest -> embed -> pgvector -> dense retrieve -> generate with sources (the reliable spine).
3. **M2 Eval:** golden Q&A + LLM-as-judge + the small-vs-large A/B (prove the core works, with numbers).
4. **M3 Quality:** add hybrid retrieval + LLM reranking; re-run eval to show the delta.
5. **M4 API:** FastAPI `POST /query` over the pipeline.
6. **M5 Multimodal:** caption the chart, index it, show the text-only-vs-multimodal comparison.

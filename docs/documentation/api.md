# API Documentation — `POST /query`

_Last updated: 2026-07-14 · reflects milestone M4_

The FastAPI serving layer: one endpoint over the measured-best pipeline
(hybrid retrieval + listwise rerank — the M3 config that scored hit@5 10/11,
MRR 0.91 on the golden set). No auth, no streaming, no extra endpoints
(spec §6 boundary).

## The contract

### `POST /query`

**Request**

| Field | Type | Constraints |
| --- | --- | --- |
| `question` | `string` | 1–2000 characters **after stripping** surrounding whitespace |

The strip runs before the length constraints (pydantic `mode="before"`
validator): a legitimate 2000-character question padded with whitespace is
accepted; a whitespace-only question strips to empty and is rejected.

**Response (200)**

| Field | Type | Meaning |
| --- | --- | --- |
| `answer` | `string` | Grounded answer with inline page citations (D15: context-only; explicit refusal when the manual doesn't cover it) |
| `sources` | `list` of `{page, section, snippet}` | The chunks that survived reranking — what the answer was generated from |
| `rerank_degraded` | `bool` | `true` → the reranker failed (API error or unparseable response) and the RRF fusion order was served instead (D14). The answer is still grounded, but ranking quality is the fused order, not the reranked one. |

`rerank_degraded` extends the spec's F6 `{answer, sources}` shape
deliberately: D14's fallback exists to keep queries alive, not to be
invisible — an API that hides its own degradation lies about its quality.

**Status behavior**

| Status | When | Body |
| --- | --- | --- |
| `200` | Pipeline succeeded (possibly with rerank degradation — see the flag) | `QueryResponse` above |
| `422` | Validation failed: empty/whitespace-only/overlong question, missing field | FastAPI's standard validation detail |
| `502` | **An upstream model failed or under-delivered**: OpenAI embedding call, Anthropic generation call, or the D15 truncation/empty-answer guard (`GenerationIncompleteError`) | `{"detail": "upstream model failure"}` — generic by design (N4: details go to server logs, never to clients) |
| `500` | **Our failure** — e.g. Postgres down mid-serving, a bug in the pipeline | FastAPI's generic internal-error body |

The 502/500 split is the honesty boundary: 502 means "a model we depend on
didn't deliver", 500 means "our code or infrastructure broke". Generation has
no graceful degradation by design — no answer beats a wrong answer (D15) —
so its failures are errors, while the reranker's failures degrade (D14).

## Running locally

```bash
uv run uvicorn api.main:app --reload
```

Startup warms the retriever caches (`warm()` — D12: the BM25 index is a
derived cache rebuilt at process start), so the first query doesn't pay
index-build latency. Note that `--reload` restarts the process on every code
change, and each restart repays the BM25 build — expected behavior, not a hang.

Requires the Docker Postgres (`rag-pg`, port 5433) up and an ingested corpus;
each query makes two paid calls (Haiku rerank + Sonnet generation).

## Per-file notes

- **`api/main.py`** — the entire layer: pydantic request/response models,
  the lifespan warm-up hook, and the endpoint. It calls `rerank()` directly
  (never `rerank_retrieve()`, which discards the fallback flag) so D14
  degradation stays observable. Serves the rerank config because M3 measured
  hybrid-without-rerank as strictly worse than plain dense (hit@5 9/11,
  MRR 0.69 vs 10/11, 0.79) — the reranker is what makes hybrid net-positive
  (10/11, 0.91).

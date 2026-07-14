# M3 Hybrid Retrieval + Reranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Revision note (2026-07-14):** revised per elena/ingrid/yuki panel review. Key corrections: RRF dedup is by `node.hash` (text+metadata), NOT `node_id` — verification now checks content identity; reranker falls back on API errors too; `rerank()` lost its footgun `k` parameter; rerank prompt shows section only (page dropped — D20 rationale, user decision); per-arm instrumentation added so the sparse-wins story is demonstrable; `rerank_model` recorded in every run artifact; mechanical D16 swap predicate + anchoring diagnostic pre-registered.

**Goal:** Add BM25 + RRF hybrid retrieval and a listwise Haiku reranker, and measure both deltas against the blessed M2 dense-small baseline (hit@5 10/11 · MRR@5 0.79) with the frozen exam and calibrated judge.

**Architecture:** `src/hybrid.py` fuses the existing dense retriever with an in-memory BM25 index rebuilt from the Postgres chunks (never by re-chunking) via `QueryFusionRetriever` RRF; `src/rerank.py` reorders the 10 fused candidates in one Haiku call with RRF-order fallback. The eval gains a retrieval-mode registry (`dense`/`hybrid`/`rerank`) so each config is a first-class, comparable run. Measurement order is fixed: hybrid *before* rerank, so each delta is attributable.

**Tech Stack:** llama-index-retrievers-bm25 (bm25s), `QueryFusionRetriever` (llama-index core), anthropic SDK (`claude-haiku-4-5` reranker), existing eval harness.

## Global Constraints

- **D12:** BM25 nodes are loaded **out of Postgres** — never by re-chunking the PDF — so dense and sparse score byte-identical chunk sets. In-memory index; Postgres stays the store of record.
- **D13:** Fusion = RRF (`mode="reciprocal_rerank"`, library constant k=60 — adopted, not tuned); `num_queries=1` (no silent LLM query expansion); candidate depth **10 per retriever in, top-5 out**; no tuned fusion weights (verified: `retriever_weights` are unused in RRF mode).
- **D14:** Reranker is **listwise**: one call, all 10 candidates, returns the **top-5 candidate numbers** as strict JSON. Parse failure **or transport/API failure** → fall back to RRF order (serving path degrades gracefully — contrast the D17 judge, which fails loudly). No retry.
- **D16:** Reranker model `claude-haiku-4-5`. Swap trigger is the **mechanical predicate in Task 4 Step 5** — pre-registered, not judged mid-measurement.
- **D17:** As-logged judging; counts, never percentages; single-run judging (calibrated 2026-07-14: 0/23 flips — judge unchanged, no recalibration; transfer to M3 outputs is an assumption, disclosed and spot-checked per Task 4 Step 7).
- **D20/D12 invariant:** `BM25Retriever` tokenizes `node.get_content(metadata_mode=MetadataMode.EMBED)` (verified in installed source, bm25/base.py:105) — loaded nodes must reproduce ingest-time nodes' EMBED content byte-for-byte.
- **D23 (pre-committed headroom, written before these runs):** M3's measurable target is MRR on q5/q7 + demoting the TOC-magnet chunk (p. 5); hit@5 immovable (10/11; q8 has no text); q10/q11 already rank 1 — no delta expected there. **TOC pre-commitment:** BM25's OR-semantics may *promote* the TOC (it is a term-dense bag of section titles); acceptance = the rerank config's top-5 TOC count ≤ dense's (4/12 rows).
- **Verified library facts:** RRF fusion **dedups by `node.hash` = sha256(text + metadata)** (fusion_retriever.py:131, schema.py) — node ids are never consulted by fusion; we use ids only to *pair* nodes for verification. `QueryFusionRetriever.__init__` resolves `Settings.llm` when `llm` is omitted → always pass `llm=MockLLM()` (never invoked at `num_queries=1`). `num_queries` defaults to 4 → must be set to 1 explicitly. Equal-rank ties across arms break deterministically toward the first retriever in the list (dense) — deterministic, mildly dense-favoring, acceptable. `BM25Retriever` always returns exactly k results, **padding with zero-score chunks** when fewer match — see the pre-registered trigger in Task 4 Step 4.
- Never pass `temperature`/`top_p`/`top_k` to Claude calls; omit `thinking`.
- **Never commit:** `.env`, `data/`, `docs/*.private.md`, `eval/results/*.json` (raw logs contain manual text). `.md` reports ARE committed.
- Unit tests make **no paid API calls and need no database**.
- Pre-commit hook: commits touching `src/` need `docs/documentation/src.md` staged; `eval/` needs `docs/documentation/eval.md`. Stage **selectively**; never `git add -A`.
- uv for everything; ruff clean; commit+push after each task. **Hybrid/rerank runs** log the 10-deep candidate list with `node_id` + score, plus per-arm top-10 pages (D23 instrumentation; dense mode logs `candidates: None`).

---

### Task 1: Nodes-from-Postgres loader + hybrid retrieval (D12/D13)

**Files:**
- Modify: `src/config.py` (add `CANDIDATE_K`)
- Modify: `src/store.py` (add `load_nodes`)
- Create: `src/hybrid.py`
- Test: `tests/test_hybrid.py`
- Modify: `docs/documentation/src.md` (hook), `pyproject.toml`/`uv.lock` (dep `llama-index-retrievers-bm25` — already added during plan research; commit it here)

**Interfaces:**
- Consumes: `store.get_index(embed)`, `store._conn()`, `store.full_table(embed)`, `config.DEFAULT_EMBED`, `chunking.build_nodes` (test only).
- Produces: `config.CANDIDATE_K = 10`; `store.load_nodes(embed: str = DEFAULT_EMBED) -> list[TextNode]`; `hybrid.hybrid_candidates(question: str, embed: str = DEFAULT_EMBED) -> list[NodeWithScore]` (10 fused, RRF order); `hybrid.arm_results(question: str, embed: str = DEFAULT_EMBED) -> dict[str, list[NodeWithScore]]` (keys `"dense"`/`"sparse"`, 10 each — eval instrumentation). Tasks 2/3 consume.

- [ ] **Step 1: Add the candidate-depth constant to `src/config.py`** (below `TOP_K`):

```python
# D13 — fusion candidate depth: 10 per retriever in, TOP_K out
CANDIDATE_K = 10
```

- [ ] **Step 2: Write the failing library-contract test** in `tests/test_hybrid.py`. This pins the two `QueryFusionRetriever` behaviors we lean on — dedup by **node hash** (text+metadata) and doubly-retrieved-wins RRF — with stub retrievers, no DB, no API:

```python
from llama_index.core.llms.mock import MockLLM
from llama_index.core.retrievers import BaseRetriever, QueryFusionRetriever
from llama_index.core.schema import MetadataMode, NodeWithScore, TextNode

from src.chunking import build_nodes


class _StubRetriever(BaseRetriever):
    def __init__(self, results):
        self._results = results
        super().__init__()

    def _retrieve(self, query_bundle):
        return self._results


def _nws(node_id: str, score: float) -> NodeWithScore:
    # fusion dedups by node.hash = sha256(text + metadata); same id + same
    # text/metadata -> same hash, which is what makes these two "B"s merge
    return NodeWithScore(node=TextNode(id_=node_id, text=f"text {node_id}"), score=score)


def test_rrf_fusion_dedups_by_content_hash_and_prefers_doubly_retrieved():
    # dense arm: A then B; sparse arm: B then C (scores on incomparable scales
    # — exactly why D13 fuses by rank, not score)
    dense = _StubRetriever([_nws("A", 0.9), _nws("B", 0.8)])
    sparse = _StubRetriever([_nws("B", 9.0), _nws("C", 5.0)])
    fused = QueryFusionRetriever(
        [dense, sparse],
        llm=MockLLM(),  # never invoked at num_queries=1; avoids Settings.llm resolution
        mode="reciprocal_rerank",
        similarity_top_k=10,
        num_queries=1,
        use_async=False,
    ).retrieve("any question")
    ids = [r.node.node_id for r in fused]
    assert ids == ["B", "A", "C"]  # B earned RRF mass from BOTH arms; deduped by hash
```

- [ ] **Step 3: Run it** — `uv run pytest tests/test_hybrid.py -v`. Expected: PASS already (it tests the library, not our code — if it FAILS, stop: the fusion behavior we designed against does not hold; do not proceed on vibes). If the package import fails, run `uv sync`.

- [ ] **Step 4: Add `load_nodes` to `src/store.py`** (below `verify_store`):

```python
def load_nodes(embed: str = DEFAULT_EMBED) -> list[TextNode]:
    """Rebuild chunk nodes FROM Postgres (D12): dense and sparse must score
    byte-identical chunk sets, so the sparse index is derived from the store
    of record — never by re-chunking the PDF. RRF dedups by node.hash
    (text + metadata), so the reconstruction must match ingest-time nodes
    exactly; node ids are used to PAIR nodes for verification, not by fusion."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(f'SELECT node_id, text, metadata_ FROM "{full_table(embed)}" ORDER BY id')
        rows = cur.fetchall()
    nodes = []
    for node_id, text, meta in rows:
        node = TextNode(
            id_=node_id,
            text=text,
            metadata={"page": meta["page"], "section": meta["section"]},
        )
        # D20: BM25Retriever tokenizes EMBED-mode content — mirror ingest exactly
        node.excluded_embed_metadata_keys = ["page"]
        nodes.append(node)
    return nodes
```

Imports to add in `store.py`: `from llama_index.core.schema import TextNode`.

- [ ] **Step 5: Write the hermetic mirror test** (pins the load_nodes reconstruction against `build_nodes` without a database — the drift guard for the D20 invariant). Append to `tests/test_hybrid.py`:

```python
def test_load_nodes_reconstruction_mirrors_ingest_nodes_exactly():
    # simulate the Postgres round-trip: build_nodes -> (node_id, text, {page,
    # section}) row -> reconstructed TextNode. Hash AND embed-content equality
    # is what RRF dedup and the D20 invariant actually require.
    from llama_index.core import Document

    pages = [
        Document(text="5.4 Lubrication Oil\nUse API CF4 grade oil.", metadata={"page": "42"}),
        Document(text="More details continue without any heading.", metadata={"page": "43"}),
    ]
    for original in build_nodes(pages):
        rebuilt = TextNode(
            id_=original.node_id,
            text=original.text,
            metadata={"page": original.metadata["page"], "section": original.metadata["section"]},
        )
        rebuilt.excluded_embed_metadata_keys = ["page"]
        assert rebuilt.hash == original.hash  # RRF dedup key
        assert rebuilt.get_content(metadata_mode=MetadataMode.EMBED) == original.get_content(
            metadata_mode=MetadataMode.EMBED
        )  # D20: BM25 tokenizes what dense embedded
```

Run: `uv run pytest tests/test_hybrid.py -v` → 2 passed. (If the hash assert fails, `load_nodes`' reconstruction has drifted from `build_nodes` — fix the mirror, never relax the test.)

- [ ] **Step 6: Create `src/hybrid.py`:**

```python
"""Hybrid retrieval (D12/D13): dense + in-memory BM25, fused by RRF (k=60).

The BM25 index is a derived cache built from the Postgres chunks at first
use (D12: never re-chunk; re-ingesting requires a process restart to rebuild).
BM25Retriever tokenizes EMBED-mode content, so sparse sees exactly the text
the dense side embedded (D20 invariant). Fusion dedups by node.hash
(text + metadata) — load_nodes must reconstruct ingest-time nodes exactly.
"""

import sys
from functools import lru_cache

from llama_index.core.llms.mock import MockLLM
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.schema import NodeWithScore
from llama_index.retrievers.bm25 import BM25Retriever

from src.config import CANDIDATE_K, DEFAULT_EMBED
from src.store import get_index, load_nodes


@lru_cache(maxsize=2)  # one per embed tier; process-lifetime cache (D12)
def _arms(embed: str):
    dense = get_index(embed).as_retriever(similarity_top_k=CANDIDATE_K)
    sparse = BM25Retriever.from_defaults(nodes=load_nodes(embed), similarity_top_k=CANDIDATE_K)
    return dense, sparse


@lru_cache(maxsize=2)
def _fusion_retriever(embed: str) -> QueryFusionRetriever:
    return QueryFusionRetriever(
        list(_arms(embed)),
        llm=MockLLM(),  # query expansion is off (num_queries=1); never invoked
        mode="reciprocal_rerank",  # D13: RRF, library constant k=60
        similarity_top_k=CANDIDATE_K,  # 10 fused candidates out
        num_queries=1,  # D13: no silent LLM query expansion (default is 4!)
        use_async=False,
    )


def hybrid_candidates(question: str, embed: str = DEFAULT_EMBED) -> list[NodeWithScore]:
    """The 10 fused candidates in RRF order — the reranker's input (D14)."""
    return _fusion_retriever(embed).retrieve(question)


def arm_results(question: str, embed: str = DEFAULT_EMBED) -> dict[str, list[NodeWithScore]]:
    """Per-arm top-10 — eval instrumentation only (D23): makes 'BM25 moved
    this row' demonstrable instead of post hoc, and makes the zero-score
    sparse-padding trigger measurable."""
    dense, sparse = _arms(embed)
    return {"dense": dense.retrieve(question), "sparse": sparse.retrieve(question)}


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "How does high fuel sulphur content affect the oil change interval?"
    results = hybrid_candidates(question)
    for r in results:
        print(
            f"{r.score:.4f}  p.{r.node.metadata['page']:>3}  "
            f"[{r.node.metadata.get('section', '?')[:40]}]  "
            f"{r.node.text[:70].replace(chr(10), ' ')}"
        )
    # smoke canaries (see Step 7)
    assert len({r.node.hash for r in results}) == len(results), "duplicate content in fused list"
    both_arms = sum(1 for r in results if (r.score or 0) > 1 / 61)
    print(f"candidates with RRF mass from BOTH arms (score > 1/61): {both_arms}")
```

- [ ] **Step 7: Smoke against the live DB** (Docker pg must be up; one embedding call):

```bash
uv run python -m src.hybrid "How does high fuel sulphur content affect the oil change interval?"
```

Expected canaries:
- 10 candidates, RRF scores in the 0.014–0.033 band (max 2/61 ≈ 0.0328, min singleton 1/70 ≈ 0.0143).
- **p. 43 ranked higher than the dense baseline placed it** (dense had it at rank 5 — "sulphur" is a rare term BM25 weights heavily; this is the D12 exhibit).
- No duplicate-hash assertion failure.
- `both arms` count ≥ 1: any candidate scoring > 1/61 ≈ 0.0164 necessarily earned RRF mass from **both** arms — the one number that proves dedup+fusion works end-to-end (a truncated-to-10 list would print 10 lines even with dedup broken; this check cannot be fooled that way).

- [ ] **Step 8: Verify the cross-arm identity invariants against the live DB** (id pairs nodes; hash and EMBED content are what fusion and D20 actually depend on):

```bash
uv run python -c "
from llama_index.core.schema import MetadataMode
from src.config import CANDIDATE_K
from src.store import get_index, load_nodes
loaded = {n.node_id: n for n in load_nodes('small')}
dense = get_index('small').as_retriever(similarity_top_k=CANDIDATE_K).retrieve('fuel sulphur oil change')
for r in dense:
    twin = loaded[r.node.node_id]                    # id pairing (KeyError = drift, loud)
    assert twin.hash == r.node.hash, f'hash mismatch on {r.node.node_id}'   # RRF dedup key
    assert twin.get_content(metadata_mode=MetadataMode.EMBED) == r.node.get_content(metadata_mode=MetadataMode.EMBED), f'EMBED content mismatch on {r.node.node_id}'  # D20 byte-identity
print(f'OK: {len(dense)} dense-retrieved nodes match their loaded twins on hash AND embed content')
"
```

- [ ] **Step 9: Docs + full suite + lint + commit.** Add a `hybrid.py` section to `docs/documentation/src.md` (after `retrieve.py`) and a `load_nodes` line to its `store.py` section (use the update-docs skill).

```bash
uv run pytest -q && uv run ruff check src tests eval
git add src/config.py src/store.py src/hybrid.py tests/test_hybrid.py docs/documentation/src.md pyproject.toml uv.lock
git commit -m "M3 Task 1: hybrid retrieval - BM25 from Postgres nodes + RRF fusion (D12/D13)" && git push
```

---

### Task 2: Listwise Haiku reranker with RRF fallback (D14/D16)

**Files:**
- Modify: `src/config.py` (add `RERANK_MODEL`)
- Create: `src/rerank.py`
- Test: `tests/test_rerank.py`
- Modify: `docs/documentation/src.md` (hook)

**Interfaces:**
- Consumes: `hybrid.hybrid_candidates`, `config.TOP_K`.
- Produces: `rerank.RerankResult` dataclass (`chunks: list[NodeWithScore]`, `fallback: bool`); `rerank.rerank(question: str, candidates: list[NodeWithScore]) -> RerankResult` (always top-`TOP_K` — no `k` parameter: D13 fixes the budget, and a `k` that disagrees with the prompt is a footgun); `rerank.rerank_retrieve(question: str, embed: str = DEFAULT_EMBED) -> list[NodeWithScore]` (CLI/serving-shaped; note it discards the fallback flag — M4 must serve from `rerank()` directly); `rerank.parse_ranking(raw: str, k: int, n: int) -> list[int]`; `rerank.rerank_prompt(question, candidates) -> str`; `rerank.RerankParseError`. Task 3 consumes.

- [ ] **Step 1: Add the model constant to `src/config.py`** (next to `JUDGE_MODEL`):

```python
RERANK_MODEL = "claude-haiku-4-5"  # D16; swap predicate pre-registered in the M3 plan Task 4
```

- [ ] **Step 2: Write the failing tests** in `tests/test_rerank.py`:

```python
from types import SimpleNamespace

import anthropic
import pytest
from llama_index.core.schema import NodeWithScore, TextNode

import src.rerank as rerank_mod
from src.rerank import RerankParseError, parse_ranking, rerank, rerank_prompt


def _chunk(node_id: str, page: str) -> NodeWithScore:
    node = TextNode(id_=node_id, text=f"chunk {node_id}", metadata={"page": page, "section": "5.6 Fuel"})
    return NodeWithScore(node=node, score=0.02)


CANDS = [_chunk(f"c{i}", str(40 + i)) for i in range(1, 11)]  # 10 candidates


def test_parse_ranking_accepts_topk_of_n():
    assert parse_ranking('{"ranking": [3, 1, 7, 2, 9]}', k=5, n=10) == [3, 1, 7, 2, 9]


def test_parse_ranking_strips_code_fences():
    assert parse_ranking('```json\n{"ranking": [1, 2, 3, 4, 5]}\n```', k=5, n=10) == [1, 2, 3, 4, 5]


def test_parse_ranking_rejects_garbage_wrong_length_dupes_out_of_range():
    for bad in (
        "the best chunks are 3 and 1",          # not JSON
        '{"ranking": [1, 2, 3]}',                # wrong length
        '{"ranking": [1, 1, 2, 3, 4]}',          # duplicate
        '{"ranking": [1, 2, 3, 4, 11]}',         # out of range
        '{"ranking": "1,2,3,4,5"}',              # wrong type
    ):
        with pytest.raises(RerankParseError):
            parse_ranking(bad, k=5, n=10)


def test_rerank_prompt_numbers_all_candidates_carries_question_and_hides_pages():
    p = rerank_prompt("Which fuel standard?", CANDS)
    assert "Which fuel standard?" in p
    for i in range(1, 11):
        assert f"[{i}]" in p
    assert '"ranking"' in p
    assert "5.6 Fuel" in p      # section = topical signal, shown (D20 rationale)
    assert "p. 41" not in p     # page number = noise, withheld from the reranker


def test_rerank_reorders_on_valid_response(monkeypatch):
    monkeypatch.setattr(rerank_mod, "_call", lambda prompt: '{"ranking": [10, 9, 8, 7, 6]}')
    result = rerank("Q?", CANDS)
    assert result.fallback is False
    assert [c.node.node_id for c in result.chunks] == ["c10", "c9", "c8", "c7", "c6"]


def test_rerank_falls_back_to_rrf_order_on_parse_failure(monkeypatch):
    # D14: a reranker failure may degrade ranking quality, never break a query
    monkeypatch.setattr(rerank_mod, "_call", lambda prompt: "I think chunk 3 is best!")
    result = rerank("Q?", CANDS)
    assert result.fallback is True
    assert [c.node.node_id for c in result.chunks] == ["c1", "c2", "c3", "c4", "c5"]


def test_rerank_falls_back_on_api_error(monkeypatch):
    # the external call is the boundary where failure is real — a transient
    # 529 on eval row 11/12 must not burn the whole paid run
    def _boom(prompt):
        raise anthropic.AnthropicError("overloaded")

    monkeypatch.setattr(rerank_mod, "_call", _boom)
    result = rerank("Q?", CANDS)
    assert result.fallback is True
    assert [c.node.node_id for c in result.chunks] == ["c1", "c2", "c3", "c4", "c5"]
```

- [ ] **Step 3: Run to fail** — `uv run pytest tests/test_rerank.py -v`. Expected: collection error (module missing).

- [ ] **Step 4: Create `src/rerank.py`:**

```python
"""Listwise reranking (D14/D16): one Haiku call orders the 10 fused candidates
against each other; the top-5 survive. Bi-encoder retrieval scores "same
topic"; a reranker reads question and chunk together — "actually answers
this". Parse failures AND transport/API failures fall back to RRF order: a
serving-path stage degrades gracefully (contrast the D17 judge, which fails
loudly — an eval instrument must never silently degrade). No retry (D14).

The prompt shows each candidate's section label (the same topical signal D20
embeds) but NOT its page number (D20 calls page numbers noise; a low page
number could read as "front matter" — an uncontrolled input, withheld)."""

import json
import re
from dataclasses import dataclass

import anthropic
from llama_index.core.schema import NodeWithScore

from src.config import DEFAULT_EMBED, RERANK_MODEL, TOP_K
from src.hybrid import hybrid_candidates


class RerankParseError(RuntimeError):
    pass


@dataclass
class RerankResult:
    chunks: list[NodeWithScore]
    fallback: bool  # True -> RRF order kept (call failed or response unparseable)


def rerank_prompt(question: str, candidates: list[NodeWithScore]) -> str:
    blocks = [
        f"[{i}] ({c.node.metadata.get('section', 'unknown')})\n{c.node.text}"
        for i, c in enumerate(candidates, start=1)
    ]
    return (
        "Rank the excerpts below by how well they ANSWER the question — not merely "
        "mention its topic. Respond with ONLY this JSON object, no other text:\n"
        f'{{"ranking": [<the {TOP_K} best excerpt numbers, best first>]}}\n\n'
        f"Question: {question}\n\n" + "\n\n---\n\n".join(blocks)
    )


def parse_ranking(raw: str, k: int, n: int) -> list[int]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise RerankParseError(f"not JSON: {raw[:200]!r}") from e
    ranking = obj.get("ranking") if isinstance(obj, dict) else None
    if not (
        isinstance(ranking, list)
        and len(ranking) == k
        and all(isinstance(i, int) and 1 <= i <= n for i in ranking)
        and len(set(ranking)) == k
    ):
        raise RerankParseError(f"invalid ranking (need {k} distinct ints in 1..{n}): {raw[:200]!r}")
    return ranking


def _call(prompt: str) -> str:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=RERANK_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return next((b.text for b in response.content if b.type == "text"), "")


def rerank(question: str, candidates: list[NodeWithScore]) -> RerankResult:
    try:
        raw = _call(rerank_prompt(question, candidates))
        order = parse_ranking(raw, k=TOP_K, n=len(candidates))
    except (anthropic.AnthropicError, RerankParseError) as e:
        print(f"rerank fallback — RRF order kept: {e}")
        return RerankResult(chunks=candidates[:TOP_K], fallback=True)
    return RerankResult(chunks=[candidates[i - 1] for i in order], fallback=False)


def rerank_retrieve(question: str, embed: str = DEFAULT_EMBED) -> list[NodeWithScore]:
    """CLI/serving-shaped wrapper. NOTE: discards the fallback flag — M4's
    API must call rerank() directly so degradation stays observable."""
    return rerank(question, hybrid_candidates(question, embed)).chunks


if __name__ == "__main__":
    import sys

    question = " ".join(sys.argv[1:]) or "How does high fuel sulphur content affect the oil change interval?"
    for r in rerank_retrieve(question):
        print(f"p.{r.node.metadata['page']:>3}  [{r.node.metadata.get('section', '?')[:40]}]  "
              f"{r.node.text[:70].replace(chr(10), ' ')}")
```

- [ ] **Step 5: Run tests** — `uv run pytest tests/test_rerank.py -v`. Expected: 7 passed.

- [ ] **Step 6: Paid smoke (one Haiku call, cents):**

```bash
uv run python -m src.rerank "How does high fuel sulphur content affect the oil change interval?"
```

Expected: 5 chunks, no fallback message, and the p. 43 sulphur chunk at or near rank 1. (Systemic parse failure — e.g. Haiku consistently truncating — would show up as the fallback count in the Task 4 report header, 12/12; one paid call cannot rule that out and doesn't need to.)

- [ ] **Step 7: Docs + commit.** Add a `rerank.py` section to `docs/documentation/src.md`.

```bash
uv run pytest -q && uv run ruff check src tests eval
git add src/config.py src/rerank.py tests/test_rerank.py docs/documentation/src.md
git commit -m "M3 Task 2: listwise Haiku reranker, RRF-order fallback on parse+API failure (D14/D16)" && git push
```

---

### Task 3: Eval retrieval-mode registry + candidate/arm instrumentation

**Files:**
- Modify: `eval/run.py`
- Test: `tests/test_run.py` (extend; ONE permitted edit to the existing test — see Step 1)
- Modify: `docs/documentation/eval.md` (hook)

**Interfaces:**
- Consumes: `retrieve`, `hybrid_candidates`, `arm_results`, `rerank` (Task 2 `RerankResult`), `config.TOP_K`, `config.RERANK_MODEL`.
- Produces: `run_eval(mode: str = "dense", embed: str = DEFAULT_EMBED) -> dict` with `config_label = f"{mode}-{embed}"` and `rerank_model` recorded (rerank mode only); rows gain `candidates: list[{node_id, page, score}] | None`, `dense_pages`/`sparse_pages` (per-arm top-10 pages, hybrid/rerank only), `rerank_fallback: bool`; CLI `--mode dense|hybrid|rerank`. `write_report` prints reranker model + named fallback rows.

- [ ] **Step 1: Fix the existing stub test's call convention** — the ONLY permitted edit to the existing test: in `tests/test_run.py`, change `run = run_mod.run_eval("small")` to `run = run_mod.run_eval(embed="small")` (the new signature is `run_eval(mode, embed)`; positional `"small"` would land in `mode`). Then append the new tests:

```python
def test_run_eval_hybrid_mode_logs_candidates_arms_and_rerank_flags(monkeypatch, tmp_path):
    golden = [
        GoldenQuestion(
            id="q1",
            qtype="lexical",
            question="Which fuel?",
            expected_pages=["43"],
            golden_answer="EN590.",
            annotation=None,
            trap=False,
        ),
    ]
    cands = [_chunk("43"), _chunk("29"), _chunk("11")]
    monkeypatch.setattr(run_mod, "load_golden", lambda: golden)
    monkeypatch.setattr(run_mod, "hybrid_candidates", lambda q, embed=None: cands)
    monkeypatch.setattr(
        run_mod,
        "arm_results",
        lambda q, embed=None: {"dense": cands[:2], "sparse": cands[1:]},
    )
    monkeypatch.setattr(
        run_mod,
        "rerank",
        lambda q, c: SimpleNamespace(chunks=c[:2], fallback=True),
    )
    monkeypatch.setattr(
        run_mod,
        "answer_from_chunks",
        lambda q, chunks: SimpleNamespace(answer="EN590 (p. 43).", sources=[]),
    )
    monkeypatch.setattr(run_mod, "judge_groundedness", lambda *a: _verdict(True))
    monkeypatch.setattr(run_mod, "judge_correctness", lambda *a: _verdict(True))

    run = run_mod.run_eval(mode="rerank", embed="small")
    assert run["config_label"] == "rerank-small"
    assert run["rerank_model"]  # provenance lives in the artifact (D16 swap!)
    row = run["rows"][0]
    assert [c["page"] for c in row["candidates"]] == ["43", "29", "11"]
    assert all("node_id" in c and "score" in c for c in row["candidates"])
    assert row["dense_pages"] == ["43", "29"] and row["sparse_pages"] == ["29", "11"]
    assert row["rerank_fallback"] is True

    report = run_mod.write_report(run, out_dir=tmp_path)
    text = report.read_text()
    assert "fallback" in text.lower() and "q1" in text  # fallback rows are NAMED


def test_run_eval_dense_mode_keeps_schema_with_null_instrumentation(monkeypatch, tmp_path):
    golden = [
        GoldenQuestion(
            id="q1",
            qtype="lexical",
            question="Which fuel?",
            expected_pages=["43"],
            golden_answer="EN590.",
            annotation=None,
            trap=False,
        ),
    ]
    monkeypatch.setattr(run_mod, "load_golden", lambda: golden)
    monkeypatch.setattr(run_mod, "retrieve", lambda q, embed=None: [_chunk("43")])
    monkeypatch.setattr(
        run_mod,
        "answer_from_chunks",
        lambda q, chunks: SimpleNamespace(answer="EN590 (p. 43).", sources=[]),
    )
    monkeypatch.setattr(run_mod, "judge_groundedness", lambda *a: _verdict(True))
    monkeypatch.setattr(run_mod, "judge_correctness", lambda *a: _verdict(True))

    run = run_mod.run_eval(embed="small")  # default mode="dense"
    row = run["rows"][0]
    assert row["candidates"] is None
    assert row["rerank_fallback"] is False
    assert run["rerank_model"] is None
    assert "dense_pages" not in row
```

- [ ] **Step 2: Run to fail** — `uv run pytest tests/test_run.py -v`. Expected: the two new tests fail (`run_eval() got an unexpected keyword argument 'mode'`).

- [ ] **Step 3: Rework `eval/run.py`.** The three `src.*` import lines become exactly (avoid duplicating existing imports — this REPLACES the current `src.config`/`src.generate`/`src.retrieve` import block):

```python
from src.config import (
    DEFAULT_EMBED,
    EMBED_CONFIGS,
    GENERATION_MODEL,
    JUDGE_MODEL,
    RERANK_MODEL,
    TOP_K,
)
from src.generate import answer_from_chunks, format_context
from src.hybrid import arm_results, hybrid_candidates
from src.rerank import rerank
from src.retrieve import retrieve
```

Registry (above `run_eval`) — each mode returns `(final_chunks, candidates_or_None, arms_or_None, rerank_fallback)`:

```python
def _dense(question: str, embed: str):
    return retrieve(question, embed=embed), None, None, False


def _hybrid(question: str, embed: str):
    cands = hybrid_candidates(question, embed)
    return cands[:TOP_K], cands, arm_results(question, embed), False


def _rerank(question: str, embed: str):
    cands = hybrid_candidates(question, embed)
    result = rerank(question, cands)
    return result.chunks, cands, arm_results(question, embed), result.fallback


MODES = {"dense": _dense, "hybrid": _hybrid, "rerank": _rerank}
```

`run_eval` head becomes (the judge if/else block and the models/version dict tail stay EXACTLY as they are in the file today; only the shown keys change/appear):

```python
def run_eval(mode: str = "dense", embed: str = DEFAULT_EMBED) -> dict:
    rows = []
    for q in load_golden():
        chunks, candidates, arms, fell_back = MODES[mode](q.question, embed)
        context = format_context(chunks)  # as-logged (D17)
        rag = answer_from_chunks(q.question, chunks)
        pages = [c.node.metadata["page"] for c in chunks]
        row = {
            "id": q.id,
            "qtype": q.qtype,
            "question": q.question,
            "expected_pages": q.expected_pages,
            "retrieved_pages": pages,
            # D23 instrumentation: 10-deep fused candidates, identity-bearing
            "candidates": (
                [
                    {
                        "node_id": c.node.node_id,
                        "page": c.node.metadata["page"],
                        "score": round(c.score or 0.0, 4),
                    }
                    for c in candidates
                ]
                if candidates is not None
                else None
            ),
            "rerank_fallback": fell_back,
            "answer": rag.answer,
            "context": context,
            "annotation": q.annotation,
            "trap": q.trap,
            "golden_answer": q.golden_answer,
        }
        if arms is not None:
            # per-arm top-10 pages + sparse scores: makes "BM25 moved this row"
            # demonstrable, and zero-score sparse padding visible
            row["dense_pages"] = [c.node.metadata["page"] for c in arms["dense"]]
            row["sparse_pages"] = [c.node.metadata["page"] for c in arms["sparse"]]
            row["sparse_scores"] = [round(c.score or 0.0, 4) for c in arms["sparse"]]
        ...  # judge block unchanged
        rows.append(row)
        print(f"{q.id}: done")
    return {
        "date": datetime.date.today().isoformat(),
        "embed": embed,
        "mode": mode,
        "config_label": f"{mode}-{embed}",
        "rerank_model": RERANK_MODEL if mode == "rerank" else None,
        ...  # embed_model/generation_model/judge_model/judge_prompt_version/rows unchanged
    }
```

In `write_report`, build these lines **inside** the `lines = [...]` list construction, immediately after the predicted-fail-ceiling entry (no positional `insert` arithmetic). Compute just above the list:

```python
    fallback_ids = [r["id"] for r in run["rows"] if r.get("rerank_fallback")]
```

and add to the list construction:

```python
        *(
            [
                f"- Reranker: `{run['rerank_model']}`."
                + (
                    f" Fallbacks: {len(fallback_ids)}/{len(run['rows'])} rows kept RRF order"
                    f" ({', '.join(fallback_ids)}) — these rows contribute zero rerank delta"
                    " by construction; the delta over non-fallback rows is the honest readout."
                    if fallback_ids
                    else " No fallbacks — all 12 rankings parsed."
                )
            ]
            if run.get("rerank_model")
            else []
        ),
```

CLI dispatch gains `--mode`:

```python
    parser.add_argument("--mode", default="dense", choices=list(MODES))
    ...
    else:
        path = write_report(run_eval(args.mode, args.embed))
        print(f"report: {path}")
```

- [ ] **Step 4: Run tests** — `uv run pytest tests/test_run.py -v`. Expected: 3 passed (old test with its one-line edit + two new).

- [ ] **Step 5: Docs + commit.** Update `docs/documentation/eval.md`: the "Running it" section gains `--mode dense|hybrid|rerank`, candidate/per-arm logging, and the reranker-provenance line.

```bash
uv run pytest -q && uv run ruff check src tests eval
git add eval/run.py tests/test_run.py docs/documentation/eval.md
git commit -m "M3 Task 3: eval retrieval-mode registry + candidate/arm instrumentation (D23)" && git push
```

---

### Task 4: Measure hybrid, then rerank — two attributable deltas (HUMAN CHECKPOINT)

Ordering is D14-mandated: hybrid **before** rerank, each delta attributable to exactly one change. Baseline JSON `eval/results/2026-07-14-dense-small.json` must exist locally (it is gitignored; if missing, stop — re-run and re-bless the baseline rather than comparing against nothing).

Capture the date ONCE at the top (all later commands use it; a midnight crossing must not split the run set):

```bash
RUN_DATE=$(date +%F)
```

- [ ] **Step 1: Hybrid run (~$1: 12 generations + ~23 judge calls):**

```bash
uv run python -m eval.run --mode hybrid --embed small
```

Sanity: q1 still hits p. 43 rank 1; q5's p. 43 should rise (BM25 loves "sulphur"); the trap must still be refused.

- [ ] **Step 2: Compare dense→hybrid** (tee — the tables feed Step 6's report section):

```bash
uv run python -m eval.run --compare eval/results/2026-07-14-dense-small.json "eval/results/${RUN_DATE}-hybrid-small.json" | tee /tmp/compare-dense-hybrid.txt
```

Read against D23: expected movement on q5 RR; q10/q11 expected unchanged at 1.00 (saturated); hit@5 expected unchanged 10/11 (q8 unfixable). Then the TOC + sparse-padding counts:

```bash
uv run python -c "
import json, sys
for path in sys.argv[1:]:
    run = json.load(open(path))
    top5 = sum(1 for r in run['rows'] if '5' in r['retrieved_pages'])
    cands = sum(1 for r in run['rows'] if r.get('candidates') and '5' in [c['page'] for c in r['candidates']])
    padded = sum(1 for r in run['rows'] if any(s == 0.0 for s in r.get('sparse_scores', [])))
    print(f\"{run['config_label']}: TOC p.5 in top-5: {top5}/12 rows; in 10-deep candidates: {cands}/12; rows with zero-score sparse padding: {padded}/12\")
" eval/results/2026-07-14-dense-small.json "eval/results/${RUN_DATE}-hybrid-small.json"
```

**Pre-registered trigger (zero-score padding):** if any fused top-5 member's only support is a zero-score sparse rank (check the row's `sparse_scores` against its `candidates`), add a score>0 filter on the sparse arm and re-measure — otherwise no filter (D13: no knobs without a number).

- [ ] **Step 3: Rerank run (~$1 + 12 Haiku calls), then verify the rerank delta's central invariant:**

```bash
uv run python -m eval.run --mode rerank --embed small
uv run python -m eval.run --compare "eval/results/${RUN_DATE}-hybrid-small.json" "eval/results/${RUN_DATE}-rerank-small.json" | tee /tmp/compare-hybrid-rerank.txt
```

**Candidate-identity check (query embeddings are fresh API calls and not bit-deterministic — identical candidates across the two runs is an assumption until checked):**

```bash
uv run python -c "
import json
h = {r['id']: r for r in json.load(open('eval/results/${RUN_DATE}-hybrid-small.json'))['rows']}
k = {r['id']: r for r in json.load(open('eval/results/${RUN_DATE}-rerank-small.json'))['rows']}
same = [i for i in h if h[i].get('candidates') and [c['node_id'] for c in h[i]['candidates']] == [c['node_id'] for c in k[i]['candidates']]]
print(f'identical candidate lists across runs: {len(same)}/{len([i for i in h if h[i].get(\"candidates\")])} rows')
"
```

State the result in the report. **Regardless of the cross-run result, the attributable rank movement is computed within the rerank run alone**: each row's `candidates[:5]` (node_ids) IS that run's hybrid top-5 — compare it to `retrieved_pages`/final chunks for the ranking delta with candidate identity guaranteed by construction. The cross-run compare table stays for the generation/judge counts.

Also check the report header's fallback line — fallback rows contribute zero rerank delta by construction, so Step 6's analysis must also report the delta over non-fallback rows only. Re-run the Step 2 TOC/padding count including the rerank JSON.

- [ ] **Step 4 (conditional diagnostic — run BEFORE any model swap): anchoring check.** The reranker's input arrives best-first (RRF order) and listwise LLMs mildly favor early positions — so a null delta may be anchoring, not model weakness, and a Sonnet swap cannot distinguish the two. If the Step 5 predicate fires, first re-run the 11 answerable questions once with candidates in REVERSED order (12 Haiku calls, cents — a one-off `python -c` loop calling `rerank(q, list(reversed(cands)))` on the logged candidates from the rerank JSON, no re-generation) and compare the outputs:
  - Output tracks the reversed input → the null is **anchoring**; record that as the finding (not "reranking doesn't help") and skip the Sonnet swap (it would anchor the same way).
  - Output recovers substantially the same top-5 → the null is real; proceed to the swap in Step 5.

- [ ] **Step 5: D16 swap — mechanical predicate (pre-registered; no mid-measurement judgment).** The swap fires iff, over the 11 answerable rows:
  - (a) hits(rerank) < hits(hybrid); **OR**
  - (b) MRR(rerank) ≤ MRR(hybrid); **OR**
  - (c) MRR(rerank) > MRR(hybrid) but **neither q5 nor q7 RR improved and the top-5 TOC count did not drop** — a positive delta that misses every pre-committed D23 headroom target is a null for D16's purpose.

If it fires (and Step 4 said "real, not anchoring"):

```bash
# in src/config.py: RERANK_MODEL = "claude-sonnet-5"
mkdir -p eval/results/superseded
mv "eval/results/${RUN_DATE}-rerank-small.json" "eval/results/superseded/${RUN_DATE}-rerank-small-haiku.json"
mv "eval/results/${RUN_DATE}-rerank-small.md" "eval/results/superseded/${RUN_DATE}-rerank-small-haiku.md"
uv run python -m eval.run --mode rerank --embed small
uv run python -m eval.run --compare "eval/results/${RUN_DATE}-hybrid-small.json" "eval/results/${RUN_DATE}-rerank-small.json" | tee /tmp/compare-hybrid-rerank-sonnet.txt
```

The run JSON records `rerank_model`, so the two runs are distinguishable by artifact content, not directory. **Whichever way the swap goes, the committed rerank report must contain the Haiku per-question hit/MRR table** (paste from the tee'd compare) — a null result is a finding and must not vanish into a gitignored folder. Both outcomes get a decision-log entry (decision-logging skill): "Sonnet rescues the delta" or "reranking adds nothing at this corpus size" (then revert `RERANK_MODEL` to Haiku).

- [ ] **Step 6: Append `## M3 vs baseline` to the rerank report** (`eval/results/${RUN_DATE}-rerank-small.md`): the two compare tables (dense→hybrid, hybrid→rerank), the within-run attributable rank movement (candidates[:5] vs final), the candidate-identity check result, TOC/padding counts per config, named fallback rows + non-fallback delta, the anchoring-diagnostic outcome if run, the swap outcome with the Haiku table if fired, and the D23 predictions checked one by one (q5/q7 MRR movement, q10/q11 unchanged, hit@5 unchanged, TOC acceptance). State plainly which predictions held and which didn't.

- [ ] **Step 7: Calibration-transfer disclosure + targeted spot-check.** Add one sentence to the M3 section: "grounded/correct judged single-run under the D17 calibration (performed on baseline outputs; treated as an instrument property, not re-verified on M3 outputs)." Then for any row whose grounded/correct verdict **changed vs the dense baseline**, re-judge that axis 3× fresh (a few Opus calls — changed rows are exactly the borderline candidates) before reporting the changed verdict; note the outcome in the report:

```bash
uv run python -c "
import json
from eval.judge import judge_correctness, judge_groundedness
base = {r['id']: r for r in json.load(open('eval/results/2026-07-14-dense-small.json'))['rows']}
new = json.load(open('eval/results/${RUN_DATE}-rerank-small.json'))['rows']
for r in new:
    if r['trap']:
        continue
    for axis, fn, args in (
        ('grounded', judge_groundedness, (r['question'], r['context'], r['answer'])),
        ('correct', judge_correctness, (r['question'], r['golden_answer'], r['answer'])),
    ):
        if r[axis] != base[r['id']][axis]:
            fresh = [fn(*args).passed for _ in range(3)]
            print(f\"{r['id']}/{axis}: baseline={base[r['id']][axis]} logged={r[axis]} fresh3x={fresh}\")
"
```

(Repeat for the hybrid JSON if its judge counts differ from baseline.)

- [ ] **Step 8 (do not skip): HUMAN CHECKPOINT.** Present both deltas with per-question movements, the within-run rank movement, candidate-identity result, TOC counts, named fallbacks, spot-check outcomes, the anchoring/swap outcome if fired, and the honest verdict sentence ("hybrid moved X, reranking moved Y — attributable readout hit/MRR only"). The user blesses before commit.

- [ ] **Step 9: Commit the blessed M3 measurement:**

```bash
git add eval/results/*.md docs/decisions.md
git commit -m "M3 Task 4: hybrid + rerank measured against dense baseline - attributable deltas (D12/D13/D14)" && git push
```

(Add `src/config.py` + `docs/documentation/src.md` only if the swap fired and stuck.)

---

### Task 5: M3 wrap-up — docs, README, lint, final commit

- [ ] **Step 1:** `docs/documentation/eval.md`: add an "M3 configs" note to the A/B section — three comparable configs (`dense`/`hybrid`/`rerank`), compare pairs share the tier, hit/MRR remain the attributable readout, reranker provenance in every artifact.
- [ ] **Step 2:** `README.md`: add to Quickstart:

```bash
uv run python -m src.hybrid "your question"     # fused dense+BM25 candidates
uv run python -m src.rerank "your question"     # reranked top-5 (one Haiku call)
uv run python -m eval.run --mode rerank --embed small
```

Also bump the decision-log range in the Documentation section (D1–D23 → current max).
- [ ] **Step 3:** `uv run ruff check src tests eval && uv run ruff format --check src tests eval` — fix findings (format-only reflows may be committed with `--no-verify`, stated in the commit message).
- [ ] **Step 4:** `uv run pytest -q` — all pass (~40 tests).
- [ ] **Step 5:** Final commit:

```bash
git add README.md docs/documentation/eval.md
git commit -m "M3 complete: hybrid BM25+RRF retrieval and listwise reranking, measured" && git push
```

Report to the user: the three-config table (dense/hybrid/rerank), which D23 predictions held, the swap/anchoring outcome, and the observations that feed M4 (FastAPI serving: BM25 startup rebuild per D12, engine-per-query F2, **serve from `rerank()` directly — `rerank_retrieve` discards the fallback flag and would hide degradation the eval was careful to surface**) and M5 (caption pages 42/48/49/50/51).

---

## Out of scope for this plan

- **M4** FastAPI `POST /query` (+ F2 engine-per-query; D12's startup rebuild becomes an API concern there; fallback-flag surfacing in the response).
- **M5** vision captioning (q8/q9's fix; caption nodes must carry pages 42/48/49/50/51).
- Overlap-aware dedup (watch-item; now *measurable* via candidate `node_id`s — trigger only if a duplicate overlap-twin eats >1 top-5 slot in the M3 runs).
- Positional-bias mitigation beyond the Task 4 Step 4 diagnostic (D14 accepted limitation).
- Sparse zero-score filter (pre-registered trigger in Task 4 Step 2 — added only if the number demands it).

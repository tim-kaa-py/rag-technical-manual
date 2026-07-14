# M3 Hybrid Retrieval + Reranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add BM25 + RRF hybrid retrieval and a listwise Haiku reranker, and measure both deltas against the blessed M2 dense-small baseline (hit@5 10/11 · MRR@5 0.79) with the frozen exam and calibrated judge.

**Architecture:** `src/hybrid.py` fuses the existing dense retriever with an in-memory BM25 index rebuilt from the Postgres chunks (never by re-chunking) via `QueryFusionRetriever` RRF; `src/rerank.py` reorders the 10 fused candidates in one Haiku call with RRF-order fallback. The eval gains a retrieval-mode registry (`dense`/`hybrid`/`rerank`) so each config is a first-class, comparable run. Measurement order is fixed: hybrid *before* rerank, so each delta is attributable.

**Tech Stack:** llama-index-retrievers-bm25 (bm25s), `QueryFusionRetriever` (llama-index core), anthropic SDK (`claude-haiku-4-5` reranker), existing eval harness.

## Global Constraints

- **D12:** BM25 nodes are loaded **out of Postgres** — never by re-chunking the PDF — so dense and sparse score byte-identical chunk sets. In-memory index; Postgres stays the store of record.
- **D13:** Fusion = RRF (`mode="reciprocal_rerank"`, library constant k=60 — adopted, not tuned); `num_queries=1` (no silent LLM query expansion); candidate depth **10 per retriever in, top-5 out**; no tuned fusion weights.
- **D14:** Reranker is **listwise**: one call, all 10 candidates, returns the **top-5 candidate numbers** as strict JSON. Parse failure → fall back to RRF order (serving path degrades gracefully — contrast the D17 judge, which fails loudly). No retry.
- **D16:** Reranker model `claude-haiku-4-5`. **Named swap trigger:** if rerank shows zero/negative delta vs hybrid, swap to `claude-sonnet-5` (one string) and re-measure before concluding anything.
- **D17:** As-logged judging; counts, never percentages; single-run judging (calibrated 2026-07-14: 0/23 flips — judge unchanged, no recalibration); attributable A/B readout = hit/MRR only.
- **D20/D12 invariant (verified in source):** `BM25Retriever` tokenizes `node.get_content(metadata_mode=MetadataMode.EMBED)` — loaded nodes must carry `{page, section}` metadata and `excluded_embed_metadata_keys = ["page"]` so sparse sees exactly what dense embedded.
- **D23 (pre-committed headroom, written before these runs):** M3's measurable target is MRR on q5/q7 + demoting the TOC-magnet chunk (p. 5); hit@5 immovable (10/11; q8 has no text); q10/q11 already rank 1 — no delta expected there; a null on them is instrument saturation, not failure.
- **Verified library facts:** `QueryFusionRetriever.__init__` resolves `Settings.llm` when `llm` is omitted → always pass `llm=MockLLM()` (never invoked at `num_queries=1`; keeps tests hermetic). `num_queries` defaults to 4 → must be set to 1 explicitly.
- Never pass `temperature`/`top_p`/`top_k` to Claude calls; omit `thinking`.
- **Never commit:** `.env`, `data/`, `docs/*.private.md`, `eval/results/*.json` (raw logs contain manual text). `.md` reports ARE committed.
- Unit tests make **no paid API calls and need no database** (Anthropic calls stubbed; fusion tested via stub retrievers).
- Pre-commit hook: commits touching `src/` need `docs/documentation/src.md` staged; `eval/` needs `docs/documentation/eval.md`. Stage **selectively** — parallel sessions may have files in flight; never `git add -A`.
- uv for everything; ruff clean; commit+push after each task. From M3 on, runs log the 10-deep candidate list with scores (D23 instrumentation).

---

### Task 1: Nodes-from-Postgres loader + hybrid retrieval (D12/D13)

**Files:**
- Modify: `src/config.py` (add `CANDIDATE_K`)
- Modify: `src/store.py` (add `load_nodes`)
- Create: `src/hybrid.py`
- Test: `tests/test_hybrid.py`
- Modify: `docs/documentation/src.md` (hook), `pyproject.toml`/`uv.lock` (dep `llama-index-retrievers-bm25` — already added during plan research; commit it here)

**Interfaces:**
- Consumes: `store.get_index(embed)`, `store._conn()`, `store.full_table(embed)`, `config.DEFAULT_EMBED/TOP_K`.
- Produces: `config.CANDIDATE_K = 10`; `store.load_nodes(embed: str = DEFAULT_EMBED) -> list[TextNode]`; `hybrid.hybrid_candidates(question: str, embed: str = DEFAULT_EMBED) -> list[NodeWithScore]` (10 fused, RRF order); `hybrid.hybrid_retrieve(question: str, k: int = TOP_K, embed: str = DEFAULT_EMBED) -> list[NodeWithScore]`. Tasks 2/3 consume.

- [ ] **Step 1: Add the candidate-depth constant to `src/config.py`** (below `TOP_K`):

```python
# D13 — fusion candidate depth: 10 per retriever in, TOP_K out
CANDIDATE_K = 10
```

- [ ] **Step 2: Write the failing library-contract test** in `tests/test_hybrid.py`. This pins the two `QueryFusionRetriever` behaviors we lean on — dedup by node id and doubly-retrieved-wins RRF — with stub retrievers, no DB, no API:

```python
from llama_index.core.llms.mock import MockLLM
from llama_index.core.retrievers import BaseRetriever, QueryFusionRetriever
from llama_index.core.schema import NodeWithScore, TextNode


class _StubRetriever(BaseRetriever):
    def __init__(self, results):
        self._results = results
        super().__init__()

    def _retrieve(self, query_bundle):
        return self._results


def _nws(node_id: str, score: float) -> NodeWithScore:
    return NodeWithScore(node=TextNode(id_=node_id, text=f"text {node_id}"), score=score)


def test_rrf_fusion_dedups_by_node_id_and_prefers_doubly_retrieved():
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
    assert ids == ["B", "A", "C"]  # B earned RRF mass from BOTH arms; deduped
```

- [ ] **Step 3: Run it** — `uv run pytest tests/test_hybrid.py -v`. Expected: PASS already (it tests the library, not our code — if it FAILS, stop: the fusion behavior we designed against does not hold; do not proceed on vibes). If the package import fails, run `uv sync`.

- [ ] **Step 4: Add `load_nodes` to `src/store.py`** (below `verify_store`):

```python
def load_nodes(embed: str = DEFAULT_EMBED) -> list[TextNode]:
    """Rebuild chunk nodes FROM Postgres (D12): dense and sparse must score
    byte-identical chunk sets, so the sparse index is derived from the store
    of record — never by re-chunking the PDF."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(f'SELECT node_id, text, metadata_ FROM "{full_table(embed)}" ORDER BY id')
        rows = cur.fetchall()
    nodes = []
    for node_id, text, meta in rows:
        node = TextNode(
            id_=node_id,  # same id as the dense arm returns -> RRF dedup works
            text=text,
            metadata={"page": meta["page"], "section": meta["section"]},
        )
        # D20: BM25Retriever tokenizes EMBED-mode content — mirror ingest exactly
        node.excluded_embed_metadata_keys = ["page"]
        nodes.append(node)
    return nodes
```

Imports to add in `store.py`: `from llama_index.core.schema import TextNode`.

- [ ] **Step 5: Create `src/hybrid.py`:**

```python
"""Hybrid retrieval (D12/D13): dense + in-memory BM25, fused by RRF (k=60).

The BM25 index is a derived cache built from the Postgres chunks at first
use (D12: never re-chunk; re-ingesting requires a process restart to rebuild).
BM25Retriever tokenizes EMBED-mode content, so sparse sees exactly the text
the dense side embedded (D20 invariant, verified in the installed source).
"""

import sys
from functools import lru_cache

from llama_index.core.llms.mock import MockLLM
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.schema import NodeWithScore
from llama_index.retrievers.bm25 import BM25Retriever

from src.config import CANDIDATE_K, DEFAULT_EMBED, TOP_K
from src.store import get_index, load_nodes


@lru_cache(maxsize=2)  # one per embed tier; process-lifetime cache (D12)
def _fusion_retriever(embed: str) -> QueryFusionRetriever:
    dense = get_index(embed).as_retriever(similarity_top_k=CANDIDATE_K)
    sparse = BM25Retriever.from_defaults(nodes=load_nodes(embed), similarity_top_k=CANDIDATE_K)
    return QueryFusionRetriever(
        [dense, sparse],
        llm=MockLLM(),  # query expansion is off (num_queries=1); never invoked
        mode="reciprocal_rerank",  # D13: RRF, library constant k=60
        similarity_top_k=CANDIDATE_K,  # 10 fused candidates out
        num_queries=1,  # D13: no silent LLM query expansion (default is 4!)
        use_async=False,
    )


def hybrid_candidates(question: str, embed: str = DEFAULT_EMBED) -> list[NodeWithScore]:
    """The 10 fused candidates in RRF order — the reranker's input (D14)."""
    return _fusion_retriever(embed).retrieve(question)


def hybrid_retrieve(
    question: str, k: int = TOP_K, embed: str = DEFAULT_EMBED
) -> list[NodeWithScore]:
    return hybrid_candidates(question, embed)[:k]


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "How does high fuel sulphur content affect the oil change interval?"
    for r in hybrid_candidates(question):
        print(
            f"{r.score:.4f}  p.{r.node.metadata['page']:>3}  "
            f"[{r.node.metadata.get('section', '?')[:40]}]  "
            f"{r.node.text[:70].replace(chr(10), ' ')}"
        )
```

- [ ] **Step 6: Smoke against the live DB** (Docker pg must be up):

```bash
uv run python -m src.hybrid "How does high fuel sulphur content affect the oil change interval?"
```

Expected: 10 candidates, RRF scores (~0.01–0.03 range), and **p. 43 ranked higher than the dense baseline placed it** (dense had it at rank 5 — "sulphur" is a rare term BM25 weights heavily; this is the D12 exhibit). Also verify dedup happened: if the same page appears from both arms it must be one entry per chunk, and node count printed is 10, not 20.

- [ ] **Step 7: Verify node-id identity across arms** (the RRF dedup precondition, verified not assumed):

```bash
uv run python -c "
from src.store import get_index, load_nodes
from src.config import CANDIDATE_K
dense_ids = {r.node.node_id for r in get_index('small').as_retriever(similarity_top_k=CANDIDATE_K).retrieve('fuel sulphur oil change')}
sparse_ids = {n.node_id for n in load_nodes('small')}
overlap = dense_ids & sparse_ids
print(f'dense top-10 ids found in loaded nodes: {len(overlap)}/10')
assert len(overlap) == 10, 'node ids do NOT match across arms - RRF dedup is broken'
print('OK: both arms share node identity')
"
```

- [ ] **Step 8: Docs + full suite + lint + commit.** Add a `hybrid.py` section to `docs/documentation/src.md` (after `retrieve.py`) and a `load_nodes` line to its `store.py` section (use the update-docs skill).

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
- Produces: `rerank.RerankResult` dataclass (`chunks: list[NodeWithScore]`, `fallback: bool`); `rerank.rerank(question: str, candidates: list[NodeWithScore], k: int = TOP_K) -> RerankResult`; `rerank.rerank_retrieve(question: str, k: int = TOP_K, embed: str = DEFAULT_EMBED) -> list[NodeWithScore]`; `rerank.parse_ranking(raw: str, k: int, n: int) -> list[int]`; `rerank.rerank_prompt(question, candidates) -> str`; `rerank.RerankParseError`. Task 3 consumes.

- [ ] **Step 1: Add the model constant to `src/config.py`** (next to `JUDGE_MODEL`):

```python
RERANK_MODEL = "claude-haiku-4-5"  # D16; swap trigger: null M3 delta -> claude-sonnet-5
```

- [ ] **Step 2: Write the failing tests** in `tests/test_rerank.py`:

```python
from types import SimpleNamespace

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


def test_rerank_prompt_numbers_all_candidates_and_carries_question():
    p = rerank_prompt("Which fuel standard?", CANDS)
    assert "Which fuel standard?" in p
    for i in range(1, 11):
        assert f"[{i}]" in p
    assert '"ranking"' in p


def test_rerank_reorders_on_valid_response(monkeypatch):
    monkeypatch.setattr(rerank_mod, "_call", lambda prompt: '{"ranking": [10, 9, 8, 7, 6]}')
    result = rerank("Q?", CANDS, k=5)
    assert result.fallback is False
    assert [c.node.node_id for c in result.chunks] == ["c10", "c9", "c8", "c7", "c6"]


def test_rerank_falls_back_to_rrf_order_on_parse_failure(monkeypatch):
    # D14: a reranker failure may degrade ranking quality, never break a query
    monkeypatch.setattr(rerank_mod, "_call", lambda prompt: "I think chunk 3 is best!")
    result = rerank("Q?", CANDS, k=5)
    assert result.fallback is True
    assert [c.node.node_id for c in result.chunks] == ["c1", "c2", "c3", "c4", "c5"]
```

- [ ] **Step 3: Run to fail** — `uv run pytest tests/test_rerank.py -v`. Expected: collection error (module missing).

- [ ] **Step 4: Create `src/rerank.py`:**

```python
"""Listwise reranking (D14/D16): one Haiku call orders the 10 fused candidates
against each other; the top-5 survive. Bi-encoder retrieval scores "same
topic"; a reranker reads question and chunk together — "actually answers
this". Parse failure falls back to RRF order: a serving-path stage degrades
gracefully (contrast the D17 judge, which fails loudly — an eval instrument
must never silently degrade)."""

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
    fallback: bool  # True -> RRF order kept because the response failed to parse


def rerank_prompt(question: str, candidates: list[NodeWithScore]) -> str:
    blocks = [
        f"[{i}] (p. {c.node.metadata['page']} | {c.node.metadata.get('section', 'unknown')})\n"
        f"{c.node.text}"
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


def rerank(question: str, candidates: list[NodeWithScore], k: int = TOP_K) -> RerankResult:
    raw = _call(rerank_prompt(question, candidates))
    try:
        order = parse_ranking(raw, k=k, n=len(candidates))
    except RerankParseError as e:
        print(f"rerank fallback — RRF order kept: {e}")
        return RerankResult(chunks=candidates[:k], fallback=True)
    return RerankResult(chunks=[candidates[i - 1] for i in order], fallback=False)


def rerank_retrieve(
    question: str, k: int = TOP_K, embed: str = DEFAULT_EMBED
) -> list[NodeWithScore]:
    return rerank(question, hybrid_candidates(question, embed), k).chunks


if __name__ == "__main__":
    import sys

    question = " ".join(sys.argv[1:]) or "How does high fuel sulphur content affect the oil change interval?"
    for r in rerank_retrieve(question):
        print(f"p.{r.node.metadata['page']:>3}  [{r.node.metadata.get('section', '?')[:40]}]  "
              f"{r.node.text[:70].replace(chr(10), ' ')}")
```

- [ ] **Step 5: Run tests** — `uv run pytest tests/test_rerank.py -v`. Expected: 6 passed.

- [ ] **Step 6: Paid smoke (one Haiku call, cents):**

```bash
uv run python -m src.rerank "How does high fuel sulphur content affect the oil change interval?"
```

Expected: 5 chunks, no fallback message, and the p. 43 sulphur chunk at or near rank 1.

- [ ] **Step 7: Docs + commit.** Add a `rerank.py` section to `docs/documentation/src.md`.

```bash
uv run pytest -q && uv run ruff check src tests eval
git add src/config.py src/rerank.py tests/test_rerank.py docs/documentation/src.md
git commit -m "M3 Task 2: listwise Haiku reranker, RRF-order fallback (D14/D16)" && git push
```

---

### Task 3: Eval retrieval-mode registry + candidate instrumentation

**Files:**
- Modify: `eval/run.py`
- Test: `tests/test_run.py` (extend)
- Modify: `docs/documentation/eval.md` (hook)

**Interfaces:**
- Consumes: `retrieve`, `hybrid_candidates`, `rerank` (Task 2 `RerankResult`), `config.TOP_K`.
- Produces: `run_eval(mode: str = "dense", embed: str = DEFAULT_EMBED) -> dict` with `config_label = f"{mode}-{embed}"`; rows gain `candidates: list[{page, score}] | None` (the 10-deep fused list, D23 instrumentation) and `rerank_fallback: bool`; CLI `--mode dense|hybrid|rerank`. `write_report` prints a fallback-count line when any row fell back.

- [ ] **Step 1: Extend the stub test** in `tests/test_run.py` (append; keep the existing test untouched):

```python
def test_run_eval_hybrid_mode_logs_candidates_and_rerank_flags(monkeypatch, tmp_path):
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
        "rerank",
        lambda q, c, k=5: SimpleNamespace(chunks=c[:2], fallback=True),
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
    row = run["rows"][0]
    assert row["candidates"] == [
        {"page": "43", "score": 0.9},
        {"page": "29", "score": 0.9},
        {"page": "11", "score": 0.9},
    ]
    assert row["rerank_fallback"] is True

    report = run_mod.write_report(run, out_dir=tmp_path)
    assert "fallback" in report.read_text().lower()
```

- [ ] **Step 2: Run to fail** — `uv run pytest tests/test_run.py -v`. Expected: the new test fails (`run_eval() got an unexpected keyword argument 'mode'`).

- [ ] **Step 3: Rework `eval/run.py`.** Replace the imports/`run_eval` head and add the mode registry:

New imports (replace the `from src.retrieve import retrieve` line):

```python
from src.config import DEFAULT_EMBED, EMBED_CONFIGS, GENERATION_MODEL, JUDGE_MODEL, TOP_K
from src.generate import answer_from_chunks, format_context
from src.hybrid import hybrid_candidates
from src.rerank import rerank
from src.retrieve import retrieve
```

Registry (above `run_eval`) — each mode returns `(final_chunks, candidates_or_None, rerank_fallback)`:

```python
def _dense(question: str, embed: str):
    return retrieve(question, embed=embed), None, False


def _hybrid(question: str, embed: str):
    cands = hybrid_candidates(question, embed)
    return cands[:TOP_K], cands, False


def _rerank(question: str, embed: str):
    cands = hybrid_candidates(question, embed)
    result = rerank(question, cands)
    return result.chunks, cands, result.fallback


MODES = {"dense": _dense, "hybrid": _hybrid, "rerank": _rerank}
```

`run_eval` becomes:

```python
def run_eval(mode: str = "dense", embed: str = DEFAULT_EMBED) -> dict:
    rows = []
    for q in load_golden():
        chunks, candidates, fell_back = MODES[mode](q.question, embed)
        context = format_context(chunks)  # as-logged (D17)
        rag = answer_from_chunks(q.question, chunks)
        pages = [c.node.metadata["page"] for c in chunks]
        row = {
            "id": q.id,
            "qtype": q.qtype,
            "question": q.question,
            "expected_pages": q.expected_pages,
            "retrieved_pages": pages,
            # D23 instrumentation: the 10-deep fused candidate list with scores
            "candidates": (
                [{"page": c.node.metadata["page"], "score": round(c.score or 0.0, 4)} for c in candidates]
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
        ...  # judge block unchanged from M2
        rows.append(row)
        print(f"{q.id}: done")
    return {
        "date": datetime.date.today().isoformat(),
        "embed": embed,
        "mode": mode,
        "config_label": f"{mode}-{embed}",
        ...  # models/prompt-version block unchanged
    }
```

(The `...` lines mean: keep the M2 code exactly as it stands in the file — the judge if/else block and the models/version dict tail. Only the shown keys change.)

In `write_report`, after the predicted-fail-ceiling header line, add:

```python
    fallbacks = sum(1 for r in run["rows"] if r.get("rerank_fallback"))
    if fallbacks:
        lines.insert(
            len(lines) - 2,
            f"- Reranker fallbacks: {fallbacks}/{len(run['rows'])} rows used RRF order"
            " (parse failure — D14 graceful degradation).",
        )
```

(Insert it into the `lines` list construction instead if cleaner — the requirement is: the line appears in the header block when any fallback happened.)

CLI dispatch gains `--mode`:

```python
    parser.add_argument("--mode", default="dense", choices=list(MODES))
    ...
    else:
        path = write_report(run_eval(args.mode, args.embed))
        print(f"report: {path}")
```

- [ ] **Step 4: Run tests** — `uv run pytest tests/test_run.py -v`. Expected: both tests pass (the old dense-mode stub test must still pass unchanged — it pins backward compatibility of the row schema; `retrieve` is still monkeypatchable).

- [ ] **Step 5: Docs + commit.** Update `docs/documentation/eval.md`: the "Running it" section gains `--mode dense|hybrid|rerank` and a sentence on candidate logging.

```bash
uv run pytest -q && uv run ruff check src tests eval
git add eval/run.py tests/test_run.py docs/documentation/eval.md
git commit -m "M3 Task 3: eval retrieval-mode registry + 10-deep candidate logging (D23)" && git push
```

---

### Task 4: Measure hybrid, then rerank — two attributable deltas (HUMAN CHECKPOINT)

Ordering is D14-mandated: hybrid **before** rerank, each delta attributable to exactly one change. Baseline JSON `eval/results/2026-07-14-dense-small.json` must exist locally (it is gitignored; if missing, the baseline must be re-run and re-blessed first — stop and say so rather than comparing against nothing).

- [ ] **Step 1: Hybrid run (~$1: 12 generations + ~23 judge calls):**

```bash
uv run python -m eval.run --mode hybrid --embed small
```

Sanity: q1 still hits p. 43 rank 1; q5's p. 43 should rise (BM25 loves "sulphur"); the trap must still be refused.

- [ ] **Step 2: Compare dense→hybrid:**

```bash
uv run python -m eval.run --compare eval/results/2026-07-14-dense-small.json eval/results/$(date +%F)-hybrid-small.json
```

Read against D23: expected movement on q5 RR; q10/q11 expected unchanged at 1.00 (saturated); hit@5 expected unchanged 10/11 (q8 unfixable). Count TOC-magnet appearances:

```bash
uv run python -c "
import json, sys
for path in sys.argv[1:]:
    run = json.load(open(path))
    toc = sum(1 for r in run['rows'] if '5' in r['retrieved_pages'])
    print(run['config_label'], 'rows with TOC p.5 in top-5:', toc)
" eval/results/2026-07-14-dense-small.json eval/results/$(date +%F)-hybrid-small.json
```

- [ ] **Step 3: Rerank run (~$1 + 12 Haiku calls):**

```bash
uv run python -m eval.run --mode rerank --embed small
uv run python -m eval.run --compare eval/results/$(date +%F)-hybrid-small.json eval/results/$(date +%F)-rerank-small.json
```

Also check the report header for a fallback line — any fallback rows weaken the rerank delta's attributability and must be named in the analysis. Re-run the TOC count including the rerank JSON (the reranker demoting p. 5 is a pre-committed D23 expectation).

- [ ] **Step 4: D16 swap trigger (conditional — only if rerank hit+MRR ≤ hybrid).** One string, re-measure, keep both runs:

```bash
# in src/config.py: RERANK_MODEL = "claude-sonnet-5"
mkdir -p eval/results/superseded
mv eval/results/$(date +%F)-rerank-small.json eval/results/$(date +%F)-rerank-small.md eval/results/superseded/  # label collision: write_report refuses same-day overwrite
uv run python -m eval.run --mode rerank --embed small
uv run python -m eval.run --compare eval/results/$(date +%F)-hybrid-small.json eval/results/$(date +%F)-rerank-small.json
```

Both outcomes are recordable findings: "Sonnet rescues the delta" (log the swap as a decision) or "reranking adds nothing at this corpus size" (revert `RERANK_MODEL` to Haiku, keep the null result in the report — an honest null was pre-committed in D23). Either way `docs/decisions.md` gets the outcome under a new D-number via the decision-logging skill.

- [ ] **Step 5: Append `## M3 vs baseline` to the rerank report** (`eval/results/<date>-rerank-small.md`): the two compare tables (dense→hybrid, hybrid→rerank), the TOC-magnet counts per config, fallback count, and the D23 predictions checked one by one (q5/q7 MRR movement, q10/q11 unchanged, hit@5 unchanged, TOC demotion). State plainly which predictions held and which didn't.

- [ ] **Step 6 (do not skip): HUMAN CHECKPOINT.** Present both deltas with per-question movements, the TOC counts, any fallbacks, the swap-trigger outcome if fired, and the honest verdict sentence ("hybrid moved X, reranking moved Y — attributable readout hit/MRR only"). The user blesses before commit.

- [ ] **Step 7: Commit the blessed M3 measurement:**

```bash
git add eval/results/*.md docs/decisions.md src/config.py
git commit -m "M3 Task 4: hybrid + rerank measured against dense baseline - attributable deltas (D12/D13/D14)" && git push
```

(`src/config.py` only if the swap fired; if it's in the commit the hook wants `docs/documentation/src.md` — update its config section accordingly.)

---

### Task 5: M3 wrap-up — docs, README, lint, final commit

- [ ] **Step 1:** `docs/documentation/eval.md`: add an "M3 configs" note to the A/B section — three comparable configs exist (`dense`/`hybrid`/`rerank`), compare pairs share the tier, hit/MRR remain the attributable readout.
- [ ] **Step 2:** `README.md`: add the two new CLI lines to Quickstart:

```bash
uv run python -m src.hybrid "your question"     # fused dense+BM25 candidates
uv run python -m src.rerank "your question"     # reranked top-5 (one Haiku call)
uv run python -m eval.run --mode rerank --embed small
```

Also bump the decision-log range in the Documentation section (D1–D23 → current max).
- [ ] **Step 3:** `uv run ruff check src tests eval && uv run ruff format --check src tests eval` — fix findings (format-only reflows may be committed with `--no-verify` per the update-docs skill's no-doc-impact rule, stated in the commit message).
- [ ] **Step 4:** `uv run pytest -q` — all pass (~38 tests).
- [ ] **Step 5:** Final commit:

```bash
git add README.md docs/documentation/eval.md
git commit -m "M3 complete: hybrid BM25+RRF retrieval and listwise reranking, measured" && git push
```

Report to the user: the three-config table (dense/hybrid/rerank), which D23 predictions held, the swap-trigger outcome, and the observations that feed the M4 plan (FastAPI serving: BM25 startup rebuild per D12, engine-per-query F2) and M5 (caption pages 42/48/49/50/51).

---

## Out of scope for this plan

- **M4** FastAPI `POST /query` (+ F2 engine-per-query; D12's startup rebuild becomes an API concern there).
- **M5** vision captioning (q8/q9's fix; caption nodes must carry pages 42/48/49/50/51).
- Overlap-aware dedup (watch-item: trigger only if a duplicate overlap-twin eats >1 top-5 slot in the M3 runs).
- Positional-bias mitigation for the listwise reranker (D14 accepted limitation).

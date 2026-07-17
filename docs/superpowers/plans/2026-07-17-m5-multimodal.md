# M5 Multimodal (Vision Captioning) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Caption the manual's five image-bound pages (p. 42 SAE chart, p. 48 maintenance schedule, pp. 49–51 troubleshooting table) with Claude vision, index the captions as first-class chunks, and measure the text-only → multimodal delta against the blessed rerank-small record.

**Architecture:** A new `src/multimodal.py` step that runs AFTER `src.ingest`: it vision-captions each image-bound page (cached as inspectable files under `data/captions/`), builds caption TextNodes with deterministic IDs and the exact `{page, section}` metadata shape `store.load_nodes` reconstructs, deletes p. 48's shredded text chunks (replacement, not coexistence), and inserts the captions into the existing pgvector table. The eval harness gains a `--label` so the multimodal run is distinguishable from the text-only M3 run.

**Tech Stack:** anthropic SDK (Sonnet 5 vision, per D16), pymupdf (page → PNG rendering), existing LlamaIndex + pgvector pipeline.

## Global Constraints

- Python 3.12, `uv` for everything; lint `ruff check` + `ruff format`; tests `uv run pytest`.
- Golden set is FROZEN (D17): no question, expected-page set, or golden answer changes. Annotation amendments only, authorized by a decision-log entry (D23 precedent).
- Never commit: `.env`, anything under `data/` (including the new `data/captions/`), `docs/*.private.md`, `eval/results/*.json`.
- Pre-commit hook: commits touching `src|eval|api` need that area's `docs/documentation/*.md` staged (or `--no-verify` with justification for verified no-doc-impact).
- Concurrent sessions may run in this repo: check `git status --short` before every commit; stage only files this plan touches; never `git add -A`.
- D20: caption text/metadata must embed `section` but never `page`. D12: caption nodes must round-trip byte-identically through `store.load_nodes` (node.hash = text + metadata).
- Models per D16: captioning = `claude-sonnet-5`. No temperature parameter on Sonnet 5.
- Current measured state: 74 index rows (p. 42: 1 chunk, p. 48: 2 shredded chunks, p. 49: 1 prose chunk, pp. 50/51: 0). Post-M5 expectation: 74 − 2 + 5 = **77 rows**.

## Design decisions this plan encodes (log as D25/D26 in Task 5)

1. **D25 — caption scope + replacement.** Caption pages 42, 48, 49, 50, 51. F5 names only the chart; D19 extended to pp. 50–51; q8's answer row is on the p. 49 image; M3 measured q7's grounded-fail caused by the shredded p. 48 text. p. 48's 2 text chunks are **deleted** when its caption lands (M3 rerank q7: the shredded chunk at rank 1 lured a partial ungrounded answer — its information content is measured-negative). Pages 42/49 keep their genuine prose; 50/51 have no rows.
2. **D26 — caption pipeline mechanics.** One caption node per page image; captions cached as inspectable files in `data/captions/` (N1: the caption is the new grounding root and must be human-auditable; N3: re-runs are byte-stable so eval numbers don't wobble with vision sampling); deterministic node IDs (uuid5 of the page) so re-runs replace instead of duplicate; pp. 50/51 captions receive the p. 49 image as extra context (continuation pages may lack the table's column headers); caption nodes carry exactly `{page, section}` + `excluded_embed_metadata_keys=["page"]` — the precise shape `load_nodes` rebuilds, preserving node.hash across restarts (D12 RRF dedup; per llama-index-core `TextNode.hash = sha256(text + str(metadata))` — id, templates, and the exclusion list do NOT enter the hash, so the invariant rides on text + the pinned `{page, section}` insertion order).

**Section labels use the pipeline's normalized heading vocabulary** (ingrid review): `textprep.detect_heading` strips trailing dots and normalizes separators, so the live index says `5.4 Lubrication Oil`, `5.11 General Maintenance Schedule`, `6 TROUBLESHOOTING` — PAGE_SPECS must use these forms, never the manual's raw spellings (`5.11. General…`, `6-TROUBLESHOOTING`), or p. 42/49 would cite one section under two spellings and embed near-duplicate label tokens.

**Pre-registered contingency (name in D25):** if q8 (or q7) misses top-5 under page-level captions, the remedy is per-unit caption splitting — one node per problem for pp. 49–51, per system-group for p. 48 — the direct descendant of D9's retired "one block per problem" trigger. Naming it now makes a post-measurement split a pre-registered move, not improvisation. Prompt iteration is legitimate only BEFORE Task 7 measures.

**Known limitation (state in D26, do not hide):** the judge verifies answer-vs-caption, never caption-vs-image. Caption fidelity is secured by the Task 6 manual audit (each caption read against its image), not by the harness.

## Pre-committed expectations (freeze BEFORE Task 7 measures; D23 discipline)

| Question | Expectation | Why |
|---|---|---|
| q7 (p. 48) | hit stays 1 — **now a genuine prediction, not a carryover** (the blessed hit rode the two shredded chunks at ranks 1–2, which M5 deletes; the caption must be retrievable on its own) — and **grounded + correct now pass** | caption restores task↔interval associations and replaces the noise that caused the M3 grounded-fail |
| q8 (p. 49) | **hit + correct now pass** (was the sole retrieval miss) | the slow-crank row becomes retrievable text for the first time |
| q9 (p. 42) | **correct now passes**; retrieval stays saturated (p. 42 already rank 1) | the −30 °C → SAE grade mapping becomes visible to generation |
| q1–q6, q10, q11 | no regression (all currently RR 1.00) | +5 nodes shift BM25 IDF and dense competition — any regression is a real finding to report, not noise to dismiss |
| q12 trap | still refuses | captions must introduce no torque value (checked in the Task 6 audit) |
| Aggregates | hit@5 11/11 · MRR ≈ 1.00 · grounded 11/11 · correct 11/11 | any shortfall is a finding to explain in the report, never to hide |

Changed judge verdicts vs the blessed record get the pre-registered 3× fresh re-judge spot-check (M3 protocol).

---

### Task 1: Eval corpus label (`--label`)

The M5 run is mode `rerank`, embed `small` — same as M3. Without a label, `config_label` would collide conceptually ("rerank-small" on two different corpora). Add an explicit corpus-state tag.

**Files:**
- Modify: `eval/run.py`
- Test: `tests/test_run.py`

**Interfaces:**
- Produces: `config_label(mode: str, embed: str, label: str | None = None) -> str`; `run_eval(mode, embed, label=None)`; CLI `--label`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_run.py`, matching its existing style — read the file first and place near its other pure-function tests):

```python
def test_config_label_appends_corpus_tag():
    # the M5 corpus-state tag: same mode+embed on a different corpus must
    # not produce a colliding run identity
    assert config_label("rerank", "small") == "rerank-small"
    assert config_label("rerank", "small", "mm") == "rerank-small-mm"
```

Add `config_label` to the file's existing `from eval.run import ...` import line.

- [ ] **Step 2: Run it — expect FAIL** (`ImportError: cannot import name 'config_label'`):

```bash
uv run pytest tests/test_run.py -q
```

- [ ] **Step 3: Implement.** In `eval/run.py`, add above `run_eval`:

```python
def config_label(mode: str, embed: str, label: str | None = None) -> str:
    """Run identity (D17): a corpus-state label (e.g. 'mm' after
    src.multimodal) keeps two runs of the same mode+embed distinguishable."""
    return "-".join(filter(None, [mode, embed, label]))
```

Change `run_eval` signature to `def run_eval(mode: str = "dense", embed: str = DEFAULT_EMBED, label: str | None = None) -> dict:` and the dict line to `"config_label": config_label(mode, embed, label),`. In `__main__`, add `parser.add_argument("--label", default=None, help="corpus-state tag appended to config_label (e.g. mm)")` and change the final call to `write_report(run_eval(args.mode, args.embed, args.label))`.

- [ ] **Step 4: Run tests — expect PASS:** `uv run pytest tests/test_run.py -q`
- [ ] **Step 5: Update `docs/documentation/eval.md`** (one line in the how-to-run section explaining `--label`; bump the stamp) and commit:

```bash
git status --short   # stage ONLY these files
git add eval/run.py tests/test_run.py docs/documentation/eval.md
git commit -m "Add --label corpus-state tag to eval run identity (M5 prep)"
```

---

### Task 2: Caption engine (`src/multimodal.py` part 1)

**Files:**
- Modify: `pyproject.toml` (add `pymupdf` dependency), `src/config.py` (add `CAPTION_MODEL`)
- Create: `src/multimodal.py`
- Test: `tests/test_multimodal.py` (create)

**Interfaces:**
- Produces: `PAGE_SPECS: dict[str, dict]` (keys "42","48","49","50","51"; values with `section`, `context_pages`, `prompt`); `caption_page(client: anthropic.Anthropic, page: str) -> str`; module globals `CAPTIONS_DIR: Path`, `_page_image(page: str) -> bytes`.

- [ ] **Step 1: Add the dependency and config constant:**

```bash
uv add pymupdf
```

In `src/config.py`, below `RERANK_MODEL`:

```python
CAPTION_MODEL = "claude-sonnet-5"  # D16: the F5 vision caption shares generation's tier
```

- [ ] **Step 2: Write the failing tests** — create `tests/test_multimodal.py`:

```python
from unittest.mock import MagicMock

import pytest

import src.multimodal as mm


def _vision_response(text=" caption ", stop_reason="end_turn"):
    block = MagicMock(type="text", text=text)
    return MagicMock(stop_reason=stop_reason, content=[block])


def test_caption_cache_hit_skips_vision_call(tmp_path, monkeypatch):
    # D26/N3: cached captions are byte-stable — no paid call, no sampling wobble
    monkeypatch.setattr(mm, "CAPTIONS_DIR", tmp_path)
    (tmp_path / "p42.md").write_text("cached caption")
    client = MagicMock()
    assert mm.caption_page(client, "42") == "cached caption"
    client.messages.create.assert_not_called()


def test_caption_cache_miss_calls_vision_and_writes_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(mm, "CAPTIONS_DIR", tmp_path)
    monkeypatch.setattr(mm, "_page_image", lambda page: b"png-bytes")
    client = MagicMock()
    client.messages.create.return_value = _vision_response()
    assert mm.caption_page(client, "42") == "caption"
    assert (tmp_path / "p42.md").read_text() == "caption"


def test_truncated_or_empty_caption_raises_and_caches_nothing(tmp_path, monkeypatch):
    # loud failure, mirroring generate's D15 guard: a silently truncated
    # caption would become a silently incomplete grounding root
    monkeypatch.setattr(mm, "CAPTIONS_DIR", tmp_path)
    monkeypatch.setattr(mm, "_page_image", lambda page: b"png-bytes")
    client = MagicMock()
    client.messages.create.return_value = _vision_response(stop_reason="max_tokens")
    with pytest.raises(RuntimeError, match="caption incomplete"):
        mm.caption_page(client, "42")
    client.messages.create.return_value = _vision_response(text="   ")
    with pytest.raises(RuntimeError, match="caption incomplete"):
        mm.caption_page(client, "42")
    assert not (tmp_path / "p42.md").exists()


def test_page_specs_cover_the_five_image_bound_pages():
    # D25 scope; 50/51 ship the p. 49 image for column-header context
    assert set(mm.PAGE_SPECS) == {"42", "48", "49", "50", "51"}
    assert mm.PAGE_SPECS["50"]["context_pages"] == ["49"]
    assert mm.PAGE_SPECS["51"]["context_pages"] == ["49"]
```

- [ ] **Step 3: Run — expect FAIL** (`ModuleNotFoundError: src.multimodal`): `uv run pytest tests/test_multimodal.py -q`

- [ ] **Step 4: Create `src/multimodal.py`:**

```python
"""F5 multimodal (D6/D19/D25/D26): caption image-bound pages with Claude
vision and index the captions as first-class chunks.

Five pages hold answers no text extraction can reach (p. 42 SAE chart,
p. 48 maintenance schedule, pp. 49-51 troubleshooting table). Each gets ONE
caption node: a structured vision transcription, cached as an inspectable
file under data/captions/ (the caption is the new grounding root, so it must
be human-auditable (N1) and byte-stable across runs (N3)). Runs AFTER
src.ingest — D18's drop-and-rebuild wipes captions, so re-ingest implies
re-running this module, then restarting the API (D12 BM25 rebuild).
"""

import sys
import uuid
from base64 import standard_b64encode

import anthropic
import pymupdf
from llama_index.core import VectorStoreIndex
from llama_index.core.schema import TextNode

from src.config import CAPTION_MODEL, DEFAULT_EMBED, PDF_PATH
from src.store import (
    delete_by_node_ids,
    delete_by_page,
    embedder,
    get_vector_store,
    verify_store,
)

CAPTIONS_DIR = PDF_PATH.parent / "captions"
CHART_PNG = PDF_PATH.parent / "oil_viscosity_chart.png"

# D26: deterministic caption identity — re-runs replace, never duplicate
_CAPTION_NS = uuid.uuid5(uuid.NAMESPACE_URL, "rag-technical-manual/caption")

CAPTION_SYSTEM = (
    "You transcribe figures and tables from a diesel-generator O&M manual "
    "into complete, structured plain text for a retrieval index. "
    "Faithfulness over fluency: transcribe exactly what the image shows, "
    "completely, and nothing it does not show."
)

_TABLE_RULES = (
    "Transcribe the table completely into structured plain text, preserving "
    "every row-to-column association exactly as drawn. Transcribe only what "
    "is visible in the image - never add outside knowledge. "
)

# D25: the five image-bound pages. section = citation label + D20-embedded
# topical signal; context_pages ship an extra image whose column headers the
# continuation page lacks.
PAGE_SPECS: dict[str, dict] = {
    "42": {
        # normalized heading vocabulary (detect_heading output), NOT the
        # manual's raw spelling — must match the live index's label forms
        "section": "5.4 Lubrication Oil",
        "context_pages": [],
        "prompt": (
            "This chart maps SAE engine-oil viscosity grades to the ambient "
            "temperature ranges they cover. For EACH grade shown, write one "
            "line stating the grade and its exact lower and upper ambient "
            "temperature bounds in degrees Celsius as drawn in the chart. "
            "Transcribe only what is visible - do not add grades or bounds "
            "from outside knowledge."
        ),
    },
    "48": {
        "section": "5.11 General Maintenance Schedule",
        "context_pages": [],
        "prompt": (
            "This is the generator set's general maintenance schedule: rows "
            "are maintenance tasks grouped by system, columns are service "
            "intervals. This caption will be the page's ONLY representation "
            "in the index, so transcribe the ENTIRE page: the title, any "
            "legend or key explaining the cell markings, and any notes or "
            "footnotes, then the table. " + _TABLE_RULES + "For EACH task, "
            "write one line: the task, then every interval column marked "
            "for it."
        ),
    },
    "49": {
        "section": "6 TROUBLESHOOTING",
        "context_pages": [],
        "prompt": (
            "This page contains the start of the engine troubleshooting "
            "table, associating problems with their possible causes and "
            "remedies. " + _TABLE_RULES + "For EACH problem shown on this "
            "page, write the problem as a heading followed by the complete "
            "list of its possible causes and, where shown, remedies."
        ),
    },
    "50": {
        "section": "6 TROUBLESHOOTING",
        "context_pages": ["49"],
        "prompt": (
            "The FIRST image is the previous page of the troubleshooting "
            "table (use it only for the table structure and column "
            "headers). The SECOND image is the page to transcribe. "
            + _TABLE_RULES
            + "Transcribe ONLY the second image: for each problem, write it "
            "as a heading followed by the complete list of its possible "
            "causes and, where shown, remedies."
        ),
    },
    "51": {
        "section": "6 TROUBLESHOOTING",
        "context_pages": ["49"],
        "prompt": (
            "The FIRST image is an earlier page of the troubleshooting "
            "table (use it only for the table structure and column "
            "headers). The SECOND image is the page to transcribe. "
            + _TABLE_RULES
            + "Transcribe ONLY the second image: for each problem, write it "
            "as a heading followed by the complete list of its possible "
            "causes and, where shown, remedies."
        ),
    },
}


def _render_page(page: str) -> bytes:
    with pymupdf.open(PDF_PATH) as doc:
        # D9-verified: printed page labels equal 1-based PDF indices
        return doc[int(page) - 1].get_pixmap(matrix=pymupdf.Matrix(2, 2)).tobytes("png")


def _page_image(page: str) -> bytes:
    # F5 names the chart asset explicitly; every other page is rendered whole
    return CHART_PNG.read_bytes() if page == "42" else _render_page(page)


def _image_block(png: bytes) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": standard_b64encode(png).decode(),
        },
    }


def caption_page(client: anthropic.Anthropic, page: str) -> str:
    """Vision-caption one page; cached as an inspectable file (D26)."""
    cache = CAPTIONS_DIR / f"p{page}.md"
    if cache.exists():
        return cache.read_text()
    spec = PAGE_SPECS[page]
    blocks = [_image_block(_page_image(p)) for p in [*spec["context_pages"], page]]
    # Sonnet 5: thinking omitted = adaptive, sharing max_tokens — budget for
    # a dense table transcription plus thinking, and fail loudly on truncation
    response = client.messages.create(
        model=CAPTION_MODEL,
        max_tokens=8000,
        system=CAPTION_SYSTEM,
        messages=[
            {"role": "user", "content": [*blocks, {"type": "text", "text": spec["prompt"]}]}
        ],
    )
    text = next((b.text for b in response.content if b.type == "text"), "").strip()
    if response.stop_reason == "max_tokens" or not text:
        raise RuntimeError(
            f"caption incomplete for p. {page}: stop_reason={response.stop_reason!r}, "
            f"text_chars={len(text)}"
        )
    CAPTIONS_DIR.mkdir(exist_ok=True)
    cache.write_text(text)
    return text
```

(`sys`, `TextNode`, `VectorStoreIndex`, and the store imports are used by Tasks 3–4; if `ruff check` flags them as unused at this step, that is expected — either proceed straight to Task 3 before committing, or add them in Task 3.)

Note: `delete_by_node_ids` / `delete_by_page` do not exist in `src/store.py` yet — Task 4 adds them. For THIS task's tests to run, comment out that import line and the three store imports it accompanies is NOT allowed (no placeholder debt); instead, do Task 4's Step 1 (the two store functions) first if the import error blocks you, or write the file complete and accept that only Task 4 runs the full suite. Recommended order if executing strictly stepwise: add the store functions (Task 4 Step 1) immediately after this step.

- [ ] **Step 5: Run — expect the four Task 2 tests PASS:** `uv run pytest tests/test_multimodal.py -q` (commit happens after Task 4, when the module is whole)

---

### Task 3: Caption nodes (`src/multimodal.py` part 2)

**Files:**
- Modify: `src/multimodal.py`
- Test: `tests/test_multimodal.py`

**Interfaces:**
- Produces: `caption_node_id(page: str) -> str`; `build_node(page: str, caption: str) -> TextNode`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_multimodal.py`; extend the imports with `from llama_index.core.schema import MetadataMode, TextNode`):

```python
def test_caption_node_id_deterministic_and_page_scoped():
    # D26: re-running src.multimodal must REPLACE captions, never duplicate
    assert mm.caption_node_id("42") == mm.caption_node_id("42")
    assert mm.caption_node_id("42") != mm.caption_node_id("48")


def test_caption_node_round_trips_through_load_nodes_reconstruction():
    # D12: RRF dedups by node.hash — a caption node rebuilt from Postgres by
    # store.load_nodes must hash identically to the inserted original
    node = mm.build_node("42", "SAE grades by ambient temperature range")
    rebuilt = TextNode(
        id_=node.node_id,
        text=node.text,
        metadata={"page": node.metadata["page"], "section": node.metadata["section"]},
    )
    rebuilt.excluded_embed_metadata_keys = ["page"]
    assert rebuilt.hash == node.hash


def test_caption_node_embeds_section_but_not_page():
    # D20: BM25 tokenizes EMBED-mode content; page numbers are noise tokens
    node = mm.build_node("48", "maintenance schedule transcription")
    embed_text = node.get_content(metadata_mode=MetadataMode.EMBED)
    # the NORMALIZED label form (detect_heading vocabulary) — the raw
    # manual spelling "5.11. General…" must never enter the index
    assert "5.11 General Maintenance Schedule" in embed_text
    assert "48" not in embed_text
```

- [ ] **Step 2: Run — expect FAIL** (`AttributeError: ... 'caption_node_id'`): `uv run pytest tests/test_multimodal.py -q`

- [ ] **Step 3: Implement** — add to `src/multimodal.py` below `caption_page`:

```python
def caption_node_id(page: str) -> str:
    return str(uuid.uuid5(_CAPTION_NS, page))


def build_node(page: str, caption: str) -> TextNode:
    node = TextNode(
        id_=caption_node_id(page),
        text=caption,
        metadata={"page": page, "section": PAGE_SPECS[page]["section"]},
    )
    # exactly the shape store.load_nodes reconstructs — any extra metadata
    # key would change node.hash (sha256 of text + str(metadata)) after a
    # process restart and silently break the D12 RRF dedup invariant. The
    # exclusion list does NOT enter the hash — it matters at insert time
    # (embedding text) and load_nodes re-pins it for BM25 independently.
    node.excluded_embed_metadata_keys = ["page"]
    return node
```

- [ ] **Step 4: Run — expect PASS:** `uv run pytest tests/test_multimodal.py -q`

---

### Task 4: Store deletions + orchestration (`store.py` + `multimodal.run()`)

The two delete helpers live in `store.py` (the single DB-access module). They carry no unit tests, consistent with the rest of `store.py` — they are integration-verified by `run()`'s row-count arithmetic (74 → 77) in Task 6.

**Files:**
- Modify: `src/store.py`, `src/multimodal.py`, `docs/documentation/src.md`

**Interfaces:**
- Consumes: `caption_page`, `build_node` (Tasks 2–3).
- Produces: `store.delete_by_page(page: str, embed: str = DEFAULT_EMBED) -> int`; `store.delete_by_node_ids(node_ids: list[str], embed: str = DEFAULT_EMBED) -> int`; `multimodal.run(embed: str = DEFAULT_EMBED) -> None`; CLI `uv run python -m src.multimodal`.

- [ ] **Step 1: Add to `src/store.py`** (below `verify_store`):

```python
def delete_by_page(page: str, embed: str = DEFAULT_EMBED) -> int:
    """D25: remove one page's rows (shredded-extraction replacement)."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(f'DELETE FROM "{full_table(embed)}" WHERE metadata_->>%s = %s', ("page", page))
        return cur.rowcount


def delete_by_node_ids(node_ids: list[str], embed: str = DEFAULT_EMBED) -> int:
    """D26: idempotent caption replacement — delete by deterministic id."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(f'DELETE FROM "{full_table(embed)}" WHERE node_id = ANY(%s)', (node_ids,))
        return cur.rowcount
```

- [ ] **Step 2: Add `run()` + CLI to `src/multimodal.py`** (bottom of file):

```python
def run(embed: str = DEFAULT_EMBED) -> None:
    client = anthropic.Anthropic()
    nodes = []
    for page in PAGE_SPECS:
        caption = caption_page(client, page)
        nodes.append(build_node(page, caption))
        print(f"p. {page}: caption {len(caption)} chars")

    before, _ = verify_store(embed)
    # D25: p. 48's extracted text is shredded noise the caption REPLACES —
    # M3 measured it luring a partial ungrounded answer (rerank q7). On a
    # re-run this also removes the old p. 48 caption; delete_by_node_ids
    # then clears the remaining stale captions. Both run before insert, so
    # the step is idempotent.
    dropped = delete_by_page("48", embed)
    stale = delete_by_node_ids([n.node_id for n in nodes], embed)
    VectorStoreIndex.from_vector_store(
        get_vector_store(embed), embed_model=embedder(embed)
    ).insert_nodes(nodes)

    after, ann = verify_store(embed)
    expected = before - dropped - stale + len(nodes)
    print(
        f"rows: {before} -> {after} (removed {dropped} p. 48 rows + "
        f"{stale} stale captions, inserted {len(nodes)} captions)"
    )
    if after != expected:
        raise RuntimeError(f"row count {after} != expected {expected}")
    if ann:
        raise RuntimeError(f"unexpected ANN index: {ann} (violates D11)")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMBED)
```

- [ ] **Step 3: Full suite + lint — expect all green:**

```bash
uv run pytest -q && uv run ruff check && uv run ruff format --check
```

- [ ] **Step 4: Update `docs/documentation/src.md`:** add a `multimodal.py` section (responsibility, caption cache, replacement semantics, decision IDs D25/D26), extend the `store.py` section with the two delete helpers, note `CAPTION_MODEL` under config, bump the stamp.

- [ ] **Step 5: Verify `data/captions/` is gitignore-covered** (`git check-ignore -v data/captions/x` — the existing `data/` rule should cover it; if not, add `data/captions/` to `.gitignore`), then commit:

```bash
git status --short   # stage ONLY files this plan touches
git add pyproject.toml uv.lock src/config.py src/multimodal.py src/store.py tests/test_multimodal.py docs/documentation/src.md
git commit -m "Add M5 vision-caption module: cached captions, deterministic node IDs, p.48 replacement (D25/D26)"
```

---

### Task 5: Freeze the measurement frame (annotations + decision log)

Do this BEFORE any measurement (D23 discipline: expectations must predate the numbers).

**Files:**
- Modify: `eval/golden.json` (annotations ONLY), `docs/decisions.md`

- [ ] **Step 1: Amend the three annotations in `eval/golden.json`** (nothing else changes; note: the report's predicted-fail counter matches the literal substring `"predicted fail"` — the new texts deliberately use the hyphenated form only, so the ceiling line correctly reports 11/11 achievable post-M5):

q7 → `"pre-M5 predicted-fail (D9: the p. 48 schedule table extracts shredded, task-to-interval associations lost); M5 replaced the p. 48 text with a vision caption (D25) — pre-committed: grounded + correct expected"`

q8 → `"pre-M5 predicted-fail (D19: troubleshooting table image-only; this row on the p. 49 image, table continues on pp. 50-51); M5 captions pp. 49-51 (D25) — pre-committed (D23): hit + correct expected"`

q9 → `"pre-M5 predicted-fail (D6: answer only in the SAE chart image on p. 42); M5 captions the chart (D25) — pre-committed (D23): correct expected; retrieval already saturated (p. 42 at rank 1)"`

- [ ] **Step 2: Run `uv run pytest tests/test_golden.py -q`.** If a test pins the old annotation texts, that test IS the freeze mechanism — update it in the same commit, citing D25 as the authorizing entry (D23 precedent: annotation amendments go through the log).

- [ ] **Step 3: Append D25 and D26 to `docs/decisions.md`** (decision-logging format; content = the two "Design decisions this plan encodes" entries above, with the considered-and-rejected alternatives: D25 rejected *chart-only strict-F5 scope* — leaves measured q7/q8 failures standing when the identical mechanism fixes them — and *coexistence for p. 48* — M3 measured the shredded text's information content as negative; D26 rejected *no caption cache* — vision re-sampling would change node text, node.hash, and eval numbers on every run — and *one merged caption for the 49–51 table* — page-attributed nodes are what D17's expected-page sets score. D25 additionally names: the pre-registered miss contingency (per-unit caption splitting, descendant of D9's retired trigger) and the note that the **`large` embed table stays text-only after M5** — any future `--embed large` run compares across different corpora until re-ingested + re-captioned. D26 carries the known limitation: judge verifies answer-vs-caption, not caption-vs-image; manual audit is the mitigation.)

- [ ] **Step 4: Commit** (golden.json is under `eval/` → hook wants `docs/documentation/eval.md`; the annotation change is doc-visible only if eval.md quotes annotations — check; if untouched, `--no-verify` with justification):

```bash
git add eval/golden.json docs/decisions.md tests/test_golden.py   # test only if changed
git commit -m "Freeze M5 measurement frame: amend q7-q9 annotations, log D25/D26"
```

(append `--no-verify` + justification line in the message if eval.md needed no edit)

---

### Task 6: Execute captioning + caption audit (paid: 5 vision calls)

- [ ] **Step 1: Run it:** `uv run python -m src.multimodal` — expect five `p. NN: caption ...` lines and `rows: 74 -> 77 (removed 2 p. 48 rows + 0 stale captions, inserted 5 captions)`, no exception.
- [ ] **Step 2: AUDIT each caption against its image** (the caption is the new grounding root; this is the only caption-vs-image check that exists). Read `data/oil_viscosity_chart.png` and render pp. 48–51 to files for viewing:

```bash
uv run python -c "
import pymupdf
from src.config import PDF_PATH
doc = pymupdf.open(PDF_PATH)
for p in (48, 49, 50, 51):
    doc[p-1].get_pixmap(matrix=pymupdf.Matrix(2,2)).save(f'data/captions/render_p{p}.png')
print('rendered')"
```

Then read each image alongside `data/captions/p*.md` and verify: (a) p. 42 — every SAE grade's bounds match the chart, especially that exactly one grade covers −30 °C (q9's golden: 5W/30; 10W/30 stops at −25; 15W/40 at −15); (b) p. 48 — V-belt tension row maps to start-up + 200 hours + every year (q7's golden), **and the page's title, legend/key, and any footnotes present in the image are present in the caption** (replacement makes it the page's sole representation); (c) p. 49 — the "engine turns slow but does not start" column lists the causes in q8's golden; (d) pp. 50/51 — transcriptions attribute only content actually on those pages; (e) **NO caption anywhere contains a torque value** (q12 trap integrity). Fix caption errors by deleting the bad cache file, improving the prompt, and re-running — prompt iteration BEFORE measurement is legitimate; after Task 7 it is not.
- [ ] **Step 2b: Label-vocabulary check** — one query confirming caption rows use the normalized heading forms present on the coexisting chunks (pp. 42/49; e.g. `SELECT metadata_->>'section' FROM ... WHERE node_id = ANY(<caption ids>)` and eyeball against the page-42/49 chunk labels).
- [ ] **Step 3: Idempotency check:** run `uv run python -m src.multimodal` again — expect `rows: 77 -> 77 (removed 1 p. 48 rows + 4 stale captions, inserted 5 captions)` (the p. 48 caption falls to the page delete; on re-runs the printed split shifts between the two delete counters — the invariant is the total).

---

### Task 7: Measure (paid: ~1 eval run) — full process restart semantics apply (D12: fresh process rebuilds BM25 including captions)

- [ ] **Step 1:** `uv run python -m eval.run --mode rerank --embed small --label mm` → writes `eval/results/2026-07-17-rerank-small-mm.{json,md}`.
- [ ] **Step 2:** `uv run python -m eval.run --compare eval/results/2026-07-14-rerank-small.json eval/results/2026-07-17-rerank-small-mm.json` — the text-only vs multimodal A/B (attributable readout: hit/MRR; grounded/correct deltas carry generation + judge noise, per the harness's own caveat — but for q7/q8/q9 the corpus change IS the treatment, so their correctness flips are the measured M5 effect; say it exactly that way).
- [ ] **Step 3:** Check every pre-committed expectation from the table above against the per-question rows. **q8's hit must be verified by identity, not page**: confirm via the logged `candidates[].node_id` that the hitting chunk is `caption_node_id("49")` — the coexisting p. 49 prose chunk could satisfy a page-level hit spuriously. Changed judge verdicts vs the blessed record → 3× fresh re-judge spot-check (M3 protocol) via a small script against the logged JSON (same pattern as M3's; judge the logged answer+context 3×, unanimity required).
- [ ] **Step 4:** Extend `2026-07-17-rerank-small-mm.md` with an "M5 vs M3 (text-only → multimodal)" section mirroring the M3 report's comparison structure: per-question deltas, pre-committed-expectations checklist (held / not held), any regression analyzed honestly, the trap outcome, the caption-grounding limitation restated, and one line acknowledging the now-vestigial predicted-fail counter wording (the header's "(D9/D19/D6)" citation next to 0 predicted-fail rows).
- [ ] **Step 5: Live API smoke** (the project's closing demo): start `uv run uvicorn api.main:app` (fresh process → BM25 includes captions), then

```bash
curl -s -X POST http://127.0.0.1:8000/query -H "Content-Type: application/json" \
  -d '{"question": "Which SAE oil grade should be used at an ambient temperature of -30°C?"}' | python3 -m json.tool
```

Expect: an answer naming SAE 5W/30 with p. 42 in sources, `rerank_degraded: false`. Then kill the server (`lsof -ti :8000 | xargs -r kill`).
- [ ] **Step 6: Commit** the report (`.md` only — `.json` is gitignored) + any eval.md touch-ups:

```bash
git add eval/results/2026-07-17-rerank-small-mm.md
git commit -m "M5 measured: multimodal captions vs text-only rerank baseline" # --no-verify only if eval.md genuinely unaffected; justify in message
```

---

### Task 8: Results review, bless, finish

- [ ] **Step 1:** yuki-eval reviews the M5 report + comparison (agent review, FIX-THEN-BLESS: apply must-fix items, re-run only what the fix invalidates, iterate until blessed).
- [ ] **Step 2:** Log any decisions the review forces (via decision-logging); fold accepted nits.
- [ ] **Step 3:** Final docs pass: README quickstart gains the `uv run python -m src.multimodal` line (it lists every other pipeline command); `docs/documentation/src.md` / `eval.md` stamps current; verify no `data/`, `.json` results, or `.private.md` files staged anywhere.
- [ ] **Step 4:** Final commit + push; confirm `git status --short` clean and origin in sync.

## Self-review (writing-plans checklist)

- **Spec coverage:** F5 (caption + index + answerable q9) → Tasks 2–4, 6, 7; D19 extension (pp. 50–51) → PAGE_SPECS; "text-only vs multimodal comparison" (M5 milestone text) → Task 7 Steps 2/4; measurement discipline D17/D23 → Task 5 + pre-committed table. ✓
- **Placeholders:** none — all code complete, all prompts written, all expected outputs stated. The one deliberate sequencing note (Task 2 imports depend on Task 4 Step 1) is called out explicitly with the resolution. ✓
- **Type consistency:** `caption_page(client, page) -> str`, `build_node(page, caption) -> TextNode`, `delete_by_page/delete_by_node_ids -> int` used consistently across Tasks 2–4/6. ✓

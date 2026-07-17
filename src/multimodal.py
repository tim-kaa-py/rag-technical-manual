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
# topical signal, in the pipeline's NORMALIZED heading vocabulary
# (textprep.detect_heading output) so captions and coexisting text chunks
# cite one section under one spelling; context_pages ship an extra image
# whose column headers the continuation page lacks.
PAGE_SPECS: dict[str, dict] = {
    "42": {
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
    # Sonnet 5: thinking omitted = adaptive, sharing max_tokens — the visible
    # transcription is small, but thinking over a dense table image is not
    # (8000 measured truncating on the p. 42 chart); fail loudly on truncation
    response = client.messages.create(
        model=CAPTION_MODEL,
        max_tokens=16000,
        system=CAPTION_SYSTEM,
        messages=[{"role": "user", "content": [*blocks, {"type": "text", "text": spec["prompt"]}]}],
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

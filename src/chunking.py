"""Chunking (D9): SentenceSplitter 512/64 + section TAGGING (not splitting).

The section of a chunk = the most recent heading seen at the chunk's start.
Headings inside a chunk update the running section for FOLLOWING chunks.
A missed heading can only mislabel a citation — never move a boundary.
"""

from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode

from src.config import CHUNK_OVERLAP, CHUNK_SIZE
from src.textprep import detect_heading


def _headings_in(text: str) -> list[str]:
    return [h for line in text.splitlines() if (h := detect_heading(line))]


def build_nodes(pages: list[Document]) -> list[TextNode]:
    splitter = SentenceSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    nodes = splitter.get_nodes_from_documents(pages)  # preserves document order

    current: str | None = None
    for node in nodes:
        headings = _headings_in(node.text)
        first_line = node.text.strip().splitlines()[0] if node.text.strip() else ""
        starts_with_heading = detect_heading(first_line)
        node.metadata["section"] = starts_with_heading or current or "unknown"
        # D20: the section is topical signal (continuation chunks inherit a
        # heading their body lacks) — embed it; the page number is noise.
        node.excluded_embed_metadata_keys = ["page"]
        if headings:
            current = headings[-1]
    return nodes


if __name__ == "__main__":
    from src.parse import load_pages

    nodes = build_nodes(load_pages())
    print(f"{len(nodes)} chunks")
    for n in nodes[:5] + nodes[-3:]:
        print(
            f"p.{n.metadata['page']:>3}  [{n.metadata['section'][:40]:<40}] "
            f"{n.text[:60].replace(chr(10), ' ')}"
        )

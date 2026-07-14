"""Full ingest pipeline: parse → clean → chunk → embed → pgvector (D8/D9/D18)."""

import sys

from llama_index.core import StorageContext, VectorStoreIndex

from src.chunking import build_nodes
from src.config import DEFAULT_EMBED, EMBED_CONFIGS
from src.parse import load_pages
from src.store import drop_table, embedder, get_vector_store, verify_store


def run(embed: str = DEFAULT_EMBED) -> None:
    print(f"embed config: {embed} ({EMBED_CONFIGS[embed]['model']})")
    print("D18 drop-and-rebuild: dropping existing table (if any)...")
    drop_table(embed)

    pages = load_pages()
    nodes = build_nodes(pages)
    print(f"parsed {len(pages)} pages -> {len(nodes)} chunks; embedding...")

    storage = StorageContext.from_defaults(vector_store=get_vector_store(embed))
    VectorStoreIndex(nodes, storage_context=storage, embed_model=embedder(embed))

    rows, ann_indexes = verify_store(embed)
    print(f"loaded {rows} rows into pgvector")
    # F4: explicit raises — these guards must survive python -O (D11/D18)
    if rows != len(nodes):
        raise RuntimeError(f"row count {rows} != chunk count {len(nodes)} (violates D18)")
    if ann_indexes:
        raise RuntimeError(f"unexpected ANN index found: {ann_indexes} (violates D11)")
    print("D11 verified: no ANN index — exact scan")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_EMBED)

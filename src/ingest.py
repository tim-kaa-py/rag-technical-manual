"""Full ingest pipeline: parse → clean → chunk → embed → pgvector (D8/D9/D18)."""

from llama_index.core import StorageContext, VectorStoreIndex

from src.chunking import build_nodes
from src.parse import load_pages
from src.store import drop_table, embedder, get_vector_store, verify_store


def run() -> None:
    print("D18 drop-and-rebuild: dropping existing table (if any)...")
    drop_table()

    pages = load_pages()
    nodes = build_nodes(pages)
    print(f"parsed {len(pages)} pages -> {len(nodes)} chunks; embedding...")

    storage = StorageContext.from_defaults(vector_store=get_vector_store())
    VectorStoreIndex(nodes, storage_context=storage, embed_model=embedder())

    rows, ann_indexes = verify_store()
    print(f"loaded {rows} rows into pgvector")
    assert rows == len(nodes), f"row count {rows} != chunk count {len(nodes)}"
    # D11: the store must NOT have created an ANN index behind our back
    assert not ann_indexes, f"unexpected ANN index found: {ann_indexes} (violates D11)"
    print("D11 verified: no ANN index — exact scan")


if __name__ == "__main__":
    run()

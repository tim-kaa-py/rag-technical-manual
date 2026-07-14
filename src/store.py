"""pgvector store access (D11: exact scan + cosine — no ANN index)."""

from contextlib import contextmanager

import psycopg2
from llama_index.core import VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.postgres import PGVectorStore

from src.config import DEFAULT_EMBED, EMBED_CONFIGS, pg_params


def full_table(embed: str = DEFAULT_EMBED) -> str:
    # LlamaIndex prefixes table names with "data_"
    return f"data_{EMBED_CONFIGS[embed]['table']}"


@contextmanager
def _conn():
    conn = psycopg2.connect(**pg_params())
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def embedder(embed: str = DEFAULT_EMBED) -> OpenAIEmbedding:
    return OpenAIEmbedding(model=EMBED_CONFIGS[embed]["model"])


def get_vector_store(embed: str = DEFAULT_EMBED) -> PGVectorStore:
    p = pg_params()
    cfg = EMBED_CONFIGS[embed]
    # No hnsw_kwargs → no ANN index gets created (D11). Verified post-ingest.
    return PGVectorStore.from_params(
        host=p["host"],
        port=p["port"],
        database=p["database"],
        user=p["user"],
        password=p["password"],
        table_name=cfg["table"],
        embed_dim=cfg["dim"],
    )


def get_index(embed: str = DEFAULT_EMBED) -> VectorStoreIndex:
    return VectorStoreIndex.from_vector_store(get_vector_store(embed), embed_model=embedder(embed))


def drop_table(embed: str = DEFAULT_EMBED) -> None:
    """D18: ingest is drop-and-rebuild."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(f'DROP TABLE IF EXISTS "{full_table(embed)}"')


def verify_store(embed: str = DEFAULT_EMBED) -> tuple[int, list[str]]:
    """Return (row count, ANN index names) — the D11/D18 post-ingest check."""
    with _conn() as conn, conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM "{full_table(embed)}"')
        rows = cur.fetchone()[0]
        cur.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s "
            "AND (indexdef ILIKE '%%hnsw%%' OR indexdef ILIKE '%%ivfflat%%')",
            (full_table(embed),),
        )
        ann = [r[0] for r in cur.fetchall()]
    return rows, ann

"""pgvector store access (D11: exact scan + cosine — no ANN index)."""

import psycopg2
from llama_index.core import VectorStoreIndex
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.vector_stores.postgres import PGVectorStore

from src.config import EMBED_DIM, EMBED_MODEL, TABLE_NAME, pg_params

# LlamaIndex prefixes table names with "data_"
FULL_TABLE = f"data_{TABLE_NAME}"


def embedder() -> OpenAIEmbedding:
    return OpenAIEmbedding(model=EMBED_MODEL)


def get_vector_store() -> PGVectorStore:
    p = pg_params()
    # No hnsw_kwargs → no ANN index gets created (D11). Verified below.
    return PGVectorStore.from_params(
        host=p["host"],
        port=p["port"],
        database=p["database"],
        user=p["user"],
        password=p["password"],
        table_name=TABLE_NAME,
        embed_dim=EMBED_DIM,
    )


def get_index() -> VectorStoreIndex:
    return VectorStoreIndex.from_vector_store(get_vector_store(), embed_model=embedder())


def drop_table() -> None:
    """D18: ingest is drop-and-rebuild."""
    conn = psycopg2.connect(**pg_params())
    with conn.cursor() as cur:
        cur.execute(f'DROP TABLE IF EXISTS "{FULL_TABLE}"')
    conn.commit()
    conn.close()


def verify_store() -> tuple[int, list[str]]:
    """Return (row count, ANN index names) — the D11/D18 post-ingest check."""
    conn = psycopg2.connect(**pg_params())
    with conn.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM "{FULL_TABLE}"')
        rows = cur.fetchone()[0]
        cur.execute(
            "SELECT indexname FROM pg_indexes WHERE tablename = %s "
            "AND (indexdef ILIKE '%%hnsw%%' OR indexdef ILIKE '%%ivfflat%%')",
            (FULL_TABLE,),
        )
        ann = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows, ann

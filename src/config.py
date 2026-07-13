"""Central config: env loading, model choices, pipeline constants.

Constants carry the decision IDs from docs/decisions.md that fixed them.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # .env is optional; shell env takes precedence for set vars

# D9 — chunking, measured from the manual (sections run 200-600 tokens)
CHUNK_SIZE = 512
CHUNK_OVERLAP = 64

# D13 — context budget: every measured config delivers exactly 5 chunks
TOP_K = 5

# D3 — embeddings (A/B against -large happens in M2)
EMBED_MODEL = "text-embedding-3-small"
EMBED_DIM = 1536

# D16 — per-role model tiers; only generation is used in M1
GENERATION_MODEL = "claude-sonnet-5"

PDF_PATH = Path("data/teksan_generator.pdf")
TABLE_NAME = "teksan_manual"  # LlamaIndex will create it as data_teksan_manual


def pg_params() -> dict:
    return {
        "host": os.getenv("PGHOST", "localhost"),
        "port": int(os.getenv("PGPORT", "5433")),
        "database": os.getenv("PGDATABASE", "rag"),
        "user": os.getenv("PGUSER", "rag"),
        "password": os.getenv("PGPASSWORD", "rag"),
    }


def _check() -> None:
    """M0 smoke test: DB reachable, both API keys present, corpus present."""
    import psycopg2

    conn = psycopg2.connect(**pg_params())
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone() == (1,)
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    conn.commit()
    conn.close()
    print("postgres: OK (pgvector extension available)")

    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        status = "set" if os.getenv(key) else "MISSING"
        print(f"{key}: {status}")

    print(f"corpus: {'OK' if PDF_PATH.exists() else 'MISSING'} ({PDF_PATH})")


if __name__ == "__main__":
    _check()

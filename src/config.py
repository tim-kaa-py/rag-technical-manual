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

# D13 — fusion candidate depth: 10 per retriever in, TOP_K out
CANDIDATE_K = 10

# D3 — embedding tiers; the M2 harness A/Bs small vs large (D7/D17).
# Each tier gets its own table so the configs are not mutually destructive
# under D18's drop-and-rebuild. LlamaIndex prefixes tables with "data_".
EMBED_CONFIGS = {
    "small": {"model": "text-embedding-3-small", "dim": 1536, "table": "teksan_manual"},
    "large": {"model": "text-embedding-3-large", "dim": 3072, "table": "teksan_manual_large"},
}
DEFAULT_EMBED = "small"

# D16 — per-role model tiers
GENERATION_MODEL = "claude-sonnet-5"
JUDGE_MODEL = "claude-opus-4-8"
RERANK_MODEL = "claude-haiku-4-5"  # D16; swap predicate pre-registered in the M3 plan Task 4

_ROOT = Path(__file__).resolve().parent.parent  # repo root, independent of cwd
PDF_PATH = _ROOT / "data" / "teksan_generator.pdf"


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

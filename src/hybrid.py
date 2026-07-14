"""Hybrid retrieval (D12/D13): dense + in-memory BM25, fused by RRF (k=60).

The BM25 index is a derived cache built from the Postgres chunks at first
use (D12: never re-chunk; re-ingesting requires a process restart to rebuild).
BM25Retriever tokenizes EMBED-mode content, so sparse sees exactly the text
the dense side embedded (D20 invariant). Fusion dedups by node.hash
(text + metadata) — load_nodes must reconstruct ingest-time nodes exactly.
"""

import sys
from functools import lru_cache

from llama_index.core.llms.mock import MockLLM
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.schema import NodeWithScore
from llama_index.retrievers.bm25 import BM25Retriever

from src.config import CANDIDATE_K, DEFAULT_EMBED
from src.store import get_index, load_nodes


@lru_cache(maxsize=2)  # one per embed tier; process-lifetime cache (D12)
def _arms(embed: str):
    dense = get_index(embed).as_retriever(similarity_top_k=CANDIDATE_K)
    sparse = BM25Retriever.from_defaults(nodes=load_nodes(embed), similarity_top_k=CANDIDATE_K)
    return dense, sparse


@lru_cache(maxsize=2)
def _fusion_retriever(embed: str) -> QueryFusionRetriever:
    return QueryFusionRetriever(
        list(_arms(embed)),
        llm=MockLLM(),  # query expansion is off (num_queries=1); never invoked
        mode="reciprocal_rerank",  # D13: RRF, library constant k=60
        similarity_top_k=CANDIDATE_K,  # 10 fused candidates out
        num_queries=1,  # D13: no silent LLM query expansion (default is 4!)
        use_async=False,
    )


def hybrid_candidates(question: str, embed: str = DEFAULT_EMBED) -> list[NodeWithScore]:
    """The 10 fused candidates in RRF order — the reranker's input (D14)."""
    return _fusion_retriever(embed).retrieve(question)


def arm_results(question: str, embed: str = DEFAULT_EMBED) -> dict[str, list[NodeWithScore]]:
    """Per-arm top-10 — eval instrumentation only (D23): makes 'BM25 moved
    this row' demonstrable instead of post hoc, and makes the zero-score
    sparse-padding trigger measurable."""
    dense, sparse = _arms(embed)
    return {"dense": dense.retrieve(question), "sparse": sparse.retrieve(question)}


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "How does high fuel sulphur content affect the oil change interval?"
    results = hybrid_candidates(question)
    for r in results:
        print(
            f"{r.score:.4f}  p.{r.node.metadata['page']:>3}  "
            f"[{r.node.metadata.get('section', '?')[:40]}]  "
            f"{r.node.text[:70].replace(chr(10), ' ')}"
        )
    # smoke canaries: no duplicate content; >1/61 proves both-arm RRF mass
    assert len({r.node.hash for r in results}) == len(results), "duplicate content in fused list"
    both_arms = sum(1 for r in results if (r.score or 0) > 1 / 61)
    print(f"candidates with RRF mass from BOTH arms (score > 1/61): {both_arms}")

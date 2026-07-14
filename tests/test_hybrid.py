from llama_index.core.llms.mock import MockLLM
from llama_index.core.retrievers import BaseRetriever, QueryFusionRetriever
from llama_index.core.schema import MetadataMode, NodeWithScore, TextNode

from src.chunking import build_nodes


class _StubRetriever(BaseRetriever):
    def __init__(self, results):
        self._results = results
        super().__init__()

    def _retrieve(self, query_bundle):
        return self._results


def _nws(node_id: str, score: float) -> NodeWithScore:
    # fusion dedups by node.hash = sha256(text + metadata); same id + same
    # text/metadata -> same hash, which is what makes these two "B"s merge
    return NodeWithScore(node=TextNode(id_=node_id, text=f"text {node_id}"), score=score)


def test_rrf_fusion_dedups_by_content_hash_and_prefers_doubly_retrieved():
    # dense arm: A then B; sparse arm: B then C (scores on incomparable scales
    # — exactly why D13 fuses by rank, not score)
    dense = _StubRetriever([_nws("A", 0.9), _nws("B", 0.8)])
    sparse = _StubRetriever([_nws("B", 9.0), _nws("C", 5.0)])
    fused = QueryFusionRetriever(
        [dense, sparse],
        llm=MockLLM(),  # never invoked at num_queries=1; avoids Settings.llm resolution
        mode="reciprocal_rerank",
        similarity_top_k=10,
        num_queries=1,
        use_async=False,
    ).retrieve("any question")
    ids = [r.node.node_id for r in fused]
    assert ids == ["B", "A", "C"]  # B earned RRF mass from BOTH arms; deduped by hash


def test_load_nodes_reconstruction_mirrors_ingest_nodes_exactly():
    # simulate the Postgres round-trip: build_nodes -> (node_id, text, {page,
    # section}) row -> reconstructed TextNode. Hash AND embed-content equality
    # is what RRF dedup and the D20 invariant actually require.
    from llama_index.core import Document

    pages = [
        Document(text="5.4 Lubrication Oil\nUse API CF4 grade oil.", metadata={"page": "42"}),
        Document(text="More details continue without any heading.", metadata={"page": "43"}),
    ]
    for original in build_nodes(pages):
        rebuilt = TextNode(
            id_=original.node_id,
            text=original.text,
            metadata={"page": original.metadata["page"], "section": original.metadata["section"]},
        )
        rebuilt.excluded_embed_metadata_keys = ["page"]
        assert rebuilt.hash == original.hash  # RRF dedup key
        assert rebuilt.get_content(metadata_mode=MetadataMode.EMBED) == original.get_content(
            metadata_mode=MetadataMode.EMBED
        )  # D20: BM25 tokenizes what dense embedded

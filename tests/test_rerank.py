import anthropic
import pytest
from llama_index.core.schema import NodeWithScore, TextNode

import src.rerank as rerank_mod
from src.rerank import RerankParseError, parse_ranking, rerank, rerank_prompt


def _chunk(node_id: str, page: str) -> NodeWithScore:
    node = TextNode(id_=node_id, text=f"chunk {node_id}", metadata={"page": page, "section": "5.6 Fuel"})
    return NodeWithScore(node=node, score=0.02)


CANDS = [_chunk(f"c{i}", str(40 + i)) for i in range(1, 11)]  # 10 candidates


def test_parse_ranking_accepts_topk_of_n():
    assert parse_ranking('{"ranking": [3, 1, 7, 2, 9]}', k=5, n=10) == [3, 1, 7, 2, 9]


def test_parse_ranking_strips_code_fences():
    assert parse_ranking('```json\n{"ranking": [1, 2, 3, 4, 5]}\n```', k=5, n=10) == [1, 2, 3, 4, 5]


def test_parse_ranking_rejects_garbage_wrong_length_dupes_out_of_range():
    for bad in (
        "the best chunks are 3 and 1",  # not JSON
        '{"ranking": [1, 2, 3]}',  # wrong length
        '{"ranking": [1, 1, 2, 3, 4]}',  # duplicate
        '{"ranking": [1, 2, 3, 4, 11]}',  # out of range
        '{"ranking": "1,2,3,4,5"}',  # wrong type
    ):
        with pytest.raises(RerankParseError):
            parse_ranking(bad, k=5, n=10)


def test_rerank_prompt_numbers_all_candidates_carries_question_and_hides_pages():
    p = rerank_prompt("Which fuel standard?", CANDS)
    assert "Which fuel standard?" in p
    for i in range(1, 11):
        assert f"[{i}]" in p
    assert '"ranking"' in p
    assert "5.6 Fuel" in p  # section = topical signal, shown (D20 rationale)
    assert "p. 41" not in p  # page number = noise, withheld from the reranker


def test_rerank_reorders_on_valid_response(monkeypatch):
    monkeypatch.setattr(rerank_mod, "_call", lambda prompt: '{"ranking": [10, 9, 8, 7, 6]}')
    result = rerank("Q?", CANDS)
    assert result.fallback is False
    assert [c.node.node_id for c in result.chunks] == ["c10", "c9", "c8", "c7", "c6"]


def test_rerank_falls_back_to_rrf_order_on_parse_failure(monkeypatch):
    # D14: a reranker failure may degrade ranking quality, never break a query
    monkeypatch.setattr(rerank_mod, "_call", lambda prompt: "I think chunk 3 is best!")
    result = rerank("Q?", CANDS)
    assert result.fallback is True
    assert [c.node.node_id for c in result.chunks] == ["c1", "c2", "c3", "c4", "c5"]


def test_rerank_falls_back_on_api_error(monkeypatch):
    # the external call is the boundary where failure is real — a transient
    # 529 on eval row 11/12 must not burn the whole paid run
    def _boom(prompt):
        raise anthropic.AnthropicError("overloaded")

    monkeypatch.setattr(rerank_mod, "_call", _boom)
    result = rerank("Q?", CANDS)
    assert result.fallback is True
    assert [c.node.node_id for c in result.chunks] == ["c1", "c2", "c3", "c4", "c5"]

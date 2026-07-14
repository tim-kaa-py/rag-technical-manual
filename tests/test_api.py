from types import SimpleNamespace

import anthropic
import pytest
from fastapi.testclient import TestClient
from llama_index.core.schema import NodeWithScore, TextNode

import api.main as api_mod
from api.main import app
from src.generate import GenerationIncompleteError, RagAnswer, Source


@pytest.fixture()
def client(monkeypatch):
    # warm() touches the DB — neutralize it so TestClient's lifespan is hermetic
    monkeypatch.setattr(api_mod, "warm", lambda: None)
    with TestClient(app) as c:
        yield c


def _chunk(page: str) -> NodeWithScore:
    node = TextNode(text=f"chunk {page}", metadata={"page": page, "section": "5.6 Fuel"})
    return NodeWithScore(node=node, score=0.02)


def _pipeline_ok(monkeypatch, fallback: bool = False):
    cands = [_chunk("43"), _chunk("29")]
    monkeypatch.setattr(api_mod, "hybrid_candidates", lambda q: cands)
    monkeypatch.setattr(
        api_mod,
        "rerank",
        lambda q, c: SimpleNamespace(chunks=c[:1], fallback=fallback),
    )
    monkeypatch.setattr(
        api_mod,
        "answer_from_chunks",
        lambda q, chunks: RagAnswer(
            answer="EN590 (p. 43).",
            sources=[Source(page="43", section="5.6 Fuel", snippet="chunk 43")],
        ),
    )


def test_query_returns_answer_sources_and_degraded_flag(monkeypatch, client):
    _pipeline_ok(monkeypatch)
    r = client.post("/query", json={"question": "Which fuel standard?"})
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "EN590 (p. 43)."
    assert body["sources"] == [{"page": "43", "section": "5.6 Fuel", "snippet": "chunk 43"}]
    assert body["rerank_degraded"] is False


def test_query_surfaces_rerank_degradation(monkeypatch, client):
    # D14: a reranker failure degrades ranking, never breaks the query —
    # but the API must not HIDE that it happened
    _pipeline_ok(monkeypatch, fallback=True)
    r = client.post("/query", json={"question": "Which fuel standard?"})
    assert r.status_code == 200
    assert r.json()["rerank_degraded"] is True


def test_query_validates_empty_and_whitespace_and_overlong(client):
    assert client.post("/query", json={"question": ""}).status_code == 422
    assert client.post("/query", json={"question": "   "}).status_code == 422
    assert client.post("/query", json={"question": "x" * 2001}).status_code == 422
    assert client.post("/query", json={}).status_code == 422


def test_query_accepts_padded_question_up_to_limit_after_strip(monkeypatch, client):
    # strip runs BEFORE Field constraints (mode="before"): a legit 2000-char
    # question with surrounding whitespace must pass, not 422
    _pipeline_ok(monkeypatch)
    r = client.post("/query", json={"question": "  " + "x" * 2000 + "  "})
    assert r.status_code == 200


def test_lifespan_calls_warm_exactly_once(monkeypatch):
    # the startup-warms-the-caches promise (D12/F2) must be pinned, or the
    # lifespan hook can vanish with the suite still green
    calls = []
    monkeypatch.setattr(api_mod, "warm", lambda: calls.append(1))
    with TestClient(app):
        pass
    assert calls == [1]


def test_upstream_model_failure_maps_to_502_without_internals(monkeypatch, client):
    cands = [_chunk("43")]
    monkeypatch.setattr(api_mod, "hybrid_candidates", lambda q: cands)
    monkeypatch.setattr(api_mod, "rerank", lambda q, c: SimpleNamespace(chunks=c, fallback=False))

    def _boom(q, chunks):
        raise anthropic.AnthropicError("api_key sk-secret leaked in message")

    monkeypatch.setattr(api_mod, "answer_from_chunks", _boom)
    r = client.post("/query", json={"question": "Which fuel standard?"})
    assert r.status_code == 502
    assert "sk-secret" not in r.text  # N4: no internals in the response body


def test_generation_incomplete_maps_to_502(monkeypatch, client):
    # generate._answer_text raises GenerationIncompleteError on truncation/empty
    # text (D15 loud-failure guard) — the API maps it to 502, never a fabricated answer
    cands = [_chunk("43")]
    monkeypatch.setattr(api_mod, "hybrid_candidates", lambda q: cands)
    monkeypatch.setattr(api_mod, "rerank", lambda q, c: SimpleNamespace(chunks=c, fallback=False))

    def _truncated(q, chunks):
        raise GenerationIncompleteError("generation incomplete: stop_reason='max_tokens'")

    monkeypatch.setattr(api_mod, "answer_from_chunks", _truncated)
    r = client.post("/query", json={"question": "Which fuel standard?"})
    assert r.status_code == 502

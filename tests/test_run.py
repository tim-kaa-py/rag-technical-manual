from types import SimpleNamespace

from llama_index.core.schema import NodeWithScore, TextNode

import eval.run as run_mod
from eval.golden import GoldenQuestion


def _chunk(page: str) -> NodeWithScore:
    node = TextNode(text=f"chunk text {page}", metadata={"page": page, "section": "5.6 Fuel"})
    return NodeWithScore(node=node, score=0.9)


def _verdict(passed: bool) -> SimpleNamespace:
    return SimpleNamespace(passed=passed, justification="stub reasoning")


def test_run_eval_and_write_report_agree_on_row_schema(monkeypatch, tmp_path):
    golden = [
        GoldenQuestion(
            id="q1",
            qtype="lexical",
            question="Which fuel?",
            expected_pages=["43"],
            golden_answer="EN590.",
            annotation=None,
            trap=False,
        ),
        GoldenQuestion(
            id="q12",
            qtype="trap",
            question="Torque?",
            expected_pages=[],
            golden_answer="",
            annotation="trap",
            trap=True,
        ),
    ]
    monkeypatch.setattr(run_mod, "load_golden", lambda: golden)
    monkeypatch.setattr(run_mod, "retrieve", lambda q, embed=None: [_chunk("43")])
    monkeypatch.setattr(
        run_mod,
        "answer_from_chunks",
        lambda q, chunks: SimpleNamespace(answer="EN590 (p. 43).", sources=[]),
    )
    monkeypatch.setattr(run_mod, "judge_groundedness", lambda *a: _verdict(True))
    monkeypatch.setattr(run_mod, "judge_correctness", lambda *a: _verdict(False))
    monkeypatch.setattr(run_mod, "judge_refusal", lambda *a: _verdict(True))

    run = run_mod.run_eval(embed="small")
    assert run["config_label"] == "dense-small"
    report = run_mod.write_report(run, out_dir=tmp_path)

    text = report.read_text()
    assert "hit@5 = 1/1" in text and "MRR@5 = 1.00" in text
    assert "q1/correct" in text and "stub reasoning" in text
    assert "refused = yes" in text
    assert (tmp_path / f"{run['date']}-dense-small.json").exists()


def test_run_eval_hybrid_mode_logs_candidates_arms_and_rerank_flags(monkeypatch, tmp_path):
    golden = [
        GoldenQuestion(
            id="q1",
            qtype="lexical",
            question="Which fuel?",
            expected_pages=["43"],
            golden_answer="EN590.",
            annotation=None,
            trap=False,
        ),
    ]
    cands = [_chunk("43"), _chunk("29"), _chunk("11")]
    monkeypatch.setattr(run_mod, "load_golden", lambda: golden)
    monkeypatch.setattr(run_mod, "hybrid_candidates", lambda q, embed=None: cands)
    monkeypatch.setattr(
        run_mod,
        "arm_results",
        lambda q, embed=None: {"dense": cands[:2], "sparse": cands[1:]},
    )
    monkeypatch.setattr(
        run_mod,
        "rerank",
        lambda q, c: SimpleNamespace(chunks=c[:2], fallback=True),
    )
    monkeypatch.setattr(
        run_mod,
        "answer_from_chunks",
        lambda q, chunks: SimpleNamespace(answer="EN590 (p. 43).", sources=[]),
    )
    monkeypatch.setattr(run_mod, "judge_groundedness", lambda *a: _verdict(True))
    monkeypatch.setattr(run_mod, "judge_correctness", lambda *a: _verdict(True))

    run = run_mod.run_eval(mode="rerank", embed="small")
    assert run["config_label"] == "rerank-small"
    assert run["rerank_model"]  # provenance lives in the artifact (D16 swap!)
    row = run["rows"][0]
    assert [c["page"] for c in row["candidates"]] == ["43", "29", "11"]
    assert all("node_id" in c and "score" in c for c in row["candidates"])
    assert row["dense_pages"] == ["43", "29"] and row["sparse_pages"] == ["29", "11"]
    assert row["rerank_fallback"] is True

    report = run_mod.write_report(run, out_dir=tmp_path)
    text = report.read_text()
    assert "fallback" in text.lower() and "q1" in text  # fallback rows are NAMED


def test_run_eval_dense_mode_keeps_schema_with_null_instrumentation(monkeypatch, tmp_path):
    golden = [
        GoldenQuestion(
            id="q1",
            qtype="lexical",
            question="Which fuel?",
            expected_pages=["43"],
            golden_answer="EN590.",
            annotation=None,
            trap=False,
        ),
    ]
    monkeypatch.setattr(run_mod, "load_golden", lambda: golden)
    monkeypatch.setattr(run_mod, "retrieve", lambda q, embed=None: [_chunk("43")])
    monkeypatch.setattr(
        run_mod,
        "answer_from_chunks",
        lambda q, chunks: SimpleNamespace(answer="EN590 (p. 43).", sources=[]),
    )
    monkeypatch.setattr(run_mod, "judge_groundedness", lambda *a: _verdict(True))
    monkeypatch.setattr(run_mod, "judge_correctness", lambda *a: _verdict(True))

    run = run_mod.run_eval(embed="small")  # default mode="dense"
    row = run["rows"][0]
    assert row["candidates"] is None
    assert row["rerank_fallback"] is False
    assert run["rerank_model"] is None
    assert "dense_pages" not in row

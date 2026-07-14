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

    run = run_mod.run_eval("small")
    assert run["config_label"] == "dense-small"
    report = run_mod.write_report(run, out_dir=tmp_path)

    text = report.read_text()
    assert "hit@5 = 1/1" in text and "MRR@5 = 1.00" in text
    assert "q1/correct" in text and "stub reasoning" in text
    assert "refused = yes" in text
    assert (tmp_path / f"{run['date']}-dense-small.json").exists()

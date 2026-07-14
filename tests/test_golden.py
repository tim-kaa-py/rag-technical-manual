import json

import pytest

from eval.golden import GoldenQuestion, load_golden


def test_load_golden_returns_frozen_questions(tmp_path):
    data = [
        {
            "id": "q1",
            "qtype": "lexical",
            "question": "Which fuel?",
            "expected_pages": ["43"],
            "golden_answer": "EN590.",
            "annotation": None,
            "trap": False,
        },
        {
            "id": "q12",
            "qtype": "trap",
            "question": "Torque?",
            "expected_pages": [],
            "golden_answer": "",
            "annotation": "trap — not in corpus",
            "trap": True,
        },
    ]
    p = tmp_path / "g.json"
    p.write_text(json.dumps(data))
    qs = load_golden(p)
    assert len(qs) == 2 and isinstance(qs[0], GoldenQuestion)
    assert qs[0].expected_pages == ["43"]


def test_non_trap_questions_must_have_pages_and_answer(tmp_path):
    bad = [
        {
            "id": "q1",
            "qtype": "lexical",
            "question": "?",
            "expected_pages": [],
            "golden_answer": "",
            "annotation": None,
            "trap": False,
        }
    ]
    p = tmp_path / "g.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="q1"):
        load_golden(p)


def test_trap_questions_must_not_have_expected_pages(tmp_path):
    bad = [
        {
            "id": "q12",
            "qtype": "trap",
            "question": "?",
            "expected_pages": ["9"],
            "golden_answer": "",
            "annotation": None,
            "trap": True,
        }
    ]
    p = tmp_path / "g.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="q12"):
        load_golden(p)

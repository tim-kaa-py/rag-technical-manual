import pytest

from eval.judge import (
    JudgeParseError,
    correctness_prompt,
    groundedness_prompt,
    parse_verdict,
)


def test_parse_verdict_accepts_strict_json():
    v = parse_verdict('{"justification": "All claims cited from context.", "verdict": "pass"}')
    assert v.passed is True and "claims" in v.justification


def test_parse_verdict_strips_code_fences():
    raw = '```json\n{"justification": "Claim X unsupported.", "verdict": "fail"}\n```'
    assert parse_verdict(raw).passed is False


def test_parse_verdict_raises_on_garbage_or_bad_verdict():
    with pytest.raises(JudgeParseError):
        parse_verdict("The answer looks fine to me.")
    with pytest.raises(JudgeParseError):
        parse_verdict('{"justification": "x", "verdict": "maybe"}')


def test_groundedness_prompt_withholds_golden_and_demands_justification_first():
    p = groundedness_prompt("Q?", "CONTEXT", "ANSWER")
    assert "CONTEXT" in p and "ANSWER" in p
    assert "golden" not in p.lower()  # reference-free axis (D17)
    assert p.index("justification") < p.index("verdict")  # autoregressive order


def test_correctness_prompt_withholds_context():
    p = correctness_prompt("Q?", "GOLDEN", "ANSWER")
    assert "GOLDEN" in p and "ANSWER" in p
    assert "context" not in p.lower()  # reference-based axis judges against golden only

"""LLM-as-judge (D16/D17): Opus 4.8, two binary axes, two separate calls.

Groundedness is reference-free (golden answer withheld: it must not pass
claims that match the golden but are absent from the context). Correctness is
reference-based (context withheld). Justification precedes verdict in the JSON
schema because generation is autoregressive — verdict-first produces a snap
judgment followed by a rationalization. Parse failure retries once, then
fails the run: a silently degraded instrument produces confident lies.
"""

import json
import re
from dataclasses import dataclass

import anthropic

from src.config import JUDGE_MODEL

JUDGE_PROMPT_VERSION = "v1"


class JudgeParseError(RuntimeError):
    pass


@dataclass
class Verdict:
    justification: str
    passed: bool


_JSON_SPEC = (
    "Respond with ONLY this JSON object, no other text:\n"
    '{"justification": "<2-4 sentences of specific reasoning first>", '
    '"verdict": "pass" or "fail"}'
)


def groundedness_prompt(question: str, context: str, answer: str) -> str:
    return (
        "You are grading a RAG system's answer for GROUNDEDNESS only: is every "
        "claim in the answer supported by the provided excerpts?\n"
        "Rules:\n"
        "- Fail if ANY claim in the answer is not supported by the excerpts.\n"
        "- Hedged claims ('typically', 'generally', 'usually') count as claims — "
        "hedging does not exempt a statement from needing support.\n"
        "- An explicit refusal ('the manual does not contain...') is grounded (pass) "
        "if the excerpts indeed lack the information.\n"
        "- Do NOT judge whether the answer is correct or useful — only support.\n\n"
        f"Excerpts:\n{context}\n\nQuestion: {question}\n\nAnswer to grade:\n{answer}\n\n"
        + _JSON_SPEC
    )


def correctness_prompt(question: str, golden_answer: str, answer: str) -> str:
    return (
        "You are grading a RAG system's answer for CORRECTNESS only: does it "
        "agree with the reference answer on the facts the question asks for?\n"
        "Rules:\n"
        "- Paraphrase and different level of detail are fine; factual conflict or a "
        "missing core fact is a fail.\n"
        "- A refusal when the reference contains a real answer is a fail.\n\n"
        f"Question: {question}\n\nReference answer:\n{golden_answer}\n\n"
        f"Answer to grade:\n{answer}\n\n" + _JSON_SPEC
    )


def refusal_prompt(answer: str) -> str:
    return (
        "Does this answer explicitly decline to answer because the manual/context "
        "does not contain the information (as opposed to attempting an answer)?\n"
        "verdict pass = it explicitly declines; fail = it attempts an answer.\n"
        "IMPORTANT: if it declines but still supplies substantive information "
        "answering the question (e.g. 'the manual does not say, but typically X'), "
        "verdict fail — that is an attempt in disguise.\n\n"
        f"Answer:\n{answer}\n\n" + _JSON_SPEC
    )


def parse_verdict(raw: str) -> Verdict:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise JudgeParseError(f"judge output is not JSON: {raw[:200]!r}") from e
    if not isinstance(obj, dict) or obj.get("verdict") not in ("pass", "fail"):
        raise JudgeParseError(f"judge JSON missing/invalid verdict: {raw[:200]!r}")
    return Verdict(justification=str(obj.get("justification", "")), passed=obj["verdict"] == "pass")


def _call(prompt: str) -> Verdict:
    client = anthropic.Anthropic()
    last_error: JudgeParseError | None = None
    for _ in range(2):  # retry once on parse failure, then fail the run (D17)
        response = client.messages.create(
            model=JUDGE_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return parse_verdict(raw)
        except JudgeParseError as e:
            last_error = e
    raise last_error


def judge_groundedness(question: str, context: str, answer: str) -> Verdict:
    return _call(groundedness_prompt(question, context, answer))


def judge_correctness(question: str, golden_answer: str, answer: str) -> Verdict:
    return _call(correctness_prompt(question, golden_answer, answer))


def judge_refusal(answer: str) -> Verdict:
    return _call(refusal_prompt(answer))

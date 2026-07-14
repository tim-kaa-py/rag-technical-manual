"""Listwise reranking (D14/D16): one Haiku call orders the 10 fused candidates
against each other; the top-5 survive. Bi-encoder retrieval scores "same
topic"; a reranker reads question and chunk together — "actually answers
this". Parse failures AND transport/API failures fall back to RRF order: a
serving-path stage degrades gracefully (contrast the D17 judge, which fails
loudly — an eval instrument must never silently degrade). No retry (D14).

The prompt shows each candidate's section label (the same topical signal D20
embeds) but NOT its page number (D20 calls page numbers noise; a low page
number could read as "front matter" — an uncontrolled input, withheld)."""

import json
import re
from dataclasses import dataclass

import anthropic
from llama_index.core.schema import NodeWithScore

from src.config import DEFAULT_EMBED, RERANK_MODEL, TOP_K
from src.hybrid import hybrid_candidates


class RerankParseError(RuntimeError):
    pass


@dataclass
class RerankResult:
    chunks: list[NodeWithScore]
    fallback: bool  # True -> RRF order kept (call failed or response unparseable)


def rerank_prompt(question: str, candidates: list[NodeWithScore]) -> str:
    blocks = [
        f"[{i}] ({c.node.metadata.get('section', 'unknown')})\n{c.node.text}"
        for i, c in enumerate(candidates, start=1)
    ]
    return (
        "Rank the excerpts below by how well they ANSWER the question — not merely "
        "mention its topic. Respond with ONLY this JSON object, no other text:\n"
        f'{{"ranking": [<the {TOP_K} best excerpt numbers, best first>]}}\n\n'
        f"Question: {question}\n\n" + "\n\n---\n\n".join(blocks)
    )


def parse_ranking(raw: str, k: int, n: int) -> list[int]:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise RerankParseError(f"not JSON: {raw[:200]!r}") from e
    ranking = obj.get("ranking") if isinstance(obj, dict) else None
    if not (
        isinstance(ranking, list)
        and len(ranking) == k
        and all(isinstance(i, int) and 1 <= i <= n for i in ranking)
        and len(set(ranking)) == k
    ):
        raise RerankParseError(f"invalid ranking (need {k} distinct ints in 1..{n}): {raw[:200]!r}")
    return ranking


def _call(prompt: str) -> str:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=RERANK_MODEL,
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    return next((b.text for b in response.content if b.type == "text"), "")


def rerank(question: str, candidates: list[NodeWithScore]) -> RerankResult:
    try:
        raw = _call(rerank_prompt(question, candidates))
        order = parse_ranking(raw, k=TOP_K, n=len(candidates))
    except (anthropic.AnthropicError, RerankParseError) as e:
        print(f"rerank fallback — RRF order kept: {e}")
        return RerankResult(chunks=candidates[:TOP_K], fallback=True)
    return RerankResult(chunks=[candidates[i - 1] for i in order], fallback=False)


def rerank_retrieve(question: str, embed: str = DEFAULT_EMBED) -> list[NodeWithScore]:
    """CLI/serving-shaped wrapper. NOTE: discards the fallback flag — M4's
    API must call rerank() directly so degradation stays observable."""
    return rerank(question, hybrid_candidates(question, embed)).chunks


if __name__ == "__main__":
    import sys

    question = " ".join(sys.argv[1:]) or "How does high fuel sulphur content affect the oil change interval?"
    for r in rerank_retrieve(question):
        print(
            f"p.{r.node.metadata['page']:>3}  [{r.node.metadata.get('section', '?')[:40]}]  "
            f"{r.node.text[:70].replace(chr(10), ' ')}"
        )

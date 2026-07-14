"""Retrieval metrics (D17): hit@5 = selection, MRR@5 = ordering.

Rank positions are defined by chunks, not pages; RR = 0 on a miss.
At n≈11 one question moves an aggregate ~9 points — report counts, never
percentages with decimals.
"""


def hit(retrieved_pages: list[str], expected: set[str]) -> bool:
    return bool(set(retrieved_pages) & expected)


def reciprocal_rank(retrieved_pages: list[str], expected: set[str]) -> float:
    for rank, page in enumerate(retrieved_pages, start=1):
        if page in expected:
            return 1.0 / rank
    return 0.0


def pages_found(retrieved_pages: list[str], expected: set[str]) -> str:
    return f"{len(set(retrieved_pages) & expected)}/{len(expected)}"

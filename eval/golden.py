"""Golden Q&A set loader (D17): frozen before any results exist."""

import json
from dataclasses import dataclass
from pathlib import Path

GOLDEN_PATH = Path(__file__).parent / "golden.json"


@dataclass(frozen=True)
class GoldenQuestion:
    id: str
    qtype: str
    question: str
    expected_pages: list[str]
    golden_answer: str
    annotation: str | None
    trap: bool


def load_golden(path: Path = GOLDEN_PATH) -> list[GoldenQuestion]:
    questions = [GoldenQuestion(**row) for row in json.loads(Path(path).read_text())]
    for q in questions:
        if not q.trap and (not q.expected_pages or not q.golden_answer):
            raise ValueError(f"{q.id}: non-trap question needs expected_pages and golden_answer")
        if q.trap and q.expected_pages:
            raise ValueError(f"{q.id}: trap question must not have expected_pages (D17)")
    return questions

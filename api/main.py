"""FastAPI serving layer (F6/D5): POST /query over the measured-best pipeline.

Serves the M3 rerank config (hybrid + listwise rerank, MRR 0.91) — measured
strictly better than dense or hybrid-alone. Calls rerank() directly so D14
degradation is surfaced in the response (rerank_degraded), never hidden.
Generation failures are 502s, not fabricated answers (D15): the pipeline
prefers no answer over a wrong one. Error bodies carry no internals (N4).
"""

import logging
from contextlib import asynccontextmanager

import anthropic
import openai
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.generate import GenerationIncompleteError, answer_from_chunks
from src.hybrid import hybrid_candidates, warm
from src.rerank import rerank

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    warm()  # D12: build BM25 + dense retriever once, at startup
    yield


app = FastAPI(title="rag-technical-manual", lifespan=lifespan)


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)

    # strip BEFORE Field constraints run: a padded 2000-char question is
    # legal, and a whitespace-only one strips to "" and fails min_length=1
    @field_validator("question", mode="before")
    @classmethod
    def strip(cls, v: object) -> object:
        return v.strip() if isinstance(v, str) else v


class SourceOut(BaseModel):
    page: str
    section: str
    snippet: str


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceOut]
    rerank_degraded: bool  # True -> RRF order served (reranker failed; D14)


@app.post("/query", response_model=QueryResponse)
def query(request: QueryRequest) -> QueryResponse:
    try:
        candidates = hybrid_candidates(request.question)
        result = rerank(request.question, candidates)
        rag = answer_from_chunks(request.question, result.chunks)
    # the three external edges: OpenAI embed, Anthropic generate, and the
    # D15 under-delivery guard (rerank's edge already degrades internally,
    # D14). Anything else — e.g. Postgres down — is OUR failure: a 500.
    except (anthropic.AnthropicError, openai.OpenAIError, GenerationIncompleteError) as e:
        logger.exception("pipeline failure")  # details + traceback to logs, not clients (N4)
        raise HTTPException(status_code=502, detail="upstream model failure") from e
    return QueryResponse(
        answer=rag.answer,
        sources=[SourceOut(page=s.page, section=s.section, snippet=s.snippet) for s in rag.sources],
        rerank_degraded=result.fallback,
    )

"""Grounded generation (D15, D16): context-scoped Claude answer + structured sources.

Prompt assembly is hand-rolled rather than a LlamaIndex query engine: every
line of what the model sees must be explainable (N1).
"""

from dataclasses import dataclass

import anthropic
from llama_index.core.schema import NodeWithScore

from src.config import GENERATION_MODEL
from src.retrieve import retrieve

# D15: answer ONLY from context; refuse explicitly when it isn't there.
SYSTEM_PROMPT = (
    "You answer field-service questions about a Teksan diesel-generator "
    "operation & maintenance manual.\n"
    "Rules:\n"
    "- Answer ONLY from the provided context excerpts. Never use outside "
    "knowledge, even when you are confident.\n"
    "- If the context does not contain the information needed, reply exactly: "
    "'The manual does not contain this information.' and briefly say what IS "
    "covered instead. Do not guess.\n"
    "- Cite pages inline where natural, e.g. 'every 200 hours (p. 45)'.\n"
    "- Be concise: a field technician needs the fact, not an essay."
)


@dataclass
class Source:
    page: str
    section: str
    snippet: str


@dataclass
class RagAnswer:
    answer: str
    sources: list[Source]


def build_prompt(question: str, chunks: list[NodeWithScore]) -> str:
    blocks = [
        f"[p. {c.node.metadata['page']} | {c.node.metadata.get('section', 'unknown')}]\n"
        f"{c.node.text}"
        for c in chunks
    ]
    context = "\n\n---\n\n".join(blocks)
    return f"Context excerpts from the manual:\n\n{context}\n\nQuestion: {question}"


def sources_from(chunks: list[NodeWithScore]) -> list[Source]:
    return [
        Source(
            page=c.node.metadata["page"],
            section=c.node.metadata.get("section", "unknown"),
            snippet=(c.node.text[:200] + "...") if len(c.node.text) > 200 else c.node.text,
        )
        for c in chunks
    ]


def answer(question: str) -> RagAnswer:
    chunks = retrieve(question)
    client = anthropic.Anthropic()
    # Sonnet 5: no temperature/top_p/top_k (400); thinking omitted = adaptive.
    response = client.messages.create(
        model=GENERATION_MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_prompt(question, chunks)}],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    return RagAnswer(answer=text, sources=sources_from(chunks))


if __name__ == "__main__":
    import sys

    q = " ".join(sys.argv[1:]) or "Which fuel standard does the generator require?"
    result = answer(q)
    print(result.answer)
    print("\nSources:")
    for s in result.sources:
        print(f"  p. {s.page} [{s.section}]")

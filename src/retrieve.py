"""Dense retrieval (M1): exact-scan cosine top-k over pgvector (D11, D13 budget)."""

import sys

from llama_index.core.schema import NodeWithScore

from src.config import DEFAULT_EMBED, TOP_K
from src.store import get_index


def retrieve(
    question: str, k: int = TOP_K, embed: str = DEFAULT_EMBED
) -> list[NodeWithScore]:
    retriever = get_index(embed).as_retriever(similarity_top_k=k)
    return retriever.retrieve(question)


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "Which fuel standard does the generator require?"
    for r in retrieve(question):
        print(
            f"{r.score:.3f}  p.{r.node.metadata['page']:>3}  "
            f"[{r.node.metadata.get('section', '?')[:40]}]  "
            f"{r.node.text[:70].replace(chr(10), ' ')}"
        )

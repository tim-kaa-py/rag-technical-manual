from llama_index.core.schema import NodeWithScore, TextNode

from src.generate import build_prompt, sources_from


def _chunk(text: str, page: str, section: str, score: float = 0.9) -> NodeWithScore:
    return NodeWithScore(
        node=TextNode(text=text, metadata={"page": page, "section": section}),
        score=score,
    )


def test_build_prompt_contains_context_question_and_page_labels():
    chunks = [_chunk("Use fuel conforming to EN590.", "43", "5.6 Fuel")]
    prompt = build_prompt("Which fuel standard?", chunks)
    assert "Use fuel conforming to EN590." in prompt
    assert "Which fuel standard?" in prompt
    assert "[p. 43" in prompt  # chunks are labeled so the model can cite pages


def test_sources_from_preserves_order_and_truncates_snippets():
    chunks = [
        _chunk("A" * 500, "43", "5.6 Fuel"),
        _chunk("Short text.", "49", "6 TROUBLESHOOTING"),
    ]
    sources = sources_from(chunks)
    assert [s.page for s in sources] == ["43", "49"]
    assert sources[0].section == "5.6 Fuel"
    assert len(sources[0].snippet) <= 203  # 200 chars + ellipsis

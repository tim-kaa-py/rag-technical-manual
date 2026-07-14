from types import SimpleNamespace

import pytest
from llama_index.core.schema import NodeWithScore, TextNode

from src.generate import _answer_text, build_prompt, format_context, sources_from


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


def test_format_context_labels_blocks_and_is_used_by_build_prompt():
    chunks = [_chunk("Use fuel conforming to EN590.", "43", "5.6 Fuel")]
    context = format_context(chunks)
    assert context.startswith("[p. 43 | 5.6 Fuel]")
    assert "Use fuel conforming to EN590." in context
    assert context in build_prompt("Which fuel standard?", chunks)


def test_sources_from_preserves_order_and_truncates_snippets():
    chunks = [
        _chunk("A" * 500, "43", "5.6 Fuel"),
        _chunk("Short text.", "49", "6 TROUBLESHOOTING"),
    ]
    sources = sources_from(chunks)
    assert [s.page for s in sources] == ["43", "49"]
    assert sources[0].section == "5.6 Fuel"
    assert len(sources[0].snippet) <= 203  # 200 chars + ellipsis


def _response(blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


def test_answer_text_skips_thinking_blocks_and_returns_text():
    resp = _response(
        [
            SimpleNamespace(type="thinking"),
            SimpleNamespace(type="text", text="Use EN590 fuel (p. 43)."),
        ]
    )
    assert _answer_text(resp) == "Use EN590 fuel (p. 43)."


def test_answer_text_raises_when_thinking_consumed_the_whole_budget():
    # adaptive thinking shares max_tokens; truncation mid-thinking leaves no
    # text block — that must fail loudly, never ship as an empty answer
    resp = _response([SimpleNamespace(type="thinking")], stop_reason="max_tokens")
    with pytest.raises(RuntimeError, match="max_tokens"):
        _answer_text(resp)


def test_answer_text_raises_on_empty_text_block():
    resp = _response([SimpleNamespace(type="text", text="  ")])
    with pytest.raises(RuntimeError):
        _answer_text(resp)

from unittest.mock import MagicMock

import pytest
from llama_index.core.schema import MetadataMode, TextNode

import src.multimodal as mm


def _vision_response(text=" caption ", stop_reason="end_turn"):
    block = MagicMock(type="text", text=text)
    return MagicMock(stop_reason=stop_reason, content=[block])


def test_caption_cache_hit_skips_vision_call(tmp_path, monkeypatch):
    # D26/N3: cached captions are byte-stable — no paid call, no sampling wobble
    monkeypatch.setattr(mm, "CAPTIONS_DIR", tmp_path)
    (tmp_path / "p42.md").write_text("cached caption")
    client = MagicMock()
    assert mm.caption_page(client, "42") == "cached caption"
    client.messages.create.assert_not_called()


def test_caption_cache_miss_calls_vision_and_writes_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(mm, "CAPTIONS_DIR", tmp_path)
    monkeypatch.setattr(mm, "_page_image", lambda page: b"png-bytes")
    client = MagicMock()
    client.messages.create.return_value = _vision_response()
    assert mm.caption_page(client, "42") == "caption"
    assert (tmp_path / "p42.md").read_text() == "caption"


def test_truncated_or_empty_caption_raises_and_caches_nothing(tmp_path, monkeypatch):
    # loud failure, mirroring generate's D15 guard: a silently truncated
    # caption would become a silently incomplete grounding root
    monkeypatch.setattr(mm, "CAPTIONS_DIR", tmp_path)
    monkeypatch.setattr(mm, "_page_image", lambda page: b"png-bytes")
    client = MagicMock()
    client.messages.create.return_value = _vision_response(stop_reason="max_tokens")
    with pytest.raises(RuntimeError, match="caption incomplete"):
        mm.caption_page(client, "42")
    client.messages.create.return_value = _vision_response(text="   ")
    with pytest.raises(RuntimeError, match="caption incomplete"):
        mm.caption_page(client, "42")
    assert not (tmp_path / "p42.md").exists()


def test_page_specs_cover_the_five_image_bound_pages():
    # D25 scope; 50/51 ship the p. 49 image for column-header context
    assert set(mm.PAGE_SPECS) == {"42", "48", "49", "50", "51"}
    assert mm.PAGE_SPECS["50"]["context_pages"] == ["49"]
    assert mm.PAGE_SPECS["51"]["context_pages"] == ["49"]


def test_caption_node_id_deterministic_and_page_scoped():
    # D26: re-running src.multimodal must REPLACE captions, never duplicate
    assert mm.caption_node_id("42") == mm.caption_node_id("42")
    assert mm.caption_node_id("42") != mm.caption_node_id("48")


def test_caption_node_round_trips_through_load_nodes_reconstruction():
    # D12: RRF dedups by node.hash — a caption node rebuilt from Postgres by
    # store.load_nodes must hash identically to the inserted original
    node = mm.build_node("42", "SAE grades by ambient temperature range")
    rebuilt = TextNode(
        id_=node.node_id,
        text=node.text,
        metadata={"page": node.metadata["page"], "section": node.metadata["section"]},
    )
    rebuilt.excluded_embed_metadata_keys = ["page"]
    assert rebuilt.hash == node.hash


def test_caption_node_embeds_section_but_not_page():
    # D20: BM25 tokenizes EMBED-mode content; page numbers are noise tokens
    node = mm.build_node("48", "maintenance schedule transcription")
    embed_text = node.get_content(metadata_mode=MetadataMode.EMBED)
    # the NORMALIZED label form (detect_heading vocabulary) — the raw
    # manual spelling "5.11. General…" must never enter the index
    assert "5.11 General Maintenance Schedule" in embed_text
    assert "48" not in embed_text

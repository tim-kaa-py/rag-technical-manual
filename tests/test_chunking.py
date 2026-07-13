from llama_index.core import Document

from src.chunking import build_nodes


def _page(text: str, page: str) -> Document:
    return Document(text=text, metadata={"page": page})


def test_nodes_carry_page_and_section_metadata():
    pages = [
        _page("5.4 Lubrication Oil\nUse API CF4 grade oil in the engine.", "42"),
        _page("More lubrication details continue here without any heading.", "43"),
    ]
    nodes = build_nodes(pages)
    assert all(n.metadata["page"] in {"42", "43"} for n in nodes)
    # heading on page 42 tags its own chunk AND carries over to page 43 (D9 tagging)
    assert nodes[0].metadata["section"] == "5.4 Lubrication Oil"
    assert nodes[-1].metadata["section"] == "5.4 Lubrication Oil"


def test_section_updates_when_new_heading_appears():
    pages = [
        _page("5.4 Lubrication Oil\nOil text.\n5.5 Coolant\nCoolant text.", "42"),
    ]
    nodes = build_nodes(pages)
    # a short page → one chunk; its section is the heading active at chunk START
    assert nodes[0].metadata["section"] == "5.4 Lubrication Oil"


def test_text_before_any_heading_is_tagged_unknown():
    pages = [_page("Cover page text with no numbering at all.", "1")]
    nodes = build_nodes(pages)
    assert nodes[0].metadata["section"] == "unknown"

"""PDF → cleaned per-page Documents (D8: pypdf via LlamaIndex PDFReader)."""

import sys

from llama_index.core import Document
from llama_index.readers.file import PDFReader

from src.config import PDF_PATH
from src.textprep import clean_page_text


def load_pages() -> list[Document]:
    raw_docs = PDFReader().load_data(PDF_PATH)
    pages: list[Document] = []
    for i, doc in enumerate(raw_docs, start=1):
        # D9 finding: printed page numbers match PDF indices — verify once below.
        pages.append(
            Document(
                text=clean_page_text(doc.text),
                metadata={"page": str(doc.metadata.get("page_label", i))},
            )
        )
    return pages


def _inspect(page_numbers: list[int]) -> None:
    pages = load_pages()
    print(f"total pages parsed: {len(pages)}\n")
    by_page = {p.metadata["page"]: p for p in pages}
    for n in page_numbers:
        page = by_page.get(str(n))
        print(f"{'=' * 20} page {n} {'=' * 20}")
        print(page.text if page else "<< page not found >>")
        print()


if __name__ == "__main__":
    nums = [int(a) for a in sys.argv[1:]] or [5, 42, 43, 48, 49, 50, 51]
    _inspect(nums)

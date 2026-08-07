import pytest

from backend.documents import DocumentExtractionError, chunk_text, extract_document


def test_chunk_text_is_bounded_and_overlaps() -> None:
    text = "\n".join(f"line {index}: " + ("x" * 70) for index in range(40))

    chunks, truncated = chunk_text(
        text,
        chunk_characters=400,
        overlap=50,
        max_chunks=3,
    )

    assert len(chunks) == 3
    assert truncated is True
    assert all(len(chunk) <= 400 for chunk in chunks)


def test_extract_text_document_returns_safe_metadata() -> None:
    document = extract_document("../design.md", b"# Design\n\nA useful architecture.")

    assert document["filename"] == "design.md"
    assert document["extension"] == ".md"
    assert document["chunk_count"] == 1
    assert document["text"].startswith("# Design")
    assert document["estimated_tokens"] > 0


@pytest.mark.parametrize("filename,data", [
    ("malware.exe", b"not allowed"),
    ("empty.txt", b""),
    ("binary.txt", b"hello\x00world"),
])
def test_extract_document_rejects_unsupported_input(filename: str, data: bytes) -> None:
    with pytest.raises(DocumentExtractionError):
        extract_document(filename, data)

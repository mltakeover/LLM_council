import io
import time
import zipfile

import pytest
from docx import Document

from backend.config import MAX_EXTRACTED_CHARACTERS, UPLOAD_MAX_BYTES
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


def _docx_bomb(paragraphs: int = 60000, chars: int = 2000) -> bytes:
    """A structurally valid DOCX whose XML expands far beyond its file size."""

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-'
        'package.relationships+xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/vnd.'
        'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
        'relationships"><Relationship Id="rId1" Type="http://schemas.'
        'openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    body = f"<w:p><w:r><w:t>{'A' * chars}</w:t></w:r></w:p>" * paragraphs
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
        '2006/main"><w:body>' + body + "</w:body></w:document>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def test_decompression_bomb_is_rejected_cheaply() -> None:
    """Regression: the upload limit bounded the compressed input only.

    A 199 KB archive carrying 116 MB of XML passed every check and cost 5.4
    seconds of CPU and 471 MB of memory to extract. Because extraction ran
    inline in an async route, that blocked the whole event loop.

    The ZIP central directory declares the uncompressed size, so this is
    refused without decompressing anything.
    """

    data = _docx_bomb()
    assert len(data) < UPLOAD_MAX_BYTES, "bomb must pass the existing size check"

    started = time.perf_counter()
    with pytest.raises(DocumentExtractionError) as excinfo:
        extract_document("bomb.docx", data)
    elapsed = time.perf_counter() - started

    assert "exceeds" in str(excinfo.value)
    assert elapsed < 1.0, f"rejection took {elapsed:.2f}s, expected near-instant"


def test_ordinary_documents_are_not_rejected() -> None:
    """The guard must not fire on a normal, repetitive business document."""

    document = Document()
    for _ in range(300):
        document.add_paragraph("Repeated boilerplate paragraph. " * 20)
    buffer = io.BytesIO()
    document.save(buffer)

    result = extract_document("ordinary.docx", buffer.getvalue())

    assert result["character_count"] > 0


def test_extracted_text_is_capped() -> None:
    oversized = "x" * (MAX_EXTRACTED_CHARACTERS + 50_000)

    result = extract_document("big.txt", oversized.encode())

    assert result["character_count"] <= MAX_EXTRACTED_CHARACTERS


def test_corrupt_docx_is_reported_clearly() -> None:
    with pytest.raises(DocumentExtractionError) as excinfo:
        extract_document("broken.docx", b"this is not a zip archive at all")

    assert "DOCX" in str(excinfo.value)

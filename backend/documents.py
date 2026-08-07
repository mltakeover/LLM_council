"""Local document extraction and bounded text chunking."""

from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List

from docx import Document
from pypdf import PdfReader

from .config import (
    DOCUMENT_CHUNK_CHARACTERS,
    DOCUMENT_CHUNK_OVERLAP,
    MAX_DOCUMENT_CHUNKS,
    UPLOAD_MAX_BYTES,
)

ALLOWED_EXTENSIONS = {
    ".txt",
    ".md",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
    ".sql",
    ".xml",
    ".html",
    ".css",
    ".pdf",
    ".docx",
}


class DocumentExtractionError(ValueError):
    """Raised when an uploaded document cannot be safely extracted."""


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(BytesIO(data))
    pages = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"[Page {index}]\n{text.strip()}")
    return "\n\n".join(pages)


def _extract_docx(data: bytes) -> str:
    document = Document(BytesIO(data))
    blocks = [paragraph.text.strip() for paragraph in document.paragraphs]

    for table_index, table in enumerate(document.tables, start=1):
        rows = []
        for row in table.rows:
            rows.append(" | ".join(cell.text.strip() for cell in row.cells))
        if rows:
            blocks.append(f"[Table {table_index}]\n" + "\n".join(rows))

    return "\n\n".join(block for block in blocks if block)


def _extract_text(data: bytes) -> str:
    if b"\x00" in data:
        raise DocumentExtractionError(
            "The file appears to be binary and is not a supported document."
        )
    return data.decode("utf-8-sig", errors="replace")


def chunk_text(
    text: str,
    chunk_characters: int = DOCUMENT_CHUNK_CHARACTERS,
    overlap: int = DOCUMENT_CHUNK_OVERLAP,
    max_chunks: int = MAX_DOCUMENT_CHUNKS,
) -> tuple[List[str], bool]:
    """Split text on nearby line boundaries with bounded overlap."""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return [], False

    chunks: List[str] = []
    start = 0
    truncated = False

    while start < len(normalized):
        if len(chunks) >= max_chunks:
            truncated = True
            break

        hard_end = min(start + chunk_characters, len(normalized))
        end = hard_end
        if hard_end < len(normalized):
            newline = normalized.rfind("\n", start + chunk_characters // 2, hard_end)
            if newline > start:
                end = newline

        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)

    return chunks, truncated


def extract_document(filename: str, data: bytes) -> Dict[str, Any]:
    """Extract supported local text without retaining the original bytes."""

    safe_name = Path(filename or "document").name
    extension = Path(safe_name).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise DocumentExtractionError(
            "Unsupported file type. Allowed extensions: "
            + ", ".join(sorted(ALLOWED_EXTENSIONS))
        )

    if not data:
        raise DocumentExtractionError("The uploaded file is empty.")

    if len(data) > UPLOAD_MAX_BYTES:
        raise DocumentExtractionError(
            f"The file exceeds the {UPLOAD_MAX_BYTES} byte upload limit."
        )

    try:
        if extension == ".pdf":
            text = _extract_pdf(data)
        elif extension == ".docx":
            text = _extract_docx(data)
        else:
            text = _extract_text(data)
    except DocumentExtractionError:
        raise
    except Exception as exc:
        raise DocumentExtractionError(
            f"Unable to extract text from {safe_name}: {type(exc).__name__}."
        ) from exc

    if not text.strip():
        raise DocumentExtractionError(
            "No extractable text was found in the uploaded document."
        )

    chunks, truncated = chunk_text(text)
    return {
        "filename": safe_name,
        "extension": extension,
        "size_bytes": len(data),
        "text": text.strip(),
        "chunks": chunks,
        "chunk_count": len(chunks),
        "truncated": truncated,
        "character_count": len(text.strip()),
        "estimated_tokens": max(1, (len(text.strip()) + 3) // 4),
    }

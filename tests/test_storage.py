import json
import os
import uuid

import pytest

from backend import storage
from backend.documents import extract_document


def _open_fd_count() -> int:
    """Count this process's open file descriptors (Linux/macOS only)."""
    return len(os.listdir(f"/proc/{os.getpid()}/fd"))


@pytest.fixture
def isolated_storage(tmp_path):
    database_path = tmp_path / "council.db"
    legacy_path = tmp_path / "legacy"
    legacy_path.mkdir()
    storage.configure_database(str(database_path), str(legacy_path))
    return database_path, legacy_path


@pytest.mark.asyncio
async def test_sqlite_conversation_message_document_lifecycle(isolated_storage) -> None:
    conversation_id = str(uuid.uuid4())
    await storage.create_conversation(conversation_id)
    document = await storage.create_document(
        conversation_id,
        extract_document("design.md", b"# Design\nA reviewable document."),
    )

    await storage.add_user_message(conversation_id, "Review it", [document])
    await storage.add_assistant_message(
        conversation_id,
        [{"model": "ollama:test", "response": "Finding"}],
        [],
        {"model": "ollama:test", "response": "Report", "success": True},
        {"review_profile": "hld"},
    )

    conversation = await storage.get_conversation(conversation_id)
    assert conversation is not None
    assert len(conversation["messages"]) == 2
    assert conversation["messages"][0]["documents"][0]["filename"] == "design.md"
    assert (await storage.get_documents(conversation_id, [document["id"]]))[0]["text"]

    assert await storage.delete_conversation(conversation_id) is True
    assert await storage.list_documents(conversation_id) == []


@pytest.mark.skipif(
    not os.path.isdir("/proc/self/fd"),
    reason="Open-fd introspection via /proc is Linux-only.",
)
@pytest.mark.asyncio
async def test_storage_operations_do_not_leak_connections(isolated_storage) -> None:
    """Regression test: every storage op used to open a sqlite3 connection
    via `with _connect() as connection:` and never close it, since that
    context-manager form only manages the transaction, not the connection
    lifecycle. Left unfixed, this leaks one fd per call - and
    get_all_conversations() leaks one per stored conversation on every
    call, which the model-recommendation feature triggers on every
    debounced keystroke.
    """
    conversation_id = str(uuid.uuid4())
    await storage.create_conversation(conversation_id)

    baseline = _open_fd_count()

    for _ in range(25):
        await storage.add_user_message(conversation_id, "hello")
        await storage.get_conversation(conversation_id)
        await storage.list_conversations()
        await storage.get_all_conversations()

    after = _open_fd_count()

    # A handful of fds can legitimately fluctuate (event loop internals,
    # etc.) - the leak this guards against would add dozens to hundreds
    # over this many calls, so a small constant margin is a safe threshold.
    assert after <= baseline + 5, (
        f"open file descriptors grew from {baseline} to {after} after "
        "100 storage operations - looks like a connection leak"
    )


@pytest.mark.asyncio
async def test_legacy_json_is_imported_once(isolated_storage) -> None:
    _, legacy_path = isolated_storage
    conversation_id = str(uuid.uuid4())
    (legacy_path / f"{conversation_id}.json").write_text(
        json.dumps({
            "id": conversation_id,
            "created_at": "2026-01-01T00:00:00+00:00",
            "title": "Legacy review",
            "messages": [{"role": "user", "content": "Old question"}],
        }),
        encoding="utf-8",
    )

    await storage.initialize()
    await storage.initialize()
    conversation = await storage.get_conversation(conversation_id)

    assert conversation is not None
    assert conversation["title"] == "Legacy review"
    assert len(conversation["messages"]) == 1

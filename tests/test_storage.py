import json
import uuid

import pytest

from backend import storage
from backend.documents import extract_document


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

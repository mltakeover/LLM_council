"""SQLite persistence with one-time import of legacy JSON conversations."""

import asyncio
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from .config import DATA_DIR, DATABASE_PATH

_database_path = DATABASE_PATH
_legacy_data_dir = DATA_DIR
_initialized = False
_initialization_lock = asyncio.Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_valid_conversation_id(conversation_id: str) -> bool:
    try:
        return str(uuid.UUID(conversation_id)) == conversation_id.lower()
    except (ValueError, AttributeError, TypeError):
        return False


def configure_database(path: str, legacy_data_dir: Optional[str] = None) -> None:
    """Point storage at another database; intended for tests and tooling."""

    global _database_path, _legacy_data_dir, _initialized
    _database_path = path
    if legacy_data_dir is not None:
        _legacy_data_dir = legacy_data_dir
    _initialized = False


def _connect() -> sqlite3.Connection:
    database = Path(_database_path)
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


@contextmanager
def _connection() -> Iterator[sqlite3.Connection]:
    """Open a connection, commit/rollback its transaction, and always close it.

    `with sqlite3.Connection(...) as conn:` only manages the transaction
    (commit on success, rollback on exception) - it does NOT close the
    connection. Every call site here used to do exactly that and never
    closed the connection, leaking one file descriptor per storage
    operation for the life of the process (get_all_conversations() alone
    leaks one connection per stored conversation on every call, since it
    opens a fresh one per conversation via this same path). Closing it in
    a `finally` here fixes that for every call site at once.
    """

    connection = _connect()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode = WAL;

        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            title TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            FOREIGN KEY (conversation_id)
                REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, id);

        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            extension TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            character_count INTEGER NOT NULL,
            estimated_tokens INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL,
            truncated INTEGER NOT NULL DEFAULT 0,
            text_content TEXT NOT NULL,
            chunks_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id)
                REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_documents_conversation
            ON documents(conversation_id, created_at);
        """
    )


def _import_legacy_json(connection: sqlite3.Connection) -> int:
    legacy_dir = Path(_legacy_data_dir)
    if not legacy_dir.exists() or not legacy_dir.is_dir():
        return 0

    imported = 0
    for path in sorted(legacy_dir.glob("*.json")):
        try:
            conversation = json.loads(path.read_text(encoding="utf-8"))
            conversation_id = conversation["id"]
            if not _is_valid_conversation_id(conversation_id):
                continue

            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO conversations(id, created_at, title)
                VALUES (?, ?, ?)
                """,
                (
                    conversation_id,
                    conversation.get("created_at") or _utc_now(),
                    conversation.get("title") or "New Conversation",
                ),
            )

            if cursor.rowcount != 1:
                continue

            for message in conversation.get("messages", []):
                connection.execute(
                    """
                    INSERT INTO messages(
                        conversation_id, role, created_at, payload_json
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        conversation_id,
                        message.get("role") or "assistant",
                        _utc_now(),
                        json.dumps(message),
                    ),
                )
            imported += 1
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            continue

    return imported


def _initialize_sync() -> None:
    with _connection() as connection:
        _create_schema(connection)
        _import_legacy_json(connection)
        connection.commit()


async def initialize() -> None:
    global _initialized
    if _initialized:
        return

    async with _initialization_lock:
        if not _initialized:
            await asyncio.to_thread(_initialize_sync)
            _initialized = True


def _conversation_sync(conversation_id: str) -> Optional[Dict[str, Any]]:
    if not _is_valid_conversation_id(conversation_id):
        return None

    with _connection() as connection:
        row = connection.execute(
            "SELECT id, created_at, title FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            return None

        message_rows = connection.execute(
            """
            SELECT payload_json FROM messages
            WHERE conversation_id = ? ORDER BY id
            """,
            (conversation_id,),
        ).fetchall()

    messages = []
    for message_row in message_rows:
        try:
            messages.append(json.loads(message_row["payload_json"]))
        except (json.JSONDecodeError, TypeError):
            continue

    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "title": row["title"],
        "messages": messages,
    }


def _create_conversation_sync(conversation_id: str) -> Dict[str, Any]:
    if not _is_valid_conversation_id(conversation_id):
        raise ValueError("Conversation id must be a UUID.")

    conversation = {
        "id": conversation_id,
        "created_at": _utc_now(),
        "title": "New Conversation",
        "messages": [],
    }
    with _connection() as connection:
        connection.execute(
            """
            INSERT INTO conversations(id, created_at, title)
            VALUES (?, ?, ?)
            """,
            (
                conversation["id"],
                conversation["created_at"],
                conversation["title"],
            ),
        )
    return conversation


async def create_conversation(conversation_id: str) -> Dict[str, Any]:
    await initialize()
    return await asyncio.to_thread(_create_conversation_sync, conversation_id)


async def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    await initialize()
    return await asyncio.to_thread(_conversation_sync, conversation_id)


def _list_conversations_sync() -> List[Dict[str, Any]]:
    with _connection() as connection:
        rows = connection.execute(
            """
            SELECT c.id, c.created_at, c.title, COUNT(m.id) AS message_count
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            GROUP BY c.id, c.created_at, c.title
            ORDER BY c.created_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


async def list_conversations() -> List[Dict[str, Any]]:
    await initialize()
    return await asyncio.to_thread(_list_conversations_sync)


def _delete_conversation_sync(conversation_id: str) -> bool:
    if not _is_valid_conversation_id(conversation_id):
        return False
    with _connection() as connection:
        cursor = connection.execute(
            "DELETE FROM conversations WHERE id = ?",
            (conversation_id,),
        )
    return cursor.rowcount == 1


async def delete_conversation(conversation_id: str) -> bool:
    await initialize()
    return await asyncio.to_thread(_delete_conversation_sync, conversation_id)


def _insert_message_sync(
    conversation_id: str,
    message: Dict[str, Any],
) -> None:
    if not _is_valid_conversation_id(conversation_id):
        raise ValueError("Conversation id must be a UUID.")
    with _connection() as connection:
        cursor = connection.execute(
            "SELECT 1 FROM conversations WHERE id = ?",
            (conversation_id,),
        )
        if cursor.fetchone() is None:
            raise ValueError(f"Conversation {conversation_id} not found")
        connection.execute(
            """
            INSERT INTO messages(
                conversation_id, role, created_at, payload_json
            ) VALUES (?, ?, ?, ?)
            """,
            (
                conversation_id,
                message["role"],
                _utc_now(),
                json.dumps(message),
            ),
        )


async def add_user_message(
    conversation_id: str,
    content: str,
    documents: Optional[List[Dict[str, Any]]] = None,
) -> None:
    await initialize()
    message: Dict[str, Any] = {"role": "user", "content": content}
    if documents:
        message["documents"] = [
            {
                "id": document["id"],
                "filename": document["filename"],
                "character_count": document["character_count"],
            }
            for document in documents
        ]
    await asyncio.to_thread(_insert_message_sync, conversation_id, message)


async def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any],
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    await initialize()
    message = {
        "role": "assistant",
        "stage1": stage1,
        "stage2": stage2,
        "stage3": stage3,
        "metadata": metadata,
    }
    await asyncio.to_thread(_insert_message_sync, conversation_id, message)


def _update_title_sync(conversation_id: str, title: str) -> None:
    if not _is_valid_conversation_id(conversation_id):
        raise ValueError("Conversation id must be a UUID.")
    with _connection() as connection:
        cursor = connection.execute(
            "UPDATE conversations SET title = ? WHERE id = ?",
            (title, conversation_id),
        )
    if cursor.rowcount != 1:
        raise ValueError(f"Conversation {conversation_id} not found")


async def update_conversation_title(conversation_id: str, title: str) -> None:
    await initialize()
    await asyncio.to_thread(_update_title_sync, conversation_id, title)


def _all_conversations_sync() -> List[Dict[str, Any]]:
    with _connection() as connection:
        ids = [
            row["id"]
            for row in connection.execute(
                "SELECT id FROM conversations ORDER BY created_at DESC"
            ).fetchall()
        ]
    return [
        conversation
        for conversation_id in ids
        if (conversation := _conversation_sync(conversation_id)) is not None
    ]


async def get_all_conversations() -> List[Dict[str, Any]]:
    await initialize()
    return await asyncio.to_thread(_all_conversations_sync)


def _create_document_sync(
    conversation_id: str,
    extracted: Dict[str, Any],
) -> Dict[str, Any]:
    if not _is_valid_conversation_id(conversation_id):
        raise ValueError("Conversation id must be a UUID.")

    document_id = str(uuid.uuid4())
    created_at = _utc_now()
    with _connection() as connection:
        exists = connection.execute(
            "SELECT 1 FROM conversations WHERE id = ?",
            (conversation_id,),
        ).fetchone()
        if exists is None:
            raise ValueError(f"Conversation {conversation_id} not found")
        connection.execute(
            """
            INSERT INTO documents(
                id, conversation_id, filename, extension, size_bytes,
                character_count, estimated_tokens, chunk_count, truncated,
                text_content, chunks_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                conversation_id,
                extracted["filename"],
                extracted["extension"],
                extracted["size_bytes"],
                extracted["character_count"],
                extracted["estimated_tokens"],
                extracted["chunk_count"],
                int(bool(extracted["truncated"])),
                extracted["text"],
                json.dumps(extracted["chunks"]),
                created_at,
            ),
        )

    return {
        "id": document_id,
        "conversation_id": conversation_id,
        "filename": extracted["filename"],
        "extension": extracted["extension"],
        "size_bytes": extracted["size_bytes"],
        "character_count": extracted["character_count"],
        "estimated_tokens": extracted["estimated_tokens"],
        "chunk_count": extracted["chunk_count"],
        "truncated": bool(extracted["truncated"]),
        "created_at": created_at,
    }


async def create_document(
    conversation_id: str,
    extracted: Dict[str, Any],
) -> Dict[str, Any]:
    await initialize()
    return await asyncio.to_thread(
        _create_document_sync,
        conversation_id,
        extracted,
    )


def _documents_sync(
    conversation_id: str,
    document_ids: Optional[List[str]] = None,
    include_content: bool = False,
) -> List[Dict[str, Any]]:
    if not _is_valid_conversation_id(conversation_id):
        return []

    columns = """
        id, conversation_id, filename, extension, size_bytes,
        character_count, estimated_tokens, chunk_count, truncated, created_at
    """
    parameters: List[Any] = [conversation_id]
    where = "conversation_id = ?"

    if document_ids is not None:
        if not document_ids:
            return []
        placeholders = ",".join("?" for _ in document_ids)
        where += f" AND id IN ({placeholders})"
        parameters.extend(document_ids)

    if include_content:
        columns += ", text_content, chunks_json"

    with _connection() as connection:
        rows = connection.execute(
            f"SELECT {columns} FROM documents WHERE {where} ORDER BY created_at",
            parameters,
        ).fetchall()

    documents = []
    for row in rows:
        item = dict(row)
        item["truncated"] = bool(item["truncated"])
        if include_content:
            item["text"] = item.pop("text_content")
            try:
                item["chunks"] = json.loads(item.pop("chunks_json"))
            except (json.JSONDecodeError, TypeError):
                item["chunks"] = []
        documents.append(item)
    return documents


async def list_documents(conversation_id: str) -> List[Dict[str, Any]]:
    await initialize()
    return await asyncio.to_thread(_documents_sync, conversation_id)


async def get_documents(
    conversation_id: str,
    document_ids: List[str],
) -> List[Dict[str, Any]]:
    await initialize()
    return await asyncio.to_thread(
        _documents_sync,
        conversation_id,
        document_ids,
        True,
    )


def _delete_document_sync(conversation_id: str, document_id: str) -> bool:
    if not _is_valid_conversation_id(conversation_id):
        return False
    with _connection() as connection:
        cursor = connection.execute(
            "DELETE FROM documents WHERE id = ? AND conversation_id = ?",
            (document_id, conversation_id),
        )
    return cursor.rowcount == 1


async def delete_document(conversation_id: str, document_id: str) -> bool:
    await initialize()
    return await asyncio.to_thread(
        _delete_document_sync,
        conversation_id,
        document_id,
    )

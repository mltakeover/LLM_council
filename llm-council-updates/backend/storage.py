"""JSON-based storage for conversations.

All public functions are async: file I/O runs on a worker thread via
asyncio.to_thread so a slow disk never blocks the event loop, writes to a
given conversation are serialized with a per-conversation lock to avoid a
lost-update race between concurrent requests, and conversation *listing*
metadata is kept in an in-memory cache instead of re-parsing every
conversation file on every request.
"""

import asyncio
import json
import os
import uuid
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from .config import DATA_DIR


# One lock per conversation id, created lazily. Guarantees that concurrent
# add_user_message / add_assistant_message / update_conversation_title calls
# against the same conversation read-modify-write in order rather than
# clobbering each other.
_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

# Lazily-built cache of list_conversations() metadata, keyed by conversation
# id. Populated by scanning DATA_DIR once, then kept in sync in memory by
# every write in this module so list_conversations() never has to re-read
# and re-parse every conversation file just to show the sidebar.
_metadata_cache: Optional[Dict[str, Dict[str, Any]]] = None


def ensure_data_dir():
    """Ensure the data directory exists."""
    Path(DATA_DIR).mkdir(parents=True, exist_ok=True)


def _is_valid_conversation_id(conversation_id: str) -> bool:
    """Conversation IDs are always UUIDs minted by create_conversation.

    Rejecting anything else here stops a crafted id (e.g. containing "../")
    from ever reaching get_conversation_path and escaping DATA_DIR.
    """
    try:
        uuid.UUID(conversation_id)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def get_conversation_path(conversation_id: str) -> str:
    """Get the file path for a conversation.

    Raises ValueError for anything that isn't a plain UUID, so a path
    traversal attempt (e.g. "../../etc/passwd") can never be joined onto
    DATA_DIR in the first place.
    """
    if not _is_valid_conversation_id(conversation_id):
        raise ValueError(f"Invalid conversation id: {conversation_id!r}")

    return os.path.join(DATA_DIR, f"{conversation_id}.json")


def _metadata_from(conversation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": conversation["id"],
        "created_at": conversation["created_at"],
        "title": conversation.get("title", "New Conversation"),
        "message_count": len(conversation["messages"]),
    }


def _write_conversation_sync(conversation: Dict[str, Any]) -> None:
    ensure_data_dir()
    path = get_conversation_path(conversation["id"])
    with open(path, "w") as f:
        json.dump(conversation, f, indent=2)


def _read_conversation_sync(conversation_id: str) -> Optional[Dict[str, Any]]:
    try:
        path = get_conversation_path(conversation_id)
    except ValueError:
        # Malformed/malicious id (e.g. path traversal attempt) is treated
        # the same as "not found" rather than surfacing a 500.
        return None

    if not os.path.exists(path):
        return None

    with open(path, "r") as f:
        return json.load(f)


def _delete_conversation_sync(conversation_id: str) -> bool:
    try:
        path = get_conversation_path(conversation_id)
    except ValueError:
        return False

    if not os.path.exists(path):
        return False

    os.remove(path)
    return True


def _scan_all_metadata_sync() -> Dict[str, Dict[str, Any]]:
    ensure_data_dir()
    cache: Dict[str, Dict[str, Any]] = {}

    for filename in os.listdir(DATA_DIR):
        if not filename.endswith(".json"):
            continue

        path = os.path.join(DATA_DIR, filename)
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        cache[data["id"]] = _metadata_from(data)

    return cache


async def _ensure_metadata_cache() -> Dict[str, Dict[str, Any]]:
    global _metadata_cache
    if _metadata_cache is None:
        _metadata_cache = await asyncio.to_thread(_scan_all_metadata_sync)
    return _metadata_cache


async def create_conversation(conversation_id: str) -> Dict[str, Any]:
    """
    Create a new conversation.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        New conversation dict
    """
    conversation = {
        "id": conversation_id,
        "created_at": datetime.utcnow().isoformat(),
        "title": "New Conversation",
        "messages": [],
    }

    await asyncio.to_thread(_write_conversation_sync, conversation)

    cache = await _ensure_metadata_cache()
    cache[conversation_id] = _metadata_from(conversation)

    return conversation


async def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a conversation from storage.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        Conversation dict or None if not found
    """
    return await asyncio.to_thread(_read_conversation_sync, conversation_id)


async def save_conversation(conversation: Dict[str, Any]) -> None:
    """
    Save a conversation to storage.

    Args:
        conversation: Conversation dict to save
    """
    await asyncio.to_thread(_write_conversation_sync, conversation)

    cache = await _ensure_metadata_cache()
    cache[conversation["id"]] = _metadata_from(conversation)


async def delete_conversation(conversation_id: str) -> bool:
    """
    Delete a conversation.

    Args:
        conversation_id: Unique identifier for the conversation

    Returns:
        True if a conversation was deleted, False if it didn't exist
    """
    deleted = await asyncio.to_thread(_delete_conversation_sync, conversation_id)

    if deleted:
        cache = await _ensure_metadata_cache()
        cache.pop(conversation_id, None)
        _locks.pop(conversation_id, None)

    return deleted


async def list_conversations() -> List[Dict[str, Any]]:
    """
    List all conversations (metadata only).

    Returns:
        List of conversation metadata dicts
    """
    cache = await _ensure_metadata_cache()
    conversations = list(cache.values())

    # Sort by creation time, newest first
    conversations.sort(key=lambda x: x["created_at"], reverse=True)

    return conversations


async def add_user_message(conversation_id: str, content: str):
    """
    Add a user message to a conversation.

    Args:
        conversation_id: Conversation identifier
        content: User message content
    """
    async with _locks[conversation_id]:
        conversation = await get_conversation(conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        conversation["messages"].append({
            "role": "user",
            "content": content,
        })

        await save_conversation(conversation)


async def add_assistant_message(
    conversation_id: str,
    stage1: List[Dict[str, Any]],
    stage2: List[Dict[str, Any]],
    stage3: Dict[str, Any],
):
    """
    Add an assistant message with all 3 stages to a conversation.

    Args:
        conversation_id: Conversation identifier
        stage1: List of individual model responses
        stage2: List of model rankings
        stage3: Final synthesized response
    """
    async with _locks[conversation_id]:
        conversation = await get_conversation(conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        conversation["messages"].append({
            "role": "assistant",
            "stage1": stage1,
            "stage2": stage2,
            "stage3": stage3,
        })

        await save_conversation(conversation)


async def update_conversation_title(conversation_id: str, title: str):
    """
    Update the title of a conversation.

    Args:
        conversation_id: Conversation identifier
        title: New title for the conversation
    """
    async with _locks[conversation_id]:
        conversation = await get_conversation(conversation_id)
        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        conversation["title"] = title
        await save_conversation(conversation)

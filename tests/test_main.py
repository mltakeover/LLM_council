import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend import main, storage


def test_context_is_newest_first_with_character_bound(monkeypatch) -> None:
    monkeypatch.setattr(main, "MAX_CONTEXT_CHARACTERS", 12)
    conversation = {
        "messages": [
            {"role": "user", "content": "old question"},
            {"role": "assistant", "stage3": {"response": "old answer"}},
            {"role": "user", "content": "new question"},
        ]
    }

    history = main._history_from_conversation(conversation)

    assert history == [{"role": "user", "content": "new question"}]


@pytest.mark.asyncio
async def test_cloud_model_requires_explicit_confirmation(monkeypatch) -> None:
    monkeypatch.setattr(main, "AVAILABLE_CLOUD_MODELS", ["openai:test-model"])
    request = main.SendMessageRequest(
        content="Review this",
        models=["openai:test-model"],
        chairman_model="openai:test-model",
    )

    with pytest.raises(HTTPException) as exc_info:
        await main._resolve_request_models(request)

    assert exc_info.value.status_code == 400
    assert "Confirm cloud processing" in exc_info.value.detail


def test_stream_stops_when_every_model_fails(tmp_path, monkeypatch) -> None:
    storage.configure_database(str(tmp_path / "council.db"), str(tmp_path / "legacy"))

    async def resolve_models(_request):
        return ["ollama:test"], "ollama:test"

    async def no_responses(
        _content,
        _models,
        _history,
        _profile,
        _documents,
        event_callback,
    ):
        await event_callback({
            "type": "model_failed",
            "data": {
                "model": "ollama:test",
                "stage": "stage1",
                "error": {"code": "connection", "message": "offline"},
            },
        })
        return []

    monkeypatch.setattr(main, "_resolve_request_models", resolve_models)
    monkeypatch.setattr(main, "stage1_collect_responses", no_responses)

    with TestClient(main.app) as client:
        conversation_id = str(uuid.uuid4())
        created = client.post("/api/conversations", json={})
        conversation_id = created.json()["id"]
        response = client.post(
            f"/api/conversations/{conversation_id}/message/stream",
            json={"content": "Review this", "models": ["ollama:test"]},
        )

        assert response.status_code == 200
        assert '"type": "model_failed"' in response.text
        assert '"code": "all_models_failed"' in response.text
        assert '"type": "stage2_start"' not in response.text


def test_document_upload_and_usage_estimate(tmp_path) -> None:
    storage.configure_database(str(tmp_path / "documents.db"), str(tmp_path / "legacy"))

    with TestClient(main.app) as client:
        conversation_id = client.post("/api/conversations", json={}).json()["id"]
        upload = client.post(
            f"/api/conversations/{conversation_id}/documents",
            files={"file": ("design.md", b"# Design\n" + (b"evidence\n" * 100), "text/markdown")},
        )

        assert upload.status_code == 200
        document = upload.json()
        estimate = client.post(
            f"/api/conversations/{conversation_id}/usage-estimate",
            json={
                "content": "Review the attached design",
                "models": ["ollama:test"],
                "document_ids": [document["id"]],
                "include_context": False,
            },
        )

        assert estimate.status_code == 200
        assert estimate.json()["document_count"] == 1
        assert estimate.json()["estimated_calls"]["total"] >= 2


def test_model_connectivity_probe_returns_safe_metrics(monkeypatch) -> None:
    async def catalog():
        return {
            "models": [{"id": "ollama:test", "selectable": True}],
        }

    async def query(_model, _messages, **_kwargs):
        return {
            "ok": True,
            "elapsed_seconds": 0.25,
            "attempts": 1,
            "usage": {"input_tokens": 8, "output_tokens": 1, "total_tokens": 9},
            "error": None,
        }

    monkeypatch.setattr(main, "get_models", catalog)
    monkeypatch.setattr(main, "query_model", query)

    with TestClient(main.app) as client:
        response = client.post("/api/models/test", json={"model": "ollama:test"})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["usage"]["total_tokens"] == 9

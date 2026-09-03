import asyncio
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
async def test_existing_default_titles_are_backfilled(tmp_path) -> None:
    storage.configure_database(
        str(tmp_path / "titles.db"),
        str(tmp_path / "legacy"),
    )
    conversation_id = str(uuid.uuid4())
    await storage.create_conversation(conversation_id)
    await storage.add_user_message(
        conversation_id,
        "Please compare local Ollama models for document analysis",
    )

    updated = await main._backfill_default_conversation_titles()
    conversation = await storage.get_conversation(conversation_id)

    assert updated == 1
    assert conversation["title"] == "Local Ollama Models Document Analysis Comparison"


@pytest.mark.asyncio
async def test_cloud_model_requires_explicit_confirmation(monkeypatch) -> None:
    async def catalog():
        return {
            "models": [{
                "id": "openai:test-model",
                "selectable": True,
                "is_local": False,
            }],
        }

    monkeypatch.setattr(main, "get_models", catalog)
    request = main.SendMessageRequest(
        content="Review this",
        models=["openai:test-model"],
        chairman_model="openai:test-model",
    )

    with pytest.raises(HTTPException) as exc_info:
        await main._resolve_request_models(request)

    assert exc_info.value.status_code == 400
    assert "Confirm cloud processing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_cloud_title_requires_confirmation_on_first_turn(monkeypatch) -> None:
    async def catalog():
        return {
            "models": [{
                "id": "ollama:test-model",
                "selectable": True,
                "is_local": True,
            }],
        }

    monkeypatch.setattr(main, "get_models", catalog)
    monkeypatch.setattr(main, "TITLE_MODEL", "openai:title-model")
    monkeypatch.setattr(main, "TITLE_MODEL_IS_LOCAL", False)
    request = main.SendMessageRequest(
        content="Review this",
        models=["ollama:test-model"],
        chairman_model="ollama:test-model",
    )

    with pytest.raises(HTTPException) as exc_info:
        await main._resolve_request_models(request, include_title=True)

    assert "openai:title-model (conversation title)" in exc_info.value.detail


@pytest.mark.asyncio
async def test_closing_event_stream_cancels_provider_task() -> None:
    cancelled = asyncio.Event()

    async def provider_work(callback):
        await callback({
            "type": "model_started",
            "data": {"model": "ollama:test", "stage": "stage1"},
        })
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    stream = main._run_with_events(provider_work)
    kind, event = await anext(stream)
    assert kind == "event"
    assert event["type"] == "model_started"

    await stream.aclose()
    await asyncio.wait_for(cancelled.wait(), timeout=1)


def test_stream_stops_when_every_model_fails(tmp_path, monkeypatch) -> None:
    storage.configure_database(str(tmp_path / "council.db"), str(tmp_path / "legacy"))

    async def resolve_models(_request, include_title=False):
        assert isinstance(include_title, bool)
        return ["ollama:test"], "ollama:test"

    async def no_responses(_content, **kwargs):
        event_callback = kwargs["event_callback"]
        assert kwargs["council_mode"] == "review"
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
        run_id = str(uuid.uuid4())
        response = client.post(
            f"/api/conversations/{conversation_id}/message/stream",
            json={
                "run_id": run_id,
                "content": "Review this",
                "models": ["ollama:test"],
            },
        )

        assert response.status_code == 200
        assert '"type": "model_failed"' in response.text
        assert '"code": "all_models_failed"' in response.text
        assert '"type": "stage2_start"' not in response.text
        run = client.get(
            f"/api/conversations/{conversation_id}/runs/{run_id}"
        ).json()
        conversation = client.get(
            f"/api/conversations/{conversation_id}"
        ).json()
        assert run["status"] == "failed"
        assert [message["role"] for message in conversation["messages"]] == [
            "user",
            "assistant",
        ]


def test_hybrid_stream_emits_manager_and_targets_qa(tmp_path, monkeypatch) -> None:
    storage.configure_database(str(tmp_path / "hybrid.db"), str(tmp_path / "legacy"))
    models = ["ollama:a", "ollama:b"]

    async def resolve_models(_request, include_title=False):
        assert isinstance(include_title, bool)
        return models, "ollama:a"

    async def plan(*_args, **_kwargs):
        return {
            "objective": "Create an HLD",
            "assignments": [
                {
                    "model": "ollama:a",
                    "role": "Business analyst",
                    "deliverable": "Scope",
                    "success_criteria": ["Complete"],
                    "dependencies": [],
                },
                {
                    "model": "ollama:b",
                    "role": "Security architect",
                    "deliverable": "Controls",
                    "success_criteria": ["Evidence-based"],
                    "dependencies": ["Scope"],
                },
            ],
            "qa_reviewers": ["ollama:b"],
            "integration_notes": [],
            "source": "manager",
        }

    async def stage1(_content, **_kwargs):
        return [
            {"model": "ollama:a", "role": "Business analyst", "response": "Scope"},
            {"model": "ollama:b", "role": "Security architect", "response": "Controls"},
        ]

    async def stage2(_content, _results, **kwargs):
        assert kwargs["reviewer_models"] == ["ollama:b"]
        return [], {"Response A": "ollama:a", "Response B": "ollama:b"}

    async def stage3(*_args, **_kwargs):
        return {
            "model": "ollama:a",
            "response": "Final HLD",
            "success": True,
            "structured_report": None,
        }

    async def title(_content):
        return "HLD Workforce"

    monkeypatch.setattr(main, "_resolve_request_models", resolve_models)
    monkeypatch.setattr(main, "create_workforce_plan", plan)
    monkeypatch.setattr(main, "stage1_collect_responses", stage1)
    monkeypatch.setattr(main, "stage2_collect_rankings", stage2)
    monkeypatch.setattr(main, "stage3_synthesize_final", stage3)
    monkeypatch.setattr(main, "generate_conversation_title", title)

    with TestClient(main.app) as client:
        conversation_id = client.post("/api/conversations", json={}).json()["id"]
        response = client.post(
            f"/api/conversations/{conversation_id}/message/stream",
            json={
                "run_id": str(uuid.uuid4()),
                "content": "Create an HLD",
                "models": models,
                "orchestration_strategy": "hybrid",
            },
        )
        conversation = client.get(
            f"/api/conversations/{conversation_id}"
        ).json()

    assert response.status_code == 200
    assert '"type": "manager_start"' in response.text
    assert '"type": "manager_complete"' in response.text
    assert '"targeted_qa": true' in response.text
    assert '"type": "complete"' in response.text
    assistant = conversation["messages"][-1]
    assert assistant["metadata"]["orchestration_strategy"] == "hybrid"
    assert assistant["metadata"]["qa_reviewers"] == ["ollama:b"]


def test_general_purpose_catalog_endpoints() -> None:
    with TestClient(main.app) as client:
        modes = client.get("/api/council-modes")
        strategies = client.get("/api/orchestration-strategies")
        evaluations = client.get("/api/evaluations/catalog")

    assert modes.status_code == 200
    assert modes.json()["default"] == "auto"
    assert {mode["id"] for mode in modes.json()["modes"]} >= {
        "ask",
        "review",
        "debate",
        "decide",
        "brainstorm",
        "compare",
        "plan",
        "summarize",
        "fact_check",
    }
    assert len(evaluations.json()["cases"]) == 9
    assert strategies.status_code == 200
    assert strategies.json()["default"] == "hybrid"
    assert {item["id"] for item in strategies.json()["strategies"]} == {
        "council",
        "workforce",
        "hybrid",
    }


def test_send_request_validates_modes_and_role_bounds() -> None:
    with pytest.raises(ValueError):
        main.SendMessageRequest(content="Question", council_mode="unknown")
    with pytest.raises(ValueError):
        main.SendMessageRequest(content="Question", orchestration_strategy="unknown")
    with pytest.raises(ValueError):
        main.SendMessageRequest(content="Question", output_hygiene="aggressive")

    request = main.SendMessageRequest(
        content="Question",
        council_mode="debate",
        orchestration_strategy="hybrid",
        output_hygiene="report",
        role_assignments={"ollama:a": "  Evidence advocate  ", "ollama:b": ""},
    )

    assert request.council_mode == "debate"
    assert request.orchestration_strategy == "hybrid"
    assert request.output_hygiene == "report"
    assert request.role_assignments == {"ollama:a": "Evidence advocate"}


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


def test_usage_estimate_counts_only_stored_document_chunks(tmp_path) -> None:
    storage.configure_database(str(tmp_path / "truncated.db"), str(tmp_path / "legacy"))

    with TestClient(main.app) as client:
        conversation_id = client.post("/api/conversations", json={}).json()["id"]
        upload = client.post(
            f"/api/conversations/{conversation_id}/documents",
            files={"file": ("large.md", b"evidence line\n" * 20000, "text/markdown")},
        )
        assert upload.status_code == 200
        document = upload.json()
        assert document["truncated"] is True

        estimate = client.post(
            f"/api/conversations/{conversation_id}/usage-estimate",
            json={
                "content": "Review the attached design",
                "models": ["ollama:test"],
                "document_ids": [document["id"]],
                "include_context": False,
            },
        ).json()

        assert estimate["truncated_document_count"] == 1
        assert (
            estimate["reviewed_document_characters"]
            < estimate["original_document_characters"]
        )
        assert estimate["source_characters"] == (
            len("Review the attached design")
            + estimate["reviewed_document_characters"]
        )


def test_usage_estimate_reflects_orchestration_call_pattern(tmp_path) -> None:
    storage.configure_database(str(tmp_path / "strategy.db"), str(tmp_path / "legacy"))

    with TestClient(main.app) as client:
        conversation_id = client.post("/api/conversations", json={}).json()["id"]
        base = {
            "content": "Create an HLD",
            "models": ["ollama:a", "ollama:b", "ollama:c"],
            "include_context": False,
        }
        council_estimate = client.post(
            f"/api/conversations/{conversation_id}/usage-estimate",
            json={**base, "orchestration_strategy": "council"},
        ).json()
        workforce_estimate = client.post(
            f"/api/conversations/{conversation_id}/usage-estimate",
            json={**base, "orchestration_strategy": "workforce"},
        ).json()
        hybrid_estimate = client.post(
            f"/api/conversations/{conversation_id}/usage-estimate",
            json={**base, "orchestration_strategy": "hybrid"},
        ).json()

    assert council_estimate["estimated_calls"]["manager"] == 0
    assert council_estimate["estimated_calls"]["stage2"] == 3
    assert workforce_estimate["estimated_calls"]["manager"] == 1
    assert workforce_estimate["estimated_calls"]["stage2"] == 0
    assert hybrid_estimate["estimated_calls"]["manager"] == 1
    assert hybrid_estimate["estimated_calls"]["stage2"] == 2


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

"""FastAPI backend for LLM Council."""

import asyncio
import json
from typing import Any, Dict, List, Optional, Tuple
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import storage
from .config import (
    AVAILABLE_CLOUD_MODELS,
    CHAIRMAN_MODEL,
    COUNCIL_MODELS,
)
from .council import (
    calculate_aggregate_rankings,
    generate_conversation_title,
    run_full_council,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
)
from .providers import list_ollama_models


app = FastAPI(title="LLM Council API")

# Local development only. This supports Vite selecting 5174 or another local
# port when 5173 is already occupied, without allowing remote web origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    """Request to create a new conversation."""

    pass


class SendMessageRequest(BaseModel):
    """Request to run a selected LLM council."""

    content: str
    models: Optional[List[str]] = None
    chairman_model: Optional[str] = None


class ConversationMetadata(BaseModel):
    """Conversation metadata for list view."""

    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    """Full conversation with all messages."""

    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


def _unique_models(models: List[str]) -> List[str]:
    """Remove duplicate or empty model IDs while retaining selection order."""

    return list(
        dict.fromkeys(
            model.strip()
            for model in models
            if model and model.strip()
        )
    )


async def _resolve_request_models(
    request: SendMessageRequest,
) -> Tuple[List[str], str]:
    """Validate UI-selected models against configured and installed models."""

    requested_models = _unique_models(
        request.models
        if request.models is not None
        else list(COUNCIL_MODELS)
    )

    if not requested_models:
        raise HTTPException(
            status_code=400,
            detail="Select at least one council model.",
        )

    requested_chairman = request.chairman_model
    if requested_chairman:
        requested_chairman = requested_chairman.strip()

    active_chairman = (
        requested_chairman
        or (
            CHAIRMAN_MODEL
            if CHAIRMAN_MODEL in requested_models
            else requested_models[0]
        )
    )

    if active_chairman not in requested_models:
        raise HTTPException(
            status_code=400,
            detail="The chairman must be one of the selected council models.",
        )

    allowed_models = set(AVAILABLE_CLOUD_MODELS)
    needs_ollama = any(
        model.startswith("ollama:")
        for model in requested_models
    )

    if needs_ollama:
        try:
            ollama_models = await list_ollama_models()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Ollama is unavailable. Confirm that Ollama is running "
                    "on the configured local URL."
                ),
            ) from exc

        allowed_models.update(
            model["id"]
            for model in ollama_models
            if model["selectable"]
        )

    invalid_models = [
        model
        for model in requested_models
        if model not in allowed_models
    ]

    if invalid_models:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unavailable or unapproved model selection: "
                + ", ".join(invalid_models)
            ),
        )

    return requested_models, active_chairman


@app.get("/")
async def root():
    """Health check endpoint."""

    return {"status": "ok", "service": "LLM Council API"}


@app.get("/api/models")
async def get_models():
    """Return configured cloud models and dynamically discovered Ollama models."""

    cloud_models = []
    for model_id in AVAILABLE_CLOUD_MODELS:
        provider, model_name = model_id.split(":", 1)
        cloud_models.append({
            "id": model_id,
            "name": model_name,
            "provider": provider,
            "source": "direct-api",
            "is_local": False,
            "is_cloud": True,
            "selectable": True,
            "size": None,
            "parameter_size": None,
            "quantization": None,
            "configured": model_id in COUNCIL_MODELS,
        })

    ollama_online = True
    ollama_error = None
    try:
        ollama_models = await list_ollama_models()
    except Exception:
        ollama_models = []
        ollama_online = False
        ollama_error = (
            "Ollama could not be reached. Start Ollama and refresh models."
        )

    for model in ollama_models:
        model["configured"] = model["id"] in COUNCIL_MODELS

    all_models = cloud_models + ollama_models
    selectable_ids = {
        model["id"]
        for model in all_models
        if model["selectable"]
    }

    default_models = [
        model
        for model in COUNCIL_MODELS
        if model in selectable_ids
    ]

    if not default_models:
        default_models = [
            model["id"]
            for model in all_models
            if model["selectable"]
        ][:1]

    default_chairman = (
        CHAIRMAN_MODEL
        if CHAIRMAN_MODEL in default_models
        else (default_models[0] if default_models else None)
    )

    return {
        "models": all_models,
        "default_models": default_models,
        "default_chairman_model": default_chairman,
        "ollama_online": ollama_online,
        "ollama_error": ollama_error,
    }


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    """List all conversations (metadata only)."""

    return storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(request: CreateConversationRequest):
    """Create a new conversation."""

    conversation_id = str(uuid.uuid4())
    return storage.create_conversation(conversation_id)


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    """Get a specific conversation with all its messages."""

    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    """Run the council and return all stages in one response."""

    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    models, chairman_model = await _resolve_request_models(request)
    is_first_message = len(conversation["messages"]) == 0
    storage.add_user_message(conversation_id, request.content)

    if is_first_message:
        title = await generate_conversation_title(request.content)
        storage.update_conversation_title(conversation_id, title)

    stage1_results, stage2_results, stage3_result, metadata = (
        await run_full_council(
            request.content,
            models,
            chairman_model,
        )
    )

    storage.add_assistant_message(
        conversation_id,
        stage1_results,
        stage2_results,
        stage3_result,
    )

    return {
        "stage1": stage1_results,
        "stage2": stage2_results,
        "stage3": stage3_result,
        "metadata": metadata,
    }


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(
    conversation_id: str,
    request: SendMessageRequest,
):
    """Run the selected council and stream real stage transitions."""

    conversation = storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    models, chairman_model = await _resolve_request_models(request)
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        title_task = None
        try:
            storage.add_user_message(conversation_id, request.content)

            yield f"data: {json.dumps({'type': 'council_start', 'data': {'models': models, 'chairman_model': chairman_model}})}\n\n"

            if is_first_message:
                title_task = asyncio.create_task(
                    generate_conversation_title(request.content)
                )

            yield f"data: {json.dumps({'type': 'stage1_start', 'data': {'models': models}})}\n\n"
            stage1_results = await stage1_collect_responses(
                request.content,
                models,
            )
            yield f"data: {json.dumps({'type': 'stage1_complete', 'data': stage1_results})}\n\n"

            yield f"data: {json.dumps({'type': 'stage2_start', 'data': {'models': models}})}\n\n"
            stage2_results, label_to_model = await stage2_collect_rankings(
                request.content,
                stage1_results,
                models,
            )
            aggregate_rankings = calculate_aggregate_rankings(
                stage2_results,
                label_to_model,
            )
            yield f"data: {json.dumps({'type': 'stage2_complete', 'data': stage2_results, 'metadata': {'label_to_model': label_to_model, 'aggregate_rankings': aggregate_rankings}})}\n\n"

            yield f"data: {json.dumps({'type': 'stage3_start', 'data': {'chairman_model': chairman_model}})}\n\n"
            stage3_result = await stage3_synthesize_final(
                request.content,
                stage1_results,
                stage2_results,
                chairman_model,
            )
            yield f"data: {json.dumps({'type': 'stage3_complete', 'data': stage3_result})}\n\n"

            if title_task:
                title = await title_task
                storage.update_conversation_title(conversation_id, title)
                yield f"data: {json.dumps({'type': 'title_complete', 'data': {'title': title}})}\n\n"

            storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result,
            )

            yield f"data: {json.dumps({'type': 'complete', 'data': {'models': models, 'chairman_model': chairman_model}})}\n\n"

        except Exception as exc:
            if title_task and not title_task.done():
                title_task.cancel()
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)


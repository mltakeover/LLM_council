"""FastAPI backend for the local LLM Council."""

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager, suppress
from typing import Annotated, Any, AsyncIterator, Awaitable, Dict, List, Optional, Tuple

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from . import storage
from .config import (
    APP_HOST,
    AVAILABLE_CLOUD_MODELS,
    CHAIRMAN_MODEL,
    COUNCIL_MODELS,
    EXTRACTION_TIMEOUT_SECONDS,
    MAX_CONTEXT_CHARACTERS,
    MAX_COUNCIL_MODELS,
    MAX_DOCUMENTS_PER_MESSAGE,
    MAX_PROMPT_CHARACTERS,
    OLLAMA_ENDPOINT_IS_LOCAL,
    TITLE_MODEL,
    TITLE_MODEL_IS_LOCAL,
    UPLOAD_MAX_BYTES,
)
from .council import (
    calculate_aggregate_rankings,
    calculate_consensus_metrics,
    create_fallback_conversation_title,
    generate_conversation_title,
    get_model_recommendations,
    run_full_council,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
)
from .council_modes import (
    is_valid_council_mode,
    list_council_modes,
    resolve_council_mode,
    resolve_role_assignments,
)
from .documents import DocumentExtractionError, extract_document
from .evaluations import list_evaluation_cases
from .providers import list_ollama_models, query_model
from .review_profiles import (
    get_review_profile,
    is_valid_review_profile,
    list_review_profiles,
)

logger = logging.getLogger(__name__)


async def _backfill_default_conversation_titles() -> int:
    """Give existing conversations a useful title without making model calls."""

    updated = 0
    for conversation in await storage.get_all_conversations():
        if conversation.get("title") != "New Conversation":
            continue
        first_question = next(
            (
                message.get("content", "")
                for message in conversation.get("messages", [])
                if message.get("role") == "user" and message.get("content", "").strip()
            ),
            "",
        )
        if not first_question:
            continue
        await storage.update_conversation_title(
            conversation["id"],
            create_fallback_conversation_title(first_question),
        )
        updated += 1
    return updated


@asynccontextmanager
async def lifespan(_: FastAPI):
    await storage.initialize()
    updated_titles = await _backfill_default_conversation_titles()
    if updated_titles:
        logger.info("Backfilled conversation titles count=%s", updated_titles)
    yield


app = FastAPI(title="LLM Council API", version="0.4.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateConversationRequest(BaseModel):
    pass


def _normalized_review_profile(value: str) -> str:
    normalized = value.strip().lower()
    if not is_valid_review_profile(normalized):
        raise ValueError("unknown review profile")
    return normalized


def _normalized_council_mode(value: str) -> str:
    normalized = value.strip().lower()
    if not is_valid_council_mode(normalized):
        raise ValueError("unknown council mode")
    return normalized


class SendMessageRequest(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str = Field(min_length=1, max_length=MAX_PROMPT_CHARACTERS)
    models: Optional[List[str]] = None
    chairman_model: Optional[str] = None
    council_mode: str = "auto"
    review_profile: str = "general"
    role_assignments: Dict[str, str] = Field(default_factory=dict)
    include_context: bool = True
    cloud_processing_confirmed: bool = False
    document_ids: List[str] = Field(
        default_factory=list,
        max_length=MAX_DOCUMENTS_PER_MESSAGE,
    )

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("content cannot be blank")
        return stripped

    @field_validator("run_id")
    @classmethod
    def run_id_must_be_uuid(cls, value: str) -> str:
        try:
            return str(uuid.UUID(value))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ValueError("run_id must be a UUID") from exc

    @field_validator("review_profile")
    @classmethod
    def profile_must_exist(cls, value: str) -> str:
        return _normalized_review_profile(value)

    @field_validator("council_mode")
    @classmethod
    def mode_must_exist(cls, value: str) -> str:
        return _normalized_council_mode(value)

    @field_validator("role_assignments")
    @classmethod
    def roles_must_be_bounded(cls, value: Dict[str, str]) -> Dict[str, str]:
        if len(value) > MAX_COUNCIL_MODELS:
            raise ValueError("too many role assignments")
        normalized: Dict[str, str] = {}
        for model, role in value.items():
            model_id = str(model).strip()
            role_text = str(role).strip()
            if not model_id or not role_text:
                continue
            if len(model_id) > 300 or len(role_text) > 160:
                raise ValueError("role assignments exceed the allowed length")
            normalized[model_id] = role_text
        return normalized


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class RecommendModelsRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_PROMPT_CHARACTERS)
    council_mode: str = "auto"
    review_profile: str = "general"

    @field_validator("review_profile")
    @classmethod
    def profile_must_exist(cls, value: str) -> str:
        return _normalized_review_profile(value)

    @field_validator("council_mode")
    @classmethod
    def mode_must_exist(cls, value: str) -> str:
        return _normalized_council_mode(value)


class TestModelRequest(BaseModel):
    model: str = Field(min_length=3, max_length=300)

    @field_validator("model")
    @classmethod
    def model_must_use_provider_prefix(cls, value: str) -> str:
        normalized = value.strip()
        if ":" not in normalized:
            raise ValueError("model must use provider:model-name format")
        return normalized


class UsageEstimateRequest(BaseModel):
    content: str = Field(default="", max_length=MAX_PROMPT_CHARACTERS)
    models: List[str] = Field(default_factory=list)
    document_ids: List[str] = Field(
        default_factory=list,
        max_length=MAX_DOCUMENTS_PER_MESSAGE,
    )
    include_context: bool = True
    council_mode: str = "auto"
    review_profile: str = "general"

    @field_validator("council_mode")
    @classmethod
    def mode_must_exist(cls, value: str) -> str:
        return _normalized_council_mode(value)

    @field_validator("review_profile")
    @classmethod
    def profile_must_exist(cls, value: str) -> str:
        return _normalized_review_profile(value)


class ConversationMetadata(BaseModel):
    id: str
    created_at: str
    title: str
    message_count: int


class Conversation(BaseModel):
    id: str
    created_at: str
    title: str
    messages: List[Dict[str, Any]]


def _history_from_conversation(
    conversation: Dict[str, Any],
    exclude_run_id: Optional[str] = None,
) -> List[Dict[str, str]]:
    """Return the newest complete turns within the configured context bound."""

    history: List[Dict[str, str]] = []
    for message in conversation.get("messages", []):
        if exclude_run_id and message.get("run_id") == exclude_run_id:
            continue
        if message.get("role") == "user":
            content = message.get("content", "")
            if content:
                history.append({"role": "user", "content": content})
        elif message.get("role") == "assistant":
            response = (message.get("stage3") or {}).get("response")
            if response:
                history.append({"role": "assistant", "content": response})

    bounded_reversed: List[Dict[str, str]] = []
    used = 0
    for message in reversed(history):
        remaining = MAX_CONTEXT_CHARACTERS - used
        if remaining <= 0:
            break
        content = message["content"]
        if len(content) > remaining:
            if bounded_reversed:
                break
            content = content[-remaining:]
        bounded_reversed.append({**message, "content": content})
        used += len(content)
    return list(reversed(bounded_reversed))


def _unique_models(models: List[str]) -> List[str]:
    return list(dict.fromkeys(
        model.strip() for model in models if model and model.strip()
    ))


async def _resolve_request_models(
    request: SendMessageRequest,
    include_title: bool = False,
) -> Tuple[List[str], str]:
    requested_models = _unique_models(
        request.models if request.models is not None else list(COUNCIL_MODELS)
    )
    if not requested_models:
        raise HTTPException(status_code=400, detail="Select at least one council model.")
    if len(requested_models) > MAX_COUNCIL_MODELS:
        raise HTTPException(
            status_code=400,
            detail=f"Select no more than {MAX_COUNCIL_MODELS} council models.",
        )
    unknown_role_models = sorted(set(request.role_assignments) - set(requested_models))
    if unknown_role_models:
        raise HTTPException(
            status_code=400,
            detail=(
                "Role assignments must belong to selected council models: "
                + ", ".join(unknown_role_models)
            ),
        )

    requested_chairman = (request.chairman_model or "").strip() or None
    active_chairman = requested_chairman or (
        CHAIRMAN_MODEL if CHAIRMAN_MODEL in requested_models else requested_models[0]
    )
    if active_chairman not in requested_models:
        raise HTTPException(
            status_code=400,
            detail="The chairman must be one of the selected council models.",
        )

    catalog = await get_models()
    available_models = {
        model["id"]: model
        for model in catalog["models"]
        if model.get("selectable")
    }
    invalid_models = [model for model in requested_models if model not in available_models]
    if invalid_models:
        if (
            catalog.get("ollama_online") is False
            and any(model.startswith("ollama:") for model in invalid_models)
        ):
            raise HTTPException(
                status_code=503,
                detail="Ollama is unavailable. Confirm that Ollama is running.",
            )
        raise HTTPException(
            status_code=400,
            detail="Unavailable model selection: " + ", ".join(invalid_models),
        )

    cloud_destinations = [
        model
        for model in requested_models
        if not available_models[model].get("is_local")
    ]
    if include_title and not TITLE_MODEL_IS_LOCAL:
        cloud_destinations.append(f"{TITLE_MODEL} (conversation title)")
    if cloud_destinations and not request.cloud_processing_confirmed:
        raise HTTPException(
            status_code=400,
            detail=(
                "Confirm cloud processing before sending content to: "
                + ", ".join(cloud_destinations)
            ),
        )
    return requested_models, active_chairman


def _run_request_payload(
    request: SendMessageRequest,
    models: List[str],
    chairman_model: str,
) -> Dict[str, Any]:
    """Canonical run inputs used to make retries idempotent."""

    return {
        "content": request.content,
        "models": models,
        "chairman_model": chairman_model,
        "council_mode": request.council_mode,
        "review_profile": request.review_profile,
        "role_assignments": dict(sorted(request.role_assignments.items())),
        "include_context": request.include_context,
        "document_ids": list(dict.fromkeys(request.document_ids)),
    }


async def _begin_run_or_http_error(
    conversation_id: str,
    request: SendMessageRequest,
    models: List[str],
    chairman_model: str,
    documents: List[Dict[str, Any]],
) -> Dict[str, Any]:
    try:
        return await storage.begin_run(
            conversation_id,
            request.run_id,
            _run_request_payload(request, models, chairman_model),
            documents,
        )
    except storage.RunConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except storage.RunInProgressError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except storage.RunAlreadyCompletedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _failure_stage3(
    error: Dict[str, Any],
    model: str = "error",
) -> Dict[str, Any]:
    return {
        "model": model,
        "response": error["message"],
        "success": False,
        "error": error,
    }


async def _persist_failed_run(
    conversation_id: str,
    run_id: str,
    error: Dict[str, Any],
    stage1: Optional[List[Dict[str, Any]]] = None,
    stage2: Optional[List[Dict[str, Any]]] = None,
    stage3: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    status: str = "failed",
) -> None:
    terminal_stage3 = stage3 or _failure_stage3(error)
    await storage.add_assistant_message(
        conversation_id,
        stage1 or [],
        stage2 or [],
        terminal_stage3,
        metadata,
        run_id=run_id,
    )
    await storage.set_run_status(
        conversation_id,
        run_id,
        status,
        error,
    )


async def _request_documents(
    conversation_id: str,
    document_ids: List[str],
) -> List[Dict[str, Any]]:
    if not document_ids:
        return []
    unique_ids = list(dict.fromkeys(document_ids))
    documents = await storage.get_documents(conversation_id, unique_ids)
    found_ids = {document["id"] for document in documents}
    missing = [document_id for document_id in unique_ids if document_id not in found_ids]
    if missing:
        raise HTTPException(
            status_code=400,
            detail="Unknown document selection: " + ", ".join(missing),
        )
    return documents


def _sse(event_type: str, data: Optional[Dict[str, Any]] = None, **extra: Any) -> str:
    payload: Dict[str, Any] = {"type": event_type}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return f"data: {json.dumps(payload)}\n\n"


async def _drain_provider_events(
    task: Awaitable[Any],
    queue: "asyncio.Queue[Dict[str, Any]]",
) -> AsyncIterator[Dict[str, Any]]:
    running = asyncio.ensure_future(task)
    while not running.done() or not queue.empty():
        try:
            yield await asyncio.wait_for(queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            continue
    await running


async def _run_with_events(
    coroutine_factory: Any,
) -> AsyncIterator[Tuple[str, Any]]:
    queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

    async def callback(event: Dict[str, Any]) -> None:
        await queue.put(event)

    task = asyncio.create_task(coroutine_factory(callback))
    try:
        async for event in _drain_provider_events(task, queue):
            yield "event", event
        yield "result", await task
    finally:
        # Closing an SSE response must stop the underlying provider work too.
        # Without this cleanup, browser cancellation only stopped rendering
        # while Ollama/cloud requests continued in the background.
        if not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


@app.get("/")
async def root():
    return {"status": "ok", "service": "LLM Council API", "version": "0.4.0"}


@app.get("/api/council-modes")
async def get_council_modes():
    return {"modes": list_council_modes(), "default": "auto"}


@app.get("/api/evaluations/catalog")
async def get_evaluation_catalog():
    return {"cases": list_evaluation_cases()}


@app.get("/api/review-profiles")
async def get_review_profiles():
    return {"profiles": list_review_profiles(), "default": "general"}


@app.get("/api/models")
async def get_models():
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
        ollama_error = "Ollama could not be reached. Start Ollama and refresh models."

    for model in ollama_models:
        model["configured"] = model["id"] in COUNCIL_MODELS
    all_models = cloud_models + ollama_models
    selectable_ids = {model["id"] for model in all_models if model["selectable"]}
    default_models = [model for model in COUNCIL_MODELS if model in selectable_ids]
    if not default_models:
        default_models = [model["id"] for model in all_models if model["selectable"]][:1]
    default_chairman = (
        CHAIRMAN_MODEL if CHAIRMAN_MODEL in default_models
        else (default_models[0] if default_models else None)
    )
    return {
        "models": all_models,
        "default_models": default_models,
        "default_chairman_model": default_chairman,
        "title_model": {
            "id": TITLE_MODEL,
            "is_local": TITLE_MODEL_IS_LOCAL,
            "requires_cloud_confirmation": not TITLE_MODEL_IS_LOCAL,
        },
        "ollama_endpoint_is_local": OLLAMA_ENDPOINT_IS_LOCAL,
        "ollama_online": ollama_online,
        "ollama_error": ollama_error,
        "limits": {
            "max_council_models": MAX_COUNCIL_MODELS,
            "max_prompt_characters": MAX_PROMPT_CHARACTERS,
            "max_documents_per_message": MAX_DOCUMENTS_PER_MESSAGE,
        },
    }


@app.post("/api/models/test")
async def test_model(request: TestModelRequest):
    """Run a privacy-safe connectivity probe without conversation content."""

    catalog = await get_models()
    available = {
        model["id"]: model
        for model in catalog["models"]
        if model.get("selectable")
    }
    if request.model not in available:
        raise HTTPException(status_code=400, detail="Model is not currently available")

    result = await query_model(
        request.model,
        [{
            "role": "user",
            "content": "Connectivity check. Reply with the single word OK.",
        }],
        timeout=60,
        stage="health_check",
    )
    return {
        "model": request.model,
        "ok": result.get("ok", False),
        "elapsed_seconds": result.get("elapsed_seconds"),
        "attempts": result.get("attempts"),
        "usage": result.get("usage"),
        "error": result.get("error"),
    }


@app.post("/api/recommend-models")
async def recommend_models(request: RecommendModelsRequest):
    return await get_model_recommendations(
        request.content.strip(),
        request.review_profile,
        council_mode=request.council_mode,
    )


@app.get("/api/conversations", response_model=List[ConversationMetadata])
async def list_conversations():
    return await storage.list_conversations()


@app.post("/api/conversations", response_model=Conversation)
async def create_conversation(_: CreateConversationRequest):
    return await storage.create_conversation(str(uuid.uuid4()))


@app.get("/api/conversations/{conversation_id}", response_model=Conversation)
async def get_conversation(conversation_id: str):
    conversation = await storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@app.get("/api/conversations/{conversation_id}/runs/{run_id}")
async def get_run(conversation_id: str, run_id: str):
    run = await storage.get_run(conversation_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    if not await storage.delete_conversation(conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted", "id": conversation_id}


@app.patch("/api/conversations/{conversation_id}", response_model=Conversation)
async def rename_conversation(
    conversation_id: str,
    request: RenameConversationRequest,
):
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")
    if await storage.get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    await storage.update_conversation_title(conversation_id, title)
    return await storage.get_conversation(conversation_id)


@app.post("/api/conversations/{conversation_id}/documents")
async def upload_document(
    conversation_id: str,
    file: Annotated[UploadFile, File()],
):
    if await storage.get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    data = await file.read(UPLOAD_MAX_BYTES + 1)
    try:
        # Extraction is CPU-bound and can take seconds on a large document.
        # Running it inline would block the event loop, stalling every other
        # request including active council streams, so it goes to a worker
        # thread with a hard timeout.
        extracted = await asyncio.wait_for(
            asyncio.to_thread(
                extract_document,
                file.filename or "document",
                data,
            ),
            timeout=EXTRACTION_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Extraction exceeded {EXTRACTION_TIMEOUT_SECONDS:.0f} seconds "
                "and was abandoned. The document is too complex to process."
            ),
        ) from exc
    except DocumentExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await storage.create_document(conversation_id, extracted)


@app.get("/api/conversations/{conversation_id}/documents")
async def list_documents(conversation_id: str):
    if await storage.get_conversation(conversation_id) is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"documents": await storage.list_documents(conversation_id)}


@app.delete("/api/conversations/{conversation_id}/documents/{document_id}")
async def delete_document(conversation_id: str, document_id: str):
    if not await storage.delete_document(conversation_id, document_id):
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted", "id": document_id}


@app.post("/api/conversations/{conversation_id}/usage-estimate")
async def usage_estimate(
    conversation_id: str,
    request: UsageEstimateRequest,
):
    conversation = await storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    documents = await _request_documents(conversation_id, request.document_ids)
    history = _history_from_conversation(conversation) if request.include_context else []
    models = _unique_models(request.models or list(COUNCIL_MODELS))
    model_count = min(len(models), MAX_COUNCIL_MODELS)
    chunk_count = sum(len(document.get("chunks") or []) for document in documents)
    chunked = chunk_count > 1
    stage1_calls = model_count * ((chunk_count + 1) if chunked else 1)
    stage2_calls = model_count if model_count > 1 else 0
    stage3_calls = 1 if model_count else 0
    title_calls = 1 if conversation.get("title") == "New Conversation" else 0
    reviewed_document_characters = sum(
        sum(len(chunk) for chunk in document.get("chunks") or [])
        for document in documents
    )
    original_document_characters = sum(
        document["character_count"] for document in documents
    )
    source_characters = (
        len(request.content)
        + sum(len(message["content"]) for message in history)
        + reviewed_document_characters
    )
    resolved_mode = resolve_council_mode(
        request.council_mode,
        request.content,
        review_profile=request.review_profile,
    )
    return {
        "requested_council_mode": request.council_mode,
        "council_mode": resolved_mode.id,
        "model_count": model_count,
        "document_count": len(documents),
        "document_chunk_count": chunk_count,
        "chunked_review": chunked,
        "chunked_document_processing": chunked,
        "estimated_calls": {
            "stage1": stage1_calls,
            "stage2": stage2_calls,
            "stage3": stage3_calls,
            "title": title_calls,
            "total": stage1_calls + stage2_calls + stage3_calls + title_calls,
        },
        "source_characters": source_characters,
        "reviewed_document_characters": reviewed_document_characters,
        "original_document_characters": original_document_characters,
        "truncated_document_count": sum(
            bool(document.get("truncated")) for document in documents
        ),
        "estimated_source_tokens": max(1, (source_characters + 3) // 4),
        "caveat": (
            "Token count uses the document chunks that will actually be sent, "
            "is a character-based approximation, and excludes generated answers, "
            "chunk notes, rankings and provider tokenisation."
        ),
    }


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    conversation = await storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    needs_title = conversation.get("title") == "New Conversation"
    models, chairman_model = await _resolve_request_models(
        request,
        include_title=needs_title,
    )
    documents = await _request_documents(conversation_id, request.document_ids)
    history = (
        _history_from_conversation(conversation, request.run_id)
        if request.include_context
        else []
    )
    await _begin_run_or_http_error(
        conversation_id,
        request,
        models,
        chairman_model,
        documents,
    )
    try:
        if needs_title:
            await storage.update_conversation_title(
                conversation_id,
                await generate_conversation_title(request.content),
            )
        stage1, stage2, stage3, metadata = await run_full_council(
            request.content,
            models,
            chairman_model,
            history,
            request.review_profile,
            documents,
            council_mode=request.council_mode,
            role_assignments=request.role_assignments,
        )
        await storage.add_assistant_message(
            conversation_id,
            stage1,
            stage2,
            stage3,
            metadata,
            run_id=request.run_id,
        )
        run_status = "completed" if stage3.get("success") is not False else "failed"
        await storage.set_run_status(
            conversation_id,
            request.run_id,
            run_status,
            stage3.get("error"),
        )
        return {
            "run_id": request.run_id,
            "stage1": stage1,
            "stage2": stage2,
            "stage3": stage3,
            "metadata": metadata,
        }
    except asyncio.CancelledError:
        cancelled = {
            "code": "cancelled",
            "message": "Council request cancelled.",
            "retryable": True,
        }
        await asyncio.shield(_persist_failed_run(
            conversation_id,
            request.run_id,
            cancelled,
            status="cancelled",
        ))
        raise
    except Exception:
        failure = {
            "code": "internal_error",
            "message": "The council stopped because of an internal error.",
            "retryable": True,
        }
        await asyncio.shield(_persist_failed_run(
            conversation_id,
            request.run_id,
            failure,
        ))
        raise


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(
    conversation_id: str,
    request: SendMessageRequest,
):
    conversation = await storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    needs_title = conversation.get("title") == "New Conversation"
    models, chairman_model = await _resolve_request_models(
        request,
        include_title=needs_title,
    )
    documents = await _request_documents(conversation_id, request.document_ids)
    history = (
        _history_from_conversation(conversation, request.run_id)
        if request.include_context
        else []
    )
    run = await _begin_run_or_http_error(
        conversation_id,
        request,
        models,
        chairman_model,
        documents,
    )
    resolved_mode = resolve_council_mode(
        request.council_mode,
        request.content,
        review_profile=request.review_profile,
    )
    assigned_roles = resolve_role_assignments(
        models,
        resolved_mode,
        get_review_profile(request.review_profile),
        request.role_assignments,
    )

    async def event_generator():
        title_task: Optional[asyncio.Task] = None
        provisional_title: Optional[str] = None
        stage1_results: List[Dict[str, Any]] = []
        stage2_results: List[Dict[str, Any]] = []
        stage3_result: Optional[Dict[str, Any]] = None
        turn_metadata: Dict[str, Any] = {
            "models": models,
            "chairman_model": chairman_model,
            "requested_council_mode": request.council_mode,
            "council_mode": resolved_mode.id,
            "review_profile": request.review_profile,
            "role_assignments": assigned_roles,
        }
        run_terminal = False
        try:
            yield _sse("council_start", {
                "run_id": request.run_id,
                "resumed": run["resumed"],
                "models": models,
                "chairman_model": chairman_model,
                "requested_council_mode": request.council_mode,
                "council_mode": resolved_mode.id,
                "review_profile": request.review_profile,
                "role_assignments": assigned_roles,
                "document_count": len(documents),
            })
            if needs_title:
                provisional_title = create_fallback_conversation_title(
                    request.content
                )
                await storage.update_conversation_title(
                    conversation_id,
                    provisional_title,
                )
                yield _sse("title_complete", {
                    "title": provisional_title,
                    "provisional": True,
                })
                title_task = asyncio.create_task(
                    generate_conversation_title(request.content)
                )

            yield _sse("stage1_start", {"models": models})
            collected_stage1 = None
            async for kind, value in _run_with_events(
                lambda callback: stage1_collect_responses(
                    request.content,
                    models=models,
                    history=history,
                    review_profile=request.review_profile,
                    documents=documents,
                    event_callback=callback,
                    council_mode=resolved_mode.id,
                    role_assignments=assigned_roles,
                )
            ):
                if kind == "event":
                    yield _sse(value["type"], value.get("data") or {})
                else:
                    collected_stage1 = value
            stage1_results = collected_stage1 or []
            yield _sse("stage1_complete", stage1_results)

            if not stage1_results:
                failure = {
                    "code": "all_models_failed",
                    "message": "All selected models failed during the answer stage.",
                    "retryable": True,
                }
                stage3_result = _failure_stage3(failure)
                await _persist_failed_run(
                    conversation_id,
                    request.run_id,
                    failure,
                    stage3=stage3_result,
                    metadata=turn_metadata,
                )
                run_terminal = True
                yield _sse("error", error=failure, run_id=request.run_id)
                return

            yield _sse("stage2_start", {"models": models})
            stage2_result = None
            async for kind, value in _run_with_events(
                lambda callback: stage2_collect_rankings(
                    request.content,
                    stage1_results,
                    models=models,
                    history=history,
                    review_profile=request.review_profile,
                    event_callback=callback,
                    council_mode=resolved_mode.id,
                )
            ):
                if kind == "event":
                    yield _sse(value["type"], value.get("data") or {})
                else:
                    stage2_result = value
            stage2_results, label_to_model = stage2_result or ([], {})
            aggregate_rankings = calculate_aggregate_rankings(
                stage2_results,
                label_to_model,
            )
            consensus_metrics = calculate_consensus_metrics(
                stage2_results,
                label_to_model,
            )
            turn_metadata = {
                "label_to_model": label_to_model,
                "aggregate_rankings": aggregate_rankings,
                "consensus_metrics": consensus_metrics,
                "models": models,
                "chairman_model": chairman_model,
                "requested_council_mode": request.council_mode,
                "council_mode": resolved_mode.id,
                "review_profile": request.review_profile,
                "role_assignments": assigned_roles,
                "stage2_skipped": len(stage1_results) <= 1,
            }
            yield _sse(
                "stage2_complete",
                stage2_results,
                metadata=turn_metadata,
            )

            yield _sse("stage3_start", {"chairman_model": chairman_model})
            collected_stage3 = None
            async for kind, value in _run_with_events(
                lambda callback: stage3_synthesize_final(
                    request.content,
                    stage1_results,
                    stage2_results,
                    chairman_model=chairman_model,
                    history=history,
                    review_profile=request.review_profile,
                    event_callback=callback,
                    council_mode=resolved_mode.id,
                )
            ):
                if kind == "event":
                    yield _sse(value["type"], value.get("data") or {})
                else:
                    collected_stage3 = value
            stage3_result = collected_stage3 or _failure_stage3({
                "code": "empty_synthesis",
                "message": "The Chairman did not return a final synthesis.",
                "retryable": True,
            })
            yield _sse("stage3_complete", stage3_result)

            await storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result,
                turn_metadata,
                run_id=request.run_id,
            )
            if stage3_result.get("success") is False:
                stage3_error = stage3_result.get("error") or {
                    "code": "synthesis_failed",
                    "message": "The Chairman failed to produce a final synthesis.",
                    "retryable": True,
                }
                await storage.set_run_status(
                    conversation_id,
                    request.run_id,
                    "failed",
                    stage3_error,
                )
                run_terminal = True
                yield _sse("error", error=stage3_error, run_id=request.run_id)
                return

            await storage.set_run_status(
                conversation_id,
                request.run_id,
                "completed",
            )
            run_terminal = True

            if title_task:
                try:
                    title = await title_task
                    if title != provisional_title:
                        await storage.update_conversation_title(
                            conversation_id,
                            title,
                        )
                        yield _sse("title_complete", {
                            "title": title,
                            "provisional": False,
                        })
                except Exception:
                    logger.exception(
                        "Conversation title update failed conversation=%s",
                        conversation_id,
                    )

            yield _sse("complete", {
                "run_id": request.run_id,
                "models": models,
                "chairman_model": chairman_model,
            })

        except asyncio.CancelledError:
            if not run_terminal:
                cancelled = {
                    "code": "cancelled",
                    "message": "Council request cancelled.",
                    "retryable": True,
                }
                await asyncio.shield(_persist_failed_run(
                    conversation_id,
                    request.run_id,
                    cancelled,
                    stage1_results,
                    stage2_results,
                    stage3_result,
                    turn_metadata,
                    status="cancelled",
                ))
            raise
        except Exception:
            logger.exception("Council stream failed conversation=%s", conversation_id)
            failure = {
                "code": "internal_error",
                "message": "The council stopped because of an internal error.",
                "retryable": True,
            }
            if not run_terminal:
                await asyncio.shield(_persist_failed_run(
                    conversation_id,
                    request.run_id,
                    failure,
                    stage1_results,
                    stage2_results,
                    stage3_result,
                    turn_metadata,
                ))
            yield _sse("error", error=failure, run_id=request.run_id)
        finally:
            if title_task and not title_task.done():
                title_task.cancel()
            if title_task:
                with suppress(asyncio.CancelledError, Exception):
                    await title_task

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

    uvicorn.run(app, host=APP_HOST, port=8001)

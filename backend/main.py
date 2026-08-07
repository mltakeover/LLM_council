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
    MAX_CONTEXT_CHARACTERS,
    MAX_COUNCIL_MODELS,
    MAX_DOCUMENTS_PER_MESSAGE,
    MAX_PROMPT_CHARACTERS,
    UPLOAD_MAX_BYTES,
)
from .council import (
    calculate_aggregate_rankings,
    generate_conversation_title,
    get_model_recommendations,
    run_full_council,
    stage1_collect_responses,
    stage2_collect_rankings,
    stage3_synthesize_final,
)
from .documents import DocumentExtractionError, extract_document
from .providers import list_ollama_models
from .review_profiles import is_valid_review_profile, list_review_profiles

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await storage.initialize()
    yield


app = FastAPI(title="LLM Council API", version="0.2.0", lifespan=lifespan)

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


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_PROMPT_CHARACTERS)
    models: Optional[List[str]] = None
    chairman_model: Optional[str] = None
    review_profile: str = "general"
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

    @field_validator("review_profile")
    @classmethod
    def profile_must_exist(cls, value: str) -> str:
        return _normalized_review_profile(value)


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)


class RecommendModelsRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_PROMPT_CHARACTERS)
    review_profile: str = "general"

    @field_validator("review_profile")
    @classmethod
    def profile_must_exist(cls, value: str) -> str:
        return _normalized_review_profile(value)


class UsageEstimateRequest(BaseModel):
    content: str = Field(default="", max_length=MAX_PROMPT_CHARACTERS)
    models: List[str] = Field(default_factory=list)
    document_ids: List[str] = Field(
        default_factory=list,
        max_length=MAX_DOCUMENTS_PER_MESSAGE,
    )
    include_context: bool = True


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
) -> List[Dict[str, str]]:
    """Return the newest complete turns within the configured context bound."""

    history: List[Dict[str, str]] = []
    for message in conversation.get("messages", []):
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

    requested_chairman = (request.chairman_model or "").strip() or None
    active_chairman = requested_chairman or (
        CHAIRMAN_MODEL if CHAIRMAN_MODEL in requested_models else requested_models[0]
    )
    if active_chairman not in requested_models:
        raise HTTPException(
            status_code=400,
            detail="The chairman must be one of the selected council models.",
        )

    cloud_models = [
        model for model in requested_models if not model.startswith("ollama:")
    ]
    if cloud_models and not request.cloud_processing_confirmed:
        raise HTTPException(
            status_code=400,
            detail=(
                "Confirm cloud processing before sending content to: "
                + ", ".join(cloud_models)
            ),
        )

    allowed_models = set(AVAILABLE_CLOUD_MODELS)
    if any(model.startswith("ollama:") for model in requested_models):
        try:
            ollama_models = await list_ollama_models()
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="Ollama is unavailable. Confirm that Ollama is running.",
            ) from exc
        allowed_models.update(
            model["id"] for model in ollama_models if model["selectable"]
        )

    invalid_models = [model for model in requested_models if model not in allowed_models]
    if invalid_models:
        raise HTTPException(
            status_code=400,
            detail="Unavailable model selection: " + ", ".join(invalid_models),
        )
    return requested_models, active_chairman


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
    async for event in _drain_provider_events(task, queue):
        yield "event", event
    yield "result", await task


@app.get("/")
async def root():
    return {"status": "ok", "service": "LLM Council API", "version": "0.2.0"}


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
        "ollama_online": ollama_online,
        "ollama_error": ollama_error,
        "limits": {
            "max_council_models": MAX_COUNCIL_MODELS,
            "max_prompt_characters": MAX_PROMPT_CHARACTERS,
            "max_documents_per_message": MAX_DOCUMENTS_PER_MESSAGE,
        },
    }


@app.post("/api/recommend-models")
async def recommend_models(request: RecommendModelsRequest):
    return await get_model_recommendations(
        request.content.strip(),
        request.review_profile,
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
        extracted = extract_document(file.filename or "document", data)
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
    title_calls = 1 if not conversation.get("messages") else 0
    source_characters = (
        len(request.content)
        + sum(len(message["content"]) for message in history)
        + sum(document["character_count"] for document in documents)
    )
    return {
        "model_count": model_count,
        "document_count": len(documents),
        "document_chunk_count": chunk_count,
        "chunked_review": chunked,
        "estimated_calls": {
            "stage1": stage1_calls,
            "stage2": stage2_calls,
            "stage3": stage3_calls,
            "title": title_calls,
            "total": stage1_calls + stage2_calls + stage3_calls + title_calls,
        },
        "source_characters": source_characters,
        "estimated_source_tokens": max(1, (source_characters + 3) // 4),
        "caveat": (
            "Token count is a character-based approximation and excludes "
            "generated answers, chunk notes, rankings and provider tokenisation."
        ),
    }


@app.post("/api/conversations/{conversation_id}/message")
async def send_message(conversation_id: str, request: SendMessageRequest):
    conversation = await storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    models, chairman_model = await _resolve_request_models(request)
    documents = await _request_documents(conversation_id, request.document_ids)
    history = _history_from_conversation(conversation) if request.include_context else []
    is_first_message = len(conversation["messages"]) == 0
    await storage.add_user_message(conversation_id, request.content, documents)
    if is_first_message:
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
    )
    await storage.add_assistant_message(
        conversation_id, stage1, stage2, stage3, metadata
    )
    return {"stage1": stage1, "stage2": stage2, "stage3": stage3, "metadata": metadata}


@app.post("/api/conversations/{conversation_id}/message/stream")
async def send_message_stream(
    conversation_id: str,
    request: SendMessageRequest,
):
    conversation = await storage.get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    models, chairman_model = await _resolve_request_models(request)
    documents = await _request_documents(conversation_id, request.document_ids)
    history = _history_from_conversation(conversation) if request.include_context else []
    is_first_message = len(conversation["messages"]) == 0

    async def event_generator():
        title_task: Optional[asyncio.Task] = None
        try:
            await storage.add_user_message(
                conversation_id,
                request.content,
                documents,
            )
            yield _sse("council_start", {
                "models": models,
                "chairman_model": chairman_model,
                "review_profile": request.review_profile,
                "document_count": len(documents),
            })
            if is_first_message:
                title_task = asyncio.create_task(
                    generate_conversation_title(request.content)
                )

            yield _sse("stage1_start", {"models": models})
            stage1_results = None
            async for kind, value in _run_with_events(
                lambda callback: stage1_collect_responses(
                    request.content,
                    models,
                    history,
                    request.review_profile,
                    documents,
                    callback,
                )
            ):
                if kind == "event":
                    yield _sse(value["type"], value.get("data") or {})
                else:
                    stage1_results = value
            stage1_results = stage1_results or []
            yield _sse("stage1_complete", stage1_results)

            if not stage1_results:
                failure = {
                    "code": "all_models_failed",
                    "message": "All selected models failed during the answer stage.",
                    "retryable": True,
                }
                await storage.add_assistant_message(
                    conversation_id,
                    [],
                    [],
                    {
                        "model": "error",
                        "response": failure["message"],
                        "success": False,
                        "error": failure,
                    },
                    {
                        "models": models,
                        "chairman_model": chairman_model,
                        "review_profile": request.review_profile,
                    },
                )
                yield _sse("error", error=failure)
                return

            yield _sse("stage2_start", {"models": models})
            stage2_result = None
            async for kind, value in _run_with_events(
                lambda callback: stage2_collect_rankings(
                    request.content,
                    stage1_results,
                    models,
                    history,
                    request.review_profile,
                    callback,
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
            turn_metadata = {
                "label_to_model": label_to_model,
                "aggregate_rankings": aggregate_rankings,
                "models": models,
                "chairman_model": chairman_model,
                "review_profile": request.review_profile,
                "stage2_skipped": len(stage1_results) <= 1,
            }
            yield _sse(
                "stage2_complete",
                stage2_results,
                metadata=turn_metadata,
            )

            yield _sse("stage3_start", {"chairman_model": chairman_model})
            stage3_result = None
            async for kind, value in _run_with_events(
                lambda callback: stage3_synthesize_final(
                    request.content,
                    stage1_results,
                    stage2_results,
                    chairman_model,
                    history,
                    request.review_profile,
                    callback,
                )
            ):
                if kind == "event":
                    yield _sse(value["type"], value.get("data") or {})
                else:
                    stage3_result = value
            yield _sse("stage3_complete", stage3_result)

            if title_task:
                title = await title_task
                await storage.update_conversation_title(conversation_id, title)
                yield _sse("title_complete", {"title": title})

            await storage.add_assistant_message(
                conversation_id,
                stage1_results,
                stage2_results,
                stage3_result,
                turn_metadata,
            )
            yield _sse("complete", {
                "models": models,
                "chairman_model": chairman_model,
            })

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Council stream failed conversation=%s", conversation_id)
            yield _sse("error", error={
                "code": "internal_error",
                "message": "The council stopped because of an internal error.",
                "retryable": True,
            })
        finally:
            if title_task and not title_task.done():
                title_task.cancel()
                with suppress(asyncio.CancelledError):
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

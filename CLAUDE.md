# LLM Council engineering guide

This file is working context for coding assistants and contributors. The source
of truth is the current code and tests; update this guide whenever architecture
or operational behaviour changes.

## Product summary

LLM Council is a personal, local-first technical review application. A turn has
three stages:

1. selected council models independently answer;
2. successful answers are anonymised and peer-ranked;
3. the selected Chairman returns a structured report and Markdown rendering.

It supports directly configured OpenAI, Anthropic, Google Gemini, and xAI APIs,
plus dynamically discovered Ollama models. It does not use OpenRouter.

## Runtime and commands

- Python 3.10+, FastAPI backend on port 8001
- React 19 and Vite frontend, normally on port 5173
- SQLite at `DATABASE_PATH` (default `data/llm_council.db`)

From the repository root:

```bash
python -m pip install -e '.[dev]'
python -m uvicorn backend.main:app --reload --port 8001
ruff check backend tests
pytest -q
```

From `frontend/`:

```bash
npm ci
npm run dev
npm test
npm run lint
npm run build
```

CI is defined in `.github/workflows/ci.yml` and runs without provider keys.

## Backend map

- `backend/config.py`: environment parsing, provider/model defaults, loopback
  classification, timeouts, context and document limits.
- `backend/providers.py`: direct SDK adapters, Ollama discovery, concurrency,
  retries, normalized results/errors, and model progress callbacks.
- `backend/council.py`: prompts, document map/reduce, anonymous ranking,
  consensus metrics, structured Chairman reports, and model recommendations.
- `backend/main.py`: FastAPI models/routes, privacy validation, SSE orchestration,
  run lifecycle, uploads, usage estimates, and cancellation.
- `backend/storage.py`: SQLite schema/migrations, conversations, messages,
  documents, run idempotency, and one-time legacy JSON import.
- `backend/documents.py`: bounded extraction and chunking for supported files.
- `backend/review_profiles.py`: built-in General, HLD, LLD, Code, and Security
  reviewer instructions.

All backend imports are package-relative. Run with `python -m backend.main` or
Uvicorn from the repository root; do not run `backend/main.py` directly.

## Frontend map

- `src/App.jsx`: catalogue/selection state, SSE event handling, idempotent retry,
  privacy state, conversation orchestration, and progress state.
- `src/api.js`: backend client and chunk-safe SSE parser.
- `src/components/CouncilFlow.jsx`: live per-model progress and details.
- `src/components/ChatInterface.jsx`: composer, files, estimates, confirmation,
  retry/cancel, transcript, and exports.
- `src/components/Stage1.jsx`, `Stage2.jsx`, `Stage3.jsx`: turn inspection.
- `src/components/FindingsDashboard.jsx`, `ConsensusPanel.jsx`: structured
  Chairman report views.
- `src/components/Sidebar.jsx`, `CouncilPresets.jsx`, `ProviderStatus.jsx`:
  model configuration, presets, conversations, and connectivity checks.
- `src/utils/exportConversation.js`: Markdown, DOCX, and PDF exports.

## Critical invariants

### Model IDs and privacy

Model IDs always use `provider:model-name`. Ollama can contain another colon,
for example `ollama:qwen2.5-coder:7b`, so split only on the first colon.

Only an explicit loopback `OLLAMA_BASE_URL` is local. Remote Ollama models are
labelled remote and require cloud-processing confirmation. Ollama cloud entries
(zero size or `-cloud` suffix) are not selectable. Direct cloud models require
confirmation. While a conversation still has its default title, a non-local
`TITLE_MODEL` also requires confirmation and receives the prompt only, never
document text.

Do not log API keys, prompts, document contents, or full provider response
bodies. Provider data retention/training is governed by the user's provider
account, not guaranteed by this application.

### Runs, retries, and cancellation

Every message request carries a UUID `run_id`. `storage.begin_run()` atomically
inserts the run and its user message. The same ID may resume only a failed or
cancelled run with byte-equivalent canonical inputs. It must reject changed,
active, or completed runs. Assistant messages are upserted per run, preventing
duplicate transcript turns.

The SSE generator owns provider tasks. Closing it must cancel and await the
active task. Terminal state is persisted as `completed`, `failed`, or
`cancelled`; startup converts orphaned `running` rows to retryable failures.
Ancillary title failure must not invalidate a completed council result.

### Council stages

Continue when some Stage 1 or Stage 2 models fail. Stop before Stage 2 when all
Stage 1 models fail. Stage 2 labels remain anonymous inside model prompts;
de-anonymise only through persisted `label_to_model` metadata for display and
aggregation. Reject invalid rankings rather than re-parsing a deliberately
empty `parsed_ranking`. Do not invent a single winner for tied top-choice votes.

### Context and documents

Context includes prior user messages and Chairman responses only, newest within
`MAX_CONTEXT_CHARACTERS`. Exclude the current `run_id`, especially on retry.

Uploaded original bytes are discarded after extraction. SQLite retains text
and bounded chunks. A document beyond `MAX_DOCUMENT_CHUNKS` is marked
`truncated`; never hide this status. Usage estimates must count the chunks that
will actually be sent, not discarded source text. Treat user files and model
answers as untrusted evidence in prompts.

## Test expectations

Add regression coverage for behavioural changes. In particular preserve tests
for structured retries, stream cancellation, run idempotency/conflicts,
first-turn title privacy, remote Ollama classification, document truncation,
ranking validation/ties, SQLite migration, SSE terminal errors, and frontend
run ID/export helpers. Tests must not make real provider calls.

Before handing off a change, run the complete backend and frontend commands
listed above and report any check that could not run.

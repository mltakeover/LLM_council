# LLM Council

A local multi-model review application for architecture documents, detailed
designs, source code, technical decisions and general questions.

The application runs a three-stage council:

1. Selected models independently answer the request.
2. The models review and rank the anonymised answers.
3. A selected Chairman produces the final synthesis.

This version supports:

- locally downloaded models through Ollama;
- dynamic Ollama model discovery with no Python changes after `ollama pull`;
- direct calls to OpenAI, Anthropic, Google Gemini and xAI;
- per-request council member and Chairman selection;
- an animated UI showing Answer, Review and Synthesis progress;
- local JSON conversation history; and
- server-sent events for real backend progress updates.

OpenRouter is not used.

## How the council works

For every question, the backend performs the following workflow:

```text
User request
     |
     +--> Stage 1: independent answer from every selected model
     |
     +--> Stage 2: anonymous peer review and ranking
     |
     +--> Stage 3: Chairman synthesis
     |
     +--> Final answer
```

For `N` selected models, a normal council run makes:

```text
N answer calls + N review calls + 1 synthesis call = 2N + 1 calls
```

For three models:

```text
(2 × 3) + 1 = 7 model calls
```

Title generation may make one additional call. Failed calls, retries and
provider-specific behaviour can also change the final number.

## Architecture

```text
React/Vite UI
  - conversations
  - council model selector
  - Chairman selector
  - live council flow
        |
        | HTTP + server-sent events
        v
FastAPI backend — http://127.0.0.1:8001
  - model catalogue
  - request validation
  - three-stage orchestration
  - conversation storage
        |
        +------------------+-----------------------------+
        |                  |                             |
        v                  v                             v
Local Ollama       Direct cloud APIs              Local JSON files
                  OpenAI / Anthropic /            data/conversations/
                  Gemini / xAI
```

## Project structure

```text
LLM_Council/
├── backend/
│   ├── __init__.py
│   ├── main.py                 # FastAPI endpoints and streamed events
│   ├── config.py               # Environment and model configuration
│   ├── providers.py            # Cloud routing and Ollama discovery
│   ├── council.py              # Three-stage council workflow
│   └── storage.py              # Local conversation persistence
├── frontend/
│   ├── package.json
│   └── src/
│       ├── App.jsx             # Main state and streamed progress handling
│       ├── api.js              # Backend API client
│       ├── App.css
│       └── components/
│           ├── ChatInterface.jsx
│           ├── CouncilFlow.jsx
│           ├── CouncilFlow.css
│           ├── Sidebar.jsx
│           └── Sidebar.css
├── data/
│   └── conversations/          # Created automatically
├── .env                        # Local configuration and secrets
├── .env.example                # Safe configuration template
├── .gitignore
├── pyproject.toml
└── README.md
```

## Requirements

- macOS
- Conda or Miniconda
- Python 3.10 or later
- Node.js and npm
- Ollama for local models
- API credentials only for the cloud providers you choose to enable

Check the installed tools:

```bash
conda --version
python --version
node --version
npm --version
ollama --version
```

## Installation on macOS with Conda

### 1. Open the project

```bash
cd /Users/mandeepchana/Library/CloudStorage/Dropbox/Software_Repo/PythonProject/LLM_Council
```

### 2. Create or activate the environment

Create it if needed:

```bash
conda create -n LLM_Council python=3.11 -y
```

Activate it:

```bash
conda activate LLM_Council
```

### 3. Configure Python packaging

Use the following `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=77.0.3"]
build-backend = "setuptools.build_meta"

[project]
name = "llm-council"
version = "0.1.0"
description = "Your LLM Council"
readme = "README.md"
requires-python = ">=3.10"

dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "python-dotenv>=1.0.0",
    "httpx>=0.27.0",
    "pydantic>=2.9.0",
    "openai>=1.55.0",
    "anthropic>=0.40.0",
    "google-genai>=1.0.0",
]

[tool.setuptools.packages.find]
where = ["."]
include = ["backend*"]
exclude = ["frontend*"]
```

The package-discovery section prevents setuptools from trying to package the
React `frontend` directory as a Python package.

Install the backend in editable mode:

```bash
python -m pip install --upgrade pip
python -m pip install -e .
```

Verify the imports:

```bash
python -c "import backend, openai, anthropic; from google import genai; print('Backend dependencies installed')"
```

### 4. Install the frontend

```bash
cd frontend
npm install
cd ..
```

## Local Ollama configuration

The recommended starting configuration is local-only. Create `.env` in the
project root:

```dotenv
COUNCIL_PROVIDERS=ollama

OLLAMA_BASE_URL=http://127.0.0.1:11434/v1/
OLLAMA_MODELS=qwen3.6:latest,qwen2.5-coder:7b,llama3.1:latest
OLLAMA_CHAIRMAN_MODEL=qwen3.6:latest
TITLE_MODEL=ollama:llama3.1:latest

OLLAMA_MAX_CONCURRENCY=1
OLLAMA_DISCOVERY_TIMEOUT=5
REQUEST_TIMEOUT=600
TITLE_TIMEOUT=120
```

`OLLAMA_MODELS` supplies only the initial defaults. It is not a fixed allowlist.
The UI obtains the current catalogue directly from Ollama.

### Start and check Ollama

The Ollama macOS application normally starts the local service. Check it with:

```bash
ollama list
```

If nothing is running on port 11434, start it with:

```bash
ollama serve
```

Do not start a second `ollama serve` process if the macOS application already
has the service running.

### Add any downloaded Ollama model

Pull a model normally:

```bash
ollama pull MODEL_NAME
```

Then:

1. Open the LLM Council UI.
2. Expand **Council Models**.
3. Click **Refresh**.
4. Select the new model.
5. Select the Chairman from the chosen council members.

No Python edit or backend restart is required. Model choices are saved in the
browser's local storage.

Ollama entries identified as cloud models are visible but disabled. This keeps
the local model selector from presenting a remote service as local processing.

## Direct cloud-provider configuration

Cloud providers are optional. Add only the credentials you intend to use:

```dotenv
OPENAI_API_KEY=replace-with-a-real-key
ANTHROPIC_API_KEY=replace-with-a-real-key
GEMINI_API_KEY=replace-with-a-real-key
XAI_API_KEY=replace-with-a-real-key

OPENAI_MODEL=your-valid-openai-model-id
ANTHROPIC_MODEL=your-valid-claude-model-id
GEMINI_MODEL=your-valid-gemini-model-id
XAI_MODEL=your-valid-grok-model-id

COUNCIL_PROVIDERS=ollama,openai,anthropic,google,xai
CHAIRMAN_PROVIDER=ollama
```

Model identifiers must be valid for the corresponding provider account. Model
names and account availability can change, so the README deliberately does not
assume a particular current cloud model.

Supported provider values are:

| Provider value | Credential | Model setting | Connection |
| --- | --- | --- | --- |
| `ollama` | None | Selected in the UI | Local Ollama API |
| `openai` | `OPENAI_API_KEY` | `OPENAI_MODEL` | OpenAI SDK |
| `anthropic` | `ANTHROPIC_API_KEY` | `ANTHROPIC_MODEL` | Anthropic SDK |
| `google` | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `GEMINI_MODEL` | Google GenAI SDK |
| `xai` | `XAI_API_KEY` | `XAI_MODEL` | xAI OpenAI-compatible API |

### Why cloud models may not appear

The backend only exposes a cloud provider when it detects a real-looking API
key. These values are intentionally treated as unconfigured:

```dotenv
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
```

Blank values and recognised placeholders are also rejected. After adding real
credentials:

1. Stop Uvicorn with `Ctrl+C`.
2. Restart the backend.
3. Click **Refresh** in the sidebar.

Do not rely on `--reload` to detect an `.env` change.

`COUNCIL_PROVIDERS` controls the initial default council. A cloud model with a
configured key can still appear in the selector even when it is not included in
that setting. Existing browser selections can be changed manually.

Never paste API keys into chat, source code, screenshots or documentation.

## Protect secrets and local data

Use a `.gitignore` containing at least:

```gitignore
.env
*.env
!.env.example
__pycache__/
*.py[cod]
.DS_Store
frontend/node_modules/
data/conversations/
```

Do not commit `.env`. If a key is exposed, revoke it through the relevant
provider account and create a replacement.

## Running the application

Run the backend and frontend in separate terminal windows.

### Terminal 1 — backend

```bash
conda activate LLM_Council

cd /Users/mandeepchana/Library/CloudStorage/Dropbox/Software_Repo/PythonProject/LLM_Council

python -m uvicorn backend.main:app \
  --reload \
  --host 127.0.0.1 \
  --port 8001
```

The frontend expects port `8001`. Uvicorn's default port is `8000`, so omitting
`--port 8001` will prevent the UI from reaching this backend.

Expected output includes:

```text
Uvicorn running on http://127.0.0.1:8001
Application startup complete.
```

### Terminal 2 — frontend

```bash
cd /Users/mandeepchana/Library/CloudStorage/Dropbox/Software_Repo/PythonProject/LLM_Council/frontend
npm run dev
```

Open the URL displayed by Vite, normally:

```text
http://localhost:5173
```

Vite may choose 5174 or another local port if 5173 is occupied. The backend CORS
configuration accepts local `localhost` and `127.0.0.1` browser origins on any
port.

## Using the UI

1. Start Ollama if local models will be used.
2. Start the backend on port 8001.
3. Start the frontend.
4. Click **New Conversation**.
5. Expand **Council Models**.
6. Select one or more available models.
7. Choose a Chairman from the selected models.
8. Enter the review request and submit it.

The live flow displays:

- **Waiting** before a stage starts;
- **In progress** while the backend is waiting for a model;
- **Completed** after a successful response; and
- **Failed** when a selected model does not return a usable response.

The flow then connects the council results to the Chairman for final synthesis.
It can be collapsed with **Hide flow**.

## Example review prompts

### HLD review

```text
Review this HLD as a technical design authority. Identify architectural gaps,
security risks, scalability concerns, missing non-functional requirements,
assumptions, dependencies and open questions. Separate confirmed findings from
recommendations and prioritise the findings by severity.
```

### LLD review

```text
Review this LLD for correctness, maintainability, resilience, security,
observability and operational support. Provide prioritised findings with
evidence, impact and recommended remediation.
```

### Code review

```text
Review this code for functional defects, security weaknesses, concurrency risks,
error-handling gaps, test gaps and unnecessary complexity. Do not claim a defect
unless it is supported by the supplied code.
```

## API verification

### Health check

```bash
curl http://127.0.0.1:8001/
```

Expected response:

```json
{"status":"ok","service":"LLM Council API"}
```

### Model catalogue

```bash
curl -s http://127.0.0.1:8001/api/models | python -m json.tool
```

The response shows:

- dynamically discovered Ollama models;
- configured cloud models;
- whether each model is selectable;
- startup defaults;
- the default Chairman; and
- whether Ollama was reachable.

The endpoint exposes model information, not API-key values.

### Create a test conversation

```bash
curl -i -X POST \
  http://127.0.0.1:8001/api/conversations \
  -H "Content-Type: application/json" \
  -d '{}'
```

A successful response returns HTTP 200 and a JSON conversation object.

### API documentation

Open:

```text
http://127.0.0.1:8001/docs
```

## Data handling and privacy

With local Ollama models only, the model request path is:

```text
Browser -> local FastAPI backend -> local Ollama service
```

When a cloud model is selected, its request path is:

```text
Browser -> local FastAPI backend -> selected cloud provider
```

Removing OpenRouter removes that intermediary. It does not keep requests local
when a cloud model is selected, and it does not by itself establish a particular
retention or training policy. Confirm the current contractual and data-handling
terms for every provider account before sending confidential HLDs, LLDs, source
code, personal data or client information.

Conversation history is stored locally under:

```text
data/conversations/
```

These JSON files are not encrypted by this application. Protect the Mac account,
project directory and backups appropriately.

## Troubleshooting

### Cloud models do not appear

Check what the backend considers configured without printing any secret:

```bash
python -c "from backend.config import AVAILABLE_CLOUD_MODELS; print(AVAILABLE_CLOUD_MODELS)"
```

If this prints `[]`:

1. Confirm `.env` is in the project root beside `pyproject.toml`.
2. Replace placeholder keys with real credentials.
3. Start Uvicorn from the project root.
4. Completely restart Uvicorn.
5. Click **Refresh** in the UI.

### Ollama models do not appear

Confirm the local service and native model catalogue:

```bash
ollama list
curl http://127.0.0.1:11434/api/tags
```

Then inspect the council catalogue:

```bash
curl -s http://127.0.0.1:8001/api/models | python -m json.tool
```

If Ollama works but the second request does not, check `OLLAMA_BASE_URL`, restart
the backend and inspect its terminal output.

### New Conversation does nothing

Test the backend directly:

```bash
curl -i -X POST \
  http://127.0.0.1:8001/api/conversations \
  -H "Content-Type: application/json" \
  -d '{}'
```

If this fails to connect, start the backend on port 8001. If it succeeds but the
button fails:

1. Confirm `frontend/src/api.js` uses `http://localhost:8001`.
2. Open browser developer tools with `Cmd+Option+I`.
3. Inspect the first red error in **Console**.
4. Inspect `/api/conversations` in **Network**.

### `ModuleNotFoundError: No module named 'backend.providers'`

Confirm this file exists:

```text
backend/providers.py
```

Verify the import from the project root:

```bash
python -c "import backend.providers; print(backend.providers.__file__)"
```

`backend/council.py` must contain:

```python
from .providers import query_models_parallel, query_model
```

### Multiple top-level packages discovered

Confirm `pyproject.toml` contains:

```toml
[tool.setuptools.packages.find]
where = ["."]
include = ["backend*"]
exclude = ["frontend*"]
```

Then rerun:

```bash
python -m pip install -e .
```

### Relative-import error

Do not run:

```bash
python backend/main.py
```

Run it as a module or through Uvicorn:

```bash
python -m backend.main
```

```bash
python -m uvicorn backend.main:app --reload --port 8001
```

### Provider returns 401 or 403

- Check the key in `.env` without printing the complete value.
- Confirm the account can access the configured model.
- Confirm the correct provider model identifier is configured.
- Restart the backend after changing `.env`.
- Check the provider account's billing or credit status.

### Provider returns 429

HTTP 429 commonly represents a provider rate limit or exhausted quota. Inspect
the provider's returned error and account dashboard. Selecting fewer council
members reduces the number of calls but does not restore exhausted credit.

### A large local council is slow

Each selected Ollama model is called during both Answer and Review stages. Large
models may also need to be loaded and unloaded. Start with two local models and:

```dotenv
OLLAMA_MAX_CONCURRENCY=1
```

Increase concurrency only after checking memory use and stability.

### README is read-only in PyCharm

A README opened from a ChatGPT download or temporary preview is not automatically
the same file as the README in the local PyCharm project. Download or copy the
updated file to exactly:

```text
/Users/mandeepchana/Library/CloudStorage/Dropbox/Software_Repo/PythonProject/LLM_Council/README.md
```

In PyCharm, open `README.md` from the **Project** panel, not from a browser preview
or temporary download location.

If PyCharm still reports that the local file is read-only, inspect its macOS
permissions and flags:

```bash
cd /Users/mandeepchana/Library/CloudStorage/Dropbox/Software_Repo/PythonProject/LLM_Council
ls -lO README.md
```

If the owner does not have write permission:

```bash
chmod u+w README.md
```

If `ls -lO` shows the immutable `uchg` flag:

```bash
chflags nouchg README.md
```

Because the project is stored under Dropbox, also confirm in Finder that the file
is available offline and not locked. PyCharm may offer **File → Make File
Writable**, but operating-system or Dropbox restrictions must still be corrected
at the file level.

Do not use `sudo` for a normal project file. If the file is owned by another
account, investigate why before changing its ownership.

## Development checks

Check backend syntax:

```bash
python -m compileall backend
```

Check backend imports:

```bash
python -c "import backend.main, backend.council, backend.providers; print('Backend imports OK')"
```

Show configured model identifiers without secrets:

```bash
python -c "from backend.config import COUNCIL_MODELS, CHAIRMAN_MODEL; print('Council:', COUNCIL_MODELS); print('Chairman:', CHAIRMAN_MODEL)"
```

Start the frontend development server:

```bash
cd frontend
npm run dev
```

## Known limitations

- The application is intended for local development and personal use.
- It does not provide user authentication or multi-user authorisation.
- Local conversation JSON files are not encrypted by the application.
- A provider or model can fail while the remaining council continues.
- A model consensus is not proof that an answer is correct.
- Several models can repeat the same unsupported assumption.
- Architecture and code-review findings still require human validation.
- The backend should not be exposed publicly without authentication, TLS,
  network controls, stricter CORS, request limits and secret management.

## Stopping the application

Press `Ctrl+C` in the frontend terminal and the backend terminal. Quit the Ollama
application separately if it should no longer run locally.

## Attribution

This project is based on Andrej Karpathy's LLM Council project. The direct cloud
provider adapters, Ollama integration, dynamic model selector and live council
flow are local modifications.

Review the upstream project's current licence before redistributing a modified
version. This README does not replace the upstream licence.

## Reference documentation

- [Original LLM Council repository](https://github.com/karpathy/llm-council)
- [Ollama API documentation](https://docs.ollama.com/api/introduction)
- [Ollama model-list endpoint](https://docs.ollama.com/api/tags)
- [Ollama OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)
- [OpenAI API documentation](https://developers.openai.com/api/docs)
- [Anthropic API documentation](https://platform.claude.com/docs)
- [Google Gemini API documentation](https://ai.google.dev/gemini-api/docs)
- [xAI API documentation](https://docs.x.ai/)
- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [Setuptools package discovery](https://setuptools.pypa.io/en/latest/userguide/package_discovery.html)

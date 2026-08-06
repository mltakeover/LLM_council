LLM Council

A local multi-model review application for architecture documents, detaileddesigns, source code, technical decisions and general questions.

The application runs a three-stage council:

Selected models independently answer the request.

The models review and rank the anonymised answers.

A selected Chairman produces the final synthesis.

This version supports:

locally downloaded models through Ollama;

dynamic Ollama model discovery with no Python changes after ollama pull;

direct calls to OpenAI, Anthropic, Google Gemini and xAI;

per-request council member and Chairman selection;

an animated UI showing Answer, Review and Synthesis progress;

local JSON conversation history; and

server-sent events for real backend progress updates.

OpenRouter is not used.

How the council works

For every question, the backend performs the following workflow:

User request
     |
     +--> Stage 1: independent answer from every selected model
     |
     +--> Stage 2: anonymous peer review and ranking
     |
     +--> Stage 3: Chairman synthesis
     |
     +--> Final answer

For N selected models, a normal council run makes:

N answer calls + N review calls + 1 synthesis call = 2N + 1 calls

For three models:

(2 × 3) + 1 = 7 model calls

Title generation may make one additional call. Failed calls, retries andprovider-specific behaviour can also change the final number.

Architecture

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

Project structure

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
│       ├── components/
│       │   ├── ChatInterface.jsx
│       │   ├── CouncilFlow.jsx
│       │   ├── CouncilFlow.css
│       │   ├── Sidebar.jsx
│       │   └── Sidebar.css
│       └── utils/
│           └── modelDisplay.js  # Shared provider/model-name formatting
├── data/
│   └── conversations/          # Created automatically
├── .env                        # Local configuration and secrets
├── .env.example                # Safe configuration template
├── .gitignore
├── pyproject.toml
└── README.md

Requirements

macOS

Conda or Miniconda

Python 3.10 or later

Node.js and npm

Ollama for local models

API credentials only for the cloud providers you choose to enable

Check the installed tools:

conda --version
python --version
node --version
npm --version
ollama --version

Installation on macOS with Conda

1. Open the project

Clone the repository if it is not already available locally:

git clone https://github.com/mltakeover/LLM_council.git
cd LLM_council

If the repository has already been cloned, open a terminal and change to itsroot directory:

cd /path/to/LLM_council

All remaining commands assume the current directory is the repository root.

2. Create or activate the environment

Create it if needed:

conda create -n LLM_Council python=3.11 -y

Activate it:

conda activate LLM_Council

3. Configure Python packaging

Use the following pyproject.toml:

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

The package-discovery section prevents setuptools from trying to package theReact frontend directory as a Python package.

Install the backend in editable mode:

python -m pip install --upgrade pip
python -m pip install -e .

Verify the imports:

python -c "import backend, openai, anthropic; from google import genai; print('Backend dependencies installed')"

4. Install the frontend

cd frontend
npm install
cd ..

Local Ollama configuration

The recommended starting configuration is local-only. Create .env in theproject root:

COUNCIL_PROVIDERS=ollama

OLLAMA_BASE_URL=http://127.0.0.1:11434/v1/
OLLAMA_MODELS=qwen3.6:latest,qwen2.5-coder:7b,llama3.1:latest
OLLAMA_CHAIRMAN_MODEL=qwen3.6:latest
TITLE_MODEL=ollama:llama3.1:latest

OLLAMA_MAX_CONCURRENCY=1
OLLAMA_DISCOVERY_TIMEOUT=5
REQUEST_TIMEOUT=600
TITLE_TIMEOUT=120

OLLAMA_MODELS supplies only the initial defaults. It is not a fixed allowlist.The UI obtains the current catalogue directly from Ollama.

Start and check Ollama

The Ollama macOS application normally starts the local service. Check it with:

ollama list

If nothing is running on port 11434, start it with:

ollama serve

Do not start a second ollama serve process if the macOS application alreadyhas the service running.

Add any downloaded Ollama model

Pull a model normally:

ollama pull MODEL_NAME

Then:

Open the LLM Council UI.

Expand Council Models.

Click Refresh.

Select the new model.

Select the Chairman from the chosen council members.

No Python edit or backend restart is required. Model choices are saved in thebrowser's local storage.

Ollama entries identified as cloud models are visible but disabled. This keepsthe local model selector from presenting a remote service as local processing.

Direct cloud-provider configuration

Cloud providers are optional. Add only the credentials you intend to use:

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

Model identifiers must be valid for the corresponding provider account. Modelnames and account availability can change, so the README deliberately does notassume a particular current cloud model.

Supported provider values are:

Provider value

Credential

Model setting

Connection

ollama

None

Selected in the UI

Local Ollama API

openai

OPENAI_API_KEY

OPENAI_MODEL

OpenAI SDK

anthropic

ANTHROPIC_API_KEY

ANTHROPIC_MODEL

Anthropic SDK

google

GEMINI_API_KEY or GOOGLE_API_KEY

GEMINI_MODEL

Google GenAI SDK

xai

XAI_API_KEY

XAI_MODEL

xAI OpenAI-compatible API

Why cloud models may not appear

The backend only exposes a cloud provider when it detects a real-looking APIkey. These values are intentionally treated as unconfigured:

OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key

Blank values and recognised placeholders are also rejected. After adding realcredentials:

Stop Uvicorn with Ctrl+C.

Restart the backend.

Click Refresh in the sidebar.

Do not rely on --reload to detect an .env change.

COUNCIL_PROVIDERS controls the initial default council. A cloud model with aconfigured key can still appear in the selector even when it is not included inthat setting. Existing browser selections can be changed manually.

Never paste API keys into chat, source code, screenshots or documentation.

Protect secrets and local data

Use a .gitignore containing at least:

.env
.env.*
!.env.example
__pycache__/
*.py[cod]
.DS_Store
frontend/node_modules/
data/conversations/

Do not commit .env. If a key is exposed, revoke it through the relevantprovider account and create a replacement.

Running the application

Run the backend and frontend in separate terminal windows.

Terminal 1 — backend

conda activate LLM_Council

cd /path/to/LLM_council

python -m uvicorn backend.main:app \
  --reload \
  --host 127.0.0.1 \
  --port 8001

The frontend expects port 8001. Uvicorn's default port is 8000, so omitting--port 8001 will prevent the UI from reaching this backend.

Expected output includes:

Uvicorn running on http://127.0.0.1:8001
Application startup complete.

Terminal 2 — frontend

From the repository root:

cd frontend
npm run dev

Open the URL displayed by Vite, normally:

http://localhost:5173

Vite may choose 5174 or another local port if 5173 is occupied. The backend CORSconfiguration accepts local localhost and 127.0.0.1 browser origins on anyport.

Using the UI

Start Ollama if local models will be used.

Start the backend on port 8001.

Start the frontend.

Click New Conversation.

Expand Council Models.

Select one or more available models.

Choose a Chairman from the selected models.

Enter the review request and submit it.

The live flow displays:

Waiting before a stage starts;

In progress while the backend is waiting for a model;

Completed after a successful response; and

Failed when a selected model does not return a usable response.

The flow then connects the council results to the Chairman for final synthesis.It can be collapsed with Hide flow.

Example review prompts

HLD review

Review this HLD as a technical design authority. Identify architectural gaps,
security risks, scalability concerns, missing non-functional requirements,
assumptions, dependencies and open questions. Separate confirmed findings from
recommendations and prioritise the findings by severity.

LLD review

Review this LLD for correctness, maintainability, resilience, security,
observability and operational support. Provide prioritised findings with
evidence, impact and recommended remediation.

Code review

Review this code for functional defects, security weaknesses, concurrency risks,
error-handling gaps, test gaps and unnecessary complexity. Do not claim a defect
unless it is supported by the supplied code.

API verification

Health check

curl http://127.0.0.1:8001/

Expected response:

{"status":"ok","service":"LLM Council API"}

Model catalogue

curl -s http://127.0.0.1:8001/api/models | python -m json.tool

The response shows:

dynamically discovered Ollama models;

configured cloud models;

whether each model is selectable;

startup defaults;

the default Chairman; and

whether Ollama was reachable.

The endpoint exposes model information, not API-key values.

Create a test conversation

curl -i -X POST \
  http://127.0.0.1:8001/api/conversations \
  -H "Content-Type: application/json" \
  -d '{}'

A successful response returns HTTP 200 and a JSON conversation object.

API documentation

Open:

http://127.0.0.1:8001/docs

Data handling and privacy

With local Ollama models only, the model request path is:

Browser -> local FastAPI backend -> local Ollama service

When a cloud model is selected, its request path is:

Browser -> local FastAPI backend -> selected cloud provider

Removing OpenRouter removes that intermediary. It does not keep requests localwhen a cloud model is selected, and it does not by itself establish a particularretention or training policy. Confirm the current contractual and data-handlingterms for every provider account before sending confidential HLDs, LLDs, sourcecode, personal data or client information.

Conversation history is stored locally under:

data/conversations/

These JSON files are not encrypted by this application. Protect the Mac account,project directory and backups appropriately.

Troubleshooting

Cloud models do not appear

Check what the backend considers configured without printing any secret:

python -c "from backend.config import AVAILABLE_CLOUD_MODELS; print(AVAILABLE_CLOUD_MODELS)"

If this prints []:

Confirm .env is in the project root beside pyproject.toml.

Replace placeholder keys with real credentials.

Start Uvicorn from the project root.

Completely restart Uvicorn.

Click Refresh in the UI.

Ollama models do not appear

Confirm the local service and native model catalogue:

ollama list
curl http://127.0.0.1:11434/api/tags

Then inspect the council catalogue:

curl -s http://127.0.0.1:8001/api/models | python -m json.tool

If Ollama works but the second request does not, check OLLAMA_BASE_URL, restartthe backend and inspect its terminal output.

New Conversation does nothing

Test the backend directly:

curl -i -X POST \
  http://127.0.0.1:8001/api/conversations \
  -H "Content-Type: application/json" \
  -d '{}'

If this fails to connect, start the backend on port 8001. If it succeeds but thebutton fails:

Confirm frontend/src/api.js uses http://localhost:8001.

Open browser developer tools with Cmd+Option+I.

Inspect the first red error in Console.

Inspect /api/conversations in Network.

ModuleNotFoundError: No module named 'backend.providers'

Confirm this file exists:

backend/providers.py

Verify the import from the project root:

python -c "import backend.providers; print(backend.providers.__file__)"

backend/council.py must contain:

from .providers import query_models_parallel, query_model

Multiple top-level packages discovered

Confirm pyproject.toml contains:

[tool.setuptools.packages.find]
where = ["."]
include = ["backend*"]
exclude = ["frontend*"]

Then rerun:

python -m pip install -e .

Relative-import error

Do not run:

python backend/main.py

Run it as a module or through Uvicorn:

python -m backend.main

python -m uvicorn backend.main:app --reload --port 8001

Provider returns 401 or 403

Check the key in .env without printing the complete value.

Confirm the account can access the configured model.

Confirm the correct provider model identifier is configured.

Restart the backend after changing .env.

Check the provider account's billing or credit status.

Provider returns 429

HTTP 429 commonly represents a provider rate limit or exhausted quota. Inspectthe provider's returned error and account dashboard. Selecting fewer councilmembers reduces the number of calls but does not restore exhausted credit.

A large local council is slow

Each selected Ollama model is called during both Answer and Review stages. Largemodels may also need to be loaded and unloaded. Start with two local models and:

OLLAMA_MAX_CONCURRENCY=1

Increase concurrency only after checking memory use and stability.

README is read-only in PyCharm

A README opened from a ChatGPT download or temporary preview is not automaticallythe same file as the README in the local PyCharm project. Download or copy theupdated file into the root of the cloned repository as:

LLM_council/README.md

In PyCharm, open README.md from the Project panel, not from a browser previewor temporary download location.

If PyCharm still reports that the local file is read-only, inspect its macOSpermissions and flags from the repository root:

ls -lO README.md

If the owner does not have write permission:

chmod u+w README.md

If ls -lO shows the immutable uchg flag:

chflags nouchg README.md

If the repository is stored in a cloud-synchronised folder, also confirm that thefile is available offline and not locked by the synchronisation client. PyCharmmay offer File → Make File Writable, but operating-system or synchronisationrestrictions must still be corrected at the file level.

Do not use sudo for a normal project file. If the file is owned by anotheraccount, investigate why before changing its ownership.

Development checks

Check backend syntax:

python -m compileall backend

Check backend imports:

python -c "import backend.main, backend.council, backend.providers; print('Backend imports OK')"

Show configured model identifiers without secrets:

python -c "from backend.config import COUNCIL_MODELS, CHAIRMAN_MODEL; print('Council:', COUNCIL_MODELS); print('Chairman:', CHAIRMAN_MODEL)"

Start the frontend development server:

cd frontend
npm run dev

Known limitations

The application is intended for local development and personal use.

It does not provide user authentication or multi-user authorisation.

Local conversation JSON files are not encrypted by the application.

A provider or model can fail while the remaining council continues.

A model consensus is not proof that an answer is correct.

Several models can repeat the same unsupported assumption.

Architecture and code-review findings still require human validation.

The backend should not be exposed publicly without authentication, TLS,network controls, stricter CORS, request limits and secret management.

Stopping the application

Press Ctrl+C in the frontend terminal and the backend terminal. Quit the Ollamaapplication separately if it should no longer run locally.

Attribution

This project is based on Andrej Karpathy's LLM Council project. The direct cloudprovider adapters, Ollama integration, dynamic model selector and live councilflow are local modifications.

Review the upstream project's current licence before redistributing a modifiedversion. This README does not replace the upstream licence.

Reference documentation

Original LLM Council repository

Ollama API documentation

Ollama model-list endpoint

Ollama OpenAI compatibility

OpenAI API documentation

Anthropic API documentation

Google Gemini API documentation

xAI API documentation

FastAPI documentation

Setuptools package discovery
LLM Council — Direct Provider Edition

LLM Council is a local multi-model review application based on Andrej Karpathy'sLLM Council. It sends the same questionto several large language models, asks the models to review one another's answers,and uses a designated chairman model to produce a final synthesis.

This edition removes OpenRouter from the request path and calls the providersdirectly:

OpenAI through the official OpenAI Python SDK

Anthropic through the official Anthropic Python SDK

Google Gemini through the google-genai SDK

xAI through its OpenAI-compatible API endpoint

It is intended for local, personal use. The web interface and conversation filesrun on your Mac, but prompts and model responses are transmitted to every providerenabled in your council.

How the council works

Each submitted question passes through three stages:

Independent responses: every configured council model answers the question.

Peer review: every council model receives anonymised answers and ranks them.

Chairman synthesis: the chairman model combines the answers and reviews intoone final response.

For N council members, one complete question normally generates:

N initial calls + N review calls + 1 chairman call = 2N + 1 API calls

For four council members:

(2 × 4) + 1 = 9 API calls

This excludes retries, failed requests and any additional title-generation callmade by the application.

Architecture

Browser UI (React/Vite, port 5173)
                |
                v
FastAPI backend (port 8001)
                |
                v
Council orchestration
      |         |         |         |
      v         v         v         v
   OpenAI   Anthropic   Gemini      xAI
                |
                v
Local JSON conversation storage
data/conversations/

Project structure

The important files are:

LLM_Council/
├── backend/
│   ├── __init__.py
│   ├── main.py          # FastAPI application and HTTP endpoints
│   ├── council.py       # Three-stage council orchestration
│   ├── config.py        # Provider, model and runtime configuration
│   ├── providers.py     # Direct provider API clients
│   └── storage.py       # Local JSON conversation storage
├── data/
│   └── conversations/   # Locally stored conversation JSON files
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── api.js
│   │   └── components/
│   └── package.json
├── .env                 # Local secrets; never commit this file
├── .gitignore
├── pyproject.toml
└── README.md

Requirements

macOS

Conda or Miniconda

Python 3.10 or later

Node.js and npm

An API key and active billing/credits for every enabled provider

Confirm the local tools:

conda --version
python --version
node --version
npm --version

Installation on macOS with Conda

1. Open the project directory

cd /Users/mandeepchana/Library/CloudStorage/Dropbox/Software_Repo/PythonProject/LLM_Council

2. Create and activate the Conda environment

If the environment does not exist:

conda create -n LLM_Council python=3.11 -y

Activate it:

conda activate LLM_Council

3. Configure pyproject.toml

The project uses a flat repository layout containing both backend andfrontend. Setuptools must therefore be instructed to package only the Pythonbackend.

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

Install the backend in editable mode:

python -m pip install --upgrade pip
python -m pip install -e .

Editable mode means Python uses the current source files, so normal code changesdo not require another installation.

Verify the provider SDKs:

python -c "import openai, anthropic; from google import genai; print('Provider SDKs installed successfully')"

4. Install the frontend

cd frontend
npm install
cd ..

Provider configuration

Create .env in the project root:

OPENAI_API_KEY=your-openai-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
GEMINI_API_KEY=your-gemini-api-key
XAI_API_KEY=your-xai-api-key

OPENAI_MODEL=gpt-5.6-terra
ANTHROPIC_MODEL=claude-sonnet-5
GEMINI_MODEL=gemini-3.6-flash
XAI_MODEL=grok-4.5

COUNCIL_PROVIDERS=openai,anthropic,google,xai
CHAIRMAN_PROVIDER=openai

REQUEST_TIMEOUT=180
ANTHROPIC_MAX_TOKENS=8192

Model names above are configuration examples. Model availability, aliases andaccount access can change. If a provider reports that a model does not exist oris unavailable, replace the corresponding model value with an identifier enabledfor your provider account.

Only include providers whose API keys you have configured. For example, atwo-provider council is:

COUNCIL_PROVIDERS=openai,anthropic
CHAIRMAN_PROVIDER=openai

The provider names supported by this version are:

Provider value

Required key

Model variable

openai

OPENAI_API_KEY

OPENAI_MODEL

anthropic

ANTHROPIC_API_KEY

ANTHROPIC_MODEL

google

GEMINI_API_KEY or GOOGLE_API_KEY

GEMINI_MODEL

xai

XAI_API_KEY

XAI_MODEL

The application will fail during startup if a provider appears inCOUNCIL_PROVIDERS but its required API key is missing.

Protecting API keys

Ensure .gitignore contains:

.env
*.env
!.env.example
__pycache__/
*.py[cod]
.DS_Store
frontend/node_modules/
data/conversations/

Never place API keys in source code, screenshots, documentation, Git commits orsupport messages. If a key is exposed, revoke it through the provider console andcreate a replacement.

Running the application

The backend and frontend run as two separate processes. Keep both terminalwindows open.

Terminal 1 — backend

conda activate LLM_Council

cd /Users/mandeepchana/Library/CloudStorage/Dropbox/Software_Repo/PythonProject/LLM_Council

python -m uvicorn backend.main:app \
  --reload \
  --host 127.0.0.1 \
  --port 8001

Expected output includes:

Uvicorn running on http://127.0.0.1:8001
Application startup complete.

The following is also valid when backend/main.py contains its Uvicorn startupblock configured for port 8001:

python -m backend.main

Do not normally run python backend/main.py; package-relative imports such asfrom .council import ... require the backend to be launched as a module.

Terminal 2 — frontend

cd /Users/mandeepchana/Library/CloudStorage/Dropbox/Software_Repo/PythonProject/LLM_Council/frontend
npm run dev

Open the exact URL displayed by Vite. It is normally:

http://localhost:5173

Useful backend URLs:

Health endpoint: http://127.0.0.1:8001/

Interactive API documentation: http://127.0.0.1:8001/docs

Conversation list: http://127.0.0.1:8001/api/conversations

Verify the backend before using the UI

Health check

curl http://127.0.0.1:8001/

Expected response:

{"status":"ok","service":"LLM Council API"}

Create a test conversation

curl -i -X POST \
  http://127.0.0.1:8001/api/conversations \
  -H "Content-Type: application/json" \
  -d '{}'

The response should include:

HTTP/1.1 200 OK

and a JSON object containing an id, creation time, title and empty messagesarray.

If this request succeeds but the UI button does not, the problem is in thefrontend connection, browser console or CORS configuration rather than localconversation storage.

Frontend API address

frontend/src/api.js should point to port 8001:

const API_BASE = 'http://localhost:8001';

The original frontend expects the backend on port 8001. Starting Uvicorn on itsdefault port 8000 will display the UI but prevent conversation creation.

Local development CORS configuration

Vite normally uses port 5173 but may select another port if 5173 is occupied. Forlocal personal development, the following backend/main.py configuration acceptsonly browser origins on the local machine, regardless of the local port:

app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

This is a local-development setting. Review and restrict allowed origins beforeexposing the backend on another machine or network.

Using the council

Start the backend on port 8001.

Start the frontend.

Open the Vite URL in a browser.

Select Create New Conversation.

Enter a question, HLD, LLD, code sample or review request.

Submit the prompt and wait for all three stages.

Inspect individual responses, peer rankings and the chairman synthesis.

Useful review prompts include:

Review this HLD as a technical design authority. Identify architectural gaps,
security risks, scalability concerns, missing non-functional requirements,
assumptions, dependencies and open questions. Distinguish confirmed issues from
recommendations.

Review this LLD for correctness, maintainability, observability, resilience,
security and operational support. Provide prioritised findings with severity,
evidence, impact and a recommended remediation.

Review this code. Identify functional defects, security weaknesses, concurrency
risks, error-handling gaps, test gaps and unnecessary complexity. Do not claim a
defect unless it is supported by the supplied code.

Data handling and privacy

Removing OpenRouter means requests go directly from the local backend to theproviders you configure. It does not mean prompts remain entirely on your Mac.

The data path is:

Browser -> local FastAPI backend -> configured provider APIs

Conversation history is also written locally under:

data/conversations/

Training policy and retention are separate controls. Direct API use gives you adirect relationship with each provider, but does not automatically create ZeroData Retention.

OpenAI documents that Chat Completions API data is not used for training, whilestandard abuse-monitoring retention can be 30 days. This implementation passesstore=False to OpenAI Chat Completions, but Zero Data Retention is a separateorganisation-level control. See OpenAI data controls.

Review Anthropic's current API data-retention documentation.

Review the current Gemini API terms,particularly the distinction between paid and unpaid services.

Review xAI's current security and privacy FAQ.

Before submitting confidential HLDs, LLDs, source code, personal data or clientmaterial, confirm that every enabled provider account has the required contractual,regional, retention and privacy settings. Redact secrets, credentials, personaldata and client identifiers where possible.

Cost controls

Each user prompt creates multiple billable API calls. Long design documents alsoincrease input tokens during both initial review and peer-ranking stages.

To limit cost:

Begin with two providers rather than four.

Set provider billing limits and usage alerts.

Use smaller or lower-cost models for peer review.

Reserve the strongest model for the chairman.

Remove irrelevant appendices and duplicate content before submission.

Monitor usage in each provider console.

The application does not provide a single combined budget because each providerbills independently.

Troubleshooting

curl: (7) Failed to connect to localhost port 8001

Nothing is listening on port 8001. Start the backend and leave its terminal open:

python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8001

Then retry:

curl http://127.0.0.1:8001/

Create New Conversation does nothing

Check in this order:

Confirm the backend terminal says Application startup complete.

Run the health-check and conversation-creation curl commands above.

Confirm frontend/src/api.js uses http://localhost:8001.

Confirm the browser URL uses localhost, not an unexpected hostname.

Check the Vite port and the backend CORS configuration.

Open browser developer tools with Cmd+Option+I, select Console, click thebutton again, and inspect the first red error.

In Network, look for a failed request to /api/conversations.

If the curl POST works but the browser request fails, the most likely causes arean incorrect frontend API address or a CORS origin mismatch.

ModuleNotFoundError: No module named 'backend.providers'

Confirm the file exists at exactly:

backend/providers.py

Locate similarly named files:

find . -maxdepth 2 -iname "*provider*"

Verify the import:

python -c "import backend.providers; print(backend.providers.__file__)"

backend/council.py must import:

from .providers import query_models_parallel, query_model

Multiple top-level packages discovered

If editable installation reports:

Multiple top-level packages discovered in a flat-layout: ['backend', 'frontend']

add this to pyproject.toml:

[tool.setuptools.packages.find]
where = ["."]
include = ["backend*"]
exclude = ["frontend*"]

Then rerun:

python -m pip install -e .

Relative-import error

If Python reports:

attempted relative import with no known parent package

run the backend as a module:

python -m backend.main

or use Uvicorn:

python -m uvicorn backend.main:app --reload --port 8001

Provider returns 401 or 403

Confirm the correct API key is in the project-root .env file.

Restart the backend after changing .env.

Confirm the account has permission to use the selected model.

Confirm billing or credits are active.

Check for accidental spaces or quotes in the key.

Do not print the complete API key while diagnosing the issue.

Provider reports model not found

The configured model identifier may not be available to your account or may havechanged. Check the provider's current model documentation and replace the relatedmodel variable in .env, then restart the backend.

Provider returns 429

HTTP 429 normally indicates a rate limit, quota limit or unavailable accountcredit. Check the error body and the relevant provider dashboard. Reducing thenumber of council members reduces parallel calls but does not correct exhaustedcredit.

favicon.ico returns 404

This is harmless. The browser requested a site icon that the backend does notprovide. It does not affect the API or council workflow.

Frontend starts on port 5174

Another process is probably using 5173. Either use the CORS regex shown above orstop the older Vite process and restart the frontend.

To inspect listening processes:

lsof -nP -iTCP:5173 -sTCP:LISTEN
lsof -nP -iTCP:8001 -sTCP:LISTEN

Operational limitations

The application is designed for local development and has no user authentication.

The local conversation files are not encrypted by this application.

Provider requests can partially fail; the council may continue with fewer answers.

Direct providers have different request formats, limits and error responses.

reasoning_details is currently returned as None by the direct-provider adapter.

A consensus response is not proof of correctness. Multiple models can repeat thesame error or rely on the same unsupported assumption.

Design and code findings should be checked against authoritative documentation,actual source code, tests and organisational standards.

Do not expose port 8001 publicly without adding authentication, network controls,TLS, stricter CORS rules, request limits, secret management and appropriate logging.

Useful development commands

Check the backend imports:

python -c "import backend.main, backend.council, backend.providers; print('Backend imports OK')"

List configured models without printing API keys:

python -c "from backend.config import COUNCIL_MODELS, CHAIRMAN_MODEL; print('Council:', COUNCIL_MODELS); print('Chairman:', CHAIRMAN_MODEL)"

Check backend syntax:

python -m compileall backend

Check frontend dependencies:

cd frontend
npm install
npm run dev

Stopping the application

Press Ctrl+C in the backend terminal and then in the frontend terminal.

Attribution

This project is based on Andrej Karpathy'sLLM Council. The direct-provider adapterand provider-specific configuration are local modifications to the originalOpenRouter-based implementation.

Review the upstream repository and its licence before redistributing modifiedversions. This README does not change or replace the upstream licence.

Reference documentation

Original LLM Council repository

OpenAI API quickstart

OpenAI API data controls

Anthropic Python SDK documentation

Anthropic API data retention

Google Gemini API documentation

Google Gemini API terms

xAI developer documentation

Setuptools package discovery


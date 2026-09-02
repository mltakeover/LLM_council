# LLM Council frontend

React and Vite interface for the general-purpose LLM Council. It provides
adaptive mode selection, Council/Workforce/Hybrid orchestration, per-model
perspectives and worker assignments, dynamic model discovery, saved presets,
live Manager/worker/QA/Master progress, contribution ledgers, output-hygiene
status, documents, adaptive reports, provider checks, and Markdown/DOCX/PDF
exports.

## Requirements

- Node.js 20+
- npm
- LLM Council backend running on port 8001 by default

## Run locally

```bash
npm ci
npm run dev
```

Open the URL printed by Vite, normally `http://localhost:5173`.

To use a different backend:

```bash
VITE_API_BASE_URL=http://127.0.0.1:9000 npm run dev
```

## Checks

```bash
npm test
npm run lint
npm run build
```

The Node test suite covers browser-independent utilities. GitHub Actions runs
these checks for pushes and pull requests targeting `master`.

## Important behaviour

- `src/api.js` parses SSE blocks incrementally; network chunks do not necessarily
  align with event boundaries.
- Each submission gets a UUID `run_id`. Retrying the same request must reuse the
  same ID so the backend can replace the failed assistant result without adding
  another user message.
- Stop aborts the browser request; the backend then cancels its active provider
  task and persists a retryable cancelled run.
- Locality comes from backend catalogue metadata. Remote Ollama is not local.
- Auto mode is resolved by the backend without a classification provider call.
- Presets include models, Chairman/Master, orchestration strategy, task mode,
  output hygiene, custom roles, review profile, and conversation-context
  preference. Legacy presets preserve the earlier Council behaviour.
- Review profiles are shown only for Review and Auto. Other modes use their own
  perspectives and peer-evaluation criteria.
- The adaptive report renders only panels populated for the resolved mode, such
  as options, debate positions, ideas, comparisons, plans, claims, or findings.
- Cloud/remote processing and cloud title generation for an untitled
  conversation require explicit confirmation before Send is enabled.
- Documents marked `truncated` must remain visibly marked in the picker,
  transcript, and usage estimate.

See the repository-level `README.md` for installation, provider configuration,
privacy details, architecture, and API documentation.

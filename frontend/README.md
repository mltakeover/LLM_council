# LLM Council frontend

React and Vite interface for LLM Council. It provides dynamic model selection,
saved presets, live per-model stage progress, file review, structured findings,
consensus views, provider connectivity checks, and Markdown/DOCX/PDF exports.

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
- Cloud/remote processing and cloud title generation for an untitled
  conversation require explicit confirmation before Send is enabled.
- Documents marked `truncated` must remain visibly marked in the picker,
  transcript, and usage estimate.

See the repository-level `README.md` for installation, provider configuration,
privacy details, architecture, and API documentation.

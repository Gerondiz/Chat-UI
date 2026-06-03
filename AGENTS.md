# Chat-UI — Agent Guide

## Repo structure
- `backend/` — FastAPI (Python 3.11+), single endpoint module `main.py`
- `frontend/` — React + Vite (JS, plain CSS dark theme, no Tailwind)

## Dev commands

```bash
# Backend
cd backend && pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Frontend
cd frontend && npm install && npm run dev

# Both at once (from repo root)
./start.sh
```

Vite proxies `/api/*` → `http://localhost:8000` (timeout 120s).

## Testing

No unit test framework. Tests are shell/Python scripts that require both servers running:

```bash
./test.sh                    # curl-based smoke test (provider status, chat, streaming)
python3 run_and_test.py      # starts both servers + tests + keeps them alive
python3 test_frontend.py     # Playwright E2E (provider switch, chat send)
python3 test_full.py         # Playwright full scenario (switch model, provider, streaming)
```

Playwright tests use Chromium, not headless. No lint, typecheck, or build commands besides `npm run build`.

## Key config

Backend loads `.env` from `backend/.env` (not repo root). ChromaDB defaults: host `localhost`, port **8001** (`config.py`) — but `.env` sets port **8000**. The `.env` has actual infra addresses (e.g., `OPENAI_BASE_URL=http://20.0.0.136:1234/v1`).

Providers: `ollama` / `openai` / `lmstudio`. Base class at `backend/providers/base.py`.

## Architecture notes

- Chat messages with `<think... response` tags get thinking/content split server-side (both `/api/chat` and `/api/chat/stream`)
- RAG mode appends context documents into messages before sending to provider
- SSE streaming sends `data: {token, done}` lines; final message includes `full`, `thinking`, `sources`, `metrics`
- Workspace CRUD is in-memory only (no SQLite yet)
- Default system prompt is Russian: `"Ты — полезный ассистент. Отвечай на русском языке."`
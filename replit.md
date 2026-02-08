# Payer Data Intelligence Platform

## Overview
Policy digitalization, versioning, diff analysis, and coverage intelligence platform. Python FastAPI backend serving a REST API with Swagger docs.

## Current State
- Backend API running on port 5000
- SQLite database (local dev) with async SQLAlchemy
- Supports PostgreSQL via `EXTERNAL_DATABASE_URL` environment variable
- LLM integrations: Anthropic Claude, Google Gemini, Azure OpenAI

## Architecture

### Backend (`backend/`)
- **Entry point:** `backend/main.py` — FastAPI app
- **API routes:** `backend/api/routes/policies.py` — policy analysis, upload, diff, Q&A
- **LLM reasoning:** `backend/reasoning/` — Claude, Gemini, OpenAI clients with task-based routing
- **Policy pipeline:** `backend/policy_digitalization/` — 3-pass extraction/validation
- **Storage:** `backend/storage/` — async SQLAlchemy with SQLite/PostgreSQL
- **Config:** `backend/config/settings.py` — Pydantic Settings from `.env`

### Data (`data/`)
- `data/config/` — LLM routing and medication alias configs
- `data/policies/` — Policy documents (PDF, TXT, JSON)
- `data/rubrics/` — Clinical evaluation rubrics

### Key Endpoints
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/policies/analyze` | Coverage analysis |
| GET | `/api/v1/policies/bank` | Policy bank listing |
| POST | `/api/v1/policies/upload` | Upload & digitalize |
| POST | `/api/v1/policies/assistant/query` | Policy Q&A |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger API docs |

## Development
```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 5000 --reload
```

## Environment Variables
- `ANTHROPIC_API_KEY` — Claude API key (required for policy reasoning)
- `GEMINI_API_KEY` — Google Gemini API key
- `AZURE_OPENAI_API_KEY` — Azure OpenAI fallback
- `EXTERNAL_DATABASE_URL` — PostgreSQL connection URL (optional, uses SQLite by default)

## Recent Changes
- 2026-02-08: Imported to Replit, configured to run on port 5000, installed dependencies

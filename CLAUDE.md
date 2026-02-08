# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Payer Data Intelligence (PDI) — standalone platform for payer policy digitalization, versioning, diff analysis, and coverage intelligence. Full-stack: Python FastAPI backend (port 8001) + React/TypeScript frontend (port 6001).

## Development Commands

### Backend
```bash
source venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8001
# Or: ./run.sh
```

### Frontend
```bash
cd frontend && npm run dev    # Dev server on port 6001 (proxies API to 8001)
cd frontend && npm run build  # Production build to frontend/dist/
```

### Full Stack
Start backend first, then frontend. Backend serves the built frontend SPA from `frontend/dist/` in production.

## Architecture

### Backend (`backend/`)

**Entry point:** `backend/main.py` — FastAPI app with async lifespan, CORS, global error handler, SPA serving.

**Request flow:** Routes (`api/routes/policies.py`) → Services (reasoning/, policy_digitalization/) → Storage (storage/) → Database.

**LLM Integration — Task-Based Routing:**
- `backend/reasoning/llm_gateway.py` routes tasks to models based on `data/config/llm_routing.json`
- Claude (`claude_pa_client.py`): Policy reasoning, Q&A. **No fallback** — errors propagate for clinical accuracy. Temperature 0.0.
- Gemini (`gemini_client.py`): Extraction, summarization, general tasks. Falls back to Azure OpenAI.
- Azure OpenAI (`openai_client.py`): Fallback only for Gemini failures.
- `policy_reasoner.py` (31KB): Main policy analysis engine — loads policies, calls Claude, returns `CoverageAssessment`.

**3-Pass Digitalization Pipeline** (`backend/policy_digitalization/pipeline.py`):
1. **Pass 1** (Gemini): Extract structured criteria from policy text
2. **Pass 2** (Claude): Validate extraction against original
3. **Pass 3** (Reference Validator): Validate clinical codes (ICD-10, HCPCS, CPT, NDC)

**Prompt System:** `backend/reasoning/prompt_loader.py` loads `.txt` files from `prompts/` with `{variable_name}` substitution. Global instance via `get_prompt_loader()`. LRU cached (100 max).

**Database:** Async SQLAlchemy with `asyncpg` (PostgreSQL/NeonDB) or `aiosqlite` (local dev). Three tables: `PolicyCacheModel`, `PolicyDiffCacheModel`, `PolicyQACacheModel`. Connection via `EXTERNAL_DATABASE_URL` (NeonDB) or `DATABASE_URL` (SQLite fallback).

**Config:** Pydantic Settings in `backend/config/settings.py`, loaded from `.env`. Access via `get_settings()`.

### Frontend (`frontend/`)

React 18 + TypeScript + Vite + Tailwind CSS 3.4 (Apple HIG design tokens).

**State:** React Query with IndexedDB persistence (`queryCache.ts`), 7-day cache retention.

**Pages:** `Landing.tsx` (marketing), `Policies.tsx` (main app — policy bank, diff viewer, impact analysis, Q&A assistant), `Settings.tsx`.

**API layer:** `services/api.ts` → endpoints defined in `lib/constants.ts` → `ENDPOINTS` object.

**Animations:** Framer Motion with Apple spring easing.

### API Routes
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/policies/analyze` | Coverage analysis |
| GET | `/api/v1/policies/bank` | Policy bank listing |
| POST | `/api/v1/policies/upload` | Upload & digitalize |
| GET | `/api/v1/policies/{payer}/{medication}/versions` | Version history |
| GET | `/api/v1/policies/{payer}/{medication}/diff-summary` | Diff analysis |
| GET | `/api/v1/policies/{payer}/{medication}/impact` | Impact analysis |
| POST | `/api/v1/policies/assistant/query` | Policy Q&A |
| GET | `/health` | Health check |

### Data Files
- `data/config/llm_routing.json` — Task-to-model routing (change routing without code changes)
- `data/config/medication_aliases.json` — Brand/generic medication name mappings
- `data/policies/` — Policy text files and pre-digitized JSON
- `data/rubrics/` — Clinical evaluation rubrics (YAML)

## Critical Rules

- **Prompts:** ALL prompts as `.txt` files in `prompts/` directory. Never hardcode in Python. Use `{variable_name}` placeholders. Load via `get_prompt_loader().load("path/to/prompt.txt", variables={...})`.
- **Logging:** ALL logs in `./tmp/` directory. Use `from backend.config.logging_config import get_logger; logger = get_logger(__name__)`. For file logging: `setup_logging(log_level='DEBUG', log_file='my_module.log')`.
- **LLM calls:** Always set `max_output_tokens` to model maximums (Gemini: 65536, Claude: 8192, Azure: 4096).
- **No fallback for Claude:** Policy reasoning uses Claude with no fallback — clinical accuracy is non-negotiable.
- **Archiving:** Move old file versions to `.archive/<timestamp>/` immediately. Never keep multiple versions (v1, v2, _old suffixes forbidden). Update FILE_INVENTORY.md after archiving.
- **LLM-first approach:** Use LLMs for implementation wherever possible. Never use deterministic methods where LLM-suitable.
- **Environment:** All API keys and model configs loaded from `.env` via `get_settings()`. Never hardcode credentials.

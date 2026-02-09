# Payer Data Intelligence Platform

## Overview
Policy digitalization, versioning, diff analysis, and AI-powered policy intelligence platform. Python FastAPI backend + React TypeScript frontend with premium Apple-inspired dark UI.

## Current State
- Frontend: React + TypeScript + Vite + Tailwind CSS v4, served on port 5000
- Backend: FastAPI API on port 5001, proxied via Vite in dev
- Database: PostgreSQL (NeonDB) with SQLite fallback
- LLM integrations: Anthropic Claude, Google Gemini, Azure OpenAI
- Four core experiences: Command Center, Policy Vault, Policy Intelligence, Policy Assistant

## Architecture

### Frontend (`frontend/`)
- **Framework:** React 19 + TypeScript + Vite 7 + Tailwind CSS v4
- **Design System:** Apple-inspired dark theme with Inter font, frosted glass effects, spring animations
- **Entry point:** `frontend/src/main.tsx` → `frontend/src/App.tsx`
- **Pages:**
  - `CommandCenter.tsx` — Dashboard with stat cards, quality metrics, activity feed
  - `PolicyVault.tsx` — Policy bank grid, drag-and-drop upload with 3-step pipeline progress
  - `PolicyIntelligence.tsx` — Version timeline, diff viewer with severity-coded changes
  - `PolicyAssistant.tsx` — AI chat with filter pills, suggested questions, markdown rendering
- **API layer:** `frontend/src/lib/api.ts` — typed API client for all backend endpoints
- **Styling:** `frontend/src/index.css` — Tailwind v4 @theme tokens (surface, text, accent colors)
- **Animations:** framer-motion throughout, staggered entrances, spring physics

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
| GET | `/api/v1/policies/{payer}/{med}/versions` | Version listing |
| GET | `/api/v1/policies/{payer}/{med}/diff` | Diff summary |
| POST | `/api/v1/policies/upload/infer-metadata` | Metadata inference |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger API docs |

## Development
```bash
# Workflow runs both:
python -m uvicorn backend.main:app --host 0.0.0.0 --port 5001 --reload
cd frontend && npm run dev  # Vite on port 5000, proxies /api to 5001
```

## Production Deployment
```bash
cd frontend && npm run build
python -m uvicorn backend.main:app --host 0.0.0.0 --port 5000
```

## Design System (Light Mode)
- **Backgrounds:** #ffffff (primary), #f5f5f7 (secondary), #e8e8ed (tertiary), #ffffff (elevated)
- **Text:** #1d1d1f (primary), #6e6e73 (secondary), #86868b (tertiary), #aeaeb2 (quaternary)
- **Accent:** #0071e3 (blue, used sparingly), #248a3d (green), #b25000 (amber), #d70015 (red), #8944ab (purple)
- **Borders:** rgba(0,0,0,0.08) (primary), rgba(0,0,0,0.04) (secondary), rgba(0,0,0,0.15) (hover)
- **Font:** Inter via Google Fonts, loaded in index.html
- **Effects:** backdrop-blur-xl, rounded-2xl cards, subtle shadows

## Environment Variables
- `ANTHROPIC_API_KEY` — Claude API key (required for policy reasoning)
- `GEMINI_API_KEY` — Google Gemini API key
- `AZURE_OPENAI_API_KEY` — Azure OpenAI fallback
- `EXTERNAL_DATABASE_URL` — PostgreSQL connection URL (optional, uses SQLite by default)

## User Preferences
- Apple-inspired design: dark, minimal, frosted glass, single blue accent
- NO Coverage Analyzer in this module — four core experiences only
- Premium UI quality matching Apple product standards

## Recent Changes
- 2026-02-09: Added top navbar with Saama logo (from saama.com SVG), vertical separator, and "Payer Intelligence Platform" title; visible on all pages
- 2026-02-09: Added Landing page at "/" with HERO section, four core experiences grid, How It Works steps, and feature highlights; Command Center moved to "/dashboard"
- 2026-02-09: Fixed LLM criteria matching — Claude returns parsed JSON directly (not wrapped in "response" key), differ now handles both formats; semantic matching correctly pairs criteria like DOSE_LIMIT↔DOSING_LIMIT, NO_GENE_THERAPY↔NO_PRIOR_GENE_THERAPY
- 2026-02-09: Added dual-pane policy detail view — clicking a policy card shows extracted JSON data (left) + synced PDF viewer (right) with page navigation
- 2026-02-09: Added PDF serving endpoint at /api/v1/policies/{payer}/{medication}/pdf
- 2026-02-09: Deduplicated policy change entries in Policy Intelligence diff view
- 2026-02-09: Redesigned Summary tab with grouped impact sections (High/Medium/Low + Recommended Actions)
- 2026-02-09: Built complete React frontend with four Apple-inspired pages, all wired to backend APIs
- 2026-02-08: Imported to Replit, configured backend, installed dependencies

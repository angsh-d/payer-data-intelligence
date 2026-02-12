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
cd frontend && npm run dev      # Dev server on port 6001 (proxies /api, /health, /ws to 8001)
cd frontend && npm run build    # Production build to frontend/dist/
cd frontend && npm run lint     # ESLint
cd frontend && npm run preview  # Preview production build
```

### Full Stack
Start backend first, then frontend. Backend serves the built frontend SPA from `frontend/dist/` in production via catch-all route. Root `npm run build` handles full frontend install + build.

### Initial Setup
```bash
python3.10 -m venv venv && source venv/bin/activate
pip install --upgrade pip && pip install -r requirements.txt
cd frontend && npm install
```

## Architecture

### Backend (`backend/`)

**Entry point:** `backend/main.py` — FastAPI app with async lifespan, CORS, global error handler (logs with unique error_id), SPA serving from `frontend/dist/`.

**Request flow:** Routes (`api/routes/policies.py`) → Services (reasoning/, policy_digitalization/) → Storage (storage/) → Database.

**LLM Integration — Task-Based Routing:**
- `backend/reasoning/llm_gateway.py` routes tasks to models based on `data/config/llm_routing.json`
- Claude (`claude_pa_client.py`): Policy reasoning, Q&A. **No fallback** — errors propagate for clinical accuracy. Temperature 0.0.
- Gemini (`gemini_client.py`): Extraction, summarization, general tasks. Falls back to Azure OpenAI.
- Azure OpenAI (`openai_client.py`): Fallback only for Gemini failures.
- `policy_reasoner.py`: Main policy analysis engine — loads policies (with medication alias resolution), calls Claude, returns `CoverageAssessment`.
- Default models: `claude-sonnet-4-20250514` (Claude), `gemini-3-pro-preview` (Gemini), `gpt-4o` (Azure). Configurable via `.env`.

**3-Pass Digitalization Pipeline** (`backend/policy_digitalization/pipeline.py`):
1. **Pass 1** (Gemini): Extract structured criteria from policy text → `RawExtractionResult`
2. **Pass 2** (Claude): Validate extraction against original → `ValidatedExtractionResult`
3. **Pass 3** (Reference Validator): Validate clinical codes (ICD-10, HCPCS, CPT, NDC)

Key modules in `policy_digitalization/`: `extractor.py` (Gemini extraction), `validator.py` (Claude validation), `reference_validator.py` (clinical code validation), `differ.py` (policy diff analysis), `evaluator.py` (clinical evaluation), `policy_assistant.py` (Q&A), `policy_repository.py` (document management), `impact_analyzer.py`, `patient_data_adapter.py`, `file_watcher.py` (monitors policy directory).

**Prompt System:** `backend/reasoning/prompt_loader.py` loads `.txt` files from `prompts/` with `{variable_name}` substitution. Global instance via `get_prompt_loader()`. LRU cached (100 max). Path traversal protection built in.

**Database:** Async SQLAlchemy with `asyncpg` (PostgreSQL/NeonDB) or `aiosqlite` (local dev). Tables: `PolicyCacheModel` (policy text + parsed criteria JSON, indexed on payer+medication), `PolicyDiffCacheModel`, `PolicyQACacheModel`. Connection: `EXTERNAL_DATABASE_URL` (NeonDB) takes priority over `DATABASE_URL` (SQLite default: `data/access_strategy.db`). Connection pooling (size=10, pre_ping=True).

**Config:** Pydantic Settings in `backend/config/settings.py`, loaded from `.env`. Access via `get_settings()` (LRU cached singleton).

**Models:** `backend/models/coverage.py` defines `CoverageAssessment`, `CriterionAssessment`, `DocumentationGap`. `backend/models/enums.py` defines `TaskCategory`, `LLMProvider`, `CoverageStatus`. `backend/api/responses.py` defines `PolicyAnalysisResponse`.

### Frontend (`frontend/`)

React 19 + TypeScript 5.9 + Vite 7 + Tailwind CSS 4 (Apple HIG dark theme with Inter font, frosted glass effects).

**Pages:** `Landing.tsx` (marketing), `CommandCenter.tsx` (dashboard), `PolicyVault.tsx` (policy bank with drag-and-drop upload + 3-step pipeline progress), `PolicyIntelligence.tsx` (version timeline + diff viewer with severity-coded changes), `PolicyAssistant.tsx` (AI chat with filter pills + markdown).

**Routing** (`App.tsx`): `/` (Landing), `/dashboard`, `/vault`, `/intelligence`, `/assistant`. Conditional navbar + sidebar layout.

**Components:** `Navbar.tsx`, `Sidebar.tsx`, `PdfViewer.tsx`, `PolicyDetailView.tsx`.

**API layer:** `lib/api.ts` — typed client with interfaces (`PolicyBankItem`, `PolicyVersion`, `DiffSummaryResponse`, `AssistantResponse`). Base URL: `/api/v1/policies`.

**Animations:** Framer Motion with Apple spring easing.

### API Routes
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/policies/analyze` | Coverage analysis |
| GET | `/api/v1/policies/bank` | Policy bank listing |
| POST | `/api/v1/policies/upload` | Upload & digitalize |
| POST | `/api/v1/policies/upload/infer-metadata` | Metadata inference |
| GET | `/api/v1/policies/{payer}/{medication}/versions` | Version history |
| GET | `/api/v1/policies/{payer}/{medication}/diff-summary` | Diff analysis |
| GET | `/api/v1/policies/{payer}/{medication}/impact` | Impact analysis |
| POST | `/api/v1/policies/assistant/query` | Policy Q&A |
| GET | `/health` | Health check |

Routes also include WebSocket support via `api/routes/websocket.py`. In-memory cache (bounded to 64 entries) on expensive LLM-backed comparisons in the policies route.

### Data Files
- `data/config/llm_routing.json` — Task-to-model routing (change routing without code changes). Primary model first, fallbacks follow.
- `data/config/medication_aliases.json` — Brand/generic medication name mappings
- `data/policies/` — Policy PDFs, text files, and pre-digitized JSON
- `data/patients/` — Sample patient JSON files (pt_001 through pt_005)
- `data/rubrics/default_rubric.md` — Clinical evaluation rubric

### Prompts (`prompts/`)
- `policy_analysis/coverage_assessment.txt`, `gap_identification.txt`
- `policy_digitalization/extraction_pass1.txt`, `validation_pass2.txt`, `criteria_matching.txt`, `change_summary.txt`, `infer_metadata.txt`, `policy_assistant_query.txt`, `policy_assistant_system.txt`
- `system/clinical_reasoning_base.txt`

## Critical Rules

- **Prompts:** ALL prompts as `.txt` files in `prompts/` directory. Never hardcode in Python. Use `{variable_name}` placeholders. Load via `get_prompt_loader().load("path/to/prompt.txt", variables={...})`.
- **Logging:** ALL logs in `./tmp/` directory. Use `from backend.config.logging_config import get_logger; logger = get_logger(__name__)`. For file logging: `setup_logging(log_level='DEBUG', log_file='my_module.log')`. Structured logging via structlog (JSON for files, console renderer for stdout).
- **LLM calls:** Always set `max_output_tokens` to model maximums (Gemini: 65536, Claude: 8192, Azure: 4096).
- **No fallback for Claude:** Policy reasoning uses Claude with no fallback — clinical accuracy is non-negotiable. Claude routes: `policy_reasoning`, `policy_qa`, `appeal_strategy`.
- **No fallback code ever:** Never write workaround code, cached-result fallbacks, or simplified alternatives. Fix root causes.
- **Archiving:** Move old file versions to `.archive/<timestamp>/` immediately. Never keep multiple versions (v1, v2, _old suffixes forbidden). Update FILE_INVENTORY.md after archiving. Never archive CLAUDE.md, SYSTEM_DESIGN.md, FILE_INVENTORY.md, or README.md.
- **LLM-first approach:** Use LLMs for implementation wherever possible. Never use deterministic methods where LLM-suitable.
- **Environment:** All API keys and model configs loaded from `.env` via `get_settings()`. Never hardcode credentials. Key env vars: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `EXTERNAL_DATABASE_URL`.
- **Virtual environment:** Always activate `venv/` before running Python. If venv doesn't exist, create with Python 3.10.
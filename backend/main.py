"""Payer Data Intelligence (PDI) Platform — FastAPI entry point.

Standalone deployment for policy digitalization, versioning, diff analysis, and coverage intelligence.
Backend: port 8001 | Frontend dev: port 6001
"""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config.settings import get_settings
from backend.config.logging_config import setup_logging, get_logger
from backend.storage.database import init_db
from backend.api.routes import policies, websocket

setup_logging(log_level="INFO")
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """PDI application lifespan — database init only."""
    logger.info("Starting Payer Data Intelligence Platform")

    settings = get_settings()
    if not settings.anthropic_api_key:
        logger.error("ANTHROPIC_API_KEY not set — Claude policy reasoning will fail")
    if not settings.gemini_api_key:
        logger.warning("GEMINI_API_KEY not set — Gemini-backed features unavailable")

    await init_db()
    logger.info("Database initialized")

    yield

    logger.info("Shutting down Payer Data Intelligence Platform")


app = FastAPI(
    title="Payer Data Intelligence Platform",
    description="Policy digitalization, versioning, diff analysis, and coverage intelligence",
    version="0.1.0",
    lifespan=lifespan,
)

settings = get_settings()

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    error_id = str(uuid.uuid4())[:8]
    logger.error("Unhandled exception", error_id=error_id, error=str(exc), path=request.url.path, exc_info=True)
    return JSONResponse(status_code=500, content={"error": "Internal server error", "error_id": error_id})


# Routes
app.include_router(policies.router, prefix="/api/v1")
app.include_router(websocket.router)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "0.1.0",
        "platform": "payer-data-intelligence",
        "components": {"database": True},
    }


FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


@app.get("/")
async def root():
    index_html = FRONTEND_DIST / "index.html"
    if index_html.exists():
        return FileResponse(str(index_html))
    return {
        "name": "Payer Data Intelligence Platform",
        "version": "0.1.0",
        "description": "Policy digitalization, versioning, diff analysis, and coverage intelligence",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith("api/"):
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"API endpoint not found: /{full_path}")
    if not FRONTEND_DIST.exists():
        return JSONResponse({"error": "Frontend not built"}, status_code=404)
    try:
        file_path = (FRONTEND_DIST / full_path).resolve()
        file_path.relative_to(FRONTEND_DIST.resolve())
    except (ValueError, RuntimeError):
        return FileResponse(str(FRONTEND_DIST / "index.html"))
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    return FileResponse(str(FRONTEND_DIST / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=5000, reload=True)

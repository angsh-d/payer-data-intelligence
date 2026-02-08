"""Database configuration and session management."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from backend.config.settings import get_settings
from backend.config.logging_config import get_logger

logger = get_logger(__name__)

# Engine and session factory (initialized lazily)
_engine = None
_async_session_factory = None


def get_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        db_url = settings.external_database_url or settings.database_url
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
        if "sslmode=" in db_url or "channel_binding=" in db_url:
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed = urlparse(db_url)
            params = parse_qs(parsed.query)
            ssl_mode = params.pop("sslmode", ["disable"])[0]
            params.pop("channel_binding", None)
            new_query = urlencode(params, doseq=True)
            db_url = urlunparse(parsed._replace(query=new_query))
            if ssl_mode == "disable":
                connect_args = {"ssl": None}
            else:
                connect_args = {"ssl": "require"}
        else:
            connect_args = {}
        # Disable asyncpg prepared statement cache to avoid
        # InvalidCachedStatementError after schema changes.
        connect_args.setdefault("statement_cache_size", 0)
        _engine = create_async_engine(
            db_url,
            echo=settings.app_env == "development",
            future=True,
            connect_args=connect_args,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
        db_type = db_url.split("://")[0] if "://" in db_url else "unknown"
        logger.info("Database engine created", db_type=db_type)
    return _engine


def get_session_factory():
    """Get or create the session factory."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_engine()
        _async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False
        )
    return _async_session_factory


# Alias for convenience
AsyncSessionLocal = get_session_factory


async def _ensure_amendment_columns(engine) -> None:
    """Add amendment columns to policy_cache if they don't exist (PostgreSQL)."""
    from sqlalchemy import text

    async with engine.begin() as conn:
        for col, sql_type in [
            ("source_filename", "VARCHAR(500)"),
            ("upload_notes", "TEXT"),
            ("amendment_date", "TIMESTAMPTZ"),
            ("parent_version_id", "VARCHAR(36)"),
        ]:
            try:
                await conn.execute(text(
                    f"ALTER TABLE policy_cache ADD COLUMN IF NOT EXISTS {col} {sql_type}"
                ))
            except Exception as e:
                logger.debug(f"Column {col} may already exist: {e}")


async def init_db() -> None:
    """Initialize the database, creating all tables."""
    from backend.storage.models import Base as ModelsBase

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.create_all)
    await _ensure_amendment_columns(engine)
    logger.info("Database initialized")


async def drop_db() -> None:
    """Drop all database tables (use with caution)."""
    from backend.storage.models import Base as ModelsBase

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(ModelsBase.metadata.drop_all)
    logger.warning("Database tables dropped")


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for database sessions.

    Usage:
        async with get_db() as db:
            result = await db.execute(query)
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error("Database session error", error=str(e))
            raise
        finally:
            await session.close()


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI routes.

    Usage:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

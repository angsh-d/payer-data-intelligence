"""File watcher for automatic policy digitalization on file changes."""

import asyncio
import hashlib
import time
from pathlib import Path
from typing import Callable, Dict, Optional, Awaitable

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

from backend.config.logging_config import get_logger
from backend.config.settings import get_settings

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".txt"}
DEBOUNCE_SECONDS = 3.0

# Suppression set: paths currently being processed by the upload endpoint.
# The file watcher skips these to avoid duplicate pipeline runs.
_upload_suppressed: set[str] = set()


def suppress_watcher(path: str):
    """Mark a path as being handled by the upload endpoint."""
    _upload_suppressed.add(str(Path(path).resolve()))


def unsuppress_watcher(path: str):
    """Remove upload suppression for a path."""
    _upload_suppressed.discard(str(Path(path).resolve()))


class _PolicyEventHandler(FileSystemEventHandler):
    """Watchdog handler that forwards relevant file events to asyncio loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop, callback: Callable):
        super().__init__()
        self._loop = loop
        self._callback = callback
        self._pending: Dict[str, float] = {}

    def _is_relevant(self, path: str) -> bool:
        p = Path(path)
        return p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.name.startswith(".")

    def on_created(self, event):
        if not event.is_directory and self._is_relevant(event.src_path):
            self._schedule(event.src_path)

    def on_modified(self, event):
        if not event.is_directory and self._is_relevant(event.src_path):
            self._schedule(event.src_path)

    def _schedule(self, path: str):
        now = time.monotonic()
        self._pending[path] = now
        self._loop.call_soon_threadsafe(
            self._loop.call_later,
            DEBOUNCE_SECONDS,
            lambda p=path, t=now: self._fire_if_still_pending(p, t),
        )

    def _fire_if_still_pending(self, path: str, scheduled_time: float):
        if self._pending.get(path) == scheduled_time:
            del self._pending[path]
            asyncio.ensure_future(self._callback(path))


class PolicyFileWatcher:
    """Monitors data/policies/ for file changes and triggers digitalization."""

    def __init__(
        self,
        policies_dir: Optional[Path] = None,
        notification_callback: Optional[Callable[..., Awaitable]] = None,
    ):
        self._policies_dir = policies_dir or Path(get_settings().policies_dir)
        self._notification_callback = notification_callback
        self._observer: Optional[Observer] = None
        self._locks: Dict[str, asyncio.Lock] = {}

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    @staticmethod
    def _parse_filename(path: str):
        """Parse {payer}_{medication}.{ext} from filename."""
        p = Path(path)
        stem = p.stem
        # Skip digitized JSON files
        if stem.endswith("_digitized"):
            return None, None
        parts = stem.split("_", 1)
        if len(parts) != 2:
            return None, None
        return parts[0].lower(), parts[1].lower()

    @staticmethod
    def _compute_hash(filepath: str) -> str:
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    async def _on_file_change(self, filepath: str):
        """Called (debounced) when a policy file is created or modified."""
        resolved = str(Path(filepath).resolve())
        if resolved in _upload_suppressed:
            logger.info("Skipping file watcher — upload endpoint is handling this file", path=filepath)
            return

        payer, medication = self._parse_filename(filepath)
        if not payer or not medication:
            logger.debug("Skipping non-policy file", path=filepath)
            return

        lock = self._get_lock(f"{payer}:{medication}")
        if lock.locked():
            logger.info("Skipping concurrent processing", payer=payer, medication=medication)
            return

        async with lock:
            try:
                file_hash = self._compute_hash(filepath)

                # Check if hash differs from stored version
                from backend.policy_digitalization.policy_repository import get_policy_repository
                repo = get_policy_repository()
                versions = await repo.list_versions(payer, medication)

                # Check latest version hash
                if versions:
                    latest = versions[0]
                    if latest.content_hash == file_hash[:16]:
                        logger.debug("File unchanged, skipping", payer=payer, medication=medication)
                        return

                logger.info(
                    "Policy file change detected, starting digitalization",
                    payer=payer, medication=medication, path=filepath,
                )

                # Run pipeline
                from backend.policy_digitalization.pipeline import get_digitalization_pipeline
                pipeline = get_digitalization_pipeline()

                p = Path(filepath)
                source_type = "pdf" if p.suffix.lower() == ".pdf" else "text"

                if source_type == "text":
                    source = p.read_text(encoding="utf-8")
                else:
                    source = filepath

                result = await pipeline.digitalize_policy(
                    source=source,
                    source_type=source_type,
                    payer_name=payer,
                    medication_name=medication,
                )

                if not result.policy:
                    logger.error("Digitalization produced no policy", payer=payer, medication=medication)
                    return

                from backend.models.policy_schema import DigitizedPolicy
                policy = DigitizedPolicy(**result.policy)
                policy.payer_name = payer
                policy.medication_name = medication
                policy.source_document_hash = file_hash[:16]

                # Determine next version label
                next_version = f"v{len(versions) + 1}"
                await repo.store_version(policy, next_version)

                logger.info(
                    "Policy digitalized and stored",
                    payer=payer, medication=medication, version=next_version,
                    quality=result.extraction_quality,
                )

                # Notify via callback
                if self._notification_callback:
                    await self._notification_callback({
                        "event": "policy_update",
                        "payer": payer,
                        "medication": medication,
                        "version": next_version,
                        "extraction_quality": result.extraction_quality,
                        "criteria_count": result.criteria_count,
                    })

            except Exception as e:
                logger.error(
                    "Error processing policy file change",
                    payer=payer, medication=medication, error=str(e),
                    exc_info=True,
                )

    def start(self):
        """Start watching the policies directory."""
        if not self._policies_dir.exists():
            self._policies_dir.mkdir(parents=True, exist_ok=True)

        loop = asyncio.get_event_loop()
        handler = _PolicyEventHandler(loop, self._on_file_change)

        self._observer = Observer()
        self._observer.schedule(handler, str(self._policies_dir), recursive=False)
        self._observer.daemon = True
        self._observer.start()
        logger.info("Policy file watcher started", directory=str(self._policies_dir))

    def stop(self):
        """Stop the file watcher."""
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
            logger.info("Policy file watcher stopped")

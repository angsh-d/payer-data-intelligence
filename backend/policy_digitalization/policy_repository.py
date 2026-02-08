"""Policy Repository — stores and retrieves digitized policies from PolicyCacheModel."""

import json
import hashlib
from datetime import datetime, timezone
from typing import Optional, List
from uuid import uuid4

from backend.models.policy_schema import DigitizedPolicy
from backend.storage.database import get_db
from backend.storage.models import PolicyCacheModel
from backend.policy_digitalization.exceptions import PolicyNotFoundError
from backend.config.logging_config import get_logger

logger = get_logger(__name__)


class PolicyVersionInfo:
    """Lightweight version info for listing."""
    def __init__(
        self,
        version: str,
        cached_at: str,
        content_hash: str,
        id: Optional[str] = None,
        source_filename: Optional[str] = None,
        upload_notes: Optional[str] = None,
        amendment_date: Optional[str] = None,
        parent_version_id: Optional[str] = None,
    ):
        self.version = version
        self.cached_at = cached_at
        self.content_hash = content_hash
        self.id = id
        self.source_filename = source_filename
        self.upload_notes = upload_notes
        self.amendment_date = amendment_date
        self.parent_version_id = parent_version_id


class PolicyRepository:
    """Async repository for digitized policies — populates PolicyCacheModel.parsed_criteria."""

    async def store(self, policy: DigitizedPolicy) -> str:
        """Store a digitized policy, populating parsed_criteria."""
        from sqlalchemy import select

        policy_dict = policy.model_dump(mode="json")
        content_hash = hashlib.sha256(
            json.dumps(policy_dict, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]

        payer = policy.payer_name.lower().replace(" ", "_")
        medication = policy.medication_name.lower().replace(" ", "_")
        version = policy.version or "latest"

        async with get_db() as session:
            # Check for existing entry
            stmt = select(PolicyCacheModel).where(
                PolicyCacheModel.payer_name == payer,
                PolicyCacheModel.medication_name == medication,
                PolicyCacheModel.policy_version == version,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.parsed_criteria = policy_dict
                existing.content_hash = content_hash
                existing.cached_at = datetime.now(timezone.utc)
                cache_id = existing.id
            else:
                cache_id = str(uuid4())
                entry = PolicyCacheModel(
                    id=cache_id,
                    payer_name=payer,
                    medication_name=medication,
                    policy_version=version,
                    content_hash=content_hash,
                    policy_text=json.dumps(policy_dict, default=str),
                    parsed_criteria=policy_dict,
                )
                session.add(entry)
            # get_db() auto-commits on success

        logger.info("Policy stored", payer=payer, medication=medication, version=version)
        return cache_id

    def _medication_keys(self, medication: str) -> list:
        """Return the medication key plus its brand/generic alias (if any)."""
        from backend.policy_digitalization.pipeline import MEDICATION_NAME_ALIASES
        keys = [medication]
        alias = MEDICATION_NAME_ALIASES.get(medication)
        if alias:
            keys.append(alias)
        return keys

    async def load(
        self, payer_name: str, medication_name: str, version: str = "latest"
    ) -> Optional[DigitizedPolicy]:
        """Load a digitized policy from cache.

        Checks brand/generic aliases when the primary medication name
        is not found.  Falls back to the most recent version if the
        requested version (typically 'latest') is not found.
        """
        from sqlalchemy import select

        payer = payer_name.lower().replace(" ", "_")
        medication = medication_name.lower().replace(" ", "_")
        med_keys = self._medication_keys(medication)

        async with get_db() as session:
            # Exact version match (try primary + alias)
            for mk in med_keys:
                stmt = select(PolicyCacheModel).where(
                    PolicyCacheModel.payer_name == payer,
                    PolicyCacheModel.medication_name == mk,
                    PolicyCacheModel.policy_version == version,
                )
                result = await session.execute(stmt)
                entry = result.scalar_one_or_none()
                if entry and entry.parsed_criteria:
                    try:
                        return DigitizedPolicy(**entry.parsed_criteria)
                    except Exception as e:
                        logger.warning(
                            "Corrupted cached policy, trying next",
                            payer=payer, medication=mk, error=str(e)
                        )

            # Fallback: most recent row for primary + alias
            for mk in med_keys:
                stmt = (
                    select(PolicyCacheModel)
                    .where(
                        PolicyCacheModel.payer_name == payer,
                        PolicyCacheModel.medication_name == mk,
                    )
                    .order_by(PolicyCacheModel.cached_at.desc())
                    .limit(1)
                )
                result = await session.execute(stmt)
                entry = result.scalar_one_or_none()
                if entry and entry.parsed_criteria:
                    try:
                        return DigitizedPolicy(**entry.parsed_criteria)
                    except Exception as e:
                        logger.warning(
                            "Corrupted cached policy, treating as cache miss",
                            payer=payer, medication=mk, error=str(e)
                        )

            return None

    async def invalidate(self, payer_name: str, medication_name: str) -> bool:
        """Invalidate cached policy."""
        from sqlalchemy import delete

        payer = payer_name.lower().replace(" ", "_")
        medication = medication_name.lower().replace(" ", "_")

        async with get_db() as session:
            stmt = delete(PolicyCacheModel).where(
                PolicyCacheModel.payer_name == payer,
                PolicyCacheModel.medication_name == medication,
            )
            result = await session.execute(stmt)
            deleted = result.rowcount > 0

        logger.info("Policy cache invalidated", payer=payer, medication=medication, deleted=deleted)
        return deleted

    async def store_version(
        self,
        policy: DigitizedPolicy,
        version_label: str,
        source_filename: Optional[str] = None,
        upload_notes: Optional[str] = None,
        amendment_date: Optional[datetime] = None,
    ) -> str:
        """Store a specific version of a digitized policy with amendment metadata."""
        from sqlalchemy import select, update

        policy.version = version_label
        cache_id = await self.store(policy)

        payer = policy.payer_name.lower().replace(" ", "_")
        medication = policy.medication_name.lower().replace(" ", "_")

        async with get_db() as session:
            # Find parent: most recent prior version for same payer+med
            parent_id = None
            stmt = (
                select(PolicyCacheModel.id)
                .where(
                    PolicyCacheModel.payer_name == payer,
                    PolicyCacheModel.medication_name == medication,
                    PolicyCacheModel.id != cache_id,
                )
                .order_by(PolicyCacheModel.cached_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row:
                parent_id = row

            # Update amendment metadata on the stored row
            update_stmt = (
                update(PolicyCacheModel)
                .where(PolicyCacheModel.id == cache_id)
                .values(
                    source_filename=source_filename,
                    upload_notes=upload_notes,
                    amendment_date=amendment_date,
                    parent_version_id=parent_id,
                )
            )
            await session.execute(update_stmt)

        logger.info(
            "Policy version stored with amendment metadata",
            version=version_label,
            parent_version_id=parent_id,
        )
        return cache_id

    async def list_versions(self, payer: str, medication: str) -> List[PolicyVersionInfo]:
        """List all stored versions for a payer/medication (includes brand/generic alias)."""
        from sqlalchemy import select, or_

        payer_key = payer.lower().replace(" ", "_")
        med_key = medication.lower().replace(" ", "_")
        med_keys = self._medication_keys(med_key)

        async with get_db() as session:
            stmt = (
                select(PolicyCacheModel)
                .where(
                    PolicyCacheModel.payer_name == payer_key,
                    or_(*[PolicyCacheModel.medication_name == mk for mk in med_keys]),
                )
                .order_by(PolicyCacheModel.cached_at.desc())
            )
            result = await session.execute(stmt)
            entries = result.scalars().all()

            # Deduplicate by version label (prefer the primary medication key)
            seen_versions = set()
            unique = []
            for e in entries:
                v = e.policy_version or "latest"
                if v not in seen_versions:
                    seen_versions.add(v)
                    unique.append(e)

            return [
                PolicyVersionInfo(
                    version=e.policy_version or "latest",
                    cached_at=e.cached_at.isoformat() if e.cached_at else "",
                    content_hash=e.content_hash,
                    id=e.id,
                    source_filename=e.source_filename,
                    upload_notes=e.upload_notes,
                    amendment_date=e.amendment_date.isoformat() if e.amendment_date else None,
                    parent_version_id=e.parent_version_id,
                )
                for e in unique
            ]

    async def load_version(
        self, payer: str, medication: str, version: str
    ) -> Optional[DigitizedPolicy]:
        """Load a specific version."""
        return await self.load(payer, medication, version)


# Global instance
_policy_repository: Optional[PolicyRepository] = None


def get_policy_repository() -> PolicyRepository:
    """Get or create global PolicyRepository."""
    global _policy_repository
    if _policy_repository is None:
        _policy_repository = PolicyRepository()
    return _policy_repository

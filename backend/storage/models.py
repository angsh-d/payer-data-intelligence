"""SQLAlchemy ORM models for PDI database tables."""
from datetime import datetime, timezone

def _utcnow():
    """Return current UTC time (timezone-aware)."""
    return datetime.now(timezone.utc)

from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, Index, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class PolicyCacheModel(Base):
    """Database model for cached policy documents."""
    __tablename__ = "policy_cache"

    id = Column(String(36), primary_key=True)
    payer_name = Column(String(100), nullable=False)
    medication_name = Column(String(200), nullable=False)
    policy_version = Column(String(50), nullable=True)

    cached_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    content_hash = Column(String(64), nullable=False)

    source_filename = Column(String(500), nullable=True)
    upload_notes = Column(Text, nullable=True)
    amendment_date = Column(DateTime(timezone=True), nullable=True)
    parent_version_id = Column(String(36), nullable=True)

    policy_text = Column(Text, nullable=False)
    parsed_criteria = Column(JSON, nullable=True)

    __table_args__ = (
        Index('ix_policy_cache_payer_med', 'payer_name', 'medication_name'),
        Index('ix_policy_cache_payer_med_version', 'payer_name', 'medication_name', 'policy_version'),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "payer_name": self.payer_name,
            "medication_name": self.medication_name,
            "policy_version": self.policy_version,
            "cached_at": self.cached_at.isoformat() if self.cached_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "content_hash": self.content_hash,
        }


class PolicyDiffCacheModel(Base):
    """Persistent cache for policy diff results + LLM summaries."""
    __tablename__ = "policy_diff_cache"

    id = Column(String(36), primary_key=True)
    payer_name = Column(String(100), nullable=False)
    medication_name = Column(String(200), nullable=False)
    old_version = Column(String(50), nullable=False)
    new_version = Column(String(50), nullable=False)
    old_content_hash = Column(String(64), nullable=False)
    new_content_hash = Column(String(64), nullable=False)
    diff_data = Column(JSON, nullable=False)
    summary_data = Column(JSON, nullable=False)
    cached_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint('payer_name', 'medication_name', 'old_version', 'new_version',
                         name='uq_diff_cache_versions'),
        Index('ix_diff_cache_payer_med', 'payer_name', 'medication_name'),
    )


class PolicyImpactCacheModel(Base):
    """Persistent cache for patient impact analysis results."""
    __tablename__ = "policy_impact_cache"

    id = Column(String(36), primary_key=True)
    payer_name = Column(String(100), nullable=False)
    medication_name = Column(String(200), nullable=False)
    old_version = Column(String(50), nullable=False)
    new_version = Column(String(50), nullable=False)
    old_content_hash = Column(String(64), nullable=False)
    new_content_hash = Column(String(64), nullable=False)
    impact_data = Column(JSON, nullable=False)
    cached_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint('payer_name', 'medication_name', 'old_version', 'new_version',
                         name='uq_impact_cache_versions'),
        Index('ix_impact_cache_payer_med', 'payer_name', 'medication_name'),
    )


class PolicyQACacheModel(Base):
    """Semantic cache for Policy Assistant Q&A pairs with embeddings."""
    __tablename__ = "policy_qa_cache"

    id = Column(String(36), primary_key=True)
    question_text = Column(Text, nullable=False)
    question_embedding = Column(JSON, nullable=False)
    payer_filter = Column(String(100), nullable=True)
    medication_filter = Column(String(200), nullable=True)
    policy_content_hash = Column(String(64), nullable=False)
    response_data = Column(JSON, nullable=False)
    cached_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    hit_count = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index('ix_qa_cache_filters', 'payer_filter', 'medication_filter'),
        Index('ix_qa_cache_policy_hash', 'policy_content_hash'),
    )

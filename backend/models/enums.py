"""Enumeration types for the Payer Data Intelligence Platform."""
from enum import Enum


class TaskCategory(str, Enum):
    """Categories of LLM tasks for model routing."""
    POLICY_REASONING = "policy_reasoning"
    APPEAL_STRATEGY = "appeal_strategy"
    APPEAL_DRAFTING = "appeal_drafting"
    SUMMARY_GENERATION = "summary_generation"
    DATA_EXTRACTION = "data_extraction"
    NOTIFICATION = "notification"
    POLICY_QA = "policy_qa"


class LLMProvider(str, Enum):
    """Available LLM providers."""
    CLAUDE = "claude"
    GEMINI = "gemini"
    AZURE_OPENAI = "azure_openai"


class CoverageStatus(str, Enum):
    """Coverage assessment status."""
    COVERED = "covered"
    LIKELY_COVERED = "likely_covered"
    REQUIRES_PA = "requires_pa"
    CONDITIONAL = "conditional"
    PEND = "pend"
    NOT_COVERED = "not_covered"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"
    UNKNOWN = "unknown"


class EventType(str, Enum):
    """Types of audit events."""
    CASE_CREATED = "case_created"
    STAGE_CHANGED = "stage_changed"
    POLICY_ANALYZED = "policy_analyzed"
    STRATEGY_GENERATED = "strategy_generated"
    STRATEGY_SELECTED = "strategy_selected"
    ACTION_EXECUTED = "action_executed"
    PAYER_RESPONSE = "payer_response"
    RECOVERY_INITIATED = "recovery_initiated"
    CASE_COMPLETED = "case_completed"
    ERROR_OCCURRED = "error_occurred"


class DocumentType(str, Enum):
    """Types of clinical documents."""
    LAB_RESULT = "lab_result"
    IMAGING = "imaging"
    CLINICAL_NOTE = "clinical_note"
    PRESCRIPTION = "prescription"
    PRIOR_AUTH_FORM = "prior_auth_form"
    APPEAL_LETTER = "appeal_letter"
    PEER_TO_PEER_NOTES = "peer_to_peer_notes"

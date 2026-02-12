"""Agent tools — callable functions the LLM agent can invoke during reasoning."""

import json
from typing import Dict, Any, Optional, List

from backend.config.logging_config import get_logger

logger = get_logger(__name__)


class ToolResult:
    """Result of a tool invocation."""

    def __init__(self, name: str, data: Any, success: bool = True, error: Optional[str] = None):
        self.name = name
        self.data = data
        self.success = success
        self.error = error

    def to_context(self) -> str:
        if not self.success:
            return f"[Tool:{self.name}] ERROR: {self.error}"
        if isinstance(self.data, dict):
            return f"[Tool:{self.name}] {json.dumps(self.data, default=str, indent=2)}"
        return f"[Tool:{self.name}] {self.data}"


TOOL_DEFINITIONS = [
    {
        "name": "search_policy_bank",
        "description": "Search the policy bank for digitized policies matching a payer and/or medication. Returns structured criteria summaries.",
        "parameters": {"payer": "optional string", "medication": "optional string"},
    },
    {
        "name": "lookup_clinical_code",
        "description": "Validate a clinical code (ICD-10, CPT, HCPCS, NDC) and return its description.",
        "parameters": {"code": "string", "code_system": "ICD-10 | CPT | HCPCS | NDC"},
    },
    {
        "name": "compare_with_prior_version",
        "description": "Compare the current digitized policy with a prior version and return a diff summary.",
        "parameters": {"payer": "string", "medication": "string", "old_version": "string", "new_version": "string"},
    },
    {
        "name": "get_patient_context",
        "description": "Load patient clinical data for a specific patient ID to evaluate against policy criteria.",
        "parameters": {"patient_id": "string"},
    },
    {
        "name": "get_policy_text",
        "description": "Retrieve the raw policy document text for a payer/medication combination.",
        "parameters": {"payer": "string", "medication": "string"},
    },
]


async def execute_tool(tool_name: str, params: Dict[str, Any]) -> ToolResult:
    """Execute a named tool with the given parameters."""
    try:
        if tool_name == "search_policy_bank":
            return await _search_policy_bank(params)
        elif tool_name == "lookup_clinical_code":
            return await _lookup_clinical_code(params)
        elif tool_name == "compare_with_prior_version":
            return await _compare_with_prior_version(params)
        elif tool_name == "get_patient_context":
            return await _get_patient_context(params)
        elif tool_name == "get_policy_text":
            return await _get_policy_text(params)
        else:
            return ToolResult(tool_name, None, success=False, error=f"Unknown tool: {tool_name}")
    except Exception as e:
        logger.error("Tool execution failed", tool=tool_name, error=str(e))
        return ToolResult(tool_name, None, success=False, error=str(e))


async def _search_policy_bank(params: Dict[str, Any]) -> ToolResult:
    """Search digitized policies in the database."""
    from sqlalchemy import select
    from backend.storage.database import get_db
    from backend.storage.models import PolicyCacheModel

    payer = params.get("payer", "").lower() if params.get("payer") else None
    medication = params.get("medication", "").lower() if params.get("medication") else None

    async with get_db() as session:
        stmt = select(PolicyCacheModel).where(PolicyCacheModel.parsed_criteria.isnot(None))
        if payer:
            stmt = stmt.where(PolicyCacheModel.payer_name == payer)
        if medication:
            stmt = stmt.where(PolicyCacheModel.medication_name == medication)
        stmt = stmt.order_by(PolicyCacheModel.cached_at.desc()).limit(10)
        result = await session.execute(stmt)
        entries = result.scalars().all()

    policies = []
    for entry in entries:
        criteria = entry.parsed_criteria or {}
        policies.append({
            "payer": entry.payer_name,
            "medication": entry.medication_name,
            "version": entry.policy_version,
            "criteria_count": len(criteria.get("atomic_criteria", {})),
            "indications_count": len(criteria.get("indications", [])),
            "quality": criteria.get("extraction_quality", "unknown"),
        })

    return ToolResult("search_policy_bank", {"matches": policies, "count": len(policies)})


async def _lookup_clinical_code(params: Dict[str, Any]) -> ToolResult:
    """Validate a clinical code format and return basic info."""
    from backend.policy_digitalization.reference_validator import ReferenceDataValidator

    code = params.get("code", "")
    code_system = params.get("code_system", "").upper()

    validator = ReferenceDataValidator()
    is_valid = False

    if code_system == "ICD-10":
        is_valid = validator._validate_icd10_format(code)
    elif code_system == "CPT":
        is_valid = validator._validate_cpt_format(code)
    elif code_system == "HCPCS":
        is_valid = validator._validate_hcpcs_format(code)
    elif code_system == "NDC":
        is_valid = validator._validate_ndc_format(code)

    return ToolResult("lookup_clinical_code", {
        "code": code,
        "system": code_system,
        "format_valid": is_valid,
    })


async def _compare_with_prior_version(params: Dict[str, Any]) -> ToolResult:
    """Run a diff between two policy versions."""
    from backend.policy_digitalization.policy_repository import get_policy_repository
    from backend.policy_digitalization.differ import PolicyDiffer

    payer = params.get("payer", "").lower()
    medication = params.get("medication", "").lower()
    old_ver = params.get("old_version", "")
    new_ver = params.get("new_version", "")

    repo = get_policy_repository()
    old_policy = await repo.load_version(payer, medication, old_ver)
    new_policy = await repo.load_version(payer, medication, new_ver)

    if not old_policy or not new_policy:
        return ToolResult("compare_with_prior_version", None, success=False,
                          error=f"Could not load versions {old_ver} and/or {new_ver}")

    differ = PolicyDiffer()
    diff = await differ.diff(old_policy, new_policy)
    summary = diff.summary.model_dump() if hasattr(diff, "summary") else {}

    return ToolResult("compare_with_prior_version", {
        "old_version": old_ver,
        "new_version": new_ver,
        "summary": summary,
    })


async def _get_patient_context(params: Dict[str, Any]) -> ToolResult:
    """Load patient data from the patients directory."""
    import json as json_mod
    from pathlib import Path
    from backend.config.settings import get_settings

    patient_id = params.get("patient_id", "")
    patients_dir = Path(get_settings().patients_dir)

    for pf in patients_dir.glob("*.json"):
        with open(pf, "r", encoding="utf-8") as f:
            data = json_mod.load(f)
        if data.get("patient_id") == patient_id or pf.stem == patient_id:
            return ToolResult("get_patient_context", data)

    return ToolResult("get_patient_context", None, success=False,
                      error=f"Patient {patient_id} not found")


async def _get_policy_text(params: Dict[str, Any]) -> ToolResult:
    """Load raw policy text from file."""
    from pathlib import Path
    from backend.config.settings import get_settings

    payer = params.get("payer", "").lower().replace(" ", "_")
    medication = params.get("medication", "").lower().replace(" ", "_")

    policies_dir = Path(get_settings().policies_dir)
    txt_path = policies_dir / f"{payer}_{medication}.txt"

    if txt_path.exists():
        text = txt_path.read_text(encoding="utf-8")
        # Truncate for context window management
        if len(text) > 8000:
            text = text[:8000] + "\n... [truncated]"
        return ToolResult("get_policy_text", {"text": text, "length": len(text)})

    return ToolResult("get_policy_text", None, success=False,
                      error=f"No policy text found for {payer}/{medication}")

"""Policy analysis API routes."""
import re
import json
import hashlib
import traceback
import uuid
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from backend.api.requests import AnalyzePoliciesRequest
from backend.api.responses import PolicyAnalysisResponse
from backend.reasoning.policy_reasoner import get_policy_reasoner
from backend.policy_digitalization.exceptions import PolicyNotFoundError
from backend.config.logging_config import get_logger
from backend.config.settings import get_settings

logger = get_logger(__name__)

# ─── In-memory caches for expensive LLM-backed comparisons ───
# Key: (payer, medication, old_version, new_version) → response dict
# Bounded: evict oldest entries when exceeding MAX_CACHE_SIZE
MAX_CACHE_SIZE = 64

_diff_summary_cache: dict[tuple[str, str, str, str], dict] = {}
_impact_cache: dict[tuple[str, str, str, str], dict] = {}


def _bounded_cache_set(cache: dict, key: tuple, value: dict) -> None:
    """Set a cache entry, evicting the oldest if at capacity."""
    if len(cache) >= MAX_CACHE_SIZE:
        oldest_key = next(iter(cache))
        del cache[oldest_key]
    cache[key] = value

# Validation pattern for payer and medication names
# Allows letters, numbers, hyphens, and underscores only
VALID_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9_-]+$')
MAX_NAME_LENGTH = 50


def _validate_name(name: str, field: str) -> str:
    """Validate and sanitize payer/medication name."""
    if not name:
        raise HTTPException(status_code=400, detail=f"{field} cannot be empty")
    if len(name) > MAX_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"{field} exceeds maximum length of {MAX_NAME_LENGTH}")
    if not VALID_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=400,
            detail=f"{field} contains invalid characters. Only letters, numbers, hyphens, and underscores are allowed."
        )
    return name.lower()

router = APIRouter(prefix="/policies", tags=["Policies"])


@router.post("/analyze", response_model=PolicyAnalysisResponse)
async def analyze_policy(request: AnalyzePoliciesRequest):
    """
    Analyze a payer policy for coverage eligibility.

    This endpoint uses Claude for policy reasoning - no fallback.

    Args:
        request: Analysis request with patient, medication, and payer info

    Returns:
        Coverage assessment results
    """
    try:
        payer_safe = _validate_name(request.payer_name, "Payer")
        reasoner = get_policy_reasoner()

        assessment = await reasoner.assess_coverage(
            patient_info=request.patient_info,
            medication_info=request.medication_info,
            payer_name=payer_safe
        )

        return PolicyAnalysisResponse(
            payer_name=assessment.payer_name,
            coverage_status=assessment.coverage_status.value,
            approval_likelihood=assessment.approval_likelihood,
            criteria_met=assessment.criteria_met_count,
            criteria_total=assessment.criteria_total_count,
            documentation_gaps=[g.model_dump() for g in assessment.documentation_gaps],
            recommendations=assessment.recommendations,
            step_therapy_required=assessment.step_therapy_required,
            step_therapy_satisfied=assessment.step_therapy_satisfied
        )

    except (FileNotFoundError, PolicyNotFoundError):
        raise HTTPException(status_code=404, detail=f"Policy not found for {payer_safe}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error analyzing policy", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/available")
async def list_available_policies():
    """
    List available policy documents.

    Returns:
        List of available payer/medication policy combinations
    """
    from pathlib import Path

    policies_dir = Path(get_settings().policies_dir)
    policies = []

    if policies_dir.exists():
        for policy_file in policies_dir.glob("*.txt"):
            name = policy_file.stem
            parts = name.split("_")
            if len(parts) >= 2:
                payer = parts[0].title()
                medication = "_".join(parts[1:]).replace("_", " ").title()
                policies.append({
                    "file": policy_file.name,
                    "payer": payer,
                    "medication": medication
                })

    return {"policies": policies}


MEDICATION_ALIASES = {
    "ciltacabtagene_autoleucel": "carvykti",
    "lisocabtagene_maraleucel": "breyanzi",
    "nusinersen": "spinraza",
    "palbociclib": "ibrance",
    "infliximab": "remicade",
}

def _canonical_medication(med: str) -> str:
    return MEDICATION_ALIASES.get(med, med)


@router.get("/bank")
async def get_policy_bank():
    """
    Get all digitized policies with version counts, deduplicated by brand/generic pairs.
    """
    from sqlalchemy import select, func
    from backend.storage.database import get_db
    from backend.storage.models import PolicyCacheModel

    try:
        async with get_db() as session:
            stmt = (
                select(
                    PolicyCacheModel.payer_name,
                    PolicyCacheModel.medication_name,
                    func.count(PolicyCacheModel.id).label("version_count"),
                    func.max(PolicyCacheModel.cached_at).label("last_updated"),
                )
                .group_by(PolicyCacheModel.payer_name, PolicyCacheModel.medication_name)
            )
            result = await session.execute(stmt)
            rows = result.all()

        from backend.policy_digitalization.policy_repository import get_policy_repository
        repo = get_policy_repository()

        merged: dict[str, dict] = {}
        for row in rows:
            canonical = _canonical_medication(row.medication_name)
            key = f"{row.payer_name}/{canonical}"

            versions = await repo.list_versions(row.payer_name, row.medication_name)
            source_filenames = [v.source_filename for v in versions if v.source_filename]
            non_latest = [v for v in versions if v.version != "latest"]
            content_hashes = {v.content_hash for v in (non_latest if non_latest else versions) if v.content_hash}

            if key in merged:
                existing = merged[key]
                existing["_hashes"].update(content_hashes)
                existing["version_count"] = len(existing["_hashes"])
                existing["source_filenames"] = list(set(existing["source_filenames"] + source_filenames))
                if row.last_updated and (
                    not existing["_last_updated"] or row.last_updated > existing["_last_updated"]
                ):
                    existing["_last_updated"] = row.last_updated
                    existing["last_updated"] = row.last_updated.isoformat()
            else:
                latest_version = versions[0].version if versions else "unknown"
                latest_policy = await repo.load_version(row.payer_name, row.medication_name, latest_version)
                extraction_quality = latest_policy.extraction_quality if latest_policy else "unknown"

                merged[key] = {
                    "payer": row.payer_name,
                    "medication": canonical,
                    "latest_version": latest_version,
                    "version_count": len(content_hashes),
                    "last_updated": row.last_updated.isoformat() if row.last_updated else None,
                    "_last_updated": row.last_updated,
                    "_hashes": content_hashes,
                    "extraction_quality": extraction_quality,
                    "source_filenames": source_filenames,
                }

        bank = []
        for entry in merged.values():
            entry.pop("_last_updated", None)
            entry.pop("_hashes", None)
            bank.append(entry)

        return {"policies": bank}
    except Exception as e:
        logger.error("Error getting policy bank", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


MAX_UPLOAD_SIZE = 10 * 1024 * 1024  # 10 MB
ALLOWED_EXTENSIONS = {".pdf", ".txt"}


@router.post("/infer-metadata")
async def infer_policy_metadata(file: UploadFile = File(...)):
    """
    Analyze an uploaded policy file to infer payer_name, medication_name,
    and effective_date.  For .txt files the first 3 000 characters are sent
    as text.  For PDFs the file is uploaded to Gemini so the model reads
    the document directly — no local PDF parsing needed.
    """
    from pathlib import Path
    import tempfile
    from backend.reasoning.prompt_loader import get_prompt_loader
    from backend.models.enums import TaskCategory

    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{ext}'.")

    content_bytes = await file.read()
    if len(content_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit.")

    try:
        prompt_loader = get_prompt_loader()

        if ext == ".txt":
            # Text file — extract first 3000 chars and use LLM gateway
            document_text = content_bytes.decode("utf-8", errors="replace")[:3000]
            prompt = prompt_loader.load(
                "policy_digitalization/infer_metadata.txt",
                {"document_text": document_text},
            )

            from backend.reasoning.llm_gateway import get_llm_gateway
            gateway = get_llm_gateway()
            llm_result = await gateway.generate(
                task_category=TaskCategory.DATA_EXTRACTION,
                prompt=prompt,
                temperature=0.0,
                response_format="json",
            )
            # The gateway returns parsed JSON fields at top level when
            # response_format="json", so read directly from the result dict.
            return {
                "payer_name": llm_result.get("payer_name"),
                "medication_name": llm_result.get("medication_name"),
                "effective_date": llm_result.get("effective_date"),
            }

        else:
            # PDF — upload to Gemini and let the model read the file directly
            from google import genai as genai_client
            from google.genai import types as genai_types

            settings = get_settings()
            client = genai_client.Client(api_key=settings.gemini_api_key)

            # Write bytes to a temp file so Gemini can read it
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(content_bytes)
                tmp_path = tmp.name

            try:
                uploaded_file = await client.aio.files.upload(file=tmp_path)
                prompt = prompt_loader.load(
                    "policy_digitalization/infer_metadata.txt",
                    {"document_text": "[PDF DOCUMENT ATTACHED — read the uploaded file]"},
                )
                response = await client.aio.models.generate_content(
                    model=settings.gemini_model,
                    contents=[uploaded_file, prompt],
                    config=genai_types.GenerateContentConfig(
                        temperature=0.0,
                        max_output_tokens=1024,
                    ),
                )
                raw = response.text
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            # Parse the raw text response from Gemini using robust JSON extractor
            from backend.reasoning.json_utils import extract_json_from_text
            parsed = extract_json_from_text(raw)

            return {
                "payer_name": parsed.get("payer_name"),
                "medication_name": parsed.get("medication_name"),
                "effective_date": parsed.get("effective_date"),
            }
    except Exception as e:
        logger.warning("Metadata inference failed, returning nulls", error=str(e))
        return {"payer_name": None, "medication_name": None, "effective_date": None}


@router.post("/upload")
async def upload_policy(
    file: UploadFile = File(...),
    payer_name: str = Form(...),
    medication_name: str = Form(...),
    amendment_notes: Optional[str] = Form(None),
    amendment_date: Optional[str] = Form(None),
):
    """
    Upload a policy file (PDF or TXT), trigger the digitalization pipeline,
    and store the result as a new version with amendment metadata.
    """
    from pathlib import Path
    from backend.policy_digitalization.pipeline import get_digitalization_pipeline
    from backend.policy_digitalization.policy_repository import get_policy_repository
    from backend.models.policy_schema import DigitizedPolicy

    payer_safe = _validate_name(payer_name, "Payer")
    med_safe = _validate_name(medication_name, "Medication")

    # Validate file extension
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{ext}'. Only .pdf and .txt are allowed.",
        )

    # Read and validate file size
    content_bytes = await file.read()
    if len(content_bytes) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File exceeds 10 MB limit.")

    # Hash check: skip pipeline if ANY stored policy has the same source file hash
    from sqlalchemy import select
    from backend.storage.database import get_db
    from backend.storage.models import PolicyCacheModel

    file_hash = hashlib.sha256(content_bytes).hexdigest()[:16]

    async with get_db() as session:
        # Query directly for the hash instead of loading all rows
        from sqlalchemy import cast, String
        stmt = (
            select(PolicyCacheModel)
            .where(PolicyCacheModel.parsed_criteria.isnot(None))
            .where(PolicyCacheModel.parsed_criteria["source_document_hash"].as_string() == file_hash)
            .order_by(PolicyCacheModel.cached_at.desc())
            .limit(1)
        )
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            logger.info(
                "Upload skipped — identical file already exists",
                payer=row.payer_name, medication=row.medication_name,
                version=row.policy_version,
            )
            return {
                "status": "unchanged",
                "version": row.policy_version,
                "cache_id": row.id,
                "extraction_quality": row.parsed_criteria.get("extraction_quality", "existing"),
                "criteria_count": len(row.parsed_criteria.get("atomic_criteria", {})),
                "indications_count": len(row.parsed_criteria.get("indications", [])),
                "message": f"File already digitized as {row.payer_name}/{row.medication_name} {row.policy_version} — pipeline skipped.",
            }

    repo = get_policy_repository()
    existing_versions = await repo.list_versions(payer_safe, med_safe)

    # Save file to data/policies/ — suppress file watcher to avoid duplicate pipeline run
    from backend.policy_digitalization.file_watcher import suppress_watcher, unsuppress_watcher

    policies_dir = Path(get_settings().policies_dir)
    policies_dir.mkdir(parents=True, exist_ok=True)
    dest_path = policies_dir / f"{payer_safe}_{med_safe}{ext}"
    suppress_watcher(str(dest_path))
    dest_path.write_bytes(content_bytes)

    version_label = f"v{len(existing_versions) + 1}"

    # Parse amendment date if provided
    parsed_amendment_date = None
    if amendment_date:
        try:
            parsed_amendment_date = datetime.fromisoformat(amendment_date).replace(
                tzinfo=timezone.utc
            ) if not amendment_date.endswith("Z") else datetime.fromisoformat(
                amendment_date.replace("Z", "+00:00")
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid amendment_date format. Use ISO 8601.")

    try:
        pipeline = get_digitalization_pipeline()

        if ext == ".txt":
            source = content_bytes.decode("utf-8")
            source_type = "text"
        else:
            source = str(dest_path)
            source_type = "pdf"

        result = await pipeline.digitalize_policy(
            source=source,
            source_type=source_type,
            payer_name=payer_safe,
            medication_name=med_safe,
            skip_store=True,  # Upload endpoint handles versioned storage
        )

        # Build DigitizedPolicy from pipeline result and store as versioned entry
        from backend.models.policy_schema import DigitizedPolicy
        policy = DigitizedPolicy(**result.policy) if result.policy else None
        if policy:
            cache_id = await repo.store_version(
                policy,
                version_label,
                source_filename=file.filename,
                upload_notes=amendment_notes,
                amendment_date=parsed_amendment_date,
            )
        else:
            cache_id = result.cache_id

        # Invalidate comparison caches for this payer/medication (L1 in-memory)
        for k in list(_diff_summary_cache):
            if k[0] == payer_safe and k[1] == med_safe:
                del _diff_summary_cache[k]
        for k in list(_impact_cache):
            if k[0] == payer_safe and k[1] == med_safe:
                del _impact_cache[k]

        # Invalidate L2 DB caches (diff + QA)
        try:
            from sqlalchemy import delete
            from backend.storage.models import PolicyDiffCacheModel, PolicyQACacheModel

            async with get_db() as session:
                await session.execute(
                    delete(PolicyDiffCacheModel)
                    .where(PolicyDiffCacheModel.payer_name == payer_safe)
                    .where(PolicyDiffCacheModel.medication_name == med_safe)
                )
                # Clear QA cache for matching filters (exact match on payer_filter)
                await session.execute(
                    delete(PolicyQACacheModel)
                    .where(
                        (PolicyQACacheModel.payer_filter == payer_safe)
                        | (PolicyQACacheModel.payer_filter.is_(None))
                    )
                )
            logger.info("DB caches invalidated for policy upload", payer=payer_safe, medication=med_safe)
        except Exception as e:
            logger.warning("Failed to invalidate DB caches", error=str(e))

        # Broadcast WebSocket notification
        try:
            from backend.api.routes.websocket import get_notification_manager

            notif_mgr = get_notification_manager()
            await notif_mgr.broadcast_notification({
                "type": "policy_update",
                "payer": payer_safe,
                "medication": med_safe,
                "version": version_label,
                "message": f"Policy {payer_safe}/{med_safe} updated to {version_label}",
            })
        except Exception:
            logger.debug("WebSocket notification skipped (no active connections)")

        return {
            "status": "success",
            "version": version_label,
            "cache_id": cache_id,
            "extraction_quality": result.extraction_quality,
            "criteria_count": result.criteria_count,
            "indications_count": result.indications_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        tb = traceback.format_exc()
        logger.error("Error uploading policy", error=str(e), traceback=tb)
        raise HTTPException(status_code=500, detail="Policy processing failed")
    finally:
        unsuppress_watcher(str(dest_path))


@router.get("/assistant/query")
async def assistant_query_get():
    """Placeholder to prevent path conflict — use POST."""
    raise HTTPException(status_code=405, detail="Use POST /policies/assistant/query")


class PolicyAssistantRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=2000)
    payer_filter: Optional[str] = None
    medication_filter: Optional[str] = None


@router.post("/assistant/query")
async def query_policy_assistant(request: PolicyAssistantRequest):
    """
    Query the Policy Assistant with a natural language question.

    Uses Claude to answer questions about digitized policies.
    """
    from backend.policy_digitalization.policy_assistant import get_policy_assistant

    try:
        assistant = get_policy_assistant()
        response = await assistant.query(
            question=request.question,
            payer_filter=request.payer_filter,
            medication_filter=request.medication_filter,
        )
        return response
    except Exception as e:
        logger.error("Error in policy assistant", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{payer}/{medication}/versions")
async def get_policy_versions(payer: str, medication: str):
    """
    Get version history for a specific policy.
    """
    from backend.policy_digitalization.policy_repository import get_policy_repository

    payer_safe = _validate_name(payer, "Payer")
    med_safe = _validate_name(medication, "Medication")

    try:
        repo = get_policy_repository()
        versions = await repo.list_versions(payer_safe, med_safe)
        return {
            "payer": payer_safe,
            "medication": med_safe,
            "versions": [
                {
                    "version": v.version,
                    "cached_at": v.cached_at,
                    "content_hash": v.content_hash,
                    "id": v.id,
                    "source_filename": v.source_filename,
                    "upload_notes": v.upload_notes,
                    "amendment_date": v.amendment_date,
                    "parent_version_id": v.parent_version_id,
                }
                for v in versions
            ],
        }
    except Exception as e:
        logger.error("Error getting policy versions", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


class DiffSummaryRequest(BaseModel):
    old_version: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9._-]+$")
    new_version: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9._-]+$")


@router.post("/{payer}/{medication}/diff-summary")
async def diff_policy_with_summary(payer: str, medication: str, request: DiffSummaryRequest):
    """
    Diff two policy versions and generate an LLM-powered change summary.

    Uses L1 (in-memory) + L2 (database) caching with content-hash validation.
    """
    from sqlalchemy import select
    from backend.policy_digitalization.policy_repository import get_policy_repository
    from backend.policy_digitalization.differ import PolicyDiffer
    from backend.reasoning.llm_gateway import get_llm_gateway
    from backend.reasoning.prompt_loader import get_prompt_loader
    from backend.models.enums import TaskCategory
    from backend.storage.database import get_db
    from backend.storage.models import PolicyDiffCacheModel

    payer_safe = _validate_name(payer, "Payer")
    med_safe = _validate_name(medication, "Medication")

    # L1: Return in-memory cached result if available
    cache_key = (payer_safe, med_safe, request.old_version, request.new_version)
    if cache_key in _diff_summary_cache:
        logger.info("Returning L1 cached diff-summary", payer=payer_safe, medication=med_safe)
        return _diff_summary_cache[cache_key]

    try:
        repo = get_policy_repository()
        old_policy = await repo.load_version(payer_safe, med_safe, request.old_version)
        new_policy = await repo.load_version(payer_safe, med_safe, request.new_version)

        if not old_policy:
            raise HTTPException(status_code=404, detail=f"Version {request.old_version} not found")
        if not new_policy:
            raise HTTPException(status_code=404, detail=f"Version {request.new_version} not found")

        # Compute content hashes for cache validation
        old_hash = hashlib.sha256(old_policy.model_dump_json().encode()).hexdigest()
        new_hash = hashlib.sha256(new_policy.model_dump_json().encode()).hexdigest()

        # L2: Check database cache
        async with get_db() as session:
            stmt = (
                select(PolicyDiffCacheModel)
                .where(PolicyDiffCacheModel.payer_name == payer_safe)
                .where(PolicyDiffCacheModel.medication_name == med_safe)
                .where(PolicyDiffCacheModel.old_version == request.old_version)
                .where(PolicyDiffCacheModel.new_version == request.new_version)
                .where(PolicyDiffCacheModel.old_content_hash == old_hash)
                .where(PolicyDiffCacheModel.new_content_hash == new_hash)
            )
            db_result = await session.execute(stmt)
            cached_row = db_result.scalar_one_or_none()

        if cached_row:
            logger.info("Returning L2 DB cached diff-summary", payer=payer_safe, medication=med_safe)
            result = {"diff": cached_row.diff_data, "summary": cached_row.summary_data}
            _bounded_cache_set(_diff_summary_cache, cache_key, result)  # Promote to L1
            return result

        # Cache miss — compute diff + LLM summary
        differ = PolicyDiffer()
        diff_result = await differ.diff(old_policy, new_policy)
        diff_dict = diff_result.model_dump()

        prompt_loader = get_prompt_loader()
        prompt = prompt_loader.load(
            "policy_digitalization/change_summary.txt",
            {"diff_data": json.dumps(diff_dict, default=str, indent=2)},
        )

        gateway = get_llm_gateway()
        llm_result = await gateway.generate(
            task_category=TaskCategory.SUMMARY_GENERATION,
            prompt=prompt,
            temperature=0.2,
            response_format="json",
        )

        summary = {}
        try:
            raw = llm_result.get("response")
            if raw is None:
                summary = {k: v for k, v in llm_result.items() if k not in ("provider", "task_category")}
            elif isinstance(raw, str):
                summary = json.loads(raw)
            else:
                summary = raw
        except (json.JSONDecodeError, TypeError):
            summary = {"executive_summary": str(llm_result.get("response", "Unable to generate summary"))}

        def _remap_field_changes(changes_list):
            for change in changes_list:
                if "field_changes" in change:
                    change["field_changes"] = [
                        {"field": fc["field_name"], "old": fc["old"], "new": fc["new"]}
                        for fc in change["field_changes"]
                    ]
            return changes_list

        diff_payload = {
            "summary": {
                "total_criteria_old": diff_dict["summary"]["total_criteria_old"],
                "total_criteria_new": diff_dict["summary"]["total_criteria_new"],
                "added": diff_dict["summary"]["added_count"],
                "removed": diff_dict["summary"]["removed_count"],
                "modified": diff_dict["summary"]["modified_count"],
                "unchanged": diff_dict["summary"]["unchanged_count"],
                "breaking_changes": diff_dict["summary"]["breaking_changes"],
                "material_changes": diff_dict["summary"]["material_changes"],
                "severity_assessment": diff_dict["summary"]["severity_assessment"],
            },
            "changes": {
                "criteria": _remap_field_changes(diff_dict["criterion_changes"]),
                "indications": diff_dict["indication_changes"],
                "step_therapy": _remap_field_changes(diff_dict["step_therapy_changes"]),
                "exclusions": _remap_field_changes(diff_dict["exclusion_changes"]),
            },
        }

        result = {"diff": diff_payload, "summary": summary}

        # Store in L1 (in-memory)
        _bounded_cache_set(_diff_summary_cache, cache_key, result)

        # Store in L2 (database) — upsert
        async with get_db() as session:
            # Delete any stale row for these versions (content may have changed)
            stale_stmt = (
                select(PolicyDiffCacheModel)
                .where(PolicyDiffCacheModel.payer_name == payer_safe)
                .where(PolicyDiffCacheModel.medication_name == med_safe)
                .where(PolicyDiffCacheModel.old_version == request.old_version)
                .where(PolicyDiffCacheModel.new_version == request.new_version)
            )
            stale_result = await session.execute(stale_stmt)
            stale_row = stale_result.scalar_one_or_none()
            if stale_row:
                await session.delete(stale_row)

            new_cache_row = PolicyDiffCacheModel(
                id=str(uuid.uuid4()),
                payer_name=payer_safe,
                medication_name=med_safe,
                old_version=request.old_version,
                new_version=request.new_version,
                old_content_hash=old_hash,
                new_content_hash=new_hash,
                diff_data=diff_payload,
                summary_data=summary,
            )
            session.add(new_cache_row)
        logger.info("Diff-summary stored in DB cache", payer=payer_safe, medication=med_safe)

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error generating diff summary", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{payer}/{medication}")
async def get_policy_content(payer: str, medication: str):
    """
    Get the content of a specific policy document.

    Args:
        payer: Payer name (e.g., cigna, uhc)
        medication: Medication name (e.g., infliximab)

    Returns:
        Policy document content
    """
    from pathlib import Path

    # Validate inputs
    payer_safe = _validate_name(payer, "Payer")
    medication_safe = _validate_name(medication, "Medication")

    policies_dir = Path(get_settings().policies_dir)
    policy_file = policies_dir / f"{payer_safe}_{medication_safe}.txt"

    if not policy_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Policy not found for {payer}/{medication}"
        )

    try:
        with open(policy_file, "r", encoding="utf-8") as f:
            content = f.read()
    except IOError as e:
        logger.error(f"Error reading policy file: {e}")
        raise HTTPException(status_code=500, detail="Error reading policy file")

    return {
        "payer": payer,
        "medication": medication,
        "content": content,
        "file": policy_file.name
    }


@router.get("/criteria/{payer}/{medication}", deprecated=True)
async def get_policy_criteria(payer: str, medication: str):
    """Deprecated — use digitized policy criteria from coverage assessment instead."""
    raise HTTPException(
        status_code=410,
        detail="This endpoint is deprecated. Use GET /digitized/{payer}/{medication} for policy criteria, "
               "or POST /cases to run LLM-based coverage assessment."
    )


class DigitalizeRequest(BaseModel):
    payer_name: str
    medication_name: str
    policy_text: Optional[str] = Field(None, max_length=500_000)
    skip_validation: bool = False


class EvaluateRequest(BaseModel):
    patient_info: dict

    @field_validator("patient_info")
    @classmethod
    def validate_patient_info(cls, v: dict) -> dict:
        if not v:
            raise ValueError("patient_info must not be empty")
        if len(json.dumps(v, default=str)) > 100_000:
            raise ValueError("patient_info exceeds maximum size")
        return v


class DiffRequest(BaseModel):
    old_version: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9._-]+$")
    new_version: str = Field(..., min_length=1, max_length=50, pattern=r"^[a-zA-Z0-9._-]+$")


@router.post("/digitalize")
async def digitalize_policy(request: DigitalizeRequest):
    """
    Trigger policy digitalization pipeline.

    Runs: Gemini extraction -> Claude validation -> reference validation.
    """
    from backend.policy_digitalization.pipeline import get_digitalization_pipeline

    payer_safe = _validate_name(request.payer_name, "Payer")
    med_safe = _validate_name(request.medication_name, "Medication")

    try:
        pipeline = get_digitalization_pipeline()

        if request.policy_text:
            result = await pipeline.digitalize_policy(
                source=request.policy_text,
                source_type="text",
                skip_validation=request.skip_validation,
                payer_name=payer_safe,
                medication_name=med_safe,
            )
        else:
            # Load from file
            from pathlib import Path
            policy_file = Path(get_settings().policies_dir) / f"{payer_safe}_{med_safe}.txt"
            if not policy_file.exists():
                raise HTTPException(status_code=404, detail=f"Policy text not found for {payer_safe}/{med_safe}")
            policy_text = policy_file.read_text(encoding="utf-8")
            result = await pipeline.digitalize_policy(
                source=policy_text,
                source_type="text",
                skip_validation=request.skip_validation,
                payer_name=payer_safe,
                medication_name=med_safe,
            )

        return {
            "status": "success",
            "policy_id": result.policy.get("policy_id") if result.policy else None,
            "criteria_count": result.criteria_count,
            "indications_count": result.indications_count,
            "extraction_quality": result.extraction_quality,
            "validation_status": result.validation_status,
            "quality_score": result.quality_score,
            "passes_completed": result.passes_completed,
            "corrections_count": result.corrections_count,
            "stored": result.stored,
            "cache_id": result.cache_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error digitalizing policy", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{payer}/{medication}/evaluate")
async def evaluate_patient_against_policy(payer: str, medication: str, request: EvaluateRequest):
    """
    Deprecated: Deterministic evaluator has been replaced by LLM-first evaluation.

    Use the case workflow (POST /api/v1/cases/{id}/run-stage with stage=policy_analysis)
    to get per-criterion assessments from the LLM instead.
    """
    raise HTTPException(
        status_code=410,
        detail="Deterministic evaluation endpoint has been removed. "
               "Use the case workflow policy_analysis stage for LLM-based criterion evaluation."
    )


@router.get("/{payer}/{medication}/provenance")
async def get_policy_provenance(payer: str, medication: str):
    """
    Get extraction quality and provenance report for a digitized policy.
    """
    from backend.policy_digitalization.pipeline import get_digitalization_pipeline

    payer_safe = _validate_name(payer, "Payer")
    med_safe = _validate_name(medication, "Medication")

    try:
        pipeline = get_digitalization_pipeline()
        policy = await pipeline.get_or_digitalize(payer_safe, med_safe)

        return {
            "policy_id": policy.policy_id,
            "payer_name": policy.payer_name,
            "medication_name": policy.medication_name,
            "extraction_quality": policy.extraction_quality,
            "extraction_pipeline_version": policy.extraction_pipeline_version,
            "validation_model": policy.validation_model,
            "total_criteria": len(policy.atomic_criteria),
            "provenances": {
                cid: prov.model_dump() for cid, prov in policy.provenances.items()
            },
        }
    except (FileNotFoundError, PolicyNotFoundError):
        raise HTTPException(status_code=404, detail=f"Policy not found for {payer_safe}/{med_safe}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting provenance", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{payer}/{medication}/diff")
async def diff_policy_versions(payer: str, medication: str, request: DiffRequest):
    """
    Diff two versions of a digitized policy.
    """
    from backend.policy_digitalization.policy_repository import get_policy_repository
    from backend.policy_digitalization.differ import PolicyDiffer

    payer_safe = _validate_name(payer, "Payer")
    med_safe = _validate_name(medication, "Medication")

    try:
        repo = get_policy_repository()
        old_policy = await repo.load_version(payer_safe, med_safe, request.old_version)
        new_policy = await repo.load_version(payer_safe, med_safe, request.new_version)

        if not old_policy:
            raise HTTPException(status_code=404, detail=f"Version {request.old_version} not found")
        if not new_policy:
            raise HTTPException(status_code=404, detail=f"Version {request.new_version} not found")

        differ = PolicyDiffer()
        result = await differ.diff(old_policy, new_policy)
        return result.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error diffing policies", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


class ImpactRequest(BaseModel):
    old_version: Optional[str] = Field(None, max_length=50, pattern=r"^[a-zA-Z0-9._-]+$")
    new_version: Optional[str] = Field(None, max_length=50, pattern=r"^[a-zA-Z0-9._-]+$")


@router.post("/{payer}/{medication}/impact")
async def analyze_policy_impact(payer: str, medication: str, request: ImpactRequest):
    """
    Analyze impact of policy changes on active cases.

    If old_version/new_version not provided, auto-detects the latest two versions.
    """
    from backend.policy_digitalization.policy_repository import get_policy_repository
    from backend.policy_digitalization.differ import PolicyDiffer
    from backend.policy_digitalization.impact_analyzer import PolicyImpactAnalyzer

    payer_safe = _validate_name(payer, "Payer")
    med_safe = _validate_name(medication, "Medication")

    try:
        repo = get_policy_repository()

        old_ver = request.old_version
        new_ver = request.new_version

        # Auto-detect versions if not provided
        if not old_ver or not new_ver:
            versions = await repo.list_versions(payer_safe, med_safe)
            if len(versions) < 2:
                raise HTTPException(
                    status_code=400,
                    detail="Need at least 2 versions for impact analysis. Provide old_version and new_version explicitly.",
                )
            new_ver = new_ver or versions[0].version
            old_ver = old_ver or versions[1].version

        # Return cached result if available
        cache_key = (payer_safe, med_safe, old_ver, new_ver)
        if cache_key in _impact_cache:
            logger.info("Returning cached impact analysis", payer=payer_safe, medication=med_safe)
            return _impact_cache[cache_key]

        old_policy = await repo.load_version(payer_safe, med_safe, old_ver)
        new_policy = await repo.load_version(payer_safe, med_safe, new_ver)

        if not old_policy:
            raise HTTPException(status_code=404, detail=f"Version {old_ver} not found")
        if not new_policy:
            raise HTTPException(status_code=404, detail=f"Version {new_ver} not found")

        # Diff
        differ = PolicyDiffer()
        diff = await differ.diff(old_policy, new_policy)

        # Load patient JSON files from data/patients/
        case_states = []
        import json as _json
        from pathlib import Path as _Path
        patients_dir = _Path(get_settings().patients_dir)
        if patients_dir.exists():
            for pf in patients_dir.glob("*.json"):
                try:
                    with open(pf, "r", encoding="utf-8") as f:
                        pdata = _json.load(f)
                    # Match by medication (brand_name or medication_name) and payer
                    med_req = pdata.get("medication_request", {})
                    brand = (med_req.get("brand_name") or "").lower()
                    generic = (med_req.get("medication_name") or "").lower()
                    pt_payer = (pdata.get("insurance", {}).get("primary", {}).get("payer_name") or "").lower()
                    if (med_safe in (brand, generic) or brand == med_safe or generic == med_safe) and pt_payer == payer_safe:
                        case_states.append({"patient_data": pdata, "case_id": pdata.get("patient_id", pf.stem)})
                except Exception:
                    continue

        # Analyze impact
        analyzer = PolicyImpactAnalyzer()
        report = await analyzer.analyze_impact(diff, old_policy, new_policy, case_states)
        result = report.model_dump()

        _bounded_cache_set(_impact_cache, cache_key, result)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error analyzing impact", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{payer}/{medication}/digitized")
async def get_digitized_policy(payer: str, medication: str):
    """
    Get a digitized, structured representation of a policy.

    Returns the 3-pass pipeline output from policy_cache (preferred),
    or triggers digitalization if not cached yet.
    """
    from backend.policy_digitalization.pipeline import get_digitalization_pipeline

    payer_safe = _validate_name(payer, "Payer")
    medication_safe = _validate_name(medication, "Medication")

    try:
        pipeline = get_digitalization_pipeline()
        policy = await pipeline.get_or_digitalize(payer_safe, medication_safe)
        return policy.model_dump(mode="json")
    except (FileNotFoundError, PolicyNotFoundError):
        raise HTTPException(status_code=404, detail=f"Policy not found for {payer_safe}/{medication_safe}")
    except Exception as e:
        logger.error("Error getting digitized policy", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{payer}/{medication}/pdf")
async def get_policy_pdf(payer: str, medication: str):
    """Serve the original PDF file for a policy."""
    from pathlib import Path

    payer_safe = _validate_name(payer, "Payer")
    medication_safe = _validate_name(medication, "Medication")

    policies_dir = Path(get_settings().policies_dir)
    pdf_path = policies_dir / f"{payer_safe}_{medication_safe}.pdf"

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF not found for {payer_safe}/{medication_safe}")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=f"{payer_safe}_{medication_safe}.pdf",
        headers={
            "Content-Disposition": "inline",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=3600",
        },
    )



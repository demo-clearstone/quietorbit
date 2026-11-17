from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.plan_profile import PlanProfile
from models.review import RuleDecision, ValidationItem
from config.settings import LOG_DIR

_AUDIT_VERSION = 1
_SSN = re.compile(r"\b(?:\d{3}-\d{2}-\d{4}|\d{3}-[Xx*]{2}-[\dXx*]{4}|[Xx*]{3}-[Xx*]{2}-[\dXx*]{4})\b")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE = re.compile(r"(?<!\d)(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)")
_WINDOWS_PATH = re.compile(r"\b[A-Z]:\\[^\s]+", re.I)
_POSIX_USER_PATH = re.compile(r"/Users/[^\s]+")
_FILENAME_TOKEN = re.compile(r"[^A-Za-z0-9-]+")


def audit_log_path(profile: PlanProfile, job_id: str, created_at: datetime | None = None) -> Path:
    """Build logs/plantype_plannumber_UTCtimestamp_jobid.json."""
    timestamp = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    plan_type = _FILENAME_TOKEN.sub("-", (profile.plan_type or "unknown").strip()).strip("-").lower() or "unknown"
    plan_number = _FILENAME_TOKEN.sub("-", (profile.plan_number or "UNKNOWN").strip()).strip("-") or "UNKNOWN"
    safe_job = _FILENAME_TOKEN.sub("", job_id) or "job"
    return LOG_DIR / f"{plan_type}_{plan_number}_{timestamp}_{safe_job}.json"


def _safe_text(value: str) -> str:
    text = _SSN.sub("[REDACTED-SSN]", value)
    text = _EMAIL.sub("[REDACTED-EMAIL]", text)
    text = _PHONE.sub("[REDACTED-PHONE]", text)
    text = _WINDOWS_PATH.sub("[LOCAL-PATH]", text)
    return _POSIX_USER_PATH.sub("[LOCAL-PATH]", text)


def _file_record(name: str, data: bytes | str) -> dict[str, Any]:
    content = data.encode("utf-8") if isinstance(data, str) else data
    return {
        "name": _safe_text(Path(name).name),
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def write_audit_log(
    path: Path,
    *,
    job_id: str,
    filename: str,
    source_files: list[tuple[str, bytes | str]],
    options: dict[str, Any],
    profile: PlanProfile,
    decisions: list[RuleDecision],
    validations: list[ValidationItem],
    warnings: list[str],
    elapsed_seconds: float,
    stop_reasons: list[str] | None = None,
) -> Path:
    """Write a shareable JSON audit record without storing PDF text or personal data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    audit = {
        "schema_version": _AUDIT_VERSION,
        "job_id": job_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "stopped" if stop_reasons else "completed",
        "output_file": _safe_text(Path(filename).name),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "source_files": [_file_record(name, data) for name, data in source_files],
        "options": {
            key: value
            for key, value in options.items()
            if key in {"auto_order", "rewrite_sources", "check_assembly_stops", "validation_checks"}
        },
        "plan": {
            "number": profile.plan_number,
            "type": profile.plan_type,
            "year_start": profile.plan_year_start,
            "year_end": profile.plan_year_end,
        },
        "keep_remove_decisions": [
            {
                "rule_id": item.rule_id,
                "action": item.action,
                "reason": _safe_text(item.reason),
                "skipped": item.skipped,
            }
            for item in decisions
        ],
        "validations": [
            {
                "code": item.code,
                "label": item.label,
                "passed": item.passed,
                "detail": _safe_text(item.detail),
            }
            for item in validations
        ],
        "stop_reasons": [_safe_text(reason) for reason in (stop_reasons or [])],
        "warnings": [_safe_text(warning) for warning in warnings],
        "privacy": {
            "pdf_content_included": False,
            "source_file_hashes_included": True,
            "sensitive_text_redacted": True,
            "redactions": ["SSN", "email", "phone", "local paths"],
        },
    }
    path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path

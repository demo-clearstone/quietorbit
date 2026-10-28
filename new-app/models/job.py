from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from models.plan_profile import PlanProfile
from models.review import RuleDecision, ReviewResult


class HighlightMark(BaseModel):
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    label: str = ""


class JobResult(BaseModel):
    job_id: str
    filename: str
    pdf_path: str
    created_at: datetime
    plan_profile: PlanProfile
    review: ReviewResult | None = None
    rule_decisions: list[RuleDecision] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_files: list[str] = Field(default_factory=list)
    highlights: list[HighlightMark] = Field(default_factory=list)
    download_url: str = ""
    preview_url: str = ""
    email_subject: str = ""
    email_path: str = ""
    log_path: str = ""
    audit_log_path: str = ""
    audit_log_url: str = ""
    profile_debug_path: str = ""
    saved_copy_path: str = ""
    elapsed_seconds: float | None = None

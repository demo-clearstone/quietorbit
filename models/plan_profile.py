from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DetectedSection(BaseModel):
    name: str
    page: int
    matched_alias: str


class PlanProfile(BaseModel):
    """Single object used by every business rule (SRD §6)."""

    plan_number: str | None = None
    plan_name: str | None = None
    company_name: str | None = None
    company_address: str | None = None
    plan_type: str | None = None
    plan_year_start: str | None = None
    plan_year_end: str | None = None
    beginning_plan_year: str | None = None
    testing_method: str | None = None
    top_heavy_percent: float | None = None
    top_heavy: bool | None = None
    adp_failed: bool | None = None
    acp_failed: bool | None = None
    testing_failed: bool | None = None
    returns_required: bool | None = None
    returns_already_processed: bool | None = None
    adp_reclassified: bool | None = None
    hce_current: bool | None = None
    hce_future: bool | None = None
    fail_402g: bool | None = None
    fail_402g_after_deadline: bool | None = None
    fail_415: bool | None = None
    variance_report: bool | None = None
    true_up: bool | None = None
    annual_allocation: bool | None = None
    contributions_required: bool | None = None
    partially_vested: bool | None = None
    safe_harbor: bool | None = None
    catchup_disallowed: bool | None = None
    special_catchup_disallowed: bool | None = None
    non_governmental: bool | None = None
    forfeitures_reallocated: bool | None = None
    no_forfeitures: bool | None = None
    midyear: bool | None = None
    midyear_failed: bool | None = None
    hce_max_deferral: float | None = None
    per_payroll_match: bool | None = None
    rework: bool | None = None
    rush: bool | None = None
    keep_excess_summary: bool | None = None
    after_12_months: bool | None = None
    adp_qnec: float | None = None
    acp_qnec: float | None = None
    deferral_refund: float | None = None
    match_refund: float | None = None
    total_qnec: float | None = None
    has_action_required: bool | None = None
    action_required_items: list[str] = Field(default_factory=list)
    detected_sections: list[DetectedSection] = Field(default_factory=list)
    mentions_moa: bool | None = None
    moa_logo_found: bool | None = None
    moa_stamp_detail: str = ""
    extraction_warnings: list[str] = Field(default_factory=list)
    assembly_notes: str = ""
    source_page_count: int = 0
    extra: dict[str, Any] = Field(default_factory=dict)

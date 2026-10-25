from __future__ import annotations

from datetime import datetime, timedelta

from models.plan_profile import PlanProfile
from services.pdf_extractor import beginning_plan_year
from services.plan_config import is_457_plan, package_flags


def finalize_profile(profile: PlanProfile) -> PlanProfile:
    """Normalize derived fields after extraction.

    Purpose:
        Normalize derived fields after extraction.

    Args:
        profile: Plan profile collected from the PDF, Excel, and summary.

    Returns:
        PlanProfile.

    Raises:
        None.

    Example:
        finalize_profile(profile) returns PlanProfile.

    Side effects:
        None. This function only reads data and returns a value.
    """
    field_sources = profile.extra.setdefault("field_sources", {})
    if profile.plan_year_start is None and profile.plan_year_end:
        try:
            end = datetime.strptime(profile.plan_year_end, "%m/%d/%Y")
            next_day = end + timedelta(days=1)
            start = next_day.replace(year=next_day.year - 1)
            profile.plan_year_start = start.strftime("%m/%d/%Y")
            field_sources["plan_year_start"] = "Derived from plan_year_end"
        except ValueError:
            pass
    if profile.beginning_plan_year is None and profile.plan_year_start:
        profile.beginning_plan_year = beginning_plan_year(profile.plan_year_start)
        field_sources["beginning_plan_year"] = "Derived from plan_year_start"

    if profile.top_heavy is None and profile.top_heavy_percent is not None:
        profile.top_heavy = profile.top_heavy_percent > 60
        field_sources["top_heavy"] = "Derived from top_heavy_percent"

    flags = package_flags(profile.plan_type)
    if flags.get("ignore_adp_results"):
        profile.adp_failed = False
        profile.adp_qnec = None
        field_sources["adp_failed"] = "403(b) configuration: ADP not applicable"

    known = [profile.adp_failed, profile.acp_failed, profile.fail_402g, profile.fail_415]
    if any(v is True for v in known):
        profile.testing_failed = True
        field_sources["testing_failed"] = "Derived from test failure fields"
    elif all(v is False for v in known):
        profile.testing_failed = False
        field_sources["testing_failed"] = "Derived from test failure fields"
    if profile.testing_failed is False:
        profile.returns_required = False
        field_sources["returns_required"] = "Derived: all applicable tests passed"
    if (
        profile.testing_failed is False
        and profile.variance_report is not True
        and profile.true_up is not True
        and profile.extra.get("contributions_explicit") is not True
    ):
        profile.contributions_required = False
        field_sources["contributions_required"] = "Derived: no failure, variance, true-up, or explicit contribution requirement"
    elif profile.contributions_required is None and (profile.true_up is True or profile.variance_report is True):
        profile.contributions_required = True
        field_sources["contributions_required"] = "Derived from true-up or variance client copy"
    elif profile.contributions_required is None:
        profile.contributions_required = False
        field_sources["contributions_required"] = "Derived: no true-up, contribution note, or variance client copy"

    if profile.total_qnec is None:
        parts = [v for v in (profile.adp_qnec, profile.acp_qnec) if v is not None]
        if parts:
            profile.total_qnec = round(sum(parts), 2)

    if profile.returns_already_processed or profile.adp_reclassified:
        profile.returns_required = False

    if is_457_plan(profile.plan_type):
        if profile.non_governmental:
            profile.catchup_disallowed = True
        if profile.forfeitures_reallocated is None:
            profile.forfeitures_reallocated = False
        if profile.no_forfeitures is None:
            profile.no_forfeitures = False

    if flags.get("ignore_adp_results"):
        profile.total_qnec = profile.acp_qnec

    outstanding = profile.returns_required is True and profile.adp_reclassified is not True
    compliance_failure = profile.fail_415 is True or (
        profile.fail_402g is True and profile.fail_402g_after_deadline is not True
    )
    action_items: list[str] = []
    if outstanding and compliance_failure:
        action_items.append("Compliance returns required")
    if outstanding and (profile.adp_failed or profile.acp_failed):
        label = "ACP returns required" if flags.get("ignore_adp_results") else "ADP/ACP returns required"
        action_items.append(label)
    if profile.top_heavy:
        action_items.append("Top heavy")
    if profile.variance_report:
        action_items.append("Variance report")
    if profile.contributions_required:
        action_items.append("Contributions")
    if profile.after_12_months and (profile.adp_failed or profile.acp_failed):
        action_items.append("After 12 months")
    profile.keep_excess_summary = bool(
        profile.fail_402g
        or profile.fail_415
        or (profile.partially_vested and (profile.adp_failed or profile.acp_failed))
    )
    field_sources["keep_excess_summary"] = "Derived from non-ACP failures or partial vesting"
    profile.action_required_items = action_items
    if action_items:
        profile.has_action_required = True
        field_sources["has_action_required"] = "Derived from action_required_items"
    elif any(
        v is False
        for v in (
            profile.adp_failed,
            profile.acp_failed,
            profile.fail_402g,
            profile.fail_415,
            profile.top_heavy,
            profile.returns_required,
        )
    ):
        profile.has_action_required = False
        field_sources["has_action_required"] = "Derived from known no-action conditions"
    return profile

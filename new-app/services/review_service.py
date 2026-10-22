from __future__ import annotations

from models.plan_profile import PlanProfile
from models.review import ReviewResult, ValidationItem
from services.action_required import inspect_compliance_failure_wording


def validate(profile: PlanProfile, doc=None) -> ReviewResult:
    items = [
        _present("cover_plan_number", "Plan Number", profile.plan_number),
        _present("cover_plan_name", "Plan Name", profile.plan_name),
        _present("cover_company", "Company Name", profile.company_name),
        _present("cover_address", "Company Address", profile.company_address),
        _present("cover_plan_year_end", "Plan Year End", profile.plan_year_end),
        ValidationItem(
            code="cover_moa",
            label="MOA cover stamp",
            passed=bool(profile.moa_logo_found),
            detail=profile.moa_stamp_detail
            or (
                "Mutual of America found in text"
                if profile.mentions_moa
                else "Confirm Mutual of America stamp on the cover letter (TEST23 §A)"
            ),
        ),
        _present("top_heavy", "Top Heavy %", profile.top_heavy_percent),
    ]
    if doc is not None:
        wording = inspect_compliance_failure_wording(doc)
        items.append(
            ValidationItem(
                code="action_compliance_wording",
                label="Compliance Test Failure wording",
                passed=bool(wording["wording_ok"] or not wording["found"]),
                detail=str(wording["detail"]),
            )
        )
    return ReviewResult(items=items, ssn_found=False, ssn_pages=[])


def _present(code: str, label: str, value: object) -> ValidationItem:
    ok = value is not None and value != ""
    return ValidationItem(
        code=code,
        label=label,
        passed=ok,
        detail=str(value) if ok else "Not found — confirm on source PDF",
    )


def _order_item(profile: PlanProfile, doc=None) -> ValidationItem:
    if doc is not None:
        from services.package_polish import _assembly_order_check

        result = _assembly_order_check(doc, profile)
        result.label = "Package order (TEST23)"
        return result
    return ValidationItem(
        code="package_order",
        label="Package order (TEST23)",
        passed=False,
        detail="Could not inspect the assembled PDF pages.",
    )

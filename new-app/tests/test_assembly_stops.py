from __future__ import annotations

import fitz

from models.plan_profile import PlanProfile
from services import assembly_stops


def _doc(*pages: str) -> fitz.Document:
    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        page.insert_textbox(fitz.Rect(30, 30, 580, 760), text, fontsize=10)
    return doc


def test_address_requires_street_city_state_and_zip() -> None:
    assert assembly_stops._address_reason("100 Main Street\nBoston, MA 02110") is None
    assert assembly_stops._address_reason("Boston, MA 02110")
    assert assembly_stops._address_reason("100 Main Street")
    assert assembly_stops._address_reason(None)


def test_unresolved_summary_wording_stops_but_resolved_wording_does_not() -> None:
    unresolved = _doc("Compliance Testing Summary of Results\nPlan is/is not Top Heavy\nADP Pass/Fail")
    resolved = _doc("Compliance Testing Summary of Results\nPlan is not Top Heavy\nADP Pass")
    assert assembly_stops._content_reasons(unresolved)
    assert assembly_stops._content_reasons(resolved) == []


def test_full_and_masked_ssns_stop() -> None:
    for ssn in ("123-45-6789", "123-XX-6789", "XXX-XX-6789"):
        doc = _doc(f"Census Report\nSSN {ssn}")
        assert any("Social Security number" in reason for reason in assembly_stops._content_reasons(doc))


def test_plan_and_employer_name_mismatches_stop() -> None:
    doc = _doc(
        "Plan Name: Example 401(k) Plan\nCompany Name: Example Inc.",
        "Plan Name: Other 401(k) Plan\nCompany Name: Different Inc.",
    )
    profile = PlanProfile(plan_name="Example 401(k) Plan", company_name="Example Inc.")
    reasons = assembly_stops._name_reasons(doc, profile, "Other 401(k) Plan", "Example 401(k) Plan")
    assert any("plan name" in reason.lower() for reason in reasons)
    assert assembly_stops._company_report_reasons(doc, "Example Inc.")


def test_plan_number_mismatch_stops() -> None:
    doc = _doc("Plan Number: 100001", "Plan Number: 100002")
    assert assembly_stops._plan_number_reasons(doc, "100001")


def test_missing_identity_and_year_end_are_stop_conditions() -> None:
    doc = _doc("Cover Letter\nMUTUAL OF AMERICA\nWe are pleased to provide your valuation package")
    profile = PlanProfile(company_address="100 Main Street, Boston, MA 02110")
    reasons = assembly_stops._package_reasons(
        doc,
        profile,
        ["Valuation Pkg.pdf"],
        None,
        None,
        cover_company="Example Inc.",
        cover_address=profile.company_address,
    )
    assert any("plan name could not be verified" in reason.lower() for reason in reasons)
    assert any("plan number could not be verified" in reason.lower() for reason in reasons)
    assert any("plan year end could not be verified" in reason.lower() for reason in reasons)


def test_report_identity_check_stops_wrong_unlabeled_report_name() -> None:
    from services.package_polish import _identity_checks

    doc = _doc(
        "Example 401(k) Plan\nPlan Number: 100001",
        "Wrong 401(k) Plan\nPlan Number: 100001\n415 Limit Test",
    )
    profile = PlanProfile(plan_number="100001", plan_name="Example 401(k) Plan")
    item = _identity_checks(doc, profile)[0]
    assert not item.passed
    assert "page 2" in item.detail


def test_page_year_end_exceptions_are_limited_to_future_hce_and_402g() -> None:
    profile = PlanProfile(plan_year_end="06/30/2026")
    normal = _doc("Census Report\nPlan Year End: 12/31/2025")
    future = _doc("Future HCE Report\nPlan Year End: 06/30/2027")
    off_calendar_402g = _doc("402(g) Test\nPlan Year End: 12/31/2025")
    assert assembly_stops._pye_reasons(normal, profile)
    assert assembly_stops._pye_reasons(future, profile) == []
    assert assembly_stops._pye_reasons(off_calendar_402g, profile) == []


def test_month_name_pye_and_plan_year_range_are_checked() -> None:
    profile = PlanProfile(plan_year_end="06/30/2026")
    wrong_label = _doc("Census Report\nPlan Year End: December 31, 2025")
    wrong_range = _doc("Census Report\nJanuary 1, 2025 - December 31, 2025")
    correct_range = _doc("Census Report\nJuly 1, 2025 - June 30, 2026")
    assert assembly_stops._pye_reasons(wrong_label, profile)
    assert assembly_stops._pye_reasons(wrong_range, profile)
    assert assembly_stops._pye_reasons(correct_range, profile) == []


def test_required_report_detection_does_not_accept_failure_letter_as_test_report() -> None:
    profile = PlanProfile(plan_type="401k", safe_harbor=False)
    doc = _doc("Cover letter\nMutual of America\nWe are pleased to provide your valuation package")
    files = [
        "Valuation Pkg.pdf",
        "ResultSumm.pdf",
        "402 Failure Letter.pdf",
        "415 Failure Information.pdf",
        "ADP Failure Letter.pdf",
        "410.pdf",
        "HCEKey.pdf",
        "FYHCE.pdf",
        "TH.pdf",
        "Census.pdf",
        "Contri.pdf",
    ]
    missing = assembly_stops._missing_report_reasons(doc, profile, files)
    assert missing
    assert "402(g) Test Report" in missing[0]
    assert "415 Test Report" in missing[0]
    assert "ADP/ACP Test Report" in missing[0]


def test_safe_harbor_and_403b_report_exceptions() -> None:
    safe_harbor = PlanProfile(plan_type="401k", safe_harbor=True)
    doc = _doc("Cover letter\nMutual of America\nWe are pleased to provide your valuation package")
    files = [
        "Valuation Pkg.pdf", "ResultSumm.pdf", "402.pdf", "415.pdf", "410.pdf",
        "HCEKey.pdf", "FYHCE.pdf", "TH.pdf", "Census.pdf", "Contri.pdf",
    ]
    assert assembly_stops._missing_report_reasons(doc, safe_harbor, files) == []
    profile_403b = PlanProfile(plan_type="403b", safe_harbor=False)
    assert assembly_stops._missing_report_reasons(doc, profile_403b, files) == [
        "These required reports are missing: ADP/ACP Test Report. Assembly stopped."
    ]


def test_valuation_package_detection_uses_pdf_cover_when_filename_is_generic() -> None:
    doc = _doc("MUTUAL OF AMERICA\nWe are pleased to provide your valuation package")
    assert assembly_stops._is_valuation_package(["package.pdf"], doc)

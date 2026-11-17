from __future__ import annotations

import fitz

from models.plan_profile import PlanProfile
from services import assembly_stops, file_order, package_polish, pdf_assembler, pdf_extractor


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


def test_year_tagged_future_hce_filename_counts_when_hce_key_is_also_present() -> None:
    profile = PlanProfile(plan_type="401k", safe_harbor=True)
    doc = _doc("Cover letter\nMutual of America\nWe are pleased to provide your valuation package")
    files = [
        "Valuation Pkg 2024.pdf",
        "ResultSumm.pdf",
        "402.pdf",
        "415.pdf",
        "410.pdf",
        "123456 2024HCEKey.pdf",
        "123456 2025HCE.pdf",
        "FYHCE.pdf",
        "TH.pdf",
        "Census.pdf",
        "Contri.pdf",
    ]
    present = assembly_stops._present_reports(doc, files)
    assert "HCE Key Report" in present
    assert "Future HCE Report" in present
    assert assembly_stops._missing_report_reasons(doc, profile, files) == []


def test_later_year_hce_filename_counts_as_future_hce_without_key_named_file() -> None:
    profile = PlanProfile(plan_type="401k", safe_harbor=True)
    doc = _doc("Cover letter\nMutual of America\nWe are pleased to provide your valuation package")
    files = [
        "Valuation Pkg 2024.pdf", "ResultSumm.pdf", "402.pdf", "415.pdf", "410.pdf",
        "HCEKey.pdf", "2025HCE.pdf", "TH.pdf", "Census.pdf", "Contri.pdf",
    ]
    assert "Future HCE Report" in assembly_stops._present_reports(doc, files)


def test_future_hce_names_are_classified_for_year_only_and_explicit_future_forms() -> None:
    filenames = [
        "123456 2024 Valuation Pkg.pdf",
        "123456 2024HCEKey.pdf",
        "123456 2025HCE.pdf",
        "123456 Future 2025 HCE.pdf",
        "123456 2025 Future HCE.pdf",
        "123456 FYHCE.pdf",
    ]
    with file_order.use_filename_batch(filenames):
        sections = {name: (file_order.matched_spec(name) or {}).get("name") for name in filenames}
    assert sections[filenames[1]] == "HCE/Key"
    assert sections[filenames[2]] == "Future HCE"
    assert sections[filenames[3]] == "Future HCE"
    assert sections[filenames[4]] == "Future HCE"
    assert sections[filenames[5]] == "Future HCE"


def test_batch_ui_rows_label_and_order_future_hce_names_consistently() -> None:
    names = [
        "123456 2024 Valuation Pkg.pdf",
        "123456 2024HCEKey.pdf",
        "123456 2025HCE.pdf",
        "123456 Future 2025 HCE.pdf",
    ]
    rows = file_order.classify_file_rows(names, [0] * len(names), [1] * len(names))
    by_name = {str(row["name"]): row for row in rows}
    assert by_name[names[1]]["label"] == "HCE/Key"
    assert by_name[names[2]]["label"] == "Future HCE"
    assert by_name[names[3]]["label"] == "Future HCE"
    assert by_name[names[2]]["rank"] > by_name[names[1]]["rank"]


def test_source_tag_drives_future_hce_profile_detection_and_order_check() -> None:
    doc = _doc("Generic employee determination", "Generic employee determination")
    pdf_assembler.tag_pages(doc, 0, 1, "Future HCE")
    pdf_assembler.tag_pages(doc, 1, 2, "HCE/Key")
    detected = pdf_extractor._detect_sections(doc)
    assert [(item.name, item.page) for item in detected] == [("Future HCE", 1), ("HCE/Key", 2)]
    order_check = package_polish._assembly_order_check(doc, PlanProfile(plan_type="401k"))
    assert not order_check.passed
    assert "Future HCE appears on page 1 before HCE/Key on page 2" in order_check.detail


def test_tagged_future_hce_report_year_is_allowed_by_pye_validation() -> None:
    doc = _doc("Future HCE\nPlan Year End: 06/30/2025")
    pdf_assembler.tag_pages(doc, 0, 1, "Future HCE")
    profile = PlanProfile(plan_year_end="06/30/2024")
    assert assembly_stops._pye_reasons(doc, profile) == []


def test_valuation_package_detection_uses_pdf_cover_when_filename_is_generic() -> None:
    doc = _doc("MUTUAL OF AMERICA\nWe are pleased to provide your valuation package")
    assert assembly_stops._is_valuation_package(["package.pdf"], doc)


def test_unselected_content_validation_is_ignored() -> None:
    doc = _doc(
        "Compliance Testing Summary of Results\nPlan is/is not Top Heavy",
        "Census Report\nSSN 123-XX-6789",
    )
    assert assembly_stops._content_reasons(doc, {"ssn", "summary_placeholders"})
    assert assembly_stops._content_reasons(doc, {"summary_placeholders"})
    assert assembly_stops._content_reasons(doc, {"ssn"})


def test_explicit_empty_ignore_selection_enforces_every_stop_check() -> None:
    doc = _doc(
        "Compliance Testing Summary of Results\nPlan is/is not Top Heavy",
        "Census Report\nSSN 123-XX-6789",
    )
    assert len(assembly_stops.stop_reasons(doc, PlanProfile(), ["package.pdf"], selected_checks=[])) == 2


def test_ignoring_one_validation_message_does_not_ignore_its_sibling() -> None:
    doc = _doc(
        "Compliance Testing Summary of Results\nPlan is/is not Top Heavy",
        "Census Report\nSSN 123-XX-6789",
    )
    all_reasons = assembly_stops.stop_reasons(doc, PlanProfile(), ["package.pdf"])
    failures = assembly_stops.validation_failures(all_reasons)
    remaining = assembly_stops.stop_reasons(
        doc,
        PlanProfile(),
        ["package.pdf"],
        selected_checks=[str(failures[0]["id"])],
    )
    assert len(all_reasons) == 2
    assert len(remaining) == 1
    assert remaining[0] == all_reasons[1]


def test_failed_validation_reasons_are_individual_retry_options() -> None:
    reasons = [
        "A full or masked Social Security number was found on page(s) 2. Assembly stopped.",
        "The Result Summary still has unresolved wording such as Plan is/is not. Assembly stopped.",
        "These required reports are missing: Census Report. Assembly stopped.",
        "Report pages do not follow TEST23 order: Census appears before Top Heavy. Assembly stopped.",
    ]
    result = assembly_stops.validation_failures(reasons)
    assert [item["category"] for item in result] == ["ssn", "summary_placeholders", "required_reports", "report_order"]
    assert [item["label"] for item in result] == [
        "Full or masked Social Security numbers",
        "Unresolved Result Summary wording",
        "Required reports present",
        "Report order",
    ]
    assert result[0]["details"] == [reasons[0]]


def test_each_same_category_result_error_has_an_independent_validation_id() -> None:
    first = "Result Summary validation failed (Top heavy on Result Summary): percent was not found. Assembly stopped."
    second = "Result Summary validation failed (ACP on Result Summary): Result Summary says pass, the report says fail. Assembly stopped."
    failures = assembly_stops.validation_failures([first, second])
    assert len(failures) == 2
    assert failures[0]["category"] == failures[1]["category"] == "summary_results"
    assert failures[0]["id"] != failures[1]["id"]
    assert failures[0]["details"] == [first]
    assert failures[1]["details"] == [second]


def test_duplicate_stop_messages_also_get_separate_validation_ids() -> None:
    reason = "The plan name could not be verified. Assembly stopped."
    failures = assembly_stops.validation_failures([reason, reason])
    assert failures[0]["id"] != failures[1]["id"]


def test_unselected_package_checks_are_ignored() -> None:
    doc = _doc("MUTUAL OF AMERICA\nWe are pleased to provide your valuation package")
    profile = PlanProfile(moa_logo_found=False)
    reasons = assembly_stops._package_reasons(
        doc,
        profile,
        ["Valuation Pkg.pdf"],
        None,
        None,
        selected_checks={"ssn"},
    )
    assert reasons == []

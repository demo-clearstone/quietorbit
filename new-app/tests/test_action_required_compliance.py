import fitz

from services.action_required import inspect_compliance_failure_wording
from services.pdf_extractor import extract_plan_profile
from services.plan_profile_service import finalize_profile
from services.review_service import validate
from services.rules_engine import evaluate

HEADING = "IMMEDIATE ACTION REQUIRED - COMPLIANCE TEST FAILURE"
BODY = (
    "Contribution refunds to participants are required to correct compliance testing failures. "
    "Review the Excess Summary report provided in this package for details and return any "
    "required documents or contact your local regional office representative.\n"
    "To help ensure returns are processed correctly, please also return Form W-4R documents "
    "for each affected participant."
)


def _pdf(lines: list[str]) -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(54, 54, 558, 738), "\n".join(lines), fontsize=11, fontname="helv")
    return doc


def _compliance_pdf(*extra: str, include_paragraph: bool = True) -> fitz.Document:
    lines = ["Action Required"]
    if include_paragraph:
        lines.extend([HEADING, "", BODY, ""])
    lines.extend(extra)
    return _pdf(lines)


def test_wording_matches_test23_compliance_paragraph():
    doc = _compliance_pdf("402(g) Test: Fail", "Returns Required")
    try:
        wording = inspect_compliance_failure_wording(doc)
        review = validate(extract_plan_profile(doc), doc=doc)
        item = next(i for i in review.items if i.code == "action_compliance_wording")
        assert wording["found"] is True
        assert wording["wording_ok"] is True
        assert item.passed is True
    finally:
        doc.close()


def test_keep_paragraph_when_402g_fails_and_returns_required():
    doc = _compliance_pdf("ADP Test: Pass", "ACP Test: Pass", "402(g) Test: Fail", "415 Test: Pass")
    try:
        profile = finalize_profile(extract_plan_profile(doc))
        by_id = {d.rule_id: d for d in evaluate(profile)}
        assert profile.fail_402g is True
        assert profile.returns_required is True
        assert profile.adp_failed is False
        assert profile.fail_402g_after_deadline is False
        assert by_id["A"].action == "keep"
    finally:
        doc.close()


def test_remove_paragraph_for_adp_failure_only():
    doc = _compliance_pdf("ADP Test: Fail", "ACP Test: Pass", "402(g) Test: Pass", "415 Test: Pass")
    try:
        profile = finalize_profile(extract_plan_profile(doc))
        by_id = {d.rule_id: d for d in evaluate(profile)}
        assert profile.adp_failed is True
        assert profile.fail_402g is False
        assert profile.fail_415 is False
        assert by_id["A"].action == "remove"
    finally:
        doc.close()


def test_remove_paragraph_when_failure_does_not_cause_a_return():
    doc = _compliance_pdf(
        "402(g) Test: Fail",
        "415 Test: Pass",
        "No Returns Required",
        include_paragraph=False,
    )
    try:
        profile = finalize_profile(extract_plan_profile(doc))
        by_id = {d.rule_id: d for d in evaluate(profile)}
        assert profile.fail_402g is True
        assert profile.returns_required is False
        assert by_id["A"].action == "remove"
    finally:
        doc.close()


def test_remove_paragraph_when_402g_not_processed_by_415_deadline():
    doc = _compliance_pdf(
        "402(g) Test: Fail",
        "Returns Required",
        "402(g) failure not processed by 4/15 deadline — noted on the 402(g) test.",
    )
    try:
        profile = finalize_profile(extract_plan_profile(doc))
        by_id = {d.rule_id: d for d in evaluate(profile)}
        assert profile.fail_402g is True
        assert profile.fail_402g_after_deadline is True
        assert by_id["A"].action == "remove"
    finally:
        doc.close()


def test_wording_fails_when_required_phrases_are_missing():
    doc = _pdf([HEADING, "Some other action required text without the SOP refund language."])
    try:
        wording = inspect_compliance_failure_wording(doc)
        review = validate(extract_plan_profile(doc), doc=doc)
        item = next(i for i in review.items if i.code == "action_compliance_wording")
        assert wording["found"] is True
        assert wording["wording_ok"] is False
        assert item.passed is False
    finally:
        doc.close()

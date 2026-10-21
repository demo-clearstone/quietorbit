import re

import fitz

from services.orchestrator import process_uploads
from services.package_builder import PARAGRAPHS, build_valuation_with_action_paragraphs
from services.plan_profile_service import finalize_profile
from services.rules_engine import evaluate
from services.outlook_service import email_subject
from services.source_docs import build_assembly_excel, build_summary_pdf
from services.source_profile import parse_excel, parse_summary_text
from models.plan_profile import PlanProfile


def _heading_map() -> dict[str, str]:
    return {
        "A": PARAGRAPHS[0][0],
        "B": PARAGRAPHS[1][0],
        "C": PARAGRAPHS[2][0],
        "D": PARAGRAPHS[3][0],
        "E": PARAGRAPHS[4][0],
        "F": PARAGRAPHS[5][0],
        "G": PARAGRAPHS[6][0],
    }


def test_excel_reads_current_method_from_assembly_template():
    overlay = parse_excel(build_assembly_excel())
    assert overlay["plan_number"] == "800643"
    assert overlay["testing_method"] == "CURRENT"
    assert overlay["plan_type"] == "403b"
    assert overlay["hce_current"] is True
    assert overlay["rework"] is False
    assert overlay["rush"] is False
    assert overlay.get("adp_reclassified") is None


def test_email_subject_names_rework_and_rush():
    base = dict(plan_number="800643", plan_name="Example Plan", plan_year_end="06/30/2026")
    tail = "800643 - Example Plan - PYE 06/30/2026"
    assert email_subject(PlanProfile(**base)) == f"MOA - {tail}"
    assert email_subject(PlanProfile(**base, rework=True)) == f"MOA - Rework - {tail}"
    assert email_subject(PlanProfile(**base, rush=True)) == f"MOA - Rush - {tail}"
    assert email_subject(PlanProfile(**base, rework=True, rush=True)) == f"MOA - Rush Rework - {tail}"


def test_summary_reads_adp_fail_and_other_tests_pass():
    summary = fitz.open(stream=build_summary_pdf(), filetype="pdf")
    try:
        overlay = parse_summary_text(summary[0].get_text("text"))
    finally:
        summary.close()
    assert overlay["plan_number"] == "900062"
    assert overlay["plan_year_end"] == "12/31/2025"
    assert overlay["adp_failed"] is True
    assert overlay["fail_402g"] is False
    assert overlay["fail_415"] is False
    assert overlay["top_heavy"] is False
    assert overlay["top_heavy_percent"] == 8.85
    assert overlay["returns_required"] is False
    assert overlay["returns_already_processed"] is True


def test_package_has_cover_then_action_required_pages():
    doc = build_valuation_with_action_paragraphs()
    try:
        assert doc.page_count == 4
        cover = doc[0].get_text("text")
        assert "900062" in cover
        assert "Michigan United Credit Union" in cover
        body = "\n".join(page.get_text("text") or "" for page in doc)
        for heading, _body in PARAGRAPHS:
            assert heading in body
    finally:
        doc.close()


def test_process_excel_and_summary_keeps_only_no_action_paragraph(tmp_path, monkeypatch):
    import services.save_service as save_service

    monkeypatch.setattr(save_service, "OUTPUT_DIR", tmp_path)
    valuation = build_valuation_with_action_paragraphs()
    try:
        package_bytes = valuation.tobytes()
    finally:
        valuation.close()

    result = process_uploads(
        [
            ("01_cover-and-action.pdf", package_bytes),
            ("val-assembly.xlsx", build_assembly_excel()),
            ("compliance-summary.pdf", build_summary_pdf()),
        ]
    )
    profile = result.plan_profile
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert profile.plan_number == "900062"
    assert profile.beginning_plan_year == "2025"
    assert result.filename == "900062_2025-Valuation.pdf"
    assert profile.testing_method == "CURRENT"
    assert profile.adp_failed is True
    assert profile.fail_402g is False
    assert profile.returns_required is False
    assert profile.has_action_required is False
    assert by_id["A"].action == "remove"
    assert by_id["B"].action == "remove"
    assert by_id["C"].action == "remove"
    assert by_id["F"].action == "remove"
    assert by_id["G"].action == "keep"

    saved = fitz.open(result.pdf_path)
    try:
        assert saved.page_count == 5
        text = "\n".join(page.get_text("text") or "" for page in saved)
        assert "COMPLIANCE AND ADMINISTRATIVE REPORTS" in text
        assert "410(b) COVERAGE TEST" in text
        assert "HCE/KEY EMPLOYEE DETERMINATIONS" in text
        headings = _heading_map()
        assert headings["G"] in text
        for code in ("A", "B", "C", "D", "E", "F"):
            assert headings[code] not in text
        assert "Cover Letter" in saved[0].get_text("text")
        action = saved[1]
        assert (action.get_text("text") or "").strip()
        words = action.get_text("words")
        assert words
        assert words[0][1] < 80
        for page in saved:
            leftover = re.sub(r"\s+", " ", page.get_text("text") or "").strip()
            assert leftover
            assert leftover.lower() != "action required"
    finally:
        saved.close()


def test_prior_method_with_returns_keeps_prior_paragraph():
    profile = finalize_profile(
        PlanProfile(
            testing_method="PRIOR",
            adp_failed=True,
            acp_failed=False,
            returns_required=True,
            fail_402g=False,
            fail_415=False,
            top_heavy=False,
        )
    )
    by_id = {item.rule_id: item for item in evaluate(profile)}
    assert by_id["B"].action == "keep"
    assert by_id["C"].action == "remove"


def test_reclassified_adp_failure_removes_prior_paragraph():
    profile = finalize_profile(
        PlanProfile(
            testing_method="PRIOR",
            adp_failed=True,
            returns_required=True,
            adp_reclassified=True,
            fail_402g=False,
            fail_415=False,
        )
    )
    by_id = {item.rule_id: item for item in evaluate(profile)}
    assert profile.returns_required is False
    assert by_id["B"].action == "remove"

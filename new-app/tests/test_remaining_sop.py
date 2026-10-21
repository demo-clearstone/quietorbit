import re
from pathlib import Path

from services.orchestrator import process_uploads
from services.package_builder import RECAP_BULLETS, build_remaining_sop_pdf
from services.pdf_extractor import extract_plan_profile
from services.plan_profile_service import finalize_profile
from services.rules_engine import evaluate


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _pdf_text(path: str) -> str:
    import fitz

    doc = fitz.open(path)
    try:
        return _flat("\n".join(page.get_text("text") or "" for page in doc))
    finally:
        doc.close()


def _bytes(doc) -> bytes:
    data = doc.tobytes()
    doc.close()
    return data


def _process(tmp_path, monkeypatch, doc, source_folder=None, check_assembly_stops=False):
    import services.save_service as save_service

    monkeypatch.setattr(save_service, "OUTPUT_DIR", tmp_path)
    return process_uploads(
        [("remaining-sop.pdf", _bytes(doc))],
        source_folder=source_folder,
        check_assembly_stops=check_assembly_stops,
    )


def test_remaining_flags_and_rules():
    doc = build_remaining_sop_pdf()
    try:
        profile = finalize_profile(extract_plan_profile(doc))
        assert profile.variance_report is True
        assert profile.contributions_required is True
        assert profile.keep_excess_summary is True
        assert profile.hce_current is True
        assert profile.safe_harbor is False
        by_id = {item.rule_id: item for item in evaluate(profile)}
        assert by_id["H"].action == "keep"
        assert by_id["M"].action == "keep"
        assert by_id["ES"].action == "keep"
        assert by_id["Y1"].action == "remove"
        assert by_id["Y2"].action == "remove"
        assert by_id["Y3"].action == "keep"
        assert by_id["Y4"].action == "remove"
        assert by_id["Y8"].action == "keep"
    finally:
        doc.close()


def test_variance_contributions_excess_and_current_recap(tmp_path, monkeypatch):
    result = _process(tmp_path, monkeypatch, build_remaining_sop_pdf())
    text = _pdf_text(result.pdf_path)
    assert "IMMEDIATE ACTION REQUIRED - VARIANCE" in text
    assert "IMMEDIATE ACTION REQUIRED - CONTRIBUTIONS" in text
    assert "Excess Summary Report" in text
    assert "the actual amount the employee can defer" in text
    assert "prior year data" not in text
    assert "did not have any Highly Compensated Employees" not in text
    assert "Safe Harbor Plan" not in text
    assert "not administered by Mutual of America" in text
    assert "employer match contribution is calculated" in text
    assert result.email_subject.startswith("MOA - 777777 -")
    assert Path(result.email_path).is_file()
    assert Path(result.log_path).is_file()
    assert result.review and result.review.ssn_found is False


def test_no_variance_or_contributions_removes_those_pages(tmp_path, monkeypatch):
    doc = build_remaining_sop_pdf(
        variance="No Variance Report",
        contributions="No Contributions Required",
        g402="Pass",
        returns="No Returns Required",
    )
    result = _process(tmp_path, monkeypatch, doc)
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert by_id["H"].action == "remove"
    assert by_id["M"].action == "remove"
    assert by_id["ES"].action == "remove"
    text = _pdf_text(result.pdf_path)
    assert "IMMEDIATE ACTION REQUIRED - VARIANCE" not in text
    assert "IMMEDIATE ACTION REQUIRED - CONTRIBUTIONS" not in text
    assert "Excess Summary Report" not in text


def test_excess_summary_kept_for_partially_vested_adp(tmp_path, monkeypatch):
    doc = build_remaining_sop_pdf(
        adp="Fail",
        g402="Pass",
        s415="Pass",
        partially_vested=True,
        variance="No Variance Report",
        contributions="No Contributions Required",
    )
    result = _process(tmp_path, monkeypatch, doc)
    assert result.plan_profile.keep_excess_summary is True
    assert "Excess Summary Report" in _pdf_text(result.pdf_path)


def test_recap_no_hce_keeps_no_hce_bullet(tmp_path, monkeypatch):
    doc = build_remaining_sop_pdf(hce_current="No", hce_future="No")
    result = _process(tmp_path, monkeypatch, doc)
    text = _pdf_text(result.pdf_path)
    assert "did not have any Highly Compensated Employees" in text
    assert "prior year data" not in text
    assert "the actual amount the employee can defer" not in text


def test_recap_prior_keeps_prior_bullet(tmp_path, monkeypatch):
    doc = build_remaining_sop_pdf(method="PRIOR")
    result = _process(tmp_path, monkeypatch, doc)
    text = _pdf_text(result.pdf_path)
    assert "prior year data" in text
    assert "the actual amount the employee can defer" not in text


def test_safe_harbor_bullet_stays_when_it_also_has_the_current_sentence(tmp_path, monkeypatch):
    import fitz

    doc = fitz.open()
    doc.new_page().insert_textbox(
        fitz.Rect(54, 54, 558, 738),
        "\n".join(
            [
                "Cover Letter",
                "Plan Number: 777777",
                "Testing Method: CURRENT",
                "HCE Current Year: Yes",
                "HCE Future year: Yes",
                "Safe Harbor: Yes",
            ]
        ),
        fontsize=11,
        fontname="helv",
    )
    doc.new_page().insert_textbox(
        fitz.Rect(54, 54, 558, 738),
        "\n".join(
            [
                "Important Information",
                "",
                "- Note: in addition, the actual amount the employee can defer cannot exceed the annual addition limit.",
                "- The plan follows the rules and regulations of the Safe Harbor Plan. Note: The actual amount the employee can defer in 2022 is the lesser of $20,500.",
            ]
        ),
        fontsize=11,
        fontname="helv",
    )
    result = _process(tmp_path, monkeypatch, doc)
    text = _pdf_text(result.pdf_path)
    assert "Safe Harbor Plan" in text
    assert "cannot exceed the annual addition limit" not in text


def test_prior_recap_bullet_is_filled_from_the_adp_nhce_rate(tmp_path, monkeypatch):
    import fitz

    doc = fitz.open()
    doc.new_page().insert_textbox(
        fitz.Rect(54, 54, 558, 738),
        "\n".join(
            [
                "Cover Letter",
                "Plan Number: 777777",
                "Testing Method: PRIOR",
                "HCE Current Year: Yes",
                "HCE Future year: No",
                "Safe Harbor: No",
            ]
        ),
        fontsize=11,
        fontname="helv",
    )
    doc.new_page().insert_textbox(
        fitz.Rect(54, 54, 558, 738),
        "Important Information\n\n"
        "- The maximum average deferral rate for the Highly Compensated Employee(s) for the 2022 plan year "
        "is % based on the average deferral rate for your Nonhighly Compensated Employees (NHCE) for 2021 of %. "
        "This rate is determined using the 'prior year data' method. "
        "Note: the actual amount the employee can defer is the lesser of that rate.",
        fontsize=11,
        fontname="helv",
    )
    doc.new_page().insert_textbox(
        fitz.Rect(54, 54, 558, 738),
        "TEST RESULTS\n"
        "The ADP for the 65 NHCE(s) is 2.21% (143.65/65). This value will be used in next year's test.",
        fontsize=11,
        fontname="helv",
    )
    result = _process(tmp_path, monkeypatch, doc)
    text = _pdf_text(result.pdf_path)
    assert "is 4.21% based on" in text
    assert "of 2.21%" in text
    assert "prior year data" in text


def test_full_prior_bullet_is_filled_from_the_nhce_rate(tmp_path, monkeypatch):
    import fitz

    from services.package_builder import write_recap_page

    doc = fitz.open()
    cover = doc.new_page()
    cover.insert_textbox(
        fitz.Rect(54, 54, 540, 400),
        "\n".join(
            [
                "Cover Letter",
                "Plan Number: 800808",
                "Testing Method: PRIOR",
                "HCE Current Year: Yes",
                "HCE Future year: Yes",
                "Safe Harbor: No",
            ]
        ),
        fontsize=11,
    )
    page = doc.new_page(width=595.28, height=841.89)
    write_recap_page(page, ["Important Information"], [RECAP_BULLETS[1], RECAP_BULLETS[2]])
    results = doc.new_page()
    results.insert_text(
        (72, 72),
        "TEST RESULTS\nADP TEST USING PRIOR YEAR NHCE PERCENTAGES\n"
        "The ADP for the 65 NHCE(s) is 2.21% (143.65/65). This value will be used in next year's test.",
        fontsize=11,
    )
    result = _process(tmp_path, monkeypatch, doc)
    text = _pdf_text(result.pdf_path)
    assert "is 4.21% based on" in text
    assert "for 2025 of 2.21%" in text
    assert "the actual amount the employee can defer" not in text


def test_recap_safe_harbor_keeps_sh_bullet(tmp_path, monkeypatch):
    doc = build_remaining_sop_pdf(safe_harbor="Yes")
    result = _process(tmp_path, monkeypatch, doc)
    text = _pdf_text(result.pdf_path)
    assert "Safe Harbor Plan" in text
    assert "the actual amount the employee can defer" not in text


def test_recap_top_heavy_and_catchup_and_match(tmp_path, monkeypatch):
    keep = _process(
        tmp_path,
        monkeypatch,
        build_remaining_sop_pdf(top_heavy="Yes", catchup_allowed="Yes", per_payroll="Yes"),
    )
    keep_text = _pdf_text(keep.pdf_path)
    assert "Based on the top heavy testing results" in keep_text
    assert "designed to allow participants who were age 50" in keep_text

    drop_result = _process(
        tmp_path,
        monkeypatch,
        build_remaining_sop_pdf(top_heavy="No", catchup_allowed="No", per_payroll="No"),
    )
    drop_text = _pdf_text(drop_result.pdf_path)
    assert "Based on the top heavy testing results" not in drop_text
    assert "designed to allow participants who were age 50" not in drop_text
    assert "employer match contribution is calculated" not in drop_text


def test_ssn_scan_stops_assembly(tmp_path, monkeypatch):
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as raised:
        _process(tmp_path, monkeypatch, build_remaining_sop_pdf(include_ssn=True), check_assembly_stops=True)
    assert raised.value.status_code == 400
    assert "Social Security number" in raised.value.detail


def test_saves_copy_into_testing_folder(tmp_path, monkeypatch):
    testing = tmp_path / "800643" / "Testing" / "2024 Testing"
    package = testing / "Valuation Package"
    package.mkdir(parents=True)
    result = _process(
        tmp_path / "jobs",
        monkeypatch,
        build_remaining_sop_pdf(),
        source_folder=str(package),
    )
    copy = testing / result.filename
    assert copy.is_file()
    assert result.saved_copy_path == str(copy)


def test_recap_templates_match_test23():
    blob = " ".join(RECAP_BULLETS)
    assert "did not have any Highly Compensated Employees" in blob
    assert "prior year data" in blob
    assert "is % based on" in blob
    assert "for 2025 of %" in blob
    assert "$24,500" in blob
    assert "$11,250" in blob
    assert "Safe Harbor Plan" in blob
    assert "not administered by Mutual of America" in blob


def test_adp_results_prior_year_wording_sets_prior_method():
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "TEST RESULTS\nADP TEST USING PRIOR YEAR NHCE PERCENTAGES\nACP TEST USING PRIOR YEAR NHCE PERCENTAGES",
        fontsize=11,
    )
    try:
        profile = extract_plan_profile(doc)
    finally:
        doc.close()
    assert profile.testing_method == "PRIOR"


def test_results_page_without_prior_wording_is_current(tmp_path, monkeypatch):
    import fitz

    doc = fitz.open()
    cover = doc.new_page()
    cover.insert_textbox(
        fitz.Rect(54, 54, 540, 400),
        "\n".join(
            [
                "Cover Letter",
                "Plan Number: 777777",
                "HCE Current Year: Yes",
                "HCE Future year: Yes",
                "Safe Harbor: No",
            ]
        ),
        fontsize=11,
    )
    results = doc.new_page()
    results.insert_text(
        (72, 72),
        "TEST RESULTS\nADP TEST\nACP TEST\nThe ADP for the 65 NHCE(s) is 2.21% (143.65/65).",
        fontsize=11,
    )
    recap = doc.new_page()
    recap.insert_textbox(
        fitz.Rect(54, 54, 540, 700),
        "Important Information\n\n"
        "- This rate is determined using the \"prior year data\" method. The maximum average deferral rate "
        "for the 2026 plan year is % based on the average deferral rate for 2025 of %.\n\n"
        "- Note: In addition, the actual amount the employee can defer in 2026 cannot exceed $24,500.",
        fontsize=11,
    )
    result = _process(tmp_path, monkeypatch, doc)
    assert result.plan_profile.testing_method == "CURRENT"
    text = _pdf_text(result.pdf_path)
    assert "prior year data" not in text
    assert "the actual amount the employee can defer" in text


def test_switching_to_safe_harbor_keeps_the_sh_bullet(tmp_path, monkeypatch):
    doc = build_remaining_sop_pdf(method="CURRENT", safe_harbor="No", hce_current="Yes", hce_future="Yes")
    # The cover line is added on top of Safe Harbor: No. The switching note is the keep signal.
    page = doc[0]
    page.insert_text((72, 400), "The plan is switching to SH next year.", fontsize=11)
    result = _process(tmp_path, monkeypatch, doc)
    text = _pdf_text(result.pdf_path)
    assert result.plan_profile.safe_harbor is True
    assert "Safe Harbor Plan" in text
    assert "the actual amount the employee can defer" not in text
    assert "prior year data" not in text


def test_prior_and_safe_harbor_keeps_only_the_sh_bullet(tmp_path, monkeypatch):
    doc = build_remaining_sop_pdf(method="PRIOR", safe_harbor="Yes")
    result = _process(tmp_path, monkeypatch, doc)
    text = _pdf_text(result.pdf_path)
    assert "Safe Harbor Plan" in text
    assert "prior year data" not in text

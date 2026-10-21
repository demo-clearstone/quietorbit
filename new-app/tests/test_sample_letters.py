import re

import fitz

from models.plan_profile import PlanProfile
from services.orchestrator import process_uploads
from services.package_builder import (
    NOTICE_415,
    SAMPLE_LETTER_402G,
    SAMPLE_LETTER_415,
    SAMPLE_LETTER_ADP,
    SAMPLE_LETTER_ADP_ACP,
    _textbox,
    build_sample_letters_pdf,
)
from services.pdf_extractor import extract_plan_profile
from services.plan_profile_service import finalize_profile
from services.rules_engine import evaluate


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _pdf_text(path: str) -> str:
    doc = fitz.open(path)
    try:
        return _flat("\n".join(page.get_text("text") or "" for page in doc))
    finally:
        doc.close()


def _bytes(doc: fitz.Document) -> bytes:
    data = doc.tobytes()
    doc.close()
    return data


def _process(tmp_path, monkeypatch, doc):
    import services.save_service as save_service

    monkeypatch.setattr(save_service, "OUTPUT_DIR", tmp_path)
    return process_uploads([("sample-letters.pdf", _bytes(doc))])


def test_all_fail_with_returns_keeps_j_k_and_l():
    doc = build_sample_letters_pdf()
    try:
        profile = finalize_profile(extract_plan_profile(doc))
        assert profile.adp_failed is True
        assert profile.acp_failed is True
        assert profile.fail_402g is True
        assert profile.fail_415 is True
        assert profile.returns_required is True
        assert profile.fail_402g_after_deadline is False
        by_id = {item.rule_id: item for item in evaluate(profile)}
        assert by_id["J_ADP"].action == "keep"
        assert by_id["J_ACP"].action == "keep"
        assert by_id["K"].action == "keep"
        assert by_id["L"].action == "keep"
    finally:
        doc.close()


def test_j_k_l_pages_kept_when_all_apply(tmp_path, monkeypatch):
    result = _process(tmp_path, monkeypatch, build_sample_letters_pdf())
    text = _pdf_text(result.pdf_path)
    assert "failing the ADP/ACP nondiscrimination testing" in text
    assert "402(g) Deferral Limit has been exceeded" in text
    assert "Annual Additions (IRC 415) Test Failure Information" in text
    assert "exceeding the Annual Additions (IRC 415) limit" in text


def test_j_removed_when_adp_acp_pass(tmp_path, monkeypatch):
    doc = build_sample_letters_pdf(adp="Pass", acp="Pass")
    result = _process(tmp_path, monkeypatch, doc)
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert by_id["J_ADP"].action == "remove"
    assert by_id["J_ACP"].action == "remove"
    text = _pdf_text(result.pdf_path)
    assert "failing the ADP/ACP nondiscrimination testing" not in text
    assert "402(g) Deferral Limit has been exceeded" in text
    assert "exceeding the Annual Additions (IRC 415) limit" in text


def test_j_removed_when_no_returns(tmp_path, monkeypatch):
    doc = build_sample_letters_pdf(returns="No Returns Required")
    result = _process(tmp_path, monkeypatch, doc)
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert result.plan_profile.returns_required is False
    assert by_id["J_ADP"].action == "remove"
    assert by_id["J_ACP"].action == "remove"
    assert by_id["K"].action == "remove"
    text = _pdf_text(result.pdf_path)
    assert "failing the ADP/ACP nondiscrimination testing" not in text
    assert "402(g) Deferral Limit has been exceeded" not in text


def test_k_removed_when_402g_passes(tmp_path, monkeypatch):
    doc = build_sample_letters_pdf(g402="Pass")
    result = _process(tmp_path, monkeypatch, doc)
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert result.plan_profile.fail_402g is False
    assert by_id["K"].action == "remove"
    text = _pdf_text(result.pdf_path)
    assert "402(g) Deferral Limit has been exceeded" not in text
    assert "failing the ADP/ACP nondiscrimination testing" in text


def test_k_removed_when_402g_after_415_deadline(tmp_path, monkeypatch):
    doc = build_sample_letters_pdf(after_deadline=True)
    result = _process(tmp_path, monkeypatch, doc)
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert result.plan_profile.fail_402g_after_deadline is True
    assert by_id["K"].action == "remove"
    assert by_id["A"].action == "remove"
    text = _pdf_text(result.pdf_path)
    assert "402(g) Deferral Limit has been exceeded" not in text


def test_l_removed_when_415_passes(tmp_path, monkeypatch):
    doc = build_sample_letters_pdf(s415="Pass")
    result = _process(tmp_path, monkeypatch, doc)
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert result.plan_profile.fail_415 is False
    assert by_id["L"].action == "remove"
    text = _pdf_text(result.pdf_path)
    assert "Test Failure Information" not in text
    assert "exceeding the Annual Additions (IRC 415) limit" not in text
    assert "failing the ADP/ACP nondiscrimination testing" in text
    assert "402(g) Deferral Limit has been exceeded" in text


def test_only_415_keeps_packet_and_letter(tmp_path, monkeypatch):
    doc = build_sample_letters_pdf(
        adp="Pass",
        acp="Pass",
        g402="Pass",
        s415="Fail",
        returns="No Returns Required",
    )
    result = _process(tmp_path, monkeypatch, doc)
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert by_id["J_ADP"].action == "remove"
    assert by_id["J_ACP"].action == "remove"
    assert by_id["K"].action == "remove"
    assert by_id["L"].action == "keep"
    text = _pdf_text(result.pdf_path)
    assert "Annual Additions (IRC 415) Test Failure Information" in text
    assert "exceeding the Annual Additions (IRC 415) limit" in text
    assert "failing the ADP/ACP nondiscrimination testing" not in text
    assert "402(g) Deferral Limit has been exceeded" not in text


def test_combined_adp_acp_letter_stays_when_only_adp_fails(tmp_path, monkeypatch):
    doc = build_sample_letters_pdf(adp="Fail", acp="Pass", include_j_adp=False, include_j_acp=False)
    _textbox(
        doc,
        "SAMPLE/DRAFT Communication to Participant\n"
        "(To Be Placed on Company Letterhead)\n"
        "Actual Deferral Percentage (ADP) and/or Actual Contribution Percentage (ACP)",
    )
    result = _process(tmp_path, monkeypatch, doc)
    text = _pdf_text(result.pdf_path)
    assert "Actual Deferral Percentage (ADP)" in text
    assert "Actual Contribution Percentage (ACP)" in text


def test_combined_adp_acp_letter_stays_when_only_acp_fails(tmp_path, monkeypatch):
    doc = build_sample_letters_pdf(adp="Pass", acp="Fail", include_j_adp=False, include_j_acp=False)
    _textbox(
        doc,
        "SAMPLE/DRAFT Communication to Participant\n"
        "(To Be Placed on Company Letterhead)\n"
        "Actual Deferral Percentage (ADP) and/or Actual Contribution Percentage (ACP)",
    )
    result = _process(tmp_path, monkeypatch, doc)
    text = _pdf_text(result.pdf_path)
    assert "Actual Deferral Percentage (ADP)" in text
    assert "Actual Contribution Percentage (ACP)" in text


def test_combined_adp_acp_letter_is_removed_when_neither_fails(tmp_path, monkeypatch):
    doc = build_sample_letters_pdf(adp="Pass", acp="Pass", include_j_adp=False, include_j_acp=False)
    _textbox(
        doc,
        "SAMPLE/DRAFT Communication to Participant\n"
        "(To Be Placed on Company Letterhead)\n"
        "Actual Deferral Percentage (ADP) and/or Actual Contribution Percentage (ACP)",
    )
    result = _process(tmp_path, monkeypatch, doc)
    # The compliance overview describes the ACP test. It is not the participant letter.
    from services.package_polish import is_compliance_overview

    out = fitz.open(result.pdf_path)
    try:
        text = "\n".join(
            page.get_text("text") or ""
            for page in out
            if not is_compliance_overview(page.get_text("text") or "")
        )
    finally:
        out.close()
    assert "Actual Deferral Percentage (ADP)" not in text
    assert "Actual Contribution Percentage (ACP)" not in text


def test_adp_only_keeps_the_combined_letter(tmp_path, monkeypatch):
    doc = build_sample_letters_pdf(adp="Fail", acp="Pass")
    result = _process(tmp_path, monkeypatch, doc)
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert by_id["J_ADP"].action == "keep"
    assert by_id["J_ACP"].action == "remove"
    text = _pdf_text(result.pdf_path)
    assert "Actual Deferral Percentage (ADP)" in text
    assert "Actual Contribution Percentage (ACP)" in text


def test_acp_only_keeps_the_combined_letter(tmp_path, monkeypatch):
    doc = build_sample_letters_pdf(adp="Pass", acp="Fail")
    result = _process(tmp_path, monkeypatch, doc)
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert by_id["J_ADP"].action == "remove"
    assert by_id["J_ACP"].action == "keep"
    text = _pdf_text(result.pdf_path)
    assert "Actual Contribution Percentage (ACP)" in text
    assert "Actual Deferral Percentage (ADP)" in text


def test_k_rule_drops_after_deadline_without_pdf():
    profile = finalize_profile(
        PlanProfile(
            fail_402g=True,
            returns_required=True,
            fail_402g_after_deadline=True,
            adp_failed=False,
            acp_failed=False,
            fail_415=False,
        )
    )
    by_id = {item.rule_id: item for item in evaluate(profile)}
    assert by_id["K"].action == "remove"
    assert by_id["J_ADP"].action == "remove"
    assert by_id["J_ACP"].action == "remove"
    assert by_id["L"].action == "remove"


def test_sample_letter_templates_match_test23():
    assert "SAMPLE/DRAFT Communication to Participant" in SAMPLE_LETTER_ADP_ACP
    assert "Actual Contribution Percentage (ACP)" in SAMPLE_LETTER_ADP_ACP
    assert "Actual Deferral Percentage (ADP)" in SAMPLE_LETTER_ADP
    assert "402(g) Deferral Limit has been exceeded" in SAMPLE_LETTER_402G
    assert "Annual Additions (IRC 415) Test Failure Information" in NOTICE_415
    assert "Annual Additions (IRC 415) limit has been exceeded" in SAMPLE_LETTER_415

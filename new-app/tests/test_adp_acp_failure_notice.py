import re

import fitz

from services.orchestrator import process_uploads
from services.package_builder import FAILURE_NOTICE, build_adp_acp_failure_notice_pdf
from services.pdf_extractor import extract_plan_profile
from services.plan_profile_service import finalize_profile
from services.rules_engine import evaluate


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _pdf_text(path: str) -> str:
    doc = fitz.open(path)
    try:
        rows: list[str] = []
        for page in doc:
            lines: list[list[tuple]] = []
            for word in sorted(page.get_text("words") or [], key=lambda item: (item[1], item[0])):
                if not lines or abs(word[1] - lines[-1][0][1]) > 3:
                    lines.append([word])
                else:
                    lines[-1].append(word)
            for line in lines:
                line.sort(key=lambda item: item[0])
                rows.append(" ".join(str(item[4]) for item in line))
        return _flat("\n".join(rows))
    finally:
        doc.close()


def _bytes(doc: fitz.Document) -> bytes:
    data = doc.tobytes()
    doc.close()
    return data


def _process(tmp_path, monkeypatch, doc, name="failure-notice.pdf"):
    import services.save_service as save_service

    monkeypatch.setattr(save_service, "OUTPUT_DIR", tmp_path)
    return process_uploads([(name, _bytes(doc))])


def test_notice_pdf_has_placeholders_and_correction_qnecs():
    doc = build_adp_acp_failure_notice_pdf()
    try:
        text = _flat("\n".join(page.get_text("text") or "" for page in doc))
        assert "Failed Compliance Testing" in text
        assert "Excess Return Notice" in text
        assert "ADP/ACP test is $X,XXX,XXX.XX" in text
        assert "The ADP QNEC is $X,XXX,XXX.XX" in text
        assert "The ACP QNEC is $X,XXX,XXX.XX" in text
        profile = finalize_profile(extract_plan_profile(doc))
        assert profile.testing_method == "CURRENT"
        assert profile.adp_failed is True
        assert profile.acp_failed is True
        assert profile.returns_required is True
        assert profile.adp_qnec == 142540.41
        assert profile.acp_qnec == 42814.34
        assert profile.total_qnec == 185354.75
        by_id = {item.rule_id: item for item in evaluate(profile)}
        assert by_id["I"].action == "keep"
    finally:
        doc.close()


def test_current_both_qnecs_keeps_notice_and_fills_amounts(tmp_path, monkeypatch):
    result = _process(tmp_path, monkeypatch, build_adp_acp_failure_notice_pdf())
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert by_id["I"].action == "keep"
    text = _pdf_text(result.pdf_path)
    assert "Failed Compliance Testing" in text
    assert "Excess Return Notice" in text
    assert "The amount of the QNEC that is required to pass the ADP/ACP test is $185,354.75" in text
    assert text.index("$185,354.75") < text.index("The ADP QNEC is $142,540.41")
    assert text.index("The ADP QNEC is $142,540.41") < text.index("The ACP QNEC is $42,814.34")
    assert "444444" in text
    assert "HARBOR MANUFACTURING 401(K) PLAN" in text
    assert "$X,XXX,XXX.XX" not in text


def test_current_adp_only_removes_acp_qnec_sentence(tmp_path, monkeypatch):
    doc = build_adp_acp_failure_notice_pdf(acp="Pass", acp_qnec=None)
    result = _process(tmp_path, monkeypatch, doc)
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert result.plan_profile.adp_failed is True
    assert result.plan_profile.acp_failed is False
    assert by_id["I"].action == "keep"
    text = _pdf_text(result.pdf_path)
    assert "The ADP QNEC is $142,540.41" in text
    assert "The ACP QNEC is" not in text
    assert "ADP/ACP test is $142,540.41" in text


def test_current_acp_only_removes_adp_qnec_sentence(tmp_path, monkeypatch):
    doc = build_adp_acp_failure_notice_pdf(adp="Pass", adp_qnec=None)
    result = _process(tmp_path, monkeypatch, doc)
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert by_id["I"].action == "keep"
    text = _pdf_text(result.pdf_path)
    assert "The ACP QNEC is $42,814.34" in text
    assert "The ADP QNEC is" not in text


def test_single_adp_qnec_sentence_fills_the_notice(tmp_path, monkeypatch):
    doc = build_adp_acp_failure_notice_pdf(
        acp="Pass",
        adp_qnec=None,
        acp_qnec=None,
        correction_note=(
            "This plan will also qualify with a $98,861.35 QNEC contribution "
            "to the NHCEs for the ADP test."
        ),
    )
    result = _process(tmp_path, monkeypatch, doc)
    assert result.plan_profile.adp_qnec == 98861.35
    assert result.plan_profile.acp_qnec is None
    assert result.plan_profile.total_qnec == 98861.35
    text = _pdf_text(result.pdf_path)
    assert "ADP/ACP test is $98,861.35" in text
    assert "The ADP QNEC is $98,861.35" in text
    assert "The ACP QNEC is" not in text


def test_single_acp_qnec_sentence_is_read():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(
        fitz.Rect(54, 54, 558, 738),
        "This plan will also qualify with a $12,500.00 QNEC contribution to the NHCEs for the ACP test.",
        fontsize=11,
        fontname="helv",
    )
    try:
        profile = extract_plan_profile(doc)
    finally:
        doc.close()
    assert profile.acp_qnec == 12500.0
    assert profile.adp_qnec is None


def test_current_method_wording_is_removed_for_prior(tmp_path, monkeypatch):
    notice = FAILURE_NOTICE.replace("For current-method testing:", "Current method testing:")
    doc = build_adp_acp_failure_notice_pdf(method="PRIOR", notice=notice)
    result = _process(tmp_path, monkeypatch, doc)
    assert result.plan_profile.testing_method == "PRIOR"
    saved = fitz.open(result.pdf_path)
    try:
        text = "\n".join(page.get_text("text") or "" for page in saved)
        assert "Failed Compliance Testing" not in text
        assert "Excess Return Notice" not in text
        assert "Current method testing" not in text
    finally:
        saved.close()


def test_prior_method_removes_current_failure_notice(tmp_path, monkeypatch):
    doc = build_adp_acp_failure_notice_pdf(method="PRIOR")
    result = _process(tmp_path, monkeypatch, doc)
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert result.plan_profile.testing_method == "PRIOR"
    assert by_id["I"].action == "remove"
    saved = fitz.open(result.pdf_path)
    try:
        text = "\n".join(page.get_text("text") or "" for page in saved)
        assert "Failed Compliance Testing" not in text
        assert "Excess Return Notice" not in text
        assert "Cover Letter" in text
    finally:
        saved.close()


def test_no_returns_removes_failure_notice(tmp_path, monkeypatch):
    doc = build_adp_acp_failure_notice_pdf(returns="No Returns Required")
    result = _process(tmp_path, monkeypatch, doc)
    by_id = {item.rule_id: item for item in result.rule_decisions}
    assert result.plan_profile.returns_required is False
    assert by_id["I"].action == "remove"
    saved = fitz.open(result.pdf_path)
    try:
        text = "\n".join(page.get_text("text") or "" for page in saved)
        assert "Excess Return Notice" not in text
    finally:
        saved.close()


def test_after_12_months_does_not_keep_standard_current_notice():
    from models.plan_profile import PlanProfile

    profile = finalize_profile(
        PlanProfile(
            testing_method="CURRENT",
            adp_failed=True,
            returns_required=True,
            after_12_months=True,
        )
    )
    by_id = {item.rule_id: item for item in evaluate(profile)}
    assert by_id["I"].action == "remove"
    assert by_id["D"].action == "keep"


def test_failure_notice_template_matches_test23():
    assert "Current method testing" in FAILURE_NOTICE
    assert "Qualified Non-Elective Contribution" in FAILURE_NOTICE
    assert "Form W-4R" in FAILURE_NOTICE
    assert "The ADP QNEC is $X,XXX,XXX.XX" in FAILURE_NOTICE
    assert "The ACP QNEC is $X,XXX,XXX.XX" in FAILURE_NOTICE
    assert "After 12-months" not in FAILURE_NOTICE
    assert "Excess Return Notice" in FAILURE_NOTICE

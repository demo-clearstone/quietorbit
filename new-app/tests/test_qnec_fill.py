"""QNEC placeholder fill must update every amount without wiping nearby text."""

from __future__ import annotations

import fitz

from models.plan_profile import PlanProfile
from services.pdf_modifier import _money, fill_qnec_placeholders


def test_fills_all_qnec_placeholders_on_same_wrapped_line() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(
        fitz.Rect(54, 100, 540, 200),
        (
            "The amount of the QNEC that is required to pass the ADP/ACP test is $X,XXX,XXX.XX. "
            "The ADP QNEC is $X,XXX,XXX.XX. The ACP QNEC is $X,XXX,XXX.XX. Please contact your local office."
        ),
        fontsize=10,
        fontname="helv",
    )
    page.insert_text((54, 95), "LINE ABOVE MUST SURVIVE", fontsize=9)
    page.insert_text((54, 210), "LINE BELOW MUST SURVIVE", fontsize=9)
    page.draw_line(fitz.Point(54, 90), fitz.Point(500, 90), width=1)

    profile = PlanProfile(plan_type="401k", adp_qnec=142540.41, acp_qnec=42814.34)
    filled = fill_qnec_placeholders(doc, profile, [])
    text = page.get_text()

    assert "total=$185,354.75" in filled
    assert "adp=$142,540.41" in filled
    assert "acp=$42,814.34" in filled
    assert "$X,XXX,XXX.XX" not in text
    assert _money(185354.75) in text
    assert _money(142540.41) in text
    assert _money(42814.34) in text
    assert "LINE ABOVE MUST SURVIVE" in text
    assert "LINE BELOW MUST SURVIVE" in text
    assert "Please contact your local office." in text
    assert page.get_drawings(), "page graphics must survive QNEC redaction"


def test_missing_qnec_amount_removes_placeholder_without_wiping_sentence() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (54, 120),
        "The ADP QNEC is $X,XXX,XXX.XX. Please contact your local office.",
        fontsize=10,
    )
    # No ADP amount available — placeholder/label should clear, rest of sentence stays.
    fill_qnec_placeholders(doc, PlanProfile(plan_type="401k", acp_qnec=10.0), [])
    text = page.get_text()
    assert "$X,XXX,XXX.XX" not in text
    assert "Please contact your local office." in text

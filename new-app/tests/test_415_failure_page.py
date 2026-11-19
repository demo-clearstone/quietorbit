from __future__ import annotations

import fitz

from models.review import RuleDecision
from services.pdf_extractor import _flag_bool, _is_failure_notice_or_letter_page, _pass_fail_source_text
from services.pdf_modifier import apply_decisions, _is_415_failure_info_page
from config.field_patterns import FAIL_FLAGS, PASS_FLAGS


NOTICE = """Annual Additions (IRC 415) Test Failure Information

The Annual Additions (IRC 415) limit for the plan year ending 2026 is the lesser of $72,000 or 100% of a participant's compensation for the year.

What does an Annual Additions (IRC 415) test failure mean to an affected participant?
"""


def test_415_notice_page_is_detected() -> None:
    assert _is_415_failure_info_page(NOTICE)
    assert _is_failure_notice_or_letter_page(NOTICE)


def test_415_notice_text_does_not_force_fail_415() -> None:
    """Presence of the notice page must not mark fail_415=True by itself."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(54, 54, 540, 700), NOTICE, fontsize=11)
    summary = (
        "Compliance Testing Summary of Results\n"
        "415 Test: Pass\n"
        "ADP Tested: Pass\n"
    )
    page2 = doc.new_page()
    page2.insert_textbox(fitz.Rect(54, 54, 540, 700), summary, fontsize=11)
    full = "\n".join((p.get_text("text") or "") for p in doc)
    flag_text = _pass_fail_source_text(doc, full)
    assert _flag_bool(flag_text, FAIL_FLAGS["fail_415"], PASS_FLAGS["fail_415"]) is False


def test_apply_decisions_drops_415_info_page_when_l_remove() -> None:
    doc = fitz.open()
    action = doc.new_page()
    action.insert_text((54, 80), "Annual Valuation Report", fontsize=16, fontname="hebo")
    action.insert_text((54, 180), "ACTION REQUIRED", fontsize=11, fontname="hebo")
    action.insert_text(
        (54, 210),
        "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME",
        fontsize=11,
        fontname="hebo",
        color=(0, 0.45, 0.15),
    )
    notice = doc.new_page()
    notice.insert_textbox(fitz.Rect(54, 54, 540, 700), NOTICE, fontsize=11)
    recap = doc.new_page()
    recap.insert_text((54, 80), "Year End Recap", fontsize=14, fontname="hebo")
    recap.insert_text((54, 120), "Important Information", fontsize=12)

    apply_decisions(
        doc,
        [RuleDecision(rule_id="L", section="415", action="remove", reason="415 passed")],
        "401k",
    )

    texts = [(page.get_text("text") or "") for page in doc]
    assert not any(_is_415_failure_info_page(text) for text in texts)
    assert any(re_search_recap(text) for text in texts)


def re_search_recap(text: str) -> bool:
    import re

    return bool(re.search(r"year[- ]end recap", text or "", re.I))


def test_drop_415_pages_when_fail_415_not_true() -> None:
    from services.pdf_modifier import drop_415_failure_pages_unless_failed

    doc = fitz.open()
    page = doc.new_page()
    # Wrapped title like client packages often produce.
    page.insert_text((54, 72), "Annual Additions (IRC 415)", fontsize=12, fontname="hebo")
    page.insert_text((54, 88), "Test Failure Information", fontsize=12, fontname="hebo")
    page.insert_text((54, 120), "Body of the notice stays on this page.", fontsize=10)
    recap = doc.new_page()
    recap.insert_text((54, 80), "Year End Recap", fontsize=14, fontname="hebo")

    notes = drop_415_failure_pages_unless_failed(doc, fail_415=False)
    assert notes
    assert doc.page_count == 1
    assert "Year End Recap" in (doc[0].get_text("text") or "")
    assert drop_415_failure_pages_unless_failed(doc, fail_415=True) == []

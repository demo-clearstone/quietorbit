from __future__ import annotations

import fitz

from models.review import RuleDecision
from services.pdf_modifier import _recap_bullets_have_marks, apply_recap_bullets


_FIRST = (
    "Based on the definition of Highly Compensated Employee (HCE), the plan had Highly Compensated Employees "
    "for the plan year ending December 31, 2024, however, no employee will be considered highly compensated for "
    "the plan year beginning January 1, 2025. Please communicate to affected employees."
)
_SECOND = (
    "Your plan is designed to allow participants who were age 50 or older to make catch-up contributions. "
    "The 2025 limit was an amount up to $7,500. Please see the appropriate compliance test for any participants "
    "who took advantage of this provision during the plan year. For 2026, the catch-up contribution is an amount up "
    "to $8,000 for any participant who is or will be 50 or older at any time during the plan year."
)


def _recap(bullets: bool) -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((239, 34), "YEAR END RECAP", fontsize=10)
    page.insert_text((213, 55), "January 1, 2024 - December 31, 2024", fontsize=9)
    page.insert_text((184, 67), "EXAMPLE 401(k) PLAN", fontsize=9)
    page.insert_text((281, 82), "800001", fontsize=9)
    page.insert_text((54, 111), "Important Information", fontsize=10, fontname="hebo")
    marker = "·  " if bullets else ""
    page.insert_textbox(fitz.Rect(50, 124, 545, 240), marker + _FIRST, fontsize=8)
    page.insert_textbox(fitz.Rect(50, 250, 545, 380), marker + _SECOND, fontsize=8)
    return doc


def test_recap_rebuild_restores_bullets_and_hanging_indent_when_missing() -> None:
    doc = _recap(bullets=False)
    assert not _recap_bullets_have_marks(doc[0])

    apply_recap_bullets(doc, [])

    page = doc[0]
    text = page.get_text("text")
    assert "•" in text or "·" in text
    assert "Based on the definition of Highly Compensated Employee" in text
    assert "Your plan is designed to allow participants" in text
    assert _recap_bullets_have_marks(page)


def test_recap_with_existing_bullets_is_not_rebuilt_or_changed() -> None:
    doc = _recap(bullets=True)
    before = doc[0].get_text("text")
    assert _recap_bullets_have_marks(doc[0])

    apply_recap_bullets(doc, [])

    assert doc[0].get_text("text") == before


def test_recap_rebuild_preserves_only_bullets_selected_by_keep_remove_rules() -> None:
    doc = _recap(bullets=False)
    decisions = [
        RuleDecision(rule_id="Y5", section="Year End Recap, HCE this year but not next year", action="remove", reason="No future HCEs"),
        RuleDecision(rule_id="Y6", section="Year End Recap, age 50 catch-up", action="keep", reason="Retain applicable catch-up paragraph"),
    ]

    apply_recap_bullets(doc, decisions, "401k")

    text = doc[0].get_text("text")
    assert "no employee will be considered highly compensated" not in text
    assert "Your plan is designed to allow participants" in text
    assert _recap_bullets_have_marks(doc[0])

from __future__ import annotations

import fitz

from models.review import RuleDecision
from services.pdf_modifier import apply_decisions


def _page(lines: list[tuple[float, str, float]]) -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page()
    for y, text, x in lines:
        page.insert_text((x, y), text, fontsize=9)
    return doc


def _decisions(keep: set[str]) -> list[RuleDecision]:
    return [
        RuleDecision(rule_id=rule, section=rule, action="keep" if rule in keep else "remove", reason="")
        for rule in ("A", "B", "ES")
    ]


def test_heading_words_wrapped_inside_a_kept_paragraph_do_not_cut_it():
    doc = _page(
        [
            (100, "IMMEDIATE ACTION REQUIRED - COMPLIANCE TEST FAILURE", 54),
            (120, "Contribution refunds are required. Review the Excess Summary", 72),
            (132, "Report provided in this package for details.", 72),
            (160, "IMMEDIATE ACTION REQUIRED - ADP/ACP TEST FAILURE", 54),
            (180, "Contribution refunds to participants are required.", 72),
        ]
    )
    apply_decisions(doc, _decisions({"A"}), "401k")
    text = doc[0].get_text("text")
    assert "Report provided in this package" in text
    assert "ADP/ACP TEST FAILURE" not in text

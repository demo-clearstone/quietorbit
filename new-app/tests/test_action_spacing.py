from __future__ import annotations

import fitz

from models.review import RuleDecision
from services.pdf_modifier import apply_decisions, _restack_pages, _top_header_rule_y


def _text_top(page: fitz.Page, text: str) -> float:
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            if "".join(span["text"] for span in line["spans"]).strip() == text:
                return line["bbox"][1]
    raise AssertionError(f"text not found: {text}")


def test_action_text_is_not_pulled_into_header_divider() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((54, 80), "Annual Valuation Report", fontsize=16)
    page.insert_text((54, 105), "Plan Year: Jan-Dec", fontsize=11)
    page.insert_text((54, 130), "555001", fontsize=11)
    page.draw_line(fitz.Point(48, 150), fitz.Point(page.rect.width - 48, 150), width=1)
    page.insert_text((54, 172), "IMMEDIATE ACTION REQUIRED", fontsize=11, fontname="hebo")
    page.insert_text((54, 192), "First action paragraph", fontsize=10)
    rule_y = _top_header_rule_y(page)
    assert rule_y == 150

    _restack_pages(doc, {0: [fitz.Rect(18, 110, page.rect.width - 28, 170)]})

    assert _text_top(page, "IMMEDIATE ACTION REQUIRED") >= rule_y + 30
    assert _text_top(page, "First action paragraph") >= rule_y + 30
    assert page.get_text().count("IMMEDIATE ACTION REQUIRED") == 1


def test_restack_collapses_middle_removal_without_leaving_large_gap() -> None:
    """A mid-page removal must pull later kept blocks up by the removed height.

    Previously max_upshift capped every block by the first post-header gap, so
    KEEP HEADING TWO barely moved and left a large white hole.
    """
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((54, 80), "Annual Valuation Report", fontsize=16, fontname="hebo")
    page.insert_text((54, 100), "Plan Year End: 12/31/2025", fontsize=11)
    page.insert_text((54, 120), "555001", fontsize=11)
    page.draw_line(fitz.Point(48, 140), fitz.Point(page.rect.width - 48, 140), width=1)
    page.insert_text((54, 180), "KEEP HEADING ONE", fontsize=11, fontname="hebo")
    page.insert_text((54, 200), "Keep body one.", fontsize=10)
    page.insert_text((54, 220), "REMOVE HEADING", fontsize=11, fontname="hebo")
    page.insert_text((54, 240), "Remove body.", fontsize=10)
    page.insert_text((54, 270), "KEEP HEADING TWO", fontsize=11, fontname="hebo")
    page.insert_text((54, 290), "Keep body two.", fontsize=10)

    removed = fitz.Rect(18, 210, page.rect.width - 28, 255)
    before_two = _text_top(page, "KEEP HEADING TWO")
    page.add_redact_annot(removed, fill=(1, 1, 1))
    page.apply_redactions(images=0)
    _restack_pages(doc, {0: [removed]})

    keep_one_bottom = _text_top(page, "Keep body one.") + 12
    keep_two_top = _text_top(page, "KEEP HEADING TWO")
    assert keep_two_top < before_two - 30
    assert keep_two_top - keep_one_bottom < 40
    assert "REMOVE HEADING" not in page.get_text()


def test_apply_decisions_packs_no_immediate_under_action_heading() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((54, 80), "Annual Valuation Report", fontsize=16, fontname="hebo")
    page.insert_text((54, 100), "Plan Year End: 12/31/2025", fontsize=11)
    page.insert_text((54, 120), "555001", fontsize=11)
    page.draw_line(fitz.Point(48, 140), fitz.Point(page.rect.width - 48, 140), width=1)
    page.insert_text((54, 180), "IMMEDIATE ACTION REQUIRED - ADP/ACP TEST FAILURE", fontsize=11, fontname="hebo")
    page.insert_text(
        (54, 200),
        "Contribution refunds to participants are required to correct ADP/ACP testing failures.",
        fontsize=10,
    )
    page.insert_text((54, 280), "IMMEDIATE ACTION REQUIRED - COMPLIANCE TEST FAILURE", fontsize=11, fontname="hebo")
    page.insert_text(
        (54, 300),
        "Contribution refunds to participants are required to correct compliance testing failures.",
        fontsize=10,
    )
    page.insert_text(
        (54, 420),
        "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME",
        fontsize=11,
        fontname="hebo",
        color=(0, 0.45, 0.15),
    )

    apply_decisions(
        doc,
        [
            RuleDecision(rule_id="A", section="x", action="remove", reason="r"),
            RuleDecision(rule_id="B", section="x", action="remove", reason="r"),
            RuleDecision(rule_id="G", section="x", action="keep", reason="r"),
        ],
        "401k",
    )

    page = doc[0]
    rule_y = _top_header_rule_y(page)
    assert rule_y is not None
    action_y = _text_top(page, "ACTION REQUIRED")
    green_y = _text_top(page, "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME")
    assert action_y - rule_y < 55
    assert 15 < green_y - action_y < 45
    assert "IMMEDIATE ACTION REQUIRED" not in page.get_text()

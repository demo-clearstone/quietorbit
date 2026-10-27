from __future__ import annotations

import fitz

from services.pdf_modifier import _restack_pages, _top_header_rule_y


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

from __future__ import annotations

import fitz

from services.pdf_modifier import _redraw_action_rules


def _underline_count(page: fitz.Page) -> int:
    count = 0
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if item and item[0] == "l":
                start, end = fitz.Point(item[1]), fitz.Point(item[2])
                if abs(start.y - end.y) < 1:
                    count += 1
    return count


def test_action_heading_rule_is_not_duplicated_when_source_line_exists() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((54, 100), "ACTION REQUIRED", fontsize=11, fontname="hebo")
    page.draw_line(fitz.Point(54, 102), fitz.Point(160, 102), width=0.8)
    before = _underline_count(page)

    _redraw_action_rules(page)

    assert _underline_count(page) == before


def test_action_heading_rule_is_drawn_when_source_line_is_missing() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((54, 100), "ACTION REQUIRED", fontsize=11, fontname="hebo")

    _redraw_action_rules(page)

    assert _underline_count(page) == 1


def test_plan_number_does_not_add_duplicate_header_divider() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((180, 75), "Annual Valuation Report", fontsize=14, fontname="hebo")
    page.insert_text((180, 95), "January 1, 2024 - December 31, 2024", fontsize=10)
    page.insert_text((160, 112), "P.H. MECHANICAL CORPORATION 401(k) PLAN AND TRUST", fontsize=10, fontname="hebo")
    page.insert_text((54, 130), "801080", fontsize=11, fontname="hebo")
    page.draw_line(fitz.Point(48, 150), fitz.Point(page.rect.width - 48, 150), width=1)
    page.insert_text((54, 190), "ACTION REQUIRED", fontsize=11, fontname="hebo")
    page.draw_line(fitz.Point(54, 192), fitz.Point(160, 192), width=0.8)

    _redraw_action_rules(page)

    lines = [
        (fitz.Point(item[1]), fitz.Point(item[2]))
        for drawing in page.get_drawings()
        for item in drawing.get("items", [])
        if item and item[0] == "l" and abs(fitz.Point(item[1]).y - fitz.Point(item[2]).y) < 1
    ]
    full_width = [line for line in lines if line[1].x - line[0].x > page.rect.width * 0.7]
    heading_underlines = [line for line in lines if line[1].x - line[0].x < page.rect.width * 0.7]
    assert len(full_width) == 1
    assert len(heading_underlines) == 1

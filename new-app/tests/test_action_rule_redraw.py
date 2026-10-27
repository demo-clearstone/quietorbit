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

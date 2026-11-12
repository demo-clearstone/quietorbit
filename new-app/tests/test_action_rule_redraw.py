from __future__ import annotations

import fitz

from services.pdf_modifier import _redraw_action_rules, _strip_im_fragments


def _underline_spans(page: fitz.Page) -> list[tuple[float, float, float]]:
    spans: list[tuple[float, float, float]] = []
    for drawing in page.get_drawings():
        if drawing.get("color") in {(1, 1, 1), (1.0, 1.0, 1.0)}:
            continue
        for item in drawing.get("items", []):
            if not item or item[0] != "l":
                continue
            start, end = fitz.Point(item[1]), fitz.Point(item[2])
            if abs(start.y - end.y) >= 1:
                continue
            left, right = sorted((start.x, end.x))
            spans.append((left, right, start.y))
    return spans


def _underline_count(page: fitz.Page) -> int:
    return len(_underline_spans(page))


def test_action_heading_rule_replaces_wrong_length_source_line() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((54, 100), "ACTION REQUIRED", fontsize=11, fontname="hebo")
    # Existing underline is intentionally too long.
    page.draw_line(fitz.Point(54, 105), fitz.Point(260, 105), width=0.8)

    _redraw_action_rules(page)

    spans = [span for span in _underline_spans(page) if span[1] - span[0] < page.rect.width * 0.7]
    # New phrase-width underline must be present (old overlong stroke may remain under white cover).
    assert any(abs(left - 54) <= 1 and 95 <= right - left <= 120 for left, right, _y in spans)


def test_action_heading_rule_is_drawn_when_source_line_is_missing() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((54, 100), "ACTION REQUIRED", fontsize=11, fontname="hebo")

    _redraw_action_rules(page)

    assert _underline_count(page) == 1


def test_green_no_action_underline_matches_full_phrase_width() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 180), "ACTION REQUIRED", fontsize=11, fontname="hebo")
    page.insert_text(
        (40, 210),
        "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME",
        fontsize=11,
        fontname="hebo",
        color=(0, 0.45, 0.15),
    )
    # Short leftover underline that used to stop after "AT".
    page.draw_line(fitz.Point(40, 214), fitz.Point(220, 214), width=0.8)

    _redraw_action_rules(page)

    green = [
        span
        for span in _underline_spans(page)
        if span[1] - span[0] < page.rect.width * 0.7 and span[2] > 200
    ]
    # Full phrase-width underline must be drawn (short leftover may remain under white cover).
    assert any(abs(left - 40) <= 1 and right - left >= 270 for left, right, _y in green)


def test_plan_number_does_not_add_duplicate_header_divider() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((180, 75), "Annual Valuation Report", fontsize=14, fontname="hebo")
    page.insert_text((180, 95), "January 1, 2024 - December 31, 2024", fontsize=10)
    page.insert_text((160, 112), "P.H. MECHANICAL CORPORATION 401(k) PLAN AND TRUST", fontsize=10, fontname="hebo")
    page.insert_text((54, 130), "801080", fontsize=11, fontname="hebo")
    page.draw_line(fitz.Point(48, 150), fitz.Point(page.rect.width - 48, 150), width=1)
    page.insert_text((54, 190), "ACTION REQUIRED", fontsize=11, fontname="hebo")
    page.draw_line(fitz.Point(54, 195), fitz.Point(160, 195), width=0.8)

    _redraw_action_rules(page)

    lines = [
        (fitz.Point(item[1]), fitz.Point(item[2]))
        for drawing in page.get_drawings()
        if drawing.get("color") not in {(1, 1, 1), (1.0, 1.0, 1.0)}
        for item in drawing.get("items", [])
        if item and item[0] == "l" and abs(fitz.Point(item[1]).y - fitz.Point(item[2]).y) < 1
    ]
    full_width = [line for line in lines if line[1].x - line[0].x > page.rect.width * 0.7]
    heading_underlines = [line for line in lines if line[1].x - line[0].x < page.rect.width * 0.7]
    assert len(full_width) == 1
    # Phrase-width ACTION underline present; do not invent a second header divider.
    assert any(95 <= abs(line[1].x - line[0].x) <= 120 for line in heading_underlines)


def test_strip_im_fragments_removes_lone_i() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((200, 160), "I", fontsize=11, fontname="hebo")
    page.insert_text((54, 190), "ACTION REQUIRED", fontsize=11, fontname="hebo")
    _strip_im_fragments(doc)
    assert "I" not in page.get_text().split()
    assert "ACTION REQUIRED" in page.get_text()

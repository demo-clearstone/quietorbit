from __future__ import annotations

import fitz

from services.pdf_modifier import _finalize_no_immediate_pages


def _short_rules(page: fitz.Page) -> list[tuple[float, float, float, tuple]]:
    rules = []
    for drawing in page.get_drawings():
        color = drawing.get("color")
        if color in {(1, 1, 1), (1.0, 1.0, 1.0)}:
            continue
        for item in drawing.get("items") or []:
            if not item or item[0] != "l" or len(item) < 3:
                continue
            start, end = fitz.Point(item[1]), fitz.Point(item[2])
            if abs(start.y - end.y) > 1.5:
                continue
            width = abs(end.x - start.x)
            if width >= page.rect.width * 0.7:
                continue
            left, right = sorted((start.x, end.x))
            rules.append((round(start.y, 1), round(left, 1), round(right, 1), color))
    return rules


def test_no_immediate_page_gets_action_required_heading_without_eating_green() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((200, 60), "Annual Valuation Report", fontsize=16, fontname="hebo")
    page.insert_text((200, 80), "January 1, 2025 - December 31, 2025", fontsize=11)
    page.insert_text((180, 100), "GRACE MEDICAL HOME, INC. 403(B) PLAN", fontsize=12, fontname="hebo")
    page.insert_text((270, 120), "555403", fontsize=12, fontname="hebo")
    page.draw_line(fitz.Point(48, 130), fitz.Point(page.rect.width - 48, 130), width=1)
    # Leftover underline from a removed ACTION REQUIRED heading (cuts through text).
    page.draw_line(fitz.Point(54, 161), fitz.Point(157.3, 161), color=(0, 0, 0), width=0.8)
    page.insert_text(
        (54, 163.5),
        "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME",
        fontsize=11,
        fontname="hebo",
        color=(0, 0.45, 0.15),
    )

    _finalize_no_immediate_pages(doc)

    text = page.get_text("text") or ""
    assert "ACTION REQUIRED" in text
    assert "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME" in text
    # Must not leave a truncated green line like "ION IS REQUIRED…".
    assert "ION IS REQUIRED" not in text.replace("NO IMMEDIATE ACTION IS REQUIRED", "")

    action_box = None
    green_box = None
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            line_text = "".join(span["text"] for span in line["spans"]).strip()
            if line_text == "ACTION REQUIRED":
                action_box = line["bbox"]
            if line_text == "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME":
                green_box = line["bbox"]
    assert action_box is not None and green_box is not None
    # Visual order matters; insert_text may append after green in the content stream.
    assert action_box[1] < green_box[1]

    # Kaagaz p2: ACTION (black) and green line both underlined to phrase width.
    shorts = _short_rules(page)
    assert any(action_box[3] <= y <= action_box[3] + 6 and 95 <= right - left <= 120 for y, left, right, _ in shorts)
    assert any(
        green_box[3] <= y <= green_box[3] + 6 and right - left >= 250 for y, left, right, color in shorts
    )


def test_finalize_keeps_single_action_heading_with_both_underlines() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((200, 60), "Annual Valuation Report", fontsize=16, fontname="hebo")
    page.insert_text((200, 80), "January 1, 2025 - December 31, 2025", fontsize=11)
    page.insert_text((180, 100), "HARBOR MANUFACTURING 401(K) PLAN", fontsize=12, fontname="hebo")
    page.insert_text((270, 120), "555001", fontsize=12, fontname="hebo")
    page.draw_line(fitz.Point(48, 130), fitz.Point(page.rect.width - 48, 130), width=1)
    page.insert_text((54, 160), "ACTION REQUIRED", fontsize=11, fontname="hebo")
    page.insert_text(
        (54, 190),
        "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME",
        fontsize=11,
        fontname="hebo",
        color=(0, 0.45, 0.15),
    )

    _finalize_no_immediate_pages(doc)

    assert page.get_text().count("ACTION REQUIRED") == 1
    shorts = _short_rules(page)
    assert len(shorts) >= 2
    widths = sorted(right - left for _y, left, right, _c in shorts)
    assert any(95 <= w <= 120 for w in widths)
    assert any(w >= 250 for w in widths)

from __future__ import annotations

import fitz

from services.pdf_modifier import _finalize_no_immediate_pages, _redraw_action_rules


def test_no_immediate_page_gets_action_required_heading_and_clean_underline() -> None:
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
    _redraw_action_rules(page)

    text = page.get_text("text") or ""
    assert "ACTION REQUIRED" in text
    assert "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME" in text
    assert text.index("ACTION REQUIRED") < text.index("NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME")

    boxes = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            line_text = "".join(span["text"] for span in line["spans"]).strip()
            if line_text in {"ACTION REQUIRED", "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME"}:
                boxes.append(line["bbox"])

    for drawing in page.get_drawings():
        if drawing.get("color") in {(1, 1, 1), (1.0, 1.0, 1.0)}:
            continue
        for item in drawing.get("items", []):
            if not item or item[0] != "l":
                continue
            start, end = fitz.Point(item[1]), fitz.Point(item[2])
            if abs(start.y - end.y) > 1 or abs(end.x - start.x) > page.rect.width * 0.7:
                continue
            for box in boxes:
                assert not (box[1] < start.y < box[3] - 0.5)

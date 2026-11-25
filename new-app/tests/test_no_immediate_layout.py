from __future__ import annotations

import fitz

from services.pdf_modifier import _finalize_no_immediate_pages


def _short_rules(page: fitz.Page) -> list[tuple[float, float, float, tuple]]:
    rules = []
    white = {(1, 1, 1), (1.0, 1.0, 1.0)}
    for drawing in page.get_drawings():
        stroke = drawing.get("color")
        fill = drawing.get("fill")
        for item in drawing.get("items") or []:
            if not item:
                continue
            if item[0] == "l" and len(item) >= 3:
                if stroke in white:
                    continue
                start, end = fitz.Point(item[1]), fitz.Point(item[2])
                if abs(start.y - end.y) > 1.5:
                    continue
                width = abs(end.x - start.x)
                if width >= page.rect.width * 0.7:
                    continue
                left, right = sorted((start.x, end.x))
                rules.append((round(start.y, 1), round(left, 1), round(right, 1), stroke))
            elif item[0] == "re" and len(item) >= 2:
                if fill in white or fill is None:
                    continue
                rect = fitz.Rect(item[1])
                if rect.height > 3.5 or rect.width >= page.rect.width * 0.7:
                    continue
                rules.append(
                    (round((rect.y0 + rect.y1) / 2.0, 1), round(rect.x0, 1), round(rect.x1, 1), fill)
                )
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
    # Must not duplicate the green phrase.
    assert text.upper().count("NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME") == 1

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
    assert abs(action_box[0] - green_box[0]) < 2.0


def test_finalize_draws_underlines_on_all_clear_pages() -> None:
    """All-clear pages keep OPS filled bars under ACTION and NO IMMEDIATE."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((200, 60), "Annual Valuation Report", fontsize=16, fontname="hebo")
    page.insert_text((200, 80), "January 1, 2025 - December 31, 2025", fontsize=11)
    page.insert_text((180, 100), "HARBOR MANUFACTURING 401(K) PLAN", fontsize=12, fontname="hebo")
    page.insert_text((270, 120), "555001", fontsize=12, fontname="hebo")
    page.draw_line(fitz.Point(48, 130), fitz.Point(page.rect.width - 48, 130), width=1)
    page.insert_text((38, 160), "ACTION REQUIRED", fontsize=11, fontname="hebo")
    page.insert_text(
        (38, 190),
        "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME",
        fontsize=11,
        fontname="hebo",
        color=(0, 0.45, 0.15),
    )

    _finalize_no_immediate_pages(doc)

    assert page.get_text().count("ACTION REQUIRED") == 1
    assert page.get_text().upper().count("NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME") == 1
    shorts = _short_rules(page)
    widths = sorted(right - left for _y, left, right, _c in shorts)
    assert any(95 <= w <= 120 for w in widths)
    assert any(w >= 250 for w in widths)


def test_finalize_restores_source_underlines_when_present() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((200, 60), "Annual Valuation Report", fontsize=16, fontname="hebo")
    page.insert_text((200, 80), "January 1, 2025 - December 31, 2025", fontsize=11)
    page.insert_text((180, 100), "HARBOR MANUFACTURING 401(K) PLAN", fontsize=12, fontname="hebo")
    page.insert_text((270, 120), "555001", fontsize=12, fontname="hebo")
    page.draw_line(fitz.Point(48, 130), fitz.Point(page.rect.width - 48, 130), width=1)
    page.insert_text((54, 160), "ACTION REQUIRED", fontsize=11, fontname="hebo")
    # OPS-style filled underline bar under ACTION.
    page.draw_rect(fitz.Rect(54, 163, 157, 164.4), color=(0, 0, 0), fill=(0, 0, 0), width=0)
    page.insert_text(
        (54, 190),
        "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME",
        fontsize=11,
        fontname="hebo",
        color=(0, 0.45, 0.15),
    )
    page.draw_rect(fitz.Rect(54, 193, 320, 194), color=(0, 0.45, 0.15), fill=(0, 0.45, 0.15), width=0)

    _finalize_no_immediate_pages(doc)

    shorts = _short_rules(page)
    widths = sorted(right - left for _y, left, right, _c in shorts)
    assert any(95 <= w <= 120 for w in widths)
    assert any(w >= 250 for w in widths)


def test_finalize_detects_filled_rect_action_underline_from_source_pkg() -> None:
    """Valuation Pkg uses filled rect underlines — finalize must restore both phrases."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((200, 60), "Annual Valuation Report", fontsize=16, fontname="hebo")
    page.insert_text((200, 80), "July 1, 2025 - June 30, 2026", fontsize=11)
    page.insert_text((180, 100), "TEST PLAN 403(B)", fontsize=12, fontname="hebo")
    page.insert_text((270, 120), "800643", fontsize=12, fontname="hebo")
    page.draw_line(fitz.Point(36, 130), fitz.Point(page.rect.width - 30, 130), width=1)
    page.insert_text((36, 155), "ACTION REQUIRED", fontsize=14, fontname="hebo")
    page.draw_rect(fitz.Rect(36, 155.0, 170.25, 156.5), color=(0, 0, 0), fill=(0, 0, 0), width=0)
    page.insert_text(
        (36, 185),
        "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME",
        fontsize=10,
        fontname="hebo",
        color=(0, 0.45, 0.15),
    )

    _finalize_no_immediate_pages(doc)

    shorts = _short_rules(page)
    assert len(shorts) >= 2
    assert any(95 <= right - left <= 140 for _y, left, right, _c in shorts)
    assert any(right - left >= 220 for _y, left, right, _c in shorts)


def test_no_immediate_line_left_aligns_with_action_required() -> None:
    """Green NO IMMEDIATE line must share ACTION REQUIRED's left edge."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((200, 60), "Annual Valuation Report", fontsize=16, fontname="hebo")
    page.insert_text((200, 80), "January 1, 2025 - December 31, 2025", fontsize=11)
    page.insert_text((180, 100), "TEST PLAN 401(K)", fontsize=12, fontname="hebo")
    page.insert_text((270, 120), "555001", fontsize=12, fontname="hebo")
    page.draw_line(fitz.Point(48, 130), fitz.Point(page.rect.width - 48, 130), width=1)
    page.insert_text((38, 160), "ACTION REQUIRED", fontsize=11, fontname="hebo")
    # Intentionally indented too far right (post-pack drift).
    page.insert_text(
        (120, 190),
        "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME",
        fontsize=11,
        fontname="hebo",
        color=(0, 0.45, 0.15),
    )

    _finalize_no_immediate_pages(doc)

    action_x = green_x = None
    green_count = 0
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            line_text = "".join(span["text"] for span in line["spans"]).strip()
            if line_text == "ACTION REQUIRED":
                action_x = line["bbox"][0]
            if line_text == "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME":
                green_x = line["bbox"][0]
                green_count += 1
    assert action_x is not None and green_x is not None
    assert green_count == 1
    assert abs(action_x - green_x) < 2.0
    assert green_x < 70


def test_finalize_insets_action_column_from_header_rule() -> None:
    """When source ACTION sits flush on the AV header rule, nudge to OPS inset (~38)."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((200, 60), "Annual Valuation Report", fontsize=16, fontname="hebo")
    page.insert_text((200, 80), "January 1, 2025 - December 31, 2025", fontsize=11)
    page.insert_text((180, 100), "TEST PLAN 401(K)", fontsize=12, fontname="hebo")
    page.insert_text((270, 120), "555001", fontsize=12, fontname="hebo")
    # Full-width header rule at x0=36 (same as source Valuation Pkg).
    page.draw_line(fitz.Point(36, 130), fitz.Point(page.rect.width - 30, 130), width=1)
    page.insert_text((36, 160), "ACTION REQUIRED", fontsize=11, fontname="hebo")
    page.insert_text(
        (36, 190),
        "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME",
        fontsize=11,
        fontname="hebo",
        color=(0, 0.45, 0.15),
    )

    _finalize_no_immediate_pages(doc)

    action_x = green_x = None
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            line_text = "".join(span["text"] for span in line["spans"]).strip()
            if line_text == "ACTION REQUIRED":
                action_x = line["bbox"][0]
            if line_text == "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME":
                green_x = line["bbox"][0]
    assert action_x is not None and green_x is not None
    assert abs(action_x - 38.0) < 1.0
    assert abs(green_x - action_x) < 1.0

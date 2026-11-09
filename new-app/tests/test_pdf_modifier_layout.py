from __future__ import annotations

import fitz

from services.pdf_modifier import _restack_pages


def _line(page: fitz.Page, text: str) -> tuple[float, float, str, float]:
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            content = "".join(span["text"] for span in spans).strip()
            if content == text:
                return line["bbox"][0], line["bbox"][3], spans[0]["font"], spans[0]["size"]
    raise AssertionError(f"line not found: {text}")


def test_restack_collapses_removed_gap_and_preserves_source_alignment_and_style() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((55, 70), "Header", fontsize=11, fontname="hebo")
    page.insert_text((55, 125), "First paragraph", fontsize=10, fontname="helv")
    page.insert_text((220, 175), "Right aligned item", fontsize=9, fontname="hebo")
    page.insert_text((55, 225), "Next paragraph", fontsize=10, fontname="heit")
    page.draw_line(fitz.Point(50, 300), fitz.Point(550, 300), color=(0, 0, 0), width=1)
    before = {text: _line(page, text) for text in ("Header", "First paragraph", "Right aligned item", "Next paragraph")}

    _restack_pages(doc, {0: [fitz.Rect(20, 140, 580, 160)]})

    after = {text: _line(page, text) for text in before}
    assert after["Header"] == before["Header"]
    assert after["First paragraph"] == before["First paragraph"]
    assert after["Right aligned item"][0] == before["Right aligned item"][0]
    assert after["Right aligned item"][2:] == before["Right aligned item"][2:]
    assert after["Right aligned item"][1] == before["Right aligned item"][1] - 20
    assert after["Next paragraph"][0] == before["Next paragraph"][0]
    assert after["Next paragraph"][2:] == before["Next paragraph"][2:]
    assert after["Next paragraph"][1] == before["Next paragraph"][1] - 20
    assert any(abs(drawing["rect"].y0 - 300) < 1 and drawing["rect"].width > 450 for drawing in page.get_drawings())

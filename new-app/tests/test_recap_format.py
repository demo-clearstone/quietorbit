from __future__ import annotations

import fitz

from models.review import RuleDecision
from services.pdf_modifier import (
    _recap_bullets_have_marks,
    _recap_has_header_rule,
    _split_recap,
    apply_recap_bullets,
)


_FIRST = (
    "Based on the definition of Highly Compensated Employee (HCE), the plan had Highly Compensated Employees "
    "for the plan year ending December 31, 2024, however, no employee will be considered highly compensated for "
    "the plan year beginning January 1, 2025. Please communicate to affected employees."
)
_SECOND = (
    "Your plan is designed to allow participants who were age 50 or older to make catch-up contributions. "
    "The 2025 limit was an amount up to $7,500. Please see the appropriate compliance test for any participants "
    "who took advantage of this provision during the plan year. For 2026, the catch-up contribution is an amount up "
    "to $8,000 for any participant who is or will be 50 or older at any time during the plan year."
)
_MATCH = (
    "The plan's employer match contribution is calculated on a participant's compensation earned for each payroll "
    "period. We recommend reviewing your payroll records to determine if the plan's match formula was applied correctly."
)


def _recap(bullets: bool, *, moa_header: bool = False, include_match: bool = False) -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page()
    if moa_header:
        page.insert_text((239, 48), "YEAR END RECAP", fontsize=13, fontname="hebo")
        page.insert_text((214, 66), "January 1, 2024 - December 31, 2024", fontsize=10)
        page.insert_text((150, 79), "P.H. MECHANICAL CORPORATION 401(k) PLAN AND TRUST", fontsize=11, fontname="hebo")
        page.insert_text((280, 93), "801080", fontsize=10)
        page.draw_line(fitz.Point(54, 109), fitz.Point(page.rect.width - 54, 109), color=(0, 0, 0), width=0.8)
        page.insert_text((54, 123), "Important Information", fontsize=11, fontname="hebo")
    else:
        page.insert_text((239, 34), "YEAR END RECAP", fontsize=10.5, fontname="hebo")
        page.insert_text((213, 55), "January 1, 2024 - December 31, 2024", fontsize=9.9)
        page.insert_text((184, 67), "EXAMPLE 401(k) PLAN", fontsize=9.9)
        page.insert_text((281, 82), "800001", fontsize=9.9)
        page.insert_text((42, 111), "Important Information", fontsize=9.6, fontname="hebo")
    paragraphs = [_FIRST, _SECOND]
    if include_match:
        paragraphs.append(_MATCH)
    for y, paragraph in zip((141, 197, 280), paragraphs):
        if bullets:
            diameter = 3.6
            cy = y - 8 * 0.35
            page.draw_oval(
                fitz.Rect(54, cy - diameter / 2, 54 + diameter, cy + diameter / 2),
                color=(0, 0, 0),
                fill=(0, 0, 0),
                width=0.7,
            )
            page.insert_text((54 + diameter + 4.5, y), paragraph, fontsize=8)
        else:
            # Offset body with no marker so layout is treated as needing a rebuild.
            page.insert_textbox(fitz.Rect(90, y - 10, 545, y + 42), paragraph, fontsize=8)
    return doc


def _header_rules(page: fitz.Page) -> list[tuple[float, float, float]]:
    rules = []
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if not item or item[0] != "l" or len(item) < 3:
                continue
            start, end = fitz.Point(item[1]), fitz.Point(item[2])
            if abs(start.y - end.y) > 1.5:
                continue
            left, right = sorted((start.x, end.x))
            if right - left < 200:
                continue
            rules.append((round((start.y + end.y) / 2, 1), round(left, 1), round(right, 1)))
    return rules


def test_recap_rebuild_restores_bullets_and_hanging_indent_when_missing() -> None:
    doc = _recap(bullets=False)
    assert not _recap_bullets_have_marks(doc[0])

    apply_recap_bullets(doc, [])

    page = doc[0]
    text = page.get_text("text")
    assert "Based on the definition of Highly Compensated Employee" in text
    assert "Your plan is designed to allow participants" in text
    assert _recap_bullets_have_marks(page)
    assert _recap_has_header_rule(page)
    discs = [
        drawing
        for drawing in page.get_drawings()
        if drawing.get("fill") in {(0, 0, 0), (0.0, 0.0, 0.0)}
        and 2.5 <= float((drawing.get("rect") or fitz.Rect()).width) <= 6
    ]
    assert len(discs) >= 2
    paragraphs = [
        (line, "".join(span.get("text", "") for span in line.get("spans", [])).strip())
        for block in page.get_text("dict")["blocks"] if block.get("type") == 0
        for line in block.get("lines", [])
    ]
    first_line, first_text = next(
        (line, text)
        for line, text in paragraphs
        if "Based on the definition" in text
    )
    assert 54 <= round(first_line["bbox"][0]) <= 68
    assert "Based on the definition" in first_text


def test_recap_with_existing_bullets_is_not_rebuilt_or_changed() -> None:
    doc = _recap(bullets=True, moa_header=True)
    before = doc[0].get_text("text")
    assert _recap_bullets_have_marks(doc[0])
    assert _recap_has_header_rule(doc[0])

    apply_recap_bullets(doc, [])

    assert doc[0].get_text("text") == before


def test_recap_rebuilds_to_kaagaz_header_layout_with_border() -> None:
    doc = _recap(bullets=True, moa_header=False)
    before = doc[0].get_text("text")

    apply_recap_bullets(doc, [])

    page = doc[0]
    assert page.get_text("text") != before
    title = next(
        span
        for block in page.get_text("dict")["blocks"] if block.get("type") == 0
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip().upper() == "YEAR END RECAP"
    )
    important = next(
        (line, span)
        for block in page.get_text("dict")["blocks"] if block.get("type") == 0
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip().lower() == "important information"
    )
    assert abs(float(title["size"]) - 13.0) <= 0.3
    assert round(important[0]["bbox"][0]) == 54
    assert abs(float(important[1]["size"]) - 11.0) <= 0.3
    assert _recap_bullets_have_marks(page)
    assert _recap_has_header_rule(page)
    rules = _header_rules(page)
    assert any(abs(y - 109.0) <= 1 and left <= 54 and right >= page.rect.width - 54 for y, left, right in rules)


def test_recap_rebuild_drops_match_bullet_when_rule_says_remove() -> None:
    doc = _recap(bullets=False, include_match=True)
    decisions = [
        RuleDecision(rule_id="Y8", section="Year End Recap, per-payroll match", action="remove", reason="No per-payroll match"),
        RuleDecision(rule_id="Y6", section="Year End Recap, age 50 catch-up", action="keep", reason="Retain catch-up"),
    ]

    apply_recap_bullets(doc, decisions, "401k")

    text = doc[0].get_text("text")
    assert "employer match contribution" not in text
    assert "Your plan is designed to allow participants" in text
    assert _recap_has_header_rule(doc[0])


def test_recap_packs_bullets_after_removals_without_large_gaps() -> None:
    """Kaagaz page 3 left holes after redacting; page 4 packs bullets under Important Information."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((239, 48), "YEAR END RECAP", fontsize=13, fontname="hebo")
    page.insert_text((214, 66), "January 1, 2025 - December 31, 2025", fontsize=10)
    page.insert_text((184, 79), "GRACE MEDICAL HOME, INC. 403(B) PLAN", fontsize=11, fontname="hebo")
    page.insert_text((280, 93), "555403", fontsize=10)
    page.draw_line(fitz.Point(54, 109), fitz.Point(page.rect.width - 54, 109), color=(0, 0, 0), width=0.8)
    page.insert_text((54, 123), "Important Information", fontsize=11, fontname="hebo")
    # Spread like a source page that still has the match / extra paragraphs in between.
    page.insert_text((54, 150), "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed.", fontsize=8)
    page.insert_text((54, 280), "Your plan is designed to allow participants who were age 50 or older to make catch-up contributions.", fontsize=8)
    page.insert_text((54, 410), "If you sponsor a qualified retirement plan not administered by Mutual of America, please provide.", fontsize=8)
    page.insert_text((54, 540), "The plan's employer match contribution is calculated on a participant's compensation.", fontsize=8)

    apply_recap_bullets(
        doc,
        [RuleDecision(rule_id="Y8", section="Year End Recap, per-payroll match", action="remove", reason="no")],
        "401k",
    )

    page = doc[0]
    starts = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if text.startswith("Based on the definition") or text.startswith("Your plan is designed") or text.startswith("If you sponsor"):
                starts.append(line["bbox"][1])
    starts = sorted(set(round(y) for y in starts))
    assert len(starts) >= 3
    # Packed rebuild: first bullet soon after Important Information, no 100pt holes.
    important_y = next(
        line["bbox"][3]
        for block in page.get_text("dict")["blocks"] if block.get("type") == 0
        for line in block.get("lines", [])
        if "".join(span.get("text", "") for span in line.get("spans", [])).strip().lower() == "important information"
    )
    first_bullet_y = min(starts)
    assert first_bullet_y - important_y < 40
    gaps = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
    assert max(gaps) < 90
    assert "employer match contribution" not in page.get_text("text")
    assert _recap_has_header_rule(page)


def test_recap_rebuilds_when_bullets_are_already_sparse_without_removals() -> None:
    """Even with no drop decisions, large holes between bullets must be packed."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((239, 48), "YEAR END RECAP", fontsize=13, fontname="hebo")
    page.insert_text((214, 66), "January 1, 2025 - December 31, 2025", fontsize=10)
    page.insert_text((184, 79), "SAMPLE 401(K) PLAN", fontsize=11, fontname="hebo")
    page.insert_text((280, 93), "555001", fontsize=10)
    page.draw_line(fitz.Point(54, 109), fitz.Point(page.rect.width - 54, 109), color=(0, 0, 0), width=0.8)
    page.insert_text((54, 123), "Important Information", fontsize=11, fontname="hebo")
    for y, text in (
        (150, "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed."),
        (320, "Your plan is designed to allow participants who were age 50 or older to make catch-up contributions."),
        (500, "If you sponsor a qualified retirement plan not administered by Mutual of America, please provide."),
    ):
        page.draw_oval(fitz.Rect(54, y - 5, 57.6, y - 1.4), color=(0, 0, 0), fill=(0, 0, 0))
        page.insert_text((62, y), text, fontsize=8)

    apply_recap_bullets(doc, [], "401k")

    starts = []
    for block in doc[0].get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if text.startswith("Based on the definition") or text.startswith("Your plan is designed") or text.startswith("If you sponsor"):
                starts.append(line["bbox"][1])
    starts = sorted(set(round(y) for y in starts))
    assert len(starts) == 3
    assert max(starts[i + 1] - starts[i] for i in range(len(starts) - 1)) < 40


def test_recap_rebuild_preserves_only_bullets_selected_by_keep_remove_rules() -> None:
    doc = _recap(bullets=False)
    decisions = [
        RuleDecision(rule_id="Y5", section="Year End Recap, HCE this year but not next year", action="remove", reason="No future HCEs"),
        RuleDecision(rule_id="Y6", section="Year End Recap, age 50 catch-up", action="keep", reason="Retain applicable catch-up paragraph"),
    ]

    apply_recap_bullets(doc, decisions, "401k")

    text = doc[0].get_text("text")
    assert "no employee will be considered highly compensated" not in text
    assert "Your plan is designed to allow participants" in text
    assert _recap_bullets_have_marks(doc[0])


def test_recap_parser_preserves_currency_lines_at_line_start() -> None:
    source = (
        "YEAR END RECAP\nImportant Information\n"
        "· Your plan is designed to allow participants who were age 50 or older to make catch-up contributions. "
        "The 2025 limit was an amount up to\n"
        "$7,500. Please see the appropriate compliance test.\n"
        "For 2026, the catch-up limit is $8,000.\n$11,250.\n"
    )

    _header, bullets = _split_recap(source)

    assert len(bullets) == 1
    assert "$7,500." in bullets[0]
    assert "$11,250." in bullets[0]

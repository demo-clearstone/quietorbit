from __future__ import annotations

import fitz

from models.review import RuleDecision
from services.package_builder import (
    RECAP_BODY_SIZE,
    RECAP_BODY_X,
    RECAP_BULLET_X,
    RECAP_HEADER_RULE_Y,
    RECAP_IMPORTANT_SIZE,
    RECAP_IMPORTANT_X,
    RECAP_IMPORTANT_Y,
    RECAP_TITLE_SIZE,
    write_recap_page,
)


def test_recap_header_plan_number_does_not_merge_into_plan_name() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    write_recap_page(
        page,
        [
            "YEAR END RECAP",
            "January 1, 2025 - December 31, 2025",
            "HARBOR MANUFACTURING 401(K) PLAN",
            "555001",
            "Important Information",
        ],
        ["Based on the definition of Highly Compensated Employee (HCE), sample body."],
    )
    plan = None
    number = None
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
            if text == "HARBOR MANUFACTURING 401(K) PLAN":
                plan = line["bbox"]
            elif text == "555001":
                number = line["bbox"]
    assert plan is not None and number is not None
    # Number must start below the plan-name ink (no vertical merge).
    assert number[1] >= plan[3] - 0.5
    assert any(
        abs(((drawing["rect"].y0 + drawing["rect"].y1) / 2) - RECAP_HEADER_RULE_Y) <= 1
        for drawing in page.get_drawings()
        if drawing["rect"].width > 200 and drawing["rect"].height <= 3
    )
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
        page.insert_text((250, 48), "YEAR END RECAP", fontsize=RECAP_TITLE_SIZE, fontname="hebo")
        page.insert_text((214, 66), "January 1, 2024 - December 31, 2024", fontsize=9.9)
        page.insert_text((118, 79), "P.H. MECHANICAL CORPORATION 401(k) PLAN AND TRUST", fontsize=9.9)
        page.insert_text((280, 93), "801080", fontsize=9.9)
        page.draw_line(fitz.Point(42, RECAP_HEADER_RULE_Y), fitz.Point(504, RECAP_HEADER_RULE_Y), color=(0, 0, 0), width=0.8)
        page.insert_text((RECAP_IMPORTANT_X, RECAP_IMPORTANT_Y), "Important Information", fontsize=RECAP_IMPORTANT_SIZE, fontname="hebo")
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
            page.insert_text((RECAP_BULLET_X, y), "·", fontsize=7.3, fontname="helv")
            page.insert_text((RECAP_BODY_X, y), paragraph, fontsize=RECAP_BODY_SIZE)
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


def test_recap_preserves_source_when_no_bullet_rules_change() -> None:
    """Without keep/remove changes, do not wipe/rebuild inventing MOA layout."""
    doc = _recap(bullets=False)
    before = doc[0].get_text("text")
    assert not _recap_bullets_have_marks(doc[0])

    apply_recap_bullets(doc, [])

    assert doc[0].get_text("text") == before
    assert not _recap_bullets_have_marks(doc[0])


def test_merge_universal_availability_absorbs_exclusion_bullets() -> None:
    from services.pdf_modifier import _merge_universal_availability_bullets

    merged = _merge_universal_availability_bullets(
        [
            "UNIVERSAL AVAILABILITY RULE",
            'The "universal availability" generally requires everyone must be able to defer. Certain employees may be excluded, including:',
            "Employees who normally work less than 20 hours per week*",
            "Students performing services at a school, college or university*",
            "If you sponsor a qualified retirement plan not administered by Mutual of America, please provide your service provider",
        ]
    )
    assert len(merged) == 1
    assert merged[0].startswith("UNIVERSAL AVAILABILITY RULE")
    assert "Employees who normally work less than 20 hours per week*" in merged[0]
    assert "Students performing services at a school, college or university*" in merged[0]
    assert "If you sponsor a qualified retirement plan" in merged[0]


def test_recap_writes_universal_availability_nested_layout() -> None:
    from services.package_builder import (
        RECAP_BULLET_DIAMETER,
        RECAP_UA_FOLLOWON_BULLET_X,
        RECAP_UA_NEST_BULLET_X,
        RECAP_UA_NEST_SIZE,
        RECAP_UA_TITLE_SIZE,
    )

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    body = (
        'UNIVERSAL AVAILABILITY RULE The "universal availability" generally requires everyone must be able to defer. '
        "There is no age or service requirement permitted. To satisfy universal availability, all employees must have "
        '"effective opportunity" to make this deferral election data At least once during a plan year the plan must '
        "provide an employee with an effective opportunity. Certain employees may be excluded, including: "
        "Employees who normally work less than 20 hours per week* Students performing services at a school, college or university* "
        "Non-resident aliens with no U.S. source income Employees who are eligible to make elective deferrals under another "
        "401(k), 403(b) or 457(b) plan sponsored by the same employer Employees not able to defer $200 during the plan year "
        "If you sponsor a qualified retirement plan not administered by Mutual of America, please provide your service provider"
    )
    write_recap_page(
        page,
        ["YEAR END RECAP", "Important Information"],
        [body],
    )
    text = page.get_text("text")
    assert "UNIVERSAL AVAILABILITY RULE" in text
    assert "election annually At" in text
    assert "election data At" not in text
    assert "Employees who normally work less than 20 hours per week*" in text
    title_x = None
    title_size = None
    nest_xs = []
    nest_sizes = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
            joined = "".join(span.get("text", "") for span in spans).strip()
            if joined == "UNIVERSAL AVAILABILITY RULE":
                title_x = round(spans[0]["bbox"][0])
                title_size = round(float(spans[0]["size"]), 1)
                assert "Bold" in spans[0]["font"]
            if joined.startswith("Employees who normally work less than 20 hours"):
                nest_xs.append(round(spans[0]["bbox"][0]))
                nest_sizes.append(round(float(spans[0]["size"]), 1))
    discs = [
        fitz.Rect(drawing.get("rect") or (0, 0, 0, 0))
        for drawing in page.get_drawings()
        if drawing.get("fill") in {(0, 0, 0), (0.0, 0.0, 0.0)}
    ]
    discs = [rect for rect in discs if 2.5 <= rect.width <= 6 and 2.5 <= rect.height <= 6]
    assert title_x == 83
    assert title_size == RECAP_UA_TITLE_SIZE
    assert nest_xs and nest_xs[0] == 101
    assert nest_sizes and nest_sizes[0] == RECAP_UA_NEST_SIZE
    assert any(abs(rect.x0 - RECAP_UA_FOLLOWON_BULLET_X) < 1 for rect in discs)
    assert any(abs(rect.x0 - RECAP_UA_NEST_BULLET_X) < 1 for rect in discs)
    assert discs and all(abs(rect.width - RECAP_BULLET_DIAMETER) < 0.2 for rect in discs)


def test_recap_header_ignores_stray_bullet_glyphs() -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    write_recap_page(
        page,
        [
            "YEAR END RECAP",
            "January 1, 2024 - December 31, 2024",
            "╖",
            "P.H. MECHANICAL CORPORATION 401(k) PLAN AND TRUST",
            "801080",
            "Important Information",
        ],
        ["Your plan is designed to allow participants who were age 50 or older to make catch-up contributions."],
    )
    stray = [
        span
        for block in page.get_text("dict")["blocks"]
        if block.get("type") == 0
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if str(span.get("text") or "").strip() in {"•", "·", "╖", "●"} and float(span["bbox"][0]) > 200
    ]
    assert stray == []
    discs = [
        fitz.Rect(drawing.get("rect") or (0, 0, 0, 0))
        for drawing in page.get_drawings()
        if drawing.get("fill") in {(0, 0, 0), (0.0, 0.0, 0.0)}
    ]
    assert any(60 <= rect.x0 <= 75 and abs(rect.width - 3.6) < 0.2 for rect in discs)


def test_recap_with_existing_bullets_is_not_rebuilt_or_changed() -> None:
    doc = _recap(bullets=True, moa_header=True)
    before = doc[0].get_text("text")
    assert _recap_bullets_have_marks(doc[0])
    assert _recap_has_header_rule(doc[0])

    apply_recap_bullets(doc, [])

    assert doc[0].get_text("text") == before


def test_recap_does_not_rebuild_header_layout_without_content_change() -> None:
    doc = _recap(bullets=True, moa_header=False)
    before = doc[0].get_text("text")

    apply_recap_bullets(doc, [])

    assert doc[0].get_text("text") == before
    title = next(
        span
        for block in doc[0].get_text("dict")["blocks"] if block.get("type") == 0
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip().upper() == "YEAR END RECAP"
    )
    # Source header metrics left alone (fixture uses RECAP_TITLE_SIZE).
    assert abs(float(title["size"]) - RECAP_TITLE_SIZE) <= 0.3


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


def test_recap_remove_packs_remaining_bullets_under_important_information() -> None:
    """After keep/remove, rebuild packs kept bullets (Kaagaz p4) — no holes/fragments."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((239, 48), "YEAR END RECAP", fontsize=13, fontname="hebo")
    page.insert_text((214, 66), "January 1, 2025 - December 31, 2025", fontsize=10)
    page.insert_text((184, 79), "GRACE MEDICAL HOME, INC. 403(B) PLAN", fontsize=11, fontname="hebo")
    page.insert_text((280, 93), "555403", fontsize=10)
    page.draw_line(fitz.Point(54, 109), fitz.Point(page.rect.width - 54, 109), color=(0, 0, 0), width=0.8)
    page.insert_text((54, 123), "Important Information", fontsize=11, fontname="hebo")
    page.insert_text((54, 150), "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed.", fontsize=8)
    page.insert_text((54, 280), "Your plan is designed to allow participants who were age 50 or older to make catch-up contributions.", fontsize=8)
    page.insert_text((54, 410), "If you sponsor a qualified retirement plan not administered by Mutual of America, please provide.", fontsize=8)
    page.insert_text((54, 540), "The plan's employer match contribution is calculated on a participant's compensation.", fontsize=8)

    def _y(prefix: str) -> float:
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
                if text.startswith(prefix):
                    return float(line["bbox"][1])
        raise AssertionError(f"missing: {prefix}")

    apply_recap_bullets(
        doc,
        [RuleDecision(rule_id="Y8", section="Year End Recap, per-payroll match", action="remove", reason="no")],
        "401k",
    )

    page = doc[0]
    text = page.get_text("text")
    assert "employer match contribution" not in text
    assert "Your plan is designed to allow participants" in text
    assert "cannot ex" not in text
    important_y = _y("Important Information")
    catch_y = _y("Your plan is designed")
    # Packed under Important Information — not left at the old sparse y≈280.
    assert catch_y - important_y < 80


def test_recap_leaves_sparse_source_spacing_when_no_removals() -> None:
    """Without rule-driven content changes, keep the source Recap spacing as-is."""
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

    before = page.get_text("text")
    apply_recap_bullets(doc, [], "401k")
    assert doc[0].get_text("text") == before

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
    assert max(starts[i + 1] - starts[i] for i in range(len(starts) - 1)) >= 90


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


def test_recap_remove_preserves_remaining_source_font_size() -> None:
    """Simple keep/remove must not rewrite remaining Recap text into MOA fonts."""
    doc = _recap(bullets=False, include_match=True)
    apply_recap_bullets(
        doc,
        [RuleDecision(rule_id="Y8", section="Year End Recap, per-payroll match", action="remove", reason="no")],
        "401k",
    )
    page = doc[0]
    assert "employer match contribution" not in page.get_text("text")
    body_size = next(
        float(span["size"])
        for block in page.get_text("dict")["blocks"] if block.get("type") == 0
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if "Based on the definition" in span.get("text", "")
    )
    # Fixture body uses fontsize=8 via textbox — must remain source size.
    assert abs(body_size - 8) <= 0.3


def test_recap_safe_harbor_remove_match_preserves_source_sh_text() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((239, 48), "YEAR END RECAP", fontsize=13, fontname="hebo")
    page.insert_text((54, 123), "Important Information", fontsize=11, fontname="hebo")
    page.insert_textbox(
        fitz.Rect(62, 140, 540, 220),
        "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed "
        "on the Future HCE Determination Report are considered highly compensated for the Plan "
        "Year beginning in 2026. The maximum average deferral rate for the Highly Compensated "
        "Employee(s) for the 2026 plan year is not limited as long as the plan follows the rules "
        "and regulations of the Safe Harbor Plan. Note: The actual amount an employee can defer "
        "in 2026 is the lesser of $24,500 or the annual addition limit.",
        fontsize=8,
    )
    page.insert_text(
        (62, 280),
        "The plan's employer match contribution is calculated on a participant's compensation.",
        fontsize=8,
    )
    apply_recap_bullets(
        doc,
        [
            RuleDecision(rule_id="Y4", section="safe harbor", action="keep", reason="SH"),
            RuleDecision(rule_id="Y2", section="prior", action="remove", reason="SH"),
            RuleDecision(rule_id="Y8", section="match", action="remove", reason="no match"),
        ],
        "401k",
    )
    text = doc[0].get_text("text")
    assert "Safe Harbor Plan" in text
    assert "employer match contribution" not in text
    body_size = next(
        float(span["size"])
        for block in doc[0].get_text("dict")["blocks"] if block.get("type") == 0
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if "Based on the definition" in span.get("text", "")
    )
    assert abs(body_size - 8) <= 0.3


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

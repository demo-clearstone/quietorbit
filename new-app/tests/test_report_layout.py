from __future__ import annotations

import fitz

from services.package_polish import ensure_summary_heading_rule, normalize_report_layout
from services.source_rewrite import (
    _date_span_boundary_has_visual_gap,
    normalize_cover_address_spacing,
    normalize_cover_census_wrap,
    normalize_date_range_spacing,
    normalize_from_to_columns,
)


def _line_x(page: fitz.Page, text: str) -> float:
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            content = "".join(span["text"] for span in line["spans"]).strip()
            if content == text:
                return line["bbox"][0]
    raise AssertionError(f"line not found: {text}")


def test_aligns_action_required_headings() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((36, 100), "Annual Valuation Report", fontsize=12)
    page.insert_text((36, 130), "ACTION REQUIRED", fontsize=11)
    page.insert_text((30, 155), "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME", fontsize=11)

    normalize_report_layout(doc)
    normalize_report_layout(doc)

    assert round(_line_x(page, "ACTION REQUIRED")) == 40
    assert round(_line_x(page, "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME")) == 39


def test_aligns_client_action_headings_from_x24_to_expected_columns() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((36, 60), "Annual Valuation Report", fontsize=12)
    page.insert_text((24, 130), "ACTION REQUIRED", fontsize=11)
    page.insert_text((24, 155), "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME", fontsize=11)

    normalize_report_layout(doc)

    assert round(_line_x(page, "ACTION REQUIRED")) == 40
    assert round(_line_x(page, "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME")) == 39


def test_aligns_immediate_action_headings_to_action_column() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((36, 60), "Annual Valuation Report", fontsize=12)
    page.insert_text((24, 130), "IMMEDIATE ACTION REQUIRED - ADP/ACP TEST FAILURE", fontsize=11)
    page.insert_text((30, 160), "ATTENTION REQUIRED - VARIANCE", fontsize=11)

    normalize_report_layout(doc)

    assert round(_line_x(page, "IMMEDIATE ACTION REQUIRED - ADP/ACP TEST FAILURE")) == 40
    assert round(_line_x(page, "ATTENTION REQUIRED - VARIANCE")) == 40


def test_shifts_universal_availability_block_and_nested_bullets() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 50), "YEAR END RECAP", fontsize=12)
    page.insert_text((78, 120), "UNIVERSAL AVAILABILITY RULE", fontsize=9)
    page.insert_text((78, 140), "Universal availability body", fontsize=9)
    page.insert_text((96, 160), "Employees who normally work less than 20 hours", fontsize=9)
    page.insert_text((78, 180), "If you sponsor a qualified retirement plan", fontsize=9)
    page.insert_text((78, 195), "Please contact your local regional office representative to discuss.", fontsize=9)

    normalize_report_layout(doc)

    assert round(_line_x(page, "UNIVERSAL AVAILABILITY RULE")) == 83
    assert round(_line_x(page, "Employees who normally work less than 20 hours")) == 101
    assert round(_line_x(page, "Please contact your local regional office representative to discuss.")) == 83


def test_splits_merged_amount_percent_heading_and_aligns_census_name() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 50), "Census", fontsize=12)
    page.insert_text((36, 130), "Name", fontsize=9)
    page.insert_text((288, 180), "Amount                      %", fontsize=8, fontname="hebo")

    normalize_report_layout(doc)

    assert round(_line_x(page, "Name")) == 42
    assert round(_line_x(page, "Amount")) == 288
    assert round(_line_x(page, "%")) == 360


def test_compacts_cover_address_lines_and_shifts_re_body_up() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((45, 70), "September 9, 2026", fontsize=20)
    page.insert_text((45, 170), "GRACE MEDICAL HOME, INC.", fontsize=20)
    page.insert_text((45, 240), "88 Chapel Street", fontsize=20)
    page.insert_text((45, 310), "Orlando, FL 32801", fontsize=20)
    page.insert_text((45, 400), "RE: GRACE MEDICAL HOME, INC. 403(B) PLAN", fontsize=20)
    page.insert_text((45, 450), "Dear Plan Sponsor:", fontsize=20)

    def baseline(text: str) -> float:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                if "".join(span["text"] for span in line["spans"]).strip() == text:
                    return line["bbox"][3]
        raise AssertionError(f"line not found: {text}")

    date_y = baseline("September 9, 2026")
    re_y = baseline("RE: GRACE MEDICAL HOME, INC. 403(B) PLAN")
    dear_y = baseline("Dear Plan Sponsor:")
    assert normalize_cover_address_spacing(doc)
    address_lines = [
        "GRACE MEDICAL HOME, INC.",
        "88 Chapel Street",
        "Orlando, FL 32801",
    ]
    address_baselines = [baseline(line) for line in address_lines]
    new_re_y = baseline("RE: GRACE MEDICAL HOME, INC. 403(B) PLAN")
    new_dear_y = baseline("Dear Plan Sponsor:")

    assert all(right > left for left, right in zip(address_baselines, address_baselines[1:]))
    assert all(right - left <= 30 for left, right in zip(address_baselines, address_baselines[1:]))
    assert baseline("September 9, 2026") == date_y
    assert new_re_y < re_y
    assert new_dear_y < dear_y
    assert abs((dear_y - re_y) - (new_dear_y - new_re_y)) <= 1.0
    assert new_re_y - address_baselines[-1] <= 60


def test_adds_summary_divider_below_header_and_does_not_duplicate_it() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((54, 80), "Compliance Testing Summary of Results", fontsize=11)
    page.insert_text((54, 96), "Plan Year End: December 31, 2025", fontsize=11)
    page.insert_text((54, 112), "EXAMPLE 401(K) PLAN", fontsize=11, fontname="hebo")
    page.insert_text((54, 128), "555001", fontsize=11, fontname="hebo")
    page.insert_text((54, 160), "416 Top Heavy Determination", fontsize=11, fontname="hebo")

    assert ensure_summary_heading_rule(doc)
    rules = [drawing for drawing in page.get_drawings() if drawing["rect"].width > 400 and drawing["rect"].height <= 2]
    assert len(rules) == 1
    rule_y = rules[0]["rect"].y0
    assert 128 < rule_y < 160
    assert ensure_summary_heading_rule(doc) == []
    assert len([drawing for drawing in page.get_drawings() if drawing["rect"].width > 400 and drawing["rect"].height <= 2]) == 1


def test_does_not_add_summary_divider_to_other_pages() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((54, 80), "Annual Valuation Report", fontsize=11, fontname="hebo")
    assert ensure_summary_heading_rule(doc) == []
    assert page.get_drawings() == []


def test_normalizes_joined_date_range_connectors_on_report_pages() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "Top Heavy Report", fontsize=12)
    page.insert_text((50, 130), "Plan Year Ending Between 07/01/2025To 06/30/2026", fontsize=12)
    page.insert_text((50, 160), "Plan year 01/01/2025and12/31/2025", fontsize=12)
    page.insert_text((50, 190), "Period 01/01/2025 from 12/31/2025", fontsize=12)

    assert normalize_date_range_spacing(doc)
    lines = [line.strip() for line in page.get_text().splitlines()]
    assert "Plan Year Ending Between 07/01/2025 To 06/30/2026" in lines
    assert "Plan year 01/01/2025 and 12/31/2025" in lines
    assert "Period 01/01/2025 from 12/31/2025" in lines
    assert normalize_date_range_spacing(doc) == []


def test_date_range_to_spacing_does_not_wipe_nearby_lines() -> None:
    """Dense report lines overlap slightly in bbox; To-spacing must not redact neighbors."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 120), "Employee Name", fontsize=9)
    page.insert_text((50, 132), "Plan Year Ending Between 07/01/2025To 06/30/2026", fontsize=9)
    page.insert_text((50, 144), "Contribution Amount", fontsize=9)
    page.insert_text((50, 200), "Left label near dates", fontsize=9)
    page.insert_text((326, 200), "From 01/01/2025 To 12/31/2025", fontsize=9)

    assert normalize_date_range_spacing(doc)
    normalize_from_to_columns(doc)
    text = page.get_text()
    assert "Employee Name" in text
    assert "Contribution Amount" in text
    assert "Left label near dates" in text
    assert "07/01/2025 To 06/30/2026" in text
    assert "From 01/01/2025" in text
    assert "To 12/31/2025" in text


def test_normalizes_month_name_date_range_and_leaves_unrelated_dates_alone() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "January 1, 2025To December 31, 2025", fontsize=12)
    page.insert_text((50, 130), "Date prepared: October 26, 2026", fontsize=12)

    normalize_date_range_spacing(doc)

    lines = [line.strip() for line in page.get_text().splitlines()]
    assert "January 1, 2025 To December 31, 2025" in lines
    assert "Date prepared: October 26, 2026" in lines


def test_date_range_spacing_keeps_separate_source_spans_aligned() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((326, 100), "From 01/01/2025", fontsize=9, fontname="hebo")
    page.insert_text((406, 100), "To 12/31/2025", fontsize=9, fontname="hebo")

    spans = [
        {"text": "From 01/01/2025", "bbox": (326, 90, 396, 103), "size": 9},
        {"text": "To 12/31/2025", "bbox": (406, 90, 465, 103), "size": 9},
    ]
    assert _date_span_boundary_has_visual_gap(spans, len(spans[0]["text"]))

    assert normalize_date_range_spacing(doc) == []
    assert normalize_from_to_columns(doc) == []
    from_lines = [
        line
        for block in page.get_text("dict")["blocks"] if block.get("type") == 0
        for line in block.get("lines", [])
        if "".join(span["text"] for span in line["spans"]).strip().startswith("From")
    ]
    to_lines = [
        line
        for block in page.get_text("dict")["blocks"] if block.get("type") == 0
        for line in block.get("lines", [])
        if "".join(span["text"] for span in line["spans"]).strip().startswith("To")
    ]
    assert len(from_lines) == len(to_lines) == 1
    assert round(from_lines[0]["spans"][0]["bbox"][0]) == 326
    assert round(to_lines[0]["spans"][0]["bbox"][0]) == 406


def test_splits_merged_from_to_date_header_into_columns() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((326, 100), "From 01/01/2025 To 12/31/2025", fontsize=9, fontname="hebo")

    assert normalize_from_to_columns(doc)

    cols = [
        (round(span["bbox"][0]), span["text"].strip())
        for block in page.get_text("dict")["blocks"] if block.get("type") == 0
        for line in block.get("lines", [])
        for span in line.get("spans", [])
        if span.get("text", "").strip()
    ]
    assert (326, "From 01/01/2025") in cols
    assert (406, "To 12/31/2025") in cols


def test_cover_census_wrap_breaks_after_results_of() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (48, 200),
        "period ending 12/31/2025. This Valuation Report contains a recap of the finalized census data and results of the",
        fontsize=10,
    )
    page.insert_text((48, 214), "IRS required testing for the plan year.", fontsize=10)

    assert normalize_cover_census_wrap(doc)
    lines = [line.strip() for line in page.get_text().splitlines() if line.strip()]
    assert any(line.endswith("results of") for line in lines)
    assert any(line.startswith("the IRS required testing") for line in lines)


def test_cover_census_wrap_does_not_wipe_we_are_pleased_body_line() -> None:
    """Client covers keep tight leading; wrap redaction must not erase the body start."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((45, 72), "September 9, 2026", fontsize=11)
    page.insert_text((45, 100), "GRACE MEDICAL HOME, INC.", fontsize=11)
    page.insert_text((45, 136), "88 Chapel Street", fontsize=11)
    page.insert_text((45, 172), "Orlando, FL 32801", fontsize=11)
    page.insert_text((45, 222), "RE: GRACE MEDICAL HOME, INC. 403(B) PLAN", fontsize=11)
    page.insert_text((45, 242), "Dear Plan Sponsor:", fontsize=11)
    page.insert_text(
        (45, 262),
        "We are pleased to provide you with our completed administrative review of your",
        fontsize=11,
    )
    page.insert_text(
        (45, 276),
        "qualified retirement plan for the period ending 12/31/2025. This Valuation Report",
        fontsize=11,
    )
    page.insert_text(
        (45, 290),
        "contains a recap of the finalized census data and results of the",
        fontsize=11,
    )
    page.insert_text((45, 304), "IRS required testing for the plan year.", fontsize=11)

    assert normalize_cover_address_spacing(doc)
    assert normalize_cover_census_wrap(doc)
    text = page.get_text()
    assert "We are pleased to provide you with our completed administrative review of your" in text
    assert "qualified retirement plan for the period ending 12/31/2025. This Valuation Report" in text
    assert "results of" in text
    assert "the IRS required testing for the plan year." in text

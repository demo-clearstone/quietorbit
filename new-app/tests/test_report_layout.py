from __future__ import annotations

import fitz

from services.package_polish import ensure_summary_heading_rule, normalize_report_layout
from services.source_rewrite import normalize_cover_address_spacing, normalize_date_range_spacing


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

    assert round(_line_x(page, "ACTION REQUIRED")) == 38
    assert round(_line_x(page, "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME")) == 39


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


def test_compacts_cover_address_lines_without_moving_date_or_re_line() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((45, 70), "September 9, 2026", fontsize=20)
    page.insert_text((45, 170), "GRACE MEDICAL HOME, INC.", fontsize=20)
    page.insert_text((45, 240), "88 Chapel Street", fontsize=20)
    page.insert_text((45, 310), "Orlando, FL 32801", fontsize=20)
    page.insert_text((45, 400), "RE: GRACE MEDICAL HOME, INC. 403(B) PLAN", fontsize=20)

    def baseline(text: str) -> float:
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                if "".join(span["text"] for span in line["spans"]).strip() == text:
                    return line["bbox"][3]
        raise AssertionError(f"line not found: {text}")

    date_y = baseline("September 9, 2026")
    re_y = baseline("RE: GRACE MEDICAL HOME, INC. 403(B) PLAN")
    assert normalize_cover_address_spacing(doc)
    address_lines = [
        "GRACE MEDICAL HOME, INC.",
        "88 Chapel Street",
        "Orlando, FL 32801",
    ]
    address_baselines = [baseline(line) for line in address_lines]

    assert all(right > left for left, right in zip(address_baselines, address_baselines[1:]))
    assert all(right - left <= 30 for left, right in zip(address_baselines, address_baselines[1:]))
    assert baseline("September 9, 2026") == date_y
    assert baseline("RE: GRACE MEDICAL HOME, INC. 403(B) PLAN") == re_y


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


def test_normalizes_month_name_date_range_and_leaves_unrelated_dates_alone() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "January 1, 2025To December 31, 2025", fontsize=12)
    page.insert_text((50, 130), "Date prepared: October 26, 2026", fontsize=12)

    normalize_date_range_spacing(doc)

    lines = [line.strip() for line in page.get_text().splitlines()]
    assert "January 1, 2025 To December 31, 2025" in lines
    assert "Date prepared: October 26, 2026" in lines

from __future__ import annotations

import fitz

from services.package_polish import normalize_report_layout


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

"""410(b) Coverage Test checkpoint on the Result Summary."""

from __future__ import annotations

import fitz

from services.package_polish import _coverage_item, _result_summary_checks


def _summary_doc(*lines: str) -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((54, 72), "Compliance Testing Summary of Results", fontsize=12)
    y = 100.0
    for line in lines:
        page.insert_text((54, y), line, fontsize=10)
        y += 14
    return doc


def test_403b_flags_401k_line_under_410b_coverage() -> None:
    doc = _summary_doc(
        "410(b) Coverage Test",
        "Standard: Pass Ratio percent 100%",
        "401(k): Pass Ratio percent 100%",
        "401(m): Pass Ratio percent 100%",
    )
    item = _coverage_item(doc, doc[0].get_text(), "403b")
    assert item is not None
    assert item.passed is False
    assert "401(k) result should not appear" in item.detail


def test_403b_accepts_standard_and_401m_only() -> None:
    doc = _summary_doc(
        "410(b) Coverage Test",
        "Standard: Pass Ratio percent 100%",
        "401(m): Pass Ratio percent 95%",
    )
    item = _coverage_item(doc, doc[0].get_text(), "403b")
    assert item is not None
    assert item.passed is True


def test_401k_allows_401k_line_under_410b() -> None:
    doc = _summary_doc(
        "410(b) Coverage Test",
        "Standard: Pass Ratio percent 100%",
        "401(k): Pass Ratio percent 100%",
        "401(m): Pass Ratio percent 100%",
    )
    item = _coverage_item(doc, doc[0].get_text(), "401k")
    assert item is not None
    assert item.passed is True


def test_410b_fail_requires_abpt_wording() -> None:
    doc = _summary_doc(
        "410(b) Coverage Test",
        "Standard: Fail Ratio percent 60%",
        "401(m): Pass Ratio percent 100%",
    )
    item = _coverage_item(doc, doc[0].get_text(), "403b")
    assert item is not None
    assert item.passed is False
    assert "Average Benefits Test Passed" in item.detail


def test_result_summary_checks_include_410b_for_403b() -> None:
    doc = _summary_doc(
        "416 Top Heavy Determination 10.00%",
        "Plan is not Top Heavy",
        "410(b) Coverage Test",
        "Standard: Pass Ratio percent 100%",
        "401(k): Pass Ratio percent 100%",
        "401(m): Pass Ratio percent 100%",
    )
    items = _result_summary_checks(doc, "403b")
    coverage = next(item for item in items if item.code == "summary_410(b)")
    assert coverage.passed is False

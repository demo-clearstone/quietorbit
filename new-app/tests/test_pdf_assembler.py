from __future__ import annotations

import fitz

from services.pdf_assembler import merge_pdfs


def _pdf_with_pages(*headings: str) -> bytes:
    doc = fitz.open()
    for heading in headings:
        page = doc.new_page()
        page.insert_text((50, 60), heading, fontsize=12)
    data = doc.tobytes()
    doc.close()
    return data


def test_adp_acp_test_results_page_moves_to_first_page_before_merge() -> None:
    data = _pdf_with_pages("EMPLOYEE LISTING", "TEST RESULTS", "CORRECTIONS")

    merged = merge_pdfs([("123456 2025 ADP ACP Test.pdf", data)])

    assert [page.get_text().splitlines()[0] for page in merged] == [
        "TEST RESULTS",
        "EMPLOYEE LISTING",
        "CORRECTIONS",
    ]


def test_test_results_heading_in_other_report_is_not_reordered() -> None:
    data = _pdf_with_pages("EMPLOYEE LISTING", "TEST RESULTS", "CORRECTIONS")

    merged = merge_pdfs([("123456 Census Report.pdf", data)])

    assert [page.get_text().splitlines()[0] for page in merged] == [
        "EMPLOYEE LISTING",
        "TEST RESULTS",
        "CORRECTIONS",
    ]
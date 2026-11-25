from __future__ import annotations

import fitz

from services import file_order, upload_dedupe


def _page_pdf(lines: list[str]) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in lines:
        page.insert_text((54, y), line, fontsize=11)
        y += 16
    data = doc.tobytes()
    doc.close()
    return data


def test_finished_valuation_filename_detected() -> None:
    assert upload_dedupe.is_finished_valuation_filename("800643_2025-Valuation.pdf")
    assert upload_dedupe.is_finished_valuation_filename("123456_2024-Valuation.pdf")
    assert not upload_dedupe.is_finished_valuation_filename(
        "800643 2026 403 (b) Valuation Pkg.pdf"
    )
    assert not upload_dedupe.is_finished_valuation_filename("2026ResultSumm.pdf")


def test_finished_valuation_is_not_treated_as_cover_packet() -> None:
    assert file_order.matched_spec("800643_2025-Valuation.pdf") is None
    assert file_order.should_split_pages("800643_2025-Valuation.pdf", 22) is False
    assert file_order.should_split_pages("800643 2026 Valuation Pkg.pdf", 14) is True


def test_exclude_finished_when_sources_present() -> None:
    pkg = _page_pdf(
        [
            "August 25, 2026",
            "ACME CORP",
            "RE: ACME 401(K) PLAN",
            "We are pleased to provide you with our completed administrative review",
        ]
    )
    summary = _page_pdf(["Compliance Testing Summary of Results", "Plan Year End: June 30, 2026"])
    finished = _page_pdf(
        [
            "September 01, 2026",
            "ACME CORP",
            "RE: ACME 401(K) PLAN",
            "We are pleased to provide you with our completed administrative review",
            "Compliance Testing Summary of Results",
            "YEAR END RECAP",
            "Annual Valuation Report",
            "Contribution Analysis",
            "Employee Census",
            "402(g) Limit Report",
            "410(b) COVERAGE TEST",
            "Determination of Highly Compensated Employees",
        ]
    )
    # Multi-page finished package bytes
    fin_doc = fitz.open()
    for _ in range(10):
        p = fin_doc.new_page()
        p.insert_text((54, 72), "September 01, 2026")
        p.insert_text((54, 90), "RE: ACME 401(K) PLAN")
        p.insert_text((54, 110), "We are pleased to provide")
        p.insert_text((54, 130), "Compliance Testing Summary of Results")
        p.insert_text((54, 150), "YEAR END RECAP")
        p.insert_text((54, 170), "Annual Valuation Report")
        p.insert_text((54, 190), "Contribution Analysis By Source")
        p.insert_text((54, 210), "Employee Census")
        p.insert_text((54, 230), "402(g) Limit Report")
        p.insert_text((54, 250), "410(b) COVERAGE TEST")
        p.insert_text((54, 270), "Determination of Highly Compensated Employees")
    finished = fin_doc.tobytes()
    fin_doc.close()

    uploads = [
        ("555001 Valuation Pkg.pdf", pkg),
        ("2026ResultSumm.pdf", summary),
        ("555001_2025-Valuation.pdf", finished),
    ]
    kept, notes = upload_dedupe.exclude_finished_packages(uploads)
    names = [name for name, _ in kept]
    assert "555001_2025-Valuation.pdf" not in names
    assert "555001 Valuation Pkg.pdf" in names
    assert any("finished valuation package" in note.lower() for note in notes)


def test_dedupe_ordered_pages_keeps_single_cover_and_summary() -> None:
    cover_a = _page_pdf(
        [
            "August 25, 2026",
            "Mutual of America Financial Group",
            "RE: ACME 401(K) PLAN",
            "period ending 12/31/2025. Valuation package",
            "We are pleased to provide you with our completed administrative review",
        ]
    )
    cover_b = _page_pdf(
        [
            "September 01, 2026",
            "Mutual of America Financial Group",
            "RE: ACME 401(K) PLAN",
            "period ending 12/31/2025. Valuation package",
            "We are pleased to provide you with our completed administrative review",
        ]
    )
    summary = _page_pdf(["Compliance Testing Summary of Results", "Plan Year End: December 31, 2025"])
    summary_dup = _page_pdf(["Compliance Testing Summary of Results", "Plan Year End: December 31, 2025"])
    ordered = [
        ("pkg_p01.pdf", cover_a),
        ("555001_2025-Valuation_p01.pdf", cover_b),
        ("2026ResultSumm.pdf", summary),
        ("dupResult.pdf", summary_dup),
    ]
    kept, notes = upload_dedupe.dedupe_ordered_pages(ordered)
    assert len(kept) == 2
    assert kept[0][0] == "pkg_p01.pdf"
    assert kept[1][0] == "2026ResultSumm.pdf"
    assert notes

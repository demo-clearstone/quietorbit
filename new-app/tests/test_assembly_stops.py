import io

import fitz
import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from services.orchestrator import process_uploads
from services.package_polish import cover_date_text


def _page(doc: fitz.Document, text: str, stamp: bool = False) -> None:
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(54, 72, 540, 760), text, fontsize=11, fontname="helv")
    if stamp:
        page.draw_rect(fitz.Rect(430, 24, 500, 52), color=(0.8, 0.05, 0.05), fill=(0.8, 0.05, 0.05))
        page.draw_rect(fitz.Rect(430, 56, 520, 84), color=(0.05, 0.08, 0.35), fill=(0.05, 0.08, 0.35))


def _bytes(doc: fitz.Document) -> bytes:
    data = doc.tobytes()
    doc.close()
    return data


def _package(*extra: str, address: str = "200 Park Avenue, New York, NY 10166", stamp: bool = True) -> bytes:
    doc = fitz.open()
    _page(
        doc,
        "\n".join(
            [
                "Cover Letter",
                "Mutual of America",
                "January 1, 2020",
                "Plan Number: 100000",
                "Plan Name: Example Plan",
                "Company Name: Example Company",
                f"Address: {address}",
                "Plan Year: 01/01/2024 - 12/31/2024",
            ]
        ),
        stamp=stamp,
    )
    sections = [
        "Test Summary\nTesting Method: CURRENT\nTop Heavy Percent: 10%\nPlan is not Top Heavy\nADP Test: Pass\n402(g) Test: Pass\n415 Test: Pass",
        "402(g) Test\nPlan Name: Example Plan\nPlan Year: 01/01/2024 - 12/31/2024",
        "415 Limit Test\nPlan Name: Example Plan\nPlan Year End: 12/31/2024",
        "ADP/ACP Test\nPlan Name: Example Plan\nPlan Year End: 12/31/2024",
        "410(b) Test\nPlan Name: Example Plan\nPlan Year End: 12/31/2024",
        "HCE/Key\nPlan Name: Example Plan\nPlan Year End: 12/31/2024",
        "Future HCE\nPlan Name: Example Plan\nPlan Year End: 12/31/2025",
        "Top Heavy\nPlan Name: Example Plan\nTop Heavy Percent: 10%\nPlan Year End: 12/31/2024",
        "Census\nPlan Name: Example Plan\nPlan Year End: 12/31/2024",
        "Contribution Analysis\nPlan Name: Example Plan\nPlan Year End: 12/31/2024",
    ]
    for text in sections:
        _page(doc, text)
    for text in extra:
        _page(doc, text)
    return _bytes(doc)


def _run(tmp_path, monkeypatch, uploads):
    import services.save_service as save_service

    monkeypatch.setattr(save_service, "OUTPUT_DIR", tmp_path)
    return process_uploads(uploads, auto_order=False, check_assembly_stops=True)


def _excel(plan_name: str) -> bytes:
    book = Workbook()
    sheet = book.active
    sheet["A1"] = "Plan Number"
    sheet["B1"] = "Plan Name"
    sheet["A2"] = "100000"
    sheet["B2"] = plan_name
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_complete_valuation_package_still_saves(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch, [("100000 2024 401k Valuation Pkg.pdf", _package())])
    assert result.filename == "100000_2024-Valuation.pdf"
    assert result.elapsed_seconds is not None and result.elapsed_seconds >= 0
    assert result.email_path
    assert result.log_path


def test_cover_date_is_set_without_the_retype_checkbox(tmp_path, monkeypatch):
    doc = fitz.open()
    _page(doc, "Notice\nJanuary 1, 2020\nPlan Number: 777777")
    result = _run(tmp_path, monkeypatch, [("notice.pdf", _bytes(doc))])
    saved = fitz.open(result.pdf_path)
    try:
        assert cover_date_text() in (saved[0].get_text("text") or "")
    finally:
        saved.close()


def test_assembly_stops_stay_off_unless_requested(tmp_path, monkeypatch):
    import services.save_service as save_service

    monkeypatch.setattr(save_service, "OUTPUT_DIR", tmp_path)
    doc = fitz.open()
    _page(doc, "Census\nSSN 123-45-6789")
    result = process_uploads([("census.pdf", _bytes(doc))], auto_order=False)
    assert result.pdf_path


def test_missing_hce_report_stops(tmp_path, monkeypatch):
    doc = fitz.open()
    _page(
        doc,
        "\n".join(
            [
                "Cover Letter",
                "Mutual of America",
                "Plan Number: 100000",
                "Plan Name: Example Plan",
                "Company Name: Example Company",
                "Address: 200 Park Avenue, New York, NY 10166",
                "Plan Year: 01/01/2024 - 12/31/2024",
            ]
        ),
        stamp=True,
    )
    for text in (
        "Test Summary\nPlan is not Top Heavy\nTop Heavy Percent: 10%",
        "402(g) Test",
        "415 Limit Test",
        "ADP/ACP Test",
        "410(b) Test",
        "Future HCE",
        "Top Heavy",
        "Census",
        "Contribution Analysis",
    ):
        _page(doc, text)
    with pytest.raises(HTTPException) as raised:
        _run(tmp_path, monkeypatch, [("100000 2024 401k Valuation Pkg.pdf", _bytes(doc))])
    assert "HCE Key Report" in raised.value.detail


def test_po_box_address_is_complete(tmp_path, monkeypatch):
    result = _run(
        tmp_path,
        monkeypatch,
        [(
            "100000 2024 401k Valuation Pkg.pdf",
            _package(address="PO BOX 7174, EDMOND, OK 73083"),
        )],
    )
    assert result.filename == "100000_2024-Valuation.pdf"


def test_address_without_zip_stops(tmp_path, monkeypatch):
    with pytest.raises(HTTPException) as raised:
        _run(
            tmp_path,
            monkeypatch,
            [("100000 2024 401k Valuation Pkg.pdf", _package(address="PO BOX 7174, EDMOND, OK"))],
        )
    assert "employer address" in raised.value.detail.lower()


def test_incomplete_address_stops(tmp_path, monkeypatch):
    with pytest.raises(HTTPException) as raised:
        _run(
            tmp_path,
            monkeypatch,
            [("100000 2024 401k Valuation Pkg.pdf", _package(address="New York"))],
        )
    assert "employer address" in raised.value.detail.lower()


def test_true_up_requires_the_client_variance_report(tmp_path, monkeypatch):
    book = Workbook()
    sheet = book.active
    sheet["A1"] = "Plan Number"
    sheet["B1"] = "Plan Name"
    sheet["A2"] = "100000"
    sheet["B2"] = "Example Plan"
    sheet["A12"] = "Annual allocation (per document including true up)? (yes / no)"
    sheet["B12"] = "Yes"
    buffer = io.BytesIO()
    book.save(buffer)
    excel = buffer.getvalue()
    with pytest.raises(HTTPException) as raised:
        _run(
            tmp_path,
            monkeypatch,
            [
                ("100000 2024 401k Valuation Pkg.pdf", _package()),
                ("val-package.xlsx", excel),
            ],
        )
    assert "Variance Client Copy" in raised.value.detail
    result = _run(
        tmp_path,
        monkeypatch,
        [
            ("100000 2024 401k Valuation Pkg.pdf", _package("Variance Report\nPlan Name: Example Plan")),
            ("val-package.xlsx", excel),
        ],
    )
    assert result.plan_profile.true_up is True


def test_excel_plan_name_must_match_the_reports(tmp_path, monkeypatch):
    with pytest.raises(HTTPException) as raised:
        _run(
            tmp_path,
            monkeypatch,
            [
                ("100000 2024 401k Valuation Pkg.pdf", _package()),
                ("val-package.xlsx", _excel("Deerfield Behavioral Health")),
            ],
        )
    assert "valuation package Excel" in raised.value.detail


def test_different_plan_year_end_stops(tmp_path, monkeypatch):
    package = _package("Census\nPlan Name: Example Plan\nPlan Year End: 06/30/2024")
    with pytest.raises(HTTPException) as raised:
        _run(tmp_path, monkeypatch, [("100000 2024 401k Valuation Pkg.pdf", package)])
    assert "plan year end" in raised.value.detail.lower()


def test_ssn_and_masked_ssn_stop_a_single_report(tmp_path, monkeypatch):
    for token in ("123-45-6789", "XXX-XX-1234"):
        doc = fitz.open()
        _page(doc, f"Census\nSSN {token}")
        with pytest.raises(HTTPException) as raised:
            _run(tmp_path, monkeypatch, [("census.pdf", _bytes(doc))])
        assert "Social Security number" in raised.value.detail


def test_unresolved_result_summary_wording_stops(tmp_path, monkeypatch):
    doc = fitz.open()
    _page(doc, "Test Summary\n416 Top Heavy Determination\nPlan is\\is not Top Heavy\nADP Test: Pass/Fail")
    with pytest.raises(HTTPException) as raised:
        _run(tmp_path, monkeypatch, [("summary.pdf", _bytes(doc))])
    assert "unresolved wording" in raised.value.detail


def test_off_calendar_402g_keeps_the_prior_calendar_year(tmp_path, monkeypatch):
    doc = fitz.open()
    _page(
        doc,
        "\n".join(
            [
                "Cover Letter",
                "Mutual of America",
                "Plan Number: 100000",
                "Plan Name: Example Plan",
                "Company Name: Example Company",
                "Address: PO BOX 7174, EDMOND, OK 73083",
                "Plan Year: 07/01/2025 - 06/30/2026",
            ]
        ),
        stamp=True,
    )
    sections = [
        "Test Summary\nPlan is not Top Heavy\nTop Heavy Percent: 10%\nADP Test: Pass",
        "402(g) Test\nPlan Name: Example Plan\nPlan Year: 01/01/2025 - 12/31/2025",
        "415 Limit Test\nPlan Name: Example Plan\nPlan Year End: 06/30/2026",
        "ADP/ACP Test\nPlan Name: Example Plan\nPlan Year End: 06/30/2026",
        "410(b) Test\nPlan Name: Example Plan\nPlan Year End: 06/30/2026",
        "HCE/Key\nPlan Name: Example Plan\nPlan Year End: 06/30/2026",
        "Future HCE\nPlan Name: Example Plan\nPlan Year End: 06/30/2027",
        "Top Heavy\nPlan Name: Example Plan\nPlan Year End: 06/30/2026",
        "Census\nPlan Name: Example Plan\nPlan Year End: 06/30/2026",
        "Contribution Analysis\nPlan Name: Example Plan\nPlan Year End: 06/30/2026",
    ]
    for text in sections:
        _page(doc, text)
    result = _run(tmp_path, monkeypatch, [("100000 2025 401k Valuation Pkg.pdf", _bytes(doc))])
    assert result.filename.endswith("-Valuation.pdf")


def test_safe_harbor_does_not_require_the_adp_report(tmp_path, monkeypatch):
    doc = fitz.open()
    _page(
        doc,
        "\n".join(
            [
                "Cover Letter",
                "Mutual of America",
                "Plan Number: 100000",
                "Plan Name: Example Plan",
                "Company Name: Example Company",
                "Address: 200 Park Avenue, New York, NY 10166",
                "Plan Year: 01/01/2024 - 12/31/2024",
                "Safe Harbor: Yes",
            ]
        ),
        stamp=True,
    )
    for text in (
        "Test Summary\nPlan is not Top Heavy\nTop Heavy Percent: 10%\n"
        "Standard: Pass\n401(k): Pass\n401(m): Pass",
        "402(g) Test\nPlan Year End: 12/31/2024",
        "415 Limit Test\nPlan Year End: 12/31/2024",
        "410(b) Test\nPlan Year End: 12/31/2024",
        "HCE/Key\nPlan Year End: 12/31/2024",
        "Future HCE\nPlan Year End: 12/31/2025",
        "Top Heavy\nPlan Year End: 12/31/2024",
        "Census\nPlan Year End: 12/31/2024",
        "Contribution Analysis\nPlan Year End: 12/31/2024",
    ):
        _page(doc, text)
    result = _run(tmp_path, monkeypatch, [("100000 2024 401k Valuation Pkg.pdf", _bytes(doc))])
    assert result.plan_profile.safe_harbor is True


def test_single_notice_still_saves(tmp_path, monkeypatch):
    doc = fitz.open()
    _page(doc, "ADP/ACP Failure letter\nPlan Number: 777777\nPlan Name: Example Plan")
    result = _run(tmp_path, monkeypatch, [("failure-notice.pdf", _bytes(doc))])
    assert result.pdf_path

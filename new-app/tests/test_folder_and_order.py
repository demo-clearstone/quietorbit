from pathlib import Path

import pytest
from fastapi import HTTPException

from services.file_order import order_uploads, sop_rank
from services.folder_loader import load_pdfs_from_folder
from services.orchestrator import process_uploads

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_auto_order_matches_the_report_list():
    names = [
        "Census Report.pdf",
        "Top Heavy Test.pdf",
        "415 Test.pdf",
        "414(s) Test.pdf",
        "BRF Test.pdf",
        "Average Benefits Test.pdf",
        "401(a)(4) Test.pdf",
        "410(b) Test.pdf",
        "402(g) Test.pdf",
        "ADP ACP Test.pdf",
        "Future HCE Report.pdf",
        "HCE Key Report.pdf",
        "Contribution Analysis.pdf",
        "SHNE Variance Report.pdf",
        "PS Variance Report.pdf",
        "Variance Report.pdf",
        "Excess Return Notice.pdf",
        "Combined Compliance Testing Report.pdf",
        "Compensation Limit Failure Summary.pdf",
        "Summary of Compliance Test Results.pdf",
        "Valuation Reports.pdf",
        "Compliance Testing Reports.pdf",
        "Important Information.pdf",
        "415(c) Failure Information.pdf",
        "Action Required.pdf",
        "Result Summary.pdf",
        "Cover Letter.pdf",
    ]
    ordered = [name for name, _ in order_uploads([(name, b"%PDF") for name in names])]
    assert ordered == [
        "Cover Letter.pdf",
        "Result Summary.pdf",
        "Action Required.pdf",
        "415(c) Failure Information.pdf",
        "Important Information.pdf",
        "Compliance Testing Reports.pdf",
        "Valuation Reports.pdf",
        "Summary of Compliance Test Results.pdf",
        "Combined Compliance Testing Report.pdf",
        "Excess Return Notice.pdf",
        "HCE Key Report.pdf",
        "Future HCE Report.pdf",
        "ADP ACP Test.pdf",
        "410(b) Test.pdf",
        "Variance Report.pdf",
        "Compensation Limit Failure Summary.pdf",
        "PS Variance Report.pdf",
        "SHNE Variance Report.pdf",
        "402(g) Test.pdf",
        "Contribution Analysis.pdf",
        "Top Heavy Test.pdf",
        "415 Test.pdf",
        "Census Report.pdf",
        "401(a)(4) Test.pdf",
        "Average Benefits Test.pdf",
        "414(s) Test.pdf",
        "BRF Test.pdf",
    ]


def test_sop_rank_cover_before_census():
    assert sop_rank("222222 2024 401k Valuation Pkg.pdf") < sop_rank("2024Census.pdf")
    assert sop_rank("2024ADP-ACP.pdf") < sop_rank("2024402G.pdf")
    assert sop_rank("2027HCE.pdf") < sop_rank("2024ADP-ACP.pdf")


def test_split_packet_uses_page_text_to_put_result_summary_second():
    from services.file_order import list_file_meta

    meta = list_file_meta(
        "900062 2025 Valuation Package.pdf",
        100,
        3,
        [
            "Mutual of America\nRE: Example 401(k) Plan\nperiod ending 12/31/2025",
            "Annual Valuation Report\nAction Required",
            "Result Summary\nADP Test: Pass\nACP Test: Pass",
        ],
    )
    assert meta["labels"] == ["Cover Letter", "Action required", "Test Summary"]
    assert meta["ranks"][2] == sop_rank("Result Summary.pdf")
    assert meta["ranks"][2] < meta["ranks"][1]


def test_backend_orders_split_packet_pages_even_if_the_client_order_is_stale():
    names = [
        "2026_401(K)_Valuation Pkg_p02.pdf",
        "2026Result Summ.pdf",
        "2026_401(K)_Valuation Pkg_p01.pdf",
        "2026_401(K)_Valuation Pkg_p08.pdf",
    ]
    ordered = [name for name, _data in order_uploads([(name, b"%PDF") for name in names])]
    assert ordered == [
        "2026_401(K)_Valuation Pkg_p01.pdf",
        "2026Result Summ.pdf",
        "2026_401(K)_Valuation Pkg_p02.pdf",
        "2026_401(K)_Valuation Pkg_p08.pdf",
    ]


def test_named_result_summary_is_kept_in_the_package_and_read():
    import fitz

    from services.orchestrator import _split_summaries

    doc = fitz.open()
    doc.new_page().insert_text(
        (72, 72),
        "Compliance Testing Summary of Results\nADP Test: Pass",
        fontsize=11,
    )
    data = doc.tobytes()
    doc.close()

    valuation, summaries = _split_summaries([("2026Result Summ.pdf", data)])
    assert [name for name, _data in valuation] == ["2026Result Summ.pdf"]
    assert [name for name, _text in summaries] == ["2026Result Summ.pdf"]

    valuation, summaries = _split_summaries([("compliance-summary.pdf", data)])
    assert valuation == []
    assert [name for name, _text in summaries] == ["compliance-summary.pdf"]


def test_order_uploads_follows_sop_not_filename_sort():
    uploads = [
        ("2024Census.pdf", b"%PDF"),
        ("222222 2024 401k Valuation Pkg.pdf", b"%PDF"),
        ("2024ContriAnalysis.pdf", b"%PDF"),
    ]
    ordered = [name for name, _ in order_uploads(uploads)]
    assert ordered == [
        "222222 2024 401k Valuation Pkg.pdf",
        "2024ContriAnalysis.pdf",
        "2024Census.pdf",
    ]


def test_auto_order_uses_folder_keywords():
    from services.file_order import display_label, matched_spec, order_uploads, sop_rank

    assert matched_spec("123456 2025 401k Valuation Pkg.pdf")["name"] == "Cover Letter"
    assert display_label("123456 2025 401k Valuation Pkg.pdf") == "Cover Letter"
    assert matched_spec("2025ResultSumm.pdf")["name"] == "Test Summary"
    assert matched_spec("2025HCEKey.pdf")["name"] == "HCE/Key"
    assert matched_spec("2026FYHCE.pdf")["name"] == "Future HCE"
    assert matched_spec("2025ADP-ACP.pdf")["name"] == "ADP/ACP"
    assert matched_spec("2025410B.pdf")["name"] == "410(b)"
    assert matched_spec("2025MaVar.pdf")["name"] == "Variance"
    assert matched_spec("2025SHMaVar.pdf")["name"] == "Compensation Limit Failure Summary"
    assert matched_spec("2025PSVar.pdf")["name"] == "PS Variance"
    assert matched_spec("2025SHNEVar.pdf")["name"] == "SHNE Variance"
    assert matched_spec("2025402G.pdf")["name"] == "402(g)"
    assert matched_spec("2025ContriAnalysis.pdf")["name"] == "Contribution Analysis"
    assert matched_spec("2025TH.pdf")["name"] == "Top Heavy"
    assert matched_spec("2025Top Heavy.pdf")["name"] == "Top Heavy"
    assert matched_spec("2025415.pdf")["name"] == "415"
    assert matched_spec("2025Census.pdf")["name"] == "Census"
    assert matched_spec("2025401a4.pdf")["name"] == "401(a)(4)"
    assert matched_spec("2025ABPT.pdf")["name"] == "Average Benefit Percentage Test"
    assert matched_spec("2025414s.pdf")["name"] == "414(s)"
    assert sop_rank("2025MaVar.pdf") < sop_rank("2025SHMaVar.pdf")
    assert sop_rank("2025SHMaVar.pdf") < sop_rank("2025PSVar.pdf")
    assert sop_rank("2025PSVar.pdf") < sop_rank("2025SHNEVar.pdf")
    assert sop_rank("123456 2025 401k Valuation Pkg.pdf") < sop_rank("2025ResultSumm.pdf")
    names = [
        "2025Census.pdf",
        "2025TH.pdf",
        "2025Top Heavy.pdf",
        "2025415.pdf",
        "2025ContriAnalysis.pdf",
        "2025402G.pdf",
        "2025ADP-ACP.pdf",
        "2026FYHCE.pdf",
        "2025HCEKey.pdf",
        "2025ResultSumm.pdf",
        "123456 2025 401k Valuation Pkg.pdf",
        "2025414s.pdf",
        "2025ABPT.pdf",
        "2025401a4.pdf",
        "2025410B.pdf",
        "2025MaVar.pdf",
        "2025SHMaVar.pdf",
        "2025PSVar.pdf",
        "2025SHNEVar.pdf",
    ]
    ordered = [name for name, _ in order_uploads([(name, b"%PDF") for name in names])]
    assert ordered == [
        "123456 2025 401k Valuation Pkg.pdf",
        "2025ResultSumm.pdf",
        "2025HCEKey.pdf",
        "2026FYHCE.pdf",
        "2025ADP-ACP.pdf",
        "2025410B.pdf",
        "2025MaVar.pdf",
        "2025SHMaVar.pdf",
        "2025PSVar.pdf",
        "2025SHNEVar.pdf",
        "2025402G.pdf",
        "2025ContriAnalysis.pdf",
        "2025TH.pdf",
        "2025Top Heavy.pdf",
        "2025415.pdf",
        "2025Census.pdf",
        "2025401a4.pdf",
        "2025ABPT.pdf",
        "2025414s.pdf",
    ]
    assert sop_rank("2025ResultSumm.pdf") < sop_rank("Action Required.pdf")
    from services.file_order import list_file_meta

    packet = list_file_meta("222222 2024 401k Valuation Pkg.pdf", 10, 4)
    assert packet["labels"][1] == "Action required page 1"
    assert packet["ranks"][0] < sop_rank("2025ResultSumm.pdf") < packet["ranks"][1]


def test_list_folder_files_returns_names():
    from services.folder_loader import list_folder_files

    folder = FIXTURES / "assemble-current-fail"
    listed = list_folder_files(str(folder))
    names = [item["name"] for item in listed["files"]]
    assert any("Valuation Pkg" in name for name in names)
    assert "Valuation Pkg" in names[0]
    assert any(name == "2024Census.pdf" for name in names)


def test_expand_multipage_pdf_as_separate_rows(tmp_path):
    import fitz

    from services.folder_loader import list_folder_files
    from services.pdf_pages import expand_uploads_by_page, pdf_page_count

    folder = tmp_path / "pkg"
    folder.mkdir()
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Cover page 1", fontsize=12)
    doc.new_page().insert_text((72, 72), "Cover page 2", fontsize=12)
    pdf = folder / "Cover Letter.pdf"
    doc.save(pdf)
    data = pdf.read_bytes()
    doc.close()
    assert pdf_page_count(data) == 2
    listed = list_folder_files(str(folder))
    assert listed["files"][0]["pages"] == 2
    assert listed["files"][0]["split"] is True
    assert listed["files"][0]["labels"] == ["Cover Letter", "Action required page 1"]
    assert any("each page is listed" in w for w in listed["warnings"])
    ordered, warnings = expand_uploads_by_page(
        [("Cover Letter.pdf", data)],
        ["Cover Letter.pdf", "Cover Letter.pdf"],
        [2, 1],
    )
    assert warnings == []
    assert ordered[0][0] == "Cover Letter_p02.pdf"
    assert ordered[1][0] == "Cover Letter_p01.pdf"
    page1 = fitz.open(stream=ordered[1][1], filetype="pdf")
    page2 = fitz.open(stream=ordered[0][1], filetype="pdf")
    try:
        assert page1.page_count == 1
        assert "page 1" in (page1[0].get_text("text") or "")
        assert "page 2" in (page2[0].get_text("text") or "")
    finally:
        page1.close()
        page2.close()


def test_packet_outline_labels_and_split():
    from services.file_order import display_label, should_split_pages

    assert should_split_pages("Cover Page.pdf", 2) is True
    assert should_split_pages("222222_2024-Valuation.pdf", 15) is True
    assert should_split_pages("800643_2025-Valuation-from-photos.pdf", 15) is True
    assert display_label("222222_2024-Valuation.pdf", page=1, page_count=15) == "Cover Letter"
    assert display_label("222222_2024-Valuation.pdf", page=15, page_count=15) == "Compliance Report 3"
    assert should_split_pages("Action Required.pdf", 3) is False
    assert should_split_pages("Compliance Reports.pdf", 3) is False
    assert should_split_pages("2024Census.pdf", 2) is False
    assert display_label("222222 2024 401k Valuation Pkg.pdf") == "Cover Letter"
    assert display_label("222222 2024 401k Valuation Pkg.pdf", page=1, page_count=15) == "Cover Letter"
    assert display_label("222222 2024 401k Valuation Pkg.pdf", page=2, page_count=15) == "Action required page 1"
    assert display_label("222222 2024 401k Valuation Pkg.pdf", page=3, page_count=15) == "Action required page 2"
    assert display_label("222222 2024 401k Valuation Pkg.pdf", page=4, page_count=15) == "Action required page 3"
    assert (
        display_label("222222 2024 401k Valuation Pkg.pdf", page=5, page_count=15)
        == "ADP/ACP Failure excess page after 12 months (Current year Testing Method)"
    )
    assert (
        display_label("222222 2024 401k Valuation Pkg.pdf", page=6, page_count=15)
        == "ADP/ACP Failure excess page after 12 months (Prior year Testing Method)"
    )
    assert display_label("222222 2024 401k Valuation Pkg.pdf", page=7, page_count=15) == "ADP/ACP Failure excess page Current year"
    assert display_label("222222 2024 401k Valuation Pkg.pdf", page=8, page_count=15) == "415 Failure information"
    assert display_label("222222 2024 401k Valuation Pkg.pdf", page=9, page_count=15) == "ADP/ACP Failure letter"
    assert display_label("222222 2024 401k Valuation Pkg.pdf", page=10, page_count=15) == "402g Failure letter"
    assert display_label("222222 2024 401k Valuation Pkg.pdf", page=11, page_count=15) == "415 Failure letter"
    assert display_label("222222 2024 401k Valuation Pkg.pdf", page=12, page_count=15) == "Year End Recap"
    assert display_label("222222 2024 401k Valuation Pkg.pdf", page=13, page_count=15) == "Compliance Report 1"
    assert display_label("222222 2024 401k Valuation Pkg.pdf", page=14, page_count=15) == "Compliance Report 2"
    assert display_label("222222 2024 401k Valuation Pkg.pdf", page=15, page_count=15) == "Compliance Report 3"
    from services.file_order import list_file_meta

    meta = list_file_meta("222222 2024 401k Valuation Pkg.pdf", 1, 15)
    assert meta["split"] is True
    assert len(meta["labels"]) == 15
    assert meta["labels"][0] == "Cover Letter"
    assert meta["labels"][-1] == "Compliance Report 3"
    assert display_label("Action Required.pdf") == "Action required"
    assert display_label("Compliance Reports.pdf") == "Compliance Reports"
    assert (
        display_label("ADP ACP Failure excess page after 12 months (Current year Testing Method).pdf")
        == "ADP/ACP Failure excess page after 12 months (Current year Testing Method)"
    )
    assert (
        display_label("ADP ACP Failure excess page after 12 months (Prior year Testing Method).pdf")
        == "ADP/ACP Failure excess page after 12 months (Prior year Testing Method)"
    )
    assert display_label("ADP ACP Failure excess page Current year.pdf") == "ADP/ACP Failure excess page Current year"
    assert display_label("415 Failure information.pdf") == "415 Failure information"
    assert display_label("ADP ACP Failure letter.pdf") == "ADP/ACP Failure letter"
    assert display_label("402g Failure letter.pdf") == "402g Failure letter"
    assert display_label("415 Failure letter.pdf") == "415 Failure letter"
    assert display_label("Year End Recap.pdf") == "Year End Recap"


def test_non_cover_multipage_pdf_is_not_split(tmp_path):
    import fitz

    from services.file_order import should_split_pages
    from services.folder_loader import list_folder_files

    folder = tmp_path / "pkg"
    folder.mkdir()
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    pdf = folder / "2024Census.pdf"
    doc.save(pdf)
    doc.close()
    listed = list_folder_files(str(folder))
    assert listed["files"][0]["pages"] == 2
    assert listed["files"][0]["split"] is False
    assert should_split_pages("2024Census.pdf", 2) is False
    assert should_split_pages("Cover Page.pdf", 2) is True
    assert not any("each page is listed" in w for w in listed["warnings"])


def test_apply_file_order_keeps_ui_sequence():
    from services.folder_loader import apply_file_order

    uploads = [
        ("222222 2024 401k Valuation Pkg.pdf", b"a"),
        ("2024ADP-ACP.pdf", b"b"),
        ("2024Census.pdf", b"c"),
    ]
    ordered, warnings = apply_file_order(
        uploads,
        ["2024Census.pdf", "222222 2024 401k Valuation Pkg.pdf"],
    )
    assert [name for name, _ in ordered] == [
        "2024Census.pdf",
        "222222 2024 401k Valuation Pkg.pdf",
    ]
    assert warnings == []


def test_process_folder_uses_file_order(tmp_path, monkeypatch):
    import services.save_service as save_service
    from services.folder_loader import apply_file_order

    monkeypatch.setattr(save_service, "OUTPUT_DIR", tmp_path)
    folder = FIXTURES / "assemble-current-fail"
    uploads, warnings = load_pdfs_from_folder(str(folder))
    names = [name for name, _ in uploads]
    reversed_names = list(reversed(names))
    ordered, _ = apply_file_order(uploads, reversed_names)
    with pytest.raises(HTTPException) as raised:
        process_uploads(ordered, auto_order=False, extra_warnings=warnings, check_assembly_stops=True)
    assert raised.value.status_code == 400
    assert "Assembly stopped" in raised.value.detail


def test_load_folder_and_process(tmp_path, monkeypatch):
    folder = FIXTURES / "assemble-current-fail"
    uploads, warnings = load_pdfs_from_folder(str(folder))
    assert len(uploads) >= 16
    assert any("Loaded " in item for item in warnings)

    import services.save_service as save_service

    monkeypatch.setattr(save_service, "OUTPUT_DIR", tmp_path)
    with pytest.raises(HTTPException) as raised:
        process_uploads(uploads, auto_order=True, extra_warnings=warnings, check_assembly_stops=True)
    assert raised.value.status_code == 400
    assert "HCE Key Report" in raised.value.detail
    assert "Mutual of America stamp" in raised.value.detail

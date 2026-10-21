import fitz

from models.plan_profile import DetectedSection, PlanProfile
from services.bookmark_service import add_bookmarks, adp_acp_bookmark_title
from services.orchestrator import process_uploads


def test_bookmark_title_adp_only_from_filename():
    profile = PlanProfile(plan_type="401k")
    assert adp_acp_bookmark_title(profile, source_files=["10_adp-test.pdf"]) == "ADP Test"


def test_bookmark_title_acp_only_from_filename():
    profile = PlanProfile(plan_type="401k")
    assert adp_acp_bookmark_title(profile, source_files=["12_acp-test.pdf"]) == "ACP Test"


def test_bookmark_title_combined_filename():
    profile = PlanProfile(plan_type="401k")
    assert adp_acp_bookmark_title(profile, source_files=["10_adp-acp.pdf"]) == "ADP/ACP Tests"


def test_bookmark_title_403b_is_acp_even_if_adp_filename():
    profile = PlanProfile(plan_type="403(b)")
    assert adp_acp_bookmark_title(profile, source_files=["10_adp-test.pdf"]) == "ACP Test"


def test_bookmark_title_adp_heading_not_cover_result_line():
    profile = PlanProfile(plan_type="401k")
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Cover Letter\nADP Test: Fail\nACP Test: Pass", fontsize=11)
    page2 = doc.new_page()
    page2.insert_text((72, 72), "ADP Test\n\nTest results follow.", fontsize=11)
    try:
        assert adp_acp_bookmark_title(profile, doc=doc, source_files=["cover.pdf"]) == "ADP Test"
    finally:
        doc.close()


def test_add_bookmarks_uses_adp_test_title():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "ADP Test\nPlan Number 111", fontsize=11)
    profile = PlanProfile(
        plan_type="401k",
        detected_sections=[DetectedSection(name="ADP/ACP", page=1, matched_alias="ADP Test")],
    )
    count = add_bookmarks(doc, profile, source_files=["10_adp-test.pdf"])
    toc = doc.get_toc()
    doc.close()
    assert count == 1
    assert toc[0][1] == "ADP Test"


def test_bookmark_has_an_explicit_top_of_page_destination():
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    profile = PlanProfile(
        plan_type="401k",
        detected_sections=[
            DetectedSection(name="Future HCE", page=2, matched_alias="Future HCE"),
        ],
    )
    try:
        assert add_bookmarks(doc, profile) == 1
        toc = doc.get_toc(simple=False)
    finally:
        doc.close()
    assert toc[0][2] == 2
    assert toc[0][3]["kind"] == fitz.LINK_GOTO
    assert toc[0][3]["page"] == 1


def test_adp_children_are_summary_detail_then_corrections():
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Cover Letter\nPlan Number: 111111", fontsize=11)
    doc.new_page().insert_text((72, 72), "ADP/ACP Corrections Page\nRefunds", fontsize=11)
    doc.new_page().insert_text((72, 72), "ADP/ACP Test Detail\nRates", fontsize=11)
    doc.new_page().insert_text((72, 72), "ADP/ACP Summary Page\nResults", fontsize=11)
    profile = PlanProfile(
        plan_type="401k",
        detected_sections=[
            DetectedSection(name="Cover Letter", page=1, matched_alias="Cover Letter"),
            DetectedSection(name="ADP/ACP", page=2, matched_alias="ADP/ACP"),
        ],
    )
    try:
        add_bookmarks(doc, profile, source_files=["10_adp-acp.pdf"])
        toc = doc.get_toc()
    finally:
        doc.close()
    assert [row[1] for row in toc] == [
        "Cover Letter",
        "ADP/ACP Tests",
        "Summary",
        "Detail",
        "Corrections",
    ]
    assert [row[0] for row in toc] == [1, 1, 2, 2, 2]
    pages = {row[1]: row[2] for row in toc}
    assert pages["Summary"] == 4
    assert pages["Detail"] == 3
    assert pages["Corrections"] == 2


def test_assembled_pdf_bookmark_from_adp_filename(tmp_path, monkeypatch):
    import services.save_service as save_service

    monkeypatch.setattr(save_service, "OUTPUT_DIR", tmp_path)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "\n".join(
            [
                "Cover Letter",
                "Plan Number: 111111",
                "Plan Name: Solo ADP 401(k) Plan",
                "Plan Year: 01/01/2024 - 12/31/2024",
                "Testing Method: CURRENT",
                "ADP Test: Fail",
                "Returns Required",
            ]
        ),
        fontsize=11,
    )
    page2 = doc.new_page()
    page2.insert_text((72, 72), "ADP Test\n\nCorrection Method", fontsize=11)
    data = doc.tobytes()
    doc.close()
    result = process_uploads([("10_adp-test.pdf", data)])
    out = fitz.open(result.pdf_path)
    try:
        titles = [row[1] for row in out.get_toc()]
    finally:
        out.close()
    assert "ADP Test" in titles
    assert "ADP/ACP Tests" not in titles

from pathlib import Path

import fitz

from services.source_rewrite import (
    apply_source_rewrites,
    calendar_402g_year,
    hce_max_percent,
)


def test_hce_max_follows_prior_year_table():
    assert hce_max_percent(1.5) == 3
    assert hce_max_percent(2) == 4
    assert hce_max_percent(2.21) == 4.21
    assert hce_max_percent(5) == 7
    assert hce_max_percent(8) == 10
    assert hce_max_percent(9) == 11.25
    assert hce_max_percent(12) == 15


def test_402g_year_only_for_off_calendar():
    assert calendar_402g_year("06/30/2025") == 2024
    assert calendar_402g_year("06/30/2026") == 2025
    assert calendar_402g_year("12/31/2025") is None
    assert calendar_402g_year(None) is None


def test_cover_day_and_402g_and_hce_rewrite_in_place():
    doc = fitz.open()
    cover = doc.new_page()
    cover.insert_text((72, 72), "January 01, 2025", fontsize=12)
    page = doc.new_page()
    page.insert_text((72, 72), "402(g) Test", fontsize=12)
    page.insert_text((72, 96), "Period 07/01/2024 to 06/30/2025", fontsize=12)
    page.insert_text((72, 120), "NHCE 2%", fontsize=12)
    page.insert_text((72, 144), "HCE 9%", fontsize=12)
    from models.plan_profile import PlanProfile

    profile = PlanProfile(
        testing_method="PRIOR",
        plan_year_start="07/01/2024",
        plan_year_end="06/30/2025",
    )
    notes = apply_source_rewrites(doc, profile)
    text = "\n".join(page.get_text("text") or "" for page in doc)
    from services.package_polish import cover_date_text

    assert cover_date_text() in text
    assert "January 01, 2025" not in text
    assert "01/01/2024" in text
    assert "12/31/2024" in text
    assert "HCE 4%" in text
    assert any("Cover letter date set to" in note for note in notes)
    doc.close()


def test_preview_highlights_marks_and_download_stays_clean():
    from api.jobs import JOBS, download_job_pdf, preview_job_pdf
    from models.plan_profile import PlanProfile
    from services.change_marks import apply_highlights
    from services.orchestrator import process_uploads

    doc = fitz.open()
    cover = doc.new_page()
    cover.insert_text((72, 72), "January 01, 2025", fontsize=12)
    page = doc.new_page()
    page.insert_text((72, 96), "Period 07/01/2024 to 06/30/2025", fontsize=12)
    page.insert_text((72, 72), "402(g) Test", fontsize=12)
    page.insert_text((72, 120), "NHCE 2%", fontsize=12)
    page.insert_text((72, 144), "HCE 9%", fontsize=12)
    profile = PlanProfile(
        testing_method="PRIOR",
        plan_year_start="07/01/2024",
        plan_year_end="06/30/2025",
    )
    marks: list[dict] = []
    apply_source_rewrites(doc, profile, marks)
    labels = {item["label"] for item in marks}
    assert {"Cover date", "402(g) date", "HCE %"} <= labels
    doc.close()

    result = process_uploads([("cover.pdf", _sample_bytes())], auto_order=False, rewrite_sources=True)
    JOBS[result.job_id] = result
    assert len(result.highlights) >= 3
    download = _response_bytes(download_job_pdf(result.job_id))
    preview_off = _response_bytes(preview_job_pdf(result.job_id, highlight=False))
    preview_on = _response_bytes(preview_job_pdf(result.job_id, highlight=True))
    assert _highlight_count(download) == 0
    assert _highlight_count(preview_off) == 0
    assert _highlight_count(preview_on) == len(result.highlights)
    painted = apply_highlights(Path(result.pdf_path), [item.model_dump() for item in result.highlights])
    assert _highlight_count(painted) == len(result.highlights)
    assert _highlight_count(Path(result.pdf_path).read_bytes()) == 0


def _response_bytes(response) -> bytes:
    body = getattr(response, "body", None)
    if body:
        return body
    return Path(response.path).read_bytes()


def _sample_bytes() -> bytes:
    doc = fitz.open()
    cover = doc.new_page()
    cover.insert_text((72, 72), "January 01, 2025", fontsize=12)
    page = doc.new_page()
    page.insert_text((72, 72), "402(g) Test\nPeriod 07/01/2024 to 06/30/2025\nNHCE 2%\nHCE 9%\nTesting Method: PRIOR\nPlan Year: 07/01/2024 - 06/30/2025\nPlan Number: 222222", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _highlight_count(data: bytes) -> int:
    doc = fitz.open(stream=data, filetype="pdf")
    count = 0
    try:
        for page in doc:
            for drawing in page.get_drawings():
                fill = drawing.get("fill")
                if not fill or len(fill) < 3:
                    continue
                if abs(fill[0] - 1) < 0.05 and fill[1] > 0.8 and fill[2] < 0.35:
                    count += 1
    finally:
        doc.close()
    return count

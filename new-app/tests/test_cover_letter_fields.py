from pathlib import Path

import fitz
from openpyxl import Workbook

from services.assembly_stops import stop_reasons
from services.package_polish import _cover_date_check, cover_date_text
from services.pdf_extractor import extract_plan_profile
from services.review_service import validate
from services.source_profile import parse_excel
from services.source_rewrite import apply_cover_date

_STAMP = Path(__file__).resolve().parent / "fixtures" / "moa-company-stamp.png"
_COMPANY = "Soboba Band of Luiseno Indians DBA Soboba Casino Resort"
_ADDRESS = "PO Box 817, San Jacinto, CA 92581"
_PLAN = "Soboba Casino Operations 401(k) Plan"
_PYE = "12/31/2021"

# TEST23 §B sample from the Soboba cover letter (selectable PDF text).
_COVER_LINES = [
    "March 8, 2022",
    "",
    "Soboba Band of Luiseno Indians DBA Soboba Casino Resort",
    "PO Box 81717",
    "San Jacinto, CA 92581",
    "",
    "RE: Soboba Casino Operations 401(k) Plan",
    "",
    "We are pleased to provide you with our completed administrative review of your",
    "qualified retirement plan for the period ending 12/31/2021. This Valuation Report",
    "contains a recap of the finalized census data and results of the IRS required",
    "testing for the plan year.",
    "",
    "Please take note of the testing results for this year and refer to the Action",
    "Required section of the Annual Valuation Report to determine if any items require",
    "your immediate attention.",
    "",
    "If you have questions, please let us know.",
]


def _soboba_cover_pdf() -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "\n".join(_COVER_LINES), fontsize=11)
    return doc


def test_review_extracts_company_address_plan_and_pye_from_cover_letter():
    doc = _soboba_cover_pdf()
    try:
        profile = extract_plan_profile(doc)
        review = validate(profile)
        by_code = {item.code: item for item in review.items}

        assert profile.company_name == "Soboba Band of Luiseno Indians DBA Soboba Casino Resort"
        assert profile.company_address == "PO Box 81717, San Jacinto, CA 92581"
        assert profile.plan_name == "Soboba Casino Operations 401(k) Plan"
        assert profile.plan_year_end == "12/31/2021"

        assert by_code["cover_company"].passed is True
        assert by_code["cover_address"].passed is True
        assert by_code["cover_plan_name"].passed is True
        assert by_code["cover_plan_year_end"].passed is True
        assert by_code["cover_company"].detail == profile.company_name
        assert by_code["cover_address"].detail == profile.company_address
        assert by_code["cover_plan_name"].detail == profile.plan_name
        assert by_code["cover_plan_year_end"].detail == profile.plan_year_end
    finally:
        doc.close()


def build_soboba_cover() -> fitz.Document:
    """Cover letter from the TEST23 sample: stamp at upper right, then the letter block."""
    doc = fitz.open()
    page = doc.new_page()
    width = page.rect.width
    page.insert_image(fitz.Rect(width - 292, 28, width - 28, 108), filename=str(_STAMP))
    lines = [
        (72, 150, "March 8, 2022", "helv", 12),
        (72, 188, _COMPANY, "hebo", 11),
        (72, 206, "PO Box 817", "helv", 11),
        (72, 224, "San Jacinto, CA 92581", "helv", 11),
        (72, 260, f"RE: {_PLAN}", "hebo", 11),
    ]
    for x, y, text, font, size in lines:
        page.insert_text((x, y), text, fontsize=size, fontname=font)
    page.insert_textbox(
        fitz.Rect(72, 284, 540, 400),
        "We are pleased to provide you with our completed administrative review of your "
        f"qualified retirement plan for the period ending {_PYE}. This Valuation Report "
        "contains a recap of the finalized census data and results of the IRS required "
        "testing for the plan year.",
        fontsize=11,
        fontname="helv",
    )
    page.insert_textbox(
        fitz.Rect(72, 410, 540, 500),
        "Please take note of the testing results for this year and refer to the Action "
        "Required section of the Annual Valuation Report to determine if any items require "
        "your immediate attention.",
        fontsize=11,
        fontname="helv",
    )
    page.insert_text((72, 530), "If you have questions, please let us know.", fontsize=11, fontname="helv")
    return doc


def _soboba_excel(**overrides: str) -> bytes:
    book = Workbook()
    sheet = book.active
    headers = ["Omni Plan Number", "Plan Name", "Company Name", "Company Address", "PYE"]
    values = {
        "Omni Plan Number": "123456",
        "Plan Name": _PLAN,
        "Company Name": _COMPANY,
        "Company Address": _ADDRESS,
        "PYE": _PYE,
    }
    values.update(overrides)
    for col, header in enumerate(headers, start=1):
        sheet.cell(1, col, header)
        sheet.cell(2, col, values[header])
    import io

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_soboba_cover_matches_the_sample_and_the_excel():
    doc = build_soboba_cover()
    try:
        text = doc[0].get_text("text")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        date_at = lines.index("March 8, 2022")
        company_at = lines.index(_COMPANY)
        box_at = lines.index("PO Box 817")
        city_at = lines.index("San Jacinto, CA 92581")
        plan_at = lines.index(f"RE: {_PLAN}")
        assert date_at < company_at < box_at < city_at < plan_at
        assert "period ending 12/31/2021" in text

        profile = extract_plan_profile(doc)
        review = validate(profile)
        by_code = {item.code: item for item in review.items}
        assert profile.company_name == _COMPANY
        assert profile.company_address == _ADDRESS
        assert profile.plan_name == _PLAN
        assert profile.plan_year_end == _PYE
        assert profile.moa_logo_found is True
        assert by_code["cover_company"].passed is True
        assert by_code["cover_address"].passed is True
        assert by_code["cover_plan_name"].passed is True
        assert by_code["cover_plan_year_end"].passed is True
        assert by_code["cover_moa"].passed is True

        excel = parse_excel(_soboba_excel())
        assert excel["company_name"] == profile.company_name
        assert excel["company_address"] == profile.company_address
        assert excel["plan_name"] == profile.plan_name
        assert excel["plan_year_end"] == profile.plan_year_end
        reasons = stop_reasons(
            doc,
            profile,
            ["123456 2025 401k Valuation Pkg.pdf"],
            excel_plan_name=excel["plan_name"],
            pdf_plan_name=profile.plan_name,
            excel_company=excel["company_name"],
            excel_address=excel["company_address"],
            excel_pye=excel["plan_year_end"],
            cover_company=profile.company_name,
            cover_address=profile.company_address,
            cover_pye=profile.plan_year_end,
        )
        assert not any("does not match" in reason for reason in reasons)
        assert not any("Mutual of America stamp was not found" in reason for reason in reasons)

        changed = apply_cover_date(doc)
        today = cover_date_text()
        updated = doc[0].get_text("text")
        assert any("Cover letter date set to" in note for note in changed)
        assert today in updated
        assert "March 8, 2022" not in updated
        date_check = _cover_date_check(doc)
        assert date_check.passed is True
        assert date_check.detail == today
        words = doc[0].get_text("words")
        date_y = min(word[1] for word in words if word[4] == today.split()[0])
        company_y = min(word[1] for word in words if word[4] == "Soboba" and word[0] < 80)
        assert date_y < company_y
    finally:
        doc.close()


def test_soboba_cover_stops_when_excel_company_address_or_pye_differ():
    doc = build_soboba_cover()
    try:
        profile = extract_plan_profile(doc)
        excel = parse_excel(
            _soboba_excel(
                **{
                    "Company Name": "Other Employer",
                    "Company Address": "1 Main Street, Austin, TX 78701",
                    "PYE": "06/30/2022",
                    "Plan Name": "Other Plan",
                }
            )
        )
        reasons = stop_reasons(
            doc,
            profile,
            ["123456 2025 401k Valuation Pkg.pdf"],
            excel_plan_name=excel["plan_name"],
            pdf_plan_name=profile.plan_name,
            excel_company=excel["company_name"],
            excel_address=excel["company_address"],
            excel_pye=excel["plan_year_end"],
            cover_company=profile.company_name,
            cover_address=profile.company_address,
            cover_pye=profile.plan_year_end,
        )
    finally:
        doc.close()
    joined = "\n".join(reasons)
    assert "company name on the cover letter does not match" in joined
    assert "company address on the cover letter does not match" in joined
    assert "plan year end on the cover letter does not match" in joined
    assert "plan name in the valuation package Excel does not match" in joined


def test_review_fails_cover_fields_when_letter_block_is_missing():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Annual Valuation Report\nNo cover letter header.", fontsize=11)
    try:
        profile = extract_plan_profile(doc)
        review = validate(profile)
        by_code = {item.code: item for item in review.items}
        assert profile.company_name is None
        assert profile.company_address is None
        assert profile.plan_name is None
        assert profile.plan_year_end is None
        assert by_code["cover_company"].passed is False
        assert by_code["cover_address"].passed is False
        assert by_code["cover_plan_name"].passed is False
        assert by_code["cover_plan_year_end"].passed is False
    finally:
        doc.close()

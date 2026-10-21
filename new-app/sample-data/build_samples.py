"""Build fictional 401(k) and 403(b) sample packages and run them through the app.

Input PDFs and Excel files are written under sample-data. Expected outputs are
produced by process_uploads, not drawn by hand.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fitz
from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent

HARBOR = {
    "number": "555001",
    "plan": "HARBOR MANUFACTURING 401(K) PLAN",
    "company": "HARBOR MANUFACTURING, LLC",
    "address": "10 Harbor Way, Suite 200, Boston, MA 02110",
    "street": ["10 Harbor Way", "Suite 200", "Boston, MA 02110"],
    "pye": "12/31/2025",
    "pye_long": "December 31, 2025",
    "year_line": "Plan Year: 01/01/2025 - 12/31/2025",
    "future_pye": "12/31/2026",
    "begin": "2025",
    "type_label": "401(k)",
    "file_type": "401k",
}

NORTHWIND = {
    **HARBOR,
    "number": "555002",
    "plan": "NORTHWIND LOGISTICS 401(K) PLAN",
    "company": "NORTHWIND LOGISTICS, LLC",
    "address": "400 Warehouse Road, Chicago, IL 60601",
    "street": ["400 Warehouse Road", "Chicago, IL 60601"],
}

GRACE = {
    "number": "555403",
    "plan": "GRACE MEDICAL HOME, INC. 403(B) PLAN",
    "company": "GRACE MEDICAL HOME, INC.",
    "address": "88 Chapel Street, Orlando, FL 32801",
    "street": ["88 Chapel Street", "Orlando, FL 32801"],
    "pye": "12/31/2025",
    "pye_long": "December 31, 2025",
    "year_line": "Plan Year: 01/01/2025 - 12/31/2025",
    "future_pye": "12/31/2026",
    "begin": "2025",
    "type_label": "403(b)",
    "file_type": "403b",
}


def _stamp(page: fitz.Page) -> None:
    page.draw_rect(fitz.Rect(430, 24, 560, 52), color=(0.75, 0.08, 0.08), fill=(0.75, 0.08, 0.08))
    page.draw_rect(fitz.Rect(430, 56, 560, 92), color=(0.05, 0.08, 0.35), fill=(0.05, 0.08, 0.35))
    page.insert_text((436, 44), "MUTUAL OF AMERICA", fontsize=8, fontname="hebo", color=(1, 1, 1))
    page.insert_text((436, 76), "FINANCIAL GROUP", fontsize=8, fontname="hebo", color=(1, 1, 1))


def _new() -> fitz.Document:
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    return doc


def _write(doc: fitz.Document, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    doc.close()


def _identity(plan: dict, *, pye: str | None = None) -> str:
    end = pye or plan["pye"]
    return "\n".join(
        [
            f"Plan Number: {plan['number']}",
            f"Plan Name: {plan['plan']}",
            f"Company Name: {plan['company']}",
            f"Plan Year End: {end}",
        ]
    )


def _report(path: Path, title: str, plan: dict, body: str, *, pye: str | None = None, stamp: bool = False) -> None:
    doc = _new()
    page = doc[0]
    if stamp:
        _stamp(page)
    page.insert_text((54, 72), title, fontsize=14, fontname="hebo")
    page.insert_textbox(
        fitz.Rect(54, 96, 560, 760),
        _identity(plan, pye=pye) + "\n\n" + body,
        fontsize=11,
        fontname="helv",
    )
    _write(doc, path)


def _cover_page(doc: fitz.Document, plan: dict) -> None:
    page = doc.new_page(width=595.28, height=841.89)
    _stamp(page)
    letter = "\n".join(
        [
            "September 9, 2026",
            "",
            plan["company"],
            *plan["street"],
            "",
            f"RE: {plan['plan']}",
            "",
            "We are pleased to provide you with our completed administrative review of your",
            "qualified retirement plan for the period ending " + plan["pye"] + ".",
            "Please read the Action Required section of the Annual Valuation Report.",
            "",
            f"Plan Number: {plan['number']}",
            f"Company Name: {plan['company']}",
            f"Address: {plan['address']}",
            plan["year_line"],
            "Testing Method: CURRENT",
            "Safe Harbor: No",
            "Mutual of America Financial Group",
        ]
    )
    page.insert_textbox(fitz.Rect(54, 120, 400, 780), letter, fontsize=11, fontname="helv")


def _packet(path: Path, plan: dict) -> None:
    """Cover plus the front-matter pages the app keeps, fills, or removes."""
    from services.package_builder import (
        AFTER_12_CURRENT_NOTICE,
        AFTER_12_PRIOR_NOTICE,
        CONTRIBUTIONS_BODY,
        FAILURE_NOTICE,
        NOTICE_415,
        PARAGRAPHS,
        RECAP_BULLETS,
        SAMPLE_LETTER_402G,
        SAMPLE_LETTER_415,
        SAMPLE_LETTER_ADP_ACP,
        _action_page,
        _excess_notice_page,
        _styled_page,
        write_recap_page,
    )

    family = plan["file_type"]
    paragraphs = list(PARAGRAPHS)
    current_notice = FAILURE_NOTICE
    after_current = AFTER_12_CURRENT_NOTICE
    after_prior = AFTER_12_PRIOR_NOTICE
    if family == "403b":
        paragraphs = [(heading.replace("ADP/ACP", "ACP"), body) for heading, body in paragraphs]
        heading, body = paragraphs[2]
        paragraphs[2] = (heading, body + "\n\nReview the Excess Summary. Return Form W-4P for each affected participant.")
        current_notice = (
            FAILURE_NOTICE.replace("For current-method testing", "Current method testing")
            .replace("ADP/ACP test is", "ACP test is")
            .replace("Form W-4R", "Form W-4P")
            .replace("fw4r.pdf", "fw4p.pdf")
        )
        if "Current method testing" not in current_notice:
            current_notice = current_notice.replace(
                "Failed Compliance Testing",
                "Failed Compliance Testing\n\nCurrent method testing",
                1,
            )
    else:
        current_notice = "For current-method testing\n\n" + current_notice

    doc = fitz.open()
    _cover_page(doc, plan)
    header = (
        ("Annual Valuation Report", 16, "hebo"),
        ("January 1, 2025 - December 31, 2025", 11, "helv"),
        (plan["plan"], 11, "hebo"),
        (plan["number"], 12, "hebo"),
    )
    _action_page(
        doc,
        [
            ("red", paragraphs[0]),
            ("red", paragraphs[1]),
            ("red", paragraphs[2]),
            ("red", ("IMMEDIATE ACTION REQUIRED - CONTRIBUTIONS", CONTRIBUTIONS_BODY)),
        ],
        header=True,
        number=2,
    )
    # The shared helper always prints the Our House header. Redraw is not available,
    # so the first action page header is replaced by drawing the sample header on a copy below.
    _replace_header(doc[1], header)
    _action_page(doc, [("red", paragraphs[4]), ("red", paragraphs[3])], number=3)
    _action_page(doc, [("attention", paragraphs[5]), ("green", paragraphs[6])], number=4)
    identity = ("January 1, 2025 - December 31, 2025", plan["plan"], plan["number"])
    _excess_notice_page(doc, after_current, identity, number=5)
    _excess_notice_page(doc, after_prior, identity, number=6)
    _excess_notice_page(doc, current_notice, identity, number=7)
    notice_415 = "\n".join(
        [
            "Annual Additions (IRC 415) Test Failure Information",
            "January 1, 2025 - December 31, 2025",
            plan["plan"],
            plan["number"],
            "",
            "\n".join(NOTICE_415.splitlines()[4:]),
        ]
    )
    _styled_page(doc, notice_415, number=8)
    _styled_page(doc, SAMPLE_LETTER_ADP_ACP, number=9)
    _styled_page(doc, SAMPLE_LETTER_402G, number=10)
    _styled_page(doc, SAMPLE_LETTER_415, number=11)
    recap = doc.new_page(width=595.28, height=841.89)
    bullets = list(RECAP_BULLETS)
    if family == "403b":
        bullets.append(
            "A 403(b) plan may allow a special catch-up for an employee with fifteen or more years of service."
        )
    write_recap_page(
        recap,
        [
            "YEAR END RECAP",
            "January 1, 2025 - December 31, 2025",
            plan["plan"],
            plan["number"],
            "Important Information",
        ],
        bullets,
        number=12,
    )
    _write(doc, path)


def _replace_header(page: fitz.Page, header: tuple[tuple[str, float, str], ...]) -> None:
    """Cover the stock Our House header and write this plan's header."""
    page.add_redact_annot(fitz.Rect(40, 40, page.rect.width - 40, 155), fill=(1, 1, 1))
    page.apply_redactions()
    y = 56.0
    for text, size, font in header:
        width = fitz.get_text_length(text, fontname=font, fontsize=size)
        page.insert_text(((page.rect.width - width) / 2, y), text, fontsize=size, fontname=font)
        y += size + 6
    page.draw_line(fitz.Point(48, y), fitz.Point(page.rect.width - 48, y), color=(0, 0, 0), width=1)


def _excel(path: Path, plan: dict, *, top_heavy: str, per_payroll: str = "Yes", reclass: str = "No") -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "Val Assembly"
    headers = [
        "Omni Plan Number",
        "Plan Name",
        "PYE",
        "Plan Type",
        "Company Name",
        "Company Address",
        "Rework",
        "Rush",
        "Per Payroll Match",
    ]
    values = [
        plan["number"],
        plan["plan"],
        plan["pye"],
        plan["type_label"],
        plan["company"],
        plan["address"],
        "No",
        "No",
        per_payroll,
    ]
    for col, header in enumerate(headers, start=1):
        sheet.cell(1, col, header)
        sheet.cell(2, col, values[col - 1])
    extras = [
        (6, "If this is a 457 Plan is it a Non-Governmental plan? (Yes/No)", "No"),
        (7, "Do you have HCE Current Year? (yes/no)", "Yes"),
        (8, "Do you have HCE Future year? (yes/no)", "Yes"),
        (9, "Plan is Top heavy? (yes/no/403b n/a)", top_heavy),
        (10, "ADP/ACP Prior or current method test? (Prior / current / N/A SH)", "Current"),
        (11, "ADP/ACP Failure but All returns are reclassified (no returns needed)? (yes/no/N/A)", reclass),
        (12, "Annual allocation (per document including true up)? (yes / no)", "No"),
        (13, "Notes (if needed)", ""),
    ]
    for row, label, value in extras:
        sheet.cell(row, 1, label)
        sheet.cell(row, 2, value)
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)


def _summary(path: Path, plan: dict, lines: list[str]) -> None:
    """Plan name stands alone so the summary parser does not keep the label."""
    doc = _new()
    page = doc[0]
    text = "\n".join(
        [
            "Compliance Testing Summary of Results",
            f"Plan Year End: {plan['pye_long']}",
            plan["plan"],
            plan["number"],
            "",
            *lines,
            "",
            f"Plan Number: {plan['number']}",
            f"Plan Name: {plan['plan']}",
            f"Company Name: {plan['company']}",
            f"Plan Year End: {plan['pye']}",
        ]
    )
    page.insert_textbox(fitz.Rect(54, 72, 560, 760), text, fontsize=11, fontname="helv")
    _write(doc, path)


def _file_tag(plan: dict) -> str:
    """Report keywords must be the longest token. Do not put 401k or 403b here."""
    return f"{plan['number']} {plan['begin']}"


def _participants() -> str:
    return "\n".join(
        [
            "Participant listing (fictional). No Social Security numbers are printed.",
            "Adams, Jordan    Deferral 6,000.00    Match 3,000.00",
            "Brooks, Riley    Deferral 4,500.00    Match 2,250.00",
            "Chen, Avery      Deferral 8,000.00    Match 4,000.00",
        ]
    )


def _reset(base: Path) -> Path:
    pdfs = base / "input-pdfs"
    excel = base / "input-excel"
    if pdfs.exists():
        shutil.rmtree(pdfs)
    if excel.exists():
        shutil.rmtree(excel)
    pdfs.mkdir(parents=True)
    return pdfs


def build_401k_pass(base: Path) -> None:
    pdfs = _reset(base)
    plan = HARBOR
    tag = _file_tag(plan)
    _packet(pdfs / f"{tag} {plan['file_type']} Valuation Pkg.pdf", plan)
    _summary(
        pdfs / f"{tag} ResultSumm.pdf",
        plan,
        [
            "416 Top Heavy Determination",
            "Tested: 8.85% to Key Employees",
            "Plan is not Top Heavy",
            "",
            "410(b) Coverage Test",
            "Standard: Pass Ratio percent 100%",
            "401(k): Pass Ratio percent 100%",
            "401(m): Pass Ratio percent 100%",
            "",
            "401(a)(4) Test",
            "Tested: Pass",
            "",
            "414(s) Test",
            "Tested: Pass",
            "",
            "Average Benefit Percentage Test",
            "Tested: Pass",
            "",
            "402(g) Deferral Limits",
            "Tested: Pass",
            "",
            "415(c) Annual Additions",
            "Tested: Pass",
            "",
            "Average Deferral Percentage (ADP)",
            "Tested: Pass",
            "",
            "Average Contribution Percentage (ACP)",
            "Tested: Pass",
        ],
    )
    _report(pdfs / f"{tag} HCEKey.pdf", "HCE/Key", plan, "Highly Compensated Employees for the current plan year.\n\nBrooks, Riley    HCE")
    _report(
        pdfs / f"{tag} FYHCE.pdf",
        "Future HCE",
        plan,
        "Employees projected to be highly compensated for the following plan year.\n\nBrooks, Riley",
        pye=plan["future_pye"],
    )
    adp = fitz.open()
    for title, body in (
        ("ADP/ACP Summary", "ADP Test: Pass\nACP Test: Pass\nTEST RESULTS\nThe ADP for the 40 NHCE(s) is 4.00% (160.00/40)."),
        ("ADP/ACP Test Detail", "Detail of deferral and match rates.\n\n" + _participants()),
        ("ADP/ACP Corrections", "This plan passes. No contribution refund is required."),
    ):
        page = adp.new_page(width=612, height=792)
        page.insert_text((54, 72), title, fontsize=14, fontname="hebo")
        page.insert_textbox(fitz.Rect(54, 96, 560, 760), _identity(plan) + "\n\n" + body, fontsize=11, fontname="helv")
    _write(adp, pdfs / f"{tag} ADP.pdf")
    _report(pdfs / f"{tag} 410.pdf", "410(b) Test", plan, "Standard: Pass\n401(k): Pass\n401(m): Pass\nRatio percent 100%")
    _report(pdfs / f"{tag} 402.pdf", "402(g) Test", plan, "402(g) Deferral Limits\nTested: Pass\nNo participant exceeded the calendar-year deferral limit.")
    _report(pdfs / f"{tag} 415.pdf", "415 Limit Test", plan, "415(c) Annual Additions\nTested: Pass\nNo annual addition exceeded the limit.")
    _report(pdfs / f"{tag} TH.pdf", "Top Heavy Test", plan, "Top Heavy Percent: 8.85%\nPlan is not Top Heavy")
    _report(pdfs / f"{tag} Census.pdf", "Census", plan, _participants())
    _report(
        pdfs / f"{tag} Contri.pdf",
        "Contribution Analysis",
        plan,
        "Employer match and salary deferral totals by participant.\n\n" + _participants(),
    )
    _report(pdfs / f"{tag} 401a4.pdf", "401(a)(4) Test", plan, "401(a)(4) Test\nTested: Pass")
    _report(pdfs / f"{tag} 414s.pdf", "414(s) Test", plan, "414(s) Test\nTested: Pass")
    _report(pdfs / f"{tag} ABPT.pdf", "Average Benefit Percentage Test", plan, "Average Benefit Percentage Test\nTested: Pass")
    _excel(base / "input-excel" / "Val Assembly.xlsx", plan, top_heavy="No")


def build_401k_current_fail(base: Path) -> None:
    pdfs = _reset(base)
    plan = NORTHWIND
    tag = _file_tag(plan)
    _packet(pdfs / f"{tag} {plan['file_type']} Valuation Pkg.pdf", plan)
    _summary(
        pdfs / f"{tag} ResultSumm.pdf",
        plan,
        [
            "416 Top Heavy Determination",
            "Tested: 12.40% to Key Employees",
            "Plan is not Top Heavy",
            "",
            "410(b) Coverage Test",
            "Standard: Pass Ratio percent 100%",
            "401(k): Pass Ratio percent 100%",
            "401(m): Pass Ratio percent 100%",
            "",
            "402(g) Deferral Limits",
            "Tested: Pass",
            "",
            "415(c) Annual Additions",
            "Tested: Pass",
            "",
            "Average Deferral Percentage (ADP)",
            "Tested: Fail",
            "",
            "Average Contribution Percentage (ACP)",
            "Tested: Fail",
            "",
            "Contribution refunds to participants are required.",
            "Correction Within 12 Months",
        ],
    )
    _report(pdfs / f"{tag} HCEKey.pdf", "HCE/Key", plan, "Chen, Avery    HCE")
    _report(pdfs / f"{tag} FYHCE.pdf", "Future HCE", plan, "Chen, Avery", pye=plan["future_pye"])
    adp = fitz.open()
    pages = [
        ("ADP/ACP Summary", "ADP Test: Fail\nACP Test: Fail\nTEST RESULTS\nThe ADP for the 65 NHCE(s) is 2.21% (143.65/65)."),
        ("ADP/ACP Test Detail", "Detail of the failed ADP and ACP rates.\n\n" + _participants()),
        (
            "ADP/ACP Corrections",
            "\n".join(
                [
                    "This plan passes using the refund amount corrections.",
                    "This plan will also qualify with the following ADP QNEC/ACP QNEC contributions to NHCEs.",
                    "ADP QNEC $142,540.41",
                    "ACP QNEC $42,814.34",
                    "Deferral Refund: $17,571.00",
                    "Match Refund: $116.60",
                    "Contribution refunds to participants are required.",
                    "Correction Within 12 Months",
                ]
            ),
        ),
    ]
    for title, body in pages:
        page = adp.new_page(width=612, height=792)
        page.insert_text((54, 72), title, fontsize=14, fontname="hebo")
        page.insert_textbox(fitz.Rect(54, 96, 560, 760), _identity(plan) + "\n\n" + body, fontsize=11, fontname="helv")
    _write(adp, pdfs / f"{tag} ADP.pdf")
    for name, title, body in (
        ("410.pdf", "410(b) Test", "Standard: Pass\n401(k): Pass\n401(m): Pass"),
        ("402.pdf", "402(g) Test", "402(g) Deferral Limits\nTested: Pass"),
        ("415.pdf", "415 Limit Test", "415(c) Annual Additions\nTested: Pass"),
        ("TH.pdf", "Top Heavy Test", "Top Heavy Percent: 12.40%\nPlan is not Top Heavy"),
        ("Census.pdf", "Census", _participants()),
        ("Contri.pdf", "Contribution Analysis", "Employer match totals.\n\n" + _participants()),
    ):
        _report(pdfs / f"{tag} {name}", title, plan, body)
    _excel(base / "input-excel" / "Val Assembly.xlsx", plan, top_heavy="No", reclass="No")


def build_403b_pass(base: Path) -> None:
    pdfs = _reset(base)
    plan = GRACE
    tag = _file_tag(plan)
    _packet(pdfs / f"{tag} {plan['file_type']} Valuation Pkg.pdf", plan)
    _summary(
        pdfs / f"{tag} ResultSumm.pdf",
        plan,
        [
            "416 Top Heavy Determination",
            "Tested: 5.00% to Key Employees",
            "Plan is not Top Heavy",
            "",
            "410(b) Coverage Test",
            "Standard: Pass Ratio percent 100%",
            "401(k): Pass Ratio percent 100%",
            "401(m): Pass Ratio percent 100%",
            "",
            "402(g) Deferral Limits",
            "Tested: Pass",
            "",
            "415(c) Annual Additions",
            "Tested: Pass",
            "",
            "Average Contribution Percentage (ACP)",
            "Tested: Pass",
            "",
            "Benefits, Rights and Features",
            "Tested: Pass",
        ],
    )
    _report(pdfs / f"{tag} HCEKey.pdf", "HCE/Key", plan, "Patel, Morgan    HCE")
    _report(pdfs / f"{tag} FYHCE.pdf", "Future HCE", plan, "Patel, Morgan", pye=plan["future_pye"])
    _report(pdfs / f"{tag} ACP Test.pdf", "ACP Test", plan, "ACP Test: Pass\nTEST RESULTS\nNo excess contribution is required.")
    _report(pdfs / f"{tag} 402.pdf", "402(g) Test", plan, "402(g) Deferral Limits\nTested: Pass")
    _report(pdfs / f"{tag} 415.pdf", "415 Limit Test", plan, "415(c) Annual Additions\nTested: Pass")
    _report(pdfs / f"{tag} TH.pdf", "Top Heavy Test", plan, "Top Heavy Percent: 5.00%\nPlan is not Top Heavy")
    _report(pdfs / f"{tag} Census.pdf", "Census", plan, _participants())
    _report(pdfs / f"{tag} Contri.pdf", "Contribution Analysis", plan, "Employer contribution totals.\n\n" + _participants())
    _report(pdfs / f"{tag} BRF.pdf", "BRF Test", plan, "Benefits, Rights and Features\nTested: Pass")
    _excel(base / "input-excel" / "Val Assembly.xlsx", plan, top_heavy="403b N/A", per_payroll="No")


def build_stop_examples(base: Path) -> None:
    plan = HARBOR
    summary = _reset(base / "unresolved-summary")
    _summary(
        summary / f"{plan['number']} {plan['begin']} ResultSumm.pdf",
        plan,
        ["416 Top Heavy Determination", "Plan is\\is not Top Heavy", "ADP Test: Pass/Fail"],
    )
    census = _reset(base / "masked-ssn")
    _report(
        census / f"{plan['number']} {plan['begin']} Census.pdf",
        "Census",
        plan,
        "Adams, Jordan\nSSN XXX-XX-1234",
    )


def _uploads(folder: Path) -> list[tuple[str, bytes]]:
    files: list[tuple[str, bytes]] = []
    pdfs = folder / "input-pdfs"
    excel = folder / "input-excel"
    if pdfs.is_dir():
        files.extend((path.name, path.read_bytes()) for path in sorted(pdfs.glob("*.pdf")))
    if excel.is_dir():
        files.extend((path.name, path.read_bytes()) for path in sorted(excel.glob("*.xlsx")))
    return files


def run_package(folder: Path, *, stops: bool) -> dict:
    import services.save_service as save_service
    from fastapi import HTTPException
    from services.orchestrator import process_uploads

    out = folder / "expected-output"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    save_service.OUTPUT_DIR = out
    record: dict = {"folder": str(folder.relative_to(ROOT)), "stops": stops}
    try:
        result = process_uploads(_uploads(folder), auto_order=True, check_assembly_stops=stops)
    except HTTPException as exc:
        record["stopped"] = True
        record["detail"] = exc.detail
        (out / "assembly-stopped.txt").write_text(str(exc.detail), encoding="utf-8")
        return record
    record["stopped"] = False
    record["filename"] = result.filename
    record["email_subject"] = result.email_subject
    record["warnings"] = result.warnings
    profile = result.plan_profile
    record["profile"] = {
        "plan_number": profile.plan_number,
        "plan_name": profile.plan_name,
        "company_name": profile.company_name,
        "company_address": profile.company_address,
        "plan_type": profile.plan_type,
        "plan_year_end": profile.plan_year_end,
        "beginning_plan_year": profile.beginning_plan_year,
        "testing_method": profile.testing_method,
        "top_heavy": profile.top_heavy,
        "adp_failed": profile.adp_failed,
        "acp_failed": profile.acp_failed,
        "fail_402g": profile.fail_402g,
        "fail_415": profile.fail_415,
        "returns_required": profile.returns_required,
        "safe_harbor": profile.safe_harbor,
        "adp_qnec": profile.adp_qnec,
        "acp_qnec": profile.acp_qnec,
        "total_qnec": profile.total_qnec,
    }
    saved = Path(result.pdf_path)
    target = out / result.filename
    if saved.resolve() != target.resolve():
        shutil.copy(saved, target)
    doc = fitz.open(target)
    try:
        record["page_count"] = doc.page_count
        record["bookmarks"] = [{"level": row[0], "title": row[1], "page": row[2]} for row in doc.get_toc()]
    finally:
        doc.close()
    if result.review:
        record["review"] = [
            {"code": item.code, "passed": item.passed, "detail": item.detail}
            for item in result.review.items
        ]
    (out / "run-result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def main() -> None:
    packages = {
        "401k/pass": build_401k_pass,
        "401k/current-fail": build_401k_current_fail,
        "403b/pass": build_403b_pass,
    }
    for name, builder in packages.items():
        builder(ROOT / name)
    build_stop_examples(ROOT / "401k/scenarios")
    results = []
    for name in packages:
        results.append(run_package(ROOT / name, stops=True))
    for name in ("401k/scenarios/unresolved-summary", "401k/scenarios/masked-ssn"):
        results.append(run_package(ROOT / name, stops=True))
    (ROOT / "run-results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    for item in results:
        status = "STOPPED" if item.get("stopped") else item.get("filename")
        print(item["folder"], status)


if __name__ == "__main__":
    main()

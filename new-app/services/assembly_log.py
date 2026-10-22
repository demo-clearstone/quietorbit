"""Val Assembly Log in the column layout of logs-updation.xlsx.

Tester-owned columns (FIS, related plans, MEP, safe harbor) are left blank.
Failed Comp Limit is always N/A for MOA.
"""

from __future__ import annotations

import re
import warnings
from copy import copy
from datetime import datetime
from pathlib import Path

import fitz
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.worksheet.datavalidation import DataValidation

from config.settings import ROOT
from models.plan_profile import PlanProfile
from services.source_profile import parse_summary_text

_TEMPLATE = ROOT / "logs-updation.xlsx"
_INSTRUCTION = "Update it from Result Summary"

_HEADERS = [
    "Omni Plan Number",
    "Plan Name",
    "Are there HCE on the Future HCE Report",
    "Are there HCE Hce/Key report (Current Year HCE)",
    "Did you complete any Allocations (Annual / Varaince or Both)",
    "Failed ADP/ACP P/F/N/A",
    "Failed 402g/457 Def Limit",
    "Failed 410b",
    "Failed ABP",
    "Failed 414s",
    "Failed 401a4",
    "Failed 415",
    "Top Heavy",
    "Failed BRF",
    "Failed Comp Limit",
    "Was FIS instructed to Proceed without Document, Amendment, Against document coding",
    "",
    "Are there any Related Plans",
    "Is this a MEP Plan",
    "Is this plan Safe Harbor",
]
_SUMMARY = re.compile(r"result summary|testing summary of results|test summary", re.I)
_PERSON = re.compile(r"(?m)^[A-Z][A-Za-z' .-]+,\s+[A-Z]")
_NONE = re.compile(r"\bno\s+hce\b|there are no hce|0\s+hce", re.I)


_SENT_COL = 22
_BUILD_COL = 23


def append_row(
    log_path: Path,
    profile: PlanProfile,
    filename: str,
    job_id: str,
    doc: fitz.Document | None = None,
    finished_at: datetime | None = None,
    elapsed_seconds: float | None = None,
) -> Path:
    """Append one assembled plan using the logs-updation.xlsx columns."""
    del filename, job_id
    log_path.parent.mkdir(parents=True, exist_ok=True)
    saved: list[tuple[list, str]] = []
    if log_path.is_file():
        book = _load_workbook(log_path)
        sheet = book.active
        if not _uses_template_layout(sheet):
            saved = _saved_rows(sheet)
            book, sheet = _book_from_template()
            for old_values, old_note in saved:
                _write_data_row(sheet, _next_data_row(sheet), old_values, old_note)
    else:
        book, sheet = _book_from_template()
    values, note = build_log_row(profile, doc)
    row = _next_data_row(sheet)
    _write_data_row(sheet, row, values, note)
    _ensure_build_headers(sheet)
    if finished_at is not None:
        sheet.cell(row, _SENT_COL).value = _sent_label(finished_at)
    if elapsed_seconds is not None:
        sheet.cell(row, _BUILD_COL).value = _elapsed_label(elapsed_seconds)
    if not sheet.data_validations.dataValidation:
        _add_lists(sheet)
    book.save(log_path)
    return log_path


def _uses_template_layout(sheet) -> bool:
    fill = sheet["A1"].fill
    color = ""
    if fill.fgColor is not None and fill.patternType == "solid" and fill.fgColor.type == "rgb":
        color = str(fill.fgColor.rgb or "")
    return sheet.row_dimensions[1].height == 116 and color.endswith("808080") and _instruction_row(sheet) is None


def _instruction_row(sheet) -> int | None:
    for index in range(3, (sheet.max_row or 2) + 1):
        value = sheet.cell(index, 1).value
        if isinstance(value, str) and value.startswith(_INSTRUCTION):
            return index
    return None


def _book_from_template():
    if _TEMPLATE.is_file():
        book = _load_workbook(_TEMPLATE)
        sheet = book.active
        _strip_instructions(sheet)
        return book, sheet
    book = Workbook()
    sheet = book.active
    sheet.title = "Val Assembly Log"
    _write_headers(sheet)
    return book, sheet


def _load_workbook(path: Path):
    """Ignore only openpyxl's warning for unsupported Excel validation extensions."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Data Validation extension is not supported and will be removed",
            category=UserWarning,
            module=r"openpyxl\..*",
        )
        return load_workbook(path)


def _strip_instructions(sheet) -> None:
    """Keep the header formatting. Do not copy the fill-instruction notes."""
    start = _instruction_row(sheet)
    if start is None:
        return
    last = sheet.max_row or start
    sheet.delete_rows(start, last - start + 1)
    for index in list(sheet.row_dimensions):
        if index >= start:
            del sheet.row_dimensions[index]


def _saved_rows(sheet) -> list[tuple[list, str]]:
    if sheet.cell(1, 1).value != _HEADERS[0]:
        return []
    rows: list[tuple[list, str]] = []
    for index in range(3, (sheet.max_row or 2) + 1):
        first = str(sheet.cell(index, 1).value or "").strip()
        if not first.isdigit():
            continue
        values = [sheet.cell(index, col).value for col in range(1, 22)]
        comment = sheet.cell(index, 5).comment
        rows.append((values, comment.text if comment is not None else ""))
    return rows


def _clone_row_style(sheet, source: int, target: int) -> None:
    for col in range(1, 22):
        src = sheet.cell(source, col)
        dst = sheet.cell(target, col)
        if src.has_style:
            dst.font = copy(src.font)
            dst.border = copy(src.border)
            dst.fill = copy(src.fill)
            dst.number_format = src.number_format
            dst.protection = copy(src.protection)
            dst.alignment = copy(src.alignment)
    height = sheet.row_dimensions[source].height
    if height:
        sheet.row_dimensions[target].height = height


def _write_data_row(sheet, row: int, values: list, note: str) -> None:
    for col, value in enumerate(values, start=1):
        sheet.cell(row, col).value = value if value not in ("",) else None
    if note:
        sheet.cell(row, 5).comment = Comment(note, "MOA")


def build_log_row(profile: PlanProfile, doc: fitz.Document | None = None) -> tuple[list[str], str]:
    summary = _summary_text(doc)
    parsed = parse_summary_text(summary) if summary else {}
    number = str(parsed.get("plan_number") or profile.plan_number or "")
    name = str(parsed.get("plan_name") or profile.plan_name or "")
    allocation, allocation_note = _allocation(profile)
    values = [
        number,
        name,
        _hce_answer(profile.hce_future, _report_text(doc, r"future\s+hce")),
        _hce_answer(profile.hce_current, _report_text(doc, r"hce\s*/?\s*key", skip=r"future\s+hce")),
        allocation,
        _adp_status(profile, summary),
        _flag_status(profile.fail_402g, summary, r"402\s*\(?\s*g\s*\)?|457", _has_section(profile, "402(g)")),
        _test_status(profile, summary, "410(b)", r"410\s*\(?\s*b\s*\)?"),
        _test_status(profile, summary, "Average Benefit Percentage Test", r"average benefit|ABPT|\bABP\b"),
        _test_status(profile, summary, "414(s)", r"414\s*\(\s*s\s*\)"),
        _test_status(profile, summary, "401(a)(4)", r"401\s*\(\s*a\s*\)\s*\(\s*4\s*\)"),
        _flag_status(profile.fail_415, summary, r"415(?:\s*\(\s*c\s*\))?|Annual Additions", _has_section(profile, "415")),
        _top_heavy(profile, summary),
        _test_status(profile, summary, "BRF", r"benefits,?\s+rights|\bBRF\b"),
        "N/A",
        "",
        "",
        "",
        "",
        "",
    ]
    return values, allocation_note


def _ensure_build_headers(sheet) -> None:
    if not sheet.cell(1, _SENT_COL).value:
        sheet.cell(1, _SENT_COL).value = "Date sent back to tester"
    if not sheet.cell(1, _BUILD_COL).value:
        sheet.cell(1, _BUILD_COL).value = "Time to build"


def _sent_label(when: datetime) -> str:
    clock = when.strftime("%I:%M %p").lstrip("0")
    return f"{when.month}/{when.day}/{when.year} {clock}"


def _elapsed_label(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    minutes, secs = divmod(total, 60)
    if minutes:
        return f"{minutes} min {secs} sec"
    return f"{secs} sec"


def _write_headers(sheet) -> None:
    for col, header in enumerate(_HEADERS, start=1):
        sheet.cell(1, col, header)
    sheet.cell(2, 5, "Allocation Completed")
    _add_lists(sheet)


def _add_lists(sheet) -> None:
    lists = (
        ("C3:D500", '"Yes,No"'),
        ("E3:E500", '"Variance,Annual,Annual-Var"'),
        ("F3:L500", '"P,F,N/A"'),
        ("M3:M500", '"Yes,No"'),
        ("N3:O500", '"P,F,N/A"'),
    )
    for cells, formula in lists:
        rule = DataValidation(type="list", formula1=formula, allow_blank=True)
        rule.add(cells)
        sheet.add_data_validation(rule)


def _next_data_row(sheet) -> int:
    last = 2
    for index in range(3, (sheet.max_row or 2) + 1):
        if sheet.cell(index, 1).value not in (None, ""):
            last = index
    nxt = last + 1
    if sheet.cell(3, 1).has_style and not sheet.cell(nxt, 1).has_style:
        _clone_row_style(sheet, 3, nxt)
    return nxt


def _allocation(profile: PlanProfile) -> tuple[str, str]:
    notes = profile.assembly_notes or ""
    low = notes.lower()
    both = profile.annual_allocation is True and profile.true_up is True or re.search(r"annual allocation and true-?up both", low)
    annual_only = profile.annual_allocation is True or (re.search(r"annual allocation", low) and not re.search(r"true-?up", low))
    true_up = profile.true_up is True or bool(re.search(r"true-?up", low))
    if both:
        return "Annual-Var", ""
    if annual_only:
        return "Annual", ""
    if true_up and not re.search(r"(?<!no )variance", low):
        return "Variance", "0.00 variance"
    if profile.contributions_required is True:
        return "Variance", ""
    return "", ""


def _hce_answer(flag: bool | None, report_text: str) -> str:
    has_person = bool(_PERSON.search(report_text or ""))
    if flag is True or has_person:
        return "Yes"
    if flag is False or _NONE.search(report_text or ""):
        return "No"
    return ""


def _adp_status(profile: PlanProfile, summary: str) -> str:
    adp = _result_near(summary, r"Average Deferral Percentage|\bADP\b")
    acp = _result_near(summary, r"Average Contribution Percentage|\bACP\b")
    if profile.adp_failed or profile.acp_failed or adp == "fail" or acp == "fail":
        return "F"
    present = _has_section(profile, "ADP/ACP") or adp is not None or acp is not None
    if adp == "pass" or acp == "pass" or profile.adp_failed is False or profile.acp_failed is False:
        return "P"
    return "N/A" if not present else ""


def _flag_status(flag: bool | None, summary: str, pattern: str, present: bool) -> str:
    result = _result_near(summary, pattern)
    if flag is True or result == "fail":
        return "F"
    if flag is False or result == "pass":
        return "P"
    return "N/A" if not present and result is None else ""


def _test_status(profile: PlanProfile, summary: str, section: str, pattern: str) -> str:
    result = _result_near(summary, pattern)
    present = _has_section(profile, section) or result is not None
    if result == "fail":
        return "F"
    if result == "pass":
        return "P"
    return "N/A" if not present else ""


def _top_heavy(profile: PlanProfile, summary: str) -> str:
    if re.search(r"plan is not top heavy", summary or "", re.I):
        return "No"
    if re.search(r"plan is top heavy", summary or "", re.I):
        return "Yes"
    if profile.top_heavy is True:
        return "Yes"
    if profile.top_heavy is False:
        return "No"
    return ""


def _has_section(profile: PlanProfile, name: str) -> bool:
    return any(section.name == name for section in profile.detected_sections)


def _result_near(text: str, pattern: str) -> str | None:
    match = re.search(r"(?:" + pattern + r").{0,80}?\b(Pass|Fail)\b", text or "", re.I | re.S)
    if not match:
        return None
    return match.group(1).lower()


def _summary_text(doc: fitz.Document | None) -> str:
    if doc is None:
        return ""
    parts = [page.get_text("text") or "" for page in doc if _SUMMARY.search(page.get_text("text") or "")]
    return "\n".join(parts)


def _report_text(doc: fitz.Document | None, pattern: str, skip: str | None = None) -> str:
    if doc is None:
        return ""
    compiled = re.compile(pattern, re.I)
    skipped = re.compile(skip, re.I) if skip else None
    parts: list[str] = []
    for page in doc:
        text = page.get_text("text") or ""
        if _SUMMARY.search(text) or (skipped and skipped.search(text)):
            continue
        if compiled.search(text):
            parts.append(text)
    return "\n".join(parts)

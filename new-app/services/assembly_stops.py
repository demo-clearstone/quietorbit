"""Stop assembly before the PDF, email draft, and log are written.

These checks follow the client note "when assembling needs to stop".
A single notice PDF still processes. The full stop set runs when the
upload includes a valuation package, cover letter, or cover page file.
"""

from __future__ import annotations

import re

import fitz

from models.plan_profile import PlanProfile
from services import file_order, ssn_scan
from services.plan_config import package_flags
from services.source_rewrite import calendar_402g_year

_SLASH_WORDING = re.compile(
    r"is\s*[\\/]\s*is\s+not|\bpass\s*[\\/]\s*fail\b",
    re.I,
)
_PLAN_NAME = re.compile(r"plan\s*name\s*[:\-]\s*(.+)", re.I)
_EMPLOYER_NAME = re.compile(r"(?:employer|company)\s*name\s*[:\-]\s*(.+)", re.I)
_PYE_LABEL = re.compile(
    r"plan\s+year\s+end(?:ing)?\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})",
    re.I,
)
_PLAN_YEAR_RANGE = re.compile(
    r"plan\s+year\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})\s*[-–to]+\s*(\d{1,2}/\d{1,2}/\d{4})",
    re.I,
)
_PERIOD_ENDING = re.compile(
    r"period\s+ending\s*[:\-]?\s*(\d{1,2}/\d{1,2}/\d{4})",
    re.I,
)
_STREET = re.compile(r"(P\.?\s*O\.?\s*Box\b|\d{1,6}\s+\S)", re.I)
_CITY_STATE_ZIP = re.compile(
    r"[A-Za-z][A-Za-z .'-]{1,40},?\s+[A-Z]{2}\s+\d{5}(?:-\d{4})?\b"
)
_OTHER_CONTRIBUTION = re.compile(
    r"\b(match|profit\s+sharing|shne|safe\s+harbor|qnec|employer\s+contribution)\b",
    re.I,
)
_SUMMARY_HEAD = re.compile(
    r"test summary|result summary|compliance summary|testing summary of results",
    re.I,
)
_SKIP_HEAD = re.compile(r"test summary|result summary|compliance summary|action required|cover letter", re.I)

# Heading on the report itself, not a mention inside the Result Summary.
_REPORTS: list[tuple[str, str, str]] = [
    ("Result Summary", r"resultsumm|result\s*summary|test\s*summary", r"result summary|test summary|compliance summary"),
    ("402(g) Test Report", r"402\s*\(?g\)?", r"402\s*\(?\s*g\s*\)?"),
    ("415 Test Report", r"415", r"415"),
    ("ADP/ACP Test Report", r"adp|acp", r"adp\s*/\s*acp|adp test|acp test"),
    ("410(b) Test Report", r"410\s*\(?b\)?", r"410\s*\(?b\)?"),
    ("HCE Key Report", r"hce\s*/?\s*key|hcekey", r"hce\s*/\s*key|hce\s+key|hcekey"),
    ("Future HCE Report", r"future\s*hce|fyhce", r"future\s*hce|fyhce"),
    ("Top Heavy Report", r"top\s*-?\s*heavy|(^|[^a-z])th([^a-z]|$)", r"top\s*-?\s*heavy"),
    ("Census Report", r"census", r"\bcensus\b"),
    ("Contribution Analysis Report", r"contri", r"contribution analysis"),
]
_EXTRA_REPORTS: list[tuple[str, str, str, str]] = [
    ("Variance Client Copy", r"variance", r"variance", r"\bvariance\b"),
    ("414(s) Test Report", r"414\s*\(?s\)?", r"414\s*\(?s\)?", r"414\s*\(?s\)?"),
    ("401(a)(4) Test Report", r"401\s*\(?a\)?\s*\(?4\)?|401a4", r"401\s*\(?a\)?\s*\(?4\)?", r"401\s*\(?a\)?\s*\(?4\)?|401a4"),
    ("ABP Test Report", r"average benefit|abpt", r"average benefit|abpt", r"average benefit|\babpt\b"),
]


def stop_reasons(
    doc: fitz.Document,
    profile: PlanProfile,
    source_files: list[str],
    excel_plan_name: str | None = None,
    pdf_plan_name: str | None = None,
    excel_company: str | None = None,
    excel_address: str | None = None,
    excel_pye: str | None = None,
    cover_company: str | None = None,
    cover_address: str | None = None,
    cover_pye: str | None = None,
) -> list[str]:
    reasons = _content_reasons(doc)
    if not _is_valuation_package(source_files):
        return reasons
    reasons.extend(
        _package_reasons(
            doc,
            profile,
            source_files,
            excel_plan_name,
            pdf_plan_name,
            excel_company=excel_company,
            excel_address=excel_address,
            excel_pye=excel_pye,
            cover_company=cover_company,
            cover_address=cover_address,
            cover_pye=cover_pye,
        )
    )
    return reasons


def _content_reasons(doc: fitz.Document) -> list[str]:
    reasons: list[str] = []
    pages = ssn_scan.scan_ssns(doc)
    if pages:
        listed = ", ".join(str(page) for page in pages)
        reasons.append(
            f"A full or masked Social Security number was found on page(s) {listed}. "
            "Assembly stopped."
        )
    for page in doc:
        text = page.get_text("text") or ""
        if not _SUMMARY_HEAD.search("\n".join(text.splitlines()[:8])):
            continue
        if _SLASH_WORDING.search(text):
            reasons.append(
                "The Result Summary still has unresolved wording such as "
                "\"Plan is/is not\" or \"Pass/Fail\". Assembly stopped."
            )
            break
    return reasons


def _package_reasons(
    doc: fitz.Document,
    profile: PlanProfile,
    source_files: list[str],
    excel_plan_name: str | None,
    pdf_plan_name: str | None,
    excel_company: str | None = None,
    excel_address: str | None = None,
    excel_pye: str | None = None,
    cover_company: str | None = None,
    cover_address: str | None = None,
    cover_pye: str | None = None,
) -> list[str]:
    reasons: list[str] = []
    if profile.moa_logo_found is not True:
        reasons.append(
            "The Mutual of America stamp was not found on the upper right of the cover letter. "
            "Assembly stopped."
        )
    address = _address_reason(cover_address or profile.company_address)
    if address:
        reasons.append(address)
    reasons.extend(_name_reasons(doc, profile, excel_plan_name, pdf_plan_name))
    reasons.extend(
        _excel_cover_reasons(
            excel_company=excel_company,
            excel_address=excel_address,
            excel_pye=excel_pye,
            cover_company=cover_company,
            cover_address=cover_address,
            cover_pye=cover_pye,
        )
    )
    reasons.extend(_pye_reasons(doc, profile))
    reasons.extend(_missing_report_reasons(doc, profile, source_files))
    coverage = _coverage_reason(doc)
    if coverage:
        reasons.append(coverage)
    return reasons


def _is_valuation_package(source_files: list[str]) -> bool:
    for name in source_files:
        spec = file_order.matched_spec(name)
        if spec and spec.get("name") == "Cover Letter" and spec.get("split_pages"):
            return True
    return False


def _address_reason(address: str | None) -> str | None:
    text = (address or "").strip()
    if not text:
        return (
            "The employer address is missing. It needs address line 1 and city, state, and ZIP. "
            "Assembly stopped."
        )
    if not _STREET.search(text) or not _CITY_STATE_ZIP.search(text):
        return (
            "The employer address is incomplete. It needs address line 1 and city, state, and ZIP. "
            "Address line 2 is optional. Assembly stopped."
        )
    return None


def _name_reasons(
    doc: fitz.Document,
    profile: PlanProfile,
    excel_plan_name: str | None,
    pdf_plan_name: str | None,
) -> list[str]:
    reasons: list[str] = []
    plan_names = _labeled_values(doc, _PLAN_NAME)
    if pdf_plan_name:
        plan_names.add(_norm_name(pdf_plan_name))
    plan_names.discard("")
    if excel_plan_name and plan_names and _norm_name(excel_plan_name) not in plan_names:
        reasons.append(
            "The plan name in the valuation package Excel does not match the plan name "
            "on the cover letter or test reports. Assembly stopped."
        )
    if len(plan_names) > 1:
        reasons.append(
            "The plan name is not the same on every report. Assembly stopped."
        )
    employers = _labeled_values(doc, _EMPLOYER_NAME)
    if profile.company_name:
        employers.add(_norm_name(profile.company_name))
    employers.discard("")
    if len(employers) > 1:
        reasons.append(
            "The employer name is not the same on every report. Assembly stopped."
        )
    return reasons


def _labeled_values(doc: fitz.Document, pattern: re.Pattern[str]) -> set[str]:
    found: set[str] = set()
    for page in doc:
        for match in pattern.finditer(page.get_text("text") or ""):
            name = _norm_name(match.group(1).splitlines()[0])
            if len(name) >= 3:
                found.add(name)
    return found


def _norm_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _excel_cover_reasons(
    *,
    excel_company: str | None,
    excel_address: str | None,
    excel_pye: str | None,
    cover_company: str | None,
    cover_address: str | None,
    cover_pye: str | None,
) -> list[str]:
    """Cover letter block must match the valuation package Excel when those cells are filled."""
    reasons: list[str] = []
    if excel_company and _norm_name(excel_company) != _norm_name(cover_company or ""):
        reasons.append(
            "The company name on the cover letter does not match the company name "
            "in the valuation package Excel. Assembly stopped."
        )
    if excel_address and _norm_name(excel_address) != _norm_name(cover_address or ""):
        reasons.append(
            "The company address on the cover letter does not match the address "
            "in the valuation package Excel. Assembly stopped."
        )
    if excel_pye and _norm_date(excel_pye) != _norm_date(cover_pye):
        reasons.append(
            "The plan year end on the cover letter does not match the plan year end "
            "in the valuation package Excel. Assembly stopped."
        )
    return reasons


def _pye_reasons(doc: fitz.Document, profile: PlanProfile) -> list[str]:
    expected = _norm_date(profile.plan_year_end)
    if not expected:
        return []
    problems: list[str] = []
    for page in doc:
        text = page.get_text("text") or ""
        ends = _page_year_ends(text)
        if not ends:
            continue
        kind = _page_kind(text)
        allowed = _allowed_year_ends(expected, profile, kind)
        for found in ends:
            if kind == "future":
                if found == expected or _year(found) > _year(expected):
                    continue
            elif found in allowed:
                continue
            problems.append(f"page {page.number + 1} shows {found}")
    if not problems:
        return []
    return [
        "The plan year end does not match on every page ("
        + "; ".join(problems[:6])
        + "). Future HCE may show a later year, and an off-calendar 402(g) report "
        "may show the prior calendar year. Assembly stopped."
    ]


def _page_year_ends(text: str) -> list[str]:
    ends: list[str] = []
    for match in _PYE_LABEL.finditer(text):
        ends.append(_norm_date(match.group(1)))
    for match in _PLAN_YEAR_RANGE.finditer(text):
        ends.append(_norm_date(match.group(2)))
    for match in _PERIOD_ENDING.finditer(text):
        ends.append(_norm_date(match.group(1)))
    return [item for item in ends if item]


def _page_kind(text: str) -> str:
    head = "\n".join(text.splitlines()[:12])
    if re.search(r"future\s*hce|fyhce", head, re.I):
        return "future"
    if re.search(r"402\s*\(?\s*g\s*\)?", head, re.I):
        return "402g"
    return "normal"


def _allowed_year_ends(expected: str, profile: PlanProfile, kind: str) -> set[str]:
    allowed = {expected}
    if kind == "402g":
        year = calendar_402g_year(profile.plan_year_end)
        if year:
            allowed.add(f"12/31/{year}")
    return allowed


def _norm_date(value: str | None) -> str:
    if not value:
        return ""
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if not match:
        return ""
    return f"{int(match.group(1)):02d}/{int(match.group(2)):02d}/{match.group(3)}"


def _year(value: str) -> int:
    return int(value[-4:])


def _missing_report_reasons(
    doc: fitz.Document,
    profile: PlanProfile,
    source_files: list[str],
) -> list[str]:
    present = _present_reports(doc, source_files)
    required = [label for label, _file_pattern, _head_pattern in _REPORTS]
    if profile.safe_harbor is True:
        required = [label for label in required if label != "ADP/ACP Test Report"]
    if not package_flags(profile.plan_type).get("require_410b_report", True):
        required = [label for label in required if label != "410(b) Test Report"]
    if not package_flags(profile.plan_type).get("require_full_reports", True):
        required = []
    missing = [label for label in required if label not in present]
    summary = _summary_text(doc)
    for label, summary_pattern, _file_pattern, _head_pattern in _EXTRA_REPORTS:
        mentioned = bool(summary and re.search(summary_pattern, summary, re.I))
        if label == "Variance Client Copy" and (profile.variance_report is True or profile.true_up is True):
            mentioned = True
        if mentioned and label not in present:
            missing.append(label)
    if not missing:
        return []
    return [
        "These required reports are missing: "
        + ", ".join(missing)
        + ". Assembly stopped."
    ]


def _present_reports(doc: fitz.Document, source_files: list[str]) -> set[str]:
    present: set[str] = set()
    filenames = "\n".join(source_files)
    for label, file_pattern, _head_pattern in _REPORTS:
        if re.search(file_pattern, filenames, re.I):
            present.add(label)
    for label, _summary_pattern, file_pattern, _head_pattern in _EXTRA_REPORTS:
        if re.search(file_pattern, filenames, re.I):
            present.add(label)
    from services.package_polish import is_compliance_overview

    for page in doc:
        text = page.get_text("text") or ""
        if is_compliance_overview(text):
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            continue
        head = " ".join(lines[:3])
        if _SKIP_HEAD.search(head):
            if _SUMMARY_HEAD.search(head):
                present.add("Result Summary")
            continue
        for label, _file_pattern, head_pattern in _REPORTS:
            if re.search(head_pattern, head, re.I):
                present.add(label)
        for label, _summary_pattern, _file_pattern, head_pattern in _EXTRA_REPORTS:
            if re.search(head_pattern, head, re.I):
                present.add(label)
    return present


def _summary_text(doc: fitz.Document) -> str:
    parts: list[str] = []
    for page in doc:
        text = page.get_text("text") or ""
        head = " ".join(line.strip() for line in text.splitlines()[:6] if line.strip())
        if _SUMMARY_HEAD.search(head):
            parts.append(text)
    return "\n".join(parts)


def _coverage_reason(doc: fitz.Document) -> str | None:
    from services.package_polish import is_compliance_overview

    full = "\n".join(
        text
        for page in doc
        if (text := page.get_text("text") or "") and not is_compliance_overview(text)
    )
    if not _OTHER_CONTRIBUTION.search(full):
        return None
    summary = _summary_text(doc)
    if not summary:
        return None
    missing = [
        label
        for label, pattern in (
            ("Standard", r"standard"),
            ("401(k)", r"401\s*\(?k\)?"),
            ("401(m)", r"401\s*\(?m\)?"),
        )
        if not _resolved_result(summary, pattern)
    ]
    if not missing:
        return None
    return (
        "The plan has contributions other than deferrals and Roth, so the Result Summary "
        "needs a resolved 410(b) line for "
        + ", ".join(missing)
        + " (Standard for profit sharing and SHNE, 401(k) for deferrals and Roth, "
        "401(m) for match and safe harbor match). Assembly stopped."
    )


def _resolved_result(text: str, label: str) -> bool:
    match = re.search(label + r".{0,60}?\b(pass|fail)\b", text, re.I | re.S)
    if not match:
        return False
    window = text[max(0, match.start() - 12) : match.end() + 12]
    return _SLASH_WORDING.search(window) is None

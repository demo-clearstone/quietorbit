"""Stop assembly before the PDF, email draft, and log are written.

These checks follow the client note "when assembling needs to stop".
A single notice PDF still processes. The full stop set runs when the
upload includes a valuation package, cover letter, or cover page file.
"""

from __future__ import annotations

import re
from datetime import datetime

import fitz

from models.plan_profile import PlanProfile
from services import file_order, package_polish, ssn_scan
from services.plan_config import package_flags
from services.source_rewrite import calendar_402g_year

_SLASH_WORDING = re.compile(
    r"is\s*[\\/]\s*is\s+not|\bpass\s*[\\/]\s*fail\b|\bfail\s*[\\/]\s*pass\b",
    re.I,
)
_PLAN_NAME = re.compile(r"plan\s*name\s*[:\-]\s*(.+)", re.I)
_PLAN_NUMBER = re.compile(r"plan\s*(?:number|no\.?|#)\s*[:\-]?\s*(\d{3,10})\b", re.I)
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
_MONTH_YEAR_END = re.compile(
    r"(?:plan\s+year\s+end(?:ing)?|period\s+ending)\s*[:\-]?\s*"
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4})",
    re.I,
)
_MONTH_YEAR_RANGE = re.compile(
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4}\s*[-–]\s*"
    r"((?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4})",
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
_SKIP_HEAD = re.compile(
    r"test summary|result summary|compliance summary|action required|cover letter|"
    r"sample/draft|failure letter|failed compliance|excess return notice|415 failure information",
    re.I,
)

# Heading on the report itself, not a mention inside the Result Summary.
_REPORTS: list[tuple[str, str, str]] = [
    ("Result Summary", r"resultsumm|result\s*summary|test\s*summary", r"result summary|test summary|compliance summary"),
    ("402(g) Test Report", r"402\s*(?:\(?g\)?)?", r"402\s*\(?\s*g\s*\)?"),
    ("415 Test Report", r"415", r"415"),
    ("ADP/ACP Test Report", r"adp|acp", r"adp\s*/\s*acp|adp test|acp test"),
    ("410(b) Test Report", r"410\s*(?:\(?b\)?)?", r"410\s*\(?b\)?"),
    ("HCE Key Report", r"hce\s*/?\s*key|hcekey", r"hce\s*/\s*key|hce\s+key|hcekey"),
    ("Future HCE Report", r"future\s*hce|fyhce", r"future\s*hce|fyhce"),
    ("Top Heavy Report", r"top\s*-?\s*heavy|(^|[^a-z])th([^a-z]|$)", r"top\s*-?\s*heavy"),
    ("Census Report", r"census", r"\bcensus\b"),
    ("Contribution Analysis Report", r"contri", r"contribution analysis"),
]
_REAL_REPORT_HEADS = tuple(
    re.compile(pattern, re.I)
    for pattern in (
        r"^402\s*\(?g\)?\s+(?:deferral|test|limit)",
        r"^415(?:\s*\(\s*c\s*\))?\s+(?:limit|test|annual additions)",
        r"^(?:adp|acp|adp\s*/\s*acp)\s+(?:nondiscrimination|test|summary)",
        r"^410\s*\(?b\)?\s+(?:coverage|test)",
        r"^(?:hce\s*/?\s*key|highly compensated employees?)\b",
        r"^(?:future\s+hce|future highly compensated employees?)\b",
        r"^top\s*[- ]?heavy(?:\s+test|\s+determination)?\b",
        r"^(?:employee\s+)?census(?:\s+report)?\b",
        r"^contribution analysis(?:\s+report)?\b",
    )
)
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
    """Checking whether assembly must stop.

    Purpose:
        Checking whether assembly must stop.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and the compliance summary.
        source_files: Uploaded file names. None means there are none.
        excel_plan_name: Excel plan name. Type: str | None.
        pdf_plan_name: Pdf plan name. Type: str | None.
        excel_company: Excel company. Type: str | None.
        excel_address: Excel address. Type: str | None.
        excel_pye: Excel pye. Type: str | None.
        cover_company: Cover company. Type: str | None.
        cover_address: Cover address. Type: str | None.
        cover_pye: Cover pye. Type: str | None.

    Returns:
        a list of str.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        stop_reasons(doc, profile, []) returns a list of str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    reasons = _content_reasons(doc)
    if not _is_valuation_package(source_files, doc):
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
    """Content reasons.

    Purpose:
        Content reasons.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _content_reasons(doc) returns list[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
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
        if _unresolved_summary_wording(text):
            reasons.append(
                "The Result Summary still has unresolved wording such as "
                "\"Plan is/is not\" or \"Pass/Fail\". Assembly stopped."
            )
            break
    return reasons


def _unresolved_summary_wording(text: str) -> bool:
    """Catch result placeholders even when their slash wording is split across PDF lines."""
    compact = re.sub(r"\s+", " ", text or "")
    return bool(_SLASH_WORDING.search(compact))


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
    """Package reasons.

    Purpose:
        Package reasons.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and the compliance summary.
        source_files: Uploaded file names. None means there are none.
        excel_plan_name: Excel plan name. Type: str | None.
        pdf_plan_name: Pdf plan name. Type: str | None.
        excel_company: Excel company. Type: str | None.
        excel_address: Excel address. Type: str | None.
        excel_pye: Excel pye. Type: str | None.
        cover_company: Cover company. Type: str | None.
        cover_address: Cover address. Type: str | None.
        cover_pye: Cover pye. Type: str | None.

    Returns:
        a list of str.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _package_reasons(doc, profile, []) returns a list of str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    reasons: list[str] = []
    if profile.moa_logo_found is not True:
        reasons.append(
            "The Mutual of America stamp was not found on the upper right of the cover letter. "
            "Assembly stopped."
        )
    address = _address_reason(cover_address or profile.company_address)
    if address:
        reasons.append(address)
    if not profile.plan_name:
        reasons.append("The plan name could not be verified from the cover, Excel, or reports. Assembly stopped.")
    if not profile.plan_number:
        reasons.append("The plan number could not be verified from the cover, Excel, or reports. Assembly stopped.")
    if not profile.company_name:
        reasons.append("The employer name could not be verified from the cover or Excel. Assembly stopped.")
    if not profile.plan_year_end:
        reasons.append("The plan year end could not be verified from the cover, Excel, or reports. Assembly stopped.")
    reasons.extend(_name_reasons(doc, profile, excel_plan_name, pdf_plan_name))
    reasons.extend(_plan_number_reasons(doc, profile.plan_number))
    reasons.extend(_company_report_reasons(doc, excel_company or cover_company or profile.company_name))
    from services.package_polish import _compliance_check, _identity_checks

    for item in (_identity_checks(doc, profile) + [_compliance_check(doc, profile)]):
        if not item.passed:
            reasons.append(f"{item.label} validation failed: {item.detail}. Assembly stopped.")
    reasons.extend(_summary_result_reasons(doc))
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
    order_check = package_polish._assembly_order_check(doc, profile)
    if not order_check.passed:
        reasons.append("Report pages do not follow TEST23 order: " + order_check.detail + ". Assembly stopped.")
    coverage = _coverage_reason(doc)
    if coverage:
        reasons.append(coverage)
    return reasons


def _summary_result_reasons(doc: fitz.Document) -> list[str]:
    """Stop if the tester's Result Summary conflicts with the test reports.

    Purpose:
        Stop if the tester's Result Summary conflicts with the test reports.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _summary_result_reasons(doc) returns list[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
    from services.package_polish import _result_summary_checks

    failures = [item for item in _result_summary_checks(doc) if not item.passed]
    return [
        f"Result Summary validation failed ({item.label}): {item.detail}. Assembly stopped."
        for item in failures
    ]


def _is_valuation_package(source_files: list[str], doc: fitz.Document | None = None) -> bool:
    """Is valuation package.

    Purpose:
        Is valuation package.

    Args:
        source_files: Uploaded file names. None means no file names.

    Returns:
        bool.

    Raises:
        None.

    Example:
        _is_valuation_package([]) returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for name in source_files:
        spec = file_order.matched_spec(name)
        if spec and spec.get("name") == "Cover Letter" and spec.get("split_pages"):
            return True
    if doc and doc.page_count:
        cover = "\n".join((page.get_text("text") or "") for page in doc[:2])
        if re.search(r"mutual of america|financial group", cover, re.I) and re.search(
            r"we are pleased to provide|period ending|valuation package", cover, re.I
        ):
            return True
    return False


def _company_report_reasons(doc: fitz.Document, expected: str | None) -> list[str]:
    """Stop when explicitly labeled employer names disagree across report pages."""
    names = _labeled_values(doc, _EMPLOYER_NAME)
    normalized = {name for name in names if name}
    if expected:
        normalized.add(_norm_name(expected))
    if len(normalized) > 1:
        return ["The employer name does not match across the cover, Excel, and reports. Assembly stopped."]
    return []


def _address_reason(address: str | None) -> str | None:
    """Address reason.

    Purpose:
        Address reason.

    Args:
        address: Address. Type: str | None.

    Returns:
        a str | None.

    Raises:
        None.

    Example:
        _address_reason("text") returns a str | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
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
    """Name reasons.

    Purpose:
        Name reasons.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and the compliance summary.
        excel_plan_name: Excel plan name. Type: str | None.
        pdf_plan_name: Pdf plan name. Type: str | None.

    Returns:
        a list of str.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _name_reasons(doc, profile, "text") returns a list of str.

    Side effects:
        None. This function only reads data and returns a value.
    """
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


def _plan_number_reasons(doc: fitz.Document, expected: str | None) -> list[str]:
    """Require a consistent plan number wherever reports label one."""
    numbers = _labeled_values(doc, _PLAN_NUMBER)
    if expected:
        numbers.add(re.sub(r"\D", "", expected))
    numbers.discard("")
    if expected and numbers and any(number != re.sub(r"\D", "", expected) for number in numbers):
        return ["The plan number does not match across the cover, Excel, and reports. Assembly stopped."]
    if len(numbers) > 1:
        return ["The plan number is not the same on every report. Assembly stopped."]
    return []


def _labeled_values(doc: fitz.Document, pattern: re.Pattern[str]) -> set[str]:
    """Labeled values.

    Purpose:
        Labeled values.

    Args:
        doc: Open PDF. Must not be closed.
        pattern: Pattern. Type: re.Pattern[str].

    Returns:
        a set[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _labeled_values(doc, "text") returns a set[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
    found: set[str] = set()
    for page in doc:
        for match in pattern.finditer(page.get_text("text") or ""):
            name = _norm_name(match.group(1).splitlines()[0])
            if len(name) >= 3:
                found.add(name)
    return found


def _norm_name(value: str) -> str:
    """Norm name.

    Purpose:
        Norm name.

    Args:
        value: Value. Type: str.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _norm_name("text") returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
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
    """Cover letter block must match the valuation package Excel when those cells are filled.

    Purpose:
        Cover letter block must match the valuation package Excel when those cells are filled.

    Args:
        excel_company: Excel company. Type: str | None.
        excel_address: Excel address. Type: str | None.
        excel_pye: Excel pye. Type: str | None.
        cover_company: Cover company. Type: str | None.
        cover_address: Cover address. Type: str | None.
        cover_pye: Cover pye. Type: str | None.

    Returns:
        a list of str.

    Raises:
        None.

    Example:
        _excel_cover_reasons(excel_company="text", excel_address="text", excel_pye="text", cover_company="text") returns a list of str.

    Side effects:
        None. This function only reads data and returns a value.
    """
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
    """Pye reasons.

    Purpose:
        Pye reasons.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _pye_reasons(doc, profile) returns list[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
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
    """Page year ends.

    Purpose:
        Page year ends.

    Args:
        text: Text taken from a page or a file.

    Returns:
        list[str].

    Raises:
        None.

    Example:
        _page_year_ends("text") returns list[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
    ends: list[str] = []
    for match in _PYE_LABEL.finditer(text):
        ends.append(_norm_date(match.group(1)))
    for match in _PLAN_YEAR_RANGE.finditer(text):
        ends.append(_norm_date(match.group(2)))
    for match in _PERIOD_ENDING.finditer(text):
        ends.append(_norm_date(match.group(1)))
    for match in _MONTH_YEAR_END.finditer(text):
        try:
            ends.append(datetime.strptime(match.group(1), "%B %d, %Y").strftime("%m/%d/%Y"))
        except ValueError:
            continue
    for match in _MONTH_YEAR_RANGE.finditer(text):
        try:
            ends.append(datetime.strptime(match.group(1), "%B %d, %Y").strftime("%m/%d/%Y"))
        except ValueError:
            continue
    return [item for item in ends if item]


def _page_kind(text: str) -> str:
    """Page kind.

    Purpose:
        Page kind.

    Args:
        text: Text taken from a page or a file.

    Returns:
        str.

    Raises:
        None.

    Example:
        _page_kind("text") returns str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    head = "\n".join(text.splitlines()[:12])
    if re.search(r"future\s*hce|fyhce", head, re.I):
        return "future"
    if re.search(r"402\s*\(?\s*g\s*\)?", head, re.I):
        return "402g"
    return "normal"


def _allowed_year_ends(expected: str, profile: PlanProfile, kind: str) -> set[str]:
    """Allowed year ends.

    Purpose:
        Allowed year ends.

    Args:
        expected: Expected. Type: str.
        profile: Plan profile collected from the PDF, Excel, and the compliance summary.
        kind: Kind. Type: str.

    Returns:
        a set[str].

    Raises:
        None.

    Example:
        _allowed_year_ends("text", profile, "text") returns a set[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
    allowed = {expected}
    if kind == "402g":
        year = calendar_402g_year(profile.plan_year_end)
        if year:
            allowed.add(f"12/31/{year}")
    return allowed


def _norm_date(value: str | None) -> str:
    """Norm date.

    Purpose:
        Norm date.

    Args:
        value: Value. Type: str | None.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _norm_date("text") returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if not value:
        return ""
    match = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", value)
    if not match:
        return ""
    return f"{int(match.group(1)):02d}/{int(match.group(2)):02d}/{match.group(3)}"


def _year(value: str) -> int:
    """Year.

    Purpose:
        Year.

    Args:
        value: Value. Type: str.

    Returns:
        a int.

    Raises:
        None.

    Example:
        _year("text") returns a int.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return int(value[-4:])


def _missing_report_reasons(
    doc: fitz.Document,
    profile: PlanProfile,
    source_files: list[str],
) -> list[str]:
    """Missing report reasons.

    Purpose:
        Missing report reasons.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.
        source_files: Uploaded file names. None means no file names.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _missing_report_reasons(doc, profile, []) returns list[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
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
    """Present reports.

    Purpose:
        Present reports.

    Args:
        doc: Open PDF. Must not be closed.
        source_files: Uploaded file names. None means no file names.

    Returns:
        set[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _present_reports(doc, []) returns set[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
    present: set[str] = set()
    for label, file_pattern, _head_pattern in _REPORTS:
        if _report_filename_present(label, source_files, file_pattern):
            present.add(label)
    for label, _summary_pattern, file_pattern, _head_pattern in _EXTRA_REPORTS:
        if _report_filename_present(label, source_files, file_pattern):
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
            if not any(pattern.search(head) for pattern in _REAL_REPORT_HEADS):
                continue
            if re.search(head_pattern, head, re.I):
                present.add(label)
        for label, _summary_pattern, _file_pattern, head_pattern in _EXTRA_REPORTS:
            if re.search(head_pattern, head, re.I):
                present.add(label)
    return present


def _report_filename_present(label: str, source_files: list[str], pattern: str) -> bool:
    """Exclude notices and sample letters from satisfying required report checks."""
    for filename in source_files:
        if not re.search(pattern, filename, re.I):
            continue
        if label in {"402(g) Test Report", "415 Test Report", "ADP/ACP Test Report"} and re.search(
            r"failure|failed|letter|notice|sample|excess|correction", filename, re.I
        ):
            continue
        return True
    return False


def _summary_text(doc: fitz.Document) -> str:
    """Summary text.

    Purpose:
        Summary text.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        str.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _summary_text(doc) returns str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    parts: list[str] = []
    for page in doc:
        text = page.get_text("text") or ""
        head = " ".join(line.strip() for line in text.splitlines()[:6] if line.strip())
        if _SUMMARY_HEAD.search(head):
            parts.append(text)
    return "\n".join(parts)


def _coverage_reason(doc: fitz.Document) -> str | None:
    """Coverage reason.

    Purpose:
        Coverage reason.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        str | None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _coverage_reason(doc) returns str | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
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
    """Resolved result.

    Purpose:
        Resolved result.

    Args:
        text: Text from a page or a file.
        label: Label. Type: str.

    Returns:
        True or False.

    Raises:
        None.

    Example:
        _resolved_result("text", "text") returns True or False.

    Side effects:
        None. This function only reads data and returns a value.
    """
    match = re.search(label + r".{0,60}?\b(pass|fail)\b", text, re.I | re.S)
    if not match:
        return False
    window = text[max(0, match.start() - 12) : match.end() + 12]
    return _SLASH_WORDING.search(window) is None

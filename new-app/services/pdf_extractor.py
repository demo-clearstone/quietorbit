from __future__ import annotations

import re
from datetime import datetime
from typing import Any

import fitz
import yaml

from config.field_patterns import (
    COVER_PATTERNS,
    DEADLINE_402G_PATTERNS,
    FAIL_FLAGS,
    PASS_FLAGS,
    RETURNS_ALREADY_PROCESSED_PATTERNS,
    TEST_PATTERNS,
)
from config.settings import CONFIG_DIR
from models.plan_profile import DetectedSection, PlanProfile
from services.logo_check import inspect_cover_stamp

_NEXT_LABEL = re.compile(
    r"^(Plan\s*(Name|Number|Year|Type)|Company|Employer|Address|Sponsor)\b",
    re.I,
)
_MONTHS = (
    "January|February|March|April|May|June|July|August|September|"
    "October|November|December"
)
_DATE_LINE = re.compile(rf"^({_MONTHS})\s+\d{{1,2}},\s+\d{{4}}\s*$", re.I)
_RE_LINE = re.compile(r"^RE:\s*(.+)$", re.I)
_LETTERHEAD_LINE = re.compile(
    r"mutual of america|financial group|retirement services",
    re.I,
)
_ADDRESS_LINE = re.compile(
    r"(P\.?\s*O\.?\s*Box\b|^\d{1,6}\s+\S|\b[A-Z]{2}\s+\d{5}(?:-\d{4})?\b|Suite\s+\d+|Ste\.?\s+\d+)",
    re.I,
)
_BODY_START = re.compile(r"^(We are|Please|If you|This Valuation|Dear\s)", re.I)


def extract_plan_profile(doc: fitz.Document) -> PlanProfile:
    """Extracting plan data from the merged PDF."""
    cover_text = _pages_text(doc, 0, min(3, doc.page_count))
    full_text = _pages_text(doc, 0, doc.page_count)
    warnings: list[str] = []

    plan_number = _first_match(cover_text, COVER_PATTERNS["plan_number"])
    letter = _parse_cover_letter(cover_text)
    plan_name = _clean_line(_first_match(cover_text, COVER_PATTERNS["plan_name"])) or letter["plan_name"]
    company_name = _clean_line(_first_match(cover_text, COVER_PATTERNS["company_name"])) or letter["company_name"]
    company_address = _clean_line(_first_match(cover_text, COVER_PATTERNS["company_address"])) or letter["company_address"]
    plan_type = _clean_line(_first_match(cover_text, COVER_PATTERNS.get("plan_type") or []))

    year_start, year_end = _plan_year(cover_text or full_text)
    method = (
        _testing_method(cover_text)
        or _adp_results_method(doc)
        or _testing_method(full_text)
        or _current_when_adp_has_no_prior(full_text)
    )
    top_heavy_percent = _money_or_percent(full_text, TEST_PATTERNS["top_heavy_percent"])

    flags = {
        name: _flag_bool(full_text, FAIL_FLAGS[name], PASS_FLAGS.get(name) or [])
        for name in FAIL_FLAGS
    }
    testing_failed = _or_bools(flags.get("adp_failed"), flags.get("acp_failed"), flags.get("fail_402g"), flags.get("fail_415"))

    adp_qnec = _money_or_percent(full_text, TEST_PATTERNS["adp_qnec"])
    acp_qnec = _money_or_percent(full_text, TEST_PATTERNS["acp_qnec"])
    deferral_refund = _money_or_percent(full_text, TEST_PATTERNS["deferral_refund"])
    match_refund = _money_or_percent(full_text, TEST_PATTERNS["match_refund"])
    total_qnec = _sum_optional(adp_qnec, acp_qnec)

    if not plan_number:
        warnings.append("Plan number was not found on the cover pages. Filename will use UNKNOWN.")
    if not year_start and not year_end:
        warnings.append("Plan year was not found. Filename will use UNKNOWN for the year.")

    top_heavy = None
    if top_heavy_percent is not None:
        top_heavy = top_heavy_percent > 60

    stamp = inspect_cover_stamp(doc[0]) if doc.page_count else {
        "mentions_moa": False,
        "moa_logo_found": False,
        "moa_stamp_detail": "Cover page is missing",
    }

    profile = PlanProfile(
        plan_number=plan_number,
        plan_name=plan_name,
        company_name=company_name,
        company_address=company_address,
        plan_type=plan_type,
        plan_year_start=year_start,
        plan_year_end=year_end,
        beginning_plan_year=_beginning_year(year_start),
        testing_method=method,
        top_heavy_percent=top_heavy_percent,
        top_heavy=top_heavy,
        adp_failed=flags.get("adp_failed"),
        acp_failed=flags.get("acp_failed"),
        testing_failed=testing_failed,
        returns_required=flags.get("returns_required"),
        returns_already_processed=bool(_flag_present(full_text, RETURNS_ALREADY_PROCESSED_PATTERNS)),
        fail_402g=flags.get("fail_402g"),
        fail_402g_after_deadline=bool(_flag_present(full_text, DEADLINE_402G_PATTERNS)),
        fail_415=flags.get("fail_415"),
        variance_report=flags.get("variance_report"),
        contributions_required=flags.get("contributions_required"),
        partially_vested=flags.get("partially_vested"),
        safe_harbor=flags.get("safe_harbor"),
        catchup_disallowed=flags.get("catchup_disallowed"),
        per_payroll_match=flags.get("per_payroll_match"),
        hce_current=flags.get("hce_current"),
        hce_future=flags.get("hce_future"),
        after_12_months=flags.get("after_12_months"),
        adp_qnec=adp_qnec,
        acp_qnec=acp_qnec,
        deferral_refund=deferral_refund,
        match_refund=match_refund,
        total_qnec=total_qnec,
        has_action_required=None,
        mentions_moa=bool(stamp.get("mentions_moa")),
        moa_logo_found=bool(stamp.get("moa_logo_found")),
        moa_stamp_detail=str(stamp.get("moa_stamp_detail") or ""),
        detected_sections=_detect_sections(doc),
        extraction_warnings=warnings,
        source_page_count=doc.page_count,
    )
    return profile


def beginning_plan_year(start_date: str) -> str | None:
    """SRD §7: use the beginning plan year only."""
    return _beginning_year(start_date)


def _pages_text(doc: fitz.Document, start: int, end: int) -> str:
    parts: list[str] = []
    for index in range(start, end):
        parts.append(doc[index].get_text("text") or "")
    return "\n".join(parts)


def _first_match(text: str, patterns: list[str]) -> str | None:
    if not text:
        return None
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            value = match.group(1).strip()
            if value:
                return value
    return None


def _parse_cover_letter(text: str) -> dict[str, str | None]:
    """TEST23 §B: company, address, and plan name from a cover-letter layout."""
    empty = {"company_name": None, "company_address": None, "plan_name": None}
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    if not lines:
        return empty
    date_i = next((i for i, ln in enumerate(lines) if _DATE_LINE.match(ln)), None)
    re_i = next((i for i, ln in enumerate(lines) if _RE_LINE.match(ln)), None)
    if date_i is None and re_i is None:
        return empty

    plan_name = None
    if re_i is not None:
        match = _RE_LINE.match(lines[re_i])
        plan_name = _clean_line(match.group(1) if match else None)

    start = date_i + 1 if date_i is not None else 0
    if re_i is not None:
        end = re_i
    else:
        end = len(lines)
        for index in range(start, len(lines)):
            if _BODY_START.match(lines[index]):
                end = index
                break
        end = min(end, start + 8)

    block = [ln for ln in lines[start:end] if not _LETTERHEAD_LINE.search(ln)]
    company_lines: list[str] = []
    address_lines: list[str] = []
    seen_address = False
    for line in block:
        if seen_address or _ADDRESS_LINE.search(line):
            seen_address = True
            address_lines.append(line)
        else:
            company_lines.append(line)

    company = _clean_line(" ".join(company_lines)) if company_lines else None
    address = re.sub(r"\s{2,}", " ", ", ".join(address_lines)) if address_lines else None
    return {"company_name": company, "company_address": address or None, "plan_name": plan_name}


def _clean_line(value: str | None) -> str | None:
    if not value:
        return None
    line = value.splitlines()[0].strip()
    line = re.sub(r"\s{2,}", " ", line)
    if _NEXT_LABEL.match(line):
        return None
    return line or None


def _plan_year(text: str) -> tuple[str | None, str | None]:
    for pattern in COVER_PATTERNS["plan_year"]:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        if match.lastindex and match.lastindex >= 2:
            return _format_date(match.group(1)), _format_date(match.group(2))
        end = _format_date(match.group(1))
        return None, end
    return None, None


def _format_date(raw: str) -> str | None:
    raw = (raw or "").strip()
    for fmt in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    return raw or None


def _beginning_year(start_date: str | None) -> str | None:
    if not start_date:
        return None
    try:
        return str(datetime.strptime(start_date, "%m/%d/%Y").year)
    except ValueError:
        match = re.search(r"(19|20)\d{2}", start_date)
        return match.group(0) if match else None


def _testing_method(text: str) -> str | None:
    for pattern in TEST_PATTERNS["testing_method"]:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def _money_or_percent(text: str, patterns: list[str]) -> float | None:
    raw = _first_match(text, patterns)
    if raw is None:
        return None
    cleaned = raw.replace(",", "").replace("%", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _flag_present(text: str, patterns: list[str]) -> bool | None:
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
            return True
    return None


def _flag_bool(text: str, true_patterns: list[str], false_patterns: list[str]) -> bool | None:
    if _flag_present(text, true_patterns):
        return True
    if _flag_present(text, false_patterns):
        return False
    return None


def _or_bools(*values: bool | None) -> bool | None:
    known = [v for v in values if v is not None]
    if not known:
        return None
    return any(known)


def _sum_optional(*values: float | None) -> float | None:
    known = [v for v in values if v is not None]
    if not known:
        return None
    return round(sum(known), 2)


def _load_sections() -> list[dict[str, Any]]:
    path = CONFIG_DIR / "sections.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(data.get("expected_order") or [])


def detect_sections(doc: fitz.Document) -> list[DetectedSection]:
    """Finding each report section after the edits."""
    return _detect_sections(doc)


_PRIOR_NHCE_RESULTS = re.compile(
    r"(?:ADP|ACP)\s+TEST\s+USING\s+PRIOR\s+YEAR\s+NHCE\s+PERCENTAGES",
    re.I,
)


def _adp_results_method(doc: fitz.Document) -> str | None:
    """The ADP/ACP results page says prior year when it uses prior-year NHCE percentages.

    A results page without that wording is current-year testing. The recap sentence
    "prior year data" is not the testing method.
    """
    saw_results = False
    for page in doc:
        text = page.get_text("text") or ""
        if _PRIOR_NHCE_RESULTS.search(text):
            return "PRIOR"
        if re.search(r"\bTEST\s+RESULTS\b", text, re.I) and re.search(r"\bADP\b|\bACP\b", text, re.I):
            saw_results = True
    if saw_results:
        return "CURRENT"
    return None


def _current_when_adp_has_no_prior(text: str) -> str | None:
    """No 'Prior Testing' on an ADP/ACP Test Results page means current-year testing."""
    if not re.search(r"ADP\s*/\s*ACP\s+Test\s+Results", text or "", re.I):
        return None
    if re.search(r"prior\s+testing", text or "", re.I):
        return "PRIOR"
    return "CURRENT"


def _detect_sections(doc: fitz.Document) -> list[DetectedSection]:
    from services.package_polish import is_compliance_overview

    found: list[DetectedSection] = []
    seen: set[str] = set()
    specs = _load_sections()
    for page_index, page in enumerate(doc):
        text = page.get_text("text") or ""
        if is_compliance_overview(text):
            continue
        for spec in specs:
            name = str(spec["name"])
            if name in seen:
                continue
            for alias in spec.get("aliases") or [name]:
                alias_text = str(alias)
                if re.search(re.escape(alias_text), text, flags=re.IGNORECASE):
                    found.append(
                        DetectedSection(name=name, page=page_index + 1, matched_alias=alias_text)
                    )
                    seen.add(name)
                    break
    return found

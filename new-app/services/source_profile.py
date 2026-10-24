from __future__ import annotations

import io
import re
import warnings
from datetime import datetime
from typing import Any

from openpyxl import load_workbook

from models.plan_profile import PlanProfile

_PLAN_NUMBER = re.compile(r"\b(\d{5,7})\b")
_DATE = re.compile(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})")
_MONTH_DATE = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),\s+(\d{4})",
    re.I,
)
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")


def parse_excel(data: bytes) -> dict[str, Any]:
    """Read the Val Assembly / Omnium checklist (CURRENT vs PRIOR, reclass, HCE).

    Purpose:
        Read the Val Assembly / Omnium checklist (CURRENT vs PRIOR, reclass, HCE).

    Args:
        data: Raw file bytes.

    Returns:
        dict[str, Any].

    Raises:
        None.

    Example:
        parse_excel(data) returns dict[str, Any].

    Side effects:
        None. This function only reads data and returns a value.
    """
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message=r"Data Validation extension is not supported and will be removed",
            category=UserWarning,
            module=r"openpyxl\..*",
        )
        book = load_workbook(io.BytesIO(data), data_only=True)
    sheet = book.active
    cells: dict[str, str] = {}
    headers: list[str] = []
    header_row = 1
    for col in range(1, (sheet.max_column or 1) + 1):
        headers.append(_cell_str(sheet.cell(header_row, col).value))
    if headers and any(
        needle in h.lower()
        for h in headers
        for needle in ("plan number", "plan name", "company name", "employer name", "pye", "plan year")
    ):
        for col, header in enumerate(headers, start=1):
            value = sheet.cell(2, col).value
            if header:
                cells[header.lower()] = _cell_str(value)
    for row in sheet.iter_rows(min_row=5, max_row=sheet.max_row or 5, max_col=8, values_only=True):
        label = _cell_str(row[0] if row else None)
        value = _cell_str(row[1] if row and len(row) > 1 else None)
        if label:
            cells[label.lower()] = value

    method = None
    for key, value in cells.items():
        if "prior" in key and "current" in key:
            method = _method(value)
            break
    if method is None:
        method = _method(_first(cells, "testing method", "adp/acp method"))
    reclass = None
    for key, value in cells.items():
        if "reclassif" in key or "shifting" in key:
            reclass = _yes_no(value)
            break
    top_heavy = _yes_no(_first(cells, "top heavy"))
    if top_heavy is None and "403b" in _first(cells, "top heavy").lower():
        top_heavy = False

    pye = _normalize_date(
        _first(cells, "pye", "plan year end") or _first(cells, "plan year")
    )
    overlay: dict[str, Any] = {
        "plan_number": _digits(_first(cells, "omni plan number", "plan number", "plan #")),
        "plan_name": _first(cells, "plan name") or None,
        "company_name": _first(cells, "company name", "employer name") or None,
        "company_address": _first(cells, "company address", "employer address") or None,
        "plan_type": _plan_type(_first(cells, "plan type")),
        "plan_year_end": pye,
        "testing_method": method,
        "adp_reclassified": reclass,
        "hce_current": _yes_no(_first(cells, "hce current", "hce currently")),
        "hce_future": _yes_no(_first(cells, "hce future")),
        "per_payroll_match": _yes_no(_first(cells, "per payroll match", "per payroll")),
        "rework": _yes_no(_column(cells, "rework")),
        "rush": _yes_no(_column(cells, "rush")),
        "non_governmental": _non_governmental(cells),
        "forfeitures_reallocated": _forfeitures_reallocated(cells),
        "no_forfeitures": _no_forfeitures(cells),
    }
    if method is None and "sh" in _first(cells, "prior", "current", "adp/acp").lower():
        overlay["safe_harbor"] = True
    notes = " ".join(value for key, value in cells.items() if "note" in key or "comment" in key)
    if re.search(r"variance", notes, re.I):
        overlay["variance_report"] = True
    if re.search(
        r"contribution and/or adjustment|census adjustment|contributions required|include contribution",
        notes,
        re.I,
    ):
        overlay["contributions_required"] = True
    annual_allocation = _yes_no(_first(cells, "annual allocation"))
    true_up = _yes_no(_first_explicit_true_up(cells))
    if annual_allocation is True or true_up is True:
        overlay["contributions_required"] = True
        overlay["true_up"] = true_up is True
        overlay["annual_allocation"] = annual_allocation is True
    if re.search(r"safe harbor|\bSH\b", notes, re.I):
        overlay["safe_harbor"] = True
    if re.search(r"catch-?up.{0,40}not allowed", notes, re.I):
        overlay["catchup_disallowed"] = True
    if re.search(r"special catch-?up.{0,50}(not apply|do not apply|not allowed)", notes, re.I):
        overlay["special_catchup_disallowed"] = True
    if _yes_no(_first(cells, "special catch-up", "special catch up")) is False:
        overlay["special_catchup_disallowed"] = True
    if re.search(r"partially vested", notes, re.I):
        overlay["partially_vested"] = True
    if re.search(r"forfeitures are reallocated|forfeiture reallocation", notes, re.I):
        overlay["forfeitures_reallocated"] = True
    if re.search(r"no forfeitures", notes, re.I):
        overlay["no_forfeitures"] = True
    if overlay.get("non_governmental") is True:
        overlay["plan_type"] = "457"
    if top_heavy is not None:
        overlay["top_heavy"] = top_heavy
    if reclass is True:
        overlay["returns_required"] = False
    if notes:
        overlay["assembly_notes"] = notes
    return {key: value for key, value in overlay.items() if value not in (None, "")}


def parse_summary_text(text: str) -> dict[str, Any]:
    """Read Compliance Testing Summary of Results pass/fail lines.

    Purpose:
        Read Compliance Testing Summary of Results pass/fail lines.

    Args:
        text: Text taken from a page or a file.

    Returns:
        dict[str, Any].

    Raises:
        None.

    Example:
        parse_summary_text("text") returns dict[str, Any].

    Side effects:
        None. This function only reads data and returns a value.
    """
    source = text or ""
    lines = [line.strip() for line in source.splitlines() if line.strip()]
    # The result summary is one section of a PDF; do not infer pass/fail from
    # action-letter examples or sample notices that follow the summary page.
    end = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if re.match(
                r"^(?:annual valuation report|immediate action required|attention required|year end recap|important information|compliance and administrative reports|overview and descriptions|contribution analysis|hce/?key|future hce|adp(?:/acp)?\s+(?:summary|test)|acp test|402\s*\(?g\)?\s+test|410\s*\(?b\)?\s+test|415\s+(?:limit )?test|census|sample/draft communication)",
                line,
                re.I,
            )
        ),
        len(lines),
    )
    summary_text = "\n".join(lines[:end])
    blob = re.sub(r"\s+", " ", summary_text)
    overlay: dict[str, Any] = {}
    numbers = _PLAN_NUMBER.findall(summary_text)
    if numbers:
        overlay["plan_number"] = numbers[0]
    name = _summary_plan_name(summary_text)
    if name:
        overlay["plan_name"] = name
    pye = _summary_pye(summary_text)
    if pye:
        overlay["plan_year_end"] = pye

    percent = _PERCENT.search(summary_text)
    if percent and re.search(r"top\s*heavy", summary_text, re.I):
        overlay["top_heavy_percent"] = float(percent.group(1))
    if re.search(r"plan is not top heavy", summary_text, re.I):
        overlay["top_heavy"] = False
    elif re.search(r"plan is top heavy", summary_text, re.I):
        overlay["top_heavy"] = True

    overlay["fail_402g"] = _tested_fail(blob, r"402\s*\(?g\)?")
    overlay["fail_415"] = _tested_fail(blob, r"415\s*\(?c\)?|Annual Additions")
    overlay["adp_failed"] = _tested_fail(blob, r"Average Deferral Percentage|\bADP\b")
    overlay["acp_failed"] = _tested_fail(blob, r"Average Contribution Percentage|\bACP\b")
    if overlay["acp_failed"] is None and not re.search(r"\bACP\b", blob, re.I):
        overlay.pop("acp_failed")

    if re.search(r"already been processed", blob, re.I):
        overlay["returns_already_processed"] = True
        overlay["returns_required"] = False
    elif overlay.get("adp_failed") or overlay.get("acp_failed") or overlay.get("fail_402g") or overlay.get("fail_415"):
        if re.search(r"excess returns|returns are required|refunds", blob, re.I):
            overlay["returns_required"] = True
    if re.search(r"compliance testing summary of results", summary_text, re.I):
        overlay["after_12_months"] = bool(re.search(r"after\s+12[- ]month", summary_text, re.I))
        overlay["variance_report"] = bool(re.search(r"(?<!no )variance report", summary_text, re.I))
    return {key: value for key, value in overlay.items() if value not in (None, "")}


def merge_overlays(
    profile: PlanProfile,
    overlays: list[dict[str, Any]],
    warnings: list[str],
    sources: list[str] | None = None,
) -> PlanProfile:
    """Applying the Excel and summary results onto the plan profile.

    Purpose:
        Applying the Excel and summary results onto the plan profile.

    Args:
        profile: Plan profile collected from the PDF, Excel, and the compliance summary.
        overlays: Overlays. Type: list[dict[str, Any]].
        warnings: Messages already collected for this assembly.
        sources: Sources. Type: list[str] | None.

    Returns:
        a PlanProfile.

    Raises:
        None.

    Example:
        merge_overlays(profile, [], []) returns a PlanProfile.

    Side effects:
        None. This function only reads data and returns a value.
    """
    numbers = [str(item["plan_number"]) for item in overlays if item.get("plan_number")]
    if profile.plan_number:
        numbers.append(profile.plan_number)
    unique = list(dict.fromkeys(numbers))
    if len(unique) > 1:
        warnings.append(
            "Plan number differs between Excel and summary (" + ", ".join(unique) + "). "
            "Pass/fail comes from the Compliance Testing Summary."
        )
    field_sources = dict(profile.extra.get("field_sources") or {})
    for index, overlay in enumerate(overlays):
        source = sources[index] if sources and index < len(sources) else "overlay"
        for key, value in overlay.items():
            setattr(profile, key, value)
            field_sources[key] = source
    profile.extra["field_sources"] = field_sources
    return profile


def _tested_fail(blob: str, name: str) -> bool | None:
    """Tested fail.

    Purpose:
        Tested fail.

    Args:
        blob: Blob. Type: str.
        name: File name or section name.

    Returns:
        a bool | None.

    Raises:
        None.

    Example:
        _tested_fail("text", "text") returns a bool | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    match = re.search(
        r"(?:" + name + r").{0,100}?"
        r"(?:Test(?:ed)?|Result)?\s*[:=\-]?\s*(Pass|Fail)\b",
        blob,
        flags=re.I,
    )
    if not match:
        return None
    return match.group(1).lower() == "fail"


def _summary_plan_name(text: str) -> str | None:
    """Summary plan name.

    Purpose:
        Summary plan name.

    Args:
        text: Text taken from a page or a file.

    Returns:
        str | None.

    Raises:
        None.

    Example:
        _summary_plan_name("text") returns str | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for line in text.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if re.search(r"401\s*\(?k\)?|403\s*\(?b\)?|savings plan", cleaned, re.I) and not re.search(
            r"summary of results|plan year", cleaned, re.I
        ):
            return cleaned
    return None


def _summary_pye(text: str) -> str | None:
    """Summary pye.

    Purpose:
        Summary pye.

    Args:
        text: Text taken from a page or a file.

    Returns:
        str | None.

    Raises:
        None.

    Example:
        _summary_pye("text") returns str | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    match = re.search(r"Plan Year End:\s*(.+)", text, flags=re.I)
    raw = match.group(1).strip() if match else ""
    month = _MONTH_DATE.search(raw or text)
    if month:
        parsed = datetime.strptime(
            f"{month.group(1)} {month.group(2)} {month.group(3)}", "%B %d %Y"
        )
        return parsed.strftime("%m/%d/%Y")
    return _normalize_date(raw)


def _column(cells: dict[str, str], name: str) -> str:
    """Read a header cell, not a longer question that merely contains the word.

    Purpose:
        Read a header cell, not a longer question that merely contains the word.

    Args:
        cells: Cells. Type: dict[str, str].
        name: File name or section name.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _column({}, "text") returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for key, value in cells.items():
        if key == name or key.startswith(name + " "):
            return value
    return ""


def _first_explicit_true_up(cells: dict[str, str]) -> str:
    """Do not treat the combined annual-allocation question as proof of a true-up.

    Purpose:
        Do not treat the combined annual-allocation question as proof of a true-up.

    Args:
        cells: Cells. Type: dict[str, str].

    Returns:
        a str.

    Raises:
        None.

    Example:
        _first_explicit_true_up({}) returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for key, value in cells.items():
        if key.strip() in {"true up", "true-up", "true-up?", "true up?"}:
            return value
    return ""


def _first(cells: dict[str, str], *needles: str) -> str:
    """First.

    Purpose:
        First.

    Args:
        cells: Cells. Type: dict[str, str].
        *needles: Needles. Type: str.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _first({}) returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for key, value in cells.items():
        if any(needle in key for needle in needles) and value:
            return value
    return ""


def _cell_str(value: object) -> str:
    """Cell str.

    Purpose:
        Cell str.

    Args:
        value: Value. Type: object.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _cell_str(value) returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%m/%d/%Y")
    return str(value).strip()


def _digits(value: str) -> str | None:
    """Digits.

    Purpose:
        Digits.

    Args:
        value: Value. Type: str.

    Returns:
        a str | None.

    Raises:
        None.

    Example:
        _digits("text") returns a str | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    match = _PLAN_NUMBER.search(value or "")
    return match.group(1) if match else None


def _method(value: str) -> str | None:
    """Method.

    Purpose:
        Method.

    Args:
        value: Value. Type: str.

    Returns:
        a str | None.

    Raises:
        None.

    Example:
        _method("text") returns a str | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    text = (value or "").upper()
    if "PRIOR" in text:
        return "PRIOR"
    if "CURRENT" in text:
        return "CURRENT"
    return None


def _yes_no(value: str) -> bool | None:
    """Yes no.

    Purpose:
        Yes no.

    Args:
        value: Value. Type: str.

    Returns:
        a bool | None.

    Raises:
        None.

    Example:
        _yes_no("text") returns a bool | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    text = (value or "").strip().lower()
    if text in {"yes", "y", "true"}:
        return True
    if text in {"no", "n", "false"}:
        return False
    return None


def _plan_type(value: str) -> str | None:
    """Plan type.

    Purpose:
        Plan type.

    Args:
        value: Value. Type: str.

    Returns:
        a str | None.

    Raises:
        None.

    Example:
        _plan_type("text") returns a str | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    text = (value or "").lower()
    if "457" in text:
        return "457"
    if "403" in text:
        return "403b"
    if "401" in text:
        return "401k"
    return value or None


def _non_governmental(cells: dict[str, str]) -> bool | None:
    """Non governmental.

    Purpose:
        Non governmental.

    Args:
        cells: Cells. Type: dict[str, str].

    Returns:
        a bool | None.

    Raises:
        None.

    Example:
        _non_governmental({}) returns a bool | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for key, value in cells.items():
        if "non-governmental" in key or "non governmental" in key:
            return _yes_no(value)
    return None


def _forfeitures_reallocated(cells: dict[str, str]) -> bool | None:
    """Forfeitures reallocated.

    Purpose:
        Forfeitures reallocated.

    Args:
        cells: Cells. Type: dict[str, str].

    Returns:
        a bool | None.

    Raises:
        None.

    Example:
        _forfeitures_reallocated({}) returns a bool | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for key, value in cells.items():
        if "forfeit" not in key:
            continue
        if _yes_no(value) is True or re.search(r"reallocat", value or "", re.I):
            return True
    return None


def _no_forfeitures(cells: dict[str, str]) -> bool | None:
    """No forfeitures.

    Purpose:
        No forfeitures.

    Args:
        cells: Cells. Type: dict[str, str].

    Returns:
        a bool | None.

    Raises:
        None.

    Example:
        _no_forfeitures({}) returns a bool | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for key, value in cells.items():
        if "forfeit" not in key:
            continue
        if re.search(r"no forfeit", value or "", re.I):
            return True
        if _yes_no(value) is False and "reallocat" in key:
            return True
    return None


def _normalize_date(value: str) -> str | None:
    """Normalize date.

    Purpose:
        Normalize date.

    Args:
        value: Value. Type: str.

    Returns:
        a str | None.

    Raises:
        None.

    Example:
        _normalize_date("text") returns a str | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if not value:
        return None
    match = _DATE.search(value)
    if not match:
        return None
    try:
        parsed = datetime(int(match.group(3)), int(match.group(1)), int(match.group(2)))
        return parsed.strftime("%m/%d/%Y")
    except ValueError:
        return value

"""Mid-year ADP/ACP assembly: letter, ADP Summary, ADP Detail."""

from __future__ import annotations

import re

import fitz

from models.plan_profile import PlanProfile

_MIDYEAR = re.compile(r"mid[-\s]?year", re.I)
_LETTER = re.compile(r"we have completed a mid[-\s]?year", re.I)
_PASS = "within the range allowed"
_FAIL = "exceeds the range allowed"
_ALT = "as an alternative to reducing"
_PYE = re.compile(
    r"plan year ending\s+(\d{1,2}/\d{1,2}/\d{4})",
    re.I,
)
_HCE_MAX = re.compile(
    r"maximum (?:actual )?deferral percentage[^%]{0,80}?(\d+(?:\.\d+)?)\s*%",
    re.I,
)
_PLACEHOLDER = re.compile(r"<\s*xx\.xx\s*%\s*>|xx\.xx\s*%", re.I)


def package_is_midyear(uploads: list[tuple[str, bytes]], doc: fitz.Document | None = None) -> bool:
    """Checking whether this is a mid-year letter.

    Purpose:
        Checking whether this is a mid-year letter.

    Args:
        uploads: List of (file name, file bytes).
        doc: Open PDF. Must not be closed.

    Returns:
        bool.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        package_is_midyear(data, doc) returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for name, _data in uploads:
        if _MIDYEAR.search(name):
            return True
    if doc is None:
        return False
    text = "\n".join((page.get_text("text") or "") for page in doc[:4])
    return bool(_LETTER.search(text))


def order_uploads(uploads: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Mid-year letter, then ADP Summary, then ADP Detail.

    Purpose:
        Mid-year letter, then ADP Summary, then ADP Detail.

    Args:
        uploads: List of (file name, file bytes).

    Returns:
        list[tuple[str, bytes]].

    Raises:
        None.

    Example:
        order_uploads(data) returns list[tuple[str, bytes]].

    Side effects:
        None. This function only reads data and returns a value.
    """
    return sorted(uploads, key=lambda item: (_file_rank(item[0]), item[0].lower()))


def reorder_pages(doc: fitz.Document) -> list[str]:
    """Reordering pages in the mid-year letter.

    Purpose:
        Reordering pages in the mid-year letter.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        reorder_pages(doc) returns list[str].

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    if doc.page_count < 2:
        return []
    order = sorted(range(doc.page_count), key=lambda index: (_page_rank(doc[index].get_text("text") or ""), index))
    if order == list(range(doc.page_count)):
        return []
    doc.select(order)
    return ["Mid-year pages ordered as letter, ADP Summary, ADP Detail."]


def read_letter_facts(doc: fitz.Document) -> dict[str, object]:
    """Plan year end, pass/fail, and the HCE maximum printed on the mid-year test.

    Purpose:
        Plan year end, pass/fail, and the HCE maximum printed on the mid-year test.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        dict[str, object].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        read_letter_facts(doc) returns dict[str, object].

    Side effects:
        None. This function only reads data and returns a value.
    """
    facts: dict[str, object] = {}
    failed: bool | None = None
    for page in doc:
        text = page.get_text("text") or ""
        if not facts.get("plan_year_end"):
            match = _PYE.search(text)
            if match:
                facts["plan_year_end"] = match.group(1)
        if _LETTER.search(text):
            continue
        if not re.search(r"\bADP\b|deferral|mid[-\s]?year", text, re.I):
            continue
        if re.search(r"\bfail\b|exceeds the range", text, re.I):
            failed = True
        elif failed is None and re.search(r"\bpass\b|within the range", text, re.I):
            failed = False
        found = _HCE_MAX.search(text)
        if found and "hce_max_deferral" not in facts:
            facts["hce_max_deferral"] = float(found.group(1))
    if failed is not None:
        facts["midyear_failed"] = failed
    return facts


def apply_letter(doc: fitz.Document, profile: PlanProfile) -> list[str]:
    """Keep the pass or fail paragraph, and the current-method alternative only when the test fails.

    Purpose:
        Keep the pass or fail paragraph, and the current-method alternative only when the test fails.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        apply_letter(doc, profile) returns list[str].

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    notes: list[str] = []
    percent = _percent_label(profile.hce_max_deferral)
    for page in doc:
        original = page.get_text("text") or ""
        if not _LETTER.search(original):
            continue
        paragraphs = _paragraphs(original)
        kept: list[str] = []
        removed: list[str] = []
        for paragraph in paragraphs:
            folded = paragraph.lower()
            if _PASS in folded and profile.midyear_failed is True:
                removed.append("passing")
                continue
            if _FAIL in folded and profile.midyear_failed is False:
                removed.append("failing")
                continue
            if _ALT in folded and not (profile.midyear_failed is True and profile.testing_method == "CURRENT"):
                removed.append("current-method alternative")
                continue
            if _FAIL in folded and percent:
                paragraph = _PLACEHOLDER.sub(percent, paragraph)
            kept.append(paragraph)
        updated = "\n\n".join(kept).strip()
        if updated == original.strip():
            continue
        page.add_redact_annot(page.rect, fill=(1, 1, 1), text="")
        page.apply_redactions()
        cursor = 54
        for paragraph in kept:
            height = 20 * ((len(paragraph) // 55) + 1)
            page.insert_textbox(
                fitz.Rect(54, cursor, 558, min(cursor + height, 780)),
                paragraph,
                fontsize=10,
                fontname="helv",
            )
            cursor += height + 8
        if removed:
            notes.append("Mid-year letter removed: " + ", ".join(removed) + ".")
        if percent and profile.midyear_failed is True:
            notes.append(f"Mid-year HCE maximum deferral set to {percent}.")
    return notes


def _file_rank(name: str) -> int:
    """File rank.

    Purpose:
        File rank.

    Args:
        name: File name or section name.

    Returns:
        int.

    Raises:
        None.

    Example:
        _file_rank("text") returns int.

    Side effects:
        None. This function only reads data and returns a value.
    """
    folded = name.lower()
    if "detail" in folded:
        return 2
    if "summary" in folded:
        return 1
    if "letter" in folded or _MIDYEAR.search(folded):
        return 0
    return 3


def _page_rank(text: str) -> int:
    """Page rank.

    Purpose:
        Page rank.

    Args:
        text: Text taken from a page or a file.

    Returns:
        int.

    Raises:
        None.

    Example:
        _page_rank("text") returns int.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if _LETTER.search(text):
        return 0
    if re.search(r"\bdetail\b", text, re.I):
        return 2
    if re.search(r"\bsummary\b", text, re.I):
        return 1
    return 3


_MARKERS = (
    "The result of this mid-year analysis is attached.",
    "As an alternative to reducing",
    "Please remember that this is merely a projection",
    "Thank you for allowing us to serve you",
    "CUNA Mutual Retirement Solutions",
)


def _paragraphs(text: str) -> list[str]:
    """Split on the mid-year sentences. PDF text often drops the blank lines.

    Purpose:
        Split on the mid-year sentences. PDF text often drops the blank lines.

    Args:
        text: Text taken from a page or a file.

    Returns:
        list[str].

    Raises:
        None.

    Example:
        _paragraphs("text") returns list[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
    flat = re.sub(r"\s+", " ", text).strip()
    pieces: list[str] = []
    remaining = flat
    while remaining:
        cuts = []
        folded = remaining.lower()
        for marker in _MARKERS:
            idx = folded.find(marker.lower())
            if idx == 0:
                idx = folded.find(marker.lower(), len(marker))
            if idx > 0:
                cuts.append(idx)
        if not cuts:
            pieces.append(remaining.strip())
            break
        cut = min(cuts)
        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return [piece for piece in pieces if piece]


def _percent_label(value: float | None) -> str:
    """Percent label.

    Purpose:
        Percent label.

    Args:
        value: Value. Type: float | None.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _percent_label(1.0) returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if value is None:
        return ""
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return f"{int(rounded)}%"
    return f"{rounded:.2f}%"

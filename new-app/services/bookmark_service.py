from __future__ import annotations

import re

import fitz

from models.plan_profile import PlanProfile
from services.file_order import load_section_specs
from services.pdf_assembler import page_section
from services.plan_config import bookmark_overrides, is_403b_plan, load_package_order, package_flags

_ADP_FILE = re.compile(r"\badp\s*test\b")
_ACP_FILE = re.compile(r"\bacp\s*test\b")
_BOTH_FILE = re.compile(r"\badp\s*acp\b|\badpacp\b")
_ADP_HEADING = re.compile(r"(?im)^\s*ADP\s+Tests?\s*$")
_ACP_HEADING = re.compile(r"(?im)^\s*ACP\s+Tests?\s*$")
_BOTH_HEADING = re.compile(r"(?im)^\s*ADP\s*/\s*ACP\s+Tests?\s*$")
_TEST_HEADING = re.compile(r"(?im)^\s*(?:ADP\s*/\s*ACP|ADP|ACP)\s+Tests?\s*$")
_ADP_CHILD = (
    ("Corrections", re.compile(r"\bcorrection", re.I)),
    ("Detail", re.compile(r"\bdetail\b", re.I)),
    ("Summary", re.compile(r"\bsummary\b", re.I)),
)
_ADP_CHILD_ORDER = ("Summary", "Detail", "Corrections")
_ADP_TITLES = {"ADP/ACP Tests", "ADP Test", "ACP Test"}
_SOP_SECTION_ORDER = (
    "Cover Letter",
    "Test Summary",
    "Contribution Analysis",
    "HCE/Key",
    "Future HCE",
    "ADP/ACP",
    "402(g)",
    "410(b)",
    "401(a)(4)",
    "Average Benefit Percentage Test",
    "BRF",
    "414(s)",
    "415",
    "Top Heavy",
    "Census",
)
# A client report title often continues with Determination, Report, or "for the plan year".
_HEADING_TAIL = r"(?:\s+report)?(?:\s+for\b.{0,80})?$"
_SECTION_HEADINGS: dict[str, re.Pattern[str]] = {
    "Cover Letter": re.compile(r"^(?:cover letter|cover page)$", re.I),
    "Test Summary": re.compile(r"^(?:compliance testing summary of results|compliance summary|test summary)$", re.I),
    "Contribution Analysis": re.compile(
        rf"^contribution analysis(?:\s+report)?(?:\s+loc(?:ation)?\s*\d+)?{_HEADING_TAIL}",
        re.I,
    ),
    "HCE/Key": re.compile(
        rf"^(?:hce\s*/\s*key|hce\s+key|highly compensated(?:\s+employees?)?\s*/\s*key)"
        rf"(?:\s+employees?)?(?:\s+determinations?)?{_HEADING_TAIL}",
        re.I,
    ),
    "Future HCE": re.compile(
        rf"^(?:future\s+hce|future\s+highly compensated employees?)"
        rf"(?:\s+determinations?)?(?:\s+projection)?{_HEADING_TAIL}",
        re.I,
    ),
    "ADP/ACP": re.compile(
        r"^(?:adp\s*/\s*acp|adp|acp)\s+(?:nondiscrimination\s+)?"
        r"(?:summary|test(?:\s+results)?|tests?)(?:\s+report)?$",
        re.I,
    ),
    "402(g)": re.compile(
        rf"^(?:(?:section\s+|irc\s+)?402\s*\(\s*g\s*\)|402\s*g)"
        rf"(?:\s+excess)?(?:\s+deferral)?(?:\s+limits?)?(?:\s+test)?{_HEADING_TAIL}",
        re.I,
    ),
    "410(b)": re.compile(
        rf"^(?:410\s*\(\s*b\s*\)|410\s*b)"
        rf"(?:\s+(?:coverage|ratio\s+percentage))?(?:\s+test)?{_HEADING_TAIL}",
        re.I,
    ),
    "401(a)(4)": re.compile(
        rf"^401\s*\(\s*a\s*\)\s*\(\s*4\s*\)(?:\s+(?:general\s+)?test)?{_HEADING_TAIL}",
        re.I,
    ),
    "Average Benefit Percentage Test": re.compile(
        rf"^(?:average benefits?(?:\s+percentage)?(?:\s+test)?|abpt){_HEADING_TAIL}",
        re.I,
    ),
    "BRF": re.compile(
        rf"^(?:benefits?,?\s+rights(?:\s+and\s+features)?(?:\s+test)?|brf(?:\s+test)?){_HEADING_TAIL}",
        re.I,
    ),
    "414(s)": re.compile(
        rf"^414\s*\(\s*s\s*\)(?:\s+compensation)?(?:\s+test)?{_HEADING_TAIL}",
        re.I,
    ),
    "415": re.compile(
        rf"^(?!.*\bfailure\b)(?:415(?:\s*\(\s*c\s*\))?|415\s+limit|"
        rf"annual additions(?:\s*\(\s*irc\s*415\s*\))?)(?:\s+limit)?(?:\s+annual additions)?"
        rf"(?:\s+test)?{_HEADING_TAIL}",
        re.I,
    ),
    "Top Heavy": re.compile(
        rf"^(?:top\s*[- ]?heavy)(?:\s+determinations?)?(?:\s+test)?{_HEADING_TAIL}",
        re.I,
    ),
    "Census": re.compile(
        rf"^(?:employee\s+)?census(?:\s+report)?{_HEADING_TAIL}",
        re.I,
    ),
}
_WRAPPER_PAGE = re.compile(
    r"cover letter|as you requested|we are pleased to provide|"
    r"result summary|test summary|summary of results|summary of compliance|"
    r"immediate action required|no immediate action is required|"
    r"failed compliance testing|excess return notice|sample/draft communication",
    re.I,
)

# Pages an ADP/ACP-only or ACP-only package is allowed to contain.
_ONLY_SECTIONS = {
    "Cover Letter",
    "Test Summary",
    "Action Required",
    "HCE/Key",
    "Future HCE",
    "ADP/ACP",
    "Failed Test Notice",
    "ADP/ACP Excess After 12 Months Current",
    "ADP/ACP Excess After 12 Months Prior",
    "ADP/ACP Excess Current Year",
    "ADP/ACP Failure Letter",
}
_ONLY_BOOKMARKS = {"Cover Letter", "Test Summary", "HCE/Key", "Future HCE", "ADP/ACP"}


def add_bookmarks(
    doc: fitz.Document,
    profile: PlanProfile,
    source_files: list[str] | None = None,
) -> int:
    """Write the section bookmarks onto the assembled PDF.

    Purpose:
        Build the bookmark list from the pages that are actually in the package.

    Args:
        doc: Open assembled PDF. Page 1 is the cover. Must not be closed.
        profile: Plan profile. ``plan_type`` selects 403(b) bookmark titles.
        source_files: Uploaded file names used to tell an ADP report from an ACP report.
            ``None`` means no file names.

    Returns:
        How many top-level bookmarks were written. Child bookmarks are not counted.

    Raises:
        None. A missing section is skipped. PyMuPDF raises if ``doc`` is closed.

    Example:
        A 403(b) profile stores the ADP/ACP bookmark as "ACP Test".
        ``add_bookmarks(doc, profile, ["555403 ACP Test.pdf"])`` returns the number of sections found.

    Side effects:
        Replaces the outline stored on ``doc``. Does not save the file.
    """
    titles = _bookmark_map()
    overrides = bookmark_overrides(profile.plan_type)
    keep_brf = bool(package_flags(profile.plan_type).get("keep_brf"))
    entries: list[tuple[str, int]] = []
    toc: list[list] = []
    for name in _SOP_SECTION_ORDER:
        title = overrides.get(name) or titles.get(name)
        if name == "ADP/ACP" and name not in overrides:
            title = adp_acp_bookmark_title(profile, doc, source_files)
        if name == "BRF" and not keep_brf:
            continue
        page = _find_section_page(doc, name) or _tagged_section_page(doc, name)
        if page is None:
            continue
        if not title:
            continue
        entries.append((title, page))
    pages = [page for _title, page in entries]
    for index, (title, page) in enumerate(entries):
        toc.append([1, title, page])
        if title in _ADP_TITLES:
            for child, child_page in _adp_children(doc, page, doc.page_count + 1):
                toc.append([2, child, child_page])
    # collapse=0 keeps child bookmarks expanded. A zoom of 0 on a GoTo action is
    # not a valid destination: the viewer then stays put and closes the sidebar.
    doc.set_toc(toc, collapse=0)
    _normalize_outline_destinations(doc)
    return len([row for row in toc if row[0] == 1])


def is_testing_only(doc: fitz.Document) -> bool:
    """Decide whether the package is only the ADP/ACP testing set.

    Purpose:
        A testing-only package uses a shorter bookmark list than a full valuation.

    Args:
        doc: Open PDF. A Test Summary line by itself does not make the package a full valuation.

    Returns:
        ``True`` when no allocation, variance, or other full-valuation report page is present.
        ``False`` when any other report page is found.

    Raises:
        None.

    Example:
        A package of cover, summary, action required, HCE, and ADP/ACP returns ``True``.
        Adding a Top Heavy report page returns ``False``.

    Side effects:
        None. This function only reads the PDF.
    """
    from services.package_polish import is_compliance_overview

    specs = [
        spec
        for spec in load_section_specs()
        if str(spec.get("name") or "") not in _ONLY_SECTIONS
    ]
    for page in doc:
        text = page.get_text("text") or ""
        if not text.strip() or _WRAPPER_PAGE.search(text) or is_compliance_overview(text):
            continue
        for spec in specs:
            aliases = [str(spec.get("name") or "")] + [str(alias) for alias in (spec.get("aliases") or [])]
            for alias in aliases:
                if len(alias) < 3:
                    continue
                if re.search(re.escape(alias), text, re.I):
                    return False
    return True


def _normalize_outline_destinations(doc: fitz.Document) -> None:
    """Make each bookmark open its page without closing the sidebar.

    Purpose:
        Replace a GoTo action whose zoom is 0 with a destination the viewer accepts.

    Args:
        doc: Open PDF whose outline was just written by ``add_bookmarks``.

    Returns:
        None.

    Raises:
        None. A bookmark object that cannot be read is skipped.

    Example:
        After ``add_bookmarks``, a click on "Cover Letter" opens page 1 and leaves the sidebar open.

    Side effects:
        Rewrites outline objects inside ``doc``. Does not save the file.
    """
    for xref in range(1, doc.xref_length()):
        try:
            raw = doc.xref_object(xref)
        except Exception:
            continue
        if "/Title" not in raw or "/A" not in raw:
            continue
        kind, action = doc.xref_get_key(xref, "A")
        if kind != "dict":
            continue
        match = re.search(r"/D\s*(\[[^\]]+\])", action)
        if not match:
            continue
        dest = re.sub(r"\s+0(\s*\])", r" null\1", match.group(1))
        doc.xref_set_key(xref, "Dest", dest)
        obj = re.sub(r"/A\s+<<.*?>>", "", doc.xref_object(xref), count=1, flags=re.S)
        obj = re.sub(r"/A\s+null", "", obj, count=1)
        doc.update_object(xref, obj)


def _adp_children(doc: fitz.Document, start_page: int, end_page: int) -> list[tuple[str, int]]:
    """Find the ADP/ACP child bookmarks.

    Purpose:
        Add Summary, Detail, and Corrections under the ADP/ACP bookmark.

    Args:
        doc: Open PDF.
        start_page: First page to search. Page numbers start at 1.
        end_page: First page not to search. Must be greater than ``start_page``.

    Returns:
        ``[(title, page), ...]`` in the order Summary, Detail, Corrections.
        A child that is not on the page is omitted.

    Raises:
        None.

    Example:
        Pages headed "Summary" then "Detail" return ``[("Summary", n), ("Detail", n + 1)]``.

    Side effects:
        None. This function only reads the PDF.
    """
    found: dict[str, int] = {}
    patterns = {
        "Summary": re.compile(r"^(?:adp\s*/\s*acp\s+)?(?:adp\s*/\s*acp\s+)?summary$", re.I),
        "Detail": re.compile(r"^(?:adp\s*/\s*acp\s+)?(?:test\s+)?detail$", re.I),
        "Corrections": re.compile(r"^(?:adp\s*/\s*acp\s+)?corrections?$", re.I),
    }
    for index, page in enumerate(doc):
        if index + 1 < start_page or index + 1 >= end_page:
            continue
        if _is_summary_or_overview(page):
            continue
        lines = _heading_lines(page)
        for title, pattern in _ADP_CHILD:
            heading = patterns[title]
            if any(heading.fullmatch(line) for line in lines):
                found.setdefault(title, index + 1)
                break
    return [(title, found[title]) for title in _ADP_CHILD_ORDER if title in found]


def _heading_lines(page: fitz.Page) -> list[str]:
    """Read the heading lines at the top of one page.

    Purpose:
        Give the bookmark search the printed headings, not words inside a paragraph.

    Args:
        page: One PDF page.

    Returns:
        The non-empty lines among the first 40 lines, with extra spaces removed.

    Raises:
        None.

    Example:
        A page whose first line is "Top Heavy Test" returns a list starting with that line.

    Side effects:
        None.
    """
    return [
        re.sub(r"\s+", " ", line).strip(" \t\r\n:·")
        for line in (page.get_text("text") or "").splitlines()[:40]
        if line.strip()
    ]


def _find_section_page(doc: fitz.Document, section_name: str) -> int | None:
    """Find the page where a report section starts.

    Purpose:
        Point a bookmark at the page whose heading matches that section.

    Args:
        doc: Open PDF. An empty document has no pages.
        section_name: A name from the SOP section list, such as "Top Heavy" or "Cover Letter".

    Returns:
        The page number, starting at 1. ``None`` when the heading is not in the document.
        "Cover Letter" returns 1 when the document has at least one page.

    Raises:
        None.

    Example:
        ``_find_section_page(doc, "Cover Letter")`` returns ``1`` for a non-empty PDF.

    Side effects:
        None.
    """
    if section_name == "Cover Letter":
        return 1 if doc.page_count else None
    pattern = _SECTION_HEADINGS.get(section_name)
    if pattern is None:
        return None
    found: list[int] = []
    for index, page in enumerate(doc):
        if section_name != "Test Summary" and _is_summary_or_overview(page):
            continue
        if any(pattern.fullmatch(line) for line in _heading_lines(page)):
            found.append(index + 1)
    if not found:
        return None
    # A contents line on the cover is not the report. Use the later page.
    later = [page_number for page_number in found if page_number > 1]
    return later[0] if later else found[0]


def _tagged_section_page(doc: fitz.Document, section_name: str) -> int | None:
    """First page that came from an uploaded file matched to ``section_name``, or ``None``."""
    for index, page in enumerate(doc):
        if page_section(page) == section_name:
            return index + 1
    return None


def _is_summary_or_overview(page: fitz.Page) -> bool:
    """Tell a summary or overview page from a real report page.

    Purpose:
        Stop a heading mentioned on the summary from being treated as the report itself.

    Args:
        page: One PDF page.

    Returns:
        ``True`` when the page is a compliance overview or the Test Summary.
        ``False`` for a report page.

    Raises:
        None.

    Example:
        A page headed "Compliance Testing Summary of Results" returns ``True``.

    Side effects:
        None.
    """
    from services.package_polish import is_compliance_overview

    text = page.get_text("text") or ""
    if is_compliance_overview(text):
        return True
    return any(_SECTION_HEADINGS["Test Summary"].fullmatch(line) for line in _heading_lines(page))


def _bookmark_page(doc: fitz.Document, section_name: str, detected_page: int) -> int:
    """Choose the page number a bookmark should open.

    Purpose:
        Keep the ADP/ACP bookmark on the test report, not on a cover sentence that mentions the test.

    Args:
        doc: Open PDF.
        section_name: Section being bookmarked.
        detected_page: Page number already found for that section. Must be at least 1.

    Returns:
        A page number inside the document. An ADP/ACP heading elsewhere in the PDF wins
        over ``detected_page``.

    Raises:
        None.

    Example:
        An empty document returns ``1``. A detected page past the last page is clamped to the last page.

    Side effects:
        None.
    """
    if section_name == "ADP/ACP":
        for index, page in enumerate(doc):
            if _TEST_HEADING.search(page.get_text("text") or ""):
                return index + 1
    if doc.page_count == 0:
        return 1
    return max(1, min(detected_page, doc.page_count))


def adp_acp_bookmark_title(
    profile: PlanProfile,
    doc: fitz.Document | None = None,
    source_files: list[str] | None = None,
) -> str:
    """Choose the ADP/ACP bookmark title.

    Purpose:
        Name the bookmark "ADP Test", "ACP Test", or "ADP/ACP Tests" from what was uploaded.

    Args:
        profile: Plan profile. A 403(b) plan uses the title from plan_403b.yaml.
        doc: Open PDF, or ``None`` when only file names should be checked.
        source_files: Uploaded file names. ``None`` means no file names.

    Returns:
        "ACP Test" for a 403(b) plan. Otherwise "ADP Test", "ACP Test", or "ADP/ACP Tests".

    Raises:
        None.

    Example:
        ``adp_acp_bookmark_title(profile)`` returns "ACP Test" when ``profile.plan_type`` is "403b".
        A file named "555001 ADP Test.pdf" on a 401(k) plan returns "ADP Test".

    Side effects:
        None. Reads plan_403b.yaml when the plan is 403(b).
    """
    override = bookmark_overrides(profile.plan_type).get("ADP/ACP")
    if override:
        return override
    has_adp, has_acp = _adp_acp_present(source_files or [], doc)
    if has_adp and not has_acp:
        return "ADP Test"
    if has_acp and not has_adp:
        return "ACP Test"
    return "ADP/ACP Tests"


def _adp_acp_present(source_files: list[str], doc: fitz.Document | None) -> tuple[bool, bool]:
    """See whether the package contains an ADP report, an ACP report, or both.

    Purpose:
        Decide which ADP/ACP bookmark title matches the uploaded files and page headings.

    Args:
        source_files: Uploaded file names. An empty list means no file names.
        doc: Open PDF, or ``None`` to look at file names only.

    Returns:
        ``(has_adp, has_acp)``. A file or heading that names both tests sets both to ``True``.

    Raises:
        None.

    Example:
        ``_adp_acp_present(["555001 ADP Test.pdf"], None)`` returns ``(True, False)``.

    Side effects:
        None.
    """
    blob = " ".join(_file_tokens(name) for name in source_files)
    has_adp = bool(_ADP_FILE.search(blob) or _BOTH_FILE.search(blob))
    has_acp = bool(_ACP_FILE.search(blob) or _BOTH_FILE.search(blob))
    if doc is not None:
        page_text = "\n".join((page.get_text("text") or "") for page in doc)
        if _BOTH_HEADING.search(page_text):
            has_adp = True
            has_acp = True
        if _ADP_HEADING.search(page_text):
            has_adp = True
        if _ACP_HEADING.search(page_text):
            has_acp = True
    return has_adp, has_acp


def _file_tokens(name: str) -> str:
    """Turn a file name into lowercase words.

    Purpose:
        Let the ADP/ACP search ignore punctuation in the file name.

    Args:
        name: A file name. An empty string is allowed.

    Returns:
        The name in lowercase, with every character that is not a letter or digit replaced by a space.

    Raises:
        None.

    Example:
        ``_file_tokens("555001 ADP-Test.pdf")`` returns ``"555001 adp test pdf"``.

    Side effects:
        None.
    """
    return re.sub(r"[^a-z0-9]+", " ", name.lower())


def _bookmark_map() -> dict[str, str]:
    """Load the default bookmark titles.

    Purpose:
        Read the bookmark title for each report section.

    Args:
        None.

    Returns:
        ``{section name: bookmark title}`` from the bookmarks block in config/package_order.yaml.
        A list in that block is returned as ``{item: item}``.

    Raises:
        OSError: config/package_order.yaml cannot be read.
        yaml.YAMLError: that file is not valid YAML.

    Example:
        ``_bookmark_map()["Cover Letter"]`` returns the title stored for Cover Letter.

    Side effects:
        None. This function only reads a file and returns a value.
    """
    raw = load_package_order().get("bookmarks") or {}
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    return {str(item): str(item) for item in raw}

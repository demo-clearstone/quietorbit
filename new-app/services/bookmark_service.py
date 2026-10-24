from __future__ import annotations

import re

import fitz
import yaml

from config.settings import CONFIG_DIR
from models.plan_profile import PlanProfile
from services.file_order import load_section_specs
from services.plan_config import bookmark_overrides, is_403b_plan, package_flags

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
_SECTION_HEADINGS: dict[str, re.Pattern[str]] = {
    "Cover Letter": re.compile(r"^(?:cover letter|cover page)$", re.I),
    "Test Summary": re.compile(r"^(?:compliance testing summary of results|compliance summary|test summary)$", re.I),
    "Contribution Analysis": re.compile(r"^contribution analysis(?:\s+loc(?:ation)?\s*\d+)?$", re.I),
    "HCE/Key": re.compile(r"^(?:hce\s*/\s*key|hce\s*/\s*key employee determinations|hce\s+key)$", re.I),
    "Future HCE": re.compile(r"^(?:future\s+hce|future\s+highly compensated employee(?:s)?(?:\s+projection)?)$", re.I),
    "ADP/ACP": re.compile(r"^(?:adp\s*/\s*acp\s+(?:summary|test results|tests?)|adp\s+(?:summary|test results|tests?)|acp\s+(?:summary|test results|tests?))$", re.I),
    "402(g)": re.compile(r"^(?:402\s*\(\s*g\s*\)|402\s*g)(?:\s+(?:deferral limits?|test))?$", re.I),
    "410(b)": re.compile(r"^(?:410\s*\(\s*b\s*\)|410\s*b)(?:\s+(?:coverage\s+)?test)?$", re.I),
    "401(a)(4)": re.compile(r"^401\s*\(\s*a\s*\)\s*\(\s*4\s*\)(?:\s+test)?$", re.I),
    "Average Benefit Percentage Test": re.compile(r"^(?:average benefit percentage(?: test)?|abpt)$", re.I),
    "BRF": re.compile(r"^(?:benefits,? rights(?: and features)?(?: test)?|brf test)$", re.I),
    "414(s)": re.compile(r"^414\s*\(\s*s\s*\)(?:\s+test)?$", re.I),
    "415": re.compile(r"^(?:415(?:\s*\(\s*c\s*\))?|415\s+limit)(?:\s+(?:annual additions\s+)?test)?$", re.I),
    "Top Heavy": re.compile(r"^(?:top\s*[- ]?heavy)(?:\s+test)?$", re.I),
    "Census": re.compile(r"^census(?:\s+report)?$", re.I),
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
    """Write SOP §O bookmarks for detected sections (TEST23.docx)."""
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
        page = _find_section_page(doc, name)
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
    """True when the package has no allocation, variance, or other test reports.

    A line on the Test Summary does not count. Another report page means the
    full valuation package, and the full bookmark list is used.
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
    """Use /Dest with a null zoom so a click opens that page and leaves the sidebar up.

    PyMuPDF writes /A << /S /GoTo /D [page /XYZ x y 0] >>. Zoom 0 is invalid, and an
    action (instead of /Dest) makes Chrome and Safari close the bookmark panel.
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
    """Summary, Detail, then Corrections inside the ADP/ACP report."""
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
    """Return the page's printed headings, excluding body-text mentions."""
    return [
        re.sub(r"\s+", " ", line).strip(" \t\r\n:·")
        for line in (page.get_text("text") or "").splitlines()[:14]
        if line.strip()
    ]


def _find_section_page(doc: fitz.Document, section_name: str) -> int | None:
    if section_name == "Cover Letter":
        return 1 if doc.page_count else None
    pattern = _SECTION_HEADINGS.get(section_name)
    if pattern is None:
        return None
    for index, page in enumerate(doc):
        if section_name != "Test Summary" and _is_summary_or_overview(page):
            continue
        if any(pattern.fullmatch(line) for line in _heading_lines(page)):
            return index + 1
    return None


def _is_summary_or_overview(page: fitz.Page) -> bool:
    from services.package_polish import is_compliance_overview

    text = page.get_text("text") or ""
    if is_compliance_overview(text):
        return True
    return any(_SECTION_HEADINGS["Test Summary"].fullmatch(line) for line in _heading_lines(page))


def _bookmark_page(doc: fitz.Document, section_name: str, detected_page: int) -> int:
    """The cover sentence 'ADP/ACP test is included' is not the test bookmark."""
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
    """TEST23 §O: ADP Test, ACP Test, or ADP/ACP Tests from what is in the package."""
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
    return re.sub(r"[^a-z0-9]+", " ", name.lower())


def _bookmark_map() -> dict[str, str]:
    data = yaml.safe_load((CONFIG_DIR / "package_order.yaml").read_text(encoding="utf-8")) or {}
    raw = data.get("bookmarks") or {}
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    return {str(item): str(item) for item in raw}

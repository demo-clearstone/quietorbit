from __future__ import annotations

import re

import fitz
import yaml

from config.settings import CONFIG_DIR
from models.plan_profile import PlanProfile
from services.file_order import load_section_specs
from services.plan_config import bookmark_overrides, is_457_plan, package_flags

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
    testing_only = (
        is_testing_only(doc) and not profile.midyear and not is_457_plan(profile.plan_type)
    )
    entries: list[tuple[str, int]] = []
    seen: set[str] = set()
    for section in profile.detected_sections:
        if testing_only and section.name not in _ONLY_BOOKMARKS:
            continue
        if section.name == "BRF" and not keep_brf:
            continue
        if section.name in {"Variance", "PS Variance", "SHNE Variance", "Compensation Limit Failure Summary"}:
            continue
        title = overrides.get(section.name) or titles.get(section.name)
        if not title:
            continue
        if section.name == "ADP/ACP" and section.name not in overrides:
            title = adp_acp_bookmark_title(profile, doc, source_files)
        if title in seen:
            continue
        page = _bookmark_page(doc, section.name, section.page)
        entries.append((title, page))
        seen.add(title)
    toc: list[list] = []
    pages = [page for _title, page in entries]
    for index, (title, page) in enumerate(entries):
        toc.append([1, title, page, _destination(page)])
        if title in _ADP_TITLES:
            end = pages[index + 1] if index + 1 < len(pages) else doc.page_count + 1
            if end <= page:
                end = doc.page_count + 1
            for child, child_page in _adp_children(doc, page, end):
                toc.append([2, child, child_page, _destination(child_page)])
    doc.set_toc(toc)
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


def _destination(page: int) -> dict:
    return {
        "kind": fitz.LINK_GOTO,
        "page": page - 1,
        "to": fitz.Point(0, 0),
        "zoom": 0,
    }


def _adp_children(doc: fitz.Document, start_page: int, end_page: int) -> list[tuple[str, int]]:
    """Summary, Detail, then Corrections inside the ADP/ACP report."""
    found: dict[str, int] = {}
    last = min(end_page, doc.page_count + 1)
    for index in range(max(start_page, 1) - 1, last - 1):
        lines = [line.strip() for line in (doc[index].get_text("text") or "").splitlines() if line.strip()]
        head = " ".join(lines[:4])
        for title, pattern in _ADP_CHILD:
            if pattern.search(head):
                found.setdefault(title, index + 1)
                break
    return [(title, found[title]) for title in _ADP_CHILD_ORDER if title in found]


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
    data = yaml.safe_load((CONFIG_DIR / "sections.yaml").read_text(encoding="utf-8")) or {}
    raw = data.get("bookmarks") or {}
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items()}
    return {str(item): str(item) for item in raw}

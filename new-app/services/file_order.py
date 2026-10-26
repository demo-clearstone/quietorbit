from __future__ import annotations

import contextlib
import contextvars
import re

from services.plan_config import load_package_order

# Names passed together so 2026HCE and 2027HCE can be told apart.
_MATCH_NAMES: contextvars.ContextVar[tuple[str, ...]] = contextvars.ContextVar(
    "match_names",
    default=(),
)
_PLAIN_HCE_YEAR = re.compile(r"(20\d{2})\s*hce(?!\s*key)\b", re.I)
_HCE_KEY_FILE = re.compile(r"hce\s*/?\s*key", re.I)
_FUTURE_HCE_FILE = re.compile(r"fy\s*hce|future(?:\s*year)?\s*hce", re.I)


def load_section_specs() -> list[dict]:
    """Input: none. Calls load_package_order. Output: the expected_order list from package_order.yaml.

    Purpose:
        Input: none. Calls load_package_order. Output: the expected_order list from package_order.yaml.

    Args:
        None.

    Returns:
        list[dict].

    Raises:
        yaml.YAMLError: A YAML file is not valid.

    Example:
        load_section_specs() returns list[dict].

    Side effects:
        None. This function only reads data and returns a value.
    """
    return list(load_package_order().get("expected_order") or [])


def _norm(value: str) -> str:
    """Norm.

    Purpose:
        Norm.

    Args:
        value: Value. Type: str.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _norm("text") returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _spec_aliases(spec: dict) -> list[str]:
    """Spec aliases.

    Purpose:
        Spec aliases.

    Args:
        spec: Spec. Type: dict.

    Returns:
        a list of str.

    Raises:
        None.

    Example:
        _spec_aliases({}) returns a list of str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return [str(spec.get("name") or "")] + [str(a) for a in (spec.get("aliases") or [])]


def _rank(spec: dict, fallback: int) -> int:
    """Input: one expected_order entry. Output: its index in combine_order from package_order.yaml.

    Purpose:
        Input: one expected_order entry. Output: its index in combine_order from package_order.yaml.

    Args:
        spec: Spec. Type: dict.
        fallback: Fallback. Type: int.

    Returns:
        a int.

    Raises:
        yaml.YAMLError: A YAML file is not valid.

    Example:
        _rank({}, 1) returns a int.

    Side effects:
        None. This function only reads data and returns a value.
    """
    order = [str(name) for name in (load_package_order().get("combine_order") or [])]
    name = str(spec.get("name") or "")
    try:
        return order.index(name)
    except ValueError:
        return len(order) + fallback


def _plain_hce_year(filename: str) -> int | None:
    """Year on a plain HCE report name such as 2026HCE, or None for HCEKey and FYHCE."""
    stem = re.sub(r"\.[^.]+$", "", filename or "")
    if _FUTURE_HCE_FILE.search(stem) or _HCE_KEY_FILE.search(stem):
        return None
    match = _PLAIN_HCE_YEAR.search(stem)
    return int(match.group(1)) if match else None


def _valuation_year(names: tuple[str, ...]) -> int | None:
    """Plan year printed in the valuation package file name, such as 2026 in a 403(b) package."""
    for name in names:
        if not re.search(r"valuation", name, re.I):
            continue
        if not re.search(r"401|403|457", name, re.I):
            continue
        years = re.findall(r"20\d{2}", name)
        if years:
            return int(years[0])
    return None


def hce_section_name(filename: str) -> str | None:
    """Choose HCE/Key or Future HCE for a plain YYYYHCE file.

    A 403(b) package names the current report 2026HCE and the next year 2027HCE.
    The later year is Future HCE. The package year, or the earlier file, is HCE/Key.
    HCEKey and FYHCE keep their own names and return None here.
    """
    year = _plain_hce_year(filename)
    if year is None:
        return None
    names = _MATCH_NAMES.get() or (filename,)
    plain_years = [found for name in names if (found := _plain_hce_year(name)) is not None]
    package_year = _valuation_year(names)
    has_key_file = any(_HCE_KEY_FILE.search(name) for name in names)
    later_than_another = any(other < year for other in plain_years)
    later_than_package = package_year is not None and year > package_year
    if later_than_another or has_key_file or later_than_package:
        return "Future HCE"
    return "HCE/Key"


def _spec_named(name: str) -> dict | None:
    for spec in load_section_specs():
        if str(spec.get("name") or "") == name:
            return spec
    return None


@contextlib.contextmanager
def use_filename_batch(names: list[str]):
    """Let file matching see every uploaded name, so 2026HCE is not treated as 2027HCE."""
    token = _MATCH_NAMES.set(tuple(names))
    try:
        yield
    finally:
        _MATCH_NAMES.reset(token)


def _best_section(filename: str) -> tuple[int, dict] | None:
    """Longest keyword match wins so SHMaVar is not treated as MaVar, 401a4 is not 401k, etc.

    Purpose:
        Longest keyword match wins so SHMaVar is not treated as MaVar, 401a4 is not 401k, etc.

    Args:
        filename: File name, including the extension.

    Returns:
        tuple[int, dict] | None.

    Raises:
        None.

    Example:
        _best_section("text") returns tuple[int, dict] | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    forced = hce_section_name(filename)
    if forced:
        spec = _spec_named(forced)
        if spec:
            specs = load_section_specs()
            index = next(
                (item_index for item_index, item in enumerate(specs) if str(item.get("name") or "") == forced),
                0,
            )
            return _rank(spec, index), spec
    name = _norm(filename)
    specs = load_section_specs()
    paged = re.search(r"_p0*(\d+)(?:\.[^.]+)?$", filename, re.I)
    if paged:
        page = int(paged.group(1))
        parent = re.sub(r"_p0*\d+(?=\.[^.]+$)", "", filename, flags=re.I)
        parent_norm = _norm(parent)
        for spec in specs:
            if not spec.get("split_pages"):
                continue
            if not any(
                (token := _norm(alias)) and token in parent_norm
                for alias in _spec_aliases(spec)
            ):
                continue
            labels = [
                str(item)
                for item in (spec.get("split_page_labels") or COVER_PACKET_PAGE_LABELS)
            ]
            if 1 <= page <= len(labels):
                return _best_label_section(labels[page - 1], specs)
    best: tuple[int, int, dict] | None = None
    for index, spec in enumerate(specs):
        for alias in _spec_aliases(spec):
            token = _norm(alias)
            if not token or token not in name:
                continue
            score = (len(token), index)
            if best is None or score > (best[0], best[1]):
                best = (len(token), index, spec)
    if not best:
        return None
    _, spec_index, spec = best
    return _rank(spec, spec_index), spec


def _best_label_section(label: str, specs: list[dict]) -> tuple[int, dict] | None:
    """Best label section.

    Purpose:
        Best label section.

    Args:
        label: Label. Type: str.
        specs: Specs. Type: list[dict].

    Returns:
        a tuple[int, dict] | None.

    Raises:
        None.

    Example:
        _best_label_section("text", []) returns a tuple[int, dict] | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    name = _norm(label)
    best: tuple[int, int, dict] | None = None
    for index, spec in enumerate(specs):
        for alias in _spec_aliases(spec):
            token = _norm(alias)
            if not token or token not in name:
                continue
            score = (len(token), index)
            if best is None or score > (best[0], best[1]):
                best = (len(token), index, spec)
    if not best:
        return None
    _, spec_index, spec = best
    return _rank(spec, spec_index), spec


def matched_spec(filename: str) -> dict | None:
    """Matching a file name to its report section.

    Purpose:
        Matching a file name to its report section.

    Args:
        filename: File name, including the extension.

    Returns:
        dict | None.

    Raises:
        None.

    Example:
        matched_spec("text") returns dict | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    found = _best_section(filename)
    return found[1] if found else None


def sop_rank(filename: str) -> int:
    """Lower rank = earlier in TEST23 combine order. Unknown files stay last.

    Purpose:
        Lower rank = earlier in TEST23 combine order. Unknown files stay last.

    Args:
        filename: File name, including the extension.

    Returns:
        int.

    Raises:
        None.

    Example:
        sop_rank("text") returns int.

    Side effects:
        None. This function only reads data and returns a value.
    """
    found = _best_section(filename)
    if found:
        return found[0]
    return 1000 + len(_norm(filename))


def should_split_pages(filename: str, pages: int) -> bool:
    """Should split pages.

    Purpose:
        Should split pages.

    Args:
        filename: File name, including the extension.
        pages: Pages. Type: int.

    Returns:
        True or False.

    Raises:
        None.

    Example:
        should_split_pages("text", 1) returns True or False.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if not filename.lower().endswith(".pdf") or pages <= 1:
        return False
    spec = matched_spec(filename)
    return bool(spec and spec.get("split_pages"))


COVER_PACKET_PAGE_LABELS = [
    "Cover Letter",
    "Action required page 1",
    "Action required page 2",
    "Action required page 3",
    "ADP/ACP Failure excess page after 12 months (Current year Testing Method)",
    "ADP/ACP Failure excess page after 12 months (Prior year Testing Method)",
    "ADP/ACP Failure excess page Current year",
    "415 Failure information",
    "ADP/ACP Failure letter",
    "402g Failure letter",
    "415 Failure letter",
    "Year End Recap",
    "Compliance Report 1",
    "Compliance Report 2",
    "Compliance Report 3",
]


def display_label(filename: str, page: int = 0, page_count: int = 1) -> str:
    """UI name after upload/split (packet outline titles, not the raw filename).

    Purpose:
        UI name after upload/split (packet outline titles, not the raw filename).

    Args:
        filename: File name, including the extension.
        page: One PDF page.
        page_count: Page count. Type: int.

    Returns:
        a str.

    Raises:
        None.

    Example:
        display_label("text", page, 1) returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    spec = matched_spec(filename)
    if spec:
        base = str(spec.get("label") or spec.get("name") or filename)
        page_labels = [str(item) for item in (spec.get("split_page_labels") or []) if str(item).strip()]
        if spec.get("split_pages") and not page_labels:
            page_labels = list(COVER_PACKET_PAGE_LABELS)
        if page > 0 and page_count > 1 and page_labels:
            if page <= len(page_labels):
                return page_labels[page - 1]
            return f"{base} page {page}"
        return base
    if page > 0 and page_count > 1:
        return f"{filename} (page {page} of {page_count})"
    return filename


def rank_for_label(label: str, fallback: int) -> int:
    """Place a split page by its section title, not by the parent PDF name.

    Purpose:
        Place a split page by its section title, not by the parent PDF name.

    Args:
        label: Label. Type: str.
        fallback: Fallback. Type: int.

    Returns:
        a int.

    Raises:
        None.

    Example:
        rank_for_label("text", 1) returns a int.

    Side effects:
        None. This function only reads data and returns a value.
    """
    found = _best_section(label)
    if not found:
        return fallback
    return found[0]


def page_label_from_text(text: str, fallback: str) -> str:
    """Recognize key packet pages instead of relying only on physical position.

    Purpose:
        Recognize key packet pages instead of relying only on physical position.

    Args:
        text: Text from a page or a file.
        fallback: Fallback. Type: str.

    Returns:
        a str.

    Raises:
        None.

    Example:
        page_label_from_text("text", "text") returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    lines = [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines() if line.strip()]
    body = " ".join(lines[:12])
    if not body:
        return fallback
    # Classify headings, not references in paragraph text: cover letters and
    # action notices often mention the summary, testing failures, or reports.
    first = lines[0]
    head = " ".join(lines[:7])
    if (
        re.search(r"mutual of america|financial group", head, re.I)
        and re.search(r"\bRE\s*:|period ending|valuation package", head, re.I)
    ):
        return "Cover Letter"
    if re.fullmatch(r"(?:compliance testing summary of results|result summary|test summary|compliance summary)", first, re.I):
        return "Test Summary"
    if re.search(r"^(?:immediate action required|attention required|no immediate action is required)\b", first, re.I):
        return "Action required"
    if re.fullmatch(r"annual additions\s*\(irc\s*415\)\s*test failure information", first, re.I):
        return "415 Failure information"
    if re.search(r"\b(?:failed compliance testing|excess return notice)\b", head, re.I):
        if re.search(r"after\s+12[- ]months?", head, re.I):
            if re.search(r"prior method testing", head, re.I):
                return "ADP/ACP Failure excess page after 12 months (Prior year Testing Method)"
            if re.search(r"current method testing", head, re.I):
                return "ADP/ACP Failure excess page after 12 months (Current year Testing Method)"
        return "ADP/ACP Failure excess page Current year"
    if re.match(r"^sample/draft communication", first, re.I):
        if re.search(r"402\s*\(\s*g\s*\)|402\s*g deferral", head, re.I):
            return "402g Failure letter"
        if re.search(r"annual additions|415", head, re.I):
            return "415 Failure letter"
        if re.search(r"adp|acp", head, re.I):
            return "ADP/ACP Failure letter"
    if re.match(r"^year[- ]end recap\b", first, re.I) or re.fullmatch(r"important information", first, re.I):
        return "Year End Recap"
    if re.search(r"^(?:compliance and administrative reports|overview and descriptions|compliance reports)$", " ".join(lines[:2]), re.I):
        return "Compliance Reports"
    if re.fullmatch(r"annual valuation report", first, re.I):
        return "Action required"
    return fallback


def list_file_meta(
    name: str,
    size: int,
    pages: int,
    page_texts: list[str] | None = None,
) -> dict:
    """List file meta.

    Purpose:
        List file meta.

    Args:
        name: File name or section name.
        size: Size. Type: int.
        pages: Pages. Type: int.
        page_texts: Page texts. Type: list[str] | None.

    Returns:
        a dict.

    Raises:
        None.

    Example:
        list_file_meta("text", 1, 1) returns a dict.

    Side effects:
        None. This function only reads data and returns a value.
    """
    split = should_split_pages(name, pages)
    labels = (
        [display_label(name, page=page, page_count=pages) for page in range(1, pages + 1)]
        if split
        else [display_label(name)]
    )
    if split and page_texts:
        labels = [
            page_label_from_text(
                page_texts[index] if index < len(page_texts) else "",
                label,
            )
            for index, label in enumerate(labels)
        ]
    file_rank = sop_rank(name)
    return {
        "name": name,
        "size": size,
        "pages": pages,
        "split": split,
        "rank": file_rank,
        "ranks": [rank_for_label(label, file_rank) for label in labels],
        "label": labels[0],
        "labels": labels,
    }


_LOCATION = re.compile(r"loc(?:ation)?[\s._-]*0*(\d+)", re.I)


def location_index(filename: str) -> int:
    """Loc 1 before Loc 2. A file with no location stays first in its section.

    Purpose:
        Loc 1 before Loc 2. A file with no location stays first in its section.

    Args:
        filename: File name, including the extension.

    Returns:
        int.

    Raises:
        None.

    Example:
        location_index("text") returns int.

    Side effects:
        None. This function only reads data and returns a value.
    """
    match = _LOCATION.search(filename or "")
    return int(match.group(1)) if match else 0


def order_uploads(uploads: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    """Ordering the PDFs into report sequence.

    Purpose:
        Ordering the PDFs into report sequence.

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
    with use_filename_batch([name for name, _data in uploads]):
        return sorted(uploads, key=lambda item: (sop_rank(item[0]), location_index(item[0]), item[0].lower()))

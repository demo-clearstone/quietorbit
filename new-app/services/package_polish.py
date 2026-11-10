"""Client updates from the revised valuation-package instructions.

Drops a BRF report, reorders pages inside ADP/ACP, 410(b), and component
benefit tests, removes wording MOA packages do not use, and adds the
checks those instructions ask the reviewer to make.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import TYPE_CHECKING

import fitz

from models.plan_profile import PlanProfile
from models.review import ValidationItem
from services.file_order import matched_spec
from services.plan_config import is_457_plan, load_compliance_summary, package_flags

if TYPE_CHECKING:
    from models.plan_profile import PlanProfile

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
_LETTER_DATE = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(\d{1,2}),\s+(20\d{2})\b",
    re.I,
)
_SUMMARY = re.compile(
    r"result summary|test summary|testing summary of results|416\s+top heavy",
    re.I,
)
_BRF_REPORT = re.compile(r"benefits,?\s+rights and features|\bBRF\s+Test\b", re.I)
_KEEP_PAGE = re.compile(
    r"result summary|test summary|testing summary|action required|cover letter|year end recap",
    re.I,
)
_SOC_PAGE = re.compile(r"statement of contribution", re.I)
_DISALLOWED_LINE = re.compile(
    r"escalat|form\s+5500|5500\s+wording|audited\s+wording|statement of contribution|(?-i:\bSOC\b)(?!\.?\s*sec)",
    re.I,
)
_DISALLOWED_EXCEPT_SOC = re.compile(
    r"escalat|form\s+5500|5500\s+wording|audited\s+wording",
    re.I,
)
_COMPLIANCE = re.compile(
    r"compliance and administrative|overview and descriptions|compliance report",
    re.I,
)
_EXCESS = re.compile(r"excess return|failure notice|failed compliance|qnec", re.I)
_VARIANCE = re.compile(r"variance", re.I)
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_BAD_ZERO = re.compile(r"(?<!\d)\$?\s*(0(?:\.0+)?)(?!\d)")
_NAME_LINE = re.compile(r"^[A-Za-z][A-Za-z' .-]+,\s+[A-Za-z]")
_PASS_FAIL = (
    ("401(a)(4)", r"401\s*\(\s*a\s*\)\s*\(\s*4\s*\)", "401a4"),
    ("414(s)", r"414\s*\(\s*s\s*\)", "414s"),
    ("402(g)", r"402\s*\(?\s*g\s*\)?", "402g"),
    ("415", r"415(?:\s*\(\s*c\s*\))?|Annual Additions", "415"),
    ("ADP", r"Average Deferral Percentage|\bADP\b", "adp"),
    ("ACP", r"Average Contribution Percentage|\bACP\b", "acp"),
)
_410_LINE = re.compile(
    r"(Standard|401\s*\(\s*k\s*\)|401\s*\(\s*m\s*\))\s*:\s*(Pass|Fail)"
    r"(?:\s*/\s*Fail)?"
    r"(?:\s+Ratio\s+percent\s+(\d+(?:\.\d+)?)\s*%)?",
    re.I,
)
_PAGE_SUMMARY_HEAD = re.compile(r"^(?:compliance testing summary of results|compliance summary|test summary)$", re.I)
_TOP_HEAVY_HEAD = re.compile(r"^top\s*[- ]?heavy(?:\s+test)?$", re.I)
_ABPT_PASSED = re.compile(
    r"average benefits test passed;\s*no action needed for failed\s+410\s*\(?b\)?\s*coverage test",
    re.I,
)
_BRF_RESULT = re.compile(
    r"benefits,?\s+rights(?:\s+and\s+features)?[\s\S]{0,60}?(Pass\s*/\s*Fail|\bPass\b|\bFail\b)",
    re.I,
)


def hce_max_percent(nhce: float) -> float:
    """Prior-year HCE maximum from the NHCE actual deferral percentage.

    Purpose:
        Prior-year HCE maximum from the NHCE actual deferral percentage.

    Args:
        nhce: Nhce. Type: float.

    Returns:
        a float.

    Raises:
        None.

    Example:
        hce_max_percent(1.0) returns a float.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if nhce < 2:
        return round(nhce * 2, 2)
    if nhce < 8:
        return round(nhce + 2, 2)
    return round(nhce * 1.25, 2)


def cover_date_text(when: datetime | None = None) -> str:
    """Cover date text.

    Purpose:
        Cover date text.

    Args:
        when: When. Type: datetime | None.

    Returns:
        a str.

    Raises:
        None.

    Example:
        cover_date_text(when) returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    when = when or datetime.now()
    return f"{_MONTHS[when.month - 1]} {when.day}, {when.year}"


_VARIANCE_SECTIONS = {"Variance", "PS Variance", "SHNE Variance"}


def has_variance_client_copy(filenames: list[str], doc: fitz.Document) -> bool:
    """A variance client copy in the folder keeps the contributions paragraph.

    Purpose:
        A variance client copy in the folder keeps the contributions paragraph.

    Args:
        filenames: Filenames. Type: list[str].
        doc: Open PDF. Must not be closed.

    Returns:
        True or False.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        has_variance_client_copy([], doc) returns True or False.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for name in filenames:
        spec = matched_spec(name)
        if spec and spec.get("name") in _VARIANCE_SECTIONS:
            return True
    for page in doc:
        text = page.get_text("text") or ""
        if re.search(r"action required", text, re.I):
            continue
        if re.search(r"(?<!no )variance report|\bps\s*variance\b|\bshne\s*variance\b", text, re.I):
            return True
    return False


def package_is_403b(uploads: list[tuple[str, bytes]]) -> bool:
    """A 403(b) package keeps the BRF report and does not require a 410(b) file.

    Purpose:
        A 403(b) package keeps the BRF report and does not require a 410(b) file.

    Args:
        uploads: List of (file name, file bytes).

    Returns:
        bool.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        package_is_403b(data) returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for name, data in uploads:
        if re.search(r"403\s*\(?\s*b\)?", name, re.I):
            return True
        if not name.lower().endswith(".pdf") or not data.startswith(b"%PDF"):
            continue
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception:
            continue
        try:
            text = "".join((page.get_text("text") or "") for page in doc[:2])
        finally:
            doc.close()
        if re.search(r"403\s*\(?\s*b\)?", text, re.I):
            return True
    return False


def exclude_brf_uploads(
    uploads: list[tuple[str, bytes]],
    *,
    keep_brf: bool = False,
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """A 401(k) leaves the BRF report out. A 403(b) keeps it and bookmarks it.

    Purpose:
        A 401(k) leaves the BRF report out. A 403(b) keeps it and bookmarks it.

    Args:
        uploads: Pairs of file name and file bytes.
        keep_brf: Keep brf. Type: bool.

    Returns:
        a tuple[list[tuple[str, bytes]], list[str]].

    Raises:
        None.

    Example:
        exclude_brf_uploads(uploads, keep_brf=True) returns a tuple[list[tuple[str, bytes]], list[str]].

    Side effects:
        Changes the PDF or the object passed in.
    """
    if keep_brf:
        return list(uploads), []
    kept: list[tuple[str, bytes]] = []
    notes: list[str] = []
    for name, data in uploads:
        spec = matched_spec(name)
        if spec and spec.get("name") == "BRF":
            notes.append(f"Left out BRF report {name}. The Result Summary line is enough.")
            continue
        kept.append((name, data))
    return kept, notes


def reorder_inner_pages(doc: fitz.Document) -> list[str]:
    """Put inner report pages in the order the instructions list.

    Purpose:
        Put inner report pages in the order the instructions list.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        reorder_inner_pages(doc) returns list[str].

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    texts = [page.get_text("text") or "" for page in doc]
    kinds = [_page_kind(text) for text in texts]
    for number in range(1, len(kinds)):
        # A second employee-listing page has no heading. It stays behind its first page.
        if (
            kinds[number] is None
            and kinds[number - 1] == ("ADP/ACP", 1)
            and _LISTING_CONTINUATION.search(_head(texts[number]) + " " + texts[number][:600])
        ):
            kinds[number] = ("ADP/ACP", 1)
    order = list(range(doc.page_count))
    changed: list[str] = []
    index = 0
    while index < len(kinds):
        family = kinds[index][0] if kinds[index] else None
        if not family:
            index += 1
            continue
        end = index + 1
        while end < len(kinds) and kinds[end] and kinds[end][0] == family:
            end += 1
        block = order[index:end]
        ranked = sorted(block, key=lambda page_index: (kinds[page_index][1], page_index))
        if ranked != block:
            order[index:end] = ranked
            changed.append(family)
        index = end
    if order != list(range(doc.page_count)):
        doc.select(order)
    if not changed:
        return []
    return ["Reordered inner pages for " + ", ".join(dict.fromkeys(changed)) + "."]


def remove_disallowed_wording(doc: fitz.Document, keep_soc: bool = False) -> list[str]:
    """MOA packages do not include audited, SOC, 5500, or escalation wording.

    Purpose:
        MOA packages do not include audited, SOC, 5500, or escalation wording.

    Args:
        doc: Open PDF. Must not be closed.
        keep_soc: True leaves Statement of Contribution wording in the PDF.

    Returns:
        a list of str.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        remove_disallowed_wording(doc, True) returns a list of str.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    removed: list[str] = []
    drop: list[int] = []
    for page in doc:
        text = page.get_text("text") or ""
        if not keep_soc and _SOC_PAGE.search(text) and not _KEEP_PAGE.search(text):
            drop.append(page.number)
            if "Statement of Contribution" not in removed:
                removed.append("Statement of Contribution")
            continue
        if _redact_matching_lines(page, keep_soc=keep_soc):
            if "Disallowed wording" not in removed:
                removed.append("Disallowed wording")
    for number in reversed(drop):
        doc.delete_page(number)
    if not removed:
        return []
    return ["Removed " + ", ".join(removed) + "."]


_ADP_PHRASES = ("ADP/ACP", "ADP / ACP", "ADP and/or ACP", "ADP and ACP")
# Pages of the ADP/ACP test report keep their printed wording.
_ADP_ACP_REPORT_PAGE = re.compile(
    r"nondiscrimination test for plan year end|this plan (?:passes|fails) the", re.I
)
# Excess Return / Failure notice: convert ADP/ACP → ACP, drop ADP QNEC clauses only.
_EXCESS_RETURN_NOTICE_PAGE = re.compile(
    r"excess return notice|failed compliance testing",
    re.I,
)
_LISTING_CONTINUATION = re.compile(r"\b(?:ADP|ACP)\b[\s\S]*compensation[\s\S]*amount", re.I)


def _is_recap_page(text: str) -> bool:
    """Is recap page.

    Purpose:
        Is recap page.

    Args:
        text: Text taken from a page or a file.

    Returns:
        bool.

    Raises:
        None.

    Example:
        _is_recap_page("text") returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return bool(re.search(r"year[- ]end recap|important information", text or "", re.I))


def rewrite_403b_adp_mentions(doc: fitz.Document) -> list[str]:
    """403(b) packages mention ACP only.

    Purpose:
        403(b) packages mention ACP only. ADP/ACP becomes ACP. A Year End Recap page stays, including the bullet that says the plan is not subject to ADP/ACP testing. Other leftover ADP lines are removed.
        Excess Return / Failed Compliance Testing pages only rewrite ADP/ACP → ACP and drop
        ADP QNEC clauses — they are not line-wiped, so QNEC fill can still run.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        rewrite_403b_adp_mentions(doc) returns list[str].

    Side effects:
        Writes or changes a file on disk.
    """
    changed = False
    for page in doc:
        page_text = page.get_text("text") or ""
        if _ADP_ACP_REPORT_PAGE.search(page_text):
            continue
        recap = _is_recap_page(page_text)
        notice = bool(_EXCESS_RETURN_NOTICE_PAGE.search(page_text))
        if notice:
            # Whole-line rewrite: partial redaction destroys shared text objects on this page.
            if _rewrite_403b_excess_notice_page(page):
                changed = True
            continue
        if _rewrite_adp_acp_phrases(page):
            changed = True
        if recap:
            continue
        words = page.get_text("words") or []
        lines: dict[int, list] = {}
        for word in words:
            lines.setdefault(round(float(word[1])), []).append(word)
        boxes: list[fitz.Rect] = []
        for group in lines.values():
            text = " ".join(str(word[4]) for word in group)
            if not re.search(r"\bADP\b", text):
                continue
            boxes.append(
                fitz.Rect(
                    min(word[0] for word in group) - 2,
                    min(word[1] for word in group) - 3,
                    max(word[2] for word in group) + 2,
                    max(word[3] for word in group) + 2,
                )
            )
        if not boxes:
            continue
        for rect in boxes:
            page.add_redact_annot(rect & page.rect, fill=(1, 1, 1))
        page.apply_redactions(images=0, graphics=0)
        for rect in boxes:
            page.draw_rect(rect & page.rect, color=(1, 1, 1), fill=(1, 1, 1), width=0, overlay=True)
        changed = True
    if changed:
        from services.pdf_modifier import _drop_empty_pages

        _drop_empty_pages(doc)
    if not changed:
        return []
    return ["403(b) package uses ACP only. ADP testing wording was removed."]


def _rewrite_403b_excess_notice_page(page: fitz.Page) -> bool:
    """Rewrite Excess Return notice lines to ACP-only wording without mangling neighbors."""
    from services.pdf_modifier import _base_font, _rgb

    jobs: list[tuple[dict, list[dict], str]] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text")]
            if not spans:
                continue
            text = "".join(str(span.get("text") or "") for span in spans)
            updated = text
            for phrase in _ADP_PHRASES:
                updated = re.sub(re.escape(phrase), "ACP", updated, flags=re.I)
            # Drop ADP QNEC clause even if the placeholder was clipped at the page edge.
            updated = re.sub(
                r"\s*The ADP QNEC is\s*\$\S*\.?",
                "",
                updated,
                flags=re.I,
            )
            if updated == text:
                continue
            jobs.append((line, spans, updated))
    if not jobs:
        return False
    for line, _spans, _updated in jobs:
        box = fitz.Rect(line["bbox"])
        page.add_redact_annot(
            fitz.Rect(box.x0 - 0.4, box.y0 + 0.2, box.x1 + 0.4, box.y1 - 0.2),
            fill=(1, 1, 1),
        )
    page.apply_redactions(images=0, graphics=0)
    for _line, spans, updated in jobs:
        span = spans[0]
        origin = span.get("origin") or (span["bbox"][0], span["bbox"][3])
        page.insert_text(
            (float(origin[0]), float(origin[1])),
            updated,
            fontsize=float(span.get("size") or 10),
            fontname=_base_font(str(span.get("font") or ""), int(span.get("flags") or 0)),
            color=_rgb(span.get("color") or 0),
            overlay=True,
        )
    return True


def _rewrite_adp_acp_phrases(page: fitz.Page) -> bool:
    """Replace ADP/ACP phrases with ACP using line-safe inserts."""
    hits: list[fitz.Rect] = []
    for phrase in _ADP_PHRASES:
        hits.extend(page.search_for(phrase))
    if not hits:
        return False
    for rect in hits:
        page.add_redact_annot(
            fitz.Rect(rect.x0 - 0.4, rect.y0 + 0.2, rect.x1 + 0.4, rect.y1 - 0.2),
            fill=(1, 1, 1),
        )
    page.apply_redactions(images=0, graphics=0)
    for rect in hits:
        page.insert_text(
            (rect.x0, rect.y1 - 1),
            "ACP",
            fontsize=max(8.0, min(11.0, rect.height * 0.85)),
            fontname="helv",
            color=(0, 0, 0),
            overlay=True,
        )
    return True


def normalize_report_layout(doc: fitz.Document) -> list[str]:
    """Normalize known text offsets and split merged Amount / % column headings."""
    from services.pdf_modifier import _base_font, _rgb
    from services.source_rewrite import _tight_span_rect

    changed = False
    for page in doc:
        page_text = page.get_text("text") or ""
        # Most pages need no layout fix; skip the expensive dict extract.
        if not re.search(
            r"annual valuation report|year end recap|Amount\s{2,}%|\bcensus\b",
            page_text,
            re.I,
        ):
            continue
        lines = [
            (line, "".join(span.get("text", "") for span in line.get("spans", [])).strip())
            for block in page.get_text("dict").get("blocks", [])
            if block.get("type") == 0
            for line in block.get("lines", [])
        ]
        shifts: list[tuple[dict, float]] = []
        if re.search(r"annual valuation report", page_text, re.I):
            # Client packages often print Action Required copy near x=24/30/36.
            # Bring headings onto the shared column (~40) so rewritten lines match.
            target_action_x = 40.0
            target_green_x = 39.0
            for line, text in lines:
                upper = text.upper()
                x = float(line["bbox"][0])
                if upper == "ACTION REQUIRED" or upper.startswith("IMMEDIATE ACTION REQUIRED") or upper.startswith(
                    "ATTENTION REQUIRED"
                ):
                    delta = target_action_x - x
                    if abs(delta) >= 0.5 and abs(delta) <= 24:
                        shifts.append((line, delta))
                elif upper == "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME":
                    delta = target_green_x - x
                    if abs(delta) >= 0.5 and abs(delta) <= 24:
                        shifts.append((line, delta))
        if re.search(r"year end recap", page_text, re.I):
            for line, text in lines:
                x = float(line["bbox"][0])
                if text.lower() == "important information" and abs(x - 42) >= 0.5 and abs(x - 42) <= 20:
                    shifts.append((line, 42.0 - x))
            start = next(
                (line["bbox"][1] for line, text in lines if "UNIVERSAL AVAILABILITY RULE" in text.upper()),
                None,
            )
            end = next(
                (
                    line["bbox"][3]
                    for line, text in lines
                    if start is not None
                    and line["bbox"][1] >= start
                    and "representative to discuss" in text.lower()
                ),
                None,
            )
            bullet_only = re.compile(r"^[\u2022•\u00b7\u25cf\u25e6\u2219\uf0b7╖■□▪▫*\-·●]+$")
            if start is not None and end is not None:
                shifts.extend(
                    (line, 5.0)
                    for line, text in lines
                    if start - 1 <= line["bbox"][1] and line["bbox"][3] <= end + 1
                    and 60 <= line["bbox"][0] < 98
                    and not bullet_only.match(text.strip())
                )
            # Client expected hanging body column is x≈78. Never drag bullet glyphs
            # from the x≈67 column onto the body column.
            hang_x = 78.0
            for line, text in lines:
                if not text or text.lower() == "important information":
                    continue
                if text.upper() == "YEAR END RECAP":
                    continue
                if bullet_only.match(text.strip()):
                    continue
                x = float(line["bbox"][0])
                if 40 <= x < hang_x - 0.5 and float(line["bbox"][1]) > 120:
                    shifts.append((line, hang_x - x))
        if re.search(r"\bcensus\b", " ".join(text for _line, text in lines[:8]), re.I):
            shifts.extend(
                (line, 6.0)
                for line, text in lines
                if text.casefold() == "name"
                and line["bbox"][1] > 100
                and abs(line["bbox"][0] - 36) < 0.5
            )
        action_shifted = False
        if shifts:
            unique = {id(line): (line, delta) for line, delta in shifts}
            for line, _delta in unique.values():
                spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
                if spans:
                    page.add_redact_annot(_tight_span_rect(spans), fill=(1, 1, 1))
                else:
                    page.add_redact_annot(fitz.Rect(line["bbox"]), fill=(1, 1, 1))
            page.apply_redactions(images=0, graphics=0)
            for line, delta in unique.values():
                line_text = "".join(span.get("text", "") for span in line.get("spans", [])).strip()
                upper = line_text.upper()
                if (
                    upper == "ACTION REQUIRED"
                    or upper.startswith("IMMEDIATE ACTION REQUIRED")
                    or upper.startswith("ATTENTION REQUIRED")
                    or upper == "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME"
                ):
                    action_shifted = True
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text:
                        continue
                    origin = span.get("origin") or (span["bbox"][0], span["bbox"][3])
                    font = _base_font(str(span.get("font") or ""), int(span.get("flags") or 0))
                    try:
                        page.insert_text(
                            (origin[0] + delta, origin[1]),
                            text,
                            fontsize=float(span.get("size") or 10),
                            fontname=font,
                            color=_rgb(span.get("color") or 0),
                            overlay=True,
                        )
                    except Exception:
                        page.insert_text(
                            (origin[0] + delta, origin[1]),
                            text,
                            fontsize=float(span.get("size") or 10),
                            fontname="helv",
                            color=_rgb(span.get("color") or 0),
                            overlay=True,
                        )
            changed = True
        if action_shifted:
            # Text moves to x≈40 but old underlines can remain at x≈24. Wipe short
            # rules under the header, then redraw under the shifted headings.
            from services.pdf_modifier import (
                _clear_short_rules_below,
                _redraw_action_rules,
                _top_header_rule_y,
            )

            header_y = _top_header_rule_y(page)
            _clear_short_rules_below(page, (header_y if header_y is not None else 90.0), redact=True)
            _redraw_action_rules(page)
            changed = True

        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                original = "".join(span.get("text", "") for span in spans).strip()
                if not re.fullmatch(r"Amount\s{2,}%", original) or not spans:
                    continue
                span = spans[0]
                ink = [item for item in spans if item.get("text", "").strip()]
                box = _tight_span_rect(ink) if ink else fitz.Rect(line["bbox"])
                origin = span.get("origin") or (span["bbox"][0], span["bbox"][3])
                size = float(span.get("size") or 8)
                font = _base_font(str(span.get("font") or ""), int(span.get("flags") or 0))
                color = _rgb(span.get("color") or 0)
                page.add_redact_annot(box, fill=(1, 1, 1))
                page.apply_redactions(images=0, graphics=0)
                page.insert_text((288, origin[1]), "Amount", fontsize=size, fontname=font, color=color)
                page.insert_text((360, origin[1]), "%", fontsize=size, fontname=font, color=color)
                changed = True
    return ["Aligned report text and separated merged column headings."] if changed else []


def drop_brf_pages(doc: fitz.Document) -> list[str]:
    """Removing BRF pages from the 401(k) package.

    Purpose:
        Removing BRF pages from the 401(k) package.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        drop_brf_pages(doc) returns list[str].

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    drop = [page.number for page in doc if _is_brf_report(page.get_text("text") or "")]
    for number in reversed(drop):
        doc.delete_page(number)
    if not drop:
        return []
    return [f"Removed {len(drop)} BRF report page(s). The Result Summary line is enough."]


_NUMBER_ONLY = re.compile(r"\d{1,3}")


def renumber_footers(doc: fitz.Document) -> list[str]:
    """Numbered packet pages keep their original numbers after pages are removed. Make them match the final page.

    Purpose:
        Numbered packet pages keep their original numbers after pages are removed. Make them match the final page.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        renumber_footers(doc) returns list[str].

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    footers: dict[int, list[fitz.Rect]] = {}
    strays: dict[int, list[fitz.Rect]] = {}
    for page in doc:
        if page.number == 0:
            continue
        for block in page.get_text("blocks"):
            if block[6] != 0 or not _NUMBER_ONLY.fullmatch((block[4] or "").strip()):
                continue
            target = footers if block[1] > page.rect.y1 - 70 else strays
            target.setdefault(page.number, []).append(fitz.Rect(block[:4]))
    if not footers:
        return []
    last = max(footers)
    changed = 0
    for number in range(1, last + 1):
        page = doc[number]
        old = footers.get(number, []) + strays.get(number, [])
        label = str(number + 1)
        if len(footers.get(number, [])) == 1 and not strays.get(number):
            if page.get_textbox(old[0]).strip() == label:
                continue
        for rect in old:
            page.add_redact_annot(rect + (-1, -1, 1, 1), fill=(1, 1, 1))
        if old:
            page.apply_redactions(images=0, graphics=0)
        width = fitz.get_text_length(label, fontname="helv", fontsize=9)
        page.insert_text(
            ((page.rect.width - width) / 2, page.rect.height - 36),
            label,
            fontsize=9,
            fontname="helv",
            color=(0, 0, 0),
        )
        changed += 1
    return [f"Renumbered {changed} page footer(s) to match the final page order."] if changed else []


def _page_has_full_width_rule(page: fitz.Page, y: float, *, tol: float = 4.0) -> bool:
    """True when a near-full-width horizontal rule already sits near y."""
    min_width = page.rect.width * 0.65
    for drawing in page.get_drawings():
        for item in drawing.get("items") or []:
            if not item or item[0] != "l" or len(item) < 3:
                continue
            start, end = fitz.Point(item[1]), fitz.Point(item[2])
            if abs(start.y - end.y) > 1.5:
                continue
            if abs(((start.y + end.y) / 2) - y) <= tol and abs(end.x - start.x) >= min_width:
                return True
    return False


def ensure_summary_heading_rule(doc: fitz.Document) -> list[str]:
    """Add the horizontal divider below a Result Summary / AV title block if it is absent."""
    changed = 0
    title_pattern = re.compile(
        r"^(?:compliance testing summary of results|compliance summary|result summary|test summary|"
        r"annual valuation report)$",
        re.I,
    )
    title_hint = re.compile(
        r"compliance testing summary of results|compliance summary|result summary|test summary|"
        r"annual valuation report",
        re.I,
    )
    for page in doc:
        page_text = page.get_text("text") or ""
        if not title_hint.search(page_text):
            continue
        text_lines = [
            (line, "".join(span.get("text", "") for span in line.get("spans", [])).strip())
            for block in page.get_text("dict").get("blocks", [])
            if block.get("type") == 0
            for line in block.get("lines", [])
        ]
        text_lines.sort(key=lambda item: (item[0]["bbox"][1], item[0]["bbox"][0]))
        title_index = next((i for i, (_line, value) in enumerate(text_lines) if title_pattern.fullmatch(value)), None)
        if title_index is None:
            continue
        title_top = float(text_lines[title_index][0]["bbox"][1])
        # Client expected packages place this divider at y≈109 under the top title block.
        if title_top > 120:
            continue
        y = 109.0
        if _page_has_full_width_rule(page, y):
            continue
        if y < page.rect.y1 - 40:
            page.draw_line(
                fitz.Point(36, y),
                fitz.Point(min(page.rect.width - 30, 582), y),
                color=(0, 0, 0),
                width=1,
            )
            changed += 1
    return [f"Added a divider below {changed} Result Summary heading block(s)."] if changed else []


def normalize_coverage_satisfy_heading(doc: fitz.Document) -> list[str]:
    """Join a wrapped 'Must Satisfy I or II' coverage heading back onto one line."""
    from services.pdf_modifier import _base_font, _rgb
    from services.source_rewrite import _tight_span_rect

    changed = 0
    head_re = re.compile(r"^(?P<head>Summary of Coverage Test Results\s*\(Must Satisfy)\s*$", re.I)
    tail_re = re.compile(r"^(?P<tail>I\s+or\s+II\)|or\s+II\))\s*$", re.I)
    for page in doc:
        page_text = page.get_text("text") or ""
        if "Must Satisfy" not in page_text:
            continue
        lines: list[dict] = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
                text = "".join(span.get("text", "") for span in spans).strip()
                if text:
                    lines.append({"line": line, "spans": spans, "text": text})
        lines.sort(key=lambda item: (item["line"]["bbox"][1], item["line"]["bbox"][0]))
        targets: list[tuple[dict, dict, str]] = []
        for index, item in enumerate(lines[:-1]):
            head = head_re.match(item["text"])
            if not head:
                continue
            nxt = lines[index + 1]
            tail = tail_re.match(nxt["text"])
            if not tail:
                continue
            # Same visual band / continuation column — not a later unrelated line.
            if abs(float(nxt["line"]["bbox"][1]) - float(item["line"]["bbox"][1])) > 14:
                continue
            tail_text = tail.group("tail")
            if tail_text.lower().startswith("or "):
                joined = "Summary of Coverage Test Results (Must Satisfy I or II)"
            else:
                joined = f"{head.group('head')} {tail_text}"
            targets.append((item, nxt, joined))
        if not targets:
            continue
        for item, nxt, _joined in targets:
            page.add_redact_annot(_tight_span_rect(item["spans"]), fill=(1, 1, 1))
            page.add_redact_annot(_tight_span_rect(nxt["spans"]), fill=(1, 1, 1))
        page.apply_redactions(images=0, graphics=0)
        for item, _nxt, joined in targets:
            span = item["spans"][0]
            origin = span.get("origin") or (span["bbox"][0], span["bbox"][3])
            page.insert_text(
                (float(origin[0]), float(origin[1])),
                joined,
                fontsize=float(span.get("size") or 10),
                fontname=_base_font(str(span.get("font") or ""), int(span.get("flags") or 0) | 16),
                color=_rgb(span.get("color") or 0),
                overlay=True,
            )
            changed += 1
    return [f"Joined {changed} Coverage Test 'Must Satisfy' heading(s)."] if changed else []


def package_checks(doc: fitz.Document, profile: PlanProfile) -> list[ValidationItem]:
    """Checking the package pages against the profile.

    Purpose:
        Checking the package pages against the profile.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.

    Returns:
        list[ValidationItem].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        package_checks(doc, profile) returns list[ValidationItem].

    Side effects:
        None. This function only reads data and returns a value.
    """
    items = [
        _cover_date_check(doc),
        _compliance_check(doc, profile),
        _brf_check(doc, profile),
        _assembly_order_check(doc, profile),
    ]
    items.extend(_result_summary_checks(doc, profile.plan_type))
    items.extend(_variance_checks(doc, profile))
    items.extend(_identity_checks(doc, profile))
    return items


def _assembly_order_check(doc: fitz.Document, profile: "PlanProfile") -> ValidationItem:
    """Check the physical report order against TEST23's substantive sections.

    Purpose:
        Check the physical report order against TEST23's substantive sections.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.

    Returns:
        ValidationItem.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _assembly_order_check(doc, profile) returns ValidationItem.

    Side effects:
        None. This function only reads data and returns a value.
    """
    from services.file_order import load_section_specs
    from services.pdf_assembler import page_section
    if package_flags(profile.plan_type).get("rewrite_adp_mentions"):
        names = [
            "Cover Letter", "Test Summary", "Compensation Limit Failure Summary",
            "Combined Testing Report", "Action Required", "Failed Test Notice",
            "Variance", "PS Variance", "SHNE Variance", "Year End Recap",
            "Compliance Reports", "Contribution Analysis", "HCE/Key", "Future HCE",
            "ADP/ACP", "402(g)", "410(b)", "401(a)(4)",
            "Average Benefit Percentage Test", "BRF", "414(s)", "415", "Top Heavy", "Census",
        ]
    else:
        names = [
            "Cover Letter", "Test Summary", "Compensation Limit Failure Summary",
            "Combined Testing Report", "Action Required", "Failed Test Notice",
            "Variance", "PS Variance", "SHNE Variance", "Year End Recap",
            "Compliance Reports", "Valuation Reports", "Contribution Analysis",
            "HCE/Key", "Future HCE", "ADP/ACP", "402(g)", "410(b)",
            "401(a)(4)", "Average Benefit Percentage Test", "414(s)", "415",
            "Top Heavy", "Census",
        ]
    order = {name: index for index, name in enumerate(names)}
    order["415 Failure Information"] = order["Failed Test Notice"]
    order["ADP/ACP Excess After 12 Months Current"] = order["Failed Test Notice"]
    order["ADP/ACP Excess After 12 Months Prior"] = order["Failed Test Notice"]
    order["ADP/ACP Excess Current Year"] = order["Failed Test Notice"]
    order["ADP/ACP Failure Letter"] = order["Failed Test Notice"]
    order["402(g) Failure Letter"] = order["Failed Test Notice"]
    order["415 Failure Letter"] = order["Failed Test Notice"]
    specs = load_section_specs()
    recognized: list[tuple[int, str, int]] = []
    for page_index, page in enumerate(doc):
        text = page.get_text("text") or ""
        if not text.strip() or is_compliance_overview(text):
            continue
        lines = [" ".join(line.split()).strip() for line in text.splitlines() if line.strip()][:6]
        head_lines = lines[:3]
        head = " ".join(head_lines)
        if any(_PAGE_SUMMARY_HEAD.fullmatch(line) for line in head_lines) or re.search(r"^compliance testing summary of results\b", " ".join(head_lines), re.I):
            recognized.append((page_index + 1, "Test Summary", order["Test Summary"]))
            continue
        if any(_TOP_HEAVY_HEAD.fullmatch(line) for line in head_lines):
            recognized.append((page_index + 1, "Top Heavy", order["Top Heavy"]))
            continue
        action_head = any(re.search(r"(?:immediate action required|no immediate action is required)", line, re.I) for line in head_lines)
        if action_head or (head_lines and re.fullmatch(r"annual valuation report", head_lines[0], re.I)):
            recognized.append((page_index + 1, "Action Required", order["Action Required"]))
            continue
        if any(re.search(r"combined testing report", line, re.I) for line in head_lines):
            recognized.append((page_index + 1, "Combined Testing Report", order["Combined Testing Report"]))
            continue
        source_section = page_section(page)
        if source_section in {"HCE/Key", "Future HCE"} and source_section in order:
            recognized.append((page_index + 1, source_section, order[source_section]))
            continue
        for spec in specs:
            name = str(spec.get("name") or "")
            if name not in order:
                continue
            if name == "BRF" and not package_flags(profile.plan_type).get("keep_brf"):
                continue
            aliases = [str(spec.get("name") or "")] + [str(alias) for alias in (spec.get("aliases") or [])]
            if any(
                alias
                and re.search(
                    rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])",
                    head,
                    re.I,
                )
                for alias in aliases
            ):
                recognized.append((page_index + 1, name, order[name]))
                break
    problems = [
        f"{before} appears on page {page_before} before {after} on page {page_after}"
        for (page_before, before, rank_before), (page_after, after, rank_after)
        in zip(recognized, recognized[1:])
        if rank_before > rank_after
    ]
    return ValidationItem(
        code="package_order",
        label="Package order (TEST23)",
        passed=not problems,
        detail="Report sections follow the TEST23 combine order."
        if not problems
        else "; ".join(problems[:6]),
    )


def _page_kind(text: str) -> tuple[str, int] | None:
    """Page kind.

    Purpose:
        Page kind.

    Args:
        text: Text taken from a page or a file.

    Returns:
        tuple[str, int] | None.

    Raises:
        None.

    Example:
        _page_kind("text") returns tuple[str, int] | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    head = _head(text)
    if not head or _KEEP_PAGE.search(head):
        return None
    abpt = _abpt_rank(head)
    if abpt is not None:
        return ("Average Benefit Percentage", abpt)
    if re.search(r"410\s*\(?b\)?", head, re.I):
        rank = _ranked(
            head,
            ((r"excludable", 1), (r"includable", 2), (r"\bdetail\b", 0), (r"\bsummary\b", 3)),
        )
        if rank is not None:
            return ("410(b)", rank)
    if re.search(r"\bADP\b|\bACP\b", head, re.I):
        rank = _ranked(
            head,
            ((r"correction", 3), (r"excluded", 2), (r"\bdetail\b", 1), (r"\bsummary\b", 0)),
        )
        if rank is None:
            wider = " ".join([line.strip() for line in text.splitlines() if line.strip()][:8])
            rank = _ranked(wider, ((r"test results", 0), (r"employee listing", 1)))
        if rank is not None:
            return ("ADP/ACP", rank)
    return None


def _abpt_rank(head: str) -> int | None:
    """Abpt rank.

    Purpose:
        Abpt rank.

    Args:
        head: Head. Type: str.

    Returns:
        a int | None.

    Raises:
        None.

    Example:
        _abpt_rank("text") returns a int | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    order = (
        (r"401\s*a\s*1|401a1", 1),
        (r"gateway", 2),
        (r"overall\s+comp", 3),
        (r"rate\s+group", 4),
        (r"sum\s+comp", 5),
        (r"average benefit percentage", 0),
    )
    return _ranked(head, order)


def _ranked(head: str, pairs: tuple[tuple[str, int], ...]) -> int | None:
    """Ranked.

    Purpose:
        Ranked.

    Args:
        head: Head. Type: str.
        pairs: Pairs. Type: tuple[tuple[str, int], ...].

    Returns:
        a int | None.

    Raises:
        None.

    Example:
        _ranked("text", "text") returns a int | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for pattern, rank in pairs:
        if re.search(pattern, head, re.I):
            return rank
    return None


def _head(text: str) -> str:
    """Head.

    Purpose:
        Head.

    Args:
        text: Text taken from a page or a file.

    Returns:
        str.

    Raises:
        None.

    Example:
        _head("text") returns str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return " ".join(lines[:4])


def _is_brf_report(text: str) -> bool:
    """Is brf report.

    Purpose:
        Is brf report.

    Args:
        text: Text taken from a page or a file.

    Returns:
        bool.

    Raises:
        None.

    Example:
        _is_brf_report("text") returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if _KEEP_PAGE.search(text):
        return False
    return bool(_BRF_REPORT.search(_head(text)))


def _redact_matching_lines(page: fitz.Page, keep_soc: bool = False) -> bool:
    """Redact matching lines.

    Purpose:
        Redact matching lines.

    Args:
        page: One PDF page.
        keep_soc: True leaves Statement of Contribution wording in the PDF.

    Returns:
        True or False.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _redact_matching_lines(page, True) returns True or False.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    pattern = _DISALLOWED_EXCEPT_SOC if keep_soc else _DISALLOWED_LINE
    boxes: list[fitz.Rect] = []
    for block in page.get_text("dict").get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            line_text = "".join(span.get("text") or "" for span in line.get("spans") or [])
            if pattern.search(line_text):
                boxes.append(fitz.Rect(line["bbox"]))
    if not boxes:
        return False
    for box in boxes:
        page.add_redact_annot(box, fill=(1, 1, 1))
    page.apply_redactions()
    return True


def _cover_date_check(doc: fitz.Document) -> ValidationItem:
    """Cover date check.

    Purpose:
        Cover date check.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        ValidationItem.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _cover_date_check(doc) returns ValidationItem.

    Side effects:
        None. This function only reads data and returns a value.
    """
    today = cover_date_text()
    if not doc.page_count:
        return ValidationItem(
            code="cover_date_today",
            label="Cover date is today",
            passed=False,
            detail="Cover page is missing.",
        )
    text = doc[0].get_text("text") or ""
    match = _LETTER_DATE.search(text)
    if not match:
        return ValidationItem(
            code="cover_date_today",
            label="Cover date is today",
            passed=False,
            detail=f"No cover letter date found. It should be {today}.",
        )
    found = f"{match.group(1).title()} {int(match.group(2))}, {match.group(3)}"
    if found.lower() == today.lower():
        return ValidationItem(
            code="cover_date_today",
            label="Cover date is today",
            passed=True,
            detail=found,
        )
    return ValidationItem(
        code="cover_date_today",
        label="Cover date is today",
        passed=False,
        detail=f"Cover date is {found}. It should be {today}.",
    )


def is_compliance_overview(text: str) -> bool:
    """One of the three Compliance and Administrative Reports overview pages.

    Purpose:
        One of the three Compliance and Administrative Reports overview pages.

    Args:
        text: Text taken from a page or a file.

    Returns:
        bool.

    Raises:
        None.

    Example:
        is_compliance_overview("text") returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return _overview_kind(text) is not None


def _overview_kind(text: str) -> str | None:
    """Overview kind.

    Purpose:
        Overview kind.

    Args:
        text: Text taken from a page or a file.

    Returns:
        str | None.

    Raises:
        None.

    Example:
        _overview_kind("text") returns str | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    blob = text or ""
    if re.search(r"compliance and administrative|overview and descriptions", blob, re.I):
        return "intro"
    if re.search(r"410\s*\(\s*b\s*\)\s+coverage", blob, re.I) and re.search(
        r"compensation testing\s*\(\s*414", blob, re.I
    ):
        return "tests"
    if re.search(r"administrative reports", blob, re.I) and re.search(
        r"hce/key employee determinations", blob, re.I
    ):
        return "admin"
    return None


def _compliance_check(doc: fitz.Document, profile: PlanProfile) -> ValidationItem:
    """Compliance check.

    Purpose:
        Compliance check.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.

    Returns:
        ValidationItem.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _compliance_check(doc, profile) returns ValidationItem.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if profile.midyear or is_457_plan(profile.plan_type):
        return ValidationItem(
            code="compliance_three_pages",
            label="Compliance reports (3 pages)",
            passed=True,
            detail="This package does not use the three compliance report pages.",
        )
    kinds = {_overview_kind(page.get_text("text") or "") for page in doc}
    kinds.discard(None)
    count = len(kinds)
    return ValidationItem(
        code="compliance_three_pages",
        label="Compliance reports (3 pages)",
        passed=count == 3,
        detail="3 Compliance and Administrative Report pages are in the package."
        if count == 3
        else f"Found {count} compliance report page(s). The package should include 3.",
    )


def _brf_check(doc: fitz.Document, profile: PlanProfile) -> ValidationItem:
    """Brf check.

    Purpose:
        Brf check.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.

    Returns:
        ValidationItem.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _brf_check(doc, profile) returns ValidationItem.

    Side effects:
        None. This function only reads data and returns a value.
    """
    left = [page.number + 1 for page in doc if _is_brf_report(page.get_text("text") or "")]
    if package_flags(profile.plan_type).get("keep_brf"):
        return ValidationItem(
            code="brf_report",
            label="BRF report",
            passed=True,
            detail="403(b) keeps the Benefits, Rights and Features test when that report is in the package."
            if left
            else "No BRF report was in this 403(b) package.",
        )
    return ValidationItem(
        code="brf_report_omitted",
        label="BRF report omitted",
        passed=not left,
        detail="No BRF report is in the package."
        if not left
        else "BRF report still present on page(s) " + ", ".join(str(page) for page in left),
    )


def _result_summary_checks(
    doc: fitz.Document,
    plan_type: str | None = None,
) -> list[ValidationItem]:
    """Result summary checks.

    Purpose:
        Result summary checks, including the 410(b) Coverage Test checkpoint.

    Args:
        doc: Open PDF. Must not be closed.
        plan_type: ``401k``, ``403b``, ``457``, or empty. 403(b) summaries must not
            show a 401(k) line under 410(b).

    Returns:
        list[ValidationItem].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _result_summary_checks(doc, "403b") returns list[ValidationItem].

    Side effects:
        None. This function only reads data and returns a value.
    """
    summary_parts: list[str] = []
    for page in doc:
        text = page.get_text("text") or ""
        if _SUMMARY.search(text):
            summary_parts.append(text)
    summary = "\n".join(summary_parts)
    if not summary.strip():
        return [
            ValidationItem(
                code="result_summary",
                label="Result Summary vs test reports",
                passed=False,
                detail="Result Summary was not found, so pass/fail and top heavy were not compared.",
            )
        ]
    items = [_top_heavy_check(doc, summary)]
    items.extend(_pass_fail_checks(doc, summary, plan_type))
    return items


def summary_test_record() -> list[dict]:
    """Input: none. Calls load_compliance_summary. Output: [{code, name, means}, ...] from compliance_summary.yaml.

    Purpose:
        Input: none. Calls load_compliance_summary. Output: [{code, name, means}, ...] from compliance_summary.yaml.

    Args:
        None.

    Returns:
        list[dict].

    Raises:
        yaml.YAMLError: A YAML file is not valid.

    Example:
        summary_test_record() returns list[dict].

    Side effects:
        None. This function only reads data and returns a value.
    """
    return load_compliance_summary()


def _means(code: str) -> str:
    """Means.

    Purpose:
        Means.

    Args:
        code: Code. Type: str.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _means("text") returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for row in summary_test_record():
        if row.get("code") == code:
            return " ".join(str(row.get("means") or "").split())
    return ""


def _top_heavy_check(doc: fitz.Document, summary: str) -> ValidationItem:
    """Top heavy check.

    Purpose:
        Top heavy check.

    Args:
        doc: Open PDF. Must not be closed.
        summary: Summary. Type: str.

    Returns:
        a ValidationItem.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _top_heavy_check(doc, "text") returns a ValidationItem.

    Side effects:
        None. This function only reads data and returns a value.
    """
    shown = re.search(r"top\s*heavy[\s\S]{0,80}?(\d+(?:\.\d+)?)\s*%", summary, re.I)
    if not shown:
        return ValidationItem(
            code="top_heavy_summary",
            label="Top heavy on Result Summary",
            passed=False,
            detail="Top heavy percent was not found on the Result Summary.",
        )
    token = shown.group(1)
    percent = float(token)
    problems: list[str] = []
    if percent == 0 and token != "0.00":
        problems.append(f"{token}% should be shown as 0.00%")
    expects_top_heavy = percent > 60
    says_not = bool(re.search(r"plan is not top heavy", summary, re.I))
    says_is = bool(re.search(r"plan is top heavy", summary, re.I)) and not says_not
    unresolved = re.search(r"plan\s+is\s*/\s*is\s+not\s+top\s+heavy", summary, re.I)
    required = "Plan is Top Heavy" if expects_top_heavy else "Plan is not Top Heavy"
    if unresolved:
        problems.append(f"Plan is/is not Top Heavy should be {required}")
    elif expects_top_heavy and not says_is:
        problems.append("percent is over 60%, so the line should say Plan is Top Heavy")
    elif not expects_top_heavy and not says_not:
        problems.append("percent is 60% or less, so the line should say Plan is not Top Heavy")
    report = _report_percent(doc, r"top\s*heavy")
    if report is not None and abs(report - percent) > 0.01:
        problems.append(f"Result Summary shows {percent:g}% and the Top Heavy report shows {report:g}%")
    detail = "; ".join(problems) if problems else f"Top heavy {token}% matches the report."
    meaning = _means("top_heavy")
    if meaning:
        detail = f"{detail} {meaning}"
    return ValidationItem(
        code="top_heavy_summary",
        label="Top heavy on Result Summary",
        passed=not problems,
        detail=detail,
    )


def _pass_fail_checks(
    doc: fitz.Document,
    summary: str,
    plan_type: str | None = None,
) -> list[ValidationItem]:
    """Pass fail checks.

    Purpose:
        Pass fail checks.

    Args:
        doc: Open PDF. Must not be closed.
        summary: Summary. Type: str.
        plan_type: Plan type for 410(b) Result Summary norms.

    Returns:
        a list of ValidationItem.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _pass_fail_checks(doc, "text") returns a list of ValidationItem.

    Side effects:
        None. This function only reads data and returns a value.
    """
    items: list[ValidationItem] = []
    # One page-text pass for all patterns (used to re-scan the whole PDF per test).
    report_texts = _non_summary_page_texts(doc)
    for label, pattern, code in _PASS_FAIL:
        summary_result = _result_near(summary, pattern)
        report_result = _report_result(doc, pattern, page_texts=report_texts)
        if summary_result is None and report_result is None:
            continue
        problems: list[str] = []
        if summary_result == "unresolved":
            problems.append(f"{label} still says Pass/Fail")
        elif summary_result and report_result and summary_result != report_result:
            problems.append(f"Result Summary says {summary_result}, the report says {report_result}")
        if not summary_result and report_result:
            problems.append(f"report says {report_result}, Result Summary has no matching line")
        meaning = _means(code)
        detail = "; ".join(problems) if problems else f"{label} agrees ({summary_result or report_result})."
        if meaning:
            detail = f"{detail} {meaning}"
        items.append(
            ValidationItem(
                code=f"summary_{label}",
                label=f"{label} on Result Summary",
                passed=not problems,
                detail=detail,
            )
        )
    coverage = _coverage_item(doc, summary, plan_type)
    if coverage is not None:
        items.append(coverage)
    brf = _brf_summary_item(summary)
    if brf is not None:
        items.append(brf)
    if not items:
        items.append(
            ValidationItem(
                code="result_summary",
                label="Result Summary vs test reports",
                passed=False,
                detail="Result Summary did not include pass/fail lines to compare.",
            )
        )
    return items


_410_LABELS = (
    ("standard", "Standard", "410b_standard", r"profit\s+sharing|\bshne\b|safe\s+harbor\s+nonelective"),
    ("401k", "401(k)", "410b_401k", r"\b(?:deferrals?|roth)\b"),
    ("401m", "401(m)", "410b_401m", r"safe\s+harbor\s+match|\bmatch\b"),
)


def _coverage_item(
    doc: fitz.Document,
    summary: str,
    plan_type: str | None = None,
) -> ValidationItem | None:
    """410(b) Coverage Test checkpoint on the Result Summary.

    Purpose:
        Compare Standard / 401(k) / 401(m) lines to the 410(b) report, require ABPT
        wording when 410(b) fails, and for 403(b) plans reject a 401(k) line under
        410(b) Coverage Test (assemble guide: Standard and 401(m) only).

    Args:
        doc: Open PDF. Must not be closed.
        summary: Result Summary text.
        plan_type: Plan type. ``403b`` applies the no-401(k)-under-410(b) rule.

    Returns:
        a ValidationItem | None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _coverage_item(doc, summary, "403b") returns a ValidationItem | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    from services.plan_config import is_403b_plan

    summary_lines = _410_lines(summary)
    report_lines = _410_report_lines(doc)
    report_text = _report_text(doc)
    plan_403b = is_403b_plan(plan_type)
    required = {
        key
        for key, _label, _code, pattern in _410_LABELS
        if key in report_lines or re.search(pattern, report_text, re.I)
    }
    # 403(b): 401(k) deferral/Roth line must not appear under 410(b) Coverage Test.
    if plan_403b:
        required.discard("401k")
    if not summary_lines and not required:
        return None
    problems: list[str] = []
    notes: list[str] = []
    if plan_403b and "401k" in summary_lines:
        problems.append(
            "401(k) result should not appear under 410(b) Coverage Test on a 403(b) Result Summary "
            "(use Standard for PS/SHNE and 401(m) for match when contributions exist)"
        )
    for key, label, code, _pattern in _410_LABELS:
        shown = summary_lines.get(key)
        report = report_lines.get(key)
        meaning = _means(code)
        if plan_403b and key == "401k":
            continue
        if shown is None:
            if key in required:
                problems.append(f"{label} is missing from the Result Summary. {meaning}")
            continue
        if shown["result"] == "unresolved":
            problems.append(f"{label} still says Pass/Fail. {meaning}")
            continue
        if report and shown["result"] != report["result"]:
            problems.append(f"{label} Result Summary says {shown['result']}, the 410(b) report says {report['result']}")
        if report and report["ratio"] is not None and shown["ratio"] is None:
            problems.append(f"{label} ratio is {report['ratio_text']}% on the 410(b) report and missing on the Result Summary")
        elif (
            shown["ratio"] is not None
            and report
            and report["ratio"] is not None
            and abs(shown["ratio"] - report["ratio"]) > 0.01
        ):
            problems.append(
                f"{label} ratio is {shown['ratio_text']}% on the Result Summary and {report['ratio_text']}% on the 410(b) report"
            )
        ratio = f" {shown['ratio_text']}%" if shown["ratio_text"] else ""
        notes.append(f"{label} {shown['result']}{ratio} ({meaning})")
    failed = [
        row
        for key, row in summary_lines.items()
        if row["result"] == "fail" and not (plan_403b and key == "401k")
    ]
    if failed:
        if not _ABPT_PASSED.search(summary):
            problems.append(
                '410(b) failed. The summary needs "Average Benefits Test Passed; no action needed for Failed 410(b) Coverage Test". '
                + _means("410b_failed")
            )
        abpt = _result_near(summary, r"average benefit")
        report_abpt = _report_result(doc, r"average benefit")
        if report_abpt == "fail":
            problems.append("the Average Benefit Test report says fail, so the summary cannot say no action is needed")
        elif abpt != "pass":
            problems.append("410(b) failed and the Average Benefit Test line should say Pass")
    detail = "; ".join(problems) if problems else "; ".join(notes)
    return ValidationItem(
        code="summary_410(b)",
        label="410(b) on Result Summary",
        passed=not problems,
        detail=detail or "410(b) coverage lines agree.",
    )


def _brf_summary_item(summary: str) -> ValidationItem | None:
    """Brf summary item.

    Purpose:
        Brf summary item.

    Args:
        summary: Summary. Type: str.

    Returns:
        a ValidationItem | None.

    Raises:
        None.

    Example:
        _brf_summary_item("text") returns a ValidationItem | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    match = _BRF_RESULT.search(summary)
    if not match:
        return None
    meaning = _means("brf")
    word = match.group(1)
    if re.search(r"pass\s*/\s*fail", word, re.I):
        return ValidationItem(
            code="summary_brf",
            label="BRF on Result Summary",
            passed=False,
            detail=f"BRF still says Pass/Fail. {meaning}".strip(),
        )
    return ValidationItem(
        code="summary_brf",
        label="BRF on Result Summary",
        passed=True,
        detail=f"BRF agrees ({word.lower()}). {meaning}".strip(),
    )


def _410_lines(text: str) -> dict[str, dict]:
    """410 lines.

    Purpose:
        410 lines.

    Args:
        text: Text taken from a page or a file.

    Returns:
        dict[str, dict].

    Raises:
        None.

    Example:
        _410_lines("text") returns dict[str, dict].

    Side effects:
        None. This function only reads data and returns a value.
    """
    found: dict[str, dict] = {}
    for match in _410_LINE.finditer(text):
        compact = re.sub(r"\s+", "", match.group(1)).lower()
        key = {"standard": "standard", "401(k)": "401k", "401(m)": "401m"}.get(compact)
        if key is None:
            continue
        tail = text[match.start(2) : match.start(2) + 12]
        result = "unresolved" if re.match(r"(?:pass\s*/\s*fail|fail\s*/\s*pass)", tail, re.I) else match.group(2).lower()
        found[key] = {"result": result, "ratio": float(match.group(3)) if match.group(3) else None, "ratio_text": match.group(3)}
    return found


def _410_report_lines(doc: fitz.Document) -> dict[str, dict]:
    """410 report lines.

    Purpose:
        410 report lines.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        dict[str, dict].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _410_report_lines(doc) returns dict[str, dict].

    Side effects:
        None. This function only reads data and returns a value.
    """
    found: dict[str, dict] = {}
    for page in doc:
        text = page.get_text("text") or ""
        if _SUMMARY.search(text) or not re.search(r"410\s*\(?\s*b\s*\)?", text, re.I):
            continue
        for key, row in _410_lines(text).items():
            found.setdefault(key, row)
    return found


def _report_text(doc: fitz.Document) -> str:
    """Report text.

    Purpose:
        Report text.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        str.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _report_text(doc) returns str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return "\n".join(
        text
        for page in doc
        for text in (page.get_text("text") or "",)
        if not _SUMMARY.search(text)
    )


def _non_summary_page_texts(doc: fitz.Document) -> list[str]:
    """Page texts excluding Result Summary / compliance overview pages."""
    texts: list[str] = []
    for page in doc:
        text = page.get_text("text") or ""
        if _SUMMARY.search(text) or is_compliance_overview(text):
            continue
        texts.append(text)
    return texts


def _report_result(
    doc: fitz.Document,
    pattern: str,
    *,
    page_texts: list[str] | None = None,
) -> str | None:
    """Report result.

    Purpose:
        Report result.

    Args:
        doc: Open PDF. Must not be closed.
        pattern: Pattern. Type: str.
        page_texts: Optional cached non-summary page texts.

    Returns:
        a str | None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _report_result(doc, "text") returns a str | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    texts = page_texts if page_texts is not None else _non_summary_page_texts(doc)
    for text in texts:
        result = _result_near(text, pattern)
        if result:
            return result
    return None


def _result_near(text: str, pattern: str) -> str | None:
    """Result near.

    Purpose:
        Result near.

    Args:
        text: Text from a page or a file.
        pattern: Pattern. Type: str.

    Returns:
        a str | None.

    Raises:
        None.

    Example:
        _result_near("text", "text") returns a str | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    match = re.search(r"(?:" + pattern + r").{0,80}?\b(Pass|Fail)\b", text, re.I | re.S)
    if not match:
        return None
    tail = text[match.start(1) : match.start(1) + 12]
    if re.match(r"(?:pass\s*/\s*fail|fail\s*/\s*pass)", tail, re.I):
        return "unresolved"
    return match.group(1).lower()


def _report_percent(doc: fitz.Document, label: str) -> float | None:
    """Report percent.

    Purpose:
        Report percent.

    Args:
        doc: Open PDF. Must not be closed.
        label: Label. Type: str.

    Returns:
        a float | None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _report_percent(doc, "text") returns a float | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for page in doc:
        text = page.get_text("text") or ""
        if _SUMMARY.search(text) or is_compliance_overview(text):
            continue
        match = re.search(label + r"[\s\S]{0,80}?(\d+(?:\.\d+)?)\s*%", text, re.I)
        if match:
            return float(match.group(1))
    return None


def _variance_checks(doc: fitz.Document, profile: PlanProfile) -> list[ValidationItem]:
    """Variance checks.

    Purpose:
        Variance checks.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.

    Returns:
        list[ValidationItem].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _variance_checks(doc, profile) returns list[ValidationItem].

    Side effects:
        None. This function only reads data and returns a value.
    """
    pages = [
        page
        for page in doc
        if _VARIANCE.search(page.get_text("text") or "") and not re.search(r"action required", page.get_text("text") or "", re.I)
    ]
    if not pages:
        return [
            ValidationItem(
                code="variance_client",
                label="Client variance report",
                passed=True,
                detail="No client variance report in this package.",
            )
        ]
    problems: list[str] = []
    for page in pages:
        text = page.get_text("text") or ""
        number = page.number + 1
        if _SSN.search(text):
            problems.append(f"page {number} has a Social Security number")
        if _bad_zero(text):
            problems.append(f"page {number} has a zero that is not 0.00")
        if _mixed_font(page):
            problems.append(f"page {number} uses more than one font size")
        if _cut_off(page):
            problems.append(f"page {number} has text at the page edge")
        names = [line.strip() for line in text.splitlines() if _NAME_LINE.match(line.strip())]
        ordered = sorted(names, key=str.lower)
        if len(names) >= 2 and names != ordered:
            problems.append(f"page {number} names are not alphabetical")
        for label, value in (
            ("plan number", profile.plan_number),
            ("plan name", profile.plan_name),
            ("plan year end", profile.plan_year_end),
        ):
            if value and value.lower() not in text.lower():
                problems.append(f"page {number} is missing the {label}")
    return [
        ValidationItem(
            code="variance_client",
            label="Client variance report",
            passed=not problems,
            detail="; ".join(problems) if problems else "Variance pages have plan identity, 0.00 zeroes, one font size, and alphabetical names.",
        )
    ]


def _bad_zero(text: str) -> bool:
    """Bad zero.

    Purpose:
        Bad zero.

    Args:
        text: Text taken from a page or a file.

    Returns:
        bool.

    Raises:
        None.

    Example:
        _bad_zero("text") returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for match in _BAD_ZERO.finditer(text):
        token = match.group(1)
        if token != "0.00":
            return True
    return False


def _mixed_font(page: fitz.Page) -> bool:
    """Mixed font.

    Purpose:
        Mixed font.

    Args:
        page: One PDF page.

    Returns:
        bool.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _mixed_font(page) returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    sizes: set[float] = set()
    for block in page.get_text("dict").get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            for span in line.get("spans") or []:
                size = round(float(span.get("size") or 0), 1)
                if size >= 8:
                    sizes.add(size)
    return len(sizes) > 1


def _cut_off(page: fitz.Page) -> bool:
    """Cut off.

    Purpose:
        Cut off.

    Args:
        page: One PDF page.

    Returns:
        bool.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _cut_off(page) returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    limit = page.rect.x1 - 4
    for block in page.get_text("dict").get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            for span in line.get("spans") or []:
                if float(span["bbox"][2]) >= limit and (span.get("text") or "").strip():
                    return True
    return False


def _plan_year_present(text: str, plan_year_end: str) -> bool:
    """Accept 12/31/2025 and the notice header 'December 31, 2025'.

    Purpose:
        Accept 12/31/2025 and the notice header 'December 31, 2025'.

    Args:
        text: Text from a page or a file.
        plan_year_end: Plan year end. Type: str.

    Returns:
        True or False.

    Raises:
        None.

    Example:
        _plan_year_present("text", "text") returns True or False.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if plan_year_end in text:
        return True
    match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", plan_year_end.strip())
    if not match:
        return False
    month = int(match.group(1))
    if not 1 <= month <= 12:
        return False
    written = f"{_MONTHS[month - 1]} {int(match.group(2))}, {match.group(3)}"
    return written.lower() in text.lower()


def _identity_checks(doc: fitz.Document, profile: PlanProfile) -> list[ValidationItem]:
    """Identity checks.

    Purpose:
        Identity checks.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.

    Returns:
        list[ValidationItem].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _identity_checks(doc, profile) returns list[ValidationItem].

    Side effects:
        None. This function only reads data and returns a value.
    """
    if not profile.plan_number and not profile.plan_name:
        return [
            ValidationItem(
                code="report_identity",
                label="Plan identity on reports",
                passed=False,
                detail="Plan number and plan name were not read, so each report could not be checked.",
            )
        ]
    missing: list[str] = []
    for page in doc:
        if page.number == 0:
            continue
        text = page.get_text("text") or ""
        if len(text.strip()) < 20:
            continue
        if re.search(r"sample/draft communication to participant", text, re.I):
            continue
        if is_compliance_overview(text):
            continue
        head = _head(text)
        is_excess = bool(_EXCESS.search(text))
        is_report = bool(
            re.search(
                r"contribution analysis|future hce|\bHCE\b|ADP|ACP|402|410|401|average benefit|414|415|top heavy|census|variance|test summary",
                head,
                re.I,
            )
        )
        if not is_excess and not is_report:
            continue
        gaps: list[str] = []
        if profile.plan_number and profile.plan_number not in text:
            gaps.append("plan number")
        if profile.plan_name and profile.plan_name.lower() not in text.lower():
            gaps.append("plan name")
        if is_excess and profile.plan_year_end and not _plan_year_present(text, profile.plan_year_end):
            gaps.append("plan year end")
        if gaps:
            missing.append(f"page {page.number + 1} missing " + ", ".join(gaps))
    return [
        ValidationItem(
            code="report_identity",
            label="Plan identity on reports",
            passed=not missing,
            detail="Plan number and plan name appear on each report."
            if not missing
            else "; ".join(missing[:8]),
        )
    ]

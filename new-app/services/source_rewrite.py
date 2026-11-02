"""Optional in-place rewrites. Off unless the reviewer checks the box.

Replacements use the original text position and size so the rest of the page stays put.
A shorter string leaves a small gap. A longer string can overlap the next word.
"""

from __future__ import annotations

import re
from datetime import datetime

import fitz

from models.plan_profile import PlanProfile
from services.change_marks import add_mark
from services.package_polish import cover_date_text, hce_max_percent
from services.pdf_modifier import _base_font, _rgb

_MONTH = (
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
)
_COVER_SLASH = re.compile(r"\b(\d{1,2})/0([1-9])/(20\d{2})\b")
_LETTER_DATE = re.compile(rf"({_MONTH})\s+(\d{{1,2}}),\s+(20\d{{2}})", re.I)
_PERCENT = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*%")
_NHCE = re.compile(r"NHCE[^%\n]{0,80}?(\d{1,2}(?:\.\d+)?)\s*%", re.I)
_RANGE_DATE = (
    r"(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},\s+\d{4})"
)
_DATE_RANGE_CONNECTOR = re.compile(
    rf"(?P<left>{_RANGE_DATE})\s*(?P<connector>to|and|from)\s*(?P<right>{_RANGE_DATE})",
    re.I,
)


def calendar_402g_year(plan_year_end: str | None) -> int | None:
    """Off-calendar 402(g) uses the calendar year before the plan year end. Calendar plans are unchanged.

    Purpose:
        Off-calendar 402(g) uses the calendar year before the plan year end. Calendar plans are unchanged.

    Args:
        plan_year_end: Plan year end. Type: str | None.

    Returns:
        a int | None.

    Raises:
        None.

    Example:
        calendar_402g_year("text") returns a int | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if not plan_year_end:
        return None
    match = re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})", plan_year_end)
    if not match:
        return None
    month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
    if month == 12 and day == 31:
        return None
    return year - 1


def _format_percent(value: float) -> str:
    """Format percent.

    Purpose:
        Format percent.

    Args:
        value: Value. Type: float.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _format_percent(1.0) returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if float(value).is_integer():
        return f"{int(value)}%"
    return f"{value:g}%"


def apply_cover_date(doc: fitz.Document, marks: list[dict] | None = None) -> list[str]:
    """Set the cover letter date to today. This runs on every Process.

    Purpose:
        Set the cover letter date to today. This runs on every Process.

    Args:
        doc: Open PDF. Must not be closed.
        marks: Highlight rectangles already collected for the PDF.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        apply_cover_date(doc, []) returns list[str].

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    if not doc.page_count:
        return []
    changed = _rewrite_cover_day(doc[0], marks)
    today = cover_date_text()
    if changed:
        return [f"Cover letter date set to {today} ({changed} place(s)). Check the letterhead spacing."]
    return [f"Cover letter date left as printed (already {today}, or no letter date was found)."]


_COVER_WRAP_TAIL = re.compile(
    r"^(?P<head>.+\bresults of) the$",
    re.I,
)
_COVER_WRAP_NEXT = re.compile(r"^IRS required testing for the plan year\.?\s*$", re.I)
_FROM_TO_LINE = re.compile(
    r"^(?P<from>From\s+\d{1,2}/\d{1,2}/\d{2,4})\s+(?P<to>To\s+\d{1,2}/\d{1,2}/\d{2,4})\s*$",
    re.I,
)


def normalize_cover_census_wrap(doc: fitz.Document) -> list[str]:
    """Break the cover census sentence after 'results of', matching MOA packages."""
    if not doc.page_count:
        return []
    page = doc[0]
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
    for index, item in enumerate(lines[:-1]):
        match = _COVER_WRAP_TAIL.match(item["text"])
        nxt = lines[index + 1]
        if not match or not _COVER_WRAP_NEXT.match(nxt["text"]):
            continue
        head = match.group("head")
        first_span = item["spans"][0]
        next_span = nxt["spans"][0]
        size = float(first_span.get("size") or 10)
        font = _base_font(str(first_span.get("font") or ""), int(first_span.get("flags") or 0))
        color = _rgb(first_span.get("color") or 0)
        first_origin = first_span.get("origin") or (first_span["bbox"][0], first_span["bbox"][3])
        next_origin = next_span.get("origin") or (next_span["bbox"][0], next_span["bbox"][3])
        page.add_redact_annot(fitz.Rect(item["line"]["bbox"]) + (-1, -1, 1, 1), fill=(1, 1, 1))
        page.add_redact_annot(fitz.Rect(nxt["line"]["bbox"]) + (-1, -1, 1, 1), fill=(1, 1, 1))
        page.apply_redactions(images=0, graphics=0)
        page.insert_text(
            (first_origin[0], first_origin[1]),
            head,
            fontsize=size,
            fontname=font,
            color=color,
            overlay=True,
        )
        page.insert_text(
            (next_origin[0], next_origin[1]),
            "the IRS required testing for the plan year.",
            fontsize=float(next_span.get("size") or size),
            fontname=_base_font(str(next_span.get("font") or ""), int(next_span.get("flags") or 0)),
            color=_rgb(next_span.get("color") or 0),
            overlay=True,
        )
        return ["Cover letter census sentence wrap aligned after 'results of'."]
    return []


def normalize_from_to_columns(doc: fitz.Document) -> list[str]:
    """Split merged 'From DATE To DATE' headers into the MOA two-column layout."""
    changed = 0
    for page in doc:
        targets: list[tuple[dict, list[dict], str, str]] = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
                if not spans:
                    continue
                text = "".join(span.get("text", "") for span in spans).strip()
                match = _FROM_TO_LINE.match(text)
                if not match:
                    continue
                from_x = float(spans[0]["bbox"][0])
                to_span = next(
                    (span for span in spans if str(span.get("text", "")).strip().lower().startswith("to ")),
                    None,
                )
                if (
                    to_span is not None
                    and abs(from_x - 326) <= 2
                    and abs(float(to_span["bbox"][0]) - 406) <= 2
                ):
                    continue
                if abs(from_x - 326) > 12:
                    continue
                targets.append((line, spans, match.group("from"), match.group("to")))
        if not targets:
            continue
        for line, _spans, _from_text, _to_text in targets:
            page.add_redact_annot(fitz.Rect(line["bbox"]) + (-1, -1, 1, 1), fill=(1, 1, 1))
        page.apply_redactions(images=0, graphics=0)
        for line, spans, from_text, to_text in targets:
            span = spans[0]
            origin = span.get("origin") or (span["bbox"][0], span["bbox"][3])
            size = float(span.get("size") or 9)
            font = "hebo"
            color = _rgb(span.get("color") or 0)
            baseline = float(origin[1])
            page.insert_text((326, baseline), from_text, fontsize=size, fontname=font, color=color, overlay=True)
            page.insert_text((406, baseline), to_text, fontsize=size, fontname=font, color=color, overlay=True)
            changed += 1
    return [f"Split {changed} From/To date header(s) into columns."] if changed else []


def normalize_cover_address_spacing(doc: fitz.Document) -> list[str]:
    """Compact oversized vertical gaps between the cover date and the RE line."""
    if not doc.page_count:
        return []
    page = doc[0]
    blocks = page.get_text("dict").get("blocks", [])
    lines: list[dict] = []
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
            text = "".join(span.get("text", "") for span in spans).strip()
            if text:
                lines.append({"line": line, "spans": spans, "text": text})
    lines.sort(key=lambda item: (item["line"]["bbox"][1], item["line"]["bbox"][0]))
    date_index = next(
        (index for index, item in enumerate(lines) if _LETTER_DATE.search(item["text"])),
        None,
    )
    if date_index is None:
        return []
    re_index = next(
        (index for index in range(date_index + 1, len(lines)) if re.match(r"^RE:\s*", lines[index]["text"], re.I)),
        None,
    )
    if re_index is None:
        return []

    address_lines = lines[date_index + 1 : re_index]
    if len(address_lines) < 2:
        return []
    first_baseline = min(float(span.get("origin", (0, span["bbox"][3]))[1]) for span in address_lines[0]["spans"])
    destination_baselines: list[float] = [first_baseline]
    for index, item in enumerate(address_lines[1:], start=1):
        previous = address_lines[index - 1]
        previous_size = max(float(span.get("size") or 10) for span in previous["spans"])
        line_size = max(float(span.get("size") or 10) for span in item["spans"])
        step = max(previous_size, line_size) * 1.35
        original_baseline = min(float(span.get("origin", (0, span["bbox"][3]))[1]) for span in item["spans"])
        destination_baselines.append(min(original_baseline, destination_baselines[-1] + step))

    moved = [
        (item, destination - min(float(span.get("origin", (0, span["bbox"][3]))[1]) for span in item["spans"]))
        for item, destination in zip(address_lines, destination_baselines)
    ]
    moved = [(item, delta) for item, delta in moved if delta < -1.0]
    if not moved:
        return []

    for item, _delta in moved:
        page.add_redact_annot(fitz.Rect(item["line"]["bbox"]) + (-1, -1, 1, 1), fill=(1, 1, 1))
    page.apply_redactions(images=0, graphics=0)
    for item, delta in moved:
        for span in item["spans"]:
            origin = span.get("origin") or (span["bbox"][0], span["bbox"][3])
            page.insert_text(
                (origin[0], origin[1] + delta),
                span["text"],
                fontsize=float(span.get("size") or 10),
                fontname=_base_font(str(span.get("font") or ""), int(span.get("flags") or 0)),
                color=_rgb(span.get("color") or 0),
                overlay=True,
            )
    return [f"Compacted spacing between {len(moved)} cover-address line(s)."]


def normalize_date_range_spacing(doc: fitz.Document) -> list[str]:
    """Ensure date range connectors have spaces while retaining source text spans and alignment."""
    changed = 0
    for page in doc:
        lines: list[tuple[dict, list[dict], str, list[int]]] = []
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
                full_spans = [span for span in line.get("spans", []) if span.get("text", "")]
                text = "".join(span.get("text", "") for span in full_spans)
                if spans and _DATE_RANGE_CONNECTOR.search(text):
                    lines.append((line, full_spans, text, spans))
        changed_lines: list[tuple[dict, list[dict], list[str]]] = []
        for line, spans, original, _nonempty_spans in lines:
            insertions: list[int] = []
            for match in _DATE_RANGE_CONNECTOR.finditer(original):
                connector_start = match.start("connector")
                connector_end = match.end("connector")
                if connector_start and not original[connector_start - 1].isspace():
                    if not _date_span_boundary_has_visual_gap(spans, connector_start):
                        insertions.append(connector_start)
                if connector_end < len(original) and not original[connector_end].isspace():
                    if not _date_span_boundary_has_visual_gap(spans, connector_end):
                        insertions.append(connector_end)
            if not insertions:
                continue
            offsets: list[int] = []
            cursor = 0
            updated_spans = [str(span.get("text", "")) for span in spans]
            for span_text in updated_spans:
                offsets.append(cursor)
                cursor += len(span_text)
            local_insertions: dict[int, list[int]] = {}
            for position in insertions:
                preceding = [i for i, start in enumerate(offsets) if start < position]
                span_index = preceding[-1] if preceding else 0
                local_insertions.setdefault(span_index, []).append(position - offsets[span_index])
            for span_index, positions in local_insertions.items():
                span_text = updated_spans[span_index]
                for position in sorted(positions, reverse=True):
                    span_text = span_text[:position] + " " + span_text[position:]
                updated_spans[span_index] = span_text
            changed_lines.append((line, spans, updated_spans))
        if not changed_lines:
            continue
        for line, _spans, _texts in changed_lines:
            page.add_redact_annot(fitz.Rect(line["bbox"]) + (-1, -1, 1, 1), fill=(1, 1, 1))
        page.apply_redactions(images=0, graphics=0)
        for _line, spans, updated_spans in changed_lines:
            for span, updated in zip(spans, updated_spans):
                origin = span.get("origin") or (span["bbox"][0], span["bbox"][3])
                fontsize = float(span.get("size") or 10)
                fontname = _base_font(str(span.get("font") or ""), int(span.get("flags") or 0))
                try:
                    page.insert_text(
                        (origin[0], origin[1]), updated,
                        fontsize=fontsize, fontname=fontname,
                        color=_rgb(span.get("color") or 0),
                    )
                except Exception:
                    page.insert_text(
                        (origin[0], origin[1]), updated,
                        fontsize=fontsize, fontname="helv",
                        color=_rgb(span.get("color") or 0),
                    )
            changed += 1
    return [f"Normalized spacing in {changed} date range(s)."] if changed else []


def _date_span_boundary_has_visual_gap(spans: list[dict], position: int) -> bool:
    """Treat a source-position gap between PDF spans as whitespace when it is visibly wide enough."""
    offset = 0
    previous: dict | None = None
    for span in spans:
        text = str(span.get("text") or "")
        end = offset + len(text)
        if end == position and previous is None:
            previous = span
            offset = end
            continue
        if offset == position and previous is not None:
            previous_box = fitz.Rect(previous["bbox"])
            current_box = fitz.Rect(span["bbox"])
            gap = current_box.x0 - previous_box.x1
            size = max(float(previous.get("size") or 10), float(span.get("size") or 10))
            return gap >= max(1.0, size * 0.18)
        previous = span
        offset = end
    return False


def apply_402g_dates(
    doc: fitz.Document,
    profile: PlanProfile,
    marks: list[dict] | None = None,
) -> list[str]:
    """Off-calendar 402(g) uses the calendar year before the plan year end.

    Purpose:
        Off-calendar 402(g) uses the calendar year before the plan year end. A plan year ending 06/30/2026 uses 01/01/2025-12/31/2025 on the 402(g) report.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.
        marks: Highlight rectangles already collected for the PDF.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        apply_402g_dates(doc, profile, []) returns list[str].

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    return _rewrite_402g_dates(doc, profile, marks)


def apply_source_rewrites(
    doc: fitz.Document,
    profile: PlanProfile,
    marks: list[dict] | None = None,
) -> list[str]:
    """Rewriting dates and other source text.

    Purpose:
        Rewriting dates and other source text.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.
        marks: Highlight rectangles already collected for the PDF.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        apply_source_rewrites(doc, profile, []) returns list[str].

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    notes: list[str] = []
    if doc.page_count:
        changed = _rewrite_cover_day(doc[0], marks)
        today = cover_date_text()
        if changed:
            notes.append(f"Cover letter date set to {today} ({changed} place(s)). Check the letterhead spacing.")
        else:
            notes.append(f"Cover letter date left as printed (already {today}, or no letter date was found).")
    notes.extend(_rewrite_402g_dates(doc, profile, marks))
    notes.extend(_rewrite_hce_percent(doc, profile, marks))
    return notes


def _rewrite_cover_day(page: fitz.Page, marks: list[dict] | None = None, when: datetime | None = None) -> int:
    """Rewrite cover day.

    Purpose:
        Rewrite cover day.

    Args:
        page: One PDF page.
        marks: Highlight rectangles already collected.
        when: When. Type: datetime | None.

    Returns:
        a int.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _rewrite_cover_day(page, marks, when) returns a int.

    Side effects:
        None. This function only reads data and returns a value.
    """
    today = cover_date_text(when)

    def transform(text: str) -> str | None:
        """Transform.

        Purpose:
            Transform.

        Args:
            text: Text taken from a page or a file.

        Returns:
            str | None.

        Raises:
            None.

        Example:
            transform("text") returns str | None.

        Side effects:
            None. This function only reads data and returns a value.
        """
        updated = text

        def _to_today(match: re.Match[str]) -> str:
            """To today.

            Purpose:
                To today.

            Args:
                match: Match. Type: re.Match[str].

            Returns:
                a str.

            Raises:
                None.

            Example:
                _to_today("text") returns a str.

            Side effects:
                None. This function only reads data and returns a value.
            """
            found = f"{match.group(1)} {int(match.group(2))}, {match.group(3)}"
            if found.lower() == today.lower() and match.group(0).lower() == today.lower():
                return match.group(0)
            return today

        updated = _LETTER_DATE.sub(_to_today, updated)
        updated = _COVER_SLASH.sub(r"\1/\2/\3", updated)
        return updated if updated != text else None

    return _replace_spans(page, transform, marks, "Cover date")


def _rewrite_402g_dates(
    doc: fitz.Document,
    profile: PlanProfile,
    marks: list[dict] | None = None,
) -> list[str]:
    """Rewrite 402g dates.

    Purpose:
        Rewrite 402g dates.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.
        marks: Highlight rectangles already collected for the PDF.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _rewrite_402g_dates(doc, profile, []) returns list[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
    year = calendar_402g_year(profile.plan_year_end)
    if year is None:
        return ["402(g) dates left as printed (calendar plan, or plan year end was not read)."]
    start = f"01/01/{year}"
    end = f"12/31/{year}"
    targets = [item for item in (profile.plan_year_start, profile.plan_year_end) if item]
    changed = 0
    for page in doc:
        text = page.get_text("text") or ""
        if "402" not in text:
            continue

        def transform(value: str, targets: list[str] = targets) -> str | None:
            """Transform.

            Purpose:
                Transform.

            Args:
                value: Value. Type: str.
                targets: Targets. Type: list[str].

            Returns:
                a str | None.

            Raises:
                None.

            Example:
                transform("text", []) returns a str | None.

            Side effects:
                None. This function only reads data and returns a value.
            """
            updated = value
            for old in targets:
                if old and old in updated:
                    updated = updated.replace(old, start if old == profile.plan_year_start else end)
            return updated if updated != value else None

        changed += _replace_spans(page, transform, marks, "402(g) date")
    if changed:
        return [
            f"402(g) dates rewritten to {start}–{end} ({changed} place(s)). Check that line for overlap."
        ]
    return [f"402(g) calendar dates would be {start}–{end}, but those plan-year dates were not found on a 402(g) page."]


def _rewrite_hce_percent(
    doc: fitz.Document,
    profile: PlanProfile,
    marks: list[dict] | None = None,
) -> list[str]:
    """Rewrite hce percent.

    Purpose:
        Rewrite hce percent.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.
        marks: Highlight rectangles already collected for the PDF.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _rewrite_hce_percent(doc, profile, []) returns list[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
    if (profile.testing_method or "").upper() != "PRIOR":
        return ["HCE percentage left as printed (testing method is not PRIOR)."]
    nhce = _first_nhce_percent(doc)
    if nhce is None:
        return ["HCE percentage not calculated: no NHCE % found on the package."]
    limit = hce_max_percent(nhce)
    label = _format_percent(limit)
    changed = 0
    for page in doc:
        text = page.get_text("text") or ""
        if "HCE" not in text.upper():
            continue

        def transform(value: str, label: str = label) -> str | None:
            """Transform.

            Purpose:
                Transform.

            Args:
                value: Value. Type: str.
                label: Label. Type: str.

            Returns:
                a str | None.

            Raises:
                None.

            Example:
                transform("text", "text") returns a str | None.

            Side effects:
                None. This function only reads data and returns a value.
            """
            if "NHCE" in value.upper() or "HCE" not in value.upper():
                return None
            if not _PERCENT.search(value):
                return None
            updated = _PERCENT.sub(label, value, count=1)
            return updated if updated != value else None

        changed += _replace_spans(page, transform, marks, "HCE %")
    if changed:
        return [
            f"Prior-year HCE maximum set to {label} from NHCE {nhce:g}% ({changed} place(s)). Check that line for overlap."
        ]
    return [
        f"Prior-year HCE maximum is {label} from NHCE {nhce:g}%, but no HCE % on the page was replaced."
    ]


def _first_nhce_percent(doc: fitz.Document) -> float | None:
    """First nhce percent.

    Purpose:
        First nhce percent.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        float | None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _first_nhce_percent(doc) returns float | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for page in doc:
        match = _NHCE.search(page.get_text("text") or "")
        if match:
            return float(match.group(1))
    return None


def _replace_spans(page: fitz.Page, transform, marks: list[dict] | None = None, label: str = "Updated") -> int:
    """Replace spans.

    Purpose:
        Replace spans.

    Args:
        page: One PDF page.
        transform: Transform. Type: unspecified.
        marks: Highlight rectangles already collected.
        label: Label. Type: str.

    Returns:
        a int.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _replace_spans(page, transform, marks) returns a int.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    found: list[tuple[dict, str]] = []
    for raw in page.get_text("dict").get("blocks") or []:
        if raw.get("type") != 0:
            continue
        for line in raw.get("lines") or []:
            for span in line.get("spans") or []:
                text = span.get("text") or ""
                updated = transform(text)
                if updated:
                    found.append((span, updated))
    if not found:
        return 0
    for span, _updated in found:
        page.add_redact_annot(fitz.Rect(span["bbox"]), fill=(1, 1, 1))
    page.apply_redactions()
    for span, updated in found:
        origin = span.get("origin") or (span["bbox"][0], span["bbox"][3])
        point = fitz.Point(origin[0], origin[1])
        size = float(span.get("size") or 11)
        fontname = _base_font(str(span.get("font") or ""), int(span.get("flags") or 0))
        try:
            page.insert_text(point, updated, fontsize=size, fontname=fontname, color=_rgb(span.get("color") or 0))
        except Exception:
            fontname = "helv"
            page.insert_text(point, updated, fontsize=size, fontname=fontname, color=_rgb(span.get("color") or 0))
        add_mark(marks, page.number, _written_rect(span, updated, fontname, size), label)
    return len(found)


def _written_rect(span: dict, updated: str, fontname: str, size: float) -> fitz.Rect:
    """Written rect.

    Purpose:
        Written rect.

    Args:
        span: Span. Type: dict.
        updated: Updated. Type: str.
        fontname: Fontname. Type: str.
        size: Size. Type: float.

    Returns:
        a fitz.Rect.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _written_rect({}, "text", "text") returns a fitz.Rect.

    Side effects:
        None. This function only reads data and returns a value.
    """
    origin = span.get("origin") or (span["bbox"][0], span["bbox"][3])
    try:
        width = float(fitz.get_text_length(updated, fontname=fontname, fontsize=size))
    except Exception:
        width = float(fitz.get_text_length(updated, fontname="helv", fontsize=size))
    if width < 4:
        return fitz.Rect(span["bbox"])
    x0 = float(origin[0])
    baseline = float(origin[1])
    return fitz.Rect(x0 - 0.6, baseline - size, x0 + width + 0.6, baseline + size * 0.3)

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


def calendar_402g_year(plan_year_end: str | None) -> int | None:
    """Off-calendar 402(g) uses the calendar year before the plan year end. Calendar plans are unchanged."""
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
    if float(value).is_integer():
        return f"{int(value)}%"
    return f"{value:g}%"


def apply_cover_date(doc: fitz.Document, marks: list[dict] | None = None) -> list[str]:
    """Set the cover letter date to today. This runs on every Process."""
    if not doc.page_count:
        return []
    changed = _rewrite_cover_day(doc[0], marks)
    today = cover_date_text()
    if changed:
        return [f"Cover letter date set to {today} ({changed} place(s)). Check the letterhead spacing."]
    return [f"Cover letter date left as printed (already {today}, or no letter date was found)."]


def apply_402g_dates(
    doc: fitz.Document,
    profile: PlanProfile,
    marks: list[dict] | None = None,
) -> list[str]:
    """Off-calendar 402(g) uses the calendar year before the plan year end.

    A plan year ending 06/30/2026 uses 01/01/2025-12/31/2025 on the 402(g) report.
    """
    return _rewrite_402g_dates(doc, profile, marks)


def apply_source_rewrites(
    doc: fitz.Document,
    profile: PlanProfile,
    marks: list[dict] | None = None,
) -> list[str]:
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
    today = cover_date_text(when)

    def transform(text: str) -> str | None:
        updated = text

        def _to_today(match: re.Match[str]) -> str:
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
    for page in doc:
        match = _NHCE.search(page.get_text("text") or "")
        if match:
            return float(match.group(1))
    return None


def _replace_spans(page: fitz.Page, transform, marks: list[dict] | None = None, label: str = "Updated") -> int:
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

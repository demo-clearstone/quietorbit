"""Drop finished packages and duplicate pages before merge — plan-agnostic."""

from __future__ import annotations

import re
from pathlib import Path

import fitz

from services import file_order

# Assembled OPS output: 800643_2025-Valuation.pdf (not "Valuation Pkg").
_FINISHED_NAME = re.compile(
    r"(?i)(?:^|[/\\])(?:.*[_ -])?\d{4}-valuation\.pdf$|(?:^|[/\\])[^/\\]*valuation\.pdf$"
)
_PKG_NAME = re.compile(r"(?i)valuation\s*(?:pkg|package)")
_COVER_MARKERS = re.compile(
    r"we are pleased to provide|dear plan sponsor|\bRE\s*:",
    re.I,
)
_SUMMARY_MARKERS = re.compile(
    r"compliance testing summary of results|result summary|test summary",
    re.I,
)
_RECAP_MARKERS = re.compile(r"year[- ]end recap|important information", re.I)
_ACTION_MARKERS = re.compile(
    r"annual valuation report|no immediate action|immediate action required|action required",
    re.I,
)
_REPORT_MARKERS = re.compile(
    r"contribution analysis|nondiscrimination test|employee census|402\s*\(\s*g\s*\)|"
    r"410\s*\(\s*b\s*\)|determination of highly compensated",
    re.I,
)

# Sections that should appear once in a package (first kept after SOP order).
# Compliance Reports is multi-page (overview + 410(b) + admin) — fingerprint only.
_SINGLETON_LABELS = {
    "cover letter",
    "test summary",
    "year end recap",
}


def is_finished_valuation_filename(filename: str) -> bool:
    """True for assembled ``NNNN_YYYY-Valuation.pdf`` outputs, not Valuation Pkg sources."""
    base = Path(filename or "").name
    if _PKG_NAME.search(base):
        return False
    # Split pages from a finished package still carry the parent stem.
    stem = re.sub(r"_p0*\d+(?=\.[^.]+$)", "", base, flags=re.I)
    return bool(_FINISHED_NAME.search(stem))


def looks_like_assembled_package(data: bytes, *, filename: str = "") -> bool:
    """Heuristic: multi-section finished package (cover + summary + recap + reports)."""
    if filename and is_finished_valuation_filename(filename):
        return True
    if filename and _PKG_NAME.search(Path(filename).name):
        return False
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return False
    try:
        if doc.page_count < 8:
            return False
        texts = [(page.get_text("text") or "") for page in doc]
        joined = "\n".join(texts)
        has_cover = any(_COVER_MARKERS.search(t) and not _ACTION_MARKERS.search(t[:200]) for t in texts[:3])
        has_summary = bool(_SUMMARY_MARKERS.search(joined))
        has_recap = bool(_RECAP_MARKERS.search(joined))
        has_action = bool(_ACTION_MARKERS.search(joined))
        report_hits = sum(1 for t in texts if _REPORT_MARKERS.search(t))
        # Valuation Pkg usually lacks a Result Summary page; finished packages include it.
        return bool(has_cover and has_summary and has_recap and has_action and report_hits >= 3)
    finally:
        doc.close()


def has_source_components(uploads: list[tuple[str, bytes]]) -> bool:
    """True when Valuation Pkg and/or discrete report sidecars are present."""
    pkg = False
    sidecar_sections: set[str] = set()
    for name, data in uploads:
        base = Path(name).name
        if _PKG_NAME.search(base):
            pkg = True
            continue
        if is_finished_valuation_filename(base) or looks_like_assembled_package(data, filename=base):
            continue
        if not base.lower().endswith(".pdf"):
            continue
        spec = file_order.matched_spec(base)
        if spec and spec.get("name") and spec.get("name") != "Cover Letter":
            sidecar_sections.add(str(spec["name"]))
    return pkg or len(sidecar_sections) >= 2


def exclude_finished_packages(
    uploads: list[tuple[str, bytes]],
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """When sources are present, drop finished ``*-Valuation.pdf`` packages.

    Purpose:
        Prevent doubling the package when a prior OPS output is uploaded with
        the Valuation Pkg and report sidecars. Works for any plan number/year.
    """
    if not has_source_components(uploads):
        return list(uploads), []
    kept: list[tuple[str, bytes]] = []
    notes: list[str] = []
    for name, data in uploads:
        if looks_like_assembled_package(data, filename=name):
            notes.append(
                f"Skipped finished valuation package while sources are present: {Path(name).name}"
            )
            continue
        kept.append((name, data))
    if not kept:
        # Safety: never wipe the whole job if heuristics misfire.
        return list(uploads), ["Finished-package filter kept all files (nothing left after filter)."]
    return kept, notes


def _page_text(data: bytes) -> str:
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        if doc.page_count < 1:
            return ""
        return doc[0].get_text("text") or ""
    finally:
        doc.close()


def page_fingerprint(text: str) -> str:
    """Normalized content fingerprint for near-duplicate page detection."""
    lines = [
        re.sub(r"\s+", " ", line).strip().lower()
        for line in (text or "").splitlines()
        if line.strip()
    ]
    # Drop volatile letter dates so the same cover body still matches.
    cleaned: list[str] = []
    for line in lines:
        if re.fullmatch(
            r"(?:january|february|march|april|may|june|july|august|september|"
            r"october|november|december)\s+\d{1,2},\s+\d{4}",
            line,
            re.I,
        ):
            continue
        cleaned.append(line)
    body = " | ".join(cleaned[:12])
    return re.sub(r"\d{1,2}/\d{1,2}/\d{2,4}", "DATE", body)[:600]


def _singleton_key(label: str, text: str) -> str | None:
    label_l = (label or "").strip().lower()
    for key in _SINGLETON_LABELS:
        if key in label_l:
            return key
    first = next((ln.strip() for ln in (text or "").splitlines() if ln.strip()), "")
    guessed = file_order.page_label_from_text(text, first).strip().lower()
    for key in _SINGLETON_LABELS:
        if key in guessed:
            return key
    return None


def _source_preference(filename: str) -> int:
    """Lower is better: Valuation Pkg slices beat finished leftovers / unknown."""
    base = Path(filename).name.lower()
    if _PKG_NAME.search(base):
        return 0
    if is_finished_valuation_filename(base):
        return 2
    return 1


def dedupe_ordered_pages(
    uploads: list[tuple[str, bytes]],
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """After SOP order, drop duplicate pages by content and singleton section.

    Keeps the first occurrence in combine order, preferring Valuation Pkg when
    two candidates collide before that position is sealed.
    """
    if len(uploads) < 2:
        return list(uploads), []

    enriched: list[tuple[str, bytes, str, str, str | None, int]] = []
    for name, data in uploads:
        text = _page_text(data)
        label = file_order.page_label_from_text(
            text,
            file_order.display_label(name),
        )
        enriched.append(
            (
                name,
                data,
                page_fingerprint(text),
                label,
                _singleton_key(label, text),
                _source_preference(name),
            )
        )

    # Prefer better sources when the same fingerprint / singleton appears.
    best_fp: dict[str, int] = {}
    best_single: dict[str, int] = {}
    for index, (_n, _d, fp, _label, single, pref) in enumerate(enriched):
        if fp and (fp not in best_fp or pref < enriched[best_fp[fp]][5]):
            best_fp[fp] = index
        if single and (single not in best_single or pref < enriched[best_single[single]][5]):
            best_single[single] = index

    kept: list[tuple[str, bytes]] = []
    notes: list[str] = []
    seen_fp: set[str] = set()
    seen_single: set[str] = set()
    for index, (name, data, fp, label, single, _pref) in enumerate(enriched):
        if fp and best_fp.get(fp) not in (None, index):
            notes.append(f"Skipped duplicate page (better source kept): {Path(name).name}")
            continue
        if fp and fp in seen_fp:
            notes.append(f"Skipped duplicate page: {Path(name).name}")
            continue
        if single and best_single.get(single) not in (None, index):
            notes.append(
                f"Skipped duplicate {single} page (better source kept): {Path(name).name}"
            )
            continue
        if single and single in seen_single:
            notes.append(f"Skipped duplicate {single} page: {Path(name).name}")
            continue
        if fp:
            seen_fp.add(fp)
        if single:
            seen_single.add(single)
        kept.append((name, data))
    return kept, notes

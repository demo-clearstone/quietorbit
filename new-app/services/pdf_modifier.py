from __future__ import annotations

import re

import fitz

from models.plan_profile import PlanProfile
from models.review import RuleDecision
from services.change_marks import add_mark
from services.package_polish import hce_max_percent
from services.plan_config import package_flags, paragraphs_for

_TITLE_ONLY = re.compile(
    r"^sample/draft(?: communication to participant)?\s*$",
    re.I,
)
_REPORT_TITLE = re.compile(r"(?m)^\s*annual valuation report\s*$", re.I)


def apply_decisions(
    doc: fitz.Document,
    decisions: list[RuleDecision],
    plan_type: str | None = None,
) -> list[str]:
    """Remove Action Required blocks, pack leftover text, and drop empty pages.

    Purpose:
        Remove Action Required blocks, pack leftover text, and drop empty pages.

    Args:
        doc: Open PDF. Must not be closed.
        decisions: Keep, remove, or skipped results from the rules.
        plan_type: Plan type: "401k", "403b", "457", or empty.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        apply_decisions(doc, [], "text") returns list[str].

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    specs = _block_specs(plan_type)
    remove_ids = {item.rule_id for item in decisions if item.action == "remove"}
    keep_ids = {item.rule_id for item in decisions if item.action == "keep"}
    headings = [str(spec["heading"]) for spec in specs if spec.get("heading")]
    remove_specs = [
        spec
        for spec in specs
        if str(spec.get("id") or "") in remove_ids and str(spec.get("heading") or "")
    ]
    removed: list[str] = []
    touched: dict[int, list[fitz.Rect]] = {}
    # Snapshot source layout before any redaction so kept spans keep original x/style.
    originals: dict[int, list[dict]] = {}
    for page in doc:
        if not remove_specs:
            break
        # One text/line extract per page. Searching every remove heading via
        # _heading_hits used to re-parse the page dict hundreds of times.
        page_text = page.get_text("text") or ""
        if not page_text.strip():
            continue
        page_squashed = _squash(page_text)
        page_lines = _page_lines(page)
        boxes: list[fitz.Rect] = []
        for spec in remove_specs:
            rule_id = str(spec["id"])
            heading = str(spec.get("heading") or "")
            if _squash(heading) not in page_squashed:
                continue
            extra = str(spec.get("extra") or "")
            if not _extra_matches(page_text, extra):
                continue
            for hit in _heading_hits(page, heading, lines=page_lines):
                if _covered_by_longer_heading(page, hit, heading, headings, lines=page_lines):
                    continue
                end_y = _block_end(page, hit.y0, headings, lines=page_lines)
                if not _block_matches(page, spec, hit.y0, end_y):
                    continue
                if _kept_by_other_spec(page, page_text, specs, heading, hit.y0, end_y, keep_ids):
                    continue
                removal = fitz.Rect(18, max(28, hit.y0 - 2), page.rect.x1 - 28, end_y)
                boxes.append(removal)
                touched.setdefault(page.number, []).append(removal)
                if rule_id not in removed:
                    removed.append(rule_id)
        if boxes:
            # Capture original kept-block geometry before redaction can nudge glyphs.
            originals[page.number] = _text_blocks(page)
            # No lasting white cover: restack rewrites surviving text into these bands.
            _apply_redact_boxes(page, boxes, cover=False)
    if touched:
        _restack_pages(doc, touched, originals=originals)
        _pack_action_across_pages(doc)
        _strip_im_fragments(doc)
        _drop_empty_pages(doc)
        for page in doc:
            text = page.get_text("text") or ""
            if re.search(
                r"annual valuation report|immediate action required|attention required",
                text,
                re.I,
            ):
                # Temporary: failure underlines only. Full ACTION/green/failure
                # underline + column normalize runs in _finalize_action_page_layout.
                _redraw_action_rules(page, only_failure=True)
    # Standalone failure-info / letter pages: delete the whole page when removed
    # (heading-only redaction can miss wrapped titles and leave the sheet in place).
    if _drop_removed_failure_pages(doc, remove_ids) and "L" not in removed and "L" in remove_ids:
        removed.append("L")
    # Always run: normalize column, underlines, and all-clear ACTION packing on
    # every Action page (not only NO IMMEDIATE pages — UAT fails on mixed layouts).
    _finalize_action_page_layout(doc)
    return removed


def _extra_matches(page_text: str, extra: str) -> bool:
    """'For current-method testing' also matches the notice line 'Current method testing:'.

    Purpose:
        'For current-method testing' also matches the notice line 'Current method testing:'.

    Args:
        page_text: Page text. Type: str.
        extra: Extra. Type: str.

    Returns:
        True or False.

    Raises:
        None.

    Example:
        _extra_matches("text", "text") returns True or False.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if not extra:
        return True
    def fold(value: str) -> str:
        """Fold.

        Purpose:
            Fold.

        Args:
            value: Value. Type: str.

        Returns:
            a str.

        Raises:
            None.

        Example:
            fold("text") returns a str.

        Side effects:
            None. This function only reads data and returns a value.
        """
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    haystack = fold(page_text)
    needle = fold(extra)
    if needle in haystack:
        return True
    if needle.startswith("for "):
        return needle[4:] in haystack
    return False


def _covered_by_longer_heading(
    page: fitz.Page,
    hit,
    heading: str,
    headings: list[str],
    *,
    lines: list[tuple[str, tuple[float, float, float, float]]] | None = None,
) -> bool:
    """'Failed Compliance Testing' is the start of the after-12-month heading.

    Purpose:
        'Failed Compliance Testing' is the start of the after-12-month heading.

    Args:
        page: One PDF page.
        hit: Hit. Type: unspecified.
        heading: Heading. Type: str.
        headings: Headings. Type: list[str].
        lines: Optional cached page lines from ``_page_lines``.

    Returns:
        True or False.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _covered_by_longer_heading(page, hit, "text") returns True or False.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for other in headings:
        if not other.startswith(heading) or len(other) <= len(heading):
            continue
        for rect in _heading_hits(page, other, lines=lines):
            if abs(rect.y0 - hit.y0) <= 2 and abs(rect.x0 - hit.x0) <= 2:
                return True
    return False


def _block_end(
    page: fitz.Page,
    y0: float,
    headings: list[str],
    *,
    lines: list[tuple[str, tuple[float, float, float, float]]] | None = None,
) -> float:
    """Stop at the next heading, including another copy of this same heading.

    Purpose:
        Stop at the next heading, including another copy of this same heading.

    Args:
        page: One PDF page.
        y0: Y0. Type: float.
        headings: Headings. Type: list[str].
        lines: Optional cached page lines from ``_page_lines``.

    Returns:
        a float.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _block_end(page, 1.0, []) returns a float.

    Side effects:
        None. This function only reads data and returns a value.
    """
    end_y = page.rect.y1 - 36
    cached = lines if lines is not None else _page_lines(page)
    seen: set[str] = set()
    for heading in headings:
        if not heading or heading in seen:
            continue
        seen.add(heading)
        for rect in _heading_hits(page, heading, lines=cached):
            if rect.y0 > y0 + 8:
                end_y = min(end_y, rect.y0 - 4)
    return end_y


def _heading_hits(
    page: fitz.Page,
    heading: str,
    *,
    lines: list[tuple[str, tuple[float, float, float, float]]] | None = None,
) -> list[fitz.Rect]:
    """A heading starts a line, and may wrap onto the next lines. Words inside a sentence are not a heading.

    Purpose:
        A heading starts a line, and may wrap onto the next lines. Words inside a sentence are not a heading.

    Args:
        page: One PDF page.
        heading: Heading. Type: str.
        lines: Optional cached page lines from ``_page_lines``.

    Returns:
        a list of fitz.Rect.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _heading_hits(page, "text") returns a list of fitz.Rect.

    Side effects:
        None. This function only reads data and returns a value.
    """
    target = _squash(heading)
    if not target:
        return []
    cached = lines if lines is not None else _page_lines(page)
    hits: list[fitz.Rect] = []
    for start in range(len(cached)):
        joined = ""
        rect = fitz.Rect(cached[start][1])
        for text, bbox in cached[start : start + 4]:
            joined += _squash(text)
            rect |= fitz.Rect(bbox)
            if len(joined) >= len(target):
                break
        if joined.startswith(target):
            hits.append(rect)
    return hits


def _squash(value: str) -> str:
    """Match a heading even when the PDF uses a different dash, dot, or line break.

    Purpose:
        Match a heading even when the PDF uses a different dash, dot, or line break.

    Args:
        value: Value. Type: str.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _squash("text") returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def _page_lines(page: fitz.Page) -> list[tuple[str, tuple[float, float, float, float]]]:
    """Page lines.

    Purpose:
        Page lines.

    Args:
        page: One PDF page.

    Returns:
        list[tuple[str, tuple[float, float, float, float]]].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _page_lines(page) returns list[tuple[str, tuple[float, float, float, float]]].

    Side effects:
        None. This function only reads data and returns a value.
    """
    lines: list[tuple[str, tuple[float, float, float, float]]] = []
    for block in page.get_text("dict").get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            text = "".join(span.get("text") or "" for span in line.get("spans") or [])
            if text.strip():
                lines.append((text, tuple(line["bbox"])))
    lines.sort(key=lambda item: (round(item[1][1]), item[1][0]))
    return lines


def _kept_by_other_spec(
    page: fitz.Page,
    page_text: str,
    specs: list[dict],
    heading: str,
    y0: float,
    y1: float,
    keep_ids: set[str],
) -> bool:
    """A combined ADP/ACP letter stays when a rule that says keep still needs it.

    Purpose:
        A combined ADP/ACP letter stays when a rule that says keep still needs it.

    Args:
        page: One PDF page.
        page_text: Page text. Type: str.
        specs: Specs. Type: list[dict].
        heading: Heading. Type: str.
        y0: Y0. Type: float.
        y1: Y1. Type: float.
        keep_ids: Keep ids. Type: set[str].

    Returns:
        True or False.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _kept_by_other_spec(page, "text", []) returns True or False.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for spec in specs:
        if str(spec.get("heading") or "") != heading:
            continue
        if str(spec["id"]) not in keep_ids:
            continue
        if not _extra_matches(page_text, str(spec.get("extra") or "")):
            continue
        if _block_matches(page, spec, y0, y1):
            return True
    return False


def _block_matches(page: fitz.Page, spec: dict, y0: float, y1: float) -> bool:
    """Prior and Current share one heading. The Current block says 'unless QNEC'.

    Purpose:
        Prior and Current share one heading. The Current block says 'unless QNEC'.

    Args:
        page: One PDF page.
        spec: Spec. Type: dict.
        y0: Y0. Type: float.
        y1: Y1. Type: float.

    Returns:
        True or False.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _block_matches(page, {}, 1.0) returns True or False.

    Side effects:
        None. This function only reads data and returns a value.
    """
    contains = str(spec.get("block_contains") or "").lower()
    excludes = str(spec.get("block_excludes") or "").lower()
    if not contains and not excludes:
        return True
    words = page.get_text("words") or []
    text = " ".join(
        word[4] for word in words if word[1] >= y0 - 1 and word[3] <= y1 + 1
    ).lower()
    if contains and contains not in text:
        return False
    if excludes and excludes in text:
        return False
    return True


def _restack_pages(
    doc: fitz.Document,
    touched: dict[int, list[fitz.Rect]],
    originals: dict[int, list[dict]] | None = None,
) -> None:
    """Collapse removed regions by their exact height while keeping each surviving span at its source x-position and style.

    When ``originals`` is provided (pre-redaction snapshots), kept blocks are taken
    from that layout so alignment matches the source PDF — redaction must not be
    allowed to nudge remaining glyph positions before rewrite.
    """
    for page in doc:
        removed = touched.get(page.number)
        if not removed:
            continue
        removed_bands = _merged_vertical_bands(removed)
        header_rule_y = _top_header_rule_y(page)
        snapshot = list((originals or {}).get(page.number) or [])
        if snapshot:
            # Pre-removal layout: drop blocks that lived inside removed bands.
            kept = [block for block in snapshot if not _block_covered_by_bands(block, removed_bands)]
            wipe_sources = snapshot
        else:
            # Page already redacted: every remaining block is a survivor.
            kept = _text_blocks(page)
            wipe_sources = kept
        if not kept and not wipe_sources:
            continue
        body = [block for block in kept if not _is_page_number_block(page, block)]
        footer = [block for block in kept if _is_page_number_block(page, block)]
        # Wipe whatever text is still on the page (post-removal leftovers + survivors).
        present = _text_blocks(page)
        wipe = [block["bbox"] for block in present] + [block["bbox"] for block in wipe_sources]
        if wipe:
            _apply_redact_boxes(page, wipe, cover=False)
        for block in body:
            delta = _upshift_delta(float(block["bbox"].y0), removed_bands)
            if header_rule_y is not None and float(block["bbox"].y0) > header_rule_y:
                # Cap upshift so content cannot climb into the header divider.
                # Do not invent a new Kaagaz y — only protect the original gap floor.
                minimum_y = header_rule_y + 30.0
                delta = max(delta, minimum_y - float(block["bbox"].y0))
            for span in block["spans"]:
                # origin.x / font / size come from the pre-removal snapshot.
                _write_span(page, span, delta)
        for block in footer:
            for span in block["spans"]:
                _write_span(page, span, 0)
        # Only clear underlines that sat inside removed bands (orphans). Do not wipe
        # underlines under surviving ACTION / green / kept failure headings.
        _clear_short_rules_in_bands(page, removed_bands)


def _block_covered_by_bands(block: dict, bands: list[tuple[float, float]]) -> bool:
    """True when a text block mostly sits inside a removed vertical band."""
    if not bands:
        return False
    y0 = float(block["bbox"].y0)
    y1 = float(block["bbox"].y1)
    height = max(y1 - y0, 1.0)
    mid = (y0 + y1) / 2.0
    for top, bottom in bands:
        if top <= mid <= bottom:
            return True
        overlap = max(0.0, min(y1, bottom) - max(y0, top))
        if overlap / height >= 0.55:
            return True
    return False


def _upshift_delta(y0: float, bands: list[tuple[float, float]]) -> float:
    """Vertical shift for a block whose top is at ``y0`` after removing ``bands``."""
    total = 0.0
    for top, bottom in bands:
        if top >= y0:
            continue
        total += min(bottom, y0) - top
    return -total


def _merged_vertical_bands(boxes: list[fitz.Rect]) -> list[tuple[float, float]]:
    """Merge overlapping redaction bands so their heights are not subtracted twice."""
    intervals = sorted((float(box.y0), float(box.y1)) for box in boxes if box.y1 > box.y0)
    merged: list[tuple[float, float]] = []
    for top, bottom in intervals:
        if merged and top <= merged[-1][1]:
            previous_top, previous_bottom = merged[-1]
            merged[-1] = (previous_top, max(previous_bottom, bottom))
        else:
            merged.append((top, bottom))
    return merged


def _top_header_rule(page: fitz.Page) -> tuple[float, float] | None:
    """Return ``(y, x0)`` for the full-width AV header divider, or ``None``."""
    text = page.get_text("text") or ""
    if not re.search(r"annual valuation report", text, re.I):
        return None
    found: list[tuple[float, float]] = []
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if not item or item[0] != "l" or len(item) < 3:
                continue
            start, end = fitz.Point(item[1]), fitz.Point(item[2])
            if abs(start.y - end.y) > 1.5:
                continue
            left, right = sorted((start.x, end.x))
            if left <= 52 and right >= page.rect.width - 52 and start.y < page.rect.height * 0.4:
                found.append((start.y, left))
    if not found:
        return None
    # Prefer the lowest (main) header rule when several full-width strokes exist.
    found.sort(key=lambda item: item[0])
    return found[-1]


def _top_header_rule_y(page: fitz.Page) -> float | None:
    """Find the full-width header divider near the top of an Annual Valuation Report page."""
    found = _top_header_rule(page)
    return found[0] if found else None


def _top_header_rule_x0(page: fitz.Page) -> float | None:
    """Left edge of the AV header divider (ACTION column is inset from this)."""
    found = _top_header_rule(page)
    return found[1] if found else None


# Only nudge when ACTION sits flush on the AV header rule (rule at 36 → ≈38).
# Never pull an already-inset source column left (e.g. 40 or 54 → 38/40).
_ACTION_RULE_INSET = 2.0


def _ops_action_column_x(page: fitz.Page, preferred: float | None = None) -> float:
    """Resolve the Action Required left column for every AV / Action page.

    When a header rule exists (often x≈36):
    - flush on the rule → nudge slightly to rule+2 (≈38)
    - already in the normal band (≈38–60, including source x≈40 or ≈54) → keep it
    - do not snap a right-hand source column left to the rule inset
    """
    rule_x = _top_header_rule_x0(page)
    ops = float(rule_x) + _ACTION_RULE_INSET if rule_x is not None else None
    if preferred is not None:
        preferred = float(preferred)
        if rule_x is not None and abs(preferred - float(rule_x)) <= 1.0:
            return ops if ops is not None else preferred
        # Keep source/expected column — forcing ops was shifting ACTION left.
        if 30.0 <= preferred <= 60.0:
            return preferred
        return preferred
    if ops is not None:
        return ops
    median = _action_column_x(page)
    if 30.0 <= median <= 60.0:
        return median
    return 54.0


_ACTION_PHRASE_RE = re.compile(
    r"^(?:ACTION REQUIRED\s*$|"
    r"IMMEDIATE ACTION REQUIRED\b.*|"
    r"ATTENTION REQUIRED\b.*|"
    r"NO IMMEDIATE ACTION IS REQUIRED(?: AT THIS TIME)?\s*$)",
    re.I,
)


def _is_page_number_block(page: fitz.Page, block: dict) -> bool:
    """Is page number block.

    Purpose:
        Is page number block.

    Args:
        page: One PDF page.
        block: Block. Type: dict.

    Returns:
        True or False.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _is_page_number_block(page, {}) returns True or False.

    Side effects:
        None. This function only reads data and returns a value.
    """
    text = " ".join(span["text"] for span in block["spans"]).strip()
    return bool(re.fullmatch(r"\d{1,3}", text)) and block["bbox"].y0 > page.rect.y1 - 70


def _text_blocks(page: fitz.Page) -> list[dict]:
    """Text blocks.

    Purpose:
        Text blocks.

    Args:
        page: One PDF page.

    Returns:
        list[dict].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _text_blocks(page) returns list[dict].

    Side effects:
        None. This function only reads data and returns a value.
    """
    blocks: list[dict] = []
    for raw in page.get_text("dict").get("blocks") or []:
        if raw.get("type") != 0:
            continue
        spans: list[dict] = []
        for line in raw.get("lines") or []:
            for span in line.get("spans") or []:
                text = span.get("text") or ""
                if not text.strip():
                    continue
                origin = span.get("origin") or (span["bbox"][0], span["bbox"][3])
                spans.append(
                    {
                        "text": text,
                        "origin": fitz.Point(origin[0], origin[1]),
                        "size": float(span.get("size") or 11),
                        "font": str(span.get("font") or ""),
                        "flags": int(span.get("flags") or 0),
                        "color": span.get("color") or 0,
                        "bbox": fitz.Rect(span["bbox"]),
                    }
                )
        if not spans:
            continue
        blocks.append({"bbox": fitz.Rect(raw["bbox"]), "spans": spans})
    blocks.sort(key=lambda item: (round(item["bbox"].y0, 1), item["bbox"].x0))
    return blocks


def _image_bands(page: fitz.Page) -> tuple[float, float]:
    """Image bands.

    Purpose:
        Image bands.

    Args:
        page: One PDF page.

    Returns:
        tuple[float, float].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _image_bands(page) returns tuple[float, float].

    Side effects:
        None. This function only reads data and returns a value.
    """
    header = 54.0
    footer = page.rect.y1 - 36.0
    mid = page.rect.y0 + page.rect.height * 0.4
    low = page.rect.y0 + page.rect.height * 0.7
    for raw in page.get_text("dict").get("blocks") or []:
        if raw.get("type") != 1:
            continue
        rect = fitz.Rect(raw["bbox"])
        if rect.y1 <= mid:
            header = max(header, rect.y1 + 8)
        if rect.y0 >= low:
            footer = min(footer, rect.y0 - 8)
    return header, footer


def _write_span(page: fitz.Page, span: dict, delta: float) -> None:
    """Write span.

    Purpose:
        Write span.

    Args:
        page: One PDF page.
        span: Span. Type: dict.
        delta: Delta. Type: float.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _write_span(page, {}, 1.0) returns None.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    point = fitz.Point(span["origin"].x, span["origin"].y + delta)
    fontname = _base_font(span["font"], span["flags"])
    # Built-in Helvetica lacks many typographic glyphs; map smart quotes so
    # restack/pack does not substitute middle-dots for apostrophes.
    text = str(span.get("text") or "")
    text = (
        text.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )
    # Recap bullets come from embedded TrueType Symbol. Rewriting with the
    # built-in Type1 Symbol + WinAnsiEncoding turns · into a "<"-like glyph in
    # many viewers — draw a filled disc matching the source ink size instead.
    if _is_bullet_glyph_text(text):
        _draw_bullet_disc_for_span(page, span, delta)
        return
    try:
        page.insert_text(
            point,
            text,
            fontsize=span["size"],
            fontname=fontname,
            color=_rgb(span["color"]),
            overlay=True,
        )
    except Exception:
        page.insert_text(
            point,
            text,
            fontsize=span["size"],
            fontname="helv",
            color=_rgb(span["color"]),
            overlay=True,
        )


def _draw_bullet_disc_for_span(page: fitz.Page, span: dict, delta: float = 0.0) -> None:
    """Draw a filled disc matching a source Symbol bullet glyph.

    Position from origin (+delta) so packed/restacked spans stay aligned even
    when a stale source bbox is still attached to the span dict.
    """
    size = float(span.get("size") or 7.35)
    origin = span["origin"]
    ox = float(origin.x if hasattr(origin, "x") else origin[0])
    oy = float(origin.y if hasattr(origin, "y") else origin[1]) + float(delta)
    bbox = span.get("bbox")
    if bbox is not None:
        rect = fitz.Rect(bbox)
        # Ink diameter ≈ half the glyph box (TrueType · ≈ 3.38 @ 7.35).
        diam = max(2.8, min(4.2, (rect.width + rect.height) / 2.0 * 0.55))
    else:
        # TrueType Symbol · width ≈ 0.46 × fontsize (7.35→3.38, 8.15→3.75).
        diam = max(2.8, min(4.2, size * 0.46))
    cx = ox + diam / 2.0
    cy = oy - size * 0.35
    page.draw_oval(
        fitz.Rect(cx - diam / 2.0, cy - diam / 2.0, cx + diam / 2.0, cy + diam / 2.0),
        color=(0, 0, 0),
        fill=(0, 0, 0),
        width=0,
    )


def _is_bullet_glyph_text(text: str) -> bool:
    """True for a lone list-bullet glyph (Recap · / • marks)."""
    value = (text or "").strip()
    if len(value) != 1:
        return False
    return value in {"·", "•", "●", "∙", "▪", "▫", "■", "□"} or ord(value) in {
        0x00B7,
        0x2022,
        0x25CF,
        0x2219,
        0xF0B7,
        0x25AA,
        0x25AB,
        0x25A0,
        0x25A1,
    }


def _base_font(font: str, flags: int) -> str:
    """Base font.

    Purpose:
        Base font.

    Args:
        font: Font. Type: str.
        flags: Flags. Type: int.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _base_font("text", 1) returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    name = (font or "").lower()
    if "symbol" in name or name == "symb":
        return "symb"
    if "zapf" in name or "dingbat" in name or name == "zadb":
        return "zadb"
    bold = bool(flags & 16) or "bold" in name
    italic = bool(flags & 2) or "italic" in name or "oblique" in name
    serif = any(token in name for token in ("times", "roman", "georgia", "cambria", "garamond", "palatino"))
    mono = any(token in name for token in ("courier", "mono", "consolas"))
    if mono:
        return { (True, True): "cobi", (True, False): "cobo", (False, True): "coit" }.get((bold, italic), "cour")
    if serif:
        return { (True, True): "tibi", (True, False): "tibo", (False, True): "titi" }.get((bold, italic), "tiro")
    return { (True, True): "hibi", (True, False): "hebo", (False, True): "heit" }.get((bold, italic), "helv")


def _rgb(color: object) -> tuple[float, float, float]:
    """Rgb.

    Purpose:
        Rgb.

    Args:
        color: Color. Type: object.

    Returns:
        a tuple[float, float, float].

    Raises:
        None.

    Example:
        _rgb(color) returns a tuple[float, float, float].

    Side effects:
        None. This function only reads data and returns a value.
    """
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        values = [float(item) for item in color[:3]]
        if max(values) > 1:
            return values[0] / 255, values[1] / 255, values[2] / 255
        return values[0], values[1], values[2]
    value = int(color or 0)
    return ((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255


_KEPT_ACTION = re.compile(
    r"immediate action required|attention required|no immediate action is required",
    re.I,
)


def _is_recap_text(text: str) -> bool:
    """Is recap text.

    Purpose:
        Is recap text.

    Args:
        text: Text taken from a page or a file.

    Returns:
        bool.

    Raises:
        None.

    Example:
        _is_recap_text("text") returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return bool(re.search(r"year[- ]end recap|important information", text or "", re.I))


def _strip_im_fragments(doc: fitz.Document) -> None:
    """Remove clipped IMMEDIATE leftovers such as IM, MEDIATE, or a lone I/i.

    Purpose:
        Remove clipped IMMEDIATE leftovers such as IM, MEDIATE, or a lone I/i.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _strip_im_fragments(doc) returns None.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    for page in doc:
        boxes = [
            fitz.Rect(word[:4])
            for word in (page.get_text("words") or [])
            if str(word[4]).upper() in {"IM", "MEDIATE", "I"}
        ]
        if boxes:
            _apply_redact_boxes(page, [_pad_rect(box, page) for box in boxes])


def _is_noise_text(text: str) -> bool:
    """A page number or a stray letter such as 'i' is not a paragraph.

    Purpose:
        A page number or a stray letter such as 'i' is not a paragraph.

    Args:
        text: Text taken from a page or a file.

    Returns:
        bool.

    Raises:
        None.

    Example:
        _is_noise_text("text") returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    words = re.findall(r"[A-Za-z0-9]+", text or "")
    # "IM" is the clipped start of IMMEDIATE after a redact. It is not a paragraph.
    return not any(
        len(word) >= 2 and re.search(r"[A-Za-z]", word) and word.upper() not in {"IM", "MEDIATE"}
        for word in words
    )


def _pad_rect(rect: fitz.Rect, page: fitz.Page) -> fitz.Rect:
    """Cover the dot on a narrow glyph. Redaction otherwise leaves the letter i.

    Purpose:
        Cover the dot on a narrow glyph. Redaction otherwise leaves the letter i.

    Args:
        rect: Rect. Type: fitz.Rect.
        page: One PDF page.

    Returns:
        a fitz.Rect.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _pad_rect(rect, page) returns a fitz.Rect.

    Side effects:
        None. This function only reads data and returns a value.
    """
    # Extend upward to cover the dot on i. Keep the bottom tight so the next line stays.
    return (fitz.Rect(rect) + (-1, -3, 1, 1)) & page.rect


def _apply_redact_boxes(page: fitz.Page, boxes: list[fitz.Rect], *, cover: bool = True) -> None:
    """Apply redact boxes.

    Purpose:
        Apply redact boxes.

    Args:
        page: One PDF page.
        boxes: Boxes. Type: list[fitz.Rect].
        cover: When True, paint lasting white rectangles over the redacted bands.
            Use False when leftover text will be rewritten into those bands (restack),
            because the overlays would hide the shifted content.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _apply_redact_boxes(page, []) returns None.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    rects = [rect for box in boxes if (rect := _pad_rect(box, page)) and not rect.is_empty]
    if not rects:
        return
    for rect in rects:
        page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions(images=0)
    leftover: list[fitz.Rect] = []
    for rect in rects:
        for word in page.get_text("words") or []:
            word_rect = fitz.Rect(word[:4])
            if word_rect.intersects(rect):
                leftover.append(_pad_rect(word_rect, page))
    if leftover:
        for rect in leftover:
            page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(images=0)
    if cover:
        for rect in rects:
            page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1), width=0, overlay=True)


def _action_blocks_to_move(page: fitz.Page) -> list[dict]:
    """The kept action line and its body. Skip the page number and the Year End Recap.

    Purpose:
        The kept action line and its body. Skip the page number and the Year End Recap.

    Args:
        page: One PDF page.

    Returns:
        list[dict].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _action_blocks_to_move(page) returns list[dict].

    Side effects:
        None. This function only reads data and returns a value.
    """
    blocks: list[dict] = []
    started = False
    for block in _text_blocks(page):
        if _is_page_number_block(page, block):
            continue
        text = " ".join(span["text"] for span in block["spans"]).strip()
        if not text or _is_noise_text(text):
            continue
        if _KEPT_ACTION.search(text):
            if _is_recap_text(text):
                break
            started = True
            blocks.append(block)
            continue
        if not started:
            continue
        if _is_recap_text(text) or re.search(r"annual valuation report", text, re.I):
            break
        blocks.append(block)
    return blocks


def _action_column_x(page: fitz.Page) -> float:
    """Left edge used by Action Required headings on this page (client packages ~40, built ~54)."""
    xs: list[float] = []
    for block in _text_blocks(page):
        text = " ".join(span["text"] for span in block["spans"]).strip()
        if re.match(
            r"^(ACTION REQUIRED|IMMEDIATE ACTION REQUIRED|ATTENTION REQUIRED|NO IMMEDIATE ACTION IS REQUIRED)",
            text,
            re.I,
        ):
            xs.append(float(block["bbox"].x0))
    if not xs:
        return 54.0
    xs.sort()
    return xs[len(xs) // 2]


def _write_action_heading(page: fitz.Page, cursor: float, x: float | None = None) -> float:
    """Write the ACTION REQUIRED heading. ``cursor`` is the text baseline.

    Does not invent an underline — source packages vary, and redrawing a rule
    here makes ACTION borders diverge from the source PDF.
    """
    left = 54.0 if x is None else float(x)
    page.insert_text((left, cursor), "ACTION REQUIRED", fontsize=11, fontname="hebo", color=(0, 0, 0))
    # Approximate next-cursor below the heading ink.
    return cursor + 18


def _short_rule_boxes_below(page: fitz.Page, below_y: float) -> list[fitz.Rect]:
    """Return thin heading-underline rects below the header divider."""
    boxes: list[fitz.Rect] = []
    for drawing in page.get_drawings():
        if drawing.get("color") in {(1, 1, 1), (1.0, 1.0, 1.0)}:
            continue
        for item in drawing.get("items") or []:
            if not item or item[0] != "l" or len(item) < 3:
                continue
            start, end = fitz.Point(item[1]), fitz.Point(item[2])
            if abs(start.y - end.y) > 1.5:
                continue
            y = start.y
            if y <= below_y + 2:
                continue
            width = abs(end.x - start.x)
            if width >= page.rect.width * 0.7:
                continue
            left, right = sorted((start.x, end.x))
            boxes.append(fitz.Rect(left - 1, y - 1.5, right + 1, y + 1.5))
    return boxes


def _clear_short_rules_below(page: fitz.Page, below_y: float, *, redact: bool = False) -> None:
    """Remove leftover heading underlines below the header divider.

    Prefer white cover while text may still overlap the band. After that text
    has been redacted, ``redact=True`` deletes the strokes from the page.
    """
    boxes = _short_rule_boxes_below(page, below_y)
    _cover_or_redact_rules(page, boxes, redact=redact)


def _clear_short_rules_in_bands(page: fitz.Page, bands: list[tuple[float, float]]) -> None:
    """White-out short underlines whose y falls inside removed vertical bands."""
    if not bands:
        return
    boxes: list[fitz.Rect] = []
    for drawing in page.get_drawings():
        if drawing.get("color") in {(1, 1, 1), (1.0, 1.0, 1.0)}:
            continue
        for item in drawing.get("items") or []:
            if not item or item[0] != "l" or len(item) < 3:
                continue
            start, end = fitz.Point(item[1]), fitz.Point(item[2])
            if abs(start.y - end.y) > 1.5:
                continue
            y = start.y
            width = abs(end.x - start.x)
            if width >= page.rect.width * 0.7:
                continue
            if not any(top - 1.0 <= y <= bottom + 1.0 for top, bottom in bands):
                continue
            left, right = sorted((start.x, end.x))
            boxes.append(fitz.Rect(left - 1, y - 1.5, right + 1, y + 1.5))
    _cover_or_redact_rules(page, boxes, redact=False)


def _cover_or_redact_rules(page: fitz.Page, boxes: list[fitz.Rect], *, redact: bool) -> None:
    """Remove short rule strokes without destroying overlapping text glyphs."""
    if not boxes:
        return
    if redact:
        # Still prefer white cover: apply_redactions on a rule through text ink
        # deletes the glyphs (seen wiping ACTION / NO IMMEDIATE).
        redact = False
    for rect in boxes:
        page.draw_line(
            fitz.Point(rect.x0, (rect.y0 + rect.y1) / 2),
            fitz.Point(rect.x1, (rect.y0 + rect.y1) / 2),
            color=(1, 1, 1),
            width=2.4,
            overlay=True,
        )


def _finalize_no_immediate_pages(doc: fitz.Document) -> None:
    """Backward-compatible alias — full layout runs in ``_finalize_action_page_layout``."""
    _finalize_action_page_layout(doc)


def _finalize_action_page_layout(doc: fitz.Document) -> None:
    """Normalize Action Required column, underlines, and all-clear packing on every AV page.

    UAT fails when only NO-IMMEDIATE pages are fixed: failure / mixed pages also
    need a shared OPS column (rule + 2) and restored underlines after restack.
    """
    for page in doc:
        text = page.get_text("text") or ""
        if _is_notice_or_excess_page(text):
            continue
        if not _is_action_flow_page(page):
            continue
        if _is_recap_text(text) and not re.search(
            r"ACTION REQUIRED|IMMEDIATE ACTION|NO IMMEDIATE ACTION", text, re.I
        ):
            continue

        action = None
        green = None
        for block in _text_blocks(page):
            joined = " ".join(span["text"] for span in block["spans"]).strip()
            if action is None and re.fullmatch(r"ACTION REQUIRED", joined, re.I):
                action = block
            if green is None and re.match(
                r"NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME", joined, re.I
            ):
                green = block

        # Clear orphan rules that cut through heading ink (leftover from removals).
        for block in _text_blocks(page):
            joined = " ".join(span["text"] for span in block["spans"]).strip()
            if not _ACTION_PHRASE_RE.match(joined):
                continue
            _cover_rules_through_band(
                page,
                float(block["bbox"].y0),
                float(block["bbox"].y1),
                float(block["bbox"].x0),
                float(block["bbox"].x1),
            )

        preferred = None
        if action is not None:
            preferred = float(action["bbox"].x0)
        elif green is not None:
            preferred = float(green["bbox"].x0)
        else:
            preferred = _action_column_x(page)
        column_x = _ops_action_column_x(page, preferred)

        # All-clear: insert missing ACTION REQUIRED above the green line.
        only_green = (
            green is not None
            and action is None
            and not re.search(r"IMMEDIATE ACTION REQUIRED|ATTENTION REQUIRED", text, re.I)
        )
        if only_green:
            green_top = float(green["bbox"].y0)
            header_rule_y = _top_header_rule_y(page)
            if header_rule_y is not None:
                heading_baseline = header_rule_y + 28.0
                if heading_baseline + 4.0 >= green_top:
                    heading_baseline = green_top - 14.0
                if heading_baseline < header_rule_y + 14.0:
                    heading_baseline = header_rule_y + 14.0
            else:
                heading_baseline = green_top - 14.0
            _write_action_heading(page, heading_baseline, x=column_x)

        # Force every action phrase onto the same OPS left edge.
        _left_align_action_phrases(page, column_x)
        # Pull green closer under ACTION when nothing sits between them.
        _tighten_no_immediate_under_action(page)
        # Restore filled underlines for ACTION / green / failure headings.
        _redraw_action_rules(page, only_failure=False, invent=True)


def _left_align_action_phrases(page: fitz.Page, column_x: float) -> None:
    """Shift all Action Required phrases so their left edges share ``column_x``."""
    targets = []
    for block in _text_blocks(page):
        joined = " ".join(span["text"] for span in block["spans"]).strip()
        if _ACTION_PHRASE_RE.match(joined):
            targets.append(block)
    # Top-to-bottom so redactions do not disturb yet-to-move lower phrases' geometry
    # more than necessary; each target still uses its own captured bbox.
    targets.sort(key=lambda block: float(block["bbox"].y0))
    for block in targets:
        dx = float(column_x) - float(block["bbox"].x0)
        if abs(dx) < 0.75:
            continue
        # cover=True so the original glyphs are gone — otherwise phrases duplicate.
        _apply_redact_boxes(page, [block["bbox"]], cover=True)
        for span in block["spans"]:
            moved = {
                **span,
                "origin": fitz.Point(float(span["origin"].x) + dx, float(span["origin"].y)),
            }
            _write_span(page, moved, 0)


def _tighten_no_immediate_under_action(page: fitz.Page) -> None:
    """Reduce vertical gap between ACTION REQUIRED and the green NO IMMEDIATE line.

    Only when nothing else sits between them (failure pages keep their spacing).
    """
    action = None
    green = None
    for block in _text_blocks(page):
        joined = " ".join(span["text"] for span in block["spans"]).strip()
        if action is None and re.fullmatch(r"ACTION REQUIRED", joined, re.I):
            action = block
        if green is None and re.match(r"NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME", joined, re.I):
            green = block
    if action is None or green is None:
        return
    action_bottom = float(action["bbox"].y1)
    green_top = float(green["bbox"].y0)
    if green_top <= action_bottom:
        return
    # Bail if another action heading or body line sits between ACTION and green.
    for block in _text_blocks(page):
        mid = (float(block["bbox"].y0) + float(block["bbox"].y1)) / 2.0
        if mid <= action_bottom + 1.0 or mid >= green_top - 1.0:
            continue
        joined = " ".join(span["text"] for span in block["spans"]).strip()
        if not joined or _is_noise_text(joined):
            continue
        return
    # Target ~12pt from ACTION baseline band to green top (source/Kaagaz packing).
    target_top = action_bottom + 10.0
    gap = green_top - action_bottom
    if gap <= 14.0:
        return
    dy = target_top - green_top
    if abs(dy) < 0.75:
        return
    _apply_redact_boxes(page, [green["bbox"]], cover=True)
    for span in green["spans"]:
        moved = {
            **span,
            "origin": fitz.Point(float(span["origin"].x), float(span["origin"].y) + dy),
        }
        _write_span(page, moved, 0)


def _pack_action_across_pages(doc: fitz.Document) -> None:
    """Pull Action Required content up: fill earlier pages that still have whitespace.

    First moves kept action onto an empty Annual Valuation anchor page. Then repeatedly
    packs leftover paragraphs from later pages into prior pages that still have room
    above the footer.
    """
    _pull_kept_action_forward(doc)
    for _ in range(12):
        if not _pack_one_action_overflow(doc):
            break


def _is_notice_or_excess_page(text: str) -> bool:
    """True for Excess / Failed / sample-letter pages that share the AV header.

    These must stay on their own SOP pages and must never pack onto Action Required.
    """
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()][:16]
    head = "\n".join(lines)
    return bool(
        re.search(
            r"^(?:failed compliance testing|excess return notice|excess return summary)\b|"
            r"^sample/draft communication|"
            r"^annual additions\s*\(\s*irc\s*415\s*\)\s*test failure|"
            r"^415\s*\(\s*c\s*\)?.{0,40}test failure information",
            head,
            re.I | re.M,
        )
    )


def _is_action_flow_page(page: fitz.Page) -> bool:
    """Pages that participate in Action Required reflow (not cover; recap only if it holds action)."""
    text = page.get_text("text") or ""
    # Cover letter pages are not part of Action Required reflow.
    if re.search(r"we are pleased to provide|dear plan sponsor", text, re.I) and not re.search(
        r"annual valuation report", text, re.I
    ):
        return False
    if _is_recap_text(text) and not _KEPT_ACTION.search(text):
        return False
    # Excess / Failed / sample letters use the same AV header — exclude from reflow
    # so whitespace on ACTION cannot pull those notices onto the prior page.
    if _is_notice_or_excess_page(text):
        return False
    return bool(
        re.search(
            r"annual valuation report|immediate action required|attention required|"
            r"no immediate action|^\s*ACTION REQUIRED\s*$",
            text,
            re.I | re.M,
        )
    )


def _action_content_bottom(page: fitz.Page) -> float:
    """Lowest content edge on the page, ignoring page numbers."""
    bottom = 0.0
    for block in _text_blocks(page):
        if _is_page_number_block(page, block):
            continue
        text = " ".join(span["text"] for span in block["spans"]).strip()
        if not text or _is_noise_text(text):
            continue
        bottom = max(bottom, float(block["bbox"].y1))
    header_rule_y = _top_header_rule_y(page)
    if bottom <= 0 and header_rule_y is not None:
        return header_rule_y + 24.0
    return bottom


def _movable_action_overflow(page: fitz.Page) -> list[dict]:
    """Paragraphs on a later action page that can fill whitespace on a prior page."""
    header_rule_y = _top_header_rule_y(page)
    blocks: list[dict] = []
    for block in _text_blocks(page):
        if _is_page_number_block(page, block):
            continue
        text = " ".join(span["text"] for span in block["spans"]).strip()
        if not text or _is_noise_text(text):
            continue
        if re.search(r"annual valuation report", text, re.I):
            continue
        if header_rule_y is not None and block["bbox"].y1 <= header_rule_y + 2:
            continue
        if re.fullmatch(r"ACTION REQUIRED", text, re.I):
            # Keep the section label with its page; move body paragraphs only.
            continue
        if _is_recap_text(text):
            break
        # Never pull Excess / Failed notice bodies onto a prior ACTION page.
        if re.search(
            r"failed compliance testing|excess return notice|excess return summary|"
            r"sample/draft communication",
            text,
            re.I,
        ):
            break
        if re.fullmatch(r"\d{5,7}", text) and block["bbox"].y0 < (header_rule_y or 200):
            continue
        blocks.append(block)
    return blocks


def _pack_one_action_overflow(doc: fitz.Document) -> bool:
    """Move as many leading overflow blocks as fit from one later page onto the prior page.

    Kept spans keep their original source x. Vertical gaps between consecutively
    moved blocks reuse the original spacing from the source page.
    """
    flow = [page for page in doc if _is_action_flow_page(page)]
    for dest, source in zip(flow, flow[1:]):
        footer_limit = float(dest.rect.y1) - 52.0
        cursor = _action_content_bottom(dest) + 14.0
        free = footer_limit - cursor
        if free < 40:
            continue
        overflow = _movable_action_overflow(source)
        if not overflow:
            continue
        moved: list[dict] = []
        prev_source_bottom: float | None = None
        written_bottom = cursor
        for block in overflow:
            height = float(block["bbox"].height)
            if height + 10 > free:
                break
            if prev_source_bottom is None:
                target_top = cursor
            else:
                # Same gap the two blocks had on the original page.
                orig_gap = float(block["bbox"].y0) - prev_source_bottom
                target_top = written_bottom + max(4.0, orig_gap)
            if target_top + height > footer_limit:
                break
            delta = target_top - float(block["bbox"].y0)
            for span in block["spans"]:
                _write_span(dest, span, delta)
            moved.append(block)
            prev_source_bottom = float(block["bbox"].y1)
            written_bottom = target_top + height
            free = footer_limit - written_bottom
        if not moved:
            continue
        boxes = [block["bbox"] for block in moved]
        source_snapshot = _text_blocks(source)
        _apply_redact_boxes(source, boxes, cover=False)
        _restack_pages(doc, {source.number: boxes}, originals={source.number: source_snapshot})
        return True
    return False


def _pull_kept_action_forward(doc: fitz.Document) -> None:
    """When every item on the Action Required page is removed, move the green line up under the header.

    Purpose:
        When every item on the Action Required page is removed, move the green line up under the header.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _pull_kept_action_forward(doc) returns None.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    anchor = None
    later: list[fitz.Page] = []
    for page in doc:
        if page.number == 0:
            continue
        text = page.get_text("text") or ""
        # Skip Excess / Failed pages — they share the AV header but are not Action.
        if _is_notice_or_excess_page(text):
            continue
        if anchor is None and re.search(r"annual valuation report", text, re.I):
            anchor = page
            continue
        if anchor is not None and _KEPT_ACTION.search(text):
            later.append(page)
    if anchor is None or not later or _KEPT_ACTION.search(anchor.get_text("text") or ""):
        return
    header_rule_y = _top_header_rule_y(anchor)
    anchor_blocks = _text_blocks(anchor)
    # insert_text points are baselines; keep a gap under the header divider.
    baseline = (anchor_blocks[-1]["bbox"].y1 + 24) if anchor_blocks else 90
    if header_rule_y is not None:
        baseline = max(baseline, header_rule_y + 40)
    column_x = _action_column_x(anchor)
    if not re.search(r"(?m)^\s*ACTION REQUIRED\s*$", anchor.get_text("text") or ""):
        baseline = _write_action_heading(anchor, baseline, x=column_x)
    delete_numbers: list[int] = []
    for page in later:
        blocks = _action_blocks_to_move(page)
        if not blocks:
            continue
        prev_source_bottom: float | None = None
        for block in blocks:
            # Keep each span's original source x; reuse original vertical gaps.
            if prev_source_bottom is None:
                target_top = baseline - 11
            else:
                orig_gap = float(block["bbox"].y0) - prev_source_bottom
                target_top = baseline + max(4.0, orig_gap)
            delta = target_top - float(block["bbox"].y0)
            for span in block["spans"]:
                _write_span(anchor, span, delta)
            prev_source_bottom = float(block["bbox"].y1)
            baseline = target_top + float(block["bbox"].height)
        if _is_recap_text(page.get_text("text") or ""):
            _apply_redact_boxes(page, [block["bbox"] for block in blocks])
            continue
        delete_numbers.append(page.number)
    for number in reversed(delete_numbers):
        doc.delete_page(number)


def _action_heading_lines(page: fitz.Page) -> list[dict]:
    """Collect Action Required heading lines with exact ink bounds.

    Word y0 values often differ by a fraction of a point after restack, so grouping
    by ``round(y0)`` splits one phrase and draws a short or long underline. Prefer
    PDF text lines, then fall back to a tolerant y-cluster of words.
    """
    # Client packages often continue IMMEDIATE/ATTENTION with " - …" detail text.
    heading_re = re.compile(
        r"^(?:ACTION REQUIRED\s*$|"
        r"IMMEDIATE ACTION REQUIRED\b.*|"
        r"ATTENTION REQUIRED\b.*|"
        r"NO IMMEDIATE ACTION IS REQUIRED(?: AT THIS TIME)?\s*$)",
        re.I,
    )
    found: list[dict] = []
    for block in page.get_text("dict").get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            spans = [span for span in line.get("spans") or [] if str(span.get("text") or "").strip()]
            if not spans:
                continue
            text = "".join(str(span.get("text") or "") for span in spans).strip()
            text = re.sub(r"\s+", " ", text)
            if not heading_re.match(text):
                continue
            x0 = min(float(span["bbox"][0]) for span in spans)
            y0 = min(float(span["bbox"][1]) for span in spans)
            x1 = max(float(span["bbox"][2]) for span in spans)
            y1 = max(float(span["bbox"][3]) for span in spans)
            found.append({"text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1})
    if found:
        return found

    # Fallback: cluster words whose tops are within 2pt.
    words = sorted(page.get_text("words") or [], key=lambda item: (float(item[1]), float(item[0])))
    clusters: list[list[tuple]] = []
    for word in words:
        if clusters and abs(float(word[1]) - float(clusters[-1][0][1])) <= 2.0:
            clusters[-1].append(word)
        else:
            clusters.append([word])
    for group in clusters:
        group.sort(key=lambda item: float(item[0]))
        text = re.sub(r"\s+", " ", " ".join(str(item[4]) for item in group)).strip()
        if not heading_re.match(text):
            continue
        found.append(
            {
                "text": text,
                "x0": float(group[0][0]),
                "y0": min(float(item[1]) for item in group),
                "x1": float(group[-1][2]),
                "y1": max(float(item[3]) for item in group),
            }
        )
    return found


def _underline_shape_rects(page: fitz.Page) -> list[fitz.Rect]:
    """Collect short heading underlines — both stroked lines and filled thin rects.

    OPS / Valuation Pkg PDFs often draw ACTION underlines as filled rectangles
    (not ``l`` strokes), so line-only detection misses them.
    """
    boxes: list[fitz.Rect] = []
    for drawing in page.get_drawings():
        stroke = drawing.get("color")
        fill = drawing.get("fill")
        white = {(1, 1, 1), (1.0, 1.0, 1.0)}
        if stroke in white and (fill is None or fill in white):
            continue
        for item in drawing.get("items") or []:
            if not item:
                continue
            if item[0] == "l" and len(item) >= 3:
                if stroke in white:
                    continue
                start, end = fitz.Point(item[1]), fitz.Point(item[2])
                if abs(start.y - end.y) > 1.5:
                    continue
                width = abs(end.x - start.x)
                if width < 20 or width >= page.rect.width * 0.7:
                    continue
                left, right = sorted((start.x, end.x))
                y = start.y
                boxes.append(fitz.Rect(left, y - 0.75, right, y + 0.75))
            elif item[0] == "re" and len(item) >= 2:
                # Filled thin bars used as underlines in source/expected packages.
                if fill in white or fill is None:
                    continue
                rect = fitz.Rect(item[1])
                if rect.height > 3.5 or rect.height < 0.2:
                    continue
                if rect.width < 20 or rect.width >= page.rect.width * 0.7:
                    continue
                boxes.append(fitz.Rect(rect))
    return boxes


def _short_rules_near_heading(page: fitz.Page, top: float, bottom: float, x0: float, x1: float) -> list[fitz.Rect]:
    """Short horizontal rules near a heading, including ones that are too long or too short."""
    boxes: list[fitz.Rect] = []
    for rect in _underline_shape_rects(page):
        y = (rect.y0 + rect.y1) / 2.0
        if y < top - 1.0 or y > bottom + 4.0:
            continue
        if rect.x1 < x0 - 8 or rect.x0 > x1 + 40:
            continue
        boxes.append(fitz.Rect(rect.x0 - 1, rect.y0 - 0.5, rect.x1 + 1, rect.y1 + 0.5))
    return boxes


def _redraw_action_rules(
    page: fitz.Page,
    *,
    only_failure: bool = False,
    invent: bool = False,
) -> None:
    """Put Action Required underlines back after packing, matching each phrase width.

    Purpose:
        Restore or correct underlines after packing. By default does not invent
        plain ACTION / NO IMMEDIATE underlines when the source had none.

    Args:
        page: One PDF page.
        only_failure: When True, only IMMEDIATE/ATTENTION headings get underlines.
        invent: When True, draw missing plain ACTION / NO IMMEDIATE underlines.
            Default False keeps source-faithful all-clear pages (often no rules).

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _redraw_action_rules(page) returns None.

    Side effects:
        Changes drawings on the page.
    """
    headings = _action_heading_lines(page)
    if not headings:
        return
    # Replace underlines that sit *below* the heading ink. Do not redact rules that
    # cut through the glyphs — that deletes ACTION / NO IMMEDIATE text.
    wipe: list[fitz.Rect] = []
    planned: list[tuple[float, float, float, tuple[float, float, float]]] = []
    for heading in headings:
        text = heading["text"]
        x0 = float(heading["x0"])
        x1 = float(heading["x1"])
        top = float(heading["y0"])
        bottom = float(heading["y1"])
        # OPS places the bar at the bottom of the glyph bbox (slightly overlapping).
        upper = text.upper()
        is_failure = upper.startswith("IMMEDIATE ACTION") or upper.startswith("ATTENTION REQUIRED")
        thickness = 1.0 if upper.startswith("NO IMMEDIATE") else 1.4
        y = bottom - thickness
        if only_failure and not is_failure:
            continue
        near = _short_rules_near_heading(page, bottom - 3.0, bottom + 2.5, x0, x1)
        if not is_failure and not invent and not near:
            # Source-faithful: do not invent underlines on all-clear pages.
            continue
        # Only rules at/below the baseline band — never the ink itself.
        wipe.extend(near)
        color = (0, 0.45, 0.15) if upper.startswith("NO IMMEDIATE") else (0, 0, 0)
        if upper.startswith("IMMEDIATE ACTION"):
            color = (0.8, 0, 0)
        planned.append((x0, x1, y, color, thickness))
    # White-cover leftover rules. Never apply_redactions here — a rule that still
    # clips glyph ink would delete ACTION / NO IMMEDIATE characters.
    _cover_or_redact_rules(page, wipe, redact=False)
    for x0, x1, y, color, thickness in planned:
        # OPS packages use a thin filled bar (not only a stroked line).
        page.draw_rect(
            fitz.Rect(x0, y, x1, y + thickness),
            color=color,
            fill=color,
            width=0,
            overlay=True,
        )


def _has_horizontal_rule(page: fitz.Page, y: float, x0: float, x1: float) -> bool:
    """Check whether a horizontal vector rule already underlines this heading."""
    for rect in _underline_shape_rects(page):
        mid = (rect.y0 + rect.y1) / 2.0
        if abs(mid - y) > 4:
            continue
        if rect.x1 >= x0 - 2 and rect.x0 <= x1 + 2:
            return True
    return False


def _cover_rules_through_band(
    page: fitz.Page,
    top: float,
    bottom: float,
    x0: float,
    x1: float,
) -> None:
    """White-out short horizontal rules that cut through a heading band."""
    for rect in _underline_shape_rects(page):
        mid = (rect.y0 + rect.y1) / 2.0
        if mid < top - 0.5 or mid > bottom + 0.5:
            continue
        if rect.x1 < x0 - 4 or rect.x0 > x1 + 4:
            continue
        page.draw_rect(
            fitz.Rect(rect.x0 - 1, rect.y0 - 1, rect.x1 + 1, rect.y1 + 1),
            color=(1, 1, 1),
            fill=(1, 1, 1),
            width=0,
            overlay=True,
        )


def _drop_empty_pages(doc: fitz.Document) -> None:
    """Drop empty pages.

    Purpose:
        Drop empty pages.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _drop_empty_pages(doc) returns None.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    drop: list[int] = []
    for page in doc:
        if page.number == 0:
            continue
        text = page.get_text("text") or ""
        if _is_recap_text(text):
            continue
        # A scanned report has a logo and no text layer. A cleared page with a leftover "i" does not.
        if page.get_images() and _is_empty_text(text):
            continue
        if (
            _is_header_only_page(page)
            or _is_empty_text(text)
            or _footer_only(page)
            or _is_noise_text(text)
        ):
            drop.append(page.number)
    for number in reversed(drop):
        if doc.page_count <= 1:
            break
        doc.delete_page(number)


def _drop_removed_failure_pages(doc: fitz.Document, remove_ids: set[str]) -> bool:
    """Delete whole 415 failure-info / related sample-letter pages when rule L is remove.

    Heading redaction alone can miss wrapped titles and leave the page between
    Action Required and Year End Recap.
    """
    if "L" not in remove_ids:
        return False
    drop: list[int] = []
    for page in doc:
        text = page.get_text("text") or ""
        if _is_415_failure_info_page(text) or _is_415_sample_letter_page(text):
            drop.append(page.number)
    if not drop:
        return False
    for number in reversed(drop):
        if doc.page_count <= 1:
            break
        doc.delete_page(number)
    return True


def _is_415_failure_info_page(text: str) -> bool:
    """True when this page is the Annual Additions (IRC 415) Test Failure Information notice."""
    raw = text or ""
    if not raw.strip():
        return False
    # Titles often wrap across lines; squash the top of the page before matching.
    head = re.sub(r"\s+", " ", raw[:1200]).strip()
    if re.search(
        r"annual additions\s*\(?\s*irc\s*415\s*\)?\s*test failure information|"
        r"415\s*\(?\s*c\s*\)?\s*.{0,60}test failure information|"
        r"annual additions.{0,60}test failure information",
        head,
        re.I,
    ):
        # Do not treat the Year End Recap / Important Information overview as this notice.
        if re.search(r"^\s*year[- ]end recap\b|^\s*important information\b", head, re.I):
            return False
        return True
    return False


def drop_415_failure_pages_unless_failed(doc: fitz.Document, fail_415: bool | None) -> list[str]:
    """Remove 415 failure-info / letter pages unless 415 actually failed.

    Called from the orchestrator so the page cannot remain between Action Required
    and Year End Recap when fail_415 is not True — even if rule L heading match missed.
    """
    if fail_415 is True:
        return []
    drop: list[int] = []
    for page in doc:
        text = page.get_text("text") or ""
        # Do not skip page 0 — some packets place this notice early, and tests use a
        # single-page doc. Cover letters do not match the 415 failure-info title.
        if _is_415_failure_info_page(text) or _is_415_sample_letter_page(text):
            drop.append(page.number)
    if not drop:
        return []
    for number in reversed(drop):
        if doc.page_count <= 1:
            break
        doc.delete_page(number)
    return [f"Removed Annual Additions (IRC 415) Test Failure Information page(s) because fail_415={fail_415!r}"]


def _is_415_sample_letter_page(text: str) -> bool:
    """True for the SAMPLE/DRAFT 415 participant letter page."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return False
    first = lines[0]
    head = " ".join(lines[:10])
    if not re.match(r"^sample/draft\b", first, re.I):
        # Some packets put the exceeded heading first.
        return bool(re.search(r"annual additions\s*\(irc\s*415\)\s*limit has been exceeded", first, re.I))
    return bool(re.search(r"annual additions|irc\s*415|\b415\b", head, re.I))


_PAGE_NUMBER = re.compile(r"^(?:page\s*)?\d{1,3}$", re.I)


def _is_header_only_page(page: fitz.Page) -> bool:
    """A heading with no paragraph left is an empty page.

    Purpose:
        A heading with no paragraph left is an empty page.

    Args:
        page: One PDF page.

    Returns:
        bool.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _is_header_only_page(page) returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    text = page.get_text("text") or ""
    if _is_recap_text(text):
        return False
    has_heading = bool(
        _REPORT_TITLE.search(text) or re.search(r"(?m)^\s*action required\s*$", text, re.I)
    )
    if not has_heading:
        return False
    if re.search(
        r"immediate action required\s*-|attention required|no immediate action|excess return|failed compliance",
        text,
        re.I,
    ):
        return False
    return len(re.findall(r"[A-Za-z0-9$]+", text)) <= 45


def _is_empty_text(text: str) -> bool:
    """Is empty text.

    Purpose:
        Is empty text.

    Args:
        text: Text taken from a page or a file.

    Returns:
        bool.

    Raises:
        None.

    Example:
        _is_empty_text("text") returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    cleaned = re.sub(r"\s+", " ", text).strip()
    return not cleaned or bool(_TITLE_ONLY.match(cleaned) or _PAGE_NUMBER.match(cleaned))


def _footer_only(page: fitz.Page) -> bool:
    """A page number at the bottom is not a paragraph. The page is blank.

    Purpose:
        A page number at the bottom is not a paragraph. The page is blank.

    Args:
        page: One PDF page.

    Returns:
        bool.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _footer_only(page) returns bool.

    Side effects:
        None. This function only reads data and returns a value.
    """
    words = page.get_text("words") or []
    if not words:
        return True
    limit = page.rect.y1 - 48
    return all(word[1] >= limit for word in words)


def fill_qnec_placeholders(
    doc: fitz.Document,
    profile: PlanProfile,
    marks: list[dict] | None = None,
) -> list[str]:
    """Write QNEC amounts on the current-year Excess Return Notice.

    Purpose:
        Write QNEC amounts on the current-year Excess Return Notice. The first ADP/ACP amount is the ADP QNEC plus the ACP QNEC. The ADP and ACP lines follow it.

    Args:
        doc: Open PDF. Must not be closed.
        profile: Plan profile collected from the PDF, Excel, and summary.
        marks: Highlight rectangles already collected for the PDF.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        fill_qnec_placeholders(doc, profile, []) returns list[str].

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    filled: list[str] = []
    flags = package_flags(profile.plan_type)
    acp_only_notice = bool(flags.get("acp_notice_amount"))
    both = [value for value in (profile.adp_qnec, profile.acp_qnec) if value is not None]
    total = round(sum(both), 2) if both else profile.total_qnec
    # 403(b) Excess Return notice uses ACP QNEC only (“ACP test is $…”).
    amounts = {
        "total": None if acp_only_notice else total,
        "adp": None if acp_only_notice else profile.adp_qnec,
        "acp": profile.acp_qnec,
        "deferral": profile.deferral_refund,
        "match": profile.match_refund,
        "acp-notice": profile.acp_qnec if acp_only_notice else None,
    }
    for page in doc:
        if "$X,XXX,XXX.XX" not in (page.get_text("text") or ""):
            continue
        for kind, value in _fill_notice_amounts(page, amounts):
            money = _money(value) if value is not None else ""
            if value is not None:
                filled.append(f"{kind}={money}")
                for hit in page.search_for(money):
                    add_mark(marks, page.number, hit, "Filled amount")
    return filled


_NOTICE_LABELS = {
    "total": re.compile(r"adp/acp test is$"),
    "adp": re.compile(r"(?:the\s+)?adp qnec is$"),
    "acp": re.compile(r"(?:the\s+)?acp qnec is$"),
    "match": re.compile(r"(?:and\s+)?match contribution of$"),
    "deferral": re.compile(r"(?:excess aggregated\s+)?deferral contribution of$"),
    "acp-notice": re.compile(r"(?<!adp/)(?:the\s+)?acp test is$"),
}


def _fill_notice_amounts(page: fitz.Page, amounts: dict[str, float | None]) -> list[tuple[str, float | None]]:
    """Replace each $X,XXX,XXX.XX in place. A missing amount takes its label with it.

    Purpose:
        Replace each $X,XXX,XXX.XX in place. A missing amount takes its label with it.
        All placeholders on the page are collected first, then redacted together, so filling
        one amount cannot wipe another placeholder on the same line.

    Args:
        page: One PDF page.
        amounts: Amounts. Type: dict[str, float | None].

    Returns:
        a list of tuple[str, float | None].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _fill_notice_amounts(page, {"total": 1.0}) returns a list of tuple[str, float | None].

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    hits = sorted(page.search_for("$X,XXX,XXX.XX"), key=lambda item: (item.y0, item.x0))
    if not hits:
        return []
    words = page.get_text("words") or []
    jobs: list[dict] = []
    for hit in hits:
        kind, label_words, token = _notice_placeholder(words, hit)
        value = amounts.get(kind) if kind else None
        token_rect = fitz.Rect(token[:4]) if token else fitz.Rect(hit)
        if value is None:
            rects = [_tighten_qnec_rect(fitz.Rect(word[:4])) for word in label_words] or [
                _tighten_qnec_rect(token_rect)
            ]
            jobs.append({"kind": kind or "amount", "value": None, "rects": rects, "insert": None})
            continue
        money = _money(value)
        if token and str(token[4]).endswith("."):
            money += "."
        fontsize = _qnec_fontsize(token_rect)
        baseline = float(token[3]) - max(0.8, (token_rect.y1 - token_rect.y0) * 0.12) if token else hit.y1 - 1
        jobs.append(
            {
                "kind": kind or "amount",
                "value": value,
                "rects": [_tighten_qnec_rect(token_rect)],
                "insert": (float(token_rect.x0), baseline, money, fontsize),
            }
        )

    for job in jobs:
        for rect in job["rects"]:
            page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions(images=0, graphics=0)
    done: list[tuple[str, float | None]] = []
    for job in jobs:
        insert = job["insert"]
        if insert is not None:
            x, y, money, fontsize = insert
            page.insert_text(
                (x, y),
                money,
                fontsize=fontsize,
                fontname="helv",
                color=(0, 0, 0),
                overlay=True,
            )
        done.append((job["kind"], job["value"]))
    return done


def _tighten_qnec_rect(rect: fitz.Rect) -> fitz.Rect:
    """Keep QNEC redaction on the placeholder ink so neighbor text/lines survive."""
    return fitz.Rect(rect.x0 - 0.4, rect.y0 + 0.2, rect.x1 + 0.4, rect.y1 - 0.2)


def _qnec_fontsize(rect: fitz.Rect) -> float:
    """Estimate notice body font size from the placeholder box height."""
    height = max(1.0, float(rect.y1 - rect.y0))
    return max(8.0, min(11.0, height * 0.72))


def _notice_placeholder(words: list[tuple], hit: fitz.Rect) -> tuple[str, list[tuple], tuple | None]:
    """Notice placeholder.

    Purpose:
        Notice placeholder.

    Args:
        words: Words. Type: list[tuple].
        hit: Hit. Type: fitz.Rect.

    Returns:
        a tuple[str, list[tuple], tuple | None].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _notice_placeholder([], hit) returns a tuple[str, list[tuple], tuple | None].

    Side effects:
        None. This function only reads data and returns a value.
    """
    ordered = sorted(words, key=lambda word: (word[1], word[0]))
    index = None
    best_overlap = 0.0
    for pos, word in enumerate(ordered):
        word_rect = fitz.Rect(word[:4])
        overlap = word_rect & hit
        if overlap.is_empty:
            continue
        area = float(overlap.width * overlap.height)
        if area > best_overlap:
            best_overlap = area
            index = pos
    if index is None:
        index = next(
            (
                pos
                for pos, word in enumerate(ordered)
                if abs(word[0] - hit.x0) < 4 and abs(word[1] - hit.y0) < 4
            ),
            None,
        )
    if index is None:
        return "", [], None
    token = ordered[index]
    prior = ordered[:index]
    best: tuple[str, list[tuple]] | None = None
    for size in range(1, min(6, len(prior)) + 1):
        chunk = prior[-size:]
        if size > 1 and str(chunk[0][4]).endswith("."):
            break
        tail = " ".join(str(word[4]) for word in chunk).lower()
        for kind, pattern in _NOTICE_LABELS.items():
            if pattern.search(tail):
                best = (kind, chunk)
                break
        if best is not None:
            break
    if best is None:
        return "", [token], token
    kind, chunk = best
    chosen = list(chunk) + [token]
    if index + 1 < len(ordered) and str(ordered[index + 1][4]) in {".", ","}:
        chosen.append(ordered[index + 1])
    return kind, chosen, token


def _money(value: float) -> str:
    """Money.

    Purpose:
        Money.

    Args:
        value: Value. Type: float.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _money(1.0) returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return f"${value:,.2f}"


def _block_specs(plan_type: str | None = None) -> list[dict]:
    """Input: plan type. Calls paragraphs_for. Output: Action Required, notice, letter, and Excess Summary headings.

    Purpose:
        Input: plan type. Calls paragraphs_for. Output: Action Required, notice, letter, and Excess Summary headings.

    Args:
        plan_type: Plan type: "401k", "403b", "457", or empty.

    Returns:
        list[dict].

    Raises:
        None.

    Example:
        _block_specs("text") returns list[dict].

    Side effects:
        None. This function only reads data and returns a value.
    """
    data = paragraphs_for(plan_type)
    specs = list(data.get("action_required_headings") or [])
    specs.extend(data.get("notices") or [])
    specs.extend(data.get("sample_letters") or [])
    specs.extend(data.get("excess_summary") or [])
    specs.sort(key=lambda item: -len(str(item.get("heading") or "")))
    return specs


_ADP_NHCE = re.compile(
    r"ADP\s+for\s+the\s+\d+\s+NHCE\(?s\)?\s+is\s+(\d+(?:\.\d+)?)\s*%",
    re.I,
)


def apply_recap_bullets(
    doc: fitz.Document,
    decisions: list[RuleDecision],
    plan_type: str | None = None,
) -> list[str]:
    """TEST23 §I: drop unused Important Information bullets and pack the page.

    Purpose:
        TEST23 §I: drop unused Important Information bullets and pack the page.

    Args:
        doc: Open PDF. Must not be closed.
        decisions: Keep, remove, or skipped results from the rules.
        plan_type: Plan type: "401k", "403b", "457", or empty.

    Returns:
        list[str].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        apply_recap_bullets(doc, [], "text") returns list[str].

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    specs = _recap_specs(plan_type)
    if not specs:
        return []
    remove_ids = {item.rule_id for item in decisions if item.action == "remove"}
    keep_ids = {item.rule_id for item in decisions if item.action == "keep"}
    wanted_exclusive = _preferred_exclusive_recap(keep_ids)
    nhce = _adp_nhce_percent(doc)
    removed: list[str] = []
    for page in doc:
        original = page.get_text("text") or ""
        if not _is_recap_text(original):
            continue
        header, bullets = _split_recap(original)
        kept: list[str] = []
        dropped: list[str] = []
        # Wording replacement (exclusive swap / rate fill / inject) — not space tidy.
        wording_changed = False
        have_exclusive = False
        # (old_source_bullet, new_exclusive_text) when Future-HCE wording is swapped.
        exclusive_swaps: list[tuple[str, str]] = []
        for bullet in bullets:
            # Normalize only for rule matching; keep source spacing/quotes on kept text.
            normalized = _normalize_recap_bullet_spaces(bullet)
            spec = _matching_recap(normalized, specs)
            rule_id = str(spec["id"]) if spec else None
            exclusive_like = rule_id in _EXCLUSIVE_RECAP or _looks_like_exclusive_hce(normalized)
            if spec is None and re.search(r"(?:^|\s)%(?:\s|$)", normalized):
                dropped.append(bullet)
                continue
            if rule_id and rule_id in remove_ids:
                if rule_id not in removed:
                    removed.append(rule_id)
                # Source packages often keep PRIOR/CURRENT wording even for Safe Harbor.
                # Swap the removed exclusive bullet into the kept exclusive wording.
                if (
                    exclusive_like
                    and wanted_exclusive
                    and wanted_exclusive not in remove_ids
                    and not have_exclusive
                ):
                    swapped = _canonical_exclusive_recap(wanted_exclusive, bullet)
                    if wanted_exclusive == "Y2":
                        swapped = _fill_prior_rates(swapped, nhce)
                    kept.append(swapped)
                    exclusive_swaps.append((bullet, swapped))
                    have_exclusive = True
                    wording_changed = True
                dropped.append(bullet)
                continue
            if (
                exclusive_like
                and wanted_exclusive
                and wanted_exclusive not in remove_ids
                and rule_id != wanted_exclusive
            ):
                # Clipped source text may not hit YAML matches; still replace with the
                # kept exclusive wording so blank "%"/prior-year leftovers disappear.
                if not have_exclusive:
                    swapped = _canonical_exclusive_recap(wanted_exclusive, bullet)
                    if wanted_exclusive == "Y2":
                        swapped = _fill_prior_rates(swapped, nhce)
                    kept.append(swapped)
                    exclusive_swaps.append((bullet, swapped))
                    have_exclusive = True
                    wording_changed = True
                if rule_id and rule_id not in removed:
                    removed.append(rule_id)
                dropped.append(bullet)
                continue
            if exclusive_like:
                if have_exclusive:
                    dropped.append(bullet)
                    continue
                have_exclusive = True
            if rule_id == "Y2":
                filled = _fill_prior_rates(bullet, nhce)
                if filled != bullet:
                    wording_changed = True
                    exclusive_swaps.append((bullet, filled))
                    bullet = filled
            kept.append(bullet)
        if wanted_exclusive and wanted_exclusive not in remove_ids and not have_exclusive:
            # Exclusive keep-rule matched, but the page never had Future-HCE wording.
            sample = next((item for item in bullets if item), "")
            injected = _canonical_exclusive_recap(wanted_exclusive, sample)
            if wanted_exclusive == "Y2":
                injected = _fill_prior_rates(injected, nhce)
            kept.insert(0, injected)
            wording_changed = True
        # No content change → leave source Recap alone, unless clipped fragments
        # remain from a prior partial keep/remove (Kaagaz expects a clean page).
        if not dropped and not wording_changed and not _recap_has_clip_fragments(page):
            continue
        # Prefer in-place edits: pack drops and/or rewrite exclusive bands without
        # wiping the page (full rebuild invents borders and rewraps catch-up quotes).
        if not _recap_has_clip_fragments(page) and (
            exclusive_swaps
            or (dropped and not wording_changed)
        ):
            other_drops = [
                item
                for item in dropped
                if not any(
                    _normalize_recap_bullet_spaces(item).lower()[:48]
                    == _normalize_recap_bullet_spaces(old).lower()[:48]
                    for old, _new in exclusive_swaps
                )
            ]
            if (exclusive_swaps or other_drops) and _pack_recap_edits_inplace(
                page, other_drops, exclusive_swaps
            ):
                continue
            if (
                dropped
                and not wording_changed
                and not exclusive_swaps
                and _pack_recap_drops_inplace(page, dropped)
            ):
                continue
        header_lines = [
            line.strip()
            for line in header.splitlines()
            if _is_recap_header_line(line.strip())
        ]
        if not header_lines:
            header_lines = ["Important Information"]
        elif not any(re.fullmatch(r"Important Information", line, re.I) for line in header_lines):
            header_lines.append("Important Information")
        kept = [
            _clean_recap_bullet_text(_bullet)
            for _bullet in kept
            if _is_viable_recap_bullet(_bullet)
        ]
        kept = _merge_universal_availability_bullets(kept)
        # Fallback rebuild when wording changed or in-place pack could not run.
        _wipe_page_contents(page)
        from services.package_builder import write_recap_page

        number = _recap_page_number(original)
        write_recap_page(page, header_lines, kept, number=number, plan_type=plan_type)
    return removed


def _recap_body_top(page: fitz.Page) -> float:
    """Y just below 'Important Information' where body bullets begin."""
    top = 120.0
    for block in _text_blocks(page):
        text = " ".join(span["text"] for span in block["spans"]).strip()
        if re.fullmatch(r"Important Information", text, re.I):
            top = max(top, float(block["bbox"].y1) + 4.0)
    return top


def _recap_bullet_bands(page: fitz.Page) -> list[tuple[float, float, str]]:
    """Return ``(y0, y1, start_text)`` for each Important Information bullet band."""
    body_top = _recap_body_top(page)
    footer = page.rect.y1 - 48.0
    starts: list[tuple[float, str]] = []
    for block in _text_blocks(page):
        if float(block["bbox"].y0) < body_top - 1:
            continue
        if float(block["bbox"].y0) > footer:
            continue
        text = " ".join(span["text"] for span in block["spans"]).strip()
        if not text or re.fullmatch(r"[\u2022•\u00b7\u25cf\u25e6\u2219\uf0b7╖■□▪▫*\-·●]+", text):
            continue
        if float(block["bbox"].x0) > 110:
            continue
        clean = _strip_recap_mark(text)
        if _recap_paragraph_start(clean) or re.fullmatch(r"UNIVERSAL AVAILABILITY RULE", clean, re.I):
            starts.append((float(block["bbox"].y0), clean))
    if not starts:
        return []
    starts.sort(key=lambda item: item[0])
    # Merge UA title with the following body start into one band.
    merged_starts: list[tuple[float, str]] = []
    index = 0
    while index < len(starts):
        y0, text = starts[index]
        if re.fullmatch(r"UNIVERSAL AVAILABILITY RULE", text, re.I) and index + 1 < len(starts):
            merged_starts.append((y0, f"UNIVERSAL AVAILABILITY RULE {starts[index + 1][1]}"))
            index += 2
            continue
        merged_starts.append((y0, text))
        index += 1
    bands: list[tuple[float, float, str]] = []
    for index, (y0, text) in enumerate(merged_starts):
        y1 = merged_starts[index + 1][0] - 1.0 if index + 1 < len(merged_starts) else footer
        # Include a little padding so bullet discs above the first line are covered.
        bands.append((max(body_top, y0 - 4.0), max(y0 + 8.0, y1), text))
    return bands


def _recap_band_matches(start: str, candidate: str) -> bool:
    """True when a Recap band start matches a dropped/swapped bullet prefix."""
    start_norm = _normalize_recap_bullet_spaces(start).lower()[:72]
    cand_norm = _normalize_recap_bullet_spaces(candidate).lower()[:72]
    if not start_norm or not cand_norm:
        return False
    return start_norm.startswith(cand_norm[:48]) or cand_norm.startswith(start_norm[:48])


def _snapshot_recap_band(
    page: fitz.Page, y0: float, y1: float
) -> tuple[list[dict], list[fitz.Rect]] | None:
    """Capture source spans and bullet discs for one Recap band."""
    spans: list[dict] = []
    for block in _text_blocks(page):
        mid = (float(block["bbox"].y0) + float(block["bbox"].y1)) / 2.0
        if mid < y0 - 0.5 or mid > y1 + 0.5:
            continue
        for span in block["spans"]:
            spans.append(dict(span))
    discs: list[fitz.Rect] = []
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        if fill not in {(0, 0, 0), (0.0, 0.0, 0.0)}:
            continue
        rect = fitz.Rect(drawing.get("rect") or (0, 0, 0, 0))
        if not (2.5 <= rect.width <= 6 and 2.5 <= rect.height <= 6 and 50 <= rect.x0 <= 110):
            continue
        mid = (rect.y0 + rect.y1) / 2.0
        if y0 - 0.5 <= mid <= y1 + 0.5:
            discs.append(fitz.Rect(rect))
    if not spans:
        return None
    return spans, discs


def _pack_recap_edits_inplace(
    page: fitz.Page,
    dropped: list[str],
    replacements: list[tuple[str, str]],
) -> bool:
    """Drop and/or rewrite Recap bands while replaying other source glyphs.

    Exclusive Future-HCE swaps rewrite only that band (ASCII Helvetica text);
    every other survivor keeps its original wrap, fonts, and quotes. Avoids the
    full-page wipe that invents header borders and corrupts catch-up glyphs.
    """
    if not dropped and not replacements:
        return False
    bands = _recap_bullet_bands(page)
    if len(bands) < 1:
        return False

    from services.package_builder import (
        RECAP_BODY_LEADING,
        RECAP_BODY_SIZE,
        RECAP_BODY_X,
        RECAP_BULLET_X,
        RECAP_HEADER_RULE_X1,
        _draw_recap_bullet_mark,
        _write_recap_bullet_body,
    )

    # Classify each band: drop | replace(new_text) | keep
    plan: list[tuple[str, float, float, str | None]] = []
    used_replace = 0
    for y0, y1, start in bands:
        matched_replace = next(
            (
                new_text
                for old_text, new_text in replacements
                if _recap_band_matches(start, old_text)
            ),
            None,
        )
        if matched_replace is not None:
            plan.append(("replace", y0, y1, matched_replace))
            used_replace += 1
            continue
        if any(_recap_band_matches(start, item) for item in dropped if item):
            plan.append(("drop", y0, y1, None))
            continue
        plan.append(("keep", y0, y1, None))

    survivors = [item for item in plan if item[0] != "drop"]
    if not survivors:
        return False
    if used_replace == 0 and not any(item[0] == "drop" for item in plan):
        return False
    if replacements and used_replace == 0:
        return False

    body_top = _recap_body_top(page)
    snapshots: list[tuple[list[dict], list[fitz.Rect]] | None] = []
    for kind, y0, y1, _payload in survivors:
        if kind == "keep":
            snap = _snapshot_recap_band(page, y0, y1)
            if snap is None:
                return False
            snapshots.append(snap)
        else:
            snapshots.append(None)

    source_gaps: list[float] = []
    for index in range(len(bands) - 1):
        source_gaps.append(max(6.0, bands[index + 1][0] - bands[index][1]))
    default_gap = sorted(source_gaps)[len(source_gaps) // 2] if source_gaps else 10.0

    body_rect = fitz.Rect(36, body_top - 2, page.rect.x1 - 28, page.rect.y1 - 36)
    page.add_redact_annot(body_rect, fill=(1, 1, 1))
    page.apply_redactions(images=0, graphics=1)
    page.draw_rect(body_rect, color=(1, 1, 1), fill=(1, 1, 1), width=0, overlay=True)

    hang_x = RECAP_BODY_X
    width = max(360.0, RECAP_HEADER_RULE_X1 - hang_x)
    size = RECAP_BODY_SIZE
    leading = RECAP_BODY_LEADING
    bullet_prefix = re.compile(r"^(?:[\u2022•\u00b7\u25cf\u25e6\u2219\uf0b7╖■□▪▫*?\-]\s*)+")

    cursor = body_top + 6.0
    for index, (kind, y0, y1, payload) in enumerate(survivors):
        if kind == "replace":
            body = bullet_prefix.sub("", (payload or "").strip()).strip()
            body = _ascii_pdf_text(body)
            _draw_recap_bullet_mark(page, RECAP_BULLET_X, cursor, body_size=size)
            end_y = _write_recap_bullet_body(
                page, body, hang_x, cursor, size, leading, width
            )
            cursor = end_y + default_gap
            continue
        spans, discs = snapshots[index] or ([], [])
        dy = y0 - cursor
        content_bottom = y0 + 12.0
        for span in spans:
            origin = span["origin"]
            ox = float(origin.x if hasattr(origin, "x") else origin[0])
            oy = float(origin.y if hasattr(origin, "y") else origin[1])
            span_size = float(span.get("size") or 8.0)
            content_bottom = max(content_bottom, oy + span_size * 0.25)
            _write_span(page, {**span, "origin": fitz.Point(ox, oy - dy)}, 0)
        for rect in discs:
            shifted = fitz.Rect(rect.x0, rect.y0 - dy, rect.x1, rect.y1 - dy)
            page.draw_oval(shifted, color=(0, 0, 0), fill=(0, 0, 0), width=0)
            content_bottom = max(content_bottom, rect.y1)
        band_height = max(12.0, content_bottom - y0)
        cursor = cursor + band_height + default_gap
    return True


def _ascii_pdf_text(value: str) -> str:
    """Map smart quotes/dashes so Helvetica does not substitute middle-dots."""
    text = str(value or "")
    return (
        text.replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("╖", '"')
        .replace("ô", '"')
        .replace("ö", '"')
    )


def _pack_recap_drops_inplace(page: fitz.Page, dropped: list[str]) -> bool:
    """Remove dropped Recap bullets and restack kept source bands — no rewrap.

    Each kept bullet band is moved as a unit (same internal line breaks, x, and
    fonts as the upload). Bands are packed under Important Information with the
    source inter-band gap preserved between survivors.
    """
    if not dropped:
        return False
    return _pack_recap_edits_inplace(page, dropped, [])


def _wipe_page_contents(page: fitz.Page) -> None:
    """Hard-clear a page before rewriting Recap content (no leftover glyph crumbs)."""
    page.add_redact_annot(page.rect, fill=(1, 1, 1))
    page.apply_redactions(images=0, graphics=2)
    # Some source streams keep text after one redact pass — blank then clean.
    page.draw_rect(page.rect, color=(1, 1, 1), fill=(1, 1, 1), width=0)
    try:
        page.clean_contents()
    except Exception:
        pass
    leftover = (page.get_text("text") or "").strip()
    if leftover:
        boxes = [fitz.Rect(block["bbox"]) for block in _text_blocks(page)]
        if boxes:
            _apply_redact_boxes(page, boxes, cover=True)
        try:
            page.clean_contents()
        except Exception:
            pass


def _redact_recap_bullets_in_place(page: fitz.Page, dropped: list[str]) -> bool:
    """White out dropped Recap bullets without rewriting remaining source text."""
    boxes: list[fitz.Rect] = []
    for raw in dropped:
        clean = re.sub(r"\s+", " ", _strip_recap_bullet_prefix(raw)).strip()
        if len(clean) < 20:
            continue
        words = clean.split()
        # Search overlapping chunks so wrapped source lines still match.
        for index in range(0, max(1, len(words) - 4), 5):
            chunk = " ".join(words[index : index + 8]).strip()
            if len(chunk) < 18:
                continue
            try:
                hits = page.search_for(chunk)
            except Exception:
                hits = []
            boxes.extend(fitz.Rect(hit) for hit in hits)
        # Fallback: distinctive head of the paragraph.
        head = " ".join(words[:10]).strip()
        if len(head) >= 18:
            try:
                boxes.extend(fitz.Rect(hit) for hit in page.search_for(head))
            except Exception:
                pass
    if not boxes:
        return False
    # Expand hits slightly and clear any bullet glyph sitting just left of them.
    expanded: list[fitz.Rect] = []
    for box in boxes:
        grown = fitz.Rect(box.x0 - 18, box.y0 - 1, box.x1 + 2, box.y1 + 1)
        expanded.append(grown & page.rect)
    for box in expanded:
        page.add_redact_annot(box, fill=(1, 1, 1))
    page.apply_redactions(images=0, graphics=0)
    return True


def _strip_recap_bullet_prefix(text: str) -> str:
    """Remove a leading bullet glyph from a recap bullet string."""
    return re.sub(
        r"^(?:[\u2022•\u00b7\u25cf\u25e6\u2219\uf0b7╖■□▪▫*\-·●]+)\s*",
        "",
        (text or "").strip(),
    ).strip()


def _is_ua_exclusion_bullet(text: str) -> bool:
    """True when a bullet is one of the nested Universal Availability exclusions."""
    clean = _strip_recap_bullet_prefix(text)
    return bool(
        re.match(
            r"^(?:Employees who normally work less than 20 hours|"
            r"Students performing services at a school|"
            r"Non-resident aliens with no U\.S\. source income|"
            r"Employees who are eligible to make elective deferrals|"
            r"Employees not able to defer \$200)",
            clean,
            re.I,
        )
    )


def _is_ua_followon_bullet(text: str) -> bool:
    """True for the UA closing sponsor/service-provider paragraph."""
    clean = _strip_recap_bullet_prefix(text)
    return clean.lower().startswith("if you sponsor a qualified retirement plan")


def _merge_universal_availability_bullets(bullets: list[str]) -> list[str]:
    """Join UA title/body/exclusion/follow-on bullets into one block for nested rewrite."""
    from services.package_builder import _is_ua_recap_body

    def _absorb_tail(parts: list[str], index: int) -> int:
        while index < len(bullets) and _is_ua_exclusion_bullet(bullets[index]):
            parts.append(_strip_recap_bullet_prefix(bullets[index]))
            index += 1
        if index < len(bullets) and _is_ua_followon_bullet(bullets[index]):
            parts.append(_strip_recap_bullet_prefix(bullets[index]))
            index += 1
        return index

    merged: list[str] = []
    index = 0
    while index < len(bullets):
        current = (bullets[index] or "").strip()
        clean = _strip_recap_bullet_prefix(current)
        title_only = bool(re.fullmatch(r"UNIVERSAL AVAILABILITY RULE", clean, re.I))
        if title_only or (clean.upper().startswith("UNIVERSAL AVAILABILITY RULE") and len(clean) < 40):
            parts = [clean if clean.upper().startswith("UNIVERSAL AVAILABILITY") else f"UNIVERSAL AVAILABILITY RULE {clean}"]
            index += 1
            if index < len(bullets):
                nxt = _strip_recap_bullet_prefix(bullets[index])
                if _is_ua_recap_body(nxt) and not re.fullmatch(r"UNIVERSAL AVAILABILITY RULE", nxt, re.I):
                    parts.append(nxt)
                    index += 1
            index = _absorb_tail(parts, index)
            merged.append(" ".join(part for part in parts if part).strip())
            continue
        if _is_ua_recap_body(clean) and not clean.upper().startswith("UNIVERSAL AVAILABILITY RULE"):
            parts = [f"UNIVERSAL AVAILABILITY RULE {clean}"]
            index += 1
            index = _absorb_tail(parts, index)
            merged.append(" ".join(parts).strip())
            continue
        merged.append(current)
        index += 1
    return merged


def _recap_needs_ua_nest_rebuild(page: fitz.Page) -> bool:
    """True when Universal Availability exclusions are flattened instead of nested at x≈101."""
    found_ua = False
    has_including = False
    nest_ok = False
    nest_start = re.compile(
        r"^(?:Employees who normally|Students performing|Non-resident aliens|"
        r"Employees who are eligible|Employees not able to defer)",
        re.I,
    )
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
            if not spans:
                continue
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text:
                continue
            if "UNIVERSAL AVAILABILITY" in text.upper():
                found_ua = True
            if re.search(r"including\s*:", text, re.I):
                has_including = True
            if nest_start.match(text.lstrip()) and abs(float(line["bbox"][0]) - 101.0) <= 4:
                nest_ok = True
    return found_ua and has_including and not nest_ok


def _recap_has_sparse_bullets(page: fitz.Page) -> bool:
    """True when Important Information bullets still have large vertical holes."""
    starts: list[float] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
            if not spans:
                continue
            text = _strip_recap_mark("".join(span.get("text", "") for span in spans).strip())
            if not _recap_paragraph_start(text):
                continue
            starts.append(float(line["bbox"][1]))
    starts = sorted(set(round(y, 1) for y in starts))
    if len(starts) < 2:
        return False
    return max(starts[i + 1] - starts[i] for i in range(len(starts) - 1)) >= 90.0


def _recap_has_clip_fragments(page: fitz.Page) -> bool:
    """True when partial keep/remove left clipped Recap glyph crumbs."""
    text = page.get_text("text") or ""
    if re.search(r"(?m)^\s*n\s*$", text):
        return True
    if re.search(r"cannot ex\b", text, re.I):
        return True
    if re.search(r"(?m)^\s*A 403\(b\) plan\s*$", text):
        return True
    return False


def _clean_recap_bullet_text(text: str) -> str:
    """Strip clipped crumbs glued onto an otherwise valid Recap paragraph."""
    clean = _strip_recap_bullet_prefix(text)
    clean = re.sub(r"\s*A 403\(b\) plan\s+service\.?\s*$", "", clean, flags=re.I)
    clean = re.sub(r"\s+cannot ex\s*$", "", clean, flags=re.I)
    return clean.strip()


def _is_viable_recap_bullet(text: str) -> bool:
    """Drop clipped leftovers that are not real Important Information paragraphs."""
    clean = _clean_recap_bullet_text(text)
    if len(clean) < 40:
        return False
    if re.fullmatch(r"n", clean, re.I):
        return False
    if re.search(r"cannot ex\s*$", clean, re.I) and len(clean) < 100:
        return False
    if re.fullmatch(r"A 403\(b\) plan.*", clean, re.I) and len(clean) < 80:
        return False
    return True


def _is_recap_header_line(line: str) -> bool:
    """Keep only real Recap header rows — drop clipped body crumbs from the header band."""
    text = (line or "").strip()
    if not text:
        return False
    if re.fullmatch(r"[\u2022•\u00b7\u25cf\u25e6\u2219\uf0b7╖■□▪▫*\-·●]+", text):
        return False
    if re.fullmatch(r"YEAR END RECAP", text, re.I):
        return True
    if re.fullmatch(r"Important Information", text, re.I):
        return True
    if re.fullmatch(r"\d{4,}", text):
        return True
    if re.search(r"january|february|march|april|may|june|july|august|september|october|november|december", text, re.I) and re.search(r"\d{4}", text):
        return True
    if re.search(r"\bPLAN\b", text, re.I) and len(text) >= 8:
        return True
    return False


def _recap_has_header_rule(page: fitz.Page) -> bool:
    """True when the full-width divider under the plan headings is present."""
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if not item or item[0] != "l" or len(item) < 3:
                continue
            start, end = fitz.Point(item[1]), fitz.Point(item[2])
            if abs(start.y - end.y) > 1.5:
                continue
            left, right = sorted((start.x, end.x))
            mid_y = (start.y + end.y) / 2
            # Client expected rule is near y=92 spanning ~42..504.
            if 88 <= mid_y <= 130 and left <= 56 and right >= 480:
                return True
    return False


def _recap_solid_bullet_count(page: fitz.Page) -> int:
    """Count filled black discs used as Year End Recap bullet marks."""
    count = 0
    for drawing in page.get_drawings():
        fill = drawing.get("fill")
        if fill not in ((0, 0, 0), (0.0, 0.0, 0.0)):
            continue
        rect = fitz.Rect(drawing.get("rect") or (0, 0, 0, 0))
        # Main bullets ~x67, follow-on ~x72, nested UA ~x83.
        if 2.5 <= rect.width <= 6 and 2.5 <= rect.height <= 6 and 50 <= rect.x0 <= 90:
            count += 1
    return count


def _recap_glyph_bullet_count(page: fitz.Page) -> int:
    """Count text bullet glyphs in the expected Recap bullet column (~x=67)."""
    count = 0
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = str(span.get("text") or "").strip()
                if text not in {"•", "·", "●", "╖", "\uf0b7", "\u2022"}:
                    continue
                if 60 <= float(span["bbox"][0]) <= 75:
                    count += 1
    return count


def _recap_layout_matches(page: fitz.Page) -> bool:
    """True when the Year End Recap header and bullet columns already match the MOA layout."""
    title_ok = False
    important_ok = False
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
            if not spans:
                continue
            text = "".join(span.get("text", "") for span in spans).strip()
            size = float(spans[0].get("size") or 0)
            x = float(line["bbox"][0])
            if text.upper() == "YEAR END RECAP":
                title_ok = abs(size - 10.5) <= 0.8
            elif text.lower() == "important information":
                important_ok = abs(x - 42) <= 3 and abs(size - 9.6) <= 0.8
    if not title_ok or not important_ok or not _recap_has_header_rule(page):
        return False
    return _recap_bullets_have_marks(page)


def _recap_bullets_have_marks(page: fitz.Page) -> bool:
    """Check bullets use the divider column with body text on a hanging indent."""
    paragraph_starts: list[tuple[float, float, float]] = []
    marks = _recap_solid_bullet_count(page) + _recap_glyph_bullet_count(page)
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = [span for span in line.get("spans", []) if span.get("text", "").strip()]
            text = "".join(span.get("text", "") for span in spans).strip()
            if not spans:
                continue
            if not _recap_paragraph_start(_strip_recap_mark(text)):
                continue
            body_x = float(spans[0]["bbox"][0])
            paragraph_starts.append((body_x, float(line["bbox"][1]), float(spans[0].get("size") or 0)))
    if not paragraph_starts:
        return False
    for body_x, _body_y, body_size in paragraph_starts:
        # Client expected hanging column is ~78; allow legacy ~62 rebuilds too.
        if body_x < 48 or body_x > 90:
            return False
        if body_size and abs(body_size - 8.1) > 1.6:
            return False
    if marks < len(paragraph_starts):
        return False
    return True


def _recap_specs(plan_type: str | None = None) -> list[dict]:
    """Input: plan type. Calls paragraphs_for. Output: the Year End Recap bullet matches.

    Purpose:
        Input: plan type. Calls paragraphs_for. Output: the Year End Recap bullet matches.

    Args:
        plan_type: Plan type: "401k", "403b", "457", or empty.

    Returns:
        list[dict].

    Raises:
        None.

    Example:
        _recap_specs("text") returns list[dict].

    Side effects:
        None. This function only reads data and returns a value.
    """
    data = paragraphs_for(plan_type)
    return list(data.get("recap_bullets") or [])


def _fold_recap_text(value: str) -> str:
    """Lowercase and normalize curly/garbled quotes so YAML matches still hit."""
    return re.sub(r"[\u2018\u2019\u201c\u201d'`╖]", "'", (value or "").lower())


def _matching_recap(bullet: str, specs: list[dict]) -> dict | None:
    """Matching recap.

    Purpose:
        Matching recap.

    Args:
        bullet: Bullet. Type: str.
        specs: Specs. Type: list[dict].

    Returns:
        a dict | None.

    Raises:
        None.

    Example:
        _matching_recap("text", []) returns a dict | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    text = _fold_recap_text(bullet)
    hits = [
        spec
        for spec in specs
        if (match := _fold_recap_text(str(spec.get("match") or ""))) and match in text
    ]
    if not hits:
        return None
    # The safe-harbor and prior bullets also contain the current-testing sentence.
    specific = [spec for spec in hits if str(spec["id"]) != "Y3"]
    if specific and any(str(spec["id"]) == "Y3" for spec in hits):
        return specific[0]
    return hits[0]


def _adp_nhce_percent(doc: fitz.Document) -> float | None:
    """Adp nhce percent.

    Purpose:
        Adp nhce percent.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        float | None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _adp_nhce_percent(doc) returns float | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for page in doc:
        match = _ADP_NHCE.search(page.get_text("text") or "")
        if match:
            return float(match.group(1))
    return None


_EXCLUSIVE_RECAP = ("Y2", "Y3", "Y4", "Y5")
_EXCLUSIVE_RECAP_TEMPLATES = {
    "Y2": (
        "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed on the "
        "Future HCE Determination Report are considered highly compensated for the Plan Year beginning "
        "in 2026. The maximum average deferral rate for the Highly Compensated Employee(s) for the 2026 "
        "plan year is % based on the average deferral rate for your Nonhighly Compensated Employees (NHCE) "
        "for 2025 of %. This rate is determined using the \"prior year data\" method. Please communicate "
        "the maximum deferral percentage to affected employees. Note: the actual amount an employee can "
        "defer in 2026 is the lesser of the average deferral rate listed, $24,500 or the annual addition "
        "limit (adjusted for \"catch-up\" contributions, if applicable)."
    ),
    "Y3": (
        "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed on the "
        "Future HCE Determination Report are considered highly compensated for the Plan Year beginning "
        "in 2026. The maximum average deferral rate for the Highly Compensated Employee(s) for the 2026 "
        "plan year is based on the average deferral rate for your Nonhighly Compensated Employees for 2026. "
        "Note: In addition, the actual amount the employee can defer in 2026 cannot exceed $24,500 or the "
        "annual addition limit (adjusted for \"catch-up\" contributions, if applicable)."
    ),
    "Y4": (
        "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed on the "
        "Future HCE Determination Report are considered highly compensated for the Plan Year beginning "
        "in 2026. The maximum average deferral rate for the Highly Compensated Employee(s) for the 2026 "
        "plan year is not limited as long as the plan follows the rules and regulations of the Safe Harbor "
        "Plan. Note: The actual amount an employee can defer in 2026 is the lesser of $24,500 or the annual "
        "addition limit (adjusted for \"catch-up\" contributions, if applicable)."
    ),
    "Y5": (
        "Based on the definition of Highly Compensated Employee (HCE), the plan had Highly Compensated "
        "Employees for the plan year ending December 31, 2025, however, no employee will be considered "
        "highly compensated for the plan year beginning January 1, 2026. Please communicate to affected "
        "employees."
    ),
}


def _preferred_exclusive_recap(keep_ids: set[str]) -> str | None:
    """Pick the winning Future-HCE / method bullet among kept exclusive ids."""
    for rule_id in ("Y5", "Y4", "Y2", "Y3"):
        if rule_id in keep_ids:
            return rule_id
    return None


def _looks_like_exclusive_hce(bullet: str) -> bool:
    """True for Future-HCE / method recap wording, even when YAML match text was clipped."""
    text = (bullet or "").lower()
    return bool(
        re.search(r"based on the definition of highly compensated", text)
        or re.search(r"future hce determination", text)
        or re.search(r"prior year data", text)
        or re.search(r"not limited as long as", text)
        or re.search(r"safe harbor plan", text)
    )


def _normalize_recap_bullet_spaces(bullet: str) -> str:
    """Collapse broken quote/spacing artifacts left by source PDF extraction."""
    text = re.sub(r"[\u00b7\u2022\u2219\uf0b7]+", " ", bullet or "")
    text = re.sub(r"[“”]", '"', text)
    text = re.sub(r"[‘’]", "'", text)
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    text = re.sub(r"(\d)\s+%", r"\1%", text)
    text = re.sub(r"([(\[])\s+", r"\1", text)
    text = re.sub(r"\s+([)\]])", r"\1", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _adapt_recap_years(template: str, sample: str) -> str:
    """Map template 2025/2026 placeholders onto years found in the source bullet."""
    years = sorted({int(value) for value in re.findall(r"\b(20\d{2})\b", sample or "")})
    if len(years) >= 2:
        prior, future = years[-2], years[-1]
    elif len(years) == 1:
        future = years[0]
        prior = future - 1
    else:
        return template
    updated = template.replace("2026", "@@F@@").replace("2025", "@@P@@")
    return updated.replace("@@F@@", str(future)).replace("@@P@@", str(prior))


def _canonical_exclusive_recap(rule_id: str, sample: str) -> str:
    """Build the kept exclusive Year End Recap bullet, preserving source years."""
    template = _EXCLUSIVE_RECAP_TEMPLATES.get(rule_id)
    if not template:
        return _normalize_recap_bullet_spaces(sample)
    return _normalize_recap_bullet_spaces(_adapt_recap_years(template, sample))


def _fill_prior_rates(bullet: str, nhce: float | None) -> str:
    """Write the NHCE rate and the HCE maximum into the prior-year recap bullet.

    Purpose:
        Write the NHCE rate and the HCE maximum into the prior-year recap bullet.

    Args:
        bullet: Bullet. Type: str.
        nhce: Nhce. Type: float | None.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _fill_prior_rates("text", 1.0) returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if nhce is None:
        return bullet
    hce_label = _percent_label(hce_max_percent(nhce))
    nhce_label = _percent_label(nhce)
    updated = re.sub(
        r"(\bis\s+)(?:\d+(?:\.\d+)?\s*)?%\s*(based on\b)",
        rf"\g<1>{hce_label} \g<2>",
        bullet,
        count=1,
        flags=re.I,
    )
    updated = re.sub(
        r"(\bof\s+)(?:\d+(?:\.\d+)?\s*)?%",
        rf"\g<1>{nhce_label}",
        updated,
        count=1,
        flags=re.I,
    )
    return updated


def _percent_label(value: float) -> str:
    """Percent label.

    Purpose:
        Percent label.

    Args:
        value: Value. Type: float.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _percent_label(1.0) returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    rounded = round(float(value), 2)
    if rounded == int(rounded):
        return f"{int(rounded)}%"
    return f"{rounded:.2f}".rstrip("0").rstrip(".") + "%"


def _recap_page_number(text: str) -> int | None:
    """Recap page number.

    Purpose:
        Recap page number.

    Args:
        text: Text taken from a page or a file.

    Returns:
        int | None.

    Raises:
        None.

    Example:
        _recap_page_number("text") returns int | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if lines and re.fullmatch(r"\d{1,3}", lines[-1]):
        return int(lines[-1])
    return None


def _split_recap(text: str) -> tuple[str, list[str]]:
    """Split recap.

    Purpose:
        Split recap.

    Args:
        text: Text taken from a page or a file.

    Returns:
        tuple[str, list[str]].

    Raises:
        None.

    Example:
        _split_recap("text") returns tuple[str, list[str]].

    Side effects:
        None. This function only reads data and returns a value.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip() and not re.fullmatch(r"\d{1,3}", line.strip())]
    first = next((index for index, line in enumerate(lines) if _recap_paragraph_start(line)), None)
    if first is None:
        return _split_marked_bullets(text)
    header = lines[:first]
    bullets: list[str] = []
    current: list[str] = []
    for line in lines[first:]:
        for piece in _pieces_at_starts(line):
            if _recap_paragraph_start(piece):
                if current:
                    bullets.append(" ".join(current).strip())
                current = [piece]
                continue
            if current:
                current.append(piece)
            else:
                header.append(piece)
    if current:
        bullets.append(" ".join(current).strip())
    return "\n".join(header).strip() or "Important Information", [item for item in bullets if item]


_RECAP_START = re.compile(
    r"^(?:your plan is not subject to (?:adp|acp)|"
    r"based on the definition of highly compensated|"
    r"your plan is designed to allow participants|"
    r"your plan may also permit participants with over 15|"
    # Do NOT treat "Participants with fifteen…" as a new bullet — it continues
    # the over-15 catch-up paragraph in source packages.
    r"universal availability rule|"
    r"the ['\u2018\u2019`\"\u201c\u201d]?universal availability|"
    r"based on the top heavy|"
    r"your plan will be considered top heavy|"
    r"if you sponsor a qualified retirement plan|"
    r"the plan['\u2019`╖]s employer match contribution|"
    r"reallocation of forfeitures|"
    r"no forfeitures available to reallocate)",
    re.I,
)


def _recap_paragraph_start(line: str) -> bool:
    """A Year End Recap template paragraph, with or without a bullet mark.

    Purpose:
        A Year End Recap template paragraph, with or without a bullet mark.

    Args:
        line: Line. Type: str.

    Returns:
        True or False.

    Raises:
        None.

    Example:
        _recap_paragraph_start("Your plan is not subject to ADP/ACP testing") returns True.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return bool(_RECAP_START.match(_strip_recap_mark(line)))


_RECAP_MARK = re.compile(
    r"^(?:[\u2022•\u00b7\u25cf\u25e6\u2219\uf0b7╖■□▪▫*?\-]\s*)+",
)


def _strip_recap_mark(line: str) -> str:
    """Strip recap mark.

    Purpose:
        Strip recap mark.

    Args:
        line: Line. Type: str.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _strip_recap_mark("text") returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    # Strip only known bullet markers (including font-substituted glyphs such as ╖).
    # Removing every leading non-letter also erased standalone currency amounts
    # such as "$7,500." during recap rebuilds.
    return _RECAP_MARK.sub("", line or "").strip()


def _pieces_at_starts(line: str) -> list[str]:
    """Pieces at starts.

    Purpose:
        Pieces at starts.

    Args:
        line: Line. Type: str.

    Returns:
        list[str].

    Raises:
        None.

    Example:
        _pieces_at_starts("text") returns list[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
    body = _strip_recap_mark(line)
    matches = list(_RECAP_START.finditer(body))
    if not matches:
        return [body] if body else []
    pieces: list[str] = []
    if matches[0].start() > 0:
        pieces.append(body[: matches[0].start()].strip())
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        pieces.append(body[match.start() : end].strip())
    return [piece for piece in pieces if piece]


def _split_marked_bullets(text: str) -> tuple[str, list[str]]:
    """Split marked bullets.

    Purpose:
        Split marked bullets.

    Args:
        text: Text taken from a page or a file.

    Returns:
        tuple[str, list[str]].

    Raises:
        None.

    Example:
        _split_marked_bullets("text") returns tuple[str, list[str]].

    Side effects:
        None. This function only reads data and returns a value.
    """
    lines = [line.strip() for line in text.splitlines()]
    header: list[str] = []
    bullets: list[str] = []
    current: list[str] = []
    started = False
    for line in lines:
        if re.fullmatch(r"\d{1,3}", line):
            continue
        if _RECAP_MARK.match(line):
            if current:
                bullets.append(" ".join(current).strip())
            started = True
            current = [_strip_recap_mark(line)]
            continue
        if not started:
            header.append(line)
            continue
        if line:
            current.append(line)
        elif current:
            bullets.append(" ".join(current).strip())
            current = []
    if current:
        bullets.append(" ".join(current).strip())
    return "\n".join(header).strip() or "Important Information", [item for item in bullets if item]


def _redact_recap_paragraphs(page: fitz.Page, paragraphs: list[str]) -> bool:
    """Cover the template paragraphs that do not apply, and leave the others where they are.

    Purpose:
        Cover the template paragraphs that do not apply, and leave the others where they are.

    Args:
        page: One PDF page.
        paragraphs: Paragraphs. Type: list[str].

    Returns:
        True when every paragraph was found and covered.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _redact_recap_paragraphs(page, []) returns True or False.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    lines = _page_lines(page)
    used: set[int] = set()
    boxes: list[fitz.Rect] = []
    for paragraph in paragraphs:
        target = _squash(paragraph)
        if not target:
            continue
        found = False
        for start in range(len(lines)):
            if start in used:
                continue
            joined = ""
            rect: fitz.Rect | None = None
            consumed: list[int] = []
            for index in range(start, len(lines)):
                if index in used:
                    break
                joined += _squash(lines[index][0])
                line_rect = fitz.Rect(lines[index][1])
                rect = line_rect if rect is None else rect | line_rect
                consumed.append(index)
                if joined.startswith(target):
                    boxes.append(fitz.Rect(18, rect.y0 - 1, page.rect.x1 - 18, rect.y1 + 2))
                    used.update(consumed)
                    found = True
                    break
                if len(joined) > len(target):
                    break
            if found:
                break
        if not found:
            return False
    if not boxes:
        return False
    _apply_redact_boxes(page, boxes)
    return True


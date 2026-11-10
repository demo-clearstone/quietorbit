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
            # No lasting white cover: restack rewrites surviving text into these bands.
            _apply_redact_boxes(page, boxes, cover=False)
    if touched:
        _restack_pages(doc, touched)
        _pack_action_across_pages(doc)
        _strip_im_fragments(doc)
        _drop_empty_pages(doc)
        _finalize_no_immediate_pages(doc)
        for page in doc:
            text = page.get_text("text") or ""
            if re.search(r"annual valuation report|immediate action required|attention required|no immediate action", text, re.I):
                _redraw_action_rules(page)
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


def _restack_pages(doc: fitz.Document, touched: dict[int, list[fitz.Rect]]) -> None:
    """Collapse removed regions by their exact height while keeping each surviving span at its source x-position and style.

    Purpose:
        Shift leftover text up, keeping font/size/color. Images stay put.

    Args:
        doc: Open PDF. Must not be closed.
        touched: Page-index to removed vertical regions.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        Text below one removed region moves up by exactly that region's height; text above it stays put.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    for page in doc:
        removed = touched.get(page.number)
        if not removed:
            continue
        blocks = _text_blocks(page)
        if not blocks:
            continue
        body = [block for block in blocks if not _is_page_number_block(page, block)]
        footer = [block for block in blocks if _is_page_number_block(page, block)]
        removed_bands = _merged_vertical_bands(removed)
        header_rule_y = _top_header_rule_y(page)
        # Wipe text without lasting white overlays — overlays at old y-positions would
        # hide content that shifts up into those bands.
        _apply_redact_boxes(page, [block["bbox"] for block in blocks], cover=False)
        for block in body:
            delta = _upshift_delta(block["bbox"].y0, removed_bands)
            if header_rule_y is not None and block["bbox"].y0 > header_rule_y:
                # Keep a small gap under the header divider; do not cap later blocks by
                # the first post-header gap (that left large white holes after mid-page removals).
                minimum_y = header_rule_y + 30.0
                delta = max(delta, minimum_y - block["bbox"].y0)
            for span in block["spans"]:
                _write_span(page, span, delta)
        for block in footer:
            for span in block["spans"]:
                _write_span(page, span, 0)
        # Restack rewrites text but leaves vector underlines from removed headings.
        if header_rule_y is not None:
            _clear_short_rules_below(page, header_rule_y)


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


def _top_header_rule_y(page: fitz.Page) -> float | None:
    """Find the full-width header divider near the top of an Annual Valuation Report page."""
    text = page.get_text("text") or ""
    if not re.search(r"annual valuation report", text, re.I):
        return None
    found: list[float] = []
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if not item or item[0] != "l" or len(item) < 3:
                continue
            start, end = fitz.Point(item[1]), fitz.Point(item[2])
            if abs(start.y - end.y) > 1.5:
                continue
            left, right = sorted((start.x, end.x))
            if left <= 52 and right >= page.rect.width - 52 and start.y < page.rect.height * 0.4:
                found.append(start.y)
    return max(found) if found else None


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
    try:
        page.insert_text(
            point,
            span["text"],
            fontsize=span["size"],
            fontname=fontname,
            color=_rgb(span["color"]),
            overlay=True,
        )
    except Exception:
        page.insert_text(
            point,
            span["text"],
            fontsize=span["size"],
            fontname="helv",
            color=_rgb(span["color"]),
            overlay=True,
        )


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
    """Write the ACTION REQUIRED heading. ``cursor`` is the text baseline."""
    left = 54.0 if x is None else float(x)
    page.insert_text((left, cursor), "ACTION REQUIRED", fontsize=11, fontname="hebo", color=(0, 0, 0))
    width = fitz.get_text_length("ACTION REQUIRED", fontname="hebo", fontsize=11)
    # Place the rule under the glyph box (baseline + descent), not through the letters.
    underline_y = cursor + 4
    for word in page.get_text("words") or []:
        if abs(float(word[0]) - left) < 2 and str(word[4]).upper() == "ACTION":
            underline_y = max(underline_y, float(word[3]) + 2)
            break
    page.draw_line(
        fitz.Point(left, underline_y),
        fitz.Point(left + width, underline_y),
        color=(0, 0, 0),
        width=0.8,
    )
    return underline_y + 18


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
    if not boxes:
        return
    if redact:
        for rect in boxes:
            page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(images=0, graphics=2)
        return
    for rect in boxes:
        page.draw_line(
            fitz.Point(rect.x0, (rect.y0 + rect.y1) / 2),
            fitz.Point(rect.x1, (rect.y0 + rect.y1) / 2),
            color=(1, 1, 1),
            width=2.4,
            overlay=True,
        )


def _finalize_no_immediate_pages(doc: fitz.Document) -> None:
    """Match the package sample: ACTION REQUIRED, then the green no-action line under it."""
    for page in doc:
        text = page.get_text("text") or ""
        if not re.search(r"no immediate action is required at this time", text, re.I):
            continue
        if not re.search(r"annual valuation report", text, re.I):
            continue
        # Leave pages that still have other action blocks; only pack the all-clear page.
        if re.search(r"IMMEDIATE ACTION REQUIRED|ATTENTION REQUIRED", text, re.I):
            continue
        has_heading = bool(re.search(r"(?m)^\s*ACTION REQUIRED\s*$", text))
        green = None
        trailing: list[dict] = []
        started = False
        for block in _text_blocks(page):
            joined = " ".join(span["text"] for span in block["spans"]).strip()
            if re.match(r"NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME", joined, re.I):
                green = block
                started = True
                continue
            if started and not _is_page_number_block(page, block) and not _is_noise_text(joined):
                trailing.append(block)
        header_rule_y = _top_header_rule_y(page)
        if green is None:
            if header_rule_y is not None:
                _clear_short_rules_below(page, header_rule_y)
            continue
        if has_heading:
            if header_rule_y is not None:
                _clear_short_rules_below(page, header_rule_y)
            continue
        green_spans = [dict(span) for span in green["spans"]]
        green_text = "".join(span["text"] for span in green_spans)
        size = float(green_spans[0]["size"]) if green_spans else 11.0
        color = _rgb(green_spans[0]["color"]) if green_spans else (0, 0.45, 0.15)
        column_x = _action_column_x(page)
        # Pack under the header divider (not at the green line's current y, which left
        # a hole and overlapped any trailing paragraph that restack had already pulled up).
        heading_baseline = (header_rule_y + 40.0) if header_rule_y is not None else 90.0
        wipe = [green["bbox"], *[block["bbox"] for block in trailing]]
        _apply_redact_boxes(page, wipe, cover=False)
        if header_rule_y is not None:
            _clear_short_rules_below(page, header_rule_y, redact=True)
        cursor = _write_action_heading(page, heading_baseline, x=column_x)
        page.insert_text(
            fitz.Point(column_x, cursor),
            green_text,
            fontsize=size,
            fontname="hebo",
            color=color,
            overlay=True,
        )
        cursor += size + 14.0
        for block in trailing:
            # Place each trailing block so its top sits just under the running cursor.
            delta = (cursor - 11.0) - block["bbox"].y0
            for span in block["spans"]:
                _write_span(page, span, delta)
            cursor += block["bbox"].height + 12.0


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
        if re.fullmatch(r"\d{5,7}", text) and block["bbox"].y0 < (header_rule_y or 200):
            continue
        blocks.append(block)
    return blocks


def _pack_one_action_overflow(doc: fitz.Document) -> bool:
    """Move as many leading overflow blocks as fit from one later page onto the prior page."""
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
        for block in overflow:
            height = float(block["bbox"].height)
            if height + 10 > free:
                break
            target_top = cursor
            delta = target_top - float(block["bbox"].y0)
            for span in block["spans"]:
                _write_span(dest, span, delta)
            moved.append(block)
            cursor = target_top + height + 14.0
            free = footer_limit - cursor
        if not moved:
            continue
        boxes = [block["bbox"] for block in moved]
        _apply_redact_boxes(source, boxes, cover=False)
        _restack_pages(doc, {source.number: boxes})
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
        if anchor is None and re.search(r"annual valuation report", text, re.I):
            anchor = page
            continue
        if anchor is not None and _KEPT_ACTION.search(text):
            later.append(page)
    if anchor is None or not later or _KEPT_ACTION.search(anchor.get_text("text") or ""):
        return
    header_rule_y = _top_header_rule_y(anchor)
    if header_rule_y is not None:
        _clear_short_rules_below(anchor, header_rule_y)
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
        for block in blocks:
            # Place the block so its top sits near the current baseline gap.
            target_top = baseline - 11
            delta = target_top - block["bbox"].y0
            for span in block["spans"]:
                _write_span(anchor, span, delta)
            baseline = target_top + block["bbox"].height + 16
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


def _short_rules_near_heading(page: fitz.Page, top: float, bottom: float, x0: float, x1: float) -> list[fitz.Rect]:
    """Short horizontal rules near a heading, including ones that are too long or too short."""
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
            if y < top - 1.0 or y > bottom + 4.0:
                continue
            if abs(end.x - start.x) >= page.rect.width * 0.7:
                continue
            left, right = sorted((start.x, end.x))
            if right < x0 - 8 or left > x1 + 40:
                continue
            boxes.append(fitz.Rect(left - 1, y - 1.5, right + 1, y + 1.5))
    return boxes


def _redraw_action_rules(page: fitz.Page) -> None:
    """Put Action Required underlines back after packing, matching each phrase width.

    Purpose:
        Put Action Required underlines back after packing, matching each phrase width.

    Args:
        page: One PDF page.

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
    # Delete leftover short rules first so a too-long or too-short source underline
    # cannot survive under the replacement.
    wipe: list[fitz.Rect] = []
    planned: list[tuple[float, float, float, tuple[float, float, float]]] = []
    for heading in headings:
        text = heading["text"]
        x0 = float(heading["x0"])
        x1 = float(heading["x1"])
        top = float(heading["y0"])
        bottom = float(heading["y1"])
        y = bottom + 2.0
        upper = text.upper()
        color = (0, 0.45, 0.15) if upper.startswith("NO IMMEDIATE") else (0, 0, 0)
        if upper.startswith("IMMEDIATE ACTION"):
            color = (0.8, 0, 0)
        wipe.extend(_short_rules_near_heading(page, top, y, x0, x1))
        planned.append((x0, x1, y, color))
    if wipe:
        for rect in wipe:
            page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(images=0, graphics=2)
    for x0, x1, y, color in planned:
        page.draw_line(fitz.Point(x0, y), fitz.Point(x1, y), color=color, width=0.8)


def _has_horizontal_rule(page: fitz.Page, y: float, x0: float, x1: float) -> bool:
    """Check whether a horizontal vector rule already underlines this heading."""
    for drawing in page.get_drawings():
        if drawing.get("color") in {(1, 1, 1), (1.0, 1.0, 1.0)}:
            continue
        for item in drawing.get("items", []):
            if not item or item[0] != "l" or len(item) < 3:
                continue
            start, end = fitz.Point(item[1]), fitz.Point(item[2])
            if abs(start.y - end.y) > 1.5 or abs(start.y - y) > 4:
                continue
            left, right = sorted((start.x, end.x))
            if right >= x0 - 2 and left <= x1 + 2:
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
            if y < top - 0.5 or y > bottom + 0.5:
                continue
            if abs(end.x - start.x) >= page.rect.width * 0.7:
                continue
            left, right = sorted((start.x, end.x))
            if right < x0 - 4 or left > x1 + 4:
                continue
            page.draw_line(
                fitz.Point(left - 1, y),
                fitz.Point(right + 1, y),
                color=(1, 1, 1),
                width=2.4,
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
        content_changed = False
        have_exclusive = False
        for bullet in bullets:
            cleaned = _normalize_recap_bullet_spaces(bullet)
            if cleaned != bullet:
                content_changed = True
            bullet = cleaned
            spec = _matching_recap(bullet, specs)
            rule_id = str(spec["id"]) if spec else None
            exclusive_like = rule_id in _EXCLUSIVE_RECAP or _looks_like_exclusive_hce(bullet)
            if spec is None and re.search(r"(?:^|\s)%(?:\s|$)", bullet):
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
                    have_exclusive = True
                    content_changed = True
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
                    have_exclusive = True
                    content_changed = True
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
                    content_changed = True
                bullet = filled
            kept.append(bullet)
        if wanted_exclusive and wanted_exclusive not in remove_ids and not have_exclusive:
            # Exclusive keep-rule matched, but the page never had Future-HCE wording.
            sample = next((item for item in bullets if item), "")
            injected = _canonical_exclusive_recap(wanted_exclusive, sample)
            if wanted_exclusive == "Y2":
                injected = _fill_prior_rates(injected, nhce)
            kept.insert(0, injected)
            content_changed = True
        # In-place redaction of dropped bullets leaves large white gaps (Kaagaz page 3
        # vs packed page 4). Always rebuild whenever anything was removed, when rates
        # or exclusive wording changed, when the header/bullet columns do not already
        # match the MOA layout, or when kept bullets are still spaced with large holes.
        if (
            not dropped
            and not content_changed
            and _recap_layout_matches(page)
            and not _recap_has_sparse_bullets(page)
            and not _recap_needs_ua_nest_rebuild(page)
        ):
            continue
        header_lines = [
            line.strip()
            for line in header.splitlines()
            if line.strip()
            and not re.fullmatch(r"[\u2022•\u00b7\u25cf\u25e6\u2219\uf0b7╖■□▪▫*\-·●]+", line.strip())
        ]
        if not header_lines:
            header_lines = ["Important Information"]
        kept = _merge_universal_availability_bullets(kept)
        # Full-page wipe. Long source insert_text runs can leave clipped leftovers
        # (and stray bullet glyphs) if only redaction runs.
        page.add_redact_annot(page.rect, fill=(1, 1, 1))
        page.apply_redactions(images=0, graphics=1)
        page.draw_rect(page.rect, color=(1, 1, 1), fill=(1, 1, 1), width=0)
        try:
            page.clean_contents()
        except Exception:
            pass
        from services.package_builder import write_recap_page

        number = _recap_page_number(original)
        write_recap_page(page, header_lines, kept, number=number, plan_type=plan_type)
    return removed


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
            if 88 <= mid_y <= 122 and left <= 56 and right >= 480:
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
        if 2.5 <= rect.width <= 6 and 2.5 <= rect.height <= 6 and 50 <= rect.x0 <= 80:
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
    r"participants with fifteen or more years of service|"
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


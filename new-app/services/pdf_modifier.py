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
    removed: list[str] = []
    touched: set[int] = set()
    for page in doc:
        boxes: list[fitz.Rect] = []
        for spec in specs:
            rule_id = str(spec["id"])
            heading = str(spec.get("heading") or "")
            if rule_id not in remove_ids or not heading:
                continue
            page_text = page.get_text("text") or ""
            extra = str(spec.get("extra") or "")
            if not _extra_matches(page_text, extra):
                continue
            for hit in _heading_hits(page, heading):
                if _covered_by_longer_heading(page, hit, heading, headings):
                    continue
                end_y = _block_end(page, hit.y0, headings)
                if not _block_matches(page, spec, hit.y0, end_y):
                    continue
                if _kept_by_other_spec(page, page_text, specs, heading, hit.y0, end_y, keep_ids):
                    continue
                boxes.append(fitz.Rect(40, max(36, hit.y0 - 2), page.rect.x1 - 40, end_y))
                if rule_id not in removed:
                    removed.append(rule_id)
        if boxes:
            _apply_redact_boxes(page, boxes)
            touched.add(page.number)
    if touched:
        _restack_pages(doc, touched)
        _pull_kept_action_forward(doc)
        _drop_empty_pages(doc)
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


def _covered_by_longer_heading(page: fitz.Page, hit, heading: str, headings: list[str]) -> bool:
    """'Failed Compliance Testing' is the start of the after-12-month heading.

    Purpose:
        'Failed Compliance Testing' is the start of the after-12-month heading.

    Args:
        page: One PDF page.
        hit: Hit. Type: unspecified.
        heading: Heading. Type: str.
        headings: Headings. Type: list[str].

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
        for rect in _heading_hits(page, other):
            if abs(rect.y0 - hit.y0) <= 2 and abs(rect.x0 - hit.x0) <= 2:
                return True
    return False


def _block_end(page: fitz.Page, y0: float, headings: list[str]) -> float:
    """Stop at the next heading, including another copy of this same heading.

    Purpose:
        Stop at the next heading, including another copy of this same heading.

    Args:
        page: One PDF page.
        y0: Y0. Type: float.
        headings: Headings. Type: list[str].

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
    seen: set[str] = set()
    for heading in headings:
        if not heading or heading in seen:
            continue
        seen.add(heading)
        for rect in _heading_hits(page, heading):
            if rect.y0 > y0 + 8:
                end_y = min(end_y, rect.y0 - 4)
    return end_y


def _heading_hits(page: fitz.Page, heading: str) -> list[fitz.Rect]:
    """A heading starts a line, and may wrap onto the next lines. Words inside a sentence are not a heading.

    Purpose:
        A heading starts a line, and may wrap onto the next lines. Words inside a sentence are not a heading.

    Args:
        page: One PDF page.
        heading: Heading. Type: str.

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
    lines = _page_lines(page)
    hits: list[fitz.Rect] = []
    for start in range(len(lines)):
        joined = ""
        rect = fitz.Rect(lines[start][1])
        for text, bbox in lines[start : start + 4]:
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


def _restack_pages(doc: fitz.Document, touched: set[int]) -> None:
    """Shift leftover text up, keeping font/size/color. Images stay put.

    Purpose:
        Shift leftover text up, keeping font/size/color. Images stay put.

    Args:
        doc: Open PDF. Must not be closed.
        touched: Touched. Type: set[int].

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _restack_pages(doc, touched) returns None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    for page in doc:
        if page.number not in touched:
            continue
        blocks = _text_blocks(page)
        if not blocks:
            continue
        body = [block for block in blocks if not _is_page_number_block(page, block)]
        footer = [block for block in blocks if _is_page_number_block(page, block)]
        header_bottom, footer_top = _image_bands(page)
        _apply_redact_boxes(
            page,
            [block["bbox"] for block in blocks]
            + [fitz.Rect(drawing["rect"]) for drawing in page.get_drawings()],
        )
        cursor = header_bottom
        for block in body:
            height = block["bbox"].height
            if cursor + height > footer_top:
                break
            delta = cursor - block["bbox"].y0
            for span in block["spans"]:
                _write_span(page, span, delta)
            cursor += height + 8
        for block in footer:
            for span in block["spans"]:
                _write_span(page, span, 0)


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
    return not any(len(word) >= 2 and re.search(r"[A-Za-z]", word) for word in words)


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


def _apply_redact_boxes(page: fitz.Page, boxes: list[fitz.Rect]) -> None:
    """Apply redact boxes.

    Purpose:
        Apply redact boxes.

    Args:
        page: One PDF page.
        boxes: Boxes. Type: list[fitz.Rect].

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


def _write_action_heading(page: fitz.Page, cursor: float) -> float:
    """Write action heading.

    Purpose:
        Write action heading.

    Args:
        page: One PDF page.
        cursor: Cursor. Type: float.

    Returns:
        a float.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _write_action_heading(page, 1.0) returns a float.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    page.insert_text((54, cursor), "ACTION REQUIRED", fontsize=11, fontname="hebo", color=(0, 0, 0))
    width = fitz.get_text_length("ACTION REQUIRED", fontname="hebo", fontsize=11)
    page.draw_line(
        fitz.Point(54, cursor + 2),
        fitz.Point(54 + width, cursor + 2),
        color=(0, 0, 0),
        width=0.8,
    )
    return cursor + 22


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
    anchor_blocks = _text_blocks(anchor)
    cursor = anchor_blocks[-1]["bbox"].y1 + 18 if anchor_blocks else 90
    if not re.search(r"action required", anchor.get_text("text") or "", re.I):
        cursor = _write_action_heading(anchor, cursor)
    delete_numbers: list[int] = []
    for page in later:
        blocks = _action_blocks_to_move(page)
        if not blocks:
            continue
        for block in blocks:
            delta = cursor - block["bbox"].y0
            for span in block["spans"]:
                _write_span(anchor, span, delta)
            cursor += block["bbox"].height + 8
        if _is_recap_text(page.get_text("text") or ""):
            _apply_redact_boxes(page, [block["bbox"] for block in blocks])
            continue
        delete_numbers.append(page.number)
    for number in reversed(delete_numbers):
        doc.delete_page(number)


def _redraw_action_rules(page: fitz.Page) -> None:
    """Put the header rule and heading underlines back after the text is packed.

    Purpose:
        Put the header rule and heading underlines back after the text is packed.

    Args:
        page: One PDF page.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _redraw_action_rules(page) returns None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    lines: dict[int, list[tuple]] = {}
    for word in page.get_text("words") or []:
        lines.setdefault(round(word[1]), []).append(word)
    for group in lines.values():
        group.sort(key=lambda item: item[0])
        text = " ".join(item[4] for item in group)
        y = max(item[3] for item in group) + 1.5
        if re.fullmatch(r"\d{5,7}", text):
            page.draw_line(
                fitz.Point(48, y + 4),
                fitz.Point(page.rect.width - 48, y + 4),
                color=(0, 0, 0),
                width=1,
            )
            continue
        if not re.match(
            r"^(ACTION REQUIRED|IMMEDIATE ACTION REQUIRED|ATTENTION REQUIRED|NO IMMEDIATE ACTION IS REQUIRED)",
            text,
        ):
            continue
        color = (0, 0.45, 0.15) if text.startswith("NO IMMEDIATE") else (0, 0, 0)
        if text.startswith("IMMEDIATE ACTION"):
            color = (0.8, 0, 0)
        page.draw_line(
            fitz.Point(group[0][0], y),
            fitz.Point(group[-1][2], y),
            color=color,
            width=0.8,
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
    both = [value for value in (profile.adp_qnec, profile.acp_qnec) if value is not None]
    total = round(sum(both), 2) if both else profile.total_qnec
    amounts = {
        "total": total,
        "adp": profile.adp_qnec,
        "acp": profile.acp_qnec,
        "deferral": profile.deferral_refund,
        "match": profile.match_refund,
        "acp-notice": profile.acp_qnec if package_flags(profile.plan_type).get("acp_notice_amount") else None,
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

    Args:
        page: One PDF page.
        amounts: Amounts. Type: dict[str, float | None].

    Returns:
        a list of tuple[str, float | None].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _fill_notice_amounts(page, 1.0) returns a list of tuple[str, float | None].

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    done: list[tuple[str, float | None]] = []
    while True:
        hits = page.search_for("$X,XXX,XXX.XX")
        if not hits:
            return done
        hit = sorted(hits, key=lambda item: (item.y0, item.x0))[0]
        words = page.get_text("words") or []
        kind, label_words, token = _notice_placeholder(words, hit)
        value = amounts.get(kind) if kind else None
        rects = [fitz.Rect(token[:4])] if token else [hit]
        if value is None:
            rects = [fitz.Rect(word[:4]) for word in label_words] or rects
        for rect in rects:
            page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions()
        if value is not None and token:
            money = _money(value)
            if str(token[4]).endswith("."):
                money += "."
            page.insert_text(
                (float(token[0]), float(token[3]) - 1),
                money,
                fontsize=10,
                fontname="helv",
                color=(0, 0, 0),
            )
        done.append((kind or "amount", value))


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
    index = next(
        (
            pos
            for pos, word in enumerate(ordered)
            if abs(word[0] - hit.x0) < 3 and abs(word[1] - hit.y0) < 3
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
    nhce = _adp_nhce_percent(doc)
    removed: list[str] = []
    for page in doc:
        original = page.get_text("text") or ""
        if "important information" not in original.lower():
            continue
        header, bullets = _split_recap(original)
        kept: list[str] = []
        for bullet in bullets:
            spec = _matching_recap(bullet, specs)
            if spec and str(spec["id"]) in remove_ids:
                if spec["id"] not in removed:
                    removed.append(str(spec["id"]))
                continue
            if spec and str(spec["id"]) == "Y2":
                bullet = _fill_prior_rates(bullet, nhce)
            kept.append(bullet)
        header_lines = [line.strip() for line in header.splitlines() if line.strip()]
        if not header_lines:
            header_lines = ["Important Information"]
        updated_text = "\n".join(header_lines + kept)
        if updated_text.strip() == re.sub(r"\s+", " ", original).strip():
            continue
        _apply_redact_boxes(page, [page.rect])
        from services.package_builder import write_recap_page

        number = _recap_page_number(original)
        write_recap_page(page, header_lines, kept, number=number)
    return removed


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
    text = bullet.lower()
    hits = [
        spec
        for spec in specs
        if (match := str(spec.get("match") or "").lower()) and match in text
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
    lines = [line.strip() for line in text.splitlines()]
    header: list[str] = []
    bullets: list[str] = []
    current: list[str] = []
    started = False
    for line in lines:
        if re.fullmatch(r"\d{1,3}", line):
            continue
        if re.match(r"^[\u2022•\u00b7\-\*\?]\s+", line):
            if current:
                bullets.append(" ".join(current).strip())
            started = True
            current = [re.sub(r"^[\u2022•\u00b7\-\*\?]\s*", "", line)]
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


"""Preview pages, bookmark list, and in-place text edits.

The browser PDF viewer closes its bookmark sidebar on a click and often ignores
the destination. The preview draws the pages itself and keeps its own list open.
"""

from __future__ import annotations

import threading
import re
from pathlib import Path

import fitz

from services.change_marks import save_marks
from services.pdf_modifier import _base_font, _rgb

_LOCK = threading.Lock()
_PNG_CACHE: dict[tuple[str, int, int, float], bytes] = {}
_PAGE_SCALE = 1.5
_MAX_TEXT = 800
_MIN_REPLACEMENT_FONT_SIZE = 6.0


def outline(pdf_path: Path) -> dict:
    with _LOCK:
        doc = fitz.open(pdf_path)
        try:
            count = doc.page_count
            bookmarks = []
            for level, title, page, *_rest in doc.get_toc():
                target = int(page)
                if target < 1:
                    target = 1
                if count and target > count:
                    target = count
                bookmarks.append({"level": int(level), "title": str(title), "page": target})
            return {"page_count": count, "bookmarks": bookmarks}
        finally:
            doc.close()


def page_png(pdf_path: Path, page_number: int, scale: float = _PAGE_SCALE) -> bytes:
    key = (str(pdf_path), pdf_path.stat().st_mtime_ns, page_number, scale)
    cached = _PNG_CACHE.get(key)
    if cached is not None:
        return cached
    with _LOCK:
        cached = _PNG_CACHE.get(key)
        if cached is not None:
            return cached
        doc = fitz.open(pdf_path)
        try:
            page = _page(doc, page_number)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            data = pix.tobytes("png")
        finally:
            doc.close()
    _PNG_CACHE[key] = data
    while len(_PNG_CACHE) > 40:
        _PNG_CACHE.pop(next(iter(_PNG_CACHE)))
    return data


def page_lines(pdf_path: Path, page_number: int) -> dict:
    with _LOCK:
        doc = fitz.open(pdf_path)
        try:
            page = _page(doc, page_number)
            lines = _lines(page)
            if page.rotation:
                for line in lines:
                    rect = fitz.Rect(line["x0"], line["y0"], line["x1"], line["y1"]) * page.rotation_matrix
                    line.update(x0=float(rect.x0), y0=float(rect.y0), x1=float(rect.x1), y1=float(rect.y1))
            return {
                "page": page_number,
                "width": float(page.rect.width),
                "height": float(page.rect.height),
                "base_width": float(page.cropbox.width),
                "base_height": float(page.cropbox.height),
                "rotation": int(page.rotation),
                "lines": lines,
            }
        finally:
            doc.close()


def _split_at_caret(text: str, caret: int) -> tuple[str, str]:
    value = text or ""
    cut = max(0, min(int(caret), len(value)))
    if cut <= 0 or cut >= len(value.rstrip()):
        return "", value.strip()
    return value[:cut].rstrip(), value[cut:].lstrip()


def replace_line(
    pdf_path: Path,
    page_number: int,
    rect: tuple[float, float, float, float],
    new_text: str,
    marks: list[dict],
    copy_path: Path | None = None,
) -> list[dict]:
    """Replace a line, shrinking its font as needed to stay within the original line width."""
    return replace_lines(pdf_path, page_number, [(rect, new_text)], marks, copy_path=copy_path)


def replace_lines(
    pdf_path: Path,
    page_number: int,
    edits: list[tuple[tuple[float, float, float, float], str]],
    marks: list[dict],
    copy_path: Path | None = None,
) -> list[dict]:
    """Replace several lines on one page in a single save."""
    with _LOCK:
        doc = fitz.open(pdf_path)
        try:
            page = _page(doc, page_number)
            plans = [plan for plan in (_replacement_plan(page, rect, text) for rect, text in edits) if plan]
            if not plans:
                return marks
            for plan in plans:
                for span in plan["spans"]:
                    page.add_redact_annot(fitz.Rect(span["bbox"]), fill=(1, 1, 1))
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
            updated = marks
            for plan in plans:
                written = _insert_replacement(page, plan)
                updated = _retarget_marks(marks, page.number, plan["union"], written)
                marks = updated
            tmp = _temporary_pdf_path(pdf_path)
            doc.save(tmp, garbage=3, deflate=True)
        finally:
            doc.close()
        tmp.replace(pdf_path)
        _PNG_CACHE.clear()
        save_marks(pdf_path, updated)
        _sync_saved_copy(pdf_path, copy_path)
    return updated


def shift_line_down(
    pdf_path: Path,
    page_number: int,
    rect: tuple[float, float, float, float],
    new_text: str,
    caret: int,
    marks: list[dict],
    copy_path: Path | None = None,
) -> list[dict]:
    """Move text from the caret onto the next line and push the lines under it down."""
    stay, move = _split_at_caret(new_text, caret)
    if not move:
        raise ValueError("There is no text to move onto the next line.")
    with _LOCK:
        doc = fitz.open(pdf_path)
        try:
            page = _page(doc, page_number)
            box = fitz.Rect(*rect) * page.derotation_matrix
            spans = _spans_in(page, box)
            if not spans:
                raise ValueError("No text on that line. Double-click the words, then press Enter.")
            spans.sort(key=lambda span: (span["bbox"][1], span["bbox"][0]))
            union = fitz.Rect(spans[0]["bbox"])
            for span in spans[1:]:
                union.include_rect(fitz.Rect(span["bbox"]))
            source = spans[0]
            origin = source.get("origin") or (source["bbox"][0], source["bbox"][3])
            size = float(source.get("size") or 11)
            fontname = _base_font(str(source.get("font") or ""), int(source.get("flags") or 0))
            color = _rgb(source.get("color") or 0)
            below = [line for line in _lines(page) if line["y0"] > union.y0 + 1]
            column = [line for line in below if abs(line["x0"] - union.x0) <= 90]
            column = column or below
            column.sort(key=lambda line: (line["y0"], line["x0"]))
            captured: list[dict] = []
            current_boxes = {tuple(round(value, 2) for value in span["bbox"]) for span in spans}
            for line in column:
                line_spans = _spans_in(page, fitz.Rect(line["x0"], line["y0"], line["x1"], line["y1"]))
                if not line_spans:
                    continue
                if {tuple(round(value, 2) for value in span["bbox"]) for span in line_spans} <= current_boxes:
                    continue
                line_spans.sort(key=lambda span: (span["bbox"][1], span["bbox"][0]))
                first = line_spans[0]
                line_origin = first.get("origin") or (first["bbox"][0], first["bbox"][3])
                captured.append(
                    {
                        "spans": line_spans,
                        "text": line["text"],
                        "origin": fitz.Point(float(line_origin[0]), float(line_origin[1])),
                        "size": float(first.get("size") or size),
                        "fontname": _base_font(str(first.get("font") or ""), int(first.get("flags") or 0)),
                        "color": _rgb(first.get("color") or 0),
                    }
                )
            gap = (captured[0]["origin"].y - float(origin[1])) if captured else size * 1.45
            if gap < size * 0.8:
                gap = size * 1.45
            last_y = (captured[-1]["origin"].y if captured else float(origin[1])) + gap
            if last_y > float(page.rect.y1) - 16:
                raise ValueError("This line is too close to the bottom of the page to move the text down.")
            for group in (spans, *[item["spans"] for item in captured]):
                for span in group:
                    page.add_redact_annot(fitz.Rect(span["bbox"]), fill=(1, 1, 1))
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
            if stay:
                _insert_shifted(page, fitz.Point(float(origin[0]), float(origin[1])), stay, size, fontname, color)
            _insert_shifted(page, fitz.Point(float(origin[0]), float(origin[1]) + gap), move, size, fontname, color)
            for item in captured:
                _insert_shifted(
                    page,
                    fitz.Point(item["origin"].x, item["origin"].y + gap),
                    item["text"],
                    item["size"],
                    item["fontname"],
                    item["color"],
                )
            updated = []
            for mark in marks:
                if int(mark.get("page", -1)) != page.number or float(mark.get("y0", 0)) + 1 < union.y0:
                    updated.append(mark)
                    continue
                updated.append({**mark, "y0": float(mark["y0"]) + gap, "y1": float(mark["y1"]) + gap})
            tmp = _temporary_pdf_path(pdf_path)
            doc.save(tmp, garbage=3, deflate=True)
        finally:
            doc.close()
        tmp.replace(pdf_path)
        _PNG_CACHE.clear()
        save_marks(pdf_path, updated)
        _sync_saved_copy(pdf_path, copy_path)
    return updated


def _insert_shifted(page: fitz.Page, point: fitz.Point, text: str, size: float, fontname: str, color: tuple[float, float, float]) -> None:
    try:
        page.insert_text(point, text, fontsize=size, fontname=fontname, color=color)
    except Exception:
        page.insert_text(point, text, fontsize=size, fontname="helv", color=color)


def modify_pages(
    pdf_path: Path,
    action: str,
    page_number: int,
    marks: list[dict],
    *,
    target_page: int | None = None,
    inserted_pdf: bytes | None = None,
    rect: tuple[float, float, float, float] | None = None,
    page_size: str | None = None,
    copy_path: Path | None = None,
) -> tuple[int, int, list[dict]]:
    """Rotate, move, delete, or insert pages. Pages in the API are 1-based."""
    with _LOCK:
        doc = fitz.open(pdf_path)
        try:
            page = _page(doc, page_number)
            old_index = page_number - 1
            updated = [dict(mark) for mark in marks]
            if action == "rotate":
                page.set_rotation((page.rotation + 90) % 360)
            elif action == "crop":
                if rect is None:
                    raise ValueError("Select a rectangular area to crop.")
                area = (fitz.Rect(*rect) * page.derotation_matrix) & page.cropbox
                if area.is_empty or area.width < 20 or area.height < 20:
                    raise ValueError("The crop area is too small or outside the page.")
                page.set_cropbox(area)
            elif action == "resize":
                sizes = {"letter": (612.0, 792.0), "a4": (595.28, 841.89), "legal": (612.0, 1008.0), "original": None}
                key = (page_size or "").lower()
                if key not in sizes:
                    raise ValueError("Choose Letter, A4, Legal, or Original page size.")
                if key == "original":
                    page.set_cropbox(page.mediabox)
                else:
                    width, height = sizes[key]  # type: ignore[misc]
                    page.set_mediabox(fitz.Rect(0, 0, width, height))
                    page.set_cropbox(page.mediabox)
            elif action == "delete":
                if doc.page_count <= 1:
                    raise ValueError("A package must contain at least one page.")
                doc.delete_page(old_index)
                updated = [
                    {**mark, "page": int(mark["page"]) - 1 if int(mark["page"]) > old_index else int(mark["page"])}
                    for mark in updated
                    if int(mark.get("page", -1)) != old_index
                ]
                page_number = min(page_number, doc.page_count)
            elif action == "reorder":
                if target_page is None or target_page < 1 or target_page > doc.page_count:
                    raise ValueError("Choose a destination page in this package.")
                new_index = target_page - 1
                order = list(range(doc.page_count))
                moved = order.pop(old_index)
                order.insert(new_index, moved)
                doc.select(order)
                def moved_index(index: int) -> int:
                    if index == old_index:
                        return new_index
                    if old_index < new_index and old_index < index <= new_index:
                        return index - 1
                    if new_index < old_index and new_index <= index < old_index:
                        return index + 1
                    return index
                updated = [{**mark, "page": moved_index(int(mark["page"]))} for mark in updated]
                page_number = target_page
            elif action == "insert":
                if not inserted_pdf:
                    raise ValueError("Choose a PDF to insert.")
                source = fitz.open(stream=inserted_pdf, filetype="pdf")
                try:
                    if source.page_count == 0:
                        raise ValueError("The selected PDF has no pages.")
                    doc.insert_pdf(source, start_at=old_index)
                    updated = [
                        {**mark, "page": int(mark["page"]) + source.page_count if int(mark["page"]) >= old_index else int(mark["page"])}
                        for mark in updated
                    ]
                    page_number = old_index + 1
                finally:
                    source.close()
            else:
                raise ValueError("Unknown page operation.")
            tmp = _temporary_pdf_path(pdf_path)
            doc.save(tmp, garbage=3, deflate=True)
            page_count = doc.page_count
        except (fitz.FileDataError, RuntimeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
        finally:
            doc.close()
        tmp.replace(pdf_path)
        _PNG_CACHE.clear()
        save_marks(pdf_path, updated)
        _sync_saved_copy(pdf_path, copy_path)
    return page_number, page_count, updated


def add_text(pdf_path: Path, page_number: int, x: float, y: float, text: str, copy_path: Path | None = None) -> None:
    value = (text or "").strip()
    if not value or len(value) > 2000:
        raise ValueError("Enter text between 1 and 2,000 characters.")
    with _LOCK:
        doc = fitz.open(pdf_path)
        try:
            page = _page(doc, page_number)
            if not (page.rect.x0 <= x < page.rect.x1 and page.rect.y0 <= y < page.rect.y1):
                raise ValueError("Click inside the page to place text.")
            point = fitz.Point(x, y) * page.derotation_matrix
            page.insert_text(point, value, fontsize=11, fontname="helv", color=(0.08, 0.12, 0.2))
            tmp = _temporary_pdf_path(pdf_path)
            doc.save(tmp, garbage=3, deflate=True)
        finally:
            doc.close()
        tmp.replace(pdf_path)
        _PNG_CACHE.clear()
        _sync_saved_copy(pdf_path, copy_path)


def add_highlight(
    pdf_path: Path,
    page_number: int,
    rect: tuple[float, float, float, float],
    copy_path: Path | None = None,
) -> None:
    with _LOCK:
        doc = fitz.open(pdf_path)
        try:
            page = _page(doc, page_number)
            display_area = fitz.Rect(*rect) & page.rect
            if display_area.is_empty or display_area.width < 2 or display_area.height < 2:
                raise ValueError("Drag over an area inside the page to highlight it.")
            area = (display_area * page.derotation_matrix) & page.cropbox
            page.add_highlight_annot(area)
            tmp = _temporary_pdf_path(pdf_path)
            doc.save(tmp, garbage=3, deflate=True)
        finally:
            doc.close()
        tmp.replace(pdf_path)
        _PNG_CACHE.clear()
        _sync_saved_copy(pdf_path, copy_path)


def search_pdf(pdf_path: Path, query: str, limit: int = 100) -> list[dict]:
    phrase = " ".join((query or "").split())
    if not phrase:
        return []
    if len(phrase) > 200:
        raise ValueError("Search text must be 200 characters or fewer.")
    results: list[dict] = []
    with _LOCK:
        doc = fitz.open(pdf_path)
        try:
            for index, page in enumerate(doc):
                for found in page.search_for(phrase):
                    display = found * page.rotation_matrix
                    results.append({
                        "page": index + 1,
                        "x0": float(display.x0),
                        "y0": float(display.y0),
                        "x1": float(display.x1),
                        "y1": float(display.y1),
                        "text": phrase,
                    })
                    if len(results) >= limit:
                        return results
        finally:
            doc.close()
    return results


def update_bookmark(pdf_path: Path, action: str, *, index: int | None = None, title: str = "", page: int = 1, level: int = 1) -> list[dict]:
    clean_title = " ".join((title or "").split())
    if action in {"add", "rename"} and (not clean_title or len(clean_title) > 120):
        raise ValueError("Bookmark title must be between 1 and 120 characters.")
    with _LOCK:
        doc = fitz.open(pdf_path)
        try:
            toc = [[int(row[0]), str(row[1]), int(row[2])] for row in doc.get_toc()]
            if action == "add":
                if not 1 <= page <= doc.page_count:
                    raise ValueError("Choose a valid destination page.")
                if level not in (1, 2):
                    raise ValueError("Bookmarks can be top-level or one level nested.")
                toc.append([level, clean_title, page])
            elif action in {"rename", "delete"}:
                if index is None or not 0 <= index < len(toc):
                    raise ValueError("Select a bookmark first.")
                if action == "rename":
                    if not 1 <= page <= doc.page_count:
                        raise ValueError("Choose a valid destination page.")
                    toc[index] = [toc[index][0], clean_title, page]
                else:
                    removed_level = toc[index][0]
                    del toc[index]
                    if removed_level == 1 and index < len(toc):
                        while index < len(toc) and toc[index][0] > removed_level:
                            del toc[index]
            else:
                raise ValueError("Unknown bookmark operation.")
            doc.set_toc(toc, collapse=0)
            from services.bookmark_service import _normalize_outline_destinations

            _normalize_outline_destinations(doc)
            tmp = _temporary_pdf_path(pdf_path)
            doc.save(tmp, garbage=3, deflate=True)
        finally:
            doc.close()
        tmp.replace(pdf_path)
        _PNG_CACHE.clear()
    return [{"level": row[0], "title": row[1], "page": row[2]} for row in toc]


def validate_bookmarks(pdf_path: Path) -> dict:
    problems: list[dict] = []
    with _LOCK:
        doc = fitz.open(pdf_path)
        try:
            toc = doc.get_toc()
            for index, (level, title, page_number, *_rest) in enumerate(toc):
                if page_number < 1 or page_number > doc.page_count:
                    problems.append({"index": index, "title": title, "page": page_number, "issue": "Destination is outside the document."})
                    continue
                body = " ".join((doc[page_number - 1].get_text("text") or "").lower().split())
                normalized_title = " ".join(title.lower().split())
                tokens = [token for token in re.findall(r"[a-z0-9]+", normalized_title) if len(token) > 2]
                matched = any(token in body for token in tokens)
                if not body.strip():
                    problems.append({"index": index, "title": title, "page": page_number, "issue": "Destination page has no extractable text; verify visually."})
                elif tokens and not matched:
                    problems.append({"index": index, "title": title, "page": page_number, "issue": "Bookmark title was not found on its destination page; verify visually."})
            return {"valid": not problems, "page_count": doc.page_count, "bookmark_count": len(toc), "issues": problems}
        finally:
            doc.close()


def add_secure_redaction(pdf_path: Path, page_number: int, rect: tuple[float, float, float, float]) -> int:
    """Permanently remove text and redact touched image pixels and line art."""
    with _LOCK:
        doc = fitz.open(pdf_path)
        try:
            page = _page(doc, page_number)
            area = (fitz.Rect(*rect) * page.derotation_matrix) & page.cropbox
            if area.is_empty or area.width < 2 or area.height < 2:
                raise ValueError("Select an area inside the page to redact.")
            removed_chars = sum(
                len(span.get("text", ""))
                for block in page.get_text("dict").get("blocks", []) if block.get("type") == 0
                for line in block.get("lines", [])
                for span in line.get("spans", [])
                if fitz.Rect(span["bbox"]).intersects(area)
            )
            for annotation in list(page.annots() or []):
                if annotation.rect.intersects(area):
                    page.delete_annot(annotation)
            for link in page.get_links():
                if fitz.Rect(link.get("from", (0, 0, 0, 0))).intersects(area):
                    page.delete_link(link)
            page.add_redact_annot(area, fill=(0, 0, 0), cross_out=False)
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_PIXELS,
                graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )
            tmp = _temporary_pdf_path(pdf_path)
            doc.save(tmp, garbage=4, deflate=True, clean=True)
        finally:
            doc.close()
        tmp.replace(pdf_path)
        _PNG_CACHE.clear()
    return removed_chars


def add_annotation(pdf_path: Path, page_number: int, action: str, rect: tuple[float, float, float, float], *, text: str = "", points: list[list[float]] | None = None) -> None:
    value = (text or "").strip()
    if len(value) > 1000:
        raise ValueError("Annotation text must be 1,000 characters or fewer.")
    with _LOCK:
        doc = fitz.open(pdf_path)
        try:
            page = _page(doc, page_number)
            display = fitz.Rect(*rect) & page.rect
            box = display * page.derotation_matrix
            if display.is_empty or display.width < 2 or display.height < 2:
                raise ValueError("Select an area inside the page for the annotation.")
            if action in {"note", "stamp"}:
                if not value:
                    raise ValueError("Enter annotation text first.")
                fill = (1.0, 0.97, 0.72) if action == "note" else (1.0, 0.88, 0.88)
                color = (0.1, 0.1, 0.1) if action == "note" else (0.7, 0.05, 0.05)
                page.add_freetext_annot(box, value, fontsize=11, fontname="Helv", text_color=color, fill_color=fill)
            elif action == "rectangle":
                page.add_rect_annot(box)
            elif action == "circle":
                page.add_circle_annot(box)
            elif action == "line":
                page.add_line_annot(box.tl, box.br)
            elif action == "signature":
                if not points or len(points) < 2:
                    raise ValueError("Draw a signature stroke on the page.")
                stroke = []
                for point in points[:500]:
                    mapped = fitz.Point(float(point[0]), float(point[1])) * page.derotation_matrix
                    stroke.append((float(mapped.x), float(mapped.y)))
                page.add_ink_annot([stroke])
            else:
                raise ValueError("Choose a supported note, shape, stamp, or signature tool.")
            tmp = _temporary_pdf_path(pdf_path)
            doc.save(tmp, garbage=3, deflate=True)
        finally:
            doc.close()
        tmp.replace(pdf_path)
        _PNG_CACHE.clear()


def _temporary_pdf_path(pdf_path: Path) -> Path:
    return pdf_path.with_name(pdf_path.stem + ".edit" + pdf_path.suffix)


def _sync_saved_copy(pdf_path: Path, copy_path: Path | None) -> None:
    if copy_path is None or not copy_path.parent.exists():
        return
    try:
        copy_path.write_bytes(pdf_path.read_bytes())
    except OSError:
        pass


def _page(doc: fitz.Document, page_number: int) -> fitz.Page:
    if page_number < 1 or page_number > doc.page_count:
        raise ValueError(f"Page {page_number} is not in this package.")
    return doc[page_number - 1]


def _lines(page: fitz.Page) -> list[dict]:
    grouped: dict[tuple[int, int], list] = {}
    for word in page.get_text("words") or []:
        grouped.setdefault((int(word[5]), int(word[6])), []).append(word)
    lines: list[dict] = []
    for key in sorted(grouped):
        words = sorted(grouped[key], key=lambda item: item[0])
        rect = fitz.Rect(words[0][:4])
        for word in words[1:]:
            rect.include_rect(fitz.Rect(word[:4]))
        text = " ".join(str(word[4]) for word in words).strip()
        if not text:
            continue
        lines.append(
            {
                "x0": float(rect.x0),
                "y0": float(rect.y0),
                "x1": float(rect.x1),
                "y1": float(rect.y1),
                "text": text,
            }
        )
    return lines


def _spans_in(page: fitz.Page, box: fitz.Rect) -> list[dict]:
    found: list[dict] = []
    nearby: list[tuple[float, dict]] = []
    padded = fitz.Rect(box.x0 - 2, box.y0 - 3, box.x1 + 2, box.y1 + 3)
    for raw in page.get_text("dict").get("blocks") or []:
        if raw.get("type") != 0:
            continue
        for line in raw.get("lines") or []:
            for span in line.get("spans") or []:
                rect = fitz.Rect(span["bbox"])
                if rect.intersects(box) and _mostly_inside(rect, box):
                    found.append(span)
                    continue
                if rect.intersects(padded):
                    center = fitz.Point((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)
                    nearby.append((abs(center.y - (box.y0 + box.y1) / 2), span))
    if found:
        return found
    nearby.sort(key=lambda item: item[0])
    if not nearby:
        return []
    closest = nearby[0][1]
    mid = (closest["bbox"][1] + closest["bbox"][3]) / 2
    return [
        span
        for _dist, span in nearby
        if abs((span["bbox"][1] + span["bbox"][3]) / 2 - mid) <= 4
    ]


def _replacement_plan(page: fitz.Page, rect: tuple[float, float, float, float], new_text: str) -> dict | None:
    text = " ".join((new_text or "").split())
    if len(text) > _MAX_TEXT:
        raise ValueError(f"Keep the replacement under {_MAX_TEXT} characters.")
    box = fitz.Rect(*rect) * page.derotation_matrix
    spans = _spans_in(page, box)
    if not spans:
        raise ValueError("No text on that line. Click the words, then Apply.")
    spans.sort(key=lambda span: (span["bbox"][1], span["bbox"][0]))
    union = fitz.Rect(spans[0]["bbox"])
    for span in spans[1:]:
        union.include_rect(fitz.Rect(span["bbox"]))
    old = " ".join((span.get("text") or "").strip() for span in spans).strip()
    if old == text:
        return None
    span = spans[0]
    origin = span.get("origin") or (span["bbox"][0], span["bbox"][3])
    size = float(span.get("size") or 11)
    fontname = _base_font(str(span.get("font") or ""), int(span.get("flags") or 0))
    available_width = _replacement_width(page, union, spans)
    try:
        required_width = float(fitz.get_text_length(text, fontname=fontname, fontsize=size)) if text else 0
    except Exception:
        fontname = "helv"
        required_width = float(fitz.get_text_length(text, fontname=fontname, fontsize=size)) if text else 0
    if text and required_width > available_width:
        size *= available_width / required_width
    if text and size < _MIN_REPLACEMENT_FONT_SIZE:
        raise ValueError(
            f"That replacement will not fit in the original line, even at {_MIN_REPLACEMENT_FONT_SIZE:g} pt. "
            "Use shorter text or edit the PDF in a full editor."
        )
    return {
        "spans": spans,
        "union": union,
        "span": span,
        "point": fitz.Point(float(origin[0]), float(origin[1])),
        "size": size,
        "fontname": fontname,
        "color": _rgb(span.get("color") or 0),
        "text": text,
    }


def _insert_replacement(page: fitz.Page, plan: dict) -> fitz.Rect | None:
    text = plan["text"]
    if not text:
        return None
    fontname = plan["fontname"]
    try:
        page.insert_text(plan["point"], text, fontsize=plan["size"], fontname=fontname, color=plan["color"])
    except Exception:
        fontname = "helv"
        page.insert_text(plan["point"], text, fontsize=plan["size"], fontname=fontname, color=plan["color"])
    return _written_rect(plan["span"], text, fontname, plan["size"])


def _mostly_inside(rect: fitz.Rect, box: fitz.Rect) -> bool:
    overlap = rect & box
    if overlap.is_empty or rect.height <= 0:
        return False
    return overlap.height >= rect.height * 0.5


def _written_rect(span: dict, updated: str, fontname: str, size: float) -> fitz.Rect:
    origin = span.get("origin") or (span["bbox"][0], span["bbox"][3])
    try:
        width = float(fitz.get_text_length(updated, fontname=fontname, fontsize=size))
    except Exception:
        width = float(fitz.get_text_length(updated, fontname="helv", fontsize=size))
    x0 = float(origin[0])
    baseline = float(origin[1])
    return fitz.Rect(x0 - 0.6, baseline - size, x0 + max(width, 4) + 0.6, baseline + size * 0.3)


def _replacement_width(page: fitz.Page, old: fitz.Rect, selected: list[dict]) -> float:
    """Use available space on the line, stopping before the next text span."""
    start_x = min(float(span["bbox"][0]) for span in selected)
    end_x = float(page.rect.x1) - 6
    selected_boxes = [fitz.Rect(span["bbox"]) for span in selected]
    for block in page.get_text("dict").get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            for span in line.get("spans") or []:
                rect = fitz.Rect(span["bbox"])
                if any(rect == box for box in selected_boxes):
                    continue
                same_line = rect.y1 > old.y0 and rect.y0 < old.y1
                if same_line and rect.x0 >= old.x1 - 1:
                    end_x = min(end_x, float(rect.x0) - 2)
    return max(end_x - start_x, 1)


def _retarget_marks(
    marks: list[dict],
    page_index: int,
    old: fitz.Rect,
    written: fitz.Rect | None,
) -> list[dict]:
    updated: list[dict] = []
    for mark in marks:
        if int(mark.get("page", -1)) != page_index:
            updated.append(mark)
            continue
        rect = fitz.Rect(mark["x0"], mark["y0"], mark["x1"], mark["y1"])
        if not rect.intersects(old):
            updated.append(mark)
            continue
        if written is None:
            continue
        updated.append(
            {
                **mark,
                "x0": float(written.x0),
                "y0": float(written.y0),
                "x1": float(written.x1),
                "y1": float(written.y1),
            }
        )
    return updated

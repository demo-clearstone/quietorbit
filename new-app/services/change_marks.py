"""Rectangles of text the pipeline rewrote. Preview can paint them; the saved PDF stays clean."""

from __future__ import annotations

import json
from pathlib import Path

import fitz


def add_mark(marks: list[dict] | None, page: int, rect: fitz.Rect, label: str) -> None:
    """Add mark.

    Purpose:
        Add mark.

    Args:
        marks: Highlight rectangles already collected.
        page: One PDF page.
        rect: Rect. Type: fitz.Rect.
        label: Label. Type: str.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        add_mark(marks, page, rect) returns None.

    Side effects:
        Changes the PDF or the object passed in.
    """
    if marks is None:
        return
    if rect.is_empty or rect.is_infinite:
        return
    marks.append(
        {
            "page": int(page),
            "x0": float(rect.x0),
            "y0": float(rect.y0),
            "x1": float(rect.x1),
            "y1": float(rect.y1),
            "label": label,
        }
    )


def save_marks(pdf_path: Path, marks: list[dict]) -> None:
    """Saving the highlight marks.

    Purpose:
        Saving the highlight marks.

    Args:
        pdf_path: Path to a PDF on disk.
        marks: Highlight rectangles already collected for the PDF.

    Returns:
        None.

    Raises:
        OSError: A file cannot be read or written.

    Example:
        save_marks(pdf_path, []) returns None.

    Side effects:
        Writes or changes a file on disk.
    """
    path = pdf_path.parent / "highlights.json"
    path.write_text(json.dumps(marks), encoding="utf-8")


def load_marks(pdf_path: Path) -> list[dict]:
    """Load marks.

    Purpose:
        Load marks.

    Args:
        pdf_path: Path to a PDF on disk.

    Returns:
        list[dict].

    Raises:
        OSError: A file cannot be read or written.

    Example:
        load_marks(pdf_path) returns list[dict].

    Side effects:
        None. This function only reads data and returns a value.
    """
    path = pdf_path.parent / "highlights.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list(data) if isinstance(data, list) else []


def apply_highlights(pdf_path: Path, marks: list[dict]) -> bytes:
    """Return a copy with yellow boxes on rewritten text. Does not write that copy to disk.

    Purpose:
        Return a copy with yellow boxes on rewritten text. Does not write that copy to disk.

    Args:
        pdf_path: Path to a PDF on disk.
        marks: Highlight rectangles already collected for the PDF.

    Returns:
        bytes.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        apply_highlights(pdf_path, []) returns bytes.

    Side effects:
        Writes or changes a file on disk.
    """
    doc = fitz.open(pdf_path)
    try:
        for mark in marks:
            page_index = int(mark.get("page", -1))
            if page_index < 0 or page_index >= doc.page_count:
                continue
            rect = fitz.Rect(mark["x0"], mark["y0"], mark["x1"], mark["y1"])
            if rect.is_empty:
                continue
            doc[page_index].draw_rect(
                rect,
                color=(0.72, 0.45, 0.0),
                fill=(1, 0.86, 0.2),
                fill_opacity=0.45,
                width=0.7,
                overlay=True,
            )
        return doc.tobytes(deflate=True, garbage=0)
    finally:
        doc.close()

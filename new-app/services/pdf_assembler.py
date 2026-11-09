from __future__ import annotations

import re

from fastapi import HTTPException
import fitz

from config.settings import MAX_FILE_BYTES, MAX_FILES
from services import file_order

SECTION_KEY = "MOASection"


def tag_pages(doc: fitz.Document, start: int, end: int, section: str) -> None:
    """Record the report section on pages ``start`` to ``end - 1`` so bookmarks survive heading changes."""
    for index in range(start, end):
        doc.xref_set_key(doc[index].xref, SECTION_KEY, f"({section})")


def page_section(page: fitz.Page) -> str | None:
    """Return the section tag written by ``tag_pages``, or ``None`` when the page has none."""
    kind, value = page.parent.xref_get_key(page.xref, SECTION_KEY)
    return value if kind == "string" and value else None


def _test_results_first(source: fitz.Document, filename: str) -> bool:
    """Move an ADP/ACP report's TEST RESULTS page to its own first page."""
    spec = file_order.matched_spec(filename)
    if not spec or spec.get("name") != "ADP/ACP" or source.page_count < 2:
        return False
    result_page = None
    for index, page in enumerate(source):
        lines = [line.strip() for line in (page.get_text("text") or "").splitlines() if line.strip()]
        if any(re.fullmatch(r"TEST\s+RESULTS", line, re.I) for line in lines[:8]):
            result_page = index
            break
    if result_page is None or result_page == 0:
        return False
    source.select([result_page, *[index for index in range(source.page_count) if index != result_page]])
    return True


def merge_pdfs(uploads: list[tuple[str, bytes]]) -> fitz.Document:
    """Merge PDFs in list order. Each item is (filename, bytes).

    Purpose:
        Merge PDFs in list order. Each item is (filename, bytes).

    Args:
        uploads: List of (file name, file bytes).

    Returns:
        fitz.Document.

    Raises:
        OSError: A file cannot be read or written. HTTPException: The assembly input is not usable. A closed PDF raises from PyMuPDF.

    Example:
        merge_pdfs(data) returns fitz.Document.

    Side effects:
        Changes one of the objects passed in.
    """
    if len(uploads) < 1:
        raise HTTPException(status_code=400, detail="Upload at least one PDF")
    if len(uploads) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_FILES} PDF files")

    combined = fitz.open()
    try:
        with file_order.use_filename_batch([name for name, _data in uploads]):
            for name, data in uploads:
                if len(data) > MAX_FILE_BYTES:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{name} exceeds {MAX_FILE_BYTES // (1024 * 1024)} MB limit",
                    )
                if not data:
                    raise HTTPException(status_code=400, detail=f"{name} is empty")
                try:
                    source = fitz.open(stream=data, filetype="pdf")
                except Exception as exc:
                    raise HTTPException(
                        status_code=400,
                        detail=f"{name} is not a readable PDF ({exc})",
                    ) from exc
                try:
                    if source.is_encrypted:
                        source.authenticate("")
                    if source.is_encrypted:
                        raise HTTPException(
                            status_code=400,
                            detail=f"{name} is encrypted and cannot be assembled",
                        )
                    if source.page_count < 1:
                        raise HTTPException(status_code=400, detail=f"{name} has no pages")
                    _test_results_first(source, name)
                    first = combined.page_count
                    combined.insert_pdf(source)
                    spec = file_order.matched_spec(name)
                    if spec and spec.get("name"):
                        tag_pages(combined, first, combined.page_count, str(spec["name"]))
                finally:
                    source.close()
    except HTTPException:
        combined.close()
        raise
    except Exception:
        combined.close()
        raise
    return combined

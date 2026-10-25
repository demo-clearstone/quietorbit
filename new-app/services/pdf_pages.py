from __future__ import annotations

from pathlib import Path

import fitz


def pdf_page_count(data: bytes) -> int:
    """Pdf page count.

    Purpose:
        Pdf page count.

    Args:
        data: Raw file bytes.

    Returns:
        int.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        pdf_page_count(data) returns int.

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return max(1, int(doc.page_count or 1))
    finally:
        doc.close()


def pdf_page_count_path(path: Path) -> int:
    """Pdf page count path.

    Purpose:
        Pdf page count path.

    Args:
        path: Path to a file on disk.

    Returns:
        int.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        pdf_page_count_path(path) returns int.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if path.suffix.lower() != ".pdf":
        return 1
    try:
        doc = fitz.open(path)
        try:
            return max(1, int(doc.page_count or 1))
        finally:
            doc.close()
    except Exception:
        return 1


def pdf_page_texts(data: bytes) -> list[str]:
    """Pdf page texts.

    Purpose:
        Pdf page texts.

    Args:
        data: Raw file bytes.

    Returns:
        list[str].

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        pdf_page_texts(data) returns list[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return [(page.get_text("text") or "") for page in doc]
    finally:
        doc.close()


def pdf_page_texts_path(path: Path) -> list[str]:
    """Pdf page texts path.

    Purpose:
        Pdf page texts path.

    Args:
        path: Path to a file on disk.

    Returns:
        list[str].

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        pdf_page_texts_path(path) returns list[str].

    Side effects:
        None. This function only reads data and returns a value.
    """
    if path.suffix.lower() != ".pdf":
        return []
    try:
        doc = fitz.open(path)
        try:
            return [(page.get_text("text") or "") for page in doc]
        finally:
            doc.close()
    except Exception:
        return []


def extract_pdf_page(data: bytes, page: int) -> bytes:
    """Return a one-page PDF. page is 1-based.

    Purpose:
        Return a one-page PDF. page is 1-based.

    Args:
        data: Raw file bytes.
        page: One PDF page.

    Returns:
        bytes.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        extract_pdf_page(data, page) returns bytes.

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        index = page - 1
        if index < 0 or index >= doc.page_count:
            raise ValueError(f"page {page} is not in this PDF ({doc.page_count} pages)")
        out = fitz.open()
        out.insert_pdf(doc, from_page=index, to_page=index)
        return out.tobytes()
    finally:
        doc.close()


def paged_filename(name: str, page: int) -> str:
    """Paged filename.

    Purpose:
        Paged filename.

    Args:
        name: File name or section name.
        page: One PDF page.

    Returns:
        str.

    Raises:
        None.

    Example:
        paged_filename("text", page) returns str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    path = Path(name)
    return f"{path.stem}_p{page:02d}{path.suffix}"


def expand_uploads_by_page(
    uploads: list[tuple[str, bytes]],
    names: list[str],
    pages: list[int],
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Build the merge list from UI rows. page <= 0 means the whole file.

    Purpose:
        Build the merge list from UI rows. page <= 0 means the whole file.

    Args:
        uploads: Pairs of file name and file bytes.
        names: Names. Type: list[str].
        pages: Pages. Type: list[int].

    Returns:
        a tuple[list[tuple[str, bytes]], list[str]].

    Raises:
        None.

    Example:
        expand_uploads_by_page(uploads, [], []) returns a tuple[list[tuple[str, bytes]], list[str]].

    Side effects:
        None. This function only reads data and returns a value.
    """
    by_name = {name: data for name, data in uploads}
    ordered: list[tuple[str, bytes]] = []
    warnings: list[str] = []
    whole_used: set[str] = set()
    for index, name in enumerate(names):
        if not name:
            continue
        data = by_name.get(name)
        if data is None:
            warnings.append(f"Not in folder or upload (skipped): {name}")
            continue
        page = pages[index] if index < len(pages) else 0
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = 0
        if not name.lower().endswith(".pdf") or page <= 0:
            if name in whole_used:
                continue
            whole_used.add(name)
            ordered.append((name, data))
            continue
        try:
            ordered.append((paged_filename(name, page), extract_pdf_page(data, page)))
        except Exception as exc:
            warnings.append(f"Could not use {name} page {page}: {exc}")
    return ordered, warnings

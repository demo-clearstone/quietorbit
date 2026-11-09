from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from config.settings import MAX_FILE_BYTES, MAX_FILES
from services.file_order import list_file_meta, use_filename_batch
from services.pdf_pages import pdf_page_count_path, pdf_page_texts_path


def _resolved_dir(raw_path: str) -> Path:
    """Resolved dir.

    Purpose:
        Resolved dir.

    Args:
        raw_path: Raw path. Type: str.

    Returns:
        a Path.

    Raises:
        HTTPException: The assembly input is not usable.

    Example:
        _resolved_dir("text") returns a Path.

    Side effects:
        None. This function only reads data and returns a value.
    """
    path = Path(raw_path.strip()).expanduser()
    try:
        path = path.resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid folder path: {exc}") from exc
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Folder not found: {raw_path}")
    return path


def _folder_entries(path: Path) -> tuple[list[Path], list[str]]:
    """Folder entries.

    Purpose:
        Folder entries.

    Args:
        path: Path to a file on disk.

    Returns:
        tuple[list[Path], list[str]].

    Raises:
        None.

    Example:
        _folder_entries(path) returns tuple[list[Path], list[str]].

    Side effects:
        None. This function only reads data and returns a value.
    """
    skipped: list[str] = []
    source_paths: list[Path] = []
    for item in sorted(path.iterdir(), key=lambda p: p.name.lower()):
        if not item.is_file() or item.name.startswith("~$") or item.name.startswith("."):
            continue
        if item.suffix.lower() in {".pdf", ".xlsx", ".xls"}:
            source_paths.append(item)
        else:
            skipped.append(item.name)
    return source_paths, skipped


def list_folder_files(raw_path: str) -> dict:
    """Return PDF/Excel names in a folder so the UI can show Up/Down/Remove.

    Purpose:
        Return PDF/Excel names in a folder so the UI can show Up/Down/Remove.

    Args:
        raw_path: Raw path. Type: str.

    Returns:
        a dict.

    Raises:
        HTTPException: The assembly input is not usable.

    Example:
        list_folder_files("text") returns a dict.

    Side effects:
        None. This function only reads data and returns a value.
    """
    path = _resolved_dir(raw_path)
    source_paths, skipped = _folder_entries(path)
    files = []
    warnings: list[str] = [f"Skipped non-PDF (convert to PDF before combine): {name}" for name in skipped]
    with use_filename_batch([item.name for item in source_paths]):
        for item in source_paths:
            pages = pdf_page_count_path(item)
            page_texts = pdf_page_texts_path(item) if item.suffix.lower() == ".pdf" else []
            meta = list_file_meta(item.name, item.stat().st_size, pages, page_texts)
            files.append(meta)
            if meta["split"]:
                warnings.append(f"{item.name} has {pages} pages; each page is listed so you can reorder.")
    files.sort(key=lambda item: (item["rank"], item["name"].lower()))
    pdfs = [item for item in files if item["name"].lower().endswith(".pdf")]
    if not pdfs:
        raise HTTPException(status_code=400, detail=f"No PDF files in folder: {path}")
    if len(pdfs) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_FILES} PDF files")
    return {"path": str(path), "files": files, "warnings": warnings}


def apply_file_order(
    uploads: list[tuple[str, bytes]],
    file_order: list[str],
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Keep only named files, in the UI order. Missing names become warnings.

    Purpose:
        Keep only named files, in the UI order. Missing names become warnings.

    Args:
        uploads: Pairs of file name and file bytes.
        file_order: File order. Type: list[str].

    Returns:
        a tuple[list[tuple[str, bytes]], list[str]].

    Raises:
        None.

    Example:
        apply_file_order(uploads, []) returns a tuple[list[tuple[str, bytes]], list[str]].

    Side effects:
        Changes the PDF or the object passed in.
    """
    by_name = {name: data for name, data in uploads}
    ordered: list[tuple[str, bytes]] = []
    warnings: list[str] = []
    seen: set[str] = set()
    for name in file_order:
        if not name or name in seen:
            continue
        seen.add(name)
        data = by_name.get(name)
        if data is None:
            warnings.append(f"Not in folder (skipped): {name}")
            continue
        ordered.append((name, data))
    return ordered, warnings


def load_pdfs_from_folder(raw_path: str) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Read PDFs and the Val Assembly Excel from a Valuation Package folder.

    Purpose:
        Read PDFs and the Val Assembly Excel from a Valuation Package folder.

    Args:
        raw_path: Raw path. Type: str.

    Returns:
        a tuple[list[tuple[str, bytes]], list[str]].

    Raises:
        HTTPException: The assembly input is not usable. OSError: A file cannot be read or written.

    Example:
        load_pdfs_from_folder("text") returns a tuple[list[tuple[str, bytes]], list[str]].

    Side effects:
        None. This function only reads data and returns a value.
    """
    path = _resolved_dir(raw_path)
    source_paths, skipped = _folder_entries(path)
    pdf_paths = [item for item in source_paths if item.suffix.lower() == ".pdf"]
    if not pdf_paths:
        raise HTTPException(status_code=400, detail=f"No PDF files in folder: {path}")
    if len(pdf_paths) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_FILES} PDF files")

    uploads: list[tuple[str, bytes]] = []
    for pdf in source_paths:
        data = pdf.read_bytes()
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"{pdf.name} exceeds {MAX_FILE_BYTES // (1024 * 1024)} MB limit",
            )
        if not data:
            raise HTTPException(status_code=400, detail=f"{pdf.name} is empty")
        uploads.append((pdf.name, data))

    warnings = [
        f"Skipped non-PDF (convert to PDF before combine): {name}" for name in skipped
    ]
    warnings.append(f"Loaded {len(uploads)} PDF(s) from {path}")
    return uploads, warnings

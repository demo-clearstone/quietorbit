from __future__ import annotations

import asyncio
import re
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response

from config.settings import MAX_FILE_BYTES, MAX_FILES, OUTPUT_DIR
from models.job import JobResult
from services.change_marks import apply_highlights, load_marks
from services.file_order import list_file_meta
from services.folder_loader import apply_file_order, list_folder_files, load_pdfs_from_folder
from services.pdf_pages import expand_uploads_by_page, pdf_page_count, pdf_page_texts
from services.orchestrator import process_uploads

router = APIRouter()
JOBS: dict[str, JobResult] = {}
# Windows closes one large POST (Chrome: net::ERR_FAILED). Pieces stay in memory until Process.
_PARTS: dict[str, dict] = {}
_BLOBS: dict[str, tuple[str, bytes]] = {}
_UPLOAD_ID = re.compile(r"[A-Za-z0-9_-]{8,80}")
_CHUNK_LIMIT = 48 * 1024


def _saved_pdf(job_id: str) -> tuple[Path, str] | None:
    """Find the assembled PDF in memory or on disk (survives a server restart)."""
    if not job_id.isalnum() or len(job_id) > 40:
        return None
    job = JOBS.get(job_id)
    if job:
        path = Path(job.pdf_path)
        if path.is_file():
            return path, job.filename
    job_dir = OUTPUT_DIR / job_id
    if not job_dir.is_dir():
        return None
    pdfs = sorted(job_dir.glob("*.pdf"))
    if not pdfs:
        return None
    return pdfs[0], pdfs[0].name


@router.post("/jobs", response_model=JobResult)
async def create_job(
    request: Request,
    files: list[UploadFile] | None = File(default=None),
    source_path: str = Form(default=""),
    auto_order: bool = Form(default=True),
    rewrite_sources: bool = Form(default=False),
    check_assembly_stops: bool = Form(default=False),
    file_order: list[str] | None = Form(default=None),
    item_name: list[str] | None = Form(default=None),
    item_page: list[int] | None = Form(default=None),
    upload_id: list[str] | None = Form(default=None),
) -> JobResult:
    uploads: list[tuple[str, bytes]] = []
    warnings: list[str] = []
    folder = (source_path or "").strip()
    ordered_names = [name for name in (file_order or []) if (name or "").strip()]
    row_names = [name for name in (item_name or []) if (name or "").strip()]
    if folder:
        folder_uploads, folder_warnings = load_pdfs_from_folder(folder)
        warnings.extend(folder_warnings)
        if ordered_names and not row_names:
            folder_uploads, order_warnings = apply_file_order(folder_uploads, ordered_names)
            warnings.extend(order_warnings)
            warnings.append("Using the file order shown in the list.")
        uploads.extend(folder_uploads)

    seen_ids: set[str] = set()
    for token in upload_id or []:
        if not token or token in seen_ids:
            continue
        kept = _stored_upload(token)
        if kept is None:
            raise HTTPException(
                status_code=400,
                detail="That file is no longer on the server. Add it again, then click Process package.",
            )
        seen_ids.add(token)
        uploads.append(kept)

    for upload in files or []:
        name = upload.filename or ""
        if not name or name.startswith("~$"):
            continue
        if not name.lower().endswith((".pdf", ".xlsx", ".xls")):
            raise HTTPException(status_code=400, detail=f"{name} must be a PDF or Excel file")
        data = await upload.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"{name} is empty")
        uploads.append((name, data))

    if row_names:
        row_pages = list(item_page or [])
        uploads, page_warnings = expand_uploads_by_page(uploads, row_names, row_pages)
        warnings.extend(page_warnings)
        warnings.append("Using the page order shown in the list.")

    if not uploads:
        raise HTTPException(
            status_code=400,
            detail="Upload PDF files or enter a Valuation Package folder path",
        )

    try:
        result = process_uploads(
            uploads,
            auto_order=auto_order,
            extra_warnings=warnings,
            source_folder=folder or None,
            rewrite_sources=rewrite_sources,
            check_assembly_stops=check_assembly_stops,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not process PDFs: {exc}") from exc
    base = str(request.base_url).rstrip("/")
    result.download_url = f"{base}/api/jobs/{result.job_id}/pdf"
    result.preview_url = f"{base}/api/jobs/{result.job_id}/preview"
    JOBS[result.job_id] = result
    return result


@router.get("/folder")
def list_source_folder(path: str = "") -> dict:
    folder = (path or "").strip()
    if not folder:
        raise HTTPException(status_code=400, detail="Enter a Valuation Package folder path")
    return list_folder_files(folder)


def _stored_upload(token: str) -> tuple[str, bytes] | None:
    if not _UPLOAD_ID.fullmatch(token or ""):
        return None
    return _BLOBS.get(token)


def _remember_blob(upload_id: str, name: str, data: bytes) -> None:
    _BLOBS[upload_id] = (name, data)
    while len(_BLOBS) > MAX_FILES:
        _BLOBS.pop(next(iter(_BLOBS)))


async def _describe_file(name: str, data: bytes) -> dict:
    pages = 1
    page_texts: list[str] = []
    if name.lower().endswith(".pdf") and data:
        pages, page_texts = await asyncio.to_thread(_pdf_pages, data)
    try:
        return list_file_meta(name, len(data), pages, page_texts)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not read {name}: {exc}") from exc


@router.post("/upload-part")
async def upload_part(
    upload_id: str = Form(default=""),
    name: str = Form(default=""),
    index: int = Form(default=0),
    total: int = Form(default=1),
    chunk: UploadFile | None = File(default=None),
) -> dict:
    """Accept one small slice of a file. The last slice returns page labels."""
    token = (upload_id or "").strip()
    if not _UPLOAD_ID.fullmatch(token):
        raise HTTPException(status_code=400, detail="Upload id is not valid")
    filename = (name or "").strip()
    if not filename or filename.startswith("~$"):
        raise HTTPException(status_code=400, detail="Choose a PDF or Excel file")
    if not filename.lower().endswith((".pdf", ".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail=f"{filename} must be a PDF or Excel file")
    if total < 1 or total > 4000 or index < 0 or index >= total:
        raise HTTPException(status_code=400, detail="Upload piece is out of range")
    piece = await chunk.read() if chunk is not None else b""
    if len(piece) > _CHUNK_LIMIT:
        raise HTTPException(status_code=400, detail="Upload piece is too large")

    finished = _BLOBS.get(token)
    if finished and index == total - 1 and not _PARTS.get(token):
        stored_name, stored = finished
        return {"complete": True, "upload_id": token, "file": await _describe_file(stored_name, stored)}

    bucket = _PARTS.setdefault(token, {"name": filename, "total": total, "parts": {}})
    if bucket["name"] != filename or bucket["total"] != total:
        raise HTTPException(status_code=400, detail="Upload pieces do not match")
    bucket["parts"][index] = piece
    if len(bucket["parts"]) < total:
        return {"complete": False, "upload_id": token}

    missing = [number for number in range(total) if number not in bucket["parts"]]
    if missing:
        return {"complete": False, "upload_id": token}
    data = b"".join(bucket["parts"][number] for number in range(total))
    _PARTS.pop(token, None)
    if not data:
        raise HTTPException(status_code=400, detail=f"{filename} is empty")
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"{filename} exceeds {MAX_FILE_BYTES // (1024 * 1024)} MB limit",
        )
    _remember_blob(token, filename, data)
    return {"complete": True, "upload_id": token, "file": await _describe_file(filename, data)}


def _pdf_pages(data: bytes) -> tuple[int, list[str]]:
    try:
        return pdf_page_count(data), pdf_page_texts(data)
    except Exception:
        return 1, []


@router.post("/inspect")
async def inspect_uploads(files: list[UploadFile] | None = File(default=None)) -> dict:
    """Return page counts so the UI can list each PDF page for reordering."""
    listed: list[dict] = []
    for upload in files or []:
        name = upload.filename or ""
        if not name or name.startswith("~$"):
            continue
        data = await upload.read()
        pages = 1
        page_texts: list[str] = []
        if name.lower().endswith(".pdf") and data:
            # Fitz blocks. Keep it off the event loop so Windows can finish the upload.
            pages, page_texts = await asyncio.to_thread(_pdf_pages, data)
        try:
            listed.append(list_file_meta(name, len(data or b""), pages, page_texts))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not read {name}: {exc}") from exc
    return {"files": listed}


@router.get("/jobs/{job_id}", response_model=JobResult)
def get_job(job_id: str) -> JobResult:
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/jobs/{job_id}/pdf")
def download_job_pdf(job_id: str) -> FileResponse:
    found = _saved_pdf(job_id)
    if not found:
        raise HTTPException(
            status_code=404,
            detail="Assembled PDF not found. Restart python main.py, then click Process package again. Do not reuse an old preview URL.",
        )
    path, filename = found
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="attachment",
    )


@router.get("/jobs/{job_id}/preview")
def preview_job_pdf(job_id: str, highlight: bool = False) -> Response:
    found = _saved_pdf(job_id)
    if not found:
        raise HTTPException(
            status_code=404,
            detail="Assembled PDF not found. Restart python main.py, then click Process package again. Do not reuse an old preview URL.",
        )
    path, filename = found
    if not highlight:
        return FileResponse(
            path,
            media_type="application/pdf",
            filename=filename,
            content_disposition_type="inline",
            headers={"Cache-Control": "no-store"},
        )
    data = apply_highlights(path, _preview_marks(job_id, path))
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


def _preview_marks(job_id: str, pdf_path: Path) -> list[dict]:
    job = JOBS.get(job_id)
    if job is not None:
        return [item.model_dump() for item in job.highlights]
    return load_marks(pdf_path)


@router.get("/jobs/{job_id}/email")
def download_job_email(job_id: str) -> FileResponse:
    job = JOBS.get(job_id)
    path = Path(job.email_path) if job and job.email_path else None
    if not path or not path.is_file():
        raise HTTPException(status_code=404, detail="Outlook draft not found. Process the package again.")
    return FileResponse(
        path,
        media_type="message/rfc822",
        filename=path.name,
        content_disposition_type="attachment",
    )


@router.get("/jobs/{job_id}/log")
def download_assembly_log(job_id: str) -> FileResponse:
    job = JOBS.get(job_id)
    path = Path(job.log_path) if job and job.log_path else OUTPUT_DIR / "ValAssemblyLog.xlsx"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Val Assembly Log not found. Process a package first.")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=path.name,
        content_disposition_type="attachment",
    )

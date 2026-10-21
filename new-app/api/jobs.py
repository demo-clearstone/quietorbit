from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response

from config.settings import OUTPUT_DIR
from models.job import JobResult
from services.change_marks import apply_highlights, load_marks
from services.file_order import list_file_meta
from services.folder_loader import apply_file_order, list_folder_files, load_pdfs_from_folder
from services.pdf_pages import expand_uploads_by_page, pdf_page_count, pdf_page_texts
from services.orchestrator import process_uploads

router = APIRouter()
JOBS: dict[str, JobResult] = {}


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

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from config.settings import MAX_FILE_BYTES, MAX_FILES, OUTPUT_DIR
from models.job import HighlightMark, JobResult
from services.change_marks import apply_highlights, load_marks
from services.file_order import list_file_meta
from services.preview_view import add_annotation, add_highlight, add_secure_redaction, add_text, modify_pages
from services.preview_view import outline as preview_outline
from services.preview_view import page_lines, page_png, replace_line, search_pdf, update_bookmark, validate_bookmarks
from services.preview_history import abort as abort_edit
from services.preview_history import active_path, commit as commit_edit, edited_copy_path, editable_path, history_state, redo as redo_edit, snapshot_before, undo as undo_edit
from services.folder_loader import apply_file_order, list_folder_files, load_pdfs_from_folder
from services.pdf_pages import expand_uploads_by_page, pdf_page_count, pdf_page_texts
from services.orchestrator import process_uploads
from services.console_trace import read_trace, run_traced, start_trace

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
    check_assembly_stops: bool = Form(default=True),
    file_order: list[str] | None = Form(default=None),
    item_name: list[str] | None = Form(default=None),
    item_page: list[int] | None = Form(default=None),
    upload_id: list[str] | None = Form(default=None),
    trace_id: str = Form(default=""),
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

    if trace_id and not _UPLOAD_ID.fullmatch(trace_id):
        raise HTTPException(400, "Console trace ID is not valid")
    options = dict(
        auto_order=auto_order,
        extra_warnings=warnings,
        source_folder=folder or None,
        rewrite_sources=rewrite_sources,
        check_assembly_stops=check_assembly_stops,
    )
    token = trace_id or f"term_{uuid.uuid4().hex[:12]}"
    start_trace(token)
    try:
        result = await asyncio.to_thread(run_traced, token, process_uploads, uploads, **options)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not process PDFs: {exc}") from exc
    base = str(request.base_url).rstrip("/")
    result.download_url = f"{base}/api/jobs/{result.job_id}/pdf"
    result.preview_url = f"{base}/api/jobs/{result.job_id}/preview"
    JOBS[result.job_id] = result
    return result


@router.get("/console-traces/{trace_id}")
async def console_trace(trace_id: str, after: int = 0) -> dict:
    if not _UPLOAD_ID.fullmatch(trace_id) or after < 0:
        raise HTTPException(400, "Console trace cursor is not valid")
    try:
        return read_trace(trace_id, after)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
        return {"events": [], "status": "waiting", "total": 0, "truncated": False}


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
    original, filename = found
    path = active_path(original)
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


class PreviewEdit(BaseModel):
    page: int = Field(ge=1)
    x0: float
    y0: float
    x1: float
    y1: float
    text: str = ""


class PageOperation(BaseModel):
    action: str
    page: int = Field(ge=1)
    target_page: int | None = Field(default=None, ge=1)
    x0: float | None = None
    y0: float | None = None
    x1: float | None = None
    y1: float | None = None
    page_size: str | None = None


class PreviewAnnotation(BaseModel):
    action: str
    page: int = Field(ge=1)
    x: float | None = None
    y: float | None = None
    x0: float | None = None
    y0: float | None = None
    x1: float | None = None
    y1: float | None = None
    text: str = ""
    points: list[list[float]] = Field(default_factory=list)


class BookmarkOperation(BaseModel):
    action: str
    index: int | None = None
    title: str = ""
    page: int = Field(default=1, ge=1)
    level: int = Field(default=1, ge=1, le=2)


def _job_pdf(job_id: str) -> tuple[Path, str]:
    found = _saved_pdf(job_id)
    if not found:
        raise HTTPException(
            status_code=404,
            detail="Assembled PDF not found. Restart python main.py, then click Process package again.",
        )
    original, filename = found
    return active_path(original), filename


def _editable_job_pdf(job_id: str) -> tuple[Path, str]:
    found = _saved_pdf(job_id)
    if not found:
        raise HTTPException(status_code=404, detail="Assembled PDF not found. Process the package again.")
    original, filename = found
    return editable_path(original), filename


@router.get("/jobs/{job_id}/outline")
def job_outline(job_id: str) -> dict:
    path, _filename = _job_pdf(job_id)
    return preview_outline(path)


@router.get("/jobs/{job_id}/pages/{page_no}")
def job_page_image(job_id: str, page_no: int) -> Response:
    path, _filename = _job_pdf(job_id)
    try:
        data = page_png(path, page_no)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/jobs/{job_id}/pages/{page_no}/thumbnail")
def job_page_thumbnail(job_id: str, page_no: int) -> Response:
    path, _filename = _job_pdf(job_id)
    try:
        data = page_png(path, page_no, scale=0.35)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(content=data, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/jobs/{job_id}/pages/{page_no}/lines")
def job_page_lines(job_id: str, page_no: int) -> dict:
    path, _filename = _job_pdf(job_id)
    try:
        return page_lines(path, page_no)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/edit")
def edit_job_page(job_id: str, body: PreviewEdit) -> dict:
    path, _filename = _editable_job_pdf(job_id)
    job = JOBS.get(job_id)
    marks = _preview_marks(job_id, path)
    snapshot = snapshot_before(path)
    try:
        updated = replace_line(
            path,
            body.page,
            (body.x0, body.y0, body.x1, body.y1),
            body.text,
            marks,
        )
        commit_edit(path, snapshot)
    except ValueError as exc:
        abort_edit(snapshot)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        abort_edit(snapshot)
        raise
    if job is not None:
        job.highlights = [HighlightMark(**item) for item in updated]
    return {"page": body.page, "highlights": updated, "detail": f"Updated page {body.page}."}


@router.post("/jobs/{job_id}/pages/operation")
def operate_job_pages(job_id: str, body: PageOperation) -> dict:
    path, _filename = _editable_job_pdf(job_id)
    job = JOBS.get(job_id)
    marks = _preview_marks(job_id, path)
    if body.action in {"crop"} and None in (body.x0, body.y0, body.x1, body.y1):
        raise HTTPException(status_code=400, detail="Select the page area first.")
    snapshot = snapshot_before(path)
    try:
        page, page_count, updated = modify_pages(
            path,
            body.action,
            body.page,
            marks,
            target_page=body.target_page,
            rect=(body.x0, body.y0, body.x1, body.y1) if None not in (body.x0, body.y0, body.x1, body.y1) else None,
            page_size=body.page_size,
        )
        commit_edit(path, snapshot)
    except ValueError as exc:
        abort_edit(snapshot)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        abort_edit(snapshot)
        raise
    if job is not None:
        job.highlights = [HighlightMark(**item) for item in updated]
    return {"page": page, "page_count": page_count, "detail": f"Page operation complete: {body.action}."}


@router.post("/jobs/{job_id}/pages/insert")
async def insert_job_pages(job_id: str, page: int = Form(ge=1), file: UploadFile = File(...)) -> dict:
    path, _filename = _editable_job_pdf(job_id)
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Choose a PDF file to insert.")
    data = await file.read(MAX_FILE_BYTES + 1)
    if not data or len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail=f"The inserted PDF must be under {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    job = JOBS.get(job_id)
    marks = _preview_marks(job_id, path)
    snapshot = snapshot_before(path)
    try:
        inserted_at, page_count, updated = modify_pages(
            path,
            "insert",
            page,
            marks,
            inserted_pdf=data,
        )
        commit_edit(path, snapshot)
    except ValueError as exc:
        abort_edit(snapshot)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        abort_edit(snapshot)
        raise
    if job is not None:
        job.highlights = [HighlightMark(**item) for item in updated]
    return {"page": inserted_at, "page_count": page_count, "detail": "PDF pages inserted."}


@router.post("/jobs/{job_id}/annotate")
def annotate_job_pdf(job_id: str, body: PreviewAnnotation) -> dict:
    path, _filename = _editable_job_pdf(job_id)
    snapshot = snapshot_before(path)
    try:
        if body.action == "text" and body.x is not None and body.y is not None:
            add_text(path, body.page, body.x, body.y, body.text)
        elif body.action == "highlight" and None not in (body.x0, body.y0, body.x1, body.y1):
            add_highlight(path, body.page, (body.x0, body.y0, body.x1, body.y1))
        else:
            rect = (body.x0, body.y0, body.x1, body.y1)
            if body.action == "redact" and None not in rect:
                removed_chars = add_secure_redaction(path, body.page, rect)
            elif body.action in {"note", "rectangle", "circle", "line", "stamp", "signature"} and None not in rect:
                add_annotation(path, body.page, body.action, rect, text=body.text, points=body.points)
            else:
                raise ValueError("Choose a tool and provide its position on the page.")
            commit_edit(path, snapshot)
            return {"page": body.page, "detail": f"Permanent redaction applied; {removed_chars} text character(s) removed." if body.action == "redact" else f"{body.action.title()} added to PDF."}
        commit_edit(path, snapshot)
    except ValueError as exc:
        abort_edit(snapshot)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        abort_edit(snapshot)
        raise
    return {"page": body.page, "detail": "PDF annotation saved."}


@router.get("/jobs/{job_id}/search")
def search_job_pdf(job_id: str, q: str = "") -> dict:
    path, _filename = _job_pdf(job_id)
    try:
        matches = search_pdf(path, q)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"query": q, "matches": matches}


@router.post("/jobs/{job_id}/bookmarks")
def edit_job_bookmarks(job_id: str, body: BookmarkOperation) -> dict:
    path, _filename = _editable_job_pdf(job_id)
    snapshot = snapshot_before(path)
    try:
        bookmarks = update_bookmark(path, body.action, index=body.index, title=body.title, page=body.page, level=body.level)
        commit_edit(path, snapshot)
    except ValueError as exc:
        abort_edit(snapshot)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"bookmarks": bookmarks, "detail": "Bookmarks updated."}


@router.get("/jobs/{job_id}/bookmarks/validate")
def validate_job_bookmarks(job_id: str) -> dict:
    path, _filename = _job_pdf(job_id)
    return validate_bookmarks(path)


@router.post("/jobs/{job_id}/history/{action}")
def history_job_pdf(job_id: str, action: str) -> dict:
    path, _filename = _editable_job_pdf(job_id)
    if action == "undo":
        changed = undo_edit(path)
    elif action == "redo":
        changed = redo_edit(path)
    else:
        raise HTTPException(status_code=404, detail="Unknown history operation.")
    if changed:
        from services.preview_view import _PNG_CACHE
        _PNG_CACHE.clear()
    job = JOBS.get(job_id)
    marks = load_marks(path)
    if job is not None:
        job.highlights = [HighlightMark(**item) for item in marks]
        marks = [item.model_dump() for item in job.highlights]
    return {"changed": changed, "highlights": marks, **history_state(path), "detail": f"{action.title()} complete." if changed else f"Nothing to {action}."}


@router.get("/jobs/{job_id}/history")
def get_job_history(job_id: str) -> dict:
    found = _saved_pdf(job_id)
    if not found:
        raise HTTPException(status_code=404, detail="Assembled PDF not found.")
    return history_state(active_path(found[0]))


@router.post("/jobs/{job_id}/save-edited")
def save_edited_job_pdf(job_id: str) -> dict:
    found = _saved_pdf(job_id)
    if not found:
        raise HTTPException(status_code=404, detail="Assembled PDF not found.")
    original, _filename = found
    working = editable_path(original)
    if working.stat().st_size == original.stat().st_size and working.read_bytes() == original.read_bytes():
        raise HTTPException(status_code=400, detail="No preview edits have been made yet.")
    destination = edited_copy_path(original)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(working.read_bytes())
    return {"filename": destination.name, "url": f"/api/jobs/{job_id}/edited-pdf", "detail": "Separate edited copy saved. Original package unchanged."}


@router.get("/jobs/{job_id}/edited-pdf")
def download_edited_job_pdf(job_id: str) -> FileResponse:
    found = _saved_pdf(job_id)
    if not found:
        raise HTTPException(status_code=404, detail="Assembled PDF not found.")
    path = edited_copy_path(found[0])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Save an edited copy from the preview first.")
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="attachment")


@router.get("/jobs/{job_id}/original-pdf")
def download_original_job_pdf(job_id: str) -> FileResponse:
    found = _saved_pdf(job_id)
    if not found:
        raise HTTPException(status_code=404, detail="Original assembled PDF not found.")
    path, filename = found
    return FileResponse(path, media_type="application/pdf", filename=filename, content_disposition_type="attachment")


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

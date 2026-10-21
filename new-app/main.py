from __future__ import annotations

import sys

# Windows resets the browser connection while a PDF is uploading. Uvicorn's
# default Proactor loop does this on POST /api/inspect. A selector loop keeps
# the request open. PDF bytes also stay in memory so Windows does not lock a
# temp file once the upload passes 1 MB.
def selector_loop_factory(use_subprocess: bool = False):
    import asyncio

    return asyncio.SelectorEventLoop


from starlette.formparsers import MultiPartParser

MultiPartParser.spool_max_size = 200 * 1024 * 1024

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from api.jobs import router as jobs_router
from config.settings import HOST, PORT, TEMPLATES_DIR

app = FastAPI(
    title="MOA Valuation Package Automation",
    version="0.1.0",
    description="Phase 1: assemble source PDFs, extract a Plan Profile, and save the named valuation package.",
    servers=[{"url": "/"}],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "phase": "1"}


@app.get("/")
def ui() -> FileResponse:
    html = TEMPLATES_DIR / "index.html"
    if not html.is_file():
        raise FileNotFoundError(f"UI missing: {html}")
    return FileResponse(
        html,
        media_type="text/html",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


if __name__ == "__main__":
    import threading
    import time
    import urllib.request
    import webbrowser

    import uvicorn

    def _open_browser() -> None:
        health = f"http://127.0.0.1:{PORT}/health"
        page = f"http://127.0.0.1:{PORT}"
        for _ in range(50):
            try:
                with urllib.request.urlopen(health, timeout=0.4) as response:
                    if response.status == 200:
                        webbrowser.open(page)
                        return
            except Exception:
                time.sleep(0.2)

    print(f"Keep this window open. App: http://127.0.0.1:{PORT}", flush=True)
    threading.Thread(target=_open_browser, daemon=True).start()
    run_kwargs = {"host": HOST, "port": PORT, "reload": False}
    if sys.platform == "win32":
        # Passing loop="asyncio" still builds a ProactorEventLoop on Windows.
        run_kwargs["loop"] = "main:selector_loop_factory"
        run_kwargs["http"] = "h11"
        print("Windows PDF uploads use the selector event loop.", flush=True)
    uvicorn.run("main:app", **run_kwargs)

from __future__ import annotations

import sys

def _keep_upload_socket_open() -> None:
    """Do not pause the socket after 64 KB. That pause resets PDF uploads on Windows."""
    limit = 256 * 1024 * 1024
    modules = (
        "uvicorn.protocols.http.flow_control",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.http.zttp_impl",
    )
    import importlib

    for name in modules:
        try:
            module = importlib.import_module(name)
        except Exception:
            continue
        if hasattr(module, "HIGH_WATER_LIMIT"):
            module.HIGH_WATER_LIMIT = limit


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


class _CloseAfterResponse:
    """Tell the browser not to reuse a socket Windows may already have reset."""

    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http" or sys.platform != "win32":
            await self.asgi_app(scope, receive, send)
            return

        async def send_close(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers") or [])
                headers.append((b"connection", b"close"))
                message = {**message, "headers": headers}
            await send(message)

        await self.asgi_app(scope, receive, send_close)


app.add_middleware(_CloseAfterResponse)


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {"status": "ok", "phase": "1", "console_trace": True}


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
    _keep_upload_socket_open()
    run_kwargs = {
        "host": HOST,
        "port": PORT,
        "reload": False,
        "timeout_keep_alive": 120,
        "http": "h11",
    }
    if sys.platform == "win32":
        print("Windows uploads are sent in small pieces so the connection stays open.", flush=True)
    uvicorn.run("main:app", **run_kwargs)

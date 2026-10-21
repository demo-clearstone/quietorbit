"""Copy a client-ready runtime pack into dist/ (no tests, samples, or venv)."""

from __future__ import annotations

import base64
import json
import shutil
import textwrap
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP = DIST / "app"

COPY_DIRS = ("api", "config", "models", "services", "templates")
COPY_FILES = ("main.py",)


def _clean() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    APP.mkdir(parents=True)
    (APP / "output").mkdir()
    (APP / "logs").mkdir()
    (APP / "output" / ".gitkeep").write_text("", encoding="utf-8")
    (APP / "logs" / ".gitkeep").write_text("", encoding="utf-8")


def _copy_tree() -> None:
    for name in COPY_DIRS:
        src = ROOT / name
        dst = APP / name
        shutil.copytree(
            src,
            dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
        )
    for name in COPY_FILES:
        shutil.copy2(ROOT / name, APP / name)
    shutil.copy2(ROOT / "requirements-run.txt", APP / "requirements.txt")


def _nested_bat() -> str:
    return "\r\n".join(
        [
            "@echo off",
            "setlocal",
            "cd /d \"%~dp0app\"",
            "set PY=python",
            "where py >nul 2>&1 && set PY=py -3",
            "if not exist .venv (",
            "  echo Creating virtual environment...",
            "  %PY% -m venv .venv",
            "  if errorlevel 1 (",
            "    echo Python 3 was not found. Install Python 3.11+ and check Add python.exe to PATH.",
            "    pause",
            "    exit /b 1",
            "  )",
            ")",
            "call .venv\\Scripts\\activate.bat",
            "python -m pip install --upgrade pip",
            "python -m pip install -r requirements.txt",
            "if errorlevel 1 (",
            "  echo Package install failed. The PC needs internet the first time.",
            "  pause",
            "  exit /b 1",
            ")",
            "echo.",
            "echo Keep this window open. The browser will open http://127.0.0.1:8002",
            "echo.",
            "python main.py",
            "pause",
            "",
        ]
    )


def _flat_bat() -> str:
    return _nested_bat().replace("cd /d \"%~dp0app\"", "cd /d \"%~dp0\"")


def _write_bat() -> None:
    (DIST / "run.bat").write_text(_nested_bat(), encoding="utf-8")


def _write_text_installer() -> Path:
    """One .py file you can paste into email. Client saves it and runs: python install_moa.py"""
    payload: dict[str, str] = {}
    for path in APP.rglob("*"):
        if not path.is_file() or path.name == ".gitkeep":
            continue
        rel = path.relative_to(APP).as_posix()
        payload[rel] = base64.b64encode(path.read_bytes()).decode("ascii")
    payload["run.bat"] = base64.b64encode(_flat_bat().encode("utf-8")).decode("ascii")
    blob = base64.b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")
    wrapped = "\n".join(textwrap.wrap(blob, 76))
    installer = DIST / "install_moa.py"
    installer.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                '"""MOA Valuation Package installer (text / email safe).',
                "",
                "On the client PC:",
                "1. Copy this entire message into Notepad",
                "2. Save as install_moa.py (not .txt)",
                "3. Open a command prompt in that folder",
                "4. python install_moa.py",
                "5. Double-click moa-app\\\\run.bat",
                "6. Open http://127.0.0.1:8002",
                "",
                "First run needs internet once (pip install pymupdf, fastapi, ...).",
                '"""',
                "from __future__ import annotations",
                "",
                "import base64",
                "import json",
                "from pathlib import Path",
                "",
                'PAYLOAD = """',
                wrapped,
                '"""',
                "",
                "",
                "def main() -> None:",
                '    root = Path(__file__).resolve().parent / "moa-app"',
                '    data = json.loads(base64.b64decode("".join(PAYLOAD.split())).decode("utf-8"))',
                "    for rel, encoded in data.items():",
                "        dest = root / rel",
                "        dest.parent.mkdir(parents=True, exist_ok=True)",
                "        dest.write_bytes(base64.b64decode(encoded))",
                '        print("wrote", dest)',
                "    print()",
                '    print("Next: double-click", root / "run.bat")',
                '    print("Then open http://127.0.0.1:8002")',
                "",
                "",
                'if __name__ == "__main__":',
                "    main()",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return installer


def _write_readme() -> None:
    (DIST / "README.txt").write_text(
        "\n".join(
            [
                "MOA Valuation Package — transfer without a zip",
                "",
                "Python is on the client. First run still needs internet once for pip.",
                "Do not email a venv or PyMuPDF wheels. Those are binaries.",
                "",
                "Email this ONE text file: dist/install_moa.py",
                "Client steps:",
                "  1. Paste the whole file into Notepad",
                "  2. Save as install_moa.py",
                "  3. python install_moa.py",
                "  4. Double-click moa-app\\run.bat",
                "  5. Open http://127.0.0.1:8002",
                "",
                "If email wraps lines, that is OK. The installer ignores extra line breaks.",
                "Rebuild after code changes:",
                "  python scripts/build_dist.py",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _zip() -> Path:
    zip_path = DIST / "moa-app.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in DIST.rglob("*"):
            if path.is_dir() or path == zip_path or path.name == "install_moa.py":
                continue
            zf.write(path, path.relative_to(DIST))
    return zip_path


def main() -> None:
    _clean()
    _copy_tree()
    _write_bat()
    installer = _write_text_installer()
    _write_readme()
    zip_path = _zip()
    print(f"Wrote {APP}")
    print(f"Wrote {DIST / 'run.bat'}")
    print(f"Wrote {installer} ({installer.stat().st_size} bytes)  <- email this text file")
    print(f"Wrote {zip_path} ({zip_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

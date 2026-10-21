@echo off
setlocal
cd /d "%~dp0"
set PY=python
where py >nul 2>&1 && set PY=py -3
if not exist .venv (
  echo Creating virtual environment...
  %PY% -m venv .venv
  if errorlevel 1 (
    echo Python 3 was not found. Install Python 3.11 or newer and check Add python.exe to PATH.
    pause
    exit /b 1
  )
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements-run.txt
if errorlevel 1 (
  echo Package install failed. This PC needs internet the first time.
  pause
  exit /b 1
)
echo.
echo Keep this window open. The browser will open http://127.0.0.1:8002
echo.
python main.py
pause

@echo off
setlocal EnableExtensions
title MOA Valuation - Build Windows EXE / MSI

REM Keep a log so we can see failures even if the window closes.
set "LOG=%~dp0build_log.txt"
echo ===== MOA build started %DATE% %TIME% =====> "%LOG%"
echo Script: %~f0>> "%LOG%"
echo.

echo === MOA Valuation Windows build ===
echo Log file: %LOG%
echo.

cd /d "%~dp0\.." >> "%LOG%" 2>&1
if errorlevel 1 (
  echo ERROR: Could not change to the new-app folder.
  echo ERROR: Could not change to the new-app folder.>> "%LOG%"
  goto :end
)

echo Working folder: %CD%
echo Working folder: %CD%>> "%LOG%"
echo.

where powershell >> "%LOG%" 2>&1
if errorlevel 1 (
  echo ERROR: PowerShell was not found.
  echo ERROR: PowerShell was not found.>> "%LOG%"
  goto :end
)

where python >> "%LOG%" 2>&1
if errorlevel 1 (
  where py >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo ERROR: Python was not found on PATH.
    echo Install Python 3.12+ and check "Add python.exe to PATH".
    echo ERROR: Python not found.>> "%LOG%"
    goto :end
  )
)

echo Starting build (several minutes)... Please wait.
echo Starting PyInstaller build...>> "%LOG%"
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" %* >> "%LOG%" 2>&1
set "EXITCODE=%ERRORLEVEL%"
echo.
echo Exit code: %EXITCODE%>> "%LOG%"

if not "%EXITCODE%"=="0" (
  echo BUILD FAILED with exit code %EXITCODE%.
  echo Open packaging\build_log.txt for details.
) else (
  echo BUILD FINISHED.
  echo Check new-app\dist\ for EXE / zip / MSI.
  echo Also see packaging\build_log.txt
)

:end
echo.
echo ===== finished %DATE% %TIME% =====>> "%LOG%"
echo.
echo Press any key to close...
pause >nul
endlocal

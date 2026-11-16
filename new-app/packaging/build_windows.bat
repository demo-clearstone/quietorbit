@echo off
REM Double-click this file on a Windows PC that has the new-app source folder.
REM Builds MOA_Valuation.exe (+ portable zip) and MSI when WiX is available.
cd /d "%~dp0\.."
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" %*
echo.
pause

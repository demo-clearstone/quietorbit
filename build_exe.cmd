@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto failed

echo.
echo MOA Valuation Package - Windows EXE builder
echo This requires 64-bit Python 3.10 or newer and an internet connection.
echo.

where py >nul 2>nul
if errorlevel 1 goto use_python
set "PYTHON=py -3"
goto check_python

:use_python
where python >nul 2>nul
if errorlevel 1 goto no_python
set "PYTHON=python"

:check_python
%PYTHON% -c "import platform,struct,sys; print('Using Python '+sys.version.split()[0]+' ('+platform.architecture()[0]+')'); valid=sys.version_info >= (3,10) and struct.calcsize('P') == 8; print('ERROR: Install 64-bit Python 3.10 or newer and enable the Python launcher or add Python to PATH.' if not valid else 'Python check passed.'); sys.exit(0 if valid else 1)"
if errorlevel 1 goto failed

set "VENV_DIR=%~dp0.build-venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
if not exist "%VENV_PYTHON%" goto create_venv
"%VENV_PYTHON%" -c "import struct,sys; sys.exit(0 if sys.version_info >= (3,10) and struct.calcsize('P') == 8 and sys.prefix != sys.base_prefix else 1)" >nul 2>nul
if errorlevel 1 (
    echo.
    echo Recreating the unusable or copied build environment...
    %PYTHON% -m venv --clear "%VENV_DIR%"
    if errorlevel 1 goto failed
)
goto install_dependencies

:create_venv
echo.
echo Creating isolated build environment...
%PYTHON% -m venv "%VENV_DIR%"
if errorlevel 1 goto failed

:install_dependencies
echo.
echo Installing application and PyInstaller dependencies...
"%VENV_PYTHON%" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed

echo.
echo Building the EXE...
"%VENV_PYTHON%" scripts\build_windows.py --exe-only
if errorlevel 1 goto failed

echo.
echo SUCCESS: The executable folder is:
echo %~dp0dist\windows\publish\MOAValuationPackage
echo Copy the entire MOAValuationPackage folder, including _internal, to the other PC.
echo.
pause
exit /b 0

:no_python
echo ERROR: Python was not found. Install 64-bit Python 3.10 or newer, enable the Python launcher or add Python to PATH, then run this script again.
goto failed

:failed
echo.
echo BUILD FAILED. Read the specific error details above, fix that issue, and run this script again.
echo.
pause
exit /b 1

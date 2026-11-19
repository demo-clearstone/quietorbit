# Build MOA_Valuation.exe (portable folder + zip) and optionally MOA_Valuation_Setup.msi.
# Run on a Windows machine that has this new-app source tree.
#
# Usage:
#   Double-click packaging\build_windows.bat
#   OR from new-app/:
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
#
# Options:
#   -SkipMsi          Build EXE/zip only (no WiX)
#   -InstallWix       Try to install WiX Toolset 3.14 via Chocolatey (admin)
#   -ProductVersion   MSI version, e.g. 1.0.5 (default 1.0.0)

[CmdletBinding()]
param(
    [switch]$SkipMsi,
    [switch]$InstallWix,
    [string]$ProductVersion = "1.0.0"
)

$ErrorActionPreference = "Stop"

$AppRoot = Split-Path -Parent $PSScriptRoot
Set-Location $AppRoot

Write-Host ""
Write-Host "=== MOA Valuation Windows build ===" -ForegroundColor Cyan
Write-Host "App root: $AppRoot"
Write-Host ""

function Find-Python {
    foreach ($name in @("py", "python", "python3")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        try {
            if ($name -eq "py") {
                & $cmd.Source -3 --version 2>$null | Out-Null
                if ($LASTEXITCODE -eq 0) { return @{ Exe = $cmd.Source; Prefix = @("-3") } }
            } else {
                & $cmd.Source --version 2>$null | Out-Null
                if ($LASTEXITCODE -eq 0) { return @{ Exe = $cmd.Source; Prefix = @() } }
            }
        } catch { }
    }
    return $null
}

function Ensure-WixOnPath {
    $tools = @("heat", "candle", "light")
    $missing = @($tools | Where-Object { -not (Get-Command $_ -ErrorAction SilentlyContinue) })
    if ($missing.Count -eq 0) { return $true }

    $candidates = @(
        "C:\Program Files (x86)\WiX Toolset v3.14\bin",
        "C:\Program Files (x86)\WiX Toolset v3.11\bin",
        "C:\Program Files\WiX Toolset v3.14\bin"
    )
    foreach ($dir in $candidates) {
        if (Test-Path (Join-Path $dir "heat.exe")) {
            $env:Path = "$dir;$env:Path"
            Write-Host "Added WiX to PATH: $dir"
            return $true
        }
    }
    return $false
}

# --- Python ---
$py = Find-Python
if (-not $py) {
    throw @"
Python 3 was not found on PATH.

Install Python 3.12+ from https://www.python.org/downloads/
(check "Add python.exe to PATH"), then re-run this script.
"@
}

$PyExe = $py.Exe
$PyPrefix = $py.Prefix
Write-Host "Using: $PyExe $($PyPrefix -join ' ')"
& $PyExe @PyPrefix --version

# --- venv ---
$VenvDir = Join-Path $AppRoot ".venv-build"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating build virtualenv at .venv-build ..."
    & $PyExe @PyPrefix -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "Failed to create venv" }
}
$Python = $VenvPython

Write-Host "Installing dependencies (requirements.txt + pyinstaller) ..."
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
& $Python -m pip install -r (Join-Path $AppRoot "requirements.txt") pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

# --- PyInstaller ---
$Spec = Join-Path $AppRoot "packaging\moa_valuation.spec"
if (-not (Test-Path $Spec)) { throw "Missing spec: $Spec" }

Write-Host "Running PyInstaller (onedir) ..."
& $Python -m PyInstaller $Spec --noconfirm --clean
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$DistDir = Join-Path $AppRoot "dist\MOA_Valuation"
$AppExe = Join-Path $DistDir "MOA_Valuation.exe"
if (-not (Test-Path $AppExe)) {
    throw "Build finished but EXE not found: $AppExe"
}

# --- Portable zip ---
$ZipPath = Join-Path $AppRoot "dist\MOA_Valuation_portable.zip"
if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }
Write-Host "Creating portable zip ..."
Compress-Archive -Path (Join-Path $DistDir "*") -DestinationPath $ZipPath

Write-Host ""
Write-Host "EXE folder : $DistDir" -ForegroundColor Green
Write-Host "EXE        : $AppExe" -ForegroundColor Green
Write-Host "Portable   : $ZipPath" -ForegroundColor Green

# --- MSI ---
if ($SkipMsi) {
    Write-Host ""
    Write-Host "Skipped MSI (-SkipMsi). Portable EXE is ready." -ForegroundColor Yellow
    exit 0
}

if ($InstallWix) {
    if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
        throw "Chocolatey not found. Install from https://chocolatey.org/install or install WiX Toolset 3.x manually."
    }
    Write-Host "Installing WiX Toolset 3.14 via Chocolatey (may need admin) ..."
    & choco install wixtoolset --version=3.14.1 -y --no-progress
    if ($LASTEXITCODE -ne 0) { throw "Chocolatey WiX install failed" }
}

if (-not (Ensure-WixOnPath)) {
    Write-Host ""
    Write-Host "WiX Toolset 3.x not found — MSI was not built." -ForegroundColor Yellow
    Write-Host "EXE + portable zip are ready. To also build the MSI:"
    Write-Host "  1. Install WiX 3.14: https://wixtoolset.org/docs/wix3/"
    Write-Host "     or re-run:  powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -InstallWix"
    Write-Host "  2. Re-run this script (without -SkipMsi)."
    exit 0
}

$env:MOA_PRODUCT_VERSION = $ProductVersion
Write-Host "Building MSI (version $ProductVersion) ..."
& powershell -ExecutionPolicy Bypass -File (Join-Path $AppRoot "packaging\build_msi.ps1")
if ($LASTEXITCODE -ne 0) { throw "MSI build failed" }

$OutMsi = Join-Path $AppRoot "dist\MOA_Valuation_Setup.msi"
Write-Host ""
Write-Host "=== Build complete ===" -ForegroundColor Cyan
Write-Host "Portable zip : $ZipPath"
Write-Host "MSI          : $OutMsi"
Write-Host ""
Write-Host "Give the client either the MSI or the portable zip."
Write-Host "They do not need Python to run the app."

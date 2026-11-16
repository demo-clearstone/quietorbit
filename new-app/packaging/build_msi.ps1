# Build MOA_Valuation_Setup.msi from the PyInstaller onedir output.
# Requires WiX Toolset 3.x (heat, candle, light) on PATH.
#
# Usage (from new-app/):
#   powershell -ExecutionPolicy Bypass -File packaging/build_msi.ps1

$ErrorActionPreference = "Stop"

$AppRoot = Split-Path -Parent $PSScriptRoot
$DistDir = Join-Path $AppRoot "dist\MOA_Valuation"
$OutMsi = Join-Path $AppRoot "dist\MOA_Valuation_Setup.msi"
$Harvested = Join-Path $PSScriptRoot "harvested.wxs"
$ProductWxs = Join-Path $PSScriptRoot "moa_valuation.wxs"
$ObjDir = Join-Path $AppRoot "dist\wixobj"
$ProductVersion = if ($env:MOA_PRODUCT_VERSION) { $env:MOA_PRODUCT_VERSION } else { "1.0.0" }
$AppExe = Join-Path $DistDir "MOA_Valuation.exe"

if (-not (Test-Path $DistDir)) {
    throw "Missing frozen app folder: $DistDir. Run PyInstaller first."
}
if (-not (Test-Path $AppExe)) {
    throw "Missing executable: $AppExe"
}

foreach ($tool in @("heat", "candle", "light")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "WiX tool '$tool' not found on PATH. Install WiX Toolset 3.x."
    }
}

New-Item -ItemType Directory -Force -Path $ObjDir | Out-Null
if (Test-Path $OutMsi) { Remove-Item -Force $OutMsi }
if (Test-Path $Harvested) { Remove-Item -Force $Harvested }

Write-Host "Harvesting $DistDir ..."
& heat dir $DistDir `
    -cg MOAFiles `
    -gg `
    -sfrag `
    -srd `
    -dr INSTALLDIR `
    -var var.DistDir `
    -out $Harvested
if ($LASTEXITCODE -ne 0) { throw "heat failed ($LASTEXITCODE)" }

Write-Host "Compiling WiX sources ..."
& candle `
    -nologo `
    "-dProductVersion=$ProductVersion" `
    "-dAppExe=$AppExe" `
    "-dDistDir=$DistDir" `
    -out "$ObjDir\\" `
    $ProductWxs `
    $Harvested
if ($LASTEXITCODE -ne 0) { throw "candle failed ($LASTEXITCODE)" }

Write-Host "Linking MSI ..."
& light `
    -nologo `
    -out $OutMsi `
    (Get-ChildItem -Path $ObjDir -Filter "*.wixobj" | ForEach-Object { $_.FullName })
if ($LASTEXITCODE -ne 0) { throw "light failed ($LASTEXITCODE)" }

Write-Host "MSI created: $OutMsi"

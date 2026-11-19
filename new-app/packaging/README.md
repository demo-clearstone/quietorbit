# Windows packaging (EXE + MSI)

Builds a double-clickable `MOA_Valuation.exe` (portable folder) and an MSI installer. Clients do **not** need Python, pip, or CMD.

## What clients get

| Artifact | Use |
|----------|-----|
| `MOA_Valuation_portable.zip` | Unzip anywhere → double-click `MOA_Valuation.exe` |
| `MOA_Valuation_Setup.msi` | Install → Start Menu / Desktop shortcut → Uninstall via Windows Settings |

Closing the black console window stops the app. The browser opens to http://127.0.0.1:8002.

Writable output and logs go to `%LOCALAPPDATA%\MOA Valuation\` (override with `MOA_DATA_DIR` or `MOA_OUTPUT_DIR`).

## Build on GitHub Actions (recommended)

You develop on macOS; Windows binaries are produced on `windows-latest`.

1. Push to the repo (or open **Actions → Build Windows EXE + MSI → Run workflow**).
2. Open the completed run → **Artifacts**.
3. Download `MOA_Valuation_portable` and/or `MOA_Valuation_Setup`.
4. Give the zip or MSI to the client PC.

Workflow file: [`.github/workflows/build-windows.yml`](../../.github/workflows/build-windows.yml).

## Local build on a Windows machine (script)

Copy the whole `new-app/` folder to a Windows PC (or clone the repo), then:

1. Install **Python 3.12+** (check “Add python.exe to PATH”).
2. Double-click **`packaging\RUN_BUILD.cmd`** (preferred) or **`packaging\build_windows.bat`**.

If a window still does not appear:

- Right-click the file → **Properties** → if you see **Unblock**, check it → Apply.
- Or open **Command Prompt** and run:

```bat
cd C:\path\to\new-app\packaging
build_windows.bat
```

A log is always written to `packaging\build_log.txt`.

You can also run from `new-app/`:

```bat
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
```

Outputs (under `new-app\dist\`):

| File | Use |
|------|-----|
| `MOA_Valuation\MOA_Valuation.exe` | Portable app folder |
| `MOA_Valuation_portable.zip` | Zip of that folder to send |
| `MOA_Valuation_Setup.msi` | Installer (needs WiX 3.x) |

Useful flags:

```bat
REM EXE + zip only (skip MSI)
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -SkipMsi

REM Try to install WiX via Chocolatey, then build MSI (admin)
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -InstallWix

REM Set MSI version
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -ProductVersion 1.0.5
```

**WiX (for MSI only):** install [WiX Toolset 3.x](https://wixtoolset.org/docs/wix3/) or use `-InstallWix` if Chocolatey is available. Without WiX, the script still produces the EXE and portable zip.

Manual steps (same as the script) if you prefer:

```bat
python -m pip install -r requirements.txt pyinstaller
pyinstaller packaging\moa_valuation.spec --noconfirm --clean
powershell -ExecutionPolicy Bypass -File packaging\build_msi.ps1
```

## Smoke test on a clean Windows PC

1. Install via MSI **or** unzip the portable folder.
2. Double-click `MOA_Valuation` (shortcut or exe).
3. Confirm the console stays open and the browser opens the UI.
4. Upload a small fixture PDF / run a job; confirm a PDF appears under `%LOCALAPPDATA%\MOA Valuation\output\`.
5. Close the console → confirm the server stops.
6. (MSI) Uninstall from **Settings → Apps** and confirm shortcuts are removed.

## Notes

- Code signing / SmartScreen reputation is out of scope for this packaging pass.
- Do not build Windows `.exe` / `.msi` on macOS; use the GitHub Actions workflow.

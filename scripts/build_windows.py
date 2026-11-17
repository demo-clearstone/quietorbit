"""Build a Windows onedir executable and MSI installer for the client PC."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "build" / "windows"
OUTPUT_DIR = ROOT / "dist" / "windows"
PUBLISH_DIR = OUTPUT_DIR / "publish"
APP_NAME = "MOAValuationPackage"
UPGRADE_CODE = "{B31BAF57-2C9F-4F9C-A9CE-4A4D0A778211}"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the Windows executable and, optionally, its MSI installer."
    )
    parser.add_argument(
        "--version",
        default="1.0.0",
        help="Three-part MSI version (default: 1.0.0).",
    )
    parser.add_argument(
        "--exe-only",
        action="store_true",
        help="Build the executable without requiring WiX or creating an MSI.",
    )
    return parser.parse_args()


def _validate_version(version: str) -> None:
    if not re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,5}", version):
        raise ValueError("Version must have three numeric parts, for example 1.2.0.")
    major, minor, build = (int(part) for part in version.split("."))
    if major > 255 or minor > 255 or build > 65535:
        raise ValueError("MSI versions require major/minor <= 255 and build <= 65535.")


def _require_build_tools(exe_only: bool) -> str | None:
    if os.name != "nt":
        raise RuntimeError("Run this build script on Windows; it cannot cross-build Windows binaries.")
    try:
        subprocess.run(
            [sys.executable, "-m", "PyInstaller", "--version"],
            check=True,
            cwd=ROOT,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            "PyInstaller is missing. Install build dependencies with "
            "'python -m pip install -r requirements-build.txt'."
        ) from exc

    wix = shutil.which("wix")
    if not exe_only and wix is None:
        raise RuntimeError(
            "WiX Toolset v4 or newer is required to create the MSI. "
            "Install the WiX CLI and ensure 'wix' is on PATH, or use --exe-only."
        )
    return wix


def _prepare_build_dirs() -> None:
    for path in (BUILD_DIR, PUBLISH_DIR):
        if path.exists():
            shutil.rmtree(path)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _build_executable() -> Path:
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--name",
        APP_NAME,
        "--distpath",
        str(PUBLISH_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(BUILD_DIR),
    ]
    for source, destination in (
        (ROOT / "config", "config"),
        (ROOT / "templates", "templates"),
        (ROOT / "logs-updation.xlsx", "."),
    ):
        if not source.exists():
            raise FileNotFoundError(f"Required packaged resource is missing: {source}")
        command.extend(["--add-data", f"{source};{destination}"])

    command.extend(
        [
            "--collect-all",
            "pymupdf",
            "--collect-all",
            "uvicorn",
            "--hidden-import",
            "uvicorn.protocols.http.h11_impl",
            "--hidden-import",
            "uvicorn.lifespan.on",
            str(ROOT / "main.py"),
        ]
    )
    subprocess.run(command, check=True, cwd=ROOT)

    executable = PUBLISH_DIR / APP_NAME / f"{APP_NAME}.exe"
    if not executable.is_file():
        raise FileNotFoundError(f"PyInstaller did not produce the expected executable: {executable}")
    return executable


def _wix_source(version: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package Name="MOA Valuation Package Automation"
           Manufacturer="Mutual of America"
           Version="{version}"
           UpgradeCode="{UPGRADE_CODE}"
           Scope="perMachine">
    <MajorUpgrade DowngradeErrorMessage="A newer version is already installed." />
    <MediaTemplate EmbedCab="yes" />
    <Feature Id="Main" Title="MOA Valuation Package Automation" Level="1">
      <ComponentGroupRef Id="AppFiles" />
      <ComponentRef Id="StartMenuShortcut" />
    </Feature>
  </Package>
  <StandardDirectory Id="ProgramFiles64Folder">
    <Directory Id="INSTALLFOLDER" Name="MOA Valuation Package" />
  </StandardDirectory>
  <StandardDirectory Id="ProgramMenuFolder">
    <Directory Id="ApplicationProgramsFolder" Name="MOA Valuation Package" />
  </StandardDirectory>
  <Fragment>
    <ComponentGroup Id="AppFiles" Directory="INSTALLFOLDER">
      <Files Include="publish\\{APP_NAME}\\**" />
    </ComponentGroup>
    <Component Id="StartMenuShortcut" Directory="ApplicationProgramsFolder" Guid="*">
      <Shortcut Id="ApplicationShortcut"
                Name="MOA Valuation Package"
                Description="MOA Valuation Package Automation"
                Target="[INSTALLFOLDER]{APP_NAME}.exe"
                WorkingDirectory="INSTALLFOLDER" />
      <RemoveFolder Id="RemoveApplicationProgramsFolder" On="uninstall" />
      <RegistryValue Root="HKLM"
                     Key="Software\\Mutual of America\\MOA Valuation Package"
                     Name="installed"
                     Type="integer"
                     Value="1"
                     KeyPath="yes" />
    </Component>
  </Fragment>
</Wix>
"""


def _build_msi(wix: str, version: str) -> Path:
    source = OUTPUT_DIR / "package.wxs"
    installer = OUTPUT_DIR / f"MOAValuationPackage-{version}-x64.msi"
    source.write_text(_wix_source(version), encoding="utf-8")
    subprocess.run(
        [wix, "build", source.name, "-arch", "x64", "-o", installer.name],
        check=True,
        cwd=OUTPUT_DIR,
    )
    if not installer.is_file():
        raise FileNotFoundError(f"WiX did not produce the expected MSI: {installer}")
    return installer


def main() -> int:
    args = _arguments()
    _validate_version(args.version)
    wix = _require_build_tools(args.exe_only)
    _prepare_build_dirs()
    executable = _build_executable()
    print(f"Built executable: {executable}")
    if not args.exe_only:
        if wix is None:
            raise RuntimeError("WiX was not found after preflight.")
        installer = _build_msi(wix, args.version)
        print(f"Built MSI installer: {installer}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"Build failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

from __future__ import annotations

import runpy
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from scripts.build_windows import _validate_version, _wix_source


def test_frozen_app_uses_bundle_resources_and_user_data_directory(tmp_path, monkeypatch) -> None:
    bundle = tmp_path / "bundle"
    local_app_data = tmp_path / "local"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(local_app_data))
    monkeypatch.delenv("MOA_DATA_DIR", raising=False)
    monkeypatch.delenv("MOA_OUTPUT_DIR", raising=False)
    settings_path = Path(__file__).resolve().parents[1] / "config" / "settings.py"

    settings = runpy.run_path(str(settings_path))

    data_dir = local_app_data / "MOA Valuation Package"
    assert settings["ROOT"] == bundle
    assert settings["CONFIG_DIR"] == bundle / "config"
    assert settings["TEMPLATES_DIR"] == bundle / "templates"
    assert settings["OUTPUT_DIR"] == data_dir / "output"
    assert settings["LOG_DIR"] == data_dir / "logs"


def test_wix_installs_onedir_contents_at_install_root() -> None:
    source = ET.fromstring(_wix_source("1.2.3"))
    namespace = {"w": "http://wixtoolset.org/schemas/v4/wxs"}
    files = source.find(".//w:Files", namespace)
    shortcut = source.find(".//w:Shortcut", namespace)

    assert files is not None
    assert files.attrib["Include"] == r"publish\MOAValuationPackage\**"
    assert shortcut is not None
    assert shortcut.attrib["Target"] == "[INSTALLFOLDER]MOAValuationPackage.exe"


def test_msi_version_uses_windows_installer_limits() -> None:
    _validate_version("255.255.65535")
    for version in ("256.1.0", "1.256.0", "1.1.65536", "1.2"):
        with pytest.raises(ValueError):
            _validate_version(version)

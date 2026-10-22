from __future__ import annotations

import asyncio
from pathlib import Path

from api.jobs import _describe_file


def test_describe_excel_file_defaults_to_one_page():
    path = Path(__file__).resolve().parents[1] / "sample-data/401k/pass/input-excel/Val Assembly.xlsx"

    result = asyncio.run(_describe_file(path.name, path.read_bytes()))

    assert result["name"] == "Val Assembly.xlsx"
    assert result["pages"] == 1
    assert result["split"] is False

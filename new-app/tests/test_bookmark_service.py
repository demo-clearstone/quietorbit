from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from services.bookmark_service import add_bookmarks
from services.pdf_extractor import extract_plan_profile


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = [
    (
        "sample-data/401k/pass/expected-output/555001_2025-Valuation.pdf",
        [
            ("Cover Letter", 1),
            ("Test Summary", 7),
            ("Contribution Analysis", 15),
            ("HCE/Key", 8),
            ("Future HCE", 9),
            ("ADP/ACP Tests", 10),
            ("Summary", 10),
            ("Detail", 11),
            ("Corrections", 12),
            ("402(g) Test", 14),
            ("410(b) Test", 13),
            ("401(a)(4) Test", 19),
            ("Average Benefit Percentage Test", 20),
            ("414(s) Test", 21),
            ("415 Limit Test", 17),
            ("Top Heavy", 16),
            ("Census", 18),
        ],
    ),
    (
        "sample-data/401k/current-fail/expected-output/555002_2025-Valuation.pdf",
        [
            ("Cover Letter", 1),
            ("Test Summary", 9),
            ("Contribution Analysis", 17),
            ("HCE/Key", 10),
            ("Future HCE", 11),
            ("ADP/ACP Tests", 12),
            ("Summary", 12),
            ("Detail", 13),
            ("Corrections", 14),
            ("402(g) Test", 16),
            ("410(b) Test", 15),
            ("415 Limit Test", 19),
            ("Top Heavy", 18),
            ("Census", 20),
        ],
    ),
    (
        "sample-data/403b/pass/expected-output/555403_2025-Valuation.pdf",
        [
            ("Cover Letter", 1),
            ("Test Summary", 7),
            ("Contribution Analysis", 12),
            ("HCE", 8),
            ("Future HCE", 9),
            ("ACP Test", 10),
            ("402(g) Test", 11),
            ("415 Limit Test", 14),
            ("Top Heavy", 13),
            ("Census", 15),
        ],
    ),
]


@pytest.mark.parametrize(("relative_path", "expected"), SCENARIOS)
def test_bookmarks_follow_assembly_sop_and_target_report_pages(relative_path, expected):
    doc = fitz.open(ROOT / relative_path)
    profile = extract_plan_profile(doc)

    add_bookmarks(doc, profile)

    actual = [(title, page) for _level, title, page, *_rest in doc.get_toc()]
    assert actual == expected
    for _level, _title, page, *_rest in doc.get_toc():
        assert 1 <= page <= doc.page_count
        assert doc[page - 1].get_text("text").strip()
    doc.close()

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
            ("Test Summary", 2),
            ("Contribution Analysis", 8),
            ("HCE/Key", 9),
            ("Future HCE", 10),
            ("ADP/ACP Tests", 11),
            ("Summary", 11),
            ("Detail", 12),
            ("Corrections", 13),
            ("402(g) Test", 14),
            ("410(b) Test", 15),
            ("401(a)(4) Test", 16),
            ("Average Benefit Percentage Test", 17),
            ("414(s) Test", 18),
            ("415 Limit Test", 19),
            ("Top Heavy", 20),
            ("Census", 21),
        ],
    ),
    (
        "sample-data/401k/current-fail/expected-output/555002_2025-Valuation.pdf",
        [
            ("Cover Letter", 1),
            ("Test Summary", 2),
            ("Contribution Analysis", 10),
            ("HCE/Key", 11),
            ("Future HCE", 12),
            ("ADP/ACP Tests", 13),
            ("Summary", 13),
            ("Detail", 14),
            ("Corrections", 15),
            ("402(g) Test", 16),
            ("410(b) Test", 17),
            ("415 Limit Test", 18),
            ("Top Heavy", 19),
            ("Census", 20),
        ],
    ),
    (
        "sample-data/403b/pass/expected-output/555403_2025-Valuation.pdf",
        [
            ("Cover Letter", 1),
            ("Test Summary", 2),
            ("Contribution Analysis", 8),
            ("HCE", 9),
            ("Future HCE", 10),
            ("ACP Test", 11),
            ("402(g) Test", 12),
            ("Benefits, Rights and Features test", 13),
            ("415 Limit Test", 14),
            ("Top Heavy", 15),
            ("Census", 16),
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

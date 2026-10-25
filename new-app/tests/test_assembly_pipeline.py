from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from services import save_service
from services.file_order import list_file_meta
from services.orchestrator import process_uploads
from services.pdf_pages import expand_uploads_by_page, pdf_page_count, pdf_page_texts


ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ("sample-data/401k/pass", "555001_2025-Valuation.pdf", "401k", False, False, 21),
    ("sample-data/401k/current-fail", "555002_2025-Valuation.pdf", "401k", True, True, 20),
    ("sample-data/403b/pass", "555403_2025-Valuation.pdf", "403b", False, False, 16),
]


def _ui_ordered_uploads(folder: Path):
    uploads: list[tuple[str, bytes]] = []
    names: list[str] = []
    pages: list[int] = []
    for path in sorted((folder / "input-pdfs").glob("*.pdf")):
        data = path.read_bytes()
        uploads.append((path.name, data))
        meta = list_file_meta(path.name, len(data), pdf_page_count(data), pdf_page_texts(data))
        for page in range(1, meta["pages"] + 1) if meta["split"] else [0]:
            names.append(path.name)
            pages.append(page)
    for path in sorted((folder / "input-excel").glob("*.xlsx")):
        uploads.append((path.name, path.read_bytes()))
        names.append(path.name)
        pages.append(0)
    expanded, _warnings = expand_uploads_by_page(uploads, names, pages)
    return expanded


@pytest.mark.parametrize(("relative", "filename", "plan_type", "failed", "returns", "pages"), CASES)
def test_client_style_assembly_scenario_passes_strict_stops(
    tmp_path, monkeypatch, relative, filename, plan_type, failed, returns, pages
):
    monkeypatch.setattr(save_service, "OUTPUT_DIR", tmp_path / "output")
    result = process_uploads(
        _ui_ordered_uploads(ROOT / relative),
        auto_order=True,
        check_assembly_stops=True,
    )

    assert result.filename == filename
    assert result.plan_profile.plan_type == plan_type
    assert result.plan_profile.testing_failed is failed
    assert result.plan_profile.returns_required is returns
    assert result.review is not None
    assert result.review.ssn_found is False
    order_checks = [item for item in result.review.items if item.code == "package_order"]
    assert len(order_checks) == 1 and order_checks[0].passed

    doc = fitz.open(result.pdf_path)
    assert doc.page_count == pages
    for index, page in enumerate(doc, start=1):
        footer = [
            block[4].strip()
            for block in page.get_text("blocks")
            if block[1] > page.rect.y1 - 70 and block[4].strip().isdigit()
        ]
        if index > 1 and footer:
            assert footer == [str(index)]
    titles = [row[1] for row in doc.get_toc()]
    assert titles[0:2] == ["Cover Letter", "Test Summary"]
    if plan_type == "401k":
        assert [row for row in doc.get_toc() if row[1] == "Summary"]
    from services.package_builder import _overview_kind
    assert { _overview_kind(page.get_text() or "") for page in doc } >= {"intro", "tests", "admin"}
    if plan_type == "403b":
        assert "Benefits, Rights and Features test" in titles
        assert not any(title == "ADP/ACP Tests" for title in titles)
        assert not any(
            rule.rule_id in {"B", "C", "D", "E", "I", "J_ACP"} and rule.action == "keep"
            for rule in result.rule_decisions
        )
        assert not any("Valuation Pkg_p" in warning and "Read Compliance Testing Summary" in warning for warning in result.warnings)
        summary = next(page.get_text() for page in doc if "Compliance Testing Summary of Results" in page.get_text())
        assert "Average Contribution Percentage (ACP)\nTested: Pass" in summary
        package_text = "\n".join(page.get_text() for page in doc)
        assert "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME" in package_text
        assert "Failed Compliance Testing" not in package_text
        assert "Annual Additions (IRC 415) Test Failure Information" not in package_text
        assert "SAMPLE/DRAFT Communication to Participant" not in package_text
        assert "Your plan is not subject to ADP/ACP Nondiscrimination Testing" not in package_text
        assert "Plan Number: 555403" in package_text
    else:
        assert "Benefits, Rights and Features test" not in titles
    if failed:
        assert result.plan_profile.total_qnec == 185354.75
        assert "ADP/ACP Tests" in titles
    doc.close()


def test_console_trace_preserves_403b_assembly(tmp_path, monkeypatch):
    from uuid import uuid4
    from services.console_trace import read_trace, run_traced, start_trace

    monkeypatch.setattr(save_service, "OUTPUT_DIR", tmp_path / "output")
    token = uuid4().hex
    start_trace(token)
    result = run_traced(
        token,
        process_uploads,
        _ui_ordered_uploads(ROOT / "sample-data/403b/pass"),
        auto_order=True,
        check_assembly_stops=True,
    )
    trace = read_trace(token)
    assert trace["status"] == "completed"
    assert trace["truncated"] is False
    steps = [event for event in trace["events"] if event["event"] == "step"]
    assert steps[-1]["function"] == "process_uploads"
    assert any(event["function"] == "order_uploads" for event in steps)
    assert len(steps) < 80
    assert all(event["function"] != "_pdf_text" for event in steps)
    assert all(event["purpose"] and event["code_link"] for event in steps)
    with fitz.open(result.pdf_path) as doc:
        assert doc.page_count == 16
        assert doc.get_toc()[1][1:3] == ["Test Summary", 2]

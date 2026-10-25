from uuid import uuid4

import pytest
from fastapi import HTTPException

from services.console_trace import read_trace, run_traced, start_trace, summarize
from services.plan_config import is_457_plan


def test_trace_records_service_call_input_and_return():
    token = uuid4().hex
    start_trace(token)
    assert run_traced(token, is_457_plan, "457") is True
    trace = read_trace(token)
    assert trace["status"] == "completed"
    step = next(event for event in trace["events"] if event["event"] == "step")
    assert step["file"] == "services/plan_config.py"
    assert step["function"] == "is_457_plan"
    assert "457" in step["purpose"]
    assert step["purpose"] != "Assembly step"
    assert step["input"]["plan_type"] == "457"
    assert step["output"] is True
    assert step["code_link"].startswith("services/plan_config.py:")
    assert read_trace(token, after=1)["events"] == trace["events"][1:]


def test_trace_failure_keeps_exception_and_restores_profiler():
    import sys

    token = uuid4().hex
    start_trace(token)
    previous = sys.getprofile()

    def fail():
        raise ValueError("private customer information")

    with pytest.raises(ValueError):
        run_traced(token, fail)
    trace = read_trace(token)
    assert trace["status"] == "failed"
    assert trace["events"][-1]["exception_type"] == "ValueError"
    assert "private customer" not in str(trace)
    assert sys.getprofile() is previous


def test_repeated_pdf_reads_stay_one_step():
    import fitz
    from services.orchestrator import _split_summaries

    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Cover letter")
    data = doc.tobytes()
    doc.close()
    token = uuid4().hex
    start_trace(token)
    run_traced(token, _split_summaries, [("a.pdf", data), ("b.pdf", data), ("c.pdf", data)])
    names = [event["function"] for event in read_trace(token)["events"] if event["event"] == "step"]
    assert names == ["_split_summaries"]


def test_each_step_has_its_own_purpose():
    from services.console_trace import _purpose
    from services.file_order import order_uploads
    from services.pdf_extractor import extract_plan_profile
    from services.review_service import validate

    ordering = _purpose("services/file_order.py", order_uploads.__name__, {"uploads": ["a.pdf", "b.pdf"]})
    extracting = _purpose("services/pdf_extractor.py", extract_plan_profile.__name__, {})
    checking = _purpose("services/review_service.py", validate.__name__, {})
    assert ordering == "Ordering 2 PDFs into report sequence"
    assert extracting == "Extracting plan data from the merged PDF"
    assert checking == "Checking validation on the plan profile"
    assert len({ordering, extracting, checking}) == 3


def test_summaries_do_not_include_document_text_or_personal_values():
    value = [("cover-letter.pdf", b"123-45-6789"), {"ssn": "123-45-6789", "testing_method": "CURRENT"}]
    summary = summarize(value)
    assert "cover-letter.pdf" in str(summary)
    assert "CURRENT" in str(summary)
    assert "123-45-6789" not in str(summary)


def test_trace_endpoint_validates_and_returns_events():
    import asyncio
    from api.jobs import console_trace

    token = uuid4().hex
    start_trace(token)
    run_traced(token, is_457_plan, "457")
    assert asyncio.run(console_trace(token))["status"] == "completed"
    assert asyncio.run(console_trace(uuid4().hex))["status"] == "waiting"
    for trace_id, after, expected in [(token, -1, 400), ("invalid", 0, 400)]:
        with pytest.raises(HTTPException) as error:
            asyncio.run(console_trace(trace_id, after))
        assert error.value.status_code == expected
    with pytest.raises(HTTPException):
        start_trace(token)
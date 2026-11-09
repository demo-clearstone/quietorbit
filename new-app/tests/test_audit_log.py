from __future__ import annotations

import json
from datetime import datetime, timezone

from models.plan_profile import PlanProfile
from models.review import RuleDecision, ValidationItem
from services.audit_log import audit_log_path, write_audit_log


def test_audit_filename_contains_plan_type_number_utc_timestamp_and_job_id(tmp_path, monkeypatch) -> None:
    import services.audit_log as audit_module

    monkeypatch.setattr(audit_module, "LOG_DIR", tmp_path)
    path = audit_log_path(
        PlanProfile(plan_type="403(b)", plan_number="800643"),
        "abc123def456",
        datetime(2026, 10, 27, 16, 5, 6, tzinfo=timezone.utc),
    )
    assert path.parent == tmp_path
    assert path.name == "403-b_800643_20261027T160506000000Z_abc123def456.json"


def test_audit_log_is_shareable_redacted_and_contains_source_integrity_hashes(tmp_path) -> None:
    path = write_audit_log(
        tmp_path / "assembly-audit.json",
        job_id="abc123abc123",
        filename="800001_2025-Valuation.pdf",
        source_files=[
            ("source-123-45-6789.pdf", b"fake pdf bytes"),
            ("summary.txt", "Result Summary email test@example.com phone 212-555-1212"),
        ],
        options={"auto_order": True, "rewrite_sources": False, "secret": "do not log"},
        profile=PlanProfile(plan_number="800001", plan_type="401k", plan_year_end="12/31/2025"),
        decisions=[RuleDecision(rule_id="A", section="Failure", action="remove", reason="SSN 123-45-6789")],
        validations=[ValidationItem(code="ssn", label="SSN scan", passed=False, detail="Found 123-45-6789")],
        warnings=["Contact test@example.com or 212-555-1212; saved to /Users/client/Testing/Output"],
        elapsed_seconds=1.23456,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    serialized = path.read_text(encoding="utf-8")
    assert payload["status"] == "completed"
    assert payload["source_files"][0]["name"] == "source-[REDACTED-SSN].pdf"
    assert len(payload["source_files"][0]["sha256"]) == 64
    assert "secret" not in payload["options"]
    assert "[REDACTED-EMAIL]" in serialized
    assert "[REDACTED-PHONE]" in serialized
    assert "[REDACTED-SSN]" in serialized
    assert "/Users/client" not in serialized
    assert "fake pdf bytes" not in serialized
    assert payload["privacy"]["pdf_content_included"] is False


def test_stopped_audit_log_records_stop_reason(tmp_path) -> None:
    path = write_audit_log(
        tmp_path / "stopped.json",
        job_id="abc123abc123",
        filename="UNKNOWN_2025-Valuation.pdf",
        source_files=[],
        options={},
        profile=PlanProfile(),
        decisions=[],
        validations=[],
        warnings=[],
        elapsed_seconds=0.5,
        stop_reasons=["Required report Census missing"],
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "stopped"
    assert payload["stop_reasons"] == ["Required report Census missing"]

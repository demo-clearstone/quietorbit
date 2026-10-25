from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import fitz

from models.plan_profile import PlanProfile
from models.review import RuleDecision
from services import save_service
from services.plan_config import paragraphs_for


def write_profile_debug(
    job_id: str,
    profile: PlanProfile,
    decisions: list[RuleDecision],
    doc: fitz.Document,
    *,
    source_files: list[str],
    phase: str,
) -> Path:
    """Write the field values and exact keep/remove evidence for this assembly.

    Purpose:
        Write the field values and exact keep/remove evidence for this assembly.

    Args:
        job_id: Short id for this assembly.
        profile: Plan profile collected from the PDF, Excel, and the compliance summary.
        decisions: Keep, remove, or skipped results from the rules.
        doc: Open PDF. Must not be closed.
        source_files: Uploaded file names. None means there are none.
        phase: Phase. Type: str.

    Returns:
        a Path.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        write_profile_debug("text", profile, decisions, source_files=[], phase="text") returns a Path.

    Side effects:
        Writes a file to disk.
    """
    job_dir = save_service.OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / "profile_debug.json"
    payload = build_profile_debug(
        profile,
        decisions,
        doc,
        source_files=source_files,
        phase=phase,
    )
    if path.exists() and phase == "after_business_rule_edits":
        before = json.loads(path.read_text(encoding="utf-8"))
        payload["before_edit_detected_sections"] = before.get("detected_sections", [])
        payload["before_edit_section_decisions"] = before.get("section_decisions", [])
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=False),
        encoding="utf-8",
    )
    return path


def build_profile_debug(
    profile: PlanProfile,
    decisions: list[RuleDecision],
    doc: fitz.Document,
    *,
    source_files: list[str],
    phase: str,
) -> dict[str, Any]:
    """Build profile debug.

    Purpose:
        Build profile debug.

    Args:
        profile: Plan profile collected from the PDF, Excel, and the compliance summary.
        decisions: Keep, remove, or skipped results from the rules.
        doc: Open PDF. Must not be closed.
        source_files: Uploaded file names. None means there are none.
        phase: Phase. Type: str.

    Returns:
        a dict[str, Any].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        build_profile_debug(profile, decisions, doc, source_files=[], phase="text") returns a dict[str, Any].

    Side effects:
        None. This function only reads data and returns a value.
    """
    matches = _rule_source_matches(doc, profile.plan_type)
    selected = _unique(item.section for item in decisions if item.action == "keep")
    removed = _unique(item.section for item in decisions if item.action == "remove")
    skipped = _unique(item.section for item in decisions if item.skipped)
    detected = [
        {
            "name": item.name,
            "page": item.page,
            "matched_alias": item.matched_alias,
        }
        for item in profile.detected_sections
    ]
    detected_names = _unique(item["name"] for item in detected)

    # Ordinary reports are selected because they physically exist. Conditional
    # pages remain governed by the rule decisions listed above.
    for name in detected_names:
        if name not in selected and name not in removed:
            selected.append(name)

    section_decisions = []
    for item in decisions:
        section_decisions.append(
            {
                "rule_id": item.rule_id,
                "section": item.section,
                "action": item.action,
                "reason": item.reason,
                "skipped": item.skipped,
                "source_matches": matches.get(item.rule_id, []),
            }
        )

    return {
        "plan_type": profile.plan_type or "",
        "testing_method": profile.testing_method or "",
        "hce_current": profile.hce_current is True,
        "hce_future": profile.hce_future is True,
        "top_heavy": profile.top_heavy is True,
        "top_heavy_percent": profile.top_heavy_percent,
        "adp_failed": profile.adp_failed is True,
        "acp_failed": profile.acp_failed is True,
        "fail_402g": profile.fail_402g is True,
        "fail_415": profile.fail_415 is True,
        "returns_required": profile.returns_required is True,
        "variance_report": profile.variance_report is True,
        "contributions_required": profile.contributions_required is True,
        "fail_402g_after_deadline": profile.fail_402g_after_deadline is True,
        "selected_sections": selected,
        "removed_sections": removed,
        "skipped_sections": skipped,
        "phase": phase,
        "field_sources": dict(profile.extra.get("field_sources") or {}),
        "source_files": list(source_files),
        "detected_sections": detected,
        "section_decisions": section_decisions,
    }


def _rule_source_matches(
    doc: fitz.Document,
    plan_type: str | None,
) -> dict[str, list[dict[str, Any]]]:
    """Rule source matches.

    Purpose:
        Rule source matches.

    Args:
        doc: Open PDF. Must not be closed.
        plan_type: Plan type: "401k", "403b", "457", or empty.

    Returns:
        dict[str, list[dict[str, Any]]].

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _rule_source_matches(doc, "text") returns dict[str, list[dict[str, Any]]].

    Side effects:
        None. This function only reads data and returns a value.
    """
    specs = paragraphs_for(plan_type)
    block_specs: list[dict] = []
    for key in ("action_required_headings", "notices", "sample_letters", "excess_summary"):
        block_specs.extend(specs.get(key) or [])

    found: dict[str, list[dict[str, Any]]] = {}
    for spec in block_specs:
        rule_id = str(spec.get("id") or "")
        heading = str(spec.get("heading") or "")
        extra = str(spec.get("extra") or "")
        if not rule_id or not heading:
            continue
        for page in doc:
            text = page.get_text("text") or ""
            if not page.search_for(heading) or (extra and not _fold(extra) in _fold(text)):
                continue
            found.setdefault(rule_id, []).append(
                {"page": page.number + 1, "heading": heading, "extra": extra or None}
            )
    return found


def _fold(value: str) -> str:
    """Fold.

    Purpose:
        Fold.

    Args:
        value: Value. Type: str.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _fold("text") returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    folded = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return folded[4:] if folded.startswith("for ") else folded


def _unique(values) -> list[str]:
    """Unique.

    Purpose:
        Unique.

    Args:
        values: Values. Type: unspecified.

    Returns:
        a list of str.

    Raises:
        None.

    Example:
        _unique(values) returns a list of str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return list(dict.fromkeys(str(value) for value in values if str(value)))

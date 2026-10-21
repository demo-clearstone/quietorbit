from __future__ import annotations

import re

import fitz
import yaml

from config.settings import CONFIG_DIR

_HEADING_A = "IMMEDIATE ACTION REQUIRED - COMPLIANCE TEST FAILURE"
_PHRASES_A = [
    "Contribution refunds to participants are required to correct compliance testing failures",
    "Excess Summary",
    "Form W-4R",
]


def inspect_compliance_failure_wording(doc: fitz.Document) -> dict[str, object]:
    """TEST23 §B.1: the compliance-failure paragraph must use the SOP wording."""
    spec = _rule_a_spec()
    heading = str(spec.get("heading") or _HEADING_A)
    phrases = [str(p) for p in (spec.get("must_include") or _PHRASES_A)]
    text = _norm("\n".join((page.get_text("text") or "") for page in doc))
    found = _norm(heading) in text
    missing = [phrase for phrase in phrases if _norm(phrase) not in text]
    wording_ok = found and not missing
    if wording_ok:
        detail = f"Wording matches TEST23 §B.1: {heading}"
    elif not found:
        detail = f"Heading not found: {heading}"
    else:
        detail = "Heading found, but missing: " + "; ".join(missing)
    return {
        "found": found,
        "wording_ok": wording_ok,
        "missing": missing,
        "detail": detail,
    }


def _rule_a_spec() -> dict:
    data = yaml.safe_load((CONFIG_DIR / "paragraphs.yaml").read_text(encoding="utf-8")) or {}
    for item in data.get("action_required_headings") or []:
        if str(item.get("id")) == "A":
            return item
    return {}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()

from __future__ import annotations

import fitz

from models.plan_profile import PlanProfile
from models.review import RuleDecision
from services.pdf_modifier import apply_decisions
from services.rules_engine import evaluate


def _page(lines: list[tuple[float, str, float]]) -> fitz.Document:
    doc = fitz.open()
    page = doc.new_page()
    for y, text, x in lines:
        page.insert_text((x, y), text, fontsize=9)
    return doc


def _decisions(keep: set[str]) -> list[RuleDecision]:
    return [
        RuleDecision(rule_id=rule, section=rule, action="keep" if rule in keep else "remove", reason="")
        for rule in ("A", "B", "ES")
    ]


def test_heading_words_wrapped_inside_a_kept_paragraph_do_not_cut_it():
    doc = _page(
        [
            (100, "IMMEDIATE ACTION REQUIRED - COMPLIANCE TEST FAILURE", 54),
            (120, "Contribution refunds are required. Review the Excess Summary", 72),
            (132, "Report provided in this package for details.", 72),
            (160, "IMMEDIATE ACTION REQUIRED - ADP/ACP TEST FAILURE", 54),
            (180, "Contribution refunds to participants are required.", 72),
        ]
    )
    apply_decisions(doc, _decisions({"A"}), "401k")
    text = doc[0].get_text("text")
    assert "Report provided in this package" in text
    assert "ADP/ACP TEST FAILURE" not in text


def test_client_heading_dash_and_acp_wording_are_removed():
    doc = _page(
        [
            (100, "IMMEDIATE ACTION REQUIRED – COMPLIANCE TEST FAILURE", 54),
            (120, "Contribution refunds are required.", 72),
            (160, "IMMEDIATE ACTION REQUIRED - ACP TEST FAILURE", 54),
            (180, "Contribution refunds to participants are required.", 72),
            (220, "IMMEDIATE ACTION REQUIRED - ADP/ACP CURRENT METHOD TEST-", 54),
            (232, "FAILURE - AFTER 12-MONTHS", 72),
            (250, "Corrections after 12 months.", 72),
        ]
    )
    decisions = [
        RuleDecision(rule_id=rule, section=rule, action="remove", reason="")
        for rule in ("A", "B", "C", "D", "E")
    ]
    apply_decisions(doc, decisions, "401k")
    text = doc[0].get_text("text")
    assert "COMPLIANCE TEST FAILURE" not in text
    assert "ACP TEST FAILURE" not in text
    assert "AFTER 12-MONTHS" not in text
    assert "Corrections after 12 months" not in text


def test_missing_action_required_fact_removes_the_paragraph():
    profile = PlanProfile(testing_method="PRIOR", returns_required=True, adp_reclassified=False)
    decision = next(item for item in evaluate(profile) if item.rule_id == "B")
    assert decision.action == "remove"
    assert decision.skipped is False

    doc = _page(
        [
            (100, "IMMEDIATE ACTION REQUIRED - ADP/ACP TEST FAILURE", 54),
            (120, "Contribution refunds to participants are required.", 72),
        ]
    )
    apply_decisions(doc, [decision], "401k")
    assert "ADP/ACP TEST FAILURE" not in doc[0].get_text("text")

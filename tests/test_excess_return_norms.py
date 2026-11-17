"""Excess Return Notice keep/remove and QNEC fill per ADP/ACP assemble norms."""

from __future__ import annotations

import fitz

from models.plan_profile import PlanProfile
from services.package_polish import rewrite_403b_adp_mentions
from services.pdf_modifier import _money, fill_qnec_placeholders
from services.plan_config import clear_yaml_cache
from services.rules_engine import evaluate


def setup_function() -> None:
    clear_yaml_cache()


def _action(profile: PlanProfile, rule_id: str) -> str:
    return next(item.action for item in evaluate(profile) if item.rule_id == rule_id)


def test_401k_excess_notice_current_only_when_returns_required() -> None:
    keep = PlanProfile(
        plan_type="401k",
        testing_method="CURRENT",
        returns_required=True,
        adp_failed=True,
        after_12_months=False,
    )
    prior = PlanProfile(
        plan_type="401k",
        testing_method="PRIOR",
        returns_required=True,
        adp_failed=True,
        after_12_months=False,
    )
    no_returns = PlanProfile(
        plan_type="401k",
        testing_method="CURRENT",
        returns_required=False,
        adp_failed=True,
        after_12_months=False,
    )
    assert _action(keep, "I") == "keep"
    assert _action(prior, "I") == "remove"
    assert _action(no_returns, "I") == "remove"


def test_403b_excess_notice_requires_acp_fail_current_not_prior() -> None:
    acp_current = PlanProfile(
        plan_type="403b",
        testing_method="CURRENT",
        returns_required=True,
        acp_failed=True,
        after_12_months=False,
    )
    adp_only = PlanProfile(
        plan_type="403b",
        testing_method="CURRENT",
        returns_required=True,
        adp_failed=True,
        acp_failed=False,
        after_12_months=False,
    )
    prior = PlanProfile(
        plan_type="403b",
        testing_method="PRIOR",
        returns_required=True,
        acp_failed=True,
        after_12_months=False,
    )
    assert _action(acp_current, "I") == "keep"
    assert _action(adp_only, "I") == "remove"
    assert _action(prior, "I") == "remove"


def test_403b_excess_notice_fills_acp_test_is_qnec_after_rewrite() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((54, 100), "Failed Compliance Testing", fontsize=11)
    page.insert_text((54, 118), "Excess Return Notice", fontsize=11)
    page.insert_text(
        (54, 150),
        "Current method testing: The amount of the QNEC that is required to pass the ADP/ACP test is $X,XXX,XXX.XX.",
        fontsize=9,
    )
    page.insert_text(
        (54, 164),
        "The ADP QNEC is $X,XXX,XXX.XX. The ACP QNEC is $X,XXX,XXX.XX. Form W-4P.",
        fontsize=9,
    )
    profile = PlanProfile(
        plan_type="403b",
        testing_method="CURRENT",
        returns_required=True,
        acp_failed=True,
        acp_qnec=818.86,
        after_12_months=False,
    )
    assert rewrite_403b_adp_mentions(doc)
    filled = fill_qnec_placeholders(doc, profile, [])
    text = " ".join(page.get_text().split())
    assert any(item.startswith("acp-notice=") or item.startswith("acp=") for item in filled)
    assert "ACP test is" in text
    assert _money(818.86) in text
    assert "ADP QNEC" not in text
    assert "Form W-4P" in text
    assert "$X,XXX,XXX.XX" not in text


def test_403b_missing_acp_qnec_clears_amount_from_notice() -> None:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(
        fitz.Rect(54, 80, 540, 220),
        (
            "Failed Compliance Testing\n\nExcess Return Notice\n\n"
            "Current method testing: ACP test is $X,XXX,XXX.XX. Form W-4P."
        ),
        fontsize=10,
    )
    fill_qnec_placeholders(
        doc,
        PlanProfile(plan_type="403b", acp_qnec=None),
        [],
    )
    text = page.get_text()
    assert "$X,XXX,XXX.XX" not in text
    assert "Form W-4P" in text

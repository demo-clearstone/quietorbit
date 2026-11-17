"""401(k) Year End Recap paragraphs 2/3/4/5: PRIOR / CURRENT / Safe Harbor / current-year HCE."""

from __future__ import annotations

import re

from models.plan_profile import PlanProfile
from services.pdf_modifier import _matching_recap, _recap_specs
from services.plan_config import clear_yaml_cache
from services.rules_engine import evaluate


def setup_function() -> None:
    clear_yaml_cache()


def _y(profile: PlanProfile, *ids: str) -> dict[str, str]:
    wanted = set(ids) or {"Y2", "Y3", "Y4", "Y5"}
    return {
        item.rule_id: item.action
        for item in evaluate(profile)
        if item.rule_id in wanted
    }


def test_prior_keeps_y2_only_when_future_hce() -> None:
    assert _y(PlanProfile(plan_type="401k", testing_method="PRIOR", hce_future=True), "Y2", "Y3", "Y4") == {
        "Y2": "keep",
        "Y3": "remove",
        "Y4": "remove",
    }


def test_current_keeps_y3_only_when_future_hce() -> None:
    assert _y(PlanProfile(plan_type="401k", testing_method="CURRENT", hce_future=True), "Y2", "Y3", "Y4") == {
        "Y2": "remove",
        "Y3": "keep",
        "Y4": "remove",
    }


def test_safe_harbor_keeps_y4_only_when_future_hce() -> None:
    assert _y(PlanProfile(plan_type="401k", safe_harbor=True, hce_future=True), "Y2", "Y3", "Y4") == {
        "Y2": "remove",
        "Y3": "remove",
        "Y4": "keep",
    }


def test_safe_harbor_overrides_prior_or_current() -> None:
    assert _y(
        PlanProfile(plan_type="401k", testing_method="PRIOR", safe_harbor=True, hce_future=True),
        "Y2",
        "Y3",
        "Y4",
    ) == {
        "Y2": "remove",
        "Y3": "remove",
        "Y4": "keep",
    }
    assert _y(
        PlanProfile(plan_type="401k", testing_method="CURRENT", safe_harbor=True, hce_future=True),
        "Y2",
        "Y3",
        "Y4",
    ) == {
        "Y2": "remove",
        "Y3": "remove",
        "Y4": "keep",
    }


def test_current_year_hce_only_keeps_y5_not_future_hce_wording() -> None:
    """Had HCE this year, none next year — do not keep CURRENT/PRIOR/SH Future HCE bullets."""
    profile = PlanProfile(
        plan_type="401k",
        testing_method="CURRENT",
        hce_current=True,
        hce_future=False,
        safe_harbor=False,
    )
    assert _y(profile, "Y2", "Y3", "Y4", "Y5") == {
        "Y2": "remove",
        "Y3": "remove",
        "Y4": "remove",
        "Y5": "keep",
    }


def test_y5_match_does_not_steal_no_hce_y1_bullet() -> None:
    specs = _recap_specs("401k")
    no_hce = (
        "Your plan is not subject to ADP/ACP Nondiscrimination Testing as the plan did not have any "
        "Highly Compensated Employees for the plan year ending December 31, 2021. For the plan year "
        "beginning January 1, 2022 no employee will be considered highly compensated."
    )
    current_only = (
        "Based on the definition of Highly Compensated Employee (HCE), the plan had Highly Compensated "
        "Employees for the plan year ending December 31, 2021, however, no employee will be considered "
        "highly compensated for the plan year beginning January 1, 2022. Please communicate to affected employees."
    )
    assert _matching_recap(no_hce, specs)["id"] == "Y1"
    assert _matching_recap(current_only, specs)["id"] == "Y5"


def test_safe_harbor_plan_name_sets_profile_flag() -> None:
    from services.plan_profile_service import finalize_profile

    profile = finalize_profile(
        PlanProfile(
            plan_type="401k",
            plan_name="SH 401K PS PLAN FOR EMPLOYEES OF RAINBOW RESOURCE CENTER INC",
        )
    )
    assert profile.safe_harbor is True


def test_apply_recap_swaps_prior_bullet_to_safe_harbor_wording() -> None:
    import fitz
    from models.review import RuleDecision
    from services.pdf_modifier import apply_recap_bullets

    prior = (
        "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed "
        "on the Future HCE Determination Report are considered highly compensated for the Plan "
        "Year beginning in 2026. The maximum average deferral rate for the Highly Compensated "
        "Employee(s) for the 2026 plan year is % based on the average deferral rate for your "
        "Nonhighly Compensated Employees (NHCE) for 2025 of %. This rate is determined using "
        "the \"prior year data\" method."
    )
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((239, 48), "YEAR END RECAP", fontsize=13, fontname="hebo")
    page.insert_text((214, 66), "January 1, 2025 - December 31, 2025", fontsize=10)
    page.insert_text((100, 79), "SH 401K PS PLAN FOR EMPLOYEES OF RAINBOW RESOURCE CENTER INC", fontsize=10)
    page.insert_text((280, 93), "058865", fontsize=10)
    page.draw_line(fitz.Point(54, 109), fitz.Point(page.rect.width - 54, 109), width=0.8)
    page.insert_text((54, 123), "Important Information", fontsize=11, fontname="hebo")
    page.insert_textbox(fitz.Rect(62, 130, 540, 210), prior, fontsize=8, fontname="helv")
    page.insert_textbox(
        fitz.Rect(62, 220, 540, 280),
        "Your plan is designed to allow participants who were age 50 or older to make catch-up contributions.",
        fontsize=8,
        fontname="helv",
    )
    decisions = [
        RuleDecision(rule_id="Y2", section="prior", action="remove", reason="SH"),
        RuleDecision(rule_id="Y3", section="current", action="remove", reason="SH"),
        RuleDecision(rule_id="Y4", section="safe harbor", action="keep", reason="SH"),
        RuleDecision(rule_id="Y6", section="catch-up", action="keep", reason="ok"),
    ]

    apply_recap_bullets(doc, decisions, "401k")

    text = re.sub(r"\s+", " ", doc[0].get_text("text"))
    assert "not limited as long as the plan follows the rules and regulations of the Safe Harbor Plan" in text
    assert "prior year data" not in text
    assert "is % based" not in text
    assert "catch-up contributions" in text


def test_bullet_matches_are_distinct_for_y2_y3_y4() -> None:
    specs = _recap_specs("401k")
    prior = (
        "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed "
        "on the Future HCE Determination Report are considered highly compensated for the Plan "
        "Year beginning in 2022. The maximum average deferral rate for the Highly Compensated "
        "Employee(s) for the 2022 plan year is % based on the average deferral rate for your "
        "Nonhighly Compensated Employees (NHCE) for 2021 of %. This rate is determined using "
        "the 'prior year data' method."
    )
    current = (
        "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed "
        "on the Future HCE Determination Report are considered highly compensated for the Plan "
        "Year beginning in 2022. The maximum average deferral rate for the Highly Compensated "
        "Employee(s) for the 2022 plan year is based on the average deferral rate for your "
        "Nonhighly Compensated Employees for 2022. Note: In addition, the actual amount the "
        "employee can defer in 2022 cannot exceed $20,500 or the annual addition limit."
    )
    safe_harbor = (
        "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed "
        "on the Future HCE Determination Report are considered highly compensated for the Plan "
        "Year beginning in 2022. The maximum average deferral rate for the Highly Compensated "
        "Employee(s) for the 2022 plan year is not limited as long as the plan follows the rules "
        "and regulations of the Safe Harbor Plan."
    )
    assert _matching_recap(prior, specs)["id"] == "Y2"
    assert _matching_recap(current, specs)["id"] == "Y3"
    assert _matching_recap(safe_harbor, specs)["id"] == "Y4"

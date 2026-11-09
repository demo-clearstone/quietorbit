"""401(k) Year End Recap paragraphs 2/3/4/5: PRIOR / CURRENT / Safe Harbor / current-year HCE."""

from __future__ import annotations

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

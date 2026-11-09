"""Year End Recap keep/remove rules are separate by plan family."""

from __future__ import annotations

from services.plan_config import clear_yaml_cache, paragraphs_for, rules_for


def setup_function() -> None:
    clear_yaml_cache()


def _recap_ids(plan_type: str) -> list[str]:
    return [
        str(rule.get("id"))
        for rule in rules_for(plan_type)["rules"]
        if str(rule.get("id") or "").upper().startswith("Y")
    ]


def _recap_match_ids(plan_type: str) -> set[str]:
    return {str(item.get("id")) for item in paragraphs_for(plan_type).get("recap_bullets") or []}


def test_401k_recap_uses_year_end_recap_yaml_only() -> None:
    ids = _recap_ids("401k")
    assert ids == ["Y1", "Y2", "Y3", "Y4", "Y5", "Y6", "Y7", "Y8"]
    matches = _recap_match_ids("401k")
    assert matches == {"Y1", "Y2", "Y3", "Y4", "Y5", "Y6", "Y7", "Y8", "Y9"}
    assert "Y10" not in matches
    assert "Y14" not in matches


def test_403b_recap_is_exclusive_from_docx() -> None:
    """403(b) Important Information from tests/test copy.docx image26."""
    ids = _recap_ids("403b")
    assert ids == ["Y1", "Y6", "Y8", "Y10", "Y14"]
    # No 401(k)-only ADP / safe harbor / top-heavy bullets.
    assert "Y2" not in ids
    assert "Y3" not in ids
    assert "Y4" not in ids
    assert "Y5" not in ids
    assert "Y7" not in ids

    matches = _recap_match_ids("403b")
    assert "Y10" in matches
    assert "Y14" in matches
    assert "Y2" not in matches
    assert "Y3" not in matches
    assert "Y7" not in matches

    texts = " ".join(
        str(item.get("match") or "")
        for item in paragraphs_for("403b").get("recap_bullets") or []
    ).lower()
    assert "not subject to acp" in texts or "acp nondiscrimination" in texts
    assert "fifteen" in texts or "15 years" in texts
    assert "universal availability" in texts


def test_457_recap_starts_from_401k_and_adds_y11_y13() -> None:
    ids = _recap_ids("457")
    assert ids[:8] == ["Y1", "Y2", "Y3", "Y4", "Y5", "Y6", "Y7", "Y8"]
    assert ids[-3:] == ["Y11", "Y12", "Y13"]
    matches = _recap_match_ids("457")
    assert {"Y11", "Y12", "Y13"}.issubset(matches)
    assert "Y1" in matches
    assert "Y10" not in matches


def test_403b_non_recap_overlays_still_apply() -> None:
    by_id = {str(rule.get("id")): rule for rule in rules_for("403b")["rules"]}
    assert by_id["J_ADP"]["keep_when"]["all"][0]["equals"] == "401k"
    assert by_id["I"]["keep_when"]["all"][2]["field"] == "acp_failed"


def test_recap_paragraph_starts_cover_403b_bullets() -> None:
    from services.pdf_modifier import _recap_paragraph_start

    assert _recap_paragraph_start(
        "Your plan is not subject to ACP Nondiscrimination Testing as the plan did not have any Highly Compensated Employees."
    )
    assert _recap_paragraph_start(
        "Your plan may also permit participants with over 15 years of service to make an additional catch-up contribution."
    )
    assert _recap_paragraph_start("UNIVERSAL AVAILABILITY RULE")
    assert _recap_paragraph_start(
        'The "universal availability" generally requires everyone must be able to defer.'
    )

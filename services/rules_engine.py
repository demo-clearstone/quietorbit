from __future__ import annotations

from models.plan_profile import PlanProfile
from models.review import RuleDecision
from services.plan_config import rules_for


def evaluate(profile: PlanProfile) -> list[RuleDecision]:
    """Decide which paragraphs to keep or remove.

    Purpose:
        Read the rules for the plan type and return one keep, remove, or
        skipped decision for each rule.

    Args:
        profile: Plan profile collected from the PDF, Excel, and the compliance summary.

    Returns:
        One decision per rule. A missing Action Required fact is remove.

    Raises:
        OSError: A rules file cannot be read.
        yaml.YAMLError: A rules file is not valid YAML.

    Example:
        evaluate(profile) returns a list of RuleDecision.

    Side effects:
        None. This function only reads the YAML files and returns decisions.
    """
    spec = rules_for(profile.plan_type)
    decisions: list[RuleDecision] = []
    for rule in spec.get("rules") or []:
        decisions.append(_apply_rule(rule, profile))
    return _apply_recap_method_exclusivity(decisions)


def _apply_recap_method_exclusivity(decisions: list[RuleDecision]) -> list[RuleDecision]:
    """Year End Recap HCE / method paragraphs are mutually exclusive.

    - Y4 (Safe Harbor) wins over Y2/Y3
    - Y5 (HCE current year, no future HCE) wins over Y2/Y3/Y4 Future-HCE wording
    """
    by_id = {item.rule_id: item for item in decisions}
    updated = list(decisions)
    y5 = by_id.get("Y5")
    if y5 is not None and y5.action == "keep":
        updated = [
            RuleDecision(
                rule_id=item.rule_id,
                section=item.section,
                action="remove",
                reason=f"Rule {item.rule_id} removed: current-year HCE paragraph (Y5) is kept",
            )
            if item.rule_id in {"Y2", "Y3", "Y4"} and item.action != "remove"
            else item
            for item in updated
        ]
        return updated
    y4 = by_id.get("Y4")
    if y4 is None or y4.action != "keep":
        return updated
    return [
        RuleDecision(
            rule_id=item.rule_id,
            section=item.section,
            action="remove",
            reason=f"Rule {item.rule_id} removed: Safe Harbor paragraph (Y4) is kept",
        )
        if item.rule_id in {"Y2", "Y3"} and item.action != "remove"
        else item
        for item in updated
    ]


def _apply_rule(rule: dict, profile: PlanProfile) -> RuleDecision:
    """Apply rule.

    Purpose:
        Apply rule.

    Args:
        rule: One keep-or-remove rule from the YAML files.
        profile: Plan profile collected from the PDF, Excel, and the compliance summary.

    Returns:
        a RuleDecision.

    Raises:
        None.

    Example:
        _apply_rule({}, profile) returns a RuleDecision.

    Side effects:
        None. This function only reads data and returns a value.
    """
    rule_id = str(rule.get("id"))
    section = str(rule.get("section"))
    keep_when = rule.get("keep_when") or {}
    ok, skipped, reason = _conditions_met(keep_when, profile)
    if skipped and str(rule.get("missing") or "") == "remove":
        return RuleDecision(
            rule_id=rule_id,
            section=section,
            action="remove",
            reason=f"Rule {rule_id} did not match: {reason}",
        )
    if skipped:
        return RuleDecision(
            rule_id=rule_id,
            section=section,
            action="skipped",
            reason=reason,
            skipped=True,
        )
    if ok:
        return RuleDecision(
            rule_id=rule_id,
            section=section,
            action="keep",
            reason=f"Rule {rule_id} matched: {reason}",
        )
    return RuleDecision(
        rule_id=rule_id,
        section=section,
        action=str(rule.get("else") or "remove"),
        reason=f"Rule {rule_id} did not match: {reason}",
    )


def _conditions_met(keep_when: dict, profile: PlanProfile) -> tuple[bool, bool, str]:
    """Conditions met.

    Purpose:
        Conditions met.

    Args:
        keep_when: The conditions that must all be true to keep the paragraph.
        profile: Plan profile collected from the PDF, Excel, and the compliance summary.

    Returns:
        a tuple[bool, bool, str].

    Raises:
        None.

    Example:
        _conditions_met({}, profile) returns a tuple[bool, bool, str].

    Side effects:
        None. This function only reads data and returns a value.
    """
    clauses = keep_when.get("all") or []
    reasons: list[str] = []
    missing: list[str] = []
    for clause in clauses:
        if "any_true" in clause:
            fields = clause["any_true"]
            values = [getattr(profile, name, None) for name in fields]
            if all(v is None for v in values):
                missing.extend(fields)
                reasons.append(f"missing {', '.join(fields)}")
                continue
            matched = any(v is True for v in values)
            reasons.append(f"{fields} any true={matched}")
            if not matched:
                return False, False, "; ".join(reasons)
            continue
        if clause.get("not_true"):
            field = clause["field"]
            actual = getattr(profile, field, None)
            if actual is None:
                missing.append(field)
                reasons.append(f"missing {field}")
                continue
            matched = actual is False
            reasons.append(f"{field} not true ({actual})")
            if not matched:
                return False, False, "; ".join(reasons)
            continue
        field = clause["field"]
        expected = clause.get("equals")
        actual = getattr(profile, field, None)
        if actual is None:
            missing.append(field)
            reasons.append(f"missing {field}")
            continue
        matched = actual == expected
        reasons.append(f"{field}={actual}")
        if not matched:
            return False, False, "; ".join(reasons)
    if missing:
        return False, True, "; ".join(reasons)
    return True, False, "; ".join(reasons) or "no conditions"

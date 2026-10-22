from __future__ import annotations

from models.plan_profile import PlanProfile
from models.review import RuleDecision
from services.plan_config import rules_for


def evaluate(profile: PlanProfile) -> list[RuleDecision]:
    """Return keep/remove decisions. A 403(b) plan uses config/403b.yaml."""
    spec = rules_for(profile.plan_type)
    decisions: list[RuleDecision] = []
    for rule in spec.get("rules") or []:
        decisions.append(_apply_rule(rule, profile))
    return decisions


def _apply_rule(rule: dict, profile: PlanProfile) -> RuleDecision:
    rule_id = str(rule.get("id"))
    section = str(rule.get("section"))
    keep_when = rule.get("keep_when") or {}
    ok, skipped, reason = _conditions_met(keep_when, profile)
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

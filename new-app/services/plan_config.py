"""Choose 401(k), 403(b), or 457 configuration. Each plan reads only its own file."""

from __future__ import annotations

import re

import yaml

from config.settings import CONFIG_DIR

_401K_PLAN = re.compile(r"401\s*\(?\s*k\)?[^.\n]{0,40}\bplan\b", re.I)
_403B_PLAN = re.compile(r"403\s*\(?\s*b\)?[^.\n]{0,40}\bplan\b", re.I)
_457_PLAN = re.compile(r"\b457\b[^.\n]{0,40}\bplan\b", re.I)
_401K = re.compile(r"401\s*\(?\s*k\)?", re.I)
_403B = re.compile(r"403\s*\(?\s*b\)?", re.I)
_457 = re.compile(r"\b457\b", re.I)

_PARAGRAPH_KEYS = (
    "action_required_headings",
    "notices",
    "sample_letters",
    "excess_summary",
    "recap_bullets",
)

_PACKAGE_DEFAULTS = {
    "keep_brf": False,
    "require_410b_report": True,
    "rewrite_adp_mentions": False,
    "ignore_adp_results": False,
    "acp_notice_amount": False,
    "keep_soc": False,
    "require_full_reports": True,
}


def is_403b_plan(plan_type: str | None) -> bool:
    return "403" in (plan_type or "").lower()


def is_457_plan(plan_type: str | None) -> bool:
    """Checking whether the plan is a 457 plan."""
    return "457" in (plan_type or "").lower()


def plan_family(text: str) -> str | None:
    """Plan type printed on the valuation package. This wins over the Excel cell."""
    body = text or ""
    named_401 = bool(_401K_PLAN.search(body))
    named_403 = bool(_403B_PLAN.search(body))
    named_457 = bool(_457_PLAN.search(body))
    if named_457 and not named_401 and not named_403:
        return "457"
    if named_401 and not named_403:
        return "401k"
    if named_403 and not named_401:
        return "403b"
    if _403B.search(body) and not _401K.search(body) and not _457.search(body):
        return "403b"
    if _401K.search(body) and not _403B.search(body) and not _457.search(body):
        return "401k"
    if _457.search(body) and not _401K.search(body) and not _403B.search(body):
        return "457"
    return None


def package_flags(plan_type: str | None) -> dict:
    """Loading the rules for this plan type."""
    flags = dict(_PACKAGE_DEFAULTS)
    if is_403b_plan(plan_type):
        flags.update(_load_403b().get("package") or {})
    elif is_457_plan(plan_type):
        flags.update(_load_457().get("package") or {})
    return flags


def bookmark_overrides(plan_type: str | None) -> dict[str, str]:
    if not is_403b_plan(plan_type):
        return {}
    raw = _load_403b().get("bookmarks") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def rules_for(plan_type: str | None) -> dict:
    rules = list(_load_yaml("rules.yaml").get("rules") or [])
    extra: list[dict] = []
    if is_403b_plan(plan_type):
        extra = list(_load_403b().get("rules") or [])
    elif is_457_plan(plan_type):
        extra = list(_load_457().get("rules") or [])
    if not extra:
        return {"rules": rules}
    replacements = {str(item.get("id")): item for item in extra}
    merged: list[dict] = []
    for rule in rules:
        merged.append(replacements.pop(str(rule.get("id")), rule))
    merged.extend(replacements.values())
    return {"rules": merged}


def paragraphs_for(plan_type: str | None) -> dict:
    base = _load_yaml("paragraphs.yaml")
    overlay: dict = {}
    if is_403b_plan(plan_type):
        overlay = _load_403b().get("paragraphs") or {}
    elif is_457_plan(plan_type):
        overlay = _load_457().get("paragraphs") or {}
    if not overlay:
        return base
    merged = dict(base)
    for key in _PARAGRAPH_KEYS:
        extra = list(overlay.get(key) or [])
        if not extra:
            continue
        replace_ids = {str(item.get("id")) for item in extra}
        kept = [
            item
            for item in (base.get(key) or [])
            if str(item.get("id")) not in replace_ids
        ]
        merged[key] = kept + extra
    return merged


def _load_403b() -> dict:
    return _load_yaml("403b.yaml")


def _load_457() -> dict:
    return _load_yaml("457.yaml")


def _load_yaml(name: str) -> dict:
    data = yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}

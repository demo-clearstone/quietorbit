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

# One file for each page that has keep-or-remove text. Action Required is loaded separately.
_PAGE_FILES = (
    "excess_return_notice.yaml",
    "failure_letters.yaml",
    "excess_summary.yaml",
    "year_end_recap.yaml",
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
    rules = _action_required_rules(plan_type) + _page_rules()
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
    base = _page_paragraphs()
    base["action_required_headings"] = _action_required_headings(plan_type)
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


def _action_required_items(plan_type: str | None) -> list[dict]:
    data = _load_yaml("action_required.yaml")
    items = [item for item in (data.get("paragraphs") or []) if isinstance(item, dict)]
    overlay = [item for item in (data.get("403b") or []) if isinstance(item, dict)] if is_403b_plan(plan_type) else []
    replacements = {str(item.get("id")): item for item in overlay}
    chosen: list[dict] = []
    replaced: set[str] = set()
    for item in items:
        rule_id = str(item.get("id"))
        if rule_id in replacements:
            if rule_id not in replaced:
                chosen.append(replacements[rule_id])
                replaced.add(rule_id)
            continue
        chosen.append(item)
    for item in overlay:
        if str(item.get("id")) not in replaced:
            chosen.append(item)
    return chosen


def _action_required_rules(plan_type: str | None) -> list[dict]:
    rules: list[dict] = []
    seen: set[str] = set()
    for item in _action_required_items(plan_type):
        rule_id = str(item.get("id"))
        if rule_id in seen:
            continue
        seen.add(rule_id)
        rules.append(
            {
                "id": item.get("id"),
                "section": item.get("section"),
                "keep_when": item.get("keep_when") or {},
                "else": item.get("else") or "remove",
                "missing": "remove",
            }
        )
    return rules


def _action_required_headings(plan_type: str | None) -> list[dict]:
    """Every Action Required heading for this plan, including the other plan's wording."""
    data = _load_yaml("action_required.yaml")
    active_ids = {str(item.get("id")) for item in _action_required_items(plan_type)}
    sources = [
        item
        for item in list(data.get("paragraphs") or []) + list(data.get("403b") or [])
        if isinstance(item, dict) and str(item.get("id")) in active_ids
    ]
    headings: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in sources:
        for block in item.get("headings") or []:
            if not isinstance(block, dict) or not block.get("heading"):
                continue
            key = (str(item.get("id")), str(block.get("heading")))
            if key in seen:
                continue
            seen.add(key)
            spec = {"id": item.get("id"), "heading": block.get("heading")}
            for field in ("variant", "block_excludes", "block_contains", "must_include", "extra"):
                if block.get(field) is not None:
                    spec[field] = block[field]
            headings.append(spec)
    return headings


def _page_rules() -> list[dict]:
    rules: list[dict] = []
    for name in _PAGE_FILES:
        rules.extend(item for item in (_load_yaml(name).get("rules") or []) if isinstance(item, dict))
    return rules


def _page_paragraphs() -> dict:
    merged = {key: [] for key in _PARAGRAPH_KEYS if key != "action_required_headings"}
    for name in _PAGE_FILES:
        data = _load_yaml(name)
        for key in merged:
            merged[key].extend(item for item in (data.get(key) or []) if isinstance(item, dict))
    return merged


def _load_403b() -> dict:
    return _load_yaml("plan_403b.yaml")


def _load_457() -> dict:
    return _load_yaml("plan_457.yaml")


def _load_yaml(name: str) -> dict:
    data = yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}

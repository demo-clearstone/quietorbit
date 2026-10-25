"""Plan configuration. Every YAML file is read here.

Input for the plan functions is the plan type: "401k", "403b", "457", or empty.
A 401(k) plan uses the page files only. A 403(b) or 457 plan then replaces
matching rule ids from its own file.

Files and what they return:
- action_required.yaml: Action Required paragraphs, keep/remove plus headings.
- excess_return_notice.yaml, failure_letters.yaml, excess_summary.yaml,
  year_end_recap.yaml: the other keep/remove pages.
- plan_403b.yaml and plan_457.yaml: plan-type replacements.
- package_order.yaml: page order and bookmark titles.
- compliance_summary.yaml: what each Compliance Testing Summary line means.
"""

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
    """Check whether the plan is a 403(b) plan.

    Purpose:
        Choose the 403(b) YAML file instead of the 401(k) page files.

    Args:
        plan_type: Plan type text, such as "403b" or "403(b)". ``None`` and "" are not a 403(b) plan.

    Returns:
        ``True`` when the text contains "403". Otherwise ``False``.

    Raises:
        None.

    Example:
        ``is_403b_plan("403(b)")`` returns ``True``. ``is_403b_plan("401k")`` returns ``False``.

    Side effects:
        None.
    """
    return "403" in (plan_type or "").lower()


def is_457_plan(plan_type: str | None) -> bool:
    """Check whether the plan is a 457 plan.

    Purpose:
        Choose the 457 YAML file instead of the 401(k) page files.

    Args:
        plan_type: Plan type text, such as "457". ``None`` and "" are not a 457 plan.

    Returns:
        ``True`` when the text contains "457". Otherwise ``False``.

    Raises:
        None.

    Example:
        ``is_457_plan("457")`` returns ``True``. ``is_457_plan("401k")`` returns ``False``.

    Side effects:
        None.
    """
    return "457" in (plan_type or "").lower()


def plan_family(text: str) -> str | None:
    """Read the plan type printed on the package.

    Purpose:
        Let the cover letter decide 401(k), 403(b), or 457. That result wins over the Excel cell.

    Args:
        text: Cover-letter text. An empty string returns ``None``.

    Returns:
        ``"401k"``, ``"403b"``, ``"457"``, or ``None`` when the text names more than one family
        or names none.

    Raises:
        None.

    Example:
        ``plan_family("HARBOR MANUFACTURING 401(k) PLAN")`` returns ``"401k"``.

    Side effects:
        None.
    """
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
    """Load the package flags for one plan type.

    Purpose:
        Tell assembly which plan-type rules to apply, such as keeping the BRF report.

    Args:
        plan_type: ``"401k"``, ``"403b"``, ``"457"``, or empty.
            Empty and ``"401k"`` keep the default flags.

    Returns:
        A dict of flags. Keys include ``keep_brf``, ``rewrite_adp_mentions``, and ``keep_soc``.
        A 403(b) plan reads the package block in config/plan_403b.yaml.
        A 457 plan reads the package block in config/plan_457.yaml.

    Raises:
        OSError: The plan YAML file cannot be read.
        yaml.YAMLError: That file is not valid YAML.

    Example:
        ``package_flags("401k")["keep_brf"]`` returns ``False``.
        ``package_flags("403b")["keep_brf"]`` returns ``True``.

    Side effects:
        None. This function only reads configuration and returns a value.
    """
    flags = dict(_PACKAGE_DEFAULTS)
    if is_403b_plan(plan_type):
        flags.update(_load_403b().get("package") or {})
    elif is_457_plan(plan_type):
        flags.update(_load_457().get("package") or {})
    return flags


def bookmark_overrides(plan_type: str | None) -> dict[str, str]:
    """Load bookmark titles that replace the 401(k) titles.

    Purpose:
        Use the 403(b) bookmark names, such as "ACP Test" instead of "ADP/ACP Tests".

    Args:
        plan_type: Plan type. Only a 403(b) plan reads config/plan_403b.yaml.
            Every other value returns an empty mapping.

    Returns:
        ``{section name: bookmark title}``.

    Raises:
        OSError: config/plan_403b.yaml cannot be read for a 403(b) plan.
        yaml.YAMLError: that file is not valid YAML.

    Example:
        ``bookmark_overrides("403b")["ADP/ACP"]`` returns ``"ACP Test"``.
        ``bookmark_overrides("401k")`` returns ``{}``.

    Side effects:
        None. This function only reads configuration and returns a value.
    """
    if not is_403b_plan(plan_type):
        return {}
    raw = _load_403b().get("bookmarks") or {}
    if not isinstance(raw, dict):
        return {}
    return {str(key): str(value) for key, value in raw.items()}


def rules_for(plan_type: str | None) -> dict:
    """Build the keep-or-remove rules for one plan type.

    Purpose:
        Give the rules engine every paragraph rule in page order.

    Args:
        plan_type: ``"401k"``, ``"403b"``, ``"457"``, or empty.
            A 403(b) or 457 plan replaces rules that share an id.

    Returns:
        ``{"rules": [...]}``. Each rule has ``id``, ``section``, ``keep_when``, and ``else``.
        Reads config/action_required.yaml, excess_return_notice.yaml, failure_letters.yaml,
        excess_summary.yaml, year_end_recap.yaml, then plan_403b.yaml or plan_457.yaml.

    Raises:
        OSError: A YAML file cannot be read.
        yaml.YAMLError: A YAML file is not valid.

    Example:
        ``rules_for("401k")["rules"][0]["id"]`` returns ``"A"``, the compliance-failure paragraph.
        ``rules_for("403b")`` uses the ACP wording for rules B, C, D, and E.

    Side effects:
        None. This function only reads configuration and returns a value.
    """
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
    """Build the heading text the keep-or-remove rules search for.

    Purpose:
        Match each rule id to the heading printed on that page.

    Args:
        plan_type: ``"401k"``, ``"403b"``, ``"457"``, or empty.
            A 403(b) or 457 plan replaces headings that share an id.

    Returns:
        A dict with ``action_required_headings``, ``notices``, ``sample_letters``,
        ``excess_summary``, and ``recap_bullets``. Each value is a list of heading specs.
        Reads the same YAML files as ``rules_for``.

    Raises:
        OSError: A YAML file cannot be read.
        yaml.YAMLError: A YAML file is not valid.

    Example:
        ``paragraphs_for("401k")["action_required_headings"][0]["id"]`` returns ``"A"``.
        The heading is "IMMEDIATE ACTION REQUIRED - COMPLIANCE TEST FAILURE".

    Side effects:
        None. This function only reads configuration and returns a value.
    """
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


def load_package_order() -> dict:
    """Load the page order and bookmark titles.

    Purpose:
        Tell file ordering and bookmarks which section comes next.

    Args:
        None.

    Returns:
        The mapping in config/package_order.yaml: ``combine_order``, ``expected_order``, and ``bookmarks``.

    Raises:
        OSError: config/package_order.yaml cannot be read.
        yaml.YAMLError: that file is not valid YAML.

    Example:
        ``load_package_order()["combine_order"][0]`` returns ``"Cover Letter"``.

    Side effects:
        None. This function only reads a file and returns a value.
    """
    return _load_yaml("package_order.yaml")


def load_compliance_summary() -> list[dict]:
    """Load the meaning of each Compliance Testing Summary line.

    Purpose:
        Let the package checks compare later report pages with the summary.

    Args:
        None.

    Returns:
        ``[{code, name, means}, ...]`` from config/compliance_summary.yaml.

    Raises:
        OSError: config/compliance_summary.yaml cannot be read.
        yaml.YAMLError: that file is not valid YAML.

    Example:
        ``load_compliance_summary()[0]["code"]`` returns ``"top_heavy"``.

    Side effects:
        None. This function only reads a file and returns a value.
    """
    data = _load_yaml("compliance_summary.yaml")
    return [row for row in data.get("tests") or [] if isinstance(row, dict)]


def _action_required_items(plan_type: str | None) -> list[dict]:
    """Load the Action Required paragraphs for one plan type.

    Purpose:
        Keep the 401(k) paragraphs, and swap in the 403(b) wording for B, C, D, and E.

    Args:
        plan_type: Plan type. Only ``"403b"`` reads the ``403b`` list in config/action_required.yaml.

    Returns:
        One dict per paragraph, with ``section``, ``keep_when``, and ``headings``.

    Raises:
        OSError: config/action_required.yaml cannot be read.
        yaml.YAMLError: that file is not valid YAML.

    Example:
        ``_action_required_items("401k")[0]["id"]`` returns ``"A"``.
        ``_action_required_items("403b")`` uses "ACP test failure, prior year" for id B.

    Side effects:
        None.
    """
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
    """Turn Action Required paragraphs into keep-or-remove rules.

    Purpose:
        Produce one rule per paragraph id. A second heading for the same id does not add a second rule.

    Args:
        plan_type: Passed through to ``_action_required_items``.

    Returns:
        Rules with ``id``, ``section``, ``keep_when``, ``else``, and ``missing`` set to ``"remove"``.
        A missing fact therefore removes the paragraph.

    Raises:
        OSError: config/action_required.yaml cannot be read.
        yaml.YAMLError: that file is not valid YAML.

    Example:
        The rule for id G has section "No immediate action".

    Side effects:
        None.
    """
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
    """Collect every Action Required heading the remover should search for.

    Purpose:
        Find a paragraph even when a 401(k) package uses the 403(b) heading, or the reverse.

    Args:
        plan_type: Used to know which paragraph ids are active. Both families' heading text is returned.

    Returns:
        ``[{id, heading, ...}, ...]``. Optional keys are ``variant``, ``block_excludes``,
        ``block_contains``, ``must_include``, and ``extra``.

    Raises:
        OSError: config/action_required.yaml cannot be read.
        yaml.YAMLError: that file is not valid YAML.

    Example:
        Id F returns both "IMMEDIATE ACTION REQUIRED - TOP HEAVY" and
        "ATTENTION REQUIRED - TOP HEAVY DETERMINATION".

    Side effects:
        None.
    """
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
    """Load the keep-or-remove rules for the pages after Action Required.

    Purpose:
        Add the Excess Return Notice, letters, Excess Summary, and Year End Recap rules.

    Args:
        None.

    Returns:
        The ``rules`` lists from excess_return_notice.yaml, failure_letters.yaml,
        excess_summary.yaml, and year_end_recap.yaml, in that order.

    Raises:
        OSError: One of those files cannot be read.
        yaml.YAMLError: One of those files is not valid YAML.

    Example:
        The first rule id is ``"I"``, the current-year Excess Return Notice.

    Side effects:
        None.
    """
    rules: list[dict] = []
    for name in _PAGE_FILES:
        rules.extend(item for item in (_load_yaml(name).get("rules") or []) if isinstance(item, dict))
    return rules


def _page_paragraphs() -> dict:
    """Load the headings for the pages after Action Required.

    Purpose:
        Give each later rule the heading text printed on its page.

    Args:
        None.

    Returns:
        ``notices``, ``sample_letters``, ``excess_summary``, and ``recap_bullets``
        from the same four YAML files as ``_page_rules``.

    Raises:
        OSError: One of those files cannot be read.
        yaml.YAMLError: One of those files is not valid YAML.

    Example:
        ``_page_paragraphs()["excess_summary"][0]["heading"]`` returns ``"Excess Summary Report"``.

    Side effects:
        None.
    """
    merged = {key: [] for key in _PARAGRAPH_KEYS if key != "action_required_headings"}
    for name in _PAGE_FILES:
        data = _load_yaml(name)
        for key in merged:
            merged[key].extend(item for item in (data.get(key) or []) if isinstance(item, dict))
    return merged


def _load_403b() -> dict:
    """Read the 403(b) plan file.

    Purpose:
        Supply the 403(b) package flags, bookmark titles, rules, and headings.

    Args:
        None.

    Returns:
        The mapping in config/plan_403b.yaml: ``package``, ``bookmarks``, ``rules``, and ``paragraphs``.

    Raises:
        OSError: The file cannot be read.
        yaml.YAMLError: The file is not valid YAML.

    Example:
        ``_load_403b()["bookmarks"]["ADP/ACP"]`` returns ``"ACP Test"``.

    Side effects:
        None.
    """
    return _load_yaml("plan_403b.yaml")


def _load_457() -> dict:
    """Read the 457 plan file.

    Purpose:
        Supply the 457 package flags and the Year End Recap rules.

    Args:
        None.

    Returns:
        The mapping in config/plan_457.yaml: ``package``, ``rules``, and ``paragraphs``.

    Raises:
        OSError: The file cannot be read.
        yaml.YAMLError: The file is not valid YAML.

    Example:
        ``_load_457()["rules"][0]["id"]`` returns ``"Y11"``.

    Side effects:
        None.
    """
    return _load_yaml("plan_457.yaml")


def _load_yaml(name: str) -> dict:
    """Read one YAML file from the config folder.

    Purpose:
        Turn a configuration file into a dictionary the other functions can use.

    Args:
        name: File name inside config/, such as ``"action_required.yaml"``.
            It must be a file name, not a full path.

    Returns:
        The parsed mapping. An empty file, or a file whose top value is not a mapping, returns ``{}``.

    Raises:
        OSError: The file cannot be read.
        yaml.YAMLError: The file is not valid YAML.

    Example:
        ``_load_yaml("excess_summary.yaml")["rules"][0]["id"]`` returns ``"ES"``.

    Side effects:
        None. This function only reads a file and returns a value.
    """
    data = yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}

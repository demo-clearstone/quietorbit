"""Regex patterns for cover-page and test-summary extraction. Tune when sample PDFs arrive."""

COVER_PATTERNS: dict[str, list[str]] = {
    "plan_number": [
        r"Plan\s*(?:No\.?|Number|#)\s*[:#]?\s*(\d{3,10})",
        r"\bPlan\s+(\d{5,10})\b",
        r"\b(\d{6})\b",
    ],
    "plan_name": [
        r"Plan\s*Name\s*[:#]?\s*(.+)",
        r"RE:\s*(.+)",
    ],
    "company_name": [
        r"Company\s*Name\s*[:#]?\s*(.+)",
        r"Employer\s*Name\s*[:#]?\s*(.+)",
        r"Sponsor\s*[:#]?\s*(.+)",
    ],
    "company_address": [
        r"(?:Company\s*)?Address\s*[:#]?\s*(.+)",
    ],
    "plan_type": [
        r"Plan\s*Type\s*[:#]?\s*(.+)",
        r"\b(403\s*\(?B\)?|401\s*\(?K\)?)\s+PLAN\b",
    ],
    "plan_year": [
        r"Plan\s*Year\s*[:#]?\s*(\d{1,2}/\d{1,2}/\d{4})\s*[-–to]+\s*(\d{1,2}/\d{1,2}/\d{4})",
        r"Plan\s*Year\s*Ending\s*[:#]?\s*(\d{1,2}/\d{1,2}/\d{4})",
        r"period ending\s+(\d{1,2}/\d{1,2}/\d{4})",
        r"PYE\s*[:#]?\s*(\d{1,2}/\d{1,2}/\d{4})",
        r"(\d{1,2}/\d{1,2}/\d{4})\s*[-–]\s*(\d{1,2}/\d{1,2}/\d{4})",
    ],
}

TEST_PATTERNS: dict[str, list[str]] = {
    "testing_method": [
        r"Testing\s*Method\s*[:#]?\s*(CURRENT|PRIOR)",
        r"\b(CURRENT|PRIOR)\s+METHOD\b",
        r"\b(Prior|Current)\s+Testing\b",
    ],
    "top_heavy_percent": [
        r"Top\s*Heavy\s*(?:Percent(?:age)?|Ratio)?\s*[:#]?\s*(\d+(?:\.\d+)?)\s*%?",
        r"Top-Heavy\s*[:#]?\s*(\d+(?:\.\d+)?)\s*%",
    ],
    "adp_qnec": [
        r"ADP\s*QNEC\s*[:#]?\s*\$?\s*([\d,]+(?:\.\d{2})?)",
        r"\$\s*([\d,]+(?:\.\d{2})?)\s+QNEC\s+contribution\s+to\s+the\s+NHCE'?s?\s+for\s+the\s+ADP\s+test",
    ],
    "acp_qnec": [
        r"ACP\s*QNEC\s*[:#]?\s*\$?\s*([\d,]+(?:\.\d{2})?)",
        r"\$\s*([\d,]+(?:\.\d{2})?)\s+QNEC\s+contribution\s+to\s+the\s+NHCE'?s?\s+for\s+the\s+ACP\s+test",
    ],
    "deferral_refund": [
        r"Deferral\s*Refund\s*[:#]?\s*\$?\s*([\d,]+(?:\.\d{2})?)",
    ],
    "match_refund": [
        r"Match(?:ing)?\s*Refund\s*[:#]?\s*\$?\s*([\d,]+(?:\.\d{2})?)",
    ],
}

FAIL_FLAGS: dict[str, list[str]] = {
    "adp_failed": [
        r"ADP\s+Test\s*:\s*Fail",
        r"Average Deferral Percentage.{0,80}Tested:\s*Fail",
    ],
    "acp_failed": [
        r"ACP\s+Test\s*:\s*Fail",
        r"Average Contribution Percentage.{0,80}Tested:\s*Fail",
    ],
    "fail_402g": [
        r"402\s*\(?g\)?\s*Test\s*:\s*Fail",
        r"402\s*\(?g\)?.{0,60}Tested:\s*Fail",
    ],
    "fail_415": [
        r"415\s+Test\s*:\s*Fail",
        r"415\s*\(?c\)?.{0,60}Tested:\s*Fail",
        r"Annual Additions.{0,60}Tested:\s*Fail",
    ],
    "returns_required": [
        r"(?<!No )Returns?\s+Required",
        r"(?<!No )Refunds?\s+Required",
        r"Contribution refunds to participants are required",
    ],
    "variance_report": [r"(?<!No )Variance\s+Report"],
    "contributions_required": [
        r"(?<!No )Contributions?\s+Required",
        r"Census adjustment required",
    ],
    "partially_vested": [r"partially vested"],
    "safe_harbor": [
        r"Safe Harbor:\s*Yes",
        r"\bN/A\s*SH\b",
        r"switching to (?:SH|safe harbor)",
        r"(?:safe harbor|SH) next year",
    ],
    "catchup_disallowed": [
        r"Catch-up contributions are not allowed",
        r"catchup contributions are not allowed",
        r"Catch-up allowed:\s*No",
    ],
    "per_payroll_match": [r"Per Payroll Match:\s*Yes"],
    "hce_current": [r"HCE Current Year:\s*Yes"],
    "hce_future": [r"HCE Future(?:s)? year:\s*Yes", r"HCE Future Year:\s*Yes"],
    "after_12_months": [
        r"After\s+12\s+Months",
        r"After 12-months",
        r"AFTER 12-MONTHS",
        r"after the 12-month correction period",
    ],
}

PASS_FLAGS: dict[str, list[str]] = {
    "adp_failed": [r"ADP\s+Test\s*:\s*Pass", r"Average Deferral Percentage.{0,80}Tested:\s*Pass"],
    "acp_failed": [r"ACP\s+Test\s*:\s*Pass", r"Average Contribution Percentage.{0,80}Tested:\s*Pass"],
    "fail_402g": [r"402\s*\(?g\)?\s*Test\s*:\s*Pass", r"402\s*\(?g\)?.{0,60}Tested:\s*Pass"],
    "fail_415": [r"415\s+Test\s*:\s*Pass", r"415\s*\(?c\)?.{0,60}Tested:\s*Pass", r"Annual Additions.{0,60}Tested:\s*Pass"],
    "returns_required": [r"No Returns Required", r"No Refunds Required"],
    "variance_report": [r"No Variance Report"],
    "contributions_required": [r"No Contributions Required", r"No Contribution Adjustment"],
    "safe_harbor": [r"Safe Harbor:\s*No"],
    "catchup_disallowed": [r"Catch-up allowed:\s*Yes"],
    "per_payroll_match": [r"Per Payroll Match:\s*No"],
    "hce_current": [r"HCE Current Year:\s*No"],
    "hce_future": [r"HCE Future(?:s)? year:\s*No", r"HCE Future Year:\s*No"],
    "after_12_months": [r"Correction Within 12 Months", r"within 12 months"],
}

# TEST23 §B.1: drop the compliance-failure paragraph when this is noted on the 402(g) test.
RETURNS_ALREADY_PROCESSED_PATTERNS: list[str] = [
    r"excess returns have already been processed",
    r"returns have already been processed",
]

DEADLINE_402G_PATTERNS: list[str] = [
    r"not processed by\s+4/?15",
    r"not processed before\s+4/?15",
    r"processed after\s+(?:the\s+)?4/?15",
    r"4/?15 deadline",
    r"after April 15",
]

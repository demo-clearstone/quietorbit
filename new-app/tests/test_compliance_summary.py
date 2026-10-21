import fitz

from models.plan_profile import PlanProfile
from services.assembly_stops import stop_reasons
from services.package_polish import package_checks, summary_test_record
from services.source_profile import parse_summary_text

_PLAN = "OUR HOUSE, INC. 401(K) RETIREMENT PLAN"
_NUMBER = "800808"
_PYE = "June 30, 2026"


HEADING_X = 72
RESULT_X = 150


def build_our_house_summary(
    *,
    percent: str = "7.26",
    top_heavy_line: str = "Plan is not Top Heavy",
    report_percent: str | None = "7.26",
    coverage: list[tuple[str, str, str]] | None = None,
    abpt_note: bool = False,
    brf: str = "Pass",
    results: dict[str, str] | None = None,
    with_reports: bool = False,
    brf_report: bool = False,
    extra_report: str | None = None,
) -> fitz.Document:
    """Compliance Testing Summary. Every test heading and result uses the same x."""
    doc = fitz.open()
    page = doc.new_page()
    coverage = coverage or [
        ("Standard", "Pass", "100"),
        ("401(k)", "Pass", "100"),
        ("401(m)", "Pass", "100"),
    ]
    results = {
        "401(a)(4)": "Pass",
        "414(s)": "Pass",
        "402(g)": "Pass",
        "415(c)": "Pass",
        "ADP": "Pass",
        "ACP": "Pass",
        **(results or {}),
    }

    def center(text: str, y: float, size: float, font: str) -> tuple[float, float]:
        width = fitz.get_text_length(text, fontname=font, fontsize=size)
        x = (page.rect.width - width) / 2
        page.insert_text((x, y), text, fontsize=size, fontname=font)
        return x, width

    title = "Compliance Testing Summary of Results"
    x, width = center(title, 64, 16, "hebo")
    page.draw_line(fitz.Point(x, 70), fitz.Point(x + width, 70), width=1.1)
    pye = f"Plan Year End: {_PYE}"
    x, width = center(pye, 90, 12, "helv")
    page.draw_line(fitz.Point(x, 94), fitz.Point(x + width, 94), width=0.8)
    center(_PLAN, 114, 12, "hebo")
    center(_NUMBER, 132, 12, "hebo")

    y = 168

    def heading(text: str) -> None:
        nonlocal y
        page.insert_text((HEADING_X, y), text, fontsize=11, fontname="hebo")
        width = fitz.get_text_length(text, fontname="hebo", fontsize=11)
        page.draw_line(fitz.Point(HEADING_X, y + 2), fitz.Point(HEADING_X + width, y + 2), width=0.7)
        y += 18

    def line(text: str) -> None:
        nonlocal y
        page.insert_text((RESULT_X, y), text, fontsize=11, fontname="helv")
        y += 16

    heading("416 Top Heavy Determination")
    line(f"Test:  {percent}% to Key Employees")
    line(top_heavy_line)
    y += 8
    heading("410(b) Coverage Test")
    for label, outcome, ratio in coverage:
        line(f"{label}:  {outcome} Ratio percent {ratio}%")
    if abpt_note:
        line("Average Benefits Test Passed; no action needed for Failed 410(b) Coverage Test")
        y += 8
        heading("Average Benefit Test")
        line("Test:  Pass")
    y += 8
    heading("Benefits, Rights and Features Test")
    line(f"Test:  {brf}")
    y += 8
    heading("401(a)(4) Test")
    line(f"Test:  {results['401(a)(4)']}")
    y += 8
    heading("414(s) Test")
    line(f"Test:  {results['414(s)']}")
    y += 8
    heading("402(g) Deferral Limits")
    line(f"Test:  {results['402(g)']}")
    y += 8
    heading("415(c) Annual Additions")
    line(f"Test:  {results['415(c)']}")
    y += 8
    heading("Average Deferral Percentage (ADP)")
    line(f"Test:  {results['ADP']}")
    y += 8
    heading("Average Contribution Percentage (ACP)")
    line(f"Test:  {results['ACP']}")

    def add_report(text: str) -> None:
        report = doc.new_page()
        report.insert_text((72, 72), text, fontsize=12, fontname="helv")

    if report_percent is not None:
        add_report(
            "\n".join(
                [
                    "Top Heavy Test",
                    f"Top Heavy Percent: {report_percent}%",
                    f"Plan Number: {_NUMBER}",
                    f"Plan Name: {_PLAN}",
                    "Plan Year End: 06/30/2026",
                ]
            )
        )
    if with_reports:
        coverage_text = "\n".join(f"{label}:  {outcome} Ratio percent {ratio}%" for label, outcome, ratio in coverage)
        add_report(f"410(b) Coverage Test\n{coverage_text}\nPlan Number: {_NUMBER}")
        add_report(f"401(a)(4) Test\nTest: {results['401(a)(4)']}\nPlan Number: {_NUMBER}")
        add_report(f"414(s) Test\nTest: {results['414(s)']}\nPlan Number: {_NUMBER}")
        add_report(f"402(g) Test\nTest: {results['402(g)']}\nPlan Number: {_NUMBER}")
        add_report(f"415 Annual Additions\nTest: {results['415(c)']}\nPlan Number: {_NUMBER}")
        add_report(f"ADP Test\nAverage Deferral Percentage\nTest: {results['ADP']}\nPlan Number: {_NUMBER}")
        add_report(f"ACP Test\nAverage Contribution Percentage\nTest: {results['ACP']}\nPlan Number: {_NUMBER}")
        if abpt_note:
            add_report(f"Average Benefit Percentage Test\nTest: Pass\nPlan Number: {_NUMBER}")
    if brf_report:
        add_report(f"Benefits, Rights and Features Test\nTest: {brf}\nPlan Number: {_NUMBER}")
    if extra_report:
        add_report(extra_report)
    return doc


def _checks(doc: fitz.Document) -> dict:
    items = package_checks(
        doc,
        PlanProfile(plan_number=_NUMBER, plan_name=_PLAN, plan_year_end="06/30/2026"),
    )
    return {item.code: item for item in items}


def test_our_house_summary_matches_the_top_heavy_report():
    doc = build_our_house_summary()
    try:
        text = doc[0].get_text("text")
        parsed = parse_summary_text(text)
        assert parsed["plan_number"] == _NUMBER
        assert "OUR HOUSE" in parsed["plan_name"]
        assert parsed["plan_year_end"] == "06/30/2026"
        assert parsed["top_heavy_percent"] == 7.26
        assert parsed["top_heavy"] is False
        assert parsed["fail_402g"] is False
        assert parsed["fail_415"] is False

        items = _checks(doc)
        assert items["top_heavy_summary"].passed is True
        assert "7.26" in items["top_heavy_summary"].detail
        assert items["summary_410(b)"].passed is True
        assert items["summary_402(g)"].passed is True
        assert items["summary_415"].passed is True
    finally:
        doc.close()


def test_unresolved_top_heavy_line_must_say_plan_is_not_top_heavy():
    doc = build_our_house_summary(top_heavy_line="Plan is/is not Top Heavy", report_percent=None)
    try:
        item = _checks(doc)["top_heavy_summary"]
        reasons = stop_reasons(doc, PlanProfile(), ["2025ResultSumm.pdf"])
    finally:
        doc.close()
    assert item.passed is False
    assert 'Plan is/is not Top Heavy should be Plan is not Top Heavy' in item.detail
    assert any("Plan is/is not" in reason for reason in reasons)


def test_top_heavy_over_60_percent_must_say_plan_is_top_heavy():
    doc = build_our_house_summary(
        percent="70.00",
        top_heavy_line="Plan is/is not Top Heavy",
        report_percent="70.00",
    )
    try:
        item = _checks(doc)["top_heavy_summary"]
    finally:
        doc.close()
    assert item.passed is False
    assert "Plan is Top Heavy" in item.detail


def test_sixty_percent_is_not_top_heavy_and_zero_uses_two_decimals():
    at_sixty = build_our_house_summary(percent="60.00", report_percent="60.00")
    try:
        assert _checks(at_sixty)["top_heavy_summary"].passed is True
    finally:
        at_sixty.close()

    over = build_our_house_summary(
        percent="60.01",
        top_heavy_line="Plan is not Top Heavy",
        report_percent="60.01",
    )
    try:
        assert _checks(over)["top_heavy_summary"].passed is False
    finally:
        over.close()

    bare_zero = build_our_house_summary(percent="0", report_percent="0.00")
    try:
        zero_item = _checks(bare_zero)["top_heavy_summary"]
    finally:
        bare_zero.close()
    assert zero_item.passed is False
    assert "0.00%" in zero_item.detail

    shown = build_our_house_summary(percent="0.00", report_percent="0.00")
    try:
        assert _checks(shown)["top_heavy_summary"].passed is True
    finally:
        shown.close()


def test_summary_percent_must_equal_the_top_heavy_report():
    doc = build_our_house_summary(percent="7.26", report_percent="9.10")
    try:
        item = _checks(doc)["top_heavy_summary"]
    finally:
        doc.close()
    assert item.passed is False
    assert "7.26" in item.detail
    assert "9.1" in item.detail


def test_summary_record_keeps_the_meaning_of_each_test():
    record = {row["code"]: " ".join(str(row["means"]).split()) for row in summary_test_record()}
    assert "Key-employee" in record["top_heavy"]
    assert "Profit sharing and SHNE" in record["410b_standard"]
    assert "Salary deferrals and Roth" in record["410b_401k"]
    assert "Match and safe harbor match" in record["410b_401m"]
    assert "Average Benefits Test Passed" in record["410b_failed"]
    assert "BRF report is not included" in record["brf"]
    assert "nondiscrimination" in record["401a4"]
    assert "compensation result" in record["414s"]
    assert "deferral limit" in record["402g"]
    assert "annual additions" in record["415"]
    assert "ADP result" in record["adp"]
    assert "ACP result" in record["acp"]

    doc = build_our_house_summary(with_reports=True)
    try:
        items = _checks(doc)
    finally:
        doc.close()
    assert items["summary_410(b)"].passed is True
    assert "Profit sharing and SHNE" in items["summary_410(b)"].detail
    assert "Salary deferrals and Roth" in items["summary_410(b)"].detail
    assert "Match and safe harbor match" in items["summary_410(b)"].detail
    assert items["summary_brf"].passed is True
    assert "not included" in items["summary_brf"].detail
    assert items["summary_401(a)(4)"].passed is True
    assert "nondiscrimination" in items["summary_401(a)(4)"].detail
    assert items["summary_414(s)"].passed is True
    assert items["summary_ADP"].passed is True
    assert items["summary_ACP"].passed is True
    assert "deferral limit" in items["summary_402(g)"].detail
    assert "annual additions" in items["summary_415"].detail
    assert "More than 60%" in items["top_heavy_summary"].detail


def test_summary_lines_share_one_heading_edge_and_one_result_edge():
    doc = build_our_house_summary(report_percent=None)
    try:
        words = doc[0].get_text("words")
    finally:
        doc.close()
    lines: dict[int, list[tuple]] = {}
    for word in words:
        lines.setdefault(round(word[1]), []).append(word)
    heading_x: list[float] = []
    result_x: list[float] = []
    for group in lines.values():
        first = min(group, key=lambda item: item[0])
        token = first[4]
        if token in {"416", "410(b)", "Benefits,", "401(a)(4)", "414(s)", "402(g)", "415(c)", "Average"}:
            heading_x.append(first[0])
        elif token in {"Test:", "Standard:", "401(k):", "401(m):"} or (
            token == "Plan" and any(item[4] == "Heavy" for item in group)
        ):
            result_x.append(first[0])
    assert len(heading_x) >= 9
    assert len(result_x) >= 12
    assert max(heading_x) - min(heading_x) < 1.5
    assert max(result_x) - min(result_x) < 1.5
    assert max(heading_x) < min(result_x) - 40


def test_failed_410b_uses_the_average_benefits_sentence():
    coverage = [("Standard", "Fail", "57.52"), ("401(k)", "Pass", "100")]
    passed = build_our_house_summary(coverage=coverage, abpt_note=True, with_reports=True, report_percent=None)
    try:
        item = _checks(passed)["summary_410(b)"]
    finally:
        passed.close()
    assert item.passed is True
    assert "57.52%" in item.detail
    assert "Profit sharing and SHNE" in item.detail

    missing = build_our_house_summary(coverage=coverage, abpt_note=False, with_reports=True, report_percent=None)
    try:
        item = _checks(missing)["summary_410(b)"]
    finally:
        missing.close()
    assert item.passed is False
    assert "Average Benefits Test Passed; no action needed for Failed 410(b) Coverage Test" in item.detail

    wrong_ratio = build_our_house_summary(
        coverage=coverage,
        abpt_note=True,
        with_reports=False,
        report_percent=None,
        extra_report="410(b) Coverage Test\nStandard: Fail Ratio percent 40%\n401(k): Pass Ratio percent 100%",
    )
    try:
        item = _checks(wrong_ratio)["summary_410(b)"]
    finally:
        wrong_ratio.close()
    assert item.passed is False
    assert "57.52%" in item.detail
    assert "40%" in item.detail


def test_other_contributions_need_their_410b_line():
    doc = build_our_house_summary(
        coverage=[("401(k)", "Pass", "100")],
        report_percent=None,
        extra_report="410(b) Coverage Test\nProfit sharing and SHNE\nStandard: Pass Ratio percent 100%",
    )
    try:
        item = _checks(doc)["summary_410(b)"]
    finally:
        doc.close()
    assert item.passed is False
    assert "Standard is missing" in item.detail
    assert "Profit sharing and SHNE" in item.detail


def test_unresolved_pass_fail_and_report_mismatch_are_flagged():
    doc = build_our_house_summary(
        results={"402(g)": "Pass/Fail", "ADP": "Pass"},
        with_reports=False,
        report_percent=None,
        extra_report="ADP Test\nAverage Deferral Percentage\nTest: Fail",
    )
    try:
        items = _checks(doc)
    finally:
        doc.close()
    assert items["summary_402(g)"].passed is False
    assert "Pass/Fail" in items["summary_402(g)"].detail
    assert items["summary_ADP"].passed is False
    assert "fail" in items["summary_ADP"].detail


def test_brf_result_stays_on_the_summary_without_a_brf_report():
    doc = build_our_house_summary(report_percent=None, brf_report=True)
    try:
        items = _checks(doc)
    finally:
        doc.close()
    assert items["summary_brf"].passed is True
    assert items["brf_report_omitted"].passed is False

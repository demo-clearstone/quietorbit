import fitz

from models.plan_profile import PlanProfile
from services.package_builder import PARAGRAPHS, build_valuation_with_action_paragraphs
from services.pdf_modifier import apply_decisions
from services.plan_profile_service import finalize_profile
from services.rules_engine import evaluate

_HEADINGS = {
    "A": PARAGRAPHS[0][0],
    "B": PARAGRAPHS[1][0],
    "C": PARAGRAPHS[2][0],
    "D": PARAGRAPHS[3][0],
    "E": PARAGRAPHS[4][0],
    "F": PARAGRAPHS[5][0],
    "G": PARAGRAPHS[6][0],
    "M": "IMMEDIATE ACTION REQUIRED - CONTRIBUTIONS",
}


def _text(doc: fitz.Document) -> str:
    raw = "\n".join(page.get_text("text") or "" for page in doc)
    return " ".join(raw.split())


def _apply(profile: PlanProfile) -> fitz.Document:
    doc = build_valuation_with_action_paragraphs()
    apply_decisions(doc, evaluate(finalize_profile(profile)))
    return doc


def _base(**overrides) -> PlanProfile:
    values = dict(
        plan_number="800808",
        plan_name="OUR HOUSE, INC. 401(K) RETIREMENT PLAN",
        testing_method="CURRENT",
        adp_failed=False,
        acp_failed=False,
        fail_402g=False,
        fail_415=False,
        returns_required=False,
        after_12_months=False,
        top_heavy_percent=7.26,
        contributions_required=False,
        variance_report=False,
    )
    values.update(overrides)
    return PlanProfile(**values)


def test_action_pages_match_the_valuation_package_layout():
    doc = build_valuation_with_action_paragraphs()
    try:
        assert doc.page_count == 4
        report = doc[1]
        text = report.get_text("text")
        assert "Annual Valuation Report" in text
        assert "OUR HOUSE, INC. 401(K) RETIREMENT PLAN" in text
        assert "800808" in text
        assert "July 1, 2025 - June 30, 2026" in text
        assert _HEADINGS["A"] in text
        assert _HEADINGS["B"] in text
        assert "unless QNEC" in text
        assert _HEADINGS["M"] in text
        assert _HEADINGS["E"] in doc[2].get_text("text")
        assert _HEADINGS["D"] in doc[2].get_text("text")
        assert _HEADINGS["F"] in doc[3].get_text("text")
        assert "60.01%" in doc[3].get_text("text")
        assert _HEADINGS["G"] in doc[3].get_text("text")
        def content_bottom(page: fitz.Page) -> float:
            words = [word for word in page.get_text("words") if word[1] < page.rect.height - 50]
            return max(word[3] for word in words)

        assert content_bottom(report) < report.rect.height - 36
        assert content_bottom(doc[2]) < doc[2].rect.height - 36
        assert "2" == doc[1].get_text("words")[-1][4] or any(
            word[4] == "2" and word[1] > doc[1].rect.height - 50 for word in doc[1].get_text("words")
        )

        heading_x = []
        body_x = []
        red = set()
        green = set()
        for page in doc[1:]:
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines") or []:
                    for span in line.get("spans") or []:
                        token = span["text"]
                        if token in _HEADINGS.values() or token == "ACTION REQUIRED":
                            heading_x.append(span["origin"][0])
                        if token.startswith("Contribution refunds") or token.startswith("A Contribution"):
                            body_x.append(span["origin"][0])
                        color = span.get("color") or 0
                        if "COMPLIANCE TEST FAILURE" in token or token.startswith("Contribution refunds"):
                            red.add(color)
                        if token == _HEADINGS["G"]:
                            green.add(color)
        assert max(heading_x) - min(heading_x) < 1.5
        assert body_x
        assert max(body_x) - min(body_x) < 1.5
        assert min(body_x) > max(heading_x)
        assert red and all(item > 0 for item in red)
        assert green and green.isdisjoint(red)
    finally:
        doc.close()


def test_no_failure_leaves_only_the_green_line():
    doc = _apply(_base())
    try:
        text = _text(doc)
        assert _HEADINGS["G"] in text
        for code in ("A", "B", "C", "D", "E", "F", "M"):
            assert _HEADINGS[code] not in text
        assert "unless QNEC" not in text
        assert doc.page_count == 2
        heading = doc[1]
        identity = heading.get_text("text") or ""
        assert "Annual Valuation Report" in identity
        assert "OUR HOUSE, INC. 401(K) RETIREMENT PLAN" in identity
        assert "800808" in identity
        assert "ACTION REQUIRED" in identity
        assert _HEADINGS["G"] in identity
    finally:
        doc.close()


def test_402g_or_415_failure_leaves_the_compliance_paragraph():
    either = _apply(_base(fail_402g=True, fail_415=False, returns_required=True))
    try:
        text = _text(either)
        assert _HEADINGS["A"] in text
        assert "Form W-4R" in text
        assert _HEADINGS["G"] not in text
        assert _HEADINGS["B"] not in text
    finally:
        either.close()

    additions = _apply(_base(fail_415=True, fail_402g=False, returns_required=True))
    try:
        assert _HEADINGS["A"] in _text(additions)
    finally:
        additions.close()

    late = _apply(_base(fail_402g=True, fail_402g_after_deadline=True, returns_required=True))
    try:
        text = _text(late)
        assert _HEADINGS["A"] not in text
        assert _HEADINGS["G"] in text
    finally:
        late.close()


def test_adp_paragraph_follows_prior_or_current_and_returns():
    prior = _apply(_base(testing_method="PRIOR", adp_failed=True, returns_required=True))
    try:
        text = _text(prior)
        assert _HEADINGS["B"] in text
        assert "unless QNEC" not in text
        assert _HEADINGS["D"] not in text
        assert _HEADINGS["E"] not in text
    finally:
        prior.close()

    current = _apply(_base(testing_method="CURRENT", adp_failed=True, returns_required=True))
    try:
        text = _text(current)
        assert "unless QNEC contributions will be made" in text
        assert _HEADINGS["D"] not in text
        assert _HEADINGS["E"] not in text
    finally:
        current.close()

    reclassified = _apply(
        _base(testing_method="PRIOR", adp_failed=True, returns_required=True, adp_reclassified=True)
    )
    try:
        text = _text(reclassified)
        assert _HEADINGS["B"] not in text
        assert _HEADINGS["E"] not in text
        assert _HEADINGS["G"] in text
    finally:
        reclassified.close()


def test_after_12_months_leaves_the_method_paragraph():
    prior = _apply(
        _base(testing_method="PRIOR", adp_failed=True, returns_required=True, after_12_months=True)
    )
    try:
        text = _text(prior)
        assert _HEADINGS["E"] in text
        assert "one-to-one correction method" in text
        assert _HEADINGS["D"] not in text
        assert _HEADINGS["B"] in text
    finally:
        prior.close()

    current = _apply(
        _base(testing_method="CURRENT", acp_failed=True, returns_required=True, after_12_months=True)
    )
    try:
        text = _text(current)
        assert _HEADINGS["D"] in text
        assert "QNEC Correction Method" in text
        assert _HEADINGS["E"] not in text
        assert "unless QNEC" in text
    finally:
        current.close()


def test_contributions_wording_stays_for_true_up_and_top_heavy_uses_60_percent():
    contributions = _apply(_base(contributions_required=True, true_up=True))
    try:
        text = _text(contributions)
        assert _HEADINGS["M"] in text
        assert "accurate census data" in text
        assert _HEADINGS["G"] not in text
    finally:
        contributions.close()

    over = finalize_profile(_base(top_heavy_percent=60.01))
    assert over.top_heavy is True
    kept = _apply(_base(top_heavy_percent=60.01))
    try:
        text = _text(kept)
        assert _HEADINGS["F"] in text
        assert "60.01%" in text
        assert _HEADINGS["G"] not in text
    finally:
        kept.close()

    at_sixty = finalize_profile(_base(top_heavy_percent=60))
    assert at_sixty.top_heavy is False
    removed = _apply(_base(top_heavy_percent=60))
    try:
        text = _text(removed)
        assert _HEADINGS["F"] not in text
        assert _HEADINGS["G"] in text
    finally:
        removed.close()


def test_heading_only_page_is_removed_when_its_paragraphs_are_gone():
    doc = fitz.open()
    doc.new_page()
    heading = doc.new_page(width=595.28, height=841.89)
    y = 72
    for line in (
        "Annual Valuation Report",
        "July 1, 2025 - June 30, 2026",
        "OUR HOUSE, INC. 401(K) RETIREMENT PLAN",
        "800808",
        "ACTION REQUIRED",
    ):
        heading.insert_text((72, y), line, fontsize=12, fontname="hebo")
        y += 18
    extra = doc.new_page(width=595.28, height=841.89)
    extra.insert_text((54, 80), _HEADINGS["A"], fontsize=11, fontname="hebo")
    extra.insert_text((72, 100), "Contribution refunds to participants are required.", fontsize=9)
    blank = doc.new_page()
    blank.insert_text((280, blank.rect.height - 24), "4", fontsize=9)
    apply_decisions(doc, evaluate(finalize_profile(_base())))
    try:
        texts = [page.get_text("text") or "" for page in doc]
        assert doc.page_count == 1
        assert not any("Annual Valuation Report" in text for text in texts)
        assert not any("ACTION REQUIRED" in text for text in texts)
        assert all(" ".join(text.split()) != "4" for text in texts)
    finally:
        doc.close()


def test_blank_pages_are_removed_and_remaining_paragraphs_share_edges():
    doc = build_valuation_with_action_paragraphs()
    blank = doc.new_page()
    blank.insert_text((280, blank.rect.height - 24), "4", fontsize=9)
    apply_decisions(doc, evaluate(finalize_profile(_base(top_heavy_percent=70))))
    try:
        assert doc.page_count == 2
        for page in doc:
            text = " ".join((page.get_text("text") or "").split())
            assert text
            assert text != "4"
        page = doc[1]
        lines: dict[int, list[tuple]] = {}
        for word in page.get_text("words"):
            lines.setdefault(round(word[1]), []).append(word)
        heading_x: list[float] = []
        body_x: list[float] = []
        heading_y: list[float] = []
        for y, group in lines.items():
            group.sort(key=lambda item: item[0])
            token = " ".join(item[4] for item in group)
            if token.startswith("ACTION REQUIRED") or token.startswith("ATTENTION REQUIRED"):
                heading_x.append(group[0][0])
                heading_y.append(y)
            elif token.startswith("Review the") or token.startswith("Please contact") or token.startswith("Plans "):
                body_x.append(group[0][0])
        assert len(heading_x) >= 2
        assert len(body_x) >= 3
        assert max(heading_x) - min(heading_x) < 1.5
        assert max(body_x) - min(body_x) < 1.5
        assert min(body_x) > max(heading_x) + 8
        heading_y.sort()
        assert heading_y[1] - heading_y[0] < 50
        assert max(word[3] for word in page.get_text("words")) < page.rect.height - 24
    finally:
        doc.close()

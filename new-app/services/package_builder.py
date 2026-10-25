from __future__ import annotations

import re

import fitz

COVER_LINES = [
    "March 8, 2026",
    "",
    "Michigan United Credit Union",
    "RE: Michigan United Credit Union 401(k) Savings Plan",
    "",
    "We are pleased to provide you with our completed administrative review of your",
    "qualified retirement plan for the period ending 12/31/2025. This Valuation Report",
    "contains a recap of the finalized census data and results of the IRS required",
    "testing for the plan year.",
    "",
    "Plan Number: 900062",
    "",
    "Please take note of the testing results for this year and refer to the Action",
    "Required section of the Annual Valuation Report.",
]

_TAX = (
    "The distribution is subject to a 10% federal income tax, unless the participant completes a Form W-4R "
    "indicating he/she either does not want taxes withheld or wants an additional amount withheld."
)
_CONTACT = (
    "If you need assistance or have questions, please contact your local regional office representative right away."
)

PARAGRAPHS: list[tuple[str, str]] = [
    (
        "IMMEDIATE ACTION REQUIRED - COMPLIANCE TEST FAILURE",
        "Contribution refunds to participants are required to correct compliance testing failures. "
        "Review the Excess Summary report provided in this package for details and return any "
        "required documents or contact your local regional office representative.\n\n"
        "To help ensure returns are processed correctly, please also return Form W-4R documents "
        "for each affected participant.",
    ),
    (
        "IMMEDIATE ACTION REQUIRED - ADP/ACP TEST FAILURE",
        "Contribution refunds to participants are required to correct ADP/ACP testing failures. "
        "Review the ADP/ACP Correction Method summary for details.\n\n"
        + _TAX
        + "\n\n"
        + _CONTACT,
    ),
    (
        "IMMEDIATE ACTION REQUIRED - ADP/ACP TEST FAILURE",
        "Contribution refunds to participants are required to correct ADP/ACP testing failures "
        "unless QNEC contributions will be made. Review the ADP/ACP Correction Method summary "
        "provided in this package for details.\n\n"
        + _TAX
        + "\n\n"
        + _CONTACT,
    ),
    (
        "IMMEDIATE ACTION REQUIRED - ADP/ACP CURRENT METHOD TEST FAILURE - AFTER 12-MONTHS",
        "ADP/ACP corrections completed after the 12-month correction period need to be completed under one of the "
        "Internal Revenue Code EPCRS approved self-correction methods. The employer needs to use one of the "
        "following correction methods:\n\n"
        "1. QNEC Correction Method. This method allows the employer to contribute qualified nonelective contributions "
        "(QNECs) to the extent necessary to pass the applicable test. This amount can be found on the Correction Method "
        "page of the ADP/ACP Nondiscrimination Test reports.\n\n"
        "2. One-to-One Correction Method. Under this method, contribution refunds are required to correct the ADP/ACP "
        "testing failures, and the employer is required to make a QNEC contribution equal to the total amount of the "
        "corrective distributions, which is allocated to the non-highly compensated employees (NHCEs).\n\n"
        "Please review the ADP/ACP Correction Method summary and notify us of the correction method selected. "
        "Allocation breakdown based on selected correction option will be provided.\n\n"
        + _TAX
        + "\n\n"
        "If you have questions, please contact your local regional office representative right away.",
    ),
    (
        "IMMEDIATE ACTION REQUIRED - ADP/ACP PRIOR METHOD TEST FAILURE - AFTER 12-MONTHS",
        "ADP/ACP corrections completed after the 12-month correction period need to be completed using the one-to-one "
        "correction method under the Internal Revenue Code EPCRS Procedure.\n\n"
        "Contribution refunds are required to correct the ADP/ACP testing failures, and the employer is required to "
        "make a QNEC contribution equal to the total amount of the corrective distributions, which is allocated to "
        "the non-highly compensated employees (NHCEs).\n\n"
        "Review the ADP/ACP Correction Method summary for details.\n\n"
        + _TAX
        + "\n\n"
        + _CONTACT,
    ),
    (
        "ATTENTION REQUIRED - TOP HEAVY DETERMINATION",
        "Review the Compliance Testing Summary of Results page to see the top heavy percentage that will determine "
        "if a contribution is required next year.\n\n"
        "Please contact your local regional office representative for assistance in reviewing the implications of "
        "having a top heavy plan.\n\n"
        "Plans with a top heavy percent of 60.01% or greater require a top heavy allocation. The allocation is "
        "determined as the lesser of the highest allocation rate for any of the key employees OR 3%. The allocation "
        "rate is applied to total compensation for all non-key employees to arrive at the top heavy allocation. "
        "The allocation rate for key employees includes all contributions and forfeitures allocated to the key "
        "employees. If all key employees elect not to defer or defer below 3%, the top heavy allocation required "
        "will be substantially reduced.\n\n"
        "Plans using a Safe Harbor feature are normally exempt from the top heavy requirements. However, if the plan "
        "has different eligibility requirements between salary deferral contributions and the safe harbor contribution, "
        "or makes an allocation of any discretionary contribution in addition to the safe harbor contribution or "
        "forfeitures, the plan would lose its exemption from the top heavy requirements. Therefore, a minimum top "
        "heavy allocation to all non-key employees would be required. Should a plan eliminate the safe harbor feature, "
        "and remain top heavy, the minimum top heavy allocation requirement must be satisfied.",
    ),
    (
        "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME",
        "",
    ),
]


def build_valuation_with_action_paragraphs() -> fitz.Document:
    """Cover, then the Annual Valuation Report action pages from the 401(k) package.

    Purpose:
        Cover, then the Annual Valuation Report action pages from the 401(k) package. Headings stay on one line so the keep/remove search can find them.

    Args:
        None.

    Returns:
        fitz.Document.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        build_valuation_with_action_paragraphs() returns fitz.Document.

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open()
    _textbox(doc, "Cover Letter\n\n" + "\n".join(COVER_LINES))
    _action_page(
        doc,
        [
            ("red", PARAGRAPHS[0]),
            ("red", PARAGRAPHS[1]),
            ("red", PARAGRAPHS[2]),
            ("red", ("IMMEDIATE ACTION REQUIRED - CONTRIBUTIONS", CONTRIBUTIONS_BODY)),
        ],
        header=True,
        number=2,
    )
    _action_page(
        doc,
        [
            ("red", PARAGRAPHS[4]),
            ("red", PARAGRAPHS[3]),
        ],
        number=3,
    )
    _action_page(
        doc,
        [
            ("attention", PARAGRAPHS[5]),
            ("green", PARAGRAPHS[6]),
        ],
        number=4,
    )
    return doc


_RED = (0.8, 0.0, 0.0)
_GREEN = (0.0, 0.45, 0.15)
_BLACK = (0, 0, 0)
_HEADING_X = 54
_BODY_X = 72


def _action_page(
    doc: fitz.Document,
    blocks: list[tuple[str, tuple[str, str]]],
    *,
    header: bool = False,
    number: int | None = None,
) -> None:
    """One Annual Valuation Report page, laid out like package pages 2–4.

    Purpose:
        One Annual Valuation Report page, laid out like package pages 2–4.

    Args:
        doc: Open PDF. Must not be closed.
        blocks: Blocks. Type: list[tuple[str, tuple[str, str]]].
        header: Header. Type: bool.
        number: Number. Type: int | None.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _action_page(doc, [], header=True, number=1) returns None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    page = doc.new_page(width=595.28, height=841.89)
    y = 78.0
    if header:
        y = _valuation_header(page)
    for tone, (heading, body) in blocks:
        if tone == "attention":
            y = _heading_line(page, heading, y, _RED)
            for index, paragraph in enumerate(body.split("\n\n")):
                font = "hebo" if index < 2 else "helv"
                y = _body_lines(page, paragraph, y, _BLACK, font)
        else:
            color = {"red": _RED, "green": _GREEN, "black": _BLACK}[tone]
            y = _heading_line(page, heading, y, color)
            if tone == "red":
                y = _body_lines(page, body, y, _RED, "helv")
            elif tone == "black" and body:
                y = _body_lines(page, body, y, _BLACK, "helv")
        y += 10
    if number is not None:
        _page_number(page, number)


def _valuation_header(
    page: fitz.Page,
    lines: tuple[tuple[str, float, str], ...] | None = None,
    *,
    action_required: bool = True,
) -> float:
    """Valuation header.

    Purpose:
        Valuation header.

    Args:
        page: One PDF page.
        lines: Lines. Type: tuple[tuple[str, float, str], ...] | None.
        action_required: Action required. Type: bool.

    Returns:
        a float.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _valuation_header(page, 1.0, action_required=True) returns a float.

    Side effects:
        None. This function only reads data and returns a value.
    """
    y = 56.0
    rows = lines or (
        ("Annual Valuation Report", 16, "hebo"),
        ("July 1, 2025 - June 30, 2026", 11, "helv"),
        ("OUR HOUSE, INC. 401(K) RETIREMENT PLAN", 12, "hebo"),
        ("800808", 12, "hebo"),
    )
    for text, size, font in rows:
        _center(page, text, y, size, font)
        y += size + 6
    page.draw_line(fitz.Point(48, y), fitz.Point(page.rect.width - 48, y), color=_BLACK, width=1)
    y += 28
    if action_required:
        _heading_line(page, "ACTION REQUIRED", y, _BLACK)
        return y + 28
    return y


def _excess_notice_page(
    doc: fitz.Document,
    notice: str,
    identity: tuple[str, str, str],
    *,
    number: int,
) -> None:
    """Annual Valuation Report header, then the Excess Return Notice body.

    Purpose:
        Annual Valuation Report header, then the Excess Return Notice body.

    Args:
        doc: Open PDF. Must not be closed.
        notice: Notice. Type: str.
        identity: Identity. Type: tuple[str, str, str].
        number: Number. Type: int.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _excess_notice_page(doc, "text", "text", number=1) returns None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    page = doc.new_page(width=595.28, height=841.89)
    date_line, plan_name, plan_number = identity
    y = _valuation_header(
        page,
        (
            ("Annual Valuation Report", 16, "hebo"),
            (date_line, 11, "helv"),
            (plan_name, 12, "hebo"),
            (plan_number, 12, "hebo"),
        ),
        action_required=False,
    )
    y += 8
    heading = (
        "Failed Compliance Testing - After 12-months"
        if "After 12-months" in notice
        else "Failed Compliance Testing"
    )
    for title in (heading, "Excess Return Notice"):
        y = _center_underlined(page, title, y, 12)
        y += 18
    y += 6
    for paragraph in notice.split("\n\n"):
        if paragraph in {heading, "Excess Return Notice", "Failed Compliance Testing"}:
            continue
        bold = paragraph.startswith("A 10% withholding") or paragraph.startswith("Please note that the Employer")
        y = _notice_paragraph(page, paragraph, y, bold=bold)
        y += 10
    _page_number(page, number)


def _center_underlined(page: fitz.Page, text: str, y: float, size: float) -> float:
    """Center underlined.

    Purpose:
        Center underlined.

    Args:
        page: One PDF page.
        text: Text from a page or a file.
        y: Y. Type: float.
        size: Size. Type: float.

    Returns:
        a float.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _center_underlined(page, "text", 1.0) returns a float.

    Side effects:
        None. This function only reads data and returns a value.
    """
    _center(page, text, y, size, "hebo")
    width = fitz.get_text_length(text, fontname="hebo", fontsize=size)
    x = (page.rect.width - width) / 2
    page.draw_line(fitz.Point(x, y + 2), fitz.Point(x + width, y + 2), color=_BLACK, width=0.8)
    return y + size + 4


def _notice_paragraph(page: fitz.Page, text: str, y: float, *, bold: bool) -> float:
    """Notice paragraph.

    Purpose:
        Notice paragraph.

    Args:
        page: One PDF page.
        text: Text from a page or a file.
        y: Y. Type: float.
        bold: Bold. Type: bool.

    Returns:
        a float.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _notice_paragraph(page, "text", 1.0, bold=True) returns a float.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    font = "hebo" if bold else "helv"
    lead = ""
    rest = text
    if text.startswith("Current method testing:") or text.startswith("Prior method testing:"):
        lead, rest = text.split(":", 1)
        lead = lead + ":"
        rest = rest.strip()
    x = 54.0
    width = page.rect.width - 108
    if lead:
        lead_width = fitz.get_text_length(lead, fontname="helv", fontsize=10)
        page.insert_text((x, y), lead, fontsize=10, fontname="helv", color=_BLACK)
        page.draw_line(fitz.Point(x, y + 2), fitz.Point(x + lead_width, y + 2), color=_BLACK, width=0.6)
        first_width = width - lead_width - 6
        words = rest.split()
        first: list[str] = []
        while words and fitz.get_text_length(" ".join(first + [words[0]]), fontname=font, fontsize=10) <= first_width:
            first.append(words.pop(0))
        if first:
            page.insert_text((x + lead_width + 4, y), " ".join(first), fontsize=10, fontname=font, color=_BLACK)
        y += 13
        rest = " ".join(words)
    if rest:
        y = _wrapped_text(page, rest, y, x, width, font, 10)
    return y


def _wrapped_text(
    page: fitz.Page,
    text: str,
    y: float,
    x: float,
    width: float,
    font: str,
    size: float,
) -> float:
    """Wrapped text.

    Purpose:
        Wrapped text.

    Args:
        page: One PDF page.
        text: Text from a page or a file.
        y: Y. Type: float.
        x: X. Type: float.
        width: Width. Type: float.
        font: Font. Type: str.
        size: Size. Type: float.

    Returns:
        a float.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _wrapped_text(page, "text", 1.0) returns a float.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    url = "https://www.irs.gov/pub/irs-pdf/fw4r.pdf"
    for line in _wrap(text, font, size, width):
        if url in line:
            before, _, after = line.partition(url)
            page.insert_text((x, y), before, fontsize=size, fontname=font, color=_BLACK)
            url_x = x + fitz.get_text_length(before, fontname=font, fontsize=size)
            page.insert_text((url_x, y), url, fontsize=size, fontname="helv", color=(0, 0, 0.8))
            url_width = fitz.get_text_length(url, fontname="helv", fontsize=size)
            page.draw_line(fitz.Point(url_x, y + 2), fitz.Point(url_x + url_width, y + 2), color=(0, 0, 0.8), width=0.5)
            if after:
                page.insert_text((url_x + url_width, y), after, fontsize=size, fontname=font, color=_BLACK)
        else:
            page.insert_text((x, y), line, fontsize=size, fontname=font, color=_BLACK)
        y += 13
    return y


def _center(page: fitz.Page, text: str, y: float, size: float, font: str) -> None:
    """Center.

    Purpose:
        Center.

    Args:
        page: One PDF page.
        text: Text from a page or a file.
        y: Y. Type: float.
        size: Size. Type: float.
        font: Font. Type: str.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _center(page, "text", 1.0) returns None.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    width = fitz.get_text_length(text, fontname=font, fontsize=size)
    page.insert_text(((page.rect.width - width) / 2, y), text, fontsize=size, fontname=font, color=_BLACK)


def _heading_line(page: fitz.Page, text: str, y: float, color: tuple[float, float, float]) -> float:
    """Heading line.

    Purpose:
        Heading line.

    Args:
        page: One PDF page.
        text: Text from a page or a file.
        y: Y. Type: float.
        color: Color. Type: tuple[float, float, float].

    Returns:
        a float.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _heading_line(page, "text", 1.0) returns a float.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    size = 10 if len(text) > 70 else 11
    page.insert_text((_HEADING_X, y), text, fontsize=size, fontname="hebo", color=color)
    width = fitz.get_text_length(text, fontname="hebo", fontsize=size)
    page.draw_line(fitz.Point(_HEADING_X, y + 2), fitz.Point(_HEADING_X + width, y + 2), color=color, width=0.8)
    return y + size + 8


def _page_number(page: fitz.Page, number: int) -> None:
    """Page number.

    Purpose:
        Page number.

    Args:
        page: One PDF page.
        number: Number. Type: int.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _page_number(page, 1) returns None.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    label = str(number)
    size = 9
    width = fitz.get_text_length(label, fontname="helv", fontsize=size)
    page.insert_text(((page.rect.width - width) / 2, page.rect.height - 36), label, fontsize=size, fontname="helv", color=_BLACK)


def _body_lines(page: fitz.Page, text: str, y: float, color: tuple[float, float, float], font: str) -> float:
    """Body lines.

    Purpose:
        Body lines.

    Args:
        page: One PDF page.
        text: Text from a page or a file.
        y: Y. Type: float.
        color: Color. Type: tuple[float, float, float].
        font: Font. Type: str.

    Returns:
        a float.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _body_lines(page, "text", 1.0) returns a float.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    for paragraph in text.split("\n"):
        paragraph = paragraph.strip()
        if not paragraph:
            y += 4
            continue
        listed = bool(re.match(r"\d+\.", paragraph))
        x = _BODY_X + 16 if listed else _BODY_X
        width = page.rect.width - x - 54
        for line in _wrap(paragraph, font, 9, width):
            page.insert_text((x, y), line, fontsize=9, fontname=font, color=color)
            y += 12
        y += 4
    return y


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    """Wrap.

    Purpose:
        Wrap.

    Args:
        text: Text from a page or a file.
        font: Font. Type: str.
        size: Size. Type: float.
        width: Width. Type: float.

    Returns:
        a list of str.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _wrap("text", "text", 1.0) returns a list of str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    lines: list[str] = []
    current = ""
    for word in text.split():
        trial = word if not current else f"{current} {word}"
        if fitz.get_text_length(trial, fontname=font, fontsize=size) <= width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines or [""]


FAILURE_NOTICE = """Failed Compliance Testing

Excess Return Notice

Current method testing: Instead of returning excess contribution an employer may make a Qualified Non-Elective Contribution (QNEC) to Non-Highly compensated employees (NHCE's). The amount of the QNEC that is required to pass the ADP/ACP test is $X,XXX,XXX.XX. The ADP QNEC is $X,XXX,XXX.XX. The ACP QNEC is $X,XXX,XXX.XX. Please contact your local regional office representative to let them know if you choose this option for a breakdown per participant.

The corrective action necessary in the case of a failure of the ADP/ACP nondiscrimination test is to return Excess Contributions (Salary Deferral/Roth) and/or Excess Aggregate Contributions (Employer Match) to the appropriate Highly Compensated Employees. The actual amounts refunded have been adjusted to include any positive or negative earnings that are attributable to this excess contribution.

A 10% withholding tax will apply unless we receive a Form W-4R informing us that you either do not want any tax withheld or want an additional amount of tax withheld. You can obtain a copy of the W-4R at https://www.irs.gov/pub/irs-pdf/fw4r.pdf.

Please note that the Employer is subject to a 10% excise tax on returns made after September 14, 2026. If your plan is an Eligible Automatic Contribution Arrangement (EACA), the 10% excise tax applies to returns made after December 30, 2026.
"""


def build_adp_acp_failure_notice_pdf(
    *,
    method: str = "CURRENT",
    adp: str = "Fail",
    acp: str = "Fail",
    returns: str = "Returns Required",
    adp_qnec: str | None = "142,540.41",
    acp_qnec: str | None = "42,814.34",
    include_notice: bool = True,
    notice: str | None = None,
    correction_note: str | None = None,
) -> fitz.Document:
    """TEST23 §C: cover + correction page + Excess Return Notice placeholders.

    Purpose:
        TEST23 §C: cover + correction page + Excess Return Notice placeholders.

    Args:
        method: Method. Type: str.
        adp: Adp. Type: str.
        acp: Acp. Type: str.
        returns: Returns. Type: str.
        adp_qnec: Adp qnec. Type: str | None.
        acp_qnec: Acp qnec. Type: str | None.
        include_notice: Include notice. Type: bool.
        notice: Notice. Type: str | None.
        correction_note: Correction note. Type: str | None.

    Returns:
        a fitz.Document.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        build_adp_acp_failure_notice_pdf(method="text", adp="text", acp="text", returns="text") returns a fitz.Document.

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open()
    cover = [
        "Cover Letter",
        "Plan Number: 444444",
        "Plan Name: Harbor Manufacturing 401(k) Plan",
        "Company Name: Harbor Manufacturing",
        "Address: 10 Harbor Way, Boston, MA 02110",
        "Plan Year: 01/01/2024 - 12/31/2024",
        f"Testing Method: {method}",
        f"ADP Test: {adp}",
        f"ACP Test: {acp}",
        returns,
        "Correction Within 12 Months",
    ]
    _textbox(doc, "\n".join(cover))
    correction = [
        "ADP/ACP",
        "Correction Page",
        "Plan Number: 444444",
        "Plan Name: Harbor Manufacturing 401(k) Plan",
        "Plan Year End: 12/31/2024",
        f"Testing Method: {method}",
        f"ADP Test: {adp}",
        f"ACP Test: {acp}",
        "This plan passes using the refund amount corrections.",
    ]
    if adp_qnec is not None and acp_qnec is not None:
        correction.append(
            "This plan will also qualify with the following ADP QNEC/ACP QNEC contributions to NHCEs."
        )
        correction.append(f"ADP QNEC ${adp_qnec}")
        correction.append(f"ACP QNEC ${acp_qnec}")
    elif adp_qnec is not None:
        correction.append(
            f"This plan will also qualify with a ${adp_qnec} QNEC contribution to the NHCEs for the ADP test."
        )
    elif acp_qnec is not None:
        correction.append(
            f"This plan will also qualify with a ${acp_qnec} QNEC contribution to the NHCEs for the ACP test."
        )
    if correction_note:
        correction.append(correction_note)
    _textbox(doc, "\n".join(correction))
    if include_notice:
        if notice is None:
            _excess_notice_page(
                doc,
                FAILURE_NOTICE,
                (
                    "January 1, 2024 - December 31, 2024",
                    "HARBOR MANUFACTURING 401(K) PLAN",
                    "444444",
                ),
                number=7,
            )
        else:
            _textbox(doc, notice)
    return doc


def build_current_failure_notice_sample() -> fitz.Document:
    """Within-12-month current-year Excess Return Notice, laid out like package page 7.

    Purpose:
        Within-12-month current-year Excess Return Notice, laid out like package page 7.

    Args:
        None.

    Returns:
        fitz.Document.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        build_current_failure_notice_sample() returns fitz.Document.

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open()
    _excess_notice_page(
        doc,
        FAILURE_NOTICE,
        (
            "July 1, 2025 - June 30, 2026",
            "OUR HOUSE, INC. 401(K) RETIREMENT PLAN",
            "800808",
        ),
        number=7,
    )
    return doc


_AFTER_12_FAILURE = (
    "The ADP/ACP test failure was not corrected within the applicable correction period "
    "and must be corrected under EPCRS procedures."
)
_QNEC_CHOICE = (
    "The Plan Sponsor may elect to correct the failure by making a Qualified Non Elective Contribution (QNEC) "
    "to Non Highly compensated Employees (NHCEs). The amount of the QNEC that is required to pass the ADP/ACP "
    "test is $X,XXX,XXX.XX. The ADP QNEC is $X,XXX,XXX.XX. The ACP QNEC is $X,XXX,XXX.XX. Please contact your "
    "local regional office representative if you elect this correction method. A Detailed Participant level "
    "allocation breakdown can be provided upon request."
)
_ONE_TO_ONE = (
    "Alternatively, the Plan Sponsor may elect the One-to-One Correction Method, under Excess Aggregated "
    "Deferral Contribution of $X,XXX,XXX.XX and Match contribution of $X,XXX,XXX.XX were returned to the "
    "applicable Highly compensated Employees and an equal amount is contributed as a QNEC to eligible NHCEs. "
    "Please contact your local regional office representative if you elect this correction method. A Detailed "
    "Participant level allocation breakdown can be provided upon request."
)
_PRIOR_ONE_TO_ONE = _ONE_TO_ONE.replace("Alternatively, the Plan Sponsor may elect", "The Plan Sponsor may elect")
_EPCRS_ACTION = (
    "The corrective action necessary in the case of a failure of the ADP/ACP nondiscrimination test is to "
    "complete an approved EPCRS correction method. Additional employer contributions may require depending on "
    "the correction method selected. If you need assistance or have questions regarding the available correction "
    "methods, please contact your local regional office representative."
)
_W4R = (
    "A 10% withholding tax will apply unless we receive a Form W-4R informing us that you either do not want "
    "any tax withheld or want an additional amount of tax withheld. You can obtain a copy of the W-4R at "
    "https://www.irs.gov/pub/irs-pdf/fw4r.pdf."
)

AFTER_12_CURRENT_NOTICE = "\n\n".join(
    [
        "Failed Compliance Testing - After 12-months",
        "Excess Return Notice",
        f"Current method testing: {_AFTER_12_FAILURE}",
        _QNEC_CHOICE,
        _ONE_TO_ONE,
        _EPCRS_ACTION,
        _W4R,
    ]
)

AFTER_12_PRIOR_NOTICE = "\n\n".join(
    [
        "Failed Compliance Testing - After 12-months",
        "Excess Return Notice",
        f"Prior method testing: {_AFTER_12_FAILURE}",
        _PRIOR_ONE_TO_ONE,
        _EPCRS_ACTION,
        _W4R,
    ]
)


def build_after_12_failure_notice_pdf(
    *,
    method: str = "CURRENT",
    adp: str = "Fail",
    acp: str = "Fail",
    returns: str = "Returns Required",
    adp_qnec: str | None = "142,540.41",
    acp_qnec: str | None = "42,814.34",
    deferral: str | None = "17,571.00",
    match: str | None = "116.60",
    include_current_notice: bool = True,
    include_prior_notice: bool = True,
) -> fitz.Document:
    """TEST23 §C.2 / C.3: after-12-months Excess Return Notices plus correction page.

    Purpose:
        TEST23 §C.2 / C.3: after-12-months Excess Return Notices plus correction page.

    Args:
        method: Method. Type: str.
        adp: Adp. Type: str.
        acp: Acp. Type: str.
        returns: Returns. Type: str.
        adp_qnec: Adp qnec. Type: str | None.
        acp_qnec: Acp qnec. Type: str | None.
        deferral: Deferral. Type: str | None.
        match: Match. Type: str | None.
        include_current_notice: Include current notice. Type: bool.
        include_prior_notice: Include prior notice. Type: bool.

    Returns:
        a fitz.Document.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        build_after_12_failure_notice_pdf(method="text", adp="text", acp="text", returns="text") returns a fitz.Document.

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open()
    cover = [
        "Cover Letter",
        "Plan Number: 555555",
        "Plan Name: Harbor Manufacturing 401(k) Plan",
        "Company Name: Harbor Manufacturing",
        "Address: 10 Harbor Way, Boston, MA 02110",
        "Plan Year: 01/01/2024 - 12/31/2024",
        f"Testing Method: {method}",
        f"ADP Test: {adp}",
        f"ACP Test: {acp}",
        returns,
        "After 12 Months",
    ]
    _textbox(doc, "\n".join(cover))
    correction = [
        "ADP/ACP",
        "Correction Page",
        "Plan Number: 555555",
        "Plan Name: Harbor Manufacturing 401(k) Plan",
        "Plan Year End: 12/31/2024",
        f"Testing Method: {method}",
        f"ADP Test: {adp}",
        f"ACP Test: {acp}",
        "After 12 Months",
    ]
    if adp_qnec is not None:
        correction.append(f"ADP QNEC: ${adp_qnec}")
    if acp_qnec is not None:
        correction.append(f"ACP QNEC: ${acp_qnec}")
    if deferral is not None:
        correction.append(f"Deferral Refund: ${deferral}")
    if match is not None:
        correction.append(f"Match Refund: ${match}")
    _textbox(doc, "\n".join(correction))
    identity = (
        "January 1, 2024 - December 31, 2024",
        "HARBOR MANUFACTURING 401(K) PLAN",
        "555555",
    )
    if include_current_notice:
        _excess_notice_page(doc, AFTER_12_CURRENT_NOTICE, identity, number=5)
    if include_prior_notice:
        _excess_notice_page(doc, AFTER_12_PRIOR_NOTICE, identity, number=6)
    return doc


def build_package_excess_notices() -> fitz.Document:
    """Current and prior Excess Return Notices, laid out like package pages 5 and 6.

    Purpose:
        Current and prior Excess Return Notices, laid out like package pages 5 and 6.

    Args:
        None.

    Returns:
        fitz.Document.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        build_package_excess_notices() returns fitz.Document.

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open()
    identity = (
        "July 1, 2025 - June 30, 2026",
        "OUR HOUSE, INC. 401(K) RETIREMENT PLAN",
        "800808",
    )
    _excess_notice_page(doc, AFTER_12_CURRENT_NOTICE, identity, number=5)
    _excess_notice_page(doc, AFTER_12_PRIOR_NOTICE, identity, number=6)
    return doc


VARIANCE_PARAGRAPH = (
    "IMMEDIATE ACTION REQUIRED - VARIANCE\n\n"
    "Please review the contribution variance included in this package and confirm the amounts "
    "before finalizing the Annual Valuation Report."
)

CONTRIBUTIONS_BODY = (
    "A Contribution and/or adjustment is required. Please review the testing results, and "
    "contribution calculations to ensure they are based on accurate census data.\n\n"
    "If you need assistance or have questions, please contact your local regional office representative."
)

CONTRIBUTIONS_PARAGRAPH = "IMMEDIATE ACTION REQUIRED - CONTRIBUTIONS\n\n" + CONTRIBUTIONS_BODY

EXCESS_SUMMARY = (
    "Excess Summary Report\n\n"
    "This report lists excess amounts for affected participants who are not ADP/ACP-only, "
    "unless the ADP/ACP failure is for a partially vested participant."
)

RECAP_BULLETS = [
    "Your plan is not subject to ADP/ACP Nondiscrimination Testing as the plan did not have any Highly Compensated Employees for the plan year ending June 30, 2026. For the plan year beginning July 1, 2026 no employee will be considered highly compensated.",
    "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed on the Future HCE Determination Report are considered highly compensated for the Plan Year beginning in 2026. The maximum average deferral rate for the Highly Compensated Employee(s) for the 2026 plan year is % based on the average deferral rate for your Nonhighly Compensated Employees (NHCE) for 2025 of %. This rate is determined using the \"prior year data\" method. Please communicate the maximum deferral percentage to affected employees. Note: the actual amount an employee can defer in 2026 is the lesser of the average deferral rate listed, $24,500 or the annual addition limit (adjusted for \"catch-up\" contributions, if applicable).",
    "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed on the Future HCE Determination Report are considered highly compensated for the Plan Year beginning in 2026. The maximum average deferral rate for the Highly Compensated Employee(s) for the 2026 plan year is based on the average deferral rate for your Nonhighly Compensated Employees for 2026. Note: In addition, the actual amount the employee can defer in 2026 cannot exceed $24,500 or the annual addition limit (adjusted for \"catch-up\" contributions, if applicable).",
    "Based on the definition of Highly Compensated Employee (HCE), the employee(s) listed on the Future HCE Determination Report are considered highly compensated for the Plan Year beginning in 2026. The maximum average deferral rate for the Highly Compensated Employee(s) for the 2026 plan year is not limited as long as the plan follows the rules and regulations of the Safe Harbor Plan. Note: The actual amount an employee can defer in 2026 is the lesser of $24,500 or the annual addition limit (adjusted for \"catch-up\" contributions, if applicable).",
    "Based on the definition of Highly Compensated Employee (HCE), the plan had Highly Compensated Employees for the plan year ending June 30, 2026, however, no employee will be considered highly compensated for the plan year beginning July 1, 2026. Please communicate to affected employees.",
    "Your plan is designed to allow participants who were age 50 or older to make \"catch-up\" contributions. The 2025 limit was an amount up to $7,500. Please see the appropriate compliance test for any participants who took advantage of this provision during the plan year. For 2026, the \"catch-up\" contribution is an amount up to $8,000 for any participant who is or will be 50 or older at any time during the plan year. A plan may allow for higher catch-up contributions for participants age 60-63. For 2026, the catch-up limit for these participants is $11,250.",
    "Based on the top heavy testing results for the 2026 plan year, your plan will be considered top heavy for the 2027 plan year. Plans that are top heavy may require additional contributions to non-key employees if key employees make elective deferrals or receive allocations of employer contributions. The minimum allocation amount is determined as the lesser of the highest allocation rate for any of the key employees OR 3%. If the key employees receive a contribution (deferral, match or Employer) of less than 3%, your top-heavy allocation requirement will be substantially reduced. A plan using a safe harbor contribution feature is exempt from the top heavy requirements. If the plan's eligibility requirements differ between salary deferral contributions and the safe harbor contribution, a minimum top-heavy allocation to all non-key employees will be required for the plan year. In addition, an additional allocation of any discretionary contribution on top of the safe harbor contribution or allocation of forfeitures would cause the plan to lose its exemption from the top heavy requirements. For a complete explanation of the top heavy rules please contact your local regional office representative.",
    "If you sponsor a qualified retirement plan not administered by Mutual of America, please provide your service provider with a copy of this Valuation Report to complete the combined plan testing. Upon request, we can perform the combined plan testing. Please contact your local regional office representative to discuss.",
    "The plan's employer match contribution is calculated on a participant's compensation earned for each payroll period. We recommend reviewing your payroll records to determine if the plan's match formula was applied correctly to each payroll period. We also recommend reviewing your match contributions to ensure that employees did not receive a match contribution in excess of the contribution limit based on the annual compensation limit. Work with your local regional office representative if adjustments to the employer match contribution are required.",
]

RECAP_HEADER = [
    "YEAR END RECAP",
    "July 1, 2025 - June 30, 2026",
    "OUR HOUSE, INC. 401(K) RETIREMENT PLAN",
    "800808",
    "Important Information",
]


def build_remaining_sop_pdf(
    *,
    method: str = "CURRENT",
    adp: str = "Pass",
    acp: str = "Pass",
    g402: str = "Fail",
    s415: str = "Pass",
    returns: str = "Returns Required",
    variance: str = "Variance Report",
    contributions: str = "Contributions Required",
    hce_current: str = "Yes",
    hce_future: str = "Yes",
    safe_harbor: str = "No",
    catchup_allowed: str = "Yes",
    per_payroll: str = "Yes",
    top_heavy: str = "No",
    partially_vested: bool = False,
    include_ssn: bool = False,
) -> fitz.Document:
    """TEST23 remaining items: variance, contributions, excess summary, recap, optional SSN.

    Purpose:
        TEST23 remaining items: variance, contributions, excess summary, recap, optional SSN.

    Args:
        method: Method. Type: str.
        adp: Adp. Type: str.
        acp: Acp. Type: str.
        g402: G402. Type: str.
        s415: S415. Type: str.
        returns: Returns. Type: str.
        variance: Variance. Type: str.
        contributions: Contributions. Type: str.
        hce_current: Hce current. Type: str.
        hce_future: Hce future. Type: str.
        safe_harbor: Safe harbor. Type: str.
        catchup_allowed: Catchup allowed. Type: str.
        per_payroll: Per payroll. Type: str.
        top_heavy: Top heavy. Type: str.
        partially_vested: Partially vested. Type: bool.
        include_ssn: Include ssn. Type: bool.

    Returns:
        a fitz.Document.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        build_remaining_sop_pdf(method="text", adp="text", acp="text", g402="text") returns a fitz.Document.

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open()
    cover = [
        "Cover Letter",
        "Plan Number: 777777",
        "Plan Name: Harbor Manufacturing 401(k) Plan",
        "Company Name: Harbor Manufacturing",
        "Address: 10 Harbor Way, Boston, MA 02110",
        "Plan Year: 01/01/2024 - 12/31/2024",
        f"Testing Method: {method}",
        f"ADP Test: {adp}",
        f"ACP Test: {acp}",
        f"402(g) Test: {g402}",
        f"415 Test: {s415}",
        returns,
        variance,
        contributions,
        f"HCE Current Year: {hce_current}",
        f"HCE Future year: {hce_future}",
        f"Safe Harbor: {safe_harbor}",
        f"Catch-up allowed: {catchup_allowed}",
        f"Per Payroll Match: {per_payroll}",
        "Correction Within 12 Months",
    ]
    if top_heavy == "Yes":
        cover.append("Top Heavy Percent: 62.45%")
        cover.append("Plan is top heavy")
    else:
        cover.append("Top Heavy Percent: 8.85%")
        cover.append("Plan is not Top Heavy")
    if partially_vested:
        cover.append("Partially vested participant")
    _textbox(doc, "\n".join(cover))
    _textbox(doc, VARIANCE_PARAGRAPH)
    _textbox(doc, CONTRIBUTIONS_PARAGRAPH)
    _textbox(doc, EXCESS_SUMMARY)
    page = doc.new_page(width=595.28, height=841.89)
    write_recap_page(page, ["Important Information"], RECAP_BULLETS)
    census = ["Census", "EMPLOYEE CENSUS", "Participant listing for the plan year."]
    if include_ssn:
        census.append("SSN 123-45-6789")
    _textbox(doc, "\n".join(census))
    return doc


def build_year_end_recap_sample() -> fitz.Document:
    """Important Information page, laid out like package page 12.

    Purpose:
        Important Information page, laid out like package page 12.

    Args:
        None.

    Returns:
        fitz.Document.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        build_year_end_recap_sample() returns fitz.Document.

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open()
    page = doc.new_page(width=595.28, height=841.89)
    write_recap_page(page, RECAP_HEADER, RECAP_BULLETS, number=12)
    return doc


def write_recap_page(
    page: fitz.Page,
    header_lines: list[str],
    bullets: list[str],
    *,
    number: int | None = None,
) -> None:
    """Draw the Year End Recap. Header lines stay centered; bullets pack underneath.

    Purpose:
        Draw the Year End Recap. Header lines stay centered; bullets pack underneath.

    Args:
        page: One PDF page.
        header_lines: Header lines. Type: list[str].
        bullets: Bullets. Type: list[str].
        number: Number. Type: int | None.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        write_recap_page(page, [], [], number=1) returns None.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    y = 48.0
    for raw in header_lines:
        line = raw.strip()
        if not line:
            y += 6
            continue
        if line.upper() == "YEAR END RECAP":
            _center(page, "YEAR END RECAP", y, 13, "hebo")
            y += 18
            continue
        if line.lower() == "important information":
            y += 6
            page.insert_text((54, y), "Important Information", fontsize=11, fontname="hebo", color=_BLACK)
            width = fitz.get_text_length("Important Information", fontname="hebo", fontsize=11)
            page.draw_line(fitz.Point(54, y + 2), fitz.Point(54 + width, y + 2), color=_BLACK, width=0.7)
            y += 18
            continue
        font = "hebo" if line.replace(",", "").replace(".", "").isupper() else "helv"
        size = 11 if font == "hebo" else 10
        _center(page, line, y, size, font)
        y += size + 3
        if re.fullmatch(r"\d{5,7}", line):
            y += 3
            page.draw_line(fitz.Point(54, y), fitz.Point(page.rect.width - 54, y), color=_BLACK, width=0.8)
            y += 8
    size = 8.0
    leading = 10.0
    text_x = 68.0
    width = page.rect.width - text_x - 36
    for bullet in bullets:
        body = re.sub(r"^[\u2022•\-\*]\s*", "", bullet).strip()
        if not body:
            continue
        lines = _wrap(body, "helv", size, width)
        for index, wrapped in enumerate(lines):
            if index == 0:
                page.insert_text((50, y), "•  " + wrapped, fontsize=size, fontname="helv", color=_BLACK)
            else:
                page.insert_text((text_x, y), wrapped, fontsize=size, fontname="helv", color=_BLACK)
            y += leading
        y += 6
    if number is not None:
        _page_number(page, number)


_OVERVIEW_PAGE_1 = [
    (
        "NONDISCRIMINATION IN AMOUNTS TESTS (ADP/ACP)",
        "The Average Deferral Percentage (ADP) test determines if there is discrimination between the salary deferral contributions of the Highly Compensated Employees and the Nonhighly Compensated Employees. The Actual Contribution Percentage (ACP) test determines if there is discrimination when employer matching contributions and/or employee voluntary after-tax contributions are made for both the Highly and the Nonhighly Compensated employees.",
    ),
    (
        "EXCESS DEFERRAL CONTRIBUTIONS",
        "The Code Section 402(g) maximum employee deferral contribution for the 2025 calendar year was $23,500. This limit is $24,500 for the 2026 calendar year. Please monitor employee deferrals during the payroll process to make sure that no participant exceeds this limit. Any excess deferred contribution plus credited investment earnings must be refunded by the April 15th following the calendar year in which the excess occurred. Failure to do so could adversely affect the tax status of your plan. If an employee has participated in your plan and the 401(k) plan of an unrelated employer during the calendar year, then the employee is responsible for notifying one of the plans of any 402(g) excess before March 1st following the calendar year in which the excess occurred.\n\nIf your plan is designed to allow for catch-up contributions, they are not taken into account for this limitation. The catch-up contribution for 2025 was $7,500. The catch-up contribution is $8,000 for 2026. Any participant who turns 50 or is over 50 years of age during the plan year can take advantage of this provision.\n\nA plan may allow for higher catch-up contributions for participants age 60-63. For 2026, the catch-up limit for these participants is $11,250.",
    ),
    (
        "ANNUAL ADDITION LIMITATION (415 CONTRIBUTION LIMIT)",
        "The Annual Addition Limitation is the lesser of $72,000 or 100% of Section 415 Compensation. The employee and employer contributions and any forfeitures to be reallocated to a participant for a plan year ending 2026 cannot exceed the lesser of $72,000 or 100% of Section 415 Compensation. Section 415 Compensation is defined as total compensation earned. Section 401(k) salary deferrals, flexible spending account contributions and pre-tax insurance premiums are not deducted from the participant's compensation to perform this test. If you sponsor more than one qualified defined contribution plan, the combined contributions from all plans must be considered when testing the Annual Addition Limitation for each participant. All plans sponsored by you or administered by Mutual of America are included in the testing. (If your plan is designed to allow for catch-up contributions, they are not taken into account for this limitation.)",
    ),
    (
        "COMPENSATION LIMITATION",
        "For purposes of allocating contributions and forfeitures and for discrimination testing, the Internal Revenue Service has issued compensation limits. For plan years beginning in 2025 the compensation limit per participant is $350,000. This limit is $360,000 for the 2026 plan year.",
    ),
    (
        "TOP HEAVY TEST",
        "The top heavy test compares the plan assets of all qualified plans sponsored by the employer that benefit the key employees to the total plan assets of the same plans. Generally, a plan is top heavy when more than 60% of the plan's assets benefit the key employees. If your plan is top heavy, you may be required to make a minimum contribution for all eligible non-key employees who were employed on the last day of the plan year. Also, if your plan is top heavy you will be required to use the top heavy vesting schedule selected in your plan adoption agreement.",
    ),
]

_OVERVIEW_PAGE_2 = [
    (
        "410(b) COVERAGE TEST",
        "A retirement plan, as a condition of qualification must satisfy coverage rules. The plan in general must benefit at least 70% of the includible Nonhighly Compensated Employees. Each contribution source (employee deferrals, employer match, and employer discretionary, money purchase contribution) must be tested separately. Corrections are required for each source that does not pass the 70% benefit test.",
    ),
    (
        "COMPENSATION TESTING (414(s))",
        "A plan that utilizes a definition of compensation that does not automatically satisfy IRC Section 414(s) is required to test the compensation definition to show that it does not discriminate in favor of the highly compensated employees. Plans with Highly Compensated Employees that exclude bonuses, overtime, and/or commissions from their definition of compensation are required to pass this test. Additional exclusions can also result in the need to perform this test.",
    ),
    (
        "BENEFITS, RIGHTS AND FEATURE TESTING (401(a)(4))",
        "Plans that provide benefits or features of different levels or types, for different groups of employees are required to show that each Benefit, Right and Feature (BRF) is available to all employees on a nondiscriminatory basis. Each BRF must satisfy two nondiscrimination requirements. The first requirement is the Current Availability Test and the Nondiscriminatory Classification Test. These tests pass if they do not favor the Highly Compensated Employees. The second requirement is for Effective Availability. This is an anti-abuse provision that requires that the group of employees to whom a BRF is effectively available must not substantially favor Highly Compensated Employees. If your plan requires this type of testing, additional information will be provided.",
    ),
]

_OVERVIEW_PAGE_3 = [
    (
        "HCE/KEY EMPLOYEE DETERMINATIONS",
        "This report lists the employees, if any, classified as Highly Compensated Employees (HCE) or Key for this plan year and the prior year.",
    ),
    (
        "EMPLOYEE CENSUS REPORT",
        "This report lists all employees, including those terminated with account balances as of the last day of the plan year, reported to Mutual of America. The report includes date of birth, date of hire, date of entry, compensation, hours worked and plan status for each employee listed.",
    ),
    (
        "CONTRIBUTION ANALYSIS",
        "A summary of total contributions allocated to each employee by contribution source for the plan year. The report includes all deposits received and any receivable contributions for the plan year. Forfeitures to be reallocated for the plan year are shown for each employee entitled to the allocation. Forfeitures used to reduce contributions are not reflected on this report.",
    ),
]


def build_compliance_overview_sample() -> fitz.Document:
    """The three overview pages, laid out like package pages 13, 14, and 15.

    Purpose:
        The three overview pages, laid out like package pages 13, 14, and 15.

    Args:
        None.

    Returns:
        fitz.Document.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        build_compliance_overview_sample() returns fitz.Document.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return build_compliance_overview(
        [
            "COMPLIANCE AND ADMINISTRATIVE REPORTS",
            "OVERVIEW AND DESCRIPTIONS",
            "July 1, 2025 - June 30, 2026",
            "OUR HOUSE, INC. 401(K) RETIREMENT PLAN",
            "800808",
        ]
    )


def build_compliance_overview(header: list[str] | None = None) -> fitz.Document:
    """Build compliance overview.

    Purpose:
        Build compliance overview.

    Args:
        header: Header. Type: list[str] | None.

    Returns:
        a fitz.Document.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        build_compliance_overview([]) returns a fitz.Document.

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open()
    page = doc.new_page(width=595.28, height=841.89)
    _overview_page(page, _OVERVIEW_PAGE_1, header=header, center_title="Compliance Reports", number=13)
    page = doc.new_page(width=595.28, height=841.89)
    _overview_page(page, _OVERVIEW_PAGE_2, number=14)
    page = doc.new_page(width=595.28, height=841.89)
    _overview_page(page, _OVERVIEW_PAGE_3, center_title="Administrative Reports", number=15)
    return doc


def overview_header_for(
    plan_name: str | None,
    plan_number: str | None,
    plan_year_start: str | None,
    plan_year_end: str | None,
) -> list[str]:
    """Overview header for.

    Purpose:
        Overview header for.

    Args:
        plan_name: Plan name. Type: str | None.
        plan_number: Plan number. Type: str | None.
        plan_year_start: Plan year start. Type: str | None.
        plan_year_end: Plan year end. Type: str | None.

    Returns:
        a list of str.

    Raises:
        None.

    Example:
        overview_header_for("text", "text", "text") returns a list of str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    start = _long_mdy(plan_year_start)
    end = _long_mdy(plan_year_end)
    if start and end:
        year_line = f"{start} - {end}"
    else:
        year_line = "July 1, 2025 - June 30, 2026"
    name = (plan_name or "OUR HOUSE, INC. 401(K) RETIREMENT PLAN").upper()
    number = plan_number or "800808"
    return [
        "COMPLIANCE AND ADMINISTRATIVE REPORTS",
        "OVERVIEW AND DESCRIPTIONS",
        year_line,
        name,
        number,
    ]


def ensure_compliance_overview(
    doc: fitz.Document,
    *,
    plan_name: str | None = None,
    plan_number: str | None = None,
    plan_year_start: str | None = None,
    plan_year_end: str | None = None,
) -> list[str]:
    """Every 401(k) and 403(b) package includes the three overview pages.

    Purpose:
        Every 401(k) and 403(b) package includes the three overview pages.

    Args:
        doc: Open PDF. Must not be closed.
        plan_name: Plan name. Type: str | None.
        plan_number: Plan number. Type: str | None.
        plan_year_start: Plan year start. Type: str | None.
        plan_year_end: Plan year end. Type: str | None.

    Returns:
        a list of str.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        ensure_compliance_overview(doc, plan_name="text", plan_number="text", plan_year_start="text", plan_year_end="text") returns a list of str.

    Side effects:
        Changes the PDF or the object passed in.
    """
    kinds = {_overview_kind(page.get_text("text") or "") for page in doc}
    if {"intro", "tests", "admin"} <= kinds:
        return []
    header = overview_header_for(plan_name, plan_number, plan_year_start, plan_year_end)
    source = fitz.open()
    if "intro" not in kinds:
        _overview_page(
            source.new_page(width=595.28, height=841.89),
            _OVERVIEW_PAGE_1,
            header=header,
            center_title="Compliance Reports",
            number=13,
        )
    if "tests" not in kinds:
        _overview_page(source.new_page(width=595.28, height=841.89), _OVERVIEW_PAGE_2, number=14)
    if "admin" not in kinds:
        _overview_page(
            source.new_page(width=595.28, height=841.89),
            _OVERVIEW_PAGE_3,
            center_title="Administrative Reports",
            number=15,
        )
    if source.page_count == 0:
        source.close()
        return []
    at = _overview_insert_at(doc)
    doc.insert_pdf(source, start_at=at)
    added = source.page_count
    source.close()
    return [f"Added {added} Compliance and Administrative Reports page(s)."]


def _overview_kind(text: str) -> str | None:
    """Overview kind.

    Purpose:
        Overview kind.

    Args:
        text: Text taken from a page or a file.

    Returns:
        str | None.

    Raises:
        None.

    Example:
        _overview_kind("text") returns str | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if re.search(r"compliance and administrative|overview and descriptions", text or "", re.I):
        return "intro"
    if (
        re.search(r"410\s*\(\s*b\s*\)\s+coverage", text or "", re.I)
        and re.search(r"compensation testing\s*\(\s*414", text or "", re.I)
    ):
        return "tests"
    if re.search(r"administrative reports", text or "", re.I) and re.search(
        r"hce/key employee determinations", text or "", re.I
    ):
        return "admin"
    return None


def _overview_insert_at(doc: fitz.Document) -> int:
    """Overview insert at.

    Purpose:
        Overview insert at.

    Args:
        doc: Open PDF. Must not be closed.

    Returns:
        int.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _overview_insert_at(doc) returns int.

    Side effects:
        None. This function only reads data and returns a value.
    """
    recap = None
    for index, page in enumerate(doc):
        text = page.get_text("text") or ""
        if re.search(r"year[- ]end recap|important information", text, re.I):
            recap = index
    if recap is not None:
        return recap + 1
    return doc.page_count


def _long_mdy(value: str | None) -> str | None:
    """Long mdy.

    Purpose:
        Long mdy.

    Args:
        value: Value. Type: str | None.

    Returns:
        a str | None.

    Raises:
        None.

    Example:
        _long_mdy("text") returns a str | None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    match = re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})", value or "")
    if not match:
        return None
    month = int(match.group(1))
    if month < 1 or month > 12:
        return None
    names = (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    )
    return f"{names[month - 1]} {int(match.group(2))}, {match.group(3)}"


def _overview_page(
    page: fitz.Page,
    sections: list[tuple[str, str]],
    *,
    header: list[str] | None = None,
    center_title: str | None = None,
    number: int | None = None,
) -> None:
    """Overview page.

    Purpose:
        Overview page.

    Args:
        page: One PDF page.
        sections: Sections. Type: list[tuple[str, str]].
        header: Header. Type: list[str] | None.
        center_title: Center title. Type: str | None.
        number: Number. Type: int | None.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _overview_page(page, [], header=[], center_title="text", number=1) returns None.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    y = 48.0
    for line in header or []:
        text = line.strip()
        if not text:
            continue
        font = "hebo" if text.replace(",", "").replace(".", "").replace("(", "").replace(")", "").isupper() else "helv"
        size = 12 if text.startswith("COMPLIANCE") or text.startswith("OVERVIEW") else 11
        _center(page, text, y, size, font)
        y += size + 3
        if re.fullmatch(r"\d{5,7}", text):
            y += 2
            page.draw_line(fitz.Point(54, y), fitz.Point(page.rect.width - 54, y), color=_BLACK, width=0.8)
            y += 16
    if center_title:
        _center(page, center_title, y, 12, "hebo")
        y += 22
    for title, body in sections:
        page.insert_text((54, y), title, fontsize=9, fontname="hebo", color=_BLACK)
        width = fitz.get_text_length(title, fontname="hebo", fontsize=9)
        page.draw_line(fitz.Point(54, y + 2), fitz.Point(54 + width, y + 2), color=_BLACK, width=0.6)
        y += 14
        for paragraph in body.split("\n\n"):
            y = _wrapped_text(page, paragraph, y, 54, page.rect.width - 108, "helv", 8)
            y += 8
        y += 4
    if number is not None:
        _page_number(page, number)


def _textbox(doc: fitz.Document, text: str, fontsize: int = 11) -> None:
    """Textbox.

    Purpose:
        Textbox.

    Args:
        doc: Open PDF. Must not be closed.
        text: Text from a page or a file.
        fontsize: Fontsize. Type: int.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _textbox(doc, "text", 1) returns None.

    Side effects:
        Changes the PDF passed in. Does not save the file by itself.
    """
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(54, 54, 558, 738), text, fontsize=fontsize, fontname="helv")


NOTICE_415 = """Annual Additions (IRC 415) Test Failure Information
July 1, 2025 - June 30, 2026
OUR HOUSE, INC. 401(K) RETIREMENT PLAN
800808

The Annual Additions (IRC 415) limit for the plan year ending 2026 is the lesser of $72,000 or 100% of a participant's compensation for the year.

Sources of money included within the Annual Additions (IRC 415) limit are:
• employer contributions
• employee deferral contributions (i.e. pre-tax employee deferral, Roth)
• employee post-tax contributions (i.e. voluntary after-tax)
• forfeitures allocated to the participant for the plan year (or applicable limitation year)

The procedures for correcting excess annual additions are governed by the IRS's Employer Compliance Resolution System (EPCRS). In addition to refunding the excess amount, the Self Correction Program (SCP) rules under EPCRS require an employer to have established practices and procedures in place to assure that this operational error does not occur in future years.

What does an Annual Additions (IRC 415) test failure mean to an affected participant and what should the employer communicate to the participant?
1. The excess annual addition and attributable match (if applicable) must be removed from the participant's account.
2. The excess amount refunded to the participant will be taxed in the year of distribution.
3. The distribution is subject to a 10% federal income tax, unless the participant completes a Form W-4R indicating he/she either does not want taxes withheld or wants an additional amount withheld.
4. The distribution is not subject to the following:
a. 20% mandatory tax withholding; or
b. Additional 10% tax if the participant is under age 59½.
5. The distribution is not eligible for rollover to another qualified plan or IRA.
6. The participant will receive a Form 1099-R for the calendar year in which the refund was made.

What does the Annual Additions (IRC 415) test failure mean to the employer?
1. The Compliance Test Excess Summary provides the amount of the excess annual addition and any applicable earnings that are required to be returned from the participant account.
2. The excess amount must be removed from the participant's account so we can complete year-end administration. Please keep in mind that if any of the information is modified as reported in the attached paperwork, the testing results will be affected.
3. The employer must establish practices and procedures to assure that this operational failure does not occur in future years.
4. The employer should keep a record of the excess/refund for auditing purposes.
5. The employer should communicate the excess/refund to the affected participants. For your convenience, we have attached a sample participant communication which may need to be modified to meet each individual's situation.
"""

_ADP_ACP_LETTER = """SAMPLE/DRAFT Communication to Participant
(To Be Placed On Company Letterhead)

Dear <Participant Name>

We are writing to let you know that <$0.00> will be withdrawn from your plan account due to the failure of the plan's Actual Deferral Percentage (ADP) and/or Actual Contribution Percentage (ACP) nondiscrimination testing for the 2026 plan year. This amount includes a refund of <$0.00> which is your own employee contributions and may also include employer contributions, plus earnings.

Sources of money included within the ADP/ACP test are:
• employee deferral contributions (i.e. pre-tax employee deferrals, Roth) - ADP
• employee post-tax contributions (i.e. voluntary after tax) - ACP
• employer matching contributions - ACP
• match forfeitures allocated for the plan year - ACP

What does failing the ADP/ACP nondiscrimination testing mean to you as a participant?
1. The excess contributions must be removed from your account.
2. If applicable, attributable match must be forfeited and removed from your account.
3. The excess amount refunded to you will be taxed to you in the year of distribution.
4. The distribution is subject to a 10% federal income tax, unless waived by completing a Form W-4R indicating you do not want taxes withheld or you want a different amount withheld.
5. The distribution is not subject to the following:
a. 20% mandatory tax withholding; or
b. the additional 10% tax if you are under age 59½.
6. The distribution is not eligible for rollover to another qualified plan or IRA.
7. You will receive a Form 1099-R for the calendar year in which the refund was made.

If you have any questions, please contact me.
"""

SAMPLE_LETTER_ADP = _ADP_ACP_LETTER
SAMPLE_LETTER_ACP = _ADP_ACP_LETTER
SAMPLE_LETTER_ADP_ACP = _ADP_ACP_LETTER

SAMPLE_LETTER_402G = """SAMPLE/DRAFT Communication to Participant
(To Be Placed on Company Letterhead)

Dear <Participant Name>

We are writing to let you know that <$0.00> will be withdrawn from your plan account as the 402(g) Deferral Limit has been exceeded for the 2025 calendar year. This amount includes a refund of <$0.00> which is your own employee contributions, plus earnings.

Sources of money included in the 402(g) Deferral limit are:
• employee deferral contributions (i.e. pre-tax and Roth employee deferrals)

What does failing the 402(g) Deferral limit mean to you as a participant?
1. The excess deferrals must be removed from your account prior to 4/15 of the following calendar year in which the excess occurs.
2. If applicable, the attributable match must be forfeited and removed from your account.
3. The excess amount refunded to you will be taxed as follows:
a. if excess is returned prior to end of calendar year in which excess occurred, it is taxed in the year of distribution.
b. if excess is returned after calendar year in which excess occurred, but prior to 4/15, contributions are taxable for the calendar year excess made and earnings in year of distribution.
c. if excess is returned after 4/15 (calendar year following excess occurred), the excess contributions are taxable for the calendar year the excess contribution was made and the earnings are taxed in the year of distribution. When a distributable event occurs, the excess will be taxed again. No distribution from your account will occur at this time.
4. Federal tax withholding will not be withheld from this distribution unless Form W-4R is returned indicating the amount of taxes to be withheld.
5. The distribution is not subject to the following:
a. 20% mandatory tax withholding; or
b. the additional 10% tax if you are under age 59½.
6. The distribution is not eligible for rollover to another qualified plan or IRA.
7. You will receive a Form 1099-R for the calendar year in which the refund was made.

If you have any questions, please contact me.
"""

SAMPLE_LETTER_415 = """SAMPLE/DRAFT Communication to Participant
(To Be Placed on Company Letterhead)

Dear <Participant Name>

We are writing to let you know that <$0.00> will be withdrawn from your plan account as the Annual Additions (IRC 415) limit has been exceeded for the plan year ending 2026. This amount includes a refund of <$0.00> which is your own employee contributions, plus any positive applicable earnings, negative earnings are not included. In addition, if there are any employer contributions, plus applicable earnings, they will be forfeited as required by IRS regulations.

The Annual Additions (IRC 415) limit for the plan year ending 2026 is the lesser of $72,000 or 100% of a participant's compensation for the year.

Sources of money included within the 415 (Annual Additions) limit are:
• employer contributions
• employee deferral contributions (i.e. pre-tax employee deferrals, Roth)
• employee post-tax contributions (i.e. voluntary after tax)
• forfeitures allocated to the participant for the plan year (or applicable limitation year)

What does exceeding the Annual Additions (IRC 415) limit mean to you as a participant?
1. The excess annual addition and attributable match (if applicable) must be removed from your account.
2. The excess amount refunded to you will be taxed to you in the year of distribution.
3. The distribution is subject to a 10% federal income tax, unless waived by completing a Form W-4R indicating you do not want taxes withheld or you want a different amount withheld.
4. The distribution is not subject to the following:
a. 20% mandatory tax withholding; or
b. the additional 10% tax if you are under age 59½.
5. The distribution is not eligible for rollover to another qualified plan or IRA.
6. You will receive a Form 1099-R for the calendar year in which the refund was made.

If you have any questions, please contact me.
"""


def build_sample_letters_pdf(
    *,
    method: str = "CURRENT",
    adp: str = "Fail",
    acp: str = "Fail",
    g402: str = "Fail",
    s415: str = "Fail",
    returns: str = "Returns Required",
    after_deadline: bool = False,
    include_j: bool = True,
    include_j_adp: bool | None = None,
    include_j_acp: bool | None = None,
    include_k: bool = True,
    include_415_notice: bool = True,
    include_415_letter: bool = True,
) -> fitz.Document:
    """TEST23 sample letters (J/K) plus the 415 failure packet and letter (L).

    Purpose:
        TEST23 sample letters (J/K) plus the 415 failure packet and letter (L).

    Args:
        method: Method. Type: str.
        adp: Adp. Type: str.
        acp: Acp. Type: str.
        g402: G402. Type: str.
        s415: S415. Type: str.
        returns: Returns. Type: str.
        after_deadline: After deadline. Type: bool.
        include_j: Include j. Type: bool.
        include_j_adp: Include j adp. Type: bool | None.
        include_j_acp: Include j acp. Type: bool | None.
        include_k: Include k. Type: bool.
        include_415_notice: Include 415 notice. Type: bool.
        include_415_letter: Include 415 letter. Type: bool.

    Returns:
        a fitz.Document.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        build_sample_letters_pdf(method="text", adp="text", acp="text", g402="text") returns a fitz.Document.

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open()
    cover = [
        "Cover Letter",
        "Plan Number: 666666",
        "Plan Name: Harbor Manufacturing 401(k) Plan",
        "Company Name: Harbor Manufacturing",
        "Address: 10 Harbor Way, Boston, MA 02110",
        "Plan Year: 01/01/2024 - 12/31/2024",
        f"Testing Method: {method}",
        f"ADP Test: {adp}",
        f"ACP Test: {acp}",
        f"402(g) Test: {g402}",
        f"415 Test: {s415}",
        returns,
        "Correction Within 12 Months",
    ]
    if after_deadline:
        cover.append("402(g) failure not processed by 4/15 deadline — noted on the 402(g) test.")
    _textbox(doc, "\n".join(cover))
    if include_j_adp is None:
        include_j_adp = include_j
    if include_j_acp is None:
        include_j_acp = include_j
    if include_j_adp or include_j_acp:
        _styled_page(doc, SAMPLE_LETTER_ADP_ACP, number=9)
    if include_k:
        _styled_page(doc, SAMPLE_LETTER_402G, number=10)
    if include_415_notice:
        _styled_page(doc, NOTICE_415, number=8)
    if include_415_letter:
        _styled_page(doc, SAMPLE_LETTER_415, number=11)
    return doc


def build_failure_letter_sample() -> fitz.Document:
    """415 information and the three sample letters, laid out like package pages 8–11.

    Purpose:
        415 information and the three sample letters, laid out like package pages 8–11.

    Args:
        None.

    Returns:
        fitz.Document.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        build_failure_letter_sample() returns fitz.Document.

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open()
    _styled_page(doc, NOTICE_415, number=8)
    _styled_page(doc, SAMPLE_LETTER_ADP_ACP, number=9)
    _styled_page(doc, SAMPLE_LETTER_402G, number=10)
    _styled_page(doc, SAMPLE_LETTER_415, number=11)
    return doc


def _styled_page(doc: fitz.Document, text: str, *, number: int | None = None) -> None:
    """A failure-information page or a sample letter, with the package headings.

    Purpose:
        A failure-information page or a sample letter, with the package headings.

    Args:
        doc: Open PDF. Must not be closed.
        text: Text from a page or a file.
        number: Number. Type: int | None.

    Returns:
        None.

    Raises:
        A closed PDF raises from PyMuPDF.

    Example:
        _styled_page(doc, "text", number=1) returns None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    page = doc.new_page(width=595.28, height=841.89)
    y = 52.0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            y += 8
            continue
        if line in {
            "Annual Additions (IRC 415) Test Failure Information",
            "SAMPLE/DRAFT Communication to Participant",
        }:
            _center(page, line, y, 12, "hebo")
            y += 18
            continue
        if line.startswith("(To Be Placed"):
            _center(page, line, y, 11, "hebo")
            y += 16
            page.draw_line(fitz.Point(54, y), fitz.Point(page.rect.width - 54, y), color=_BLACK, width=0.8)
            y += 18
            continue
        if line in {
            "July 1, 2025 - June 30, 2026",
            "OUR HOUSE, INC. 401(K) RETIREMENT PLAN",
            "800808",
        }:
            font = "hebo" if line != "July 1, 2025 - June 30, 2026" else "helv"
            size = 11 if line.startswith("July") else 12
            _center(page, line, y, size, font)
            y += size + 4
            if line == "800808":
                y += 4
                page.draw_line(fitz.Point(54, y), fitz.Point(page.rect.width - 54, y), color=_BLACK, width=0.8)
                y += 16
            continue
        bullet = line.startswith("• ")
        numbered = bool(re.match(r"\d+\.\s", line))
        lettered = bool(re.match(r"[a-c]\.\s", line))
        question = line.endswith("?")
        bold = question or line.startswith("The Annual Additions (IRC 415) limit") or line.startswith("Sources of money")
        x = 90.0 if lettered else 72.0 if (bullet or numbered) else 54.0
        body = line
        font = "hebo" if bold else "helv"
        y = _wrapped_text(page, body, y, x, page.rect.width - x - 54, font, 9)
        y += 3
    if number is not None:
        _page_number(page, number)

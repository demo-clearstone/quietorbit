"""Assembly procedure. Read process_uploads from top to bottom.

1. Sort uploads into PDFs, Excel, and the compliance summary.
2. Drop a 401(k) BRF file, order the PDFs, and merge them.
3. Read the plan from the PDF, then overlay Excel and the summary.
4. Validate and decide which Action Required paragraphs to keep.
5. Edit the PDF: paragraphs, recap bullets, QNEC, wording, dates, overview.
6. Add bookmarks, scan for an SSN, and stop if a required check fails.
7. Save the PDF, the highlight marks, the email draft, and the assembly log.

The other files in this folder do one of those jobs. This file is the order.
YAML is read in plan_config.py. Each function there records its input file and its output.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone

import fitz
from fastapi import HTTPException

from models.job import JobResult
from models.review import ValidationItem
from models.job import HighlightMark
from services import (
    assembly_log,
    assembly_stops,
    bookmark_service,
    change_marks,
    file_order,
    outlook_service,
    pdf_assembler,
    pdf_extractor,
    package_polish,
    pdf_modifier,
    plan_profile_service,
    profile_debug,
    review_service,
    rules_engine,
    save_service,
    source_profile,
    source_rewrite,
    ssn_scan,
)
from services import package_builder
from services import midyear, plan_457
from services.plan_config import is_457_plan, package_flags, plan_family


def process_uploads(
    uploads: list[tuple[str, bytes]],
    *,
    auto_order: bool = True,
    extra_warnings: list[str] | None = None,
    source_folder: str | None = None,
    rewrite_sources: bool = False,
    check_assembly_stops: bool = False,
) -> JobResult:
    """Assemble one valuation package from the uploaded files.

    Purpose:
        Sort the uploads, merge the PDFs, read the plan and Excel, keep or
        remove paragraphs, edit the PDF, add bookmarks, and save the package.

    Args:
        uploads: Pairs of file name and file bytes.
        auto_order: True sorts the PDFs into report order before they are merged.
        extra_warnings: Messages to include on the result. None means none.
        source_folder: Folder the PDFs were loaded from. None when the user uploaded files.
        rewrite_sources: True rewrites dates and other source text inside the PDF.
        check_assembly_stops: True stops assembly when a required check fails.

    Returns:
        The saved package, warnings, and highlight rectangles.

    Raises:
        HTTPException: The assembly input is not usable.
        OSError: A PDF or the output folder cannot be read or written.

    Example:
        process_uploads([("555001 ADP-Test.pdf", data)], auto_order=True)
        returns a JobResult.

    Side effects:
        Writes the valuation PDF, the email draft, and the assembly log.
    """
    job_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    warnings = list(extra_warnings or [])
    highlights: list[dict] = []

    # 1. Sort the uploads.
    pdfs, excels = _split_uploads(uploads)
    valuation, summary_texts = _split_summaries(pdfs)
    excel_profiles = [(name, source_profile.parse_excel(data)) for name, data in excels]

    # 2. Choose the package type, drop BRF when required, then merge.
    is_403b = package_polish.package_is_403b(valuation) or any(
        str(parsed.get("plan_type") or "").lower().startswith("403")
        for _name, parsed in excel_profiles
    )
    is_midyear = midyear.package_is_midyear(valuation)
    valuation, brf_notes = package_polish.exclude_brf_uploads(valuation, keep_brf=is_403b)
    warnings.extend(brf_notes)
    if not valuation:
        raise HTTPException(
            status_code=400,
            detail="BRF reports are not included, and no other PDF was uploaded.",
        )
    if is_midyear:
        ordered = midyear.order_uploads(valuation) if auto_order else list(valuation)
    else:
        ordered = file_order.order_uploads(valuation) if auto_order else list(valuation)
    doc = pdf_assembler.merge_pdfs(ordered)
    email_path = ""
    log_file = ""
    saved_copy = ""
    profile_debug_path = ""
    subject = ""
    try:
        if is_midyear or midyear.package_is_midyear([], doc):
            is_midyear = True
            warnings.extend(midyear.reorder_pages(doc))
        warnings.extend(package_polish.reorder_inner_pages(doc))

        # 3. Read the plan, then let Excel and the summary override it.
        profile = pdf_extractor.extract_plan_profile(doc)
        profile.extra["field_sources"] = {
            key: "PDF package text"
            for key, value in profile.model_dump().items()
            if key not in {"extra", "detected_sections", "extraction_warnings"}
            and value not in (None, "", [], {})
        }
        pdf_plan_name = profile.plan_name
        cover_company = profile.company_name
        cover_address = profile.company_address
        cover_pye = profile.plan_year_end
        excel_overlays: list[dict] = []
        excel_sources: list[str] = []
        excel_plan_name: str | None = None
        excel_company: str | None = None
        excel_address: str | None = None
        excel_pye: str | None = None
        for name, parsed in excel_profiles:
            if parsed.get("plan_name"):
                excel_plan_name = str(parsed["plan_name"])
            if parsed.get("company_name"):
                excel_company = str(parsed["company_name"])
            if parsed.get("company_address"):
                excel_address = str(parsed["company_address"])
            if parsed.get("plan_year_end"):
                excel_pye = str(parsed["plan_year_end"])
            excel_overlays.append(parsed)
            excel_sources.append(f"Excel: {name}")
            warnings.append(f"Read Val Assembly Excel: {name}")
        summary_overlays: list[dict] = []
        summary_sources: list[str] = []
        for name, text in summary_texts:
            summary_overlays.append(source_profile.parse_summary_text(text))
            summary_sources.append(f"Result Summary: {name}")
            warnings.append(f"Read Compliance Testing Summary: {name}")
        if not summary_overlays:
            merged_text = "\n".join((page.get_text("text") or "") for page in doc)
            if re.search(
                r"compliance testing summary of results|result summary|test summary",
                merged_text,
                re.I,
            ):
                parsed = source_profile.parse_summary_text(merged_text)
                if parsed.get("adp_failed") is not None or parsed.get("fail_402g") is not None:
                    summary_overlays.append(parsed)
                    summary_sources.append("Result Summary embedded in PDF package")
        # Summary tests are authoritative for pass/fail. Excel remains the final
        # overlay for fields it explicitly provides (identity, method, HCE flags).
        overlays = summary_overlays + excel_overlays
        overlay_sources = summary_sources + excel_sources
        explicit_contributions = any(
            "contributions_required" in overlay for overlay in overlays
        )
        profile = source_profile.merge_overlays(
            profile,
            overlays,
            warnings,
            sources=overlay_sources,
        )
        if profile.top_heavy_percent is not None:
            profile.top_heavy = profile.top_heavy_percent > 60
            profile.extra.setdefault("field_sources", {})["top_heavy"] = "Top-heavy percentage; threshold is greater than 60%"
        section_names = set()
        with file_order.use_filename_batch([name for name, _data in ordered]):
            section_names = {
                str(spec.get("name"))
                for name, _data in ordered
                if (spec := file_order.matched_spec(name))
            }
        if profile.hce_current is None and "HCE/Key" in section_names:
            profile.hce_current = True
            profile.extra["field_sources"]["hce_current"] = "Uploaded report filename"
        if profile.hce_future is None and "Future HCE" in section_names:
            profile.hce_future = True
            profile.extra["field_sources"]["hce_future"] = "Uploaded report filename"
        if package_polish.has_variance_client_copy([name for name, _data in ordered], doc):
            profile.contributions_required = True
            explicit_contributions = True
            profile.extra["field_sources"]["contributions_required"] = "Variance report existence"
        profile.extra["contributions_explicit"] = explicit_contributions
        cover_text = "\n".join((page.get_text("text") or "") for page in doc[:2])
        family = plan_family(cover_text)
        if family:
            profile.plan_type = family
            profile.extra["field_sources"]["plan_type"] = "Cover letter plan name"
        elif is_403b and not (profile.plan_type or "").strip():
            profile.plan_type = "403b"
            profile.extra["field_sources"]["plan_type"] = "403(b) package detection"
        if is_midyear:
            profile.midyear = True
            for key, value in midyear.read_letter_facts(doc).items():
                if getattr(profile, key, None) in (None, ""):
                    setattr(profile, key, value)
        profile = plan_profile_service.finalize_profile(profile)

        # 4. Check the profile and decide keep or remove.
        review = review_service.validate(profile, doc=doc)
        decisions = rules_engine.evaluate(profile)
        profile_debug_path = str(
            profile_debug.write_profile_debug(
                job_id,
                profile,
                decisions,
                doc,
                source_files=[name for name, _data in ordered]
                + [name for name, _data in excels]
                + [name for name, _text in summary_texts],
                phase="before_business_rule_edits",
            )
        )
        # 5. Edit the PDF.
        removed = pdf_modifier.apply_decisions(doc, decisions, profile.plan_type)
        recap_removed = pdf_modifier.apply_recap_bullets(doc, decisions, profile.plan_type)
        filled = pdf_modifier.fill_qnec_placeholders(doc, profile, highlights)
        flags = package_flags(profile.plan_type)
        if is_457_plan(profile.plan_type):
            warnings.extend(plan_457.remove_contribution_overview(doc))
        if profile.midyear:
            warnings.extend(midyear.apply_letter(doc, profile))
        warnings.extend(package_polish.remove_disallowed_wording(doc, keep_soc=bool(flags.get("keep_soc"))))
        if flags.get("rewrite_adp_mentions"):
            warnings.extend(package_polish.rewrite_403b_adp_mentions(doc))
        else:
            warnings.extend(package_polish.drop_brf_pages(doc))
        if rewrite_sources:
            warnings.extend(source_rewrite.apply_source_rewrites(doc, profile, highlights))
        else:
            warnings.extend(source_rewrite.apply_cover_date(doc, highlights))
            warnings.extend(source_rewrite.apply_402g_dates(doc, profile, highlights))
        if not profile.midyear and not is_457_plan(profile.plan_type):
            warnings.extend(
                package_builder.ensure_compliance_overview(
                    doc,
                    plan_name=profile.plan_name,
                    plan_number=profile.plan_number,
                    plan_year_start=profile.plan_year_start,
                    plan_year_end=profile.plan_year_end,
                )
            )
        warnings.extend(package_polish.renumber_footers(doc))
        warnings.extend(package_polish.normalize_report_layout(doc))
        # 6. Bookmarks, SSN scan, and assembly stops.
        profile.detected_sections = pdf_extractor.detect_sections(doc)
        profile_debug_path = str(
            profile_debug.write_profile_debug(
                job_id,
                profile,
                decisions,
                doc,
                source_files=[name for name, _data in ordered]
                + [name for name, _data in excels]
                + [name for name, _text in summary_texts],
                phase="after_business_rule_edits",
            )
        )
        review.items.extend(package_polish.package_checks(doc, profile))
        bookmark_count = bookmark_service.add_bookmarks(
            doc,
            profile,
            source_files=[name for name, _data in ordered],
        )
        if bookmark_service.is_testing_only(doc) and not profile.midyear and not is_457_plan(profile.plan_type):
            if flags.get("rewrite_adp_mentions"):
                warnings.append(
                    "ACP only package. Bookmarks: Cover Letter, Test Summary, HCE, Future HCE, ACP Test."
                )
            else:
                warnings.append(
                    "ADP/ACP only package. Bookmarks: Cover Letter, Test Summary, HCE/Key, "
                    "Future HCE, ADP/ACP Tests."
                )
        ssn_pages = ssn_scan.scan_ssns(doc)
        review.ssn_found = bool(ssn_pages)
        review.ssn_pages = ssn_pages
        review.items.append(
            ValidationItem(
                code="ssn_scan",
                label="SSN scan",
                passed=not ssn_pages,
                detail="No SSNs found"
                if not ssn_pages
                else "SSN found on page(s) " + ", ".join(str(page) for page in ssn_pages),
            )
        )
        if check_assembly_stops:
            reasons = assembly_stops.stop_reasons(
                doc,
                profile,
                source_files=[name for name, _data in ordered],
                excel_plan_name=excel_plan_name,
                pdf_plan_name=pdf_plan_name,
                excel_company=excel_company,
                excel_address=excel_address,
                excel_pye=excel_pye,
                cover_company=cover_company,
                cover_address=cover_address,
                cover_pye=cover_pye,
            )
            if reasons:
                raise HTTPException(status_code=400, detail="Assembly stopped.\n" + "\n".join(reasons))
        # 7. Save the package, the email draft, and the log.
        dest = save_service.testing_folder_from_source(source_folder)
        path = save_service.save_package(doc, job_id, profile, dest_dir=dest)
        change_marks.save_marks(path, highlights)
        if dest:
            saved_copy = str(dest / path.name)
            warnings.append(f"Also saved to {saved_copy}")
        eml = outlook_service.write_draft(path.parent / f"{path.stem}.eml", profile, path.name)
        email_path = str(eml)
        elapsed_seconds = time.perf_counter() - started
        log_file = str(
            assembly_log.append_row(
                save_service.OUTPUT_DIR / "ValAssemblyLog.xlsx",
                profile,
                path.name,
                job_id,
                doc=doc,
                finished_at=datetime.now(),
                elapsed_seconds=elapsed_seconds,
            )
        )
        subject = outlook_service.email_subject(profile)
    finally:
        doc.close()

    warnings.extend(profile.extraction_warnings)
    if auto_order:
        warnings.append("Files were ordered using the TEST23 combine sequence.")
    if removed:
        warnings.append("Removed Action Required paragraph(s): " + ", ".join(removed))
    if recap_removed:
        warnings.append("Removed Year End Recap bullet(s): " + ", ".join(recap_removed))
    if filled:
        warnings.append("Filled Excess Return Notice QNEC amounts: " + ", ".join(filled))
    if subject:
        warnings.append("Outlook draft subject: " + subject)
    kept = [item.rule_id for item in decisions if item.action == "keep"]
    if kept:
        warnings.append("Retained Action Required paragraph(s): " + ", ".join(kept))
    if bookmark_count:
        warnings.append(f"Added {bookmark_count} SOP bookmark(s).")
    if any(d.skipped for d in decisions):
        warnings.append("Some rules were skipped because extraction did not fill required fields.")

    return JobResult(
        job_id=job_id,
        filename=path.name,
        pdf_path=str(path),
        created_at=datetime.now(timezone.utc),
        plan_profile=profile,
        review=review,
        rule_decisions=decisions,
        warnings=warnings,
        highlights=[HighlightMark(**item) for item in highlights],
        source_files=[name for name, _data in ordered] + [name for name, _data in excels] + [name for name, _text in summary_texts],
        download_url=f"/api/jobs/{job_id}/pdf",
        email_subject=subject,
        email_path=email_path,
        log_path=log_file,
        profile_debug_path=profile_debug_path,
        saved_copy_path=saved_copy,
        elapsed_seconds=round(elapsed_seconds, 1),
    )


def _split_uploads(uploads: list[tuple[str, bytes]]) -> tuple[list[tuple[str, bytes]], list[tuple[str, bytes]]]:
    """Separating the uploaded PDFs from the Excel file.

    Purpose:
        Separating the uploaded PDFs from the Excel file.

    Args:
        uploads: List of (file name, file bytes).

    Returns:
        tuple[list[tuple[str, bytes]], list[tuple[str, bytes]]].

    Raises:
        None.

    Example:
        _split_uploads(data) returns tuple[list[tuple[str, bytes]], list[tuple[str, bytes]]].

    Side effects:
        None. This function only reads data and returns a value.
    """
    pdfs: list[tuple[str, bytes]] = []
    excels: list[tuple[str, bytes]] = []
    for name, data in uploads:
        lower = name.lower()
        if lower.endswith((".xlsx", ".xls")):
            excels.append((name, data))
        elif lower.endswith(".pdf"):
            pdfs.append((name, data))
    return pdfs, excels


def _split_summaries(pdfs: list[tuple[str, bytes]]) -> tuple[list[tuple[str, bytes]], list[tuple[str, str]]]:
    """Finding the compliance summary among the PDFs.

    Purpose:
        Finding the compliance summary among the PDFs.

    Args:
        pdfs: Pdfs. Type: list[tuple[str, bytes]].

    Returns:
        a tuple[list[tuple[str, bytes]], list[tuple[str, str]]].

    Raises:
        None.

    Example:
        _split_summaries([]) returns a tuple[list[tuple[str, bytes]], list[tuple[str, str]]].

    Side effects:
        None. This function only reads data and returns a value.
    """
    valuation: list[tuple[str, bytes]] = []
    summaries: list[tuple[str, str]] = []
    for name, data in pdfs:
        text = _pdf_text(data)
        named_summary = bool(re.search(r"result\s*summ|test\s*summ", name, re.I))
        is_valuation_package = bool(re.search(r"valuation\s*(?:pkg|package)", name, re.I))
        # A valuation package mentions the summary page inside Top Heavy wording.
        # Only a document that opens with the summary is a summary sidecar.
        first_lines = [line.strip() for line in text.splitlines() if line.strip()][:6]
        opens_with_summary = bool(first_lines) and bool(
            re.match(r"^(?:compliance testing summary of results|result summary|test summary|compliance summary)\b", first_lines[0], re.I)
        )
        if (opens_with_summary and not is_valuation_package) or named_summary:
            summaries.append((name, text))
            # Summary PDFs are both extraction sources and required package pages,
            # regardless of filename. A summary embedded in a Valuation Pkg is
            # already part of that document and therefore is not duplicated.
            valuation.append((name, data))
        else:
            valuation.append((name, data))
    return valuation, summaries


def _pdf_text(data: bytes) -> str:
    """Pdf text.

    Purpose:
        Pdf text.

    Args:
        data: Raw file bytes.

    Returns:
        str.

    Raises:
        OSError: A file cannot be read or written. A closed PDF raises from PyMuPDF.

    Example:
        _pdf_text(data) returns str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        return "\n".join((page.get_text("text") or "") for page in doc)
    finally:
        doc.close()

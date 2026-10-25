"""Assembly steps for the browser console.

Only the functions called directly by the assembly procedure are recorded.
Nested helpers stay out of the log. PDF bytes and SSN-shaped text are omitted.
The Python terminal is not written.
"""

from __future__ import annotations

import re
import sys
import time
from pathlib import Path
from threading import Lock

from fastapi import HTTPException
from pydantic import BaseModel

_SERVICES = Path(__file__).resolve().parent
_SERVICE_PREFIX = str(_SERVICES).replace("\\", "/") + "/"
_TRACES: dict[str, dict] = {}
_LOCK = Lock()
_MAX_EVENTS = 6000
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_SKIP_LOCALS = {"self", "cls", "doc"}
_PROFILE_SKIP = {
    "extraction_warnings",
    "extra",
    "highlights",
    "warnings",
}
_PURPOSE = {
    "services/orchestrator.py:process_uploads": "Running the full assembly",
    "services/orchestrator.py:_split_uploads": "Separating the uploaded PDFs from the Excel file",
    "services/orchestrator.py:_split_summaries": "Finding the compliance summary among the PDFs",
    "services/source_profile.py:parse_excel": "Extracting plan answers from the Excel file",
    "services/package_polish.py:package_is_403b": "Checking whether the uploads are a 403(b) package",
    "services/midyear.py:package_is_midyear": "Checking whether this is a mid-year letter",
    "services/package_polish.py:exclude_brf_uploads": "Removing a 401(k) BRF file from the uploads",
    "services/file_order.py:order_uploads": "Ordering the PDFs into report sequence",
    "services/midyear.py:order_uploads": "Ordering the mid-year letter files",
    "services/pdf_assembler.py:merge_pdfs": "Merging the ordered PDFs into one package",
    "services/midyear.py:reorder_pages": "Reordering pages in the mid-year letter",
    "services/package_polish.py:reorder_inner_pages": "Ordering location pages inside each section",
    "services/pdf_extractor.py:extract_plan_profile": "Extracting plan data from the merged PDF",
    "services/source_profile.py:parse_summary_text": "Extracting pass/fail results from the compliance summary",
    "services/source_profile.py:merge_overlays": "Applying the Excel and summary results onto the plan profile",
    "services/file_order.py:matched_spec": "Matching a file name to its report section",
    "services/package_polish.py:has_variance_client_copy": "Checking whether a variance client copy was uploaded",
    "services/plan_config.py:plan_family": "Reading the plan type from the cover letter",
    "services/midyear.py:read_letter_facts": "Extracting facts from the mid-year letter",
    "services/plan_profile_service.py:finalize_profile": "Preparing the plan profile for the rules",
    "services/review_service.py:validate": "Checking validation on the plan profile",
    "services/rules_engine.py:evaluate": "Deciding which paragraphs to keep or remove",
    "services/profile_debug.py:write_profile_debug": "Saving a copy of the plan profile",
    "services/pdf_modifier.py:apply_decisions": "Removing Action Required paragraphs that do not apply",
    "services/pdf_modifier.py:apply_recap_bullets": "Removing Year End Recap bullets that do not apply",
    "services/pdf_modifier.py:fill_qnec_placeholders": "Filling the QNEC amounts on the excess notice",
    "services/plan_config.py:package_flags": "Loading the rules for this plan type",
    "services/plan_config.py:is_457_plan": "Checking whether the plan is a 457 plan",
    "services/plan_457.py:remove_contribution_overview": "Removing the 457 contribution overview",
    "services/midyear.py:apply_letter": "Editing the mid-year letter",
    "services/package_polish.py:remove_disallowed_wording": "Removing audited, SOC, 5500, and escalation wording",
    "services/package_polish.py:rewrite_403b_adp_mentions": "Rewriting ADP wording for the 403(b) package",
    "services/package_polish.py:drop_brf_pages": "Removing BRF pages from the 401(k) package",
    "services/source_rewrite.py:apply_source_rewrites": "Rewriting dates and other source text",
    "services/source_rewrite.py:apply_cover_date": "Rewriting the cover letter date to today",
    "services/source_rewrite.py:apply_402g_dates": "Rewriting the 402(g) dates",
    "services/package_builder.py:ensure_compliance_overview": "Adding the compliance overview pages",
    "services/package_polish.py:renumber_footers": "Renumbering the page footers",
    "services/pdf_extractor.py:detect_sections": "Finding each report section after the edits",
    "services/package_polish.py:package_checks": "Checking the package pages against the profile",
    "services/bookmark_service.py:add_bookmarks": "Writing the bookmarks",
    "services/bookmark_service.py:is_testing_only": "Checking whether this is an ADP/ACP-only package",
    "services/ssn_scan.py:scan_ssns": "Scanning the package for a Social Security number",
    "services/assembly_stops.py:stop_reasons": "Checking whether assembly must stop",
    "services/save_service.py:testing_folder_from_source": "Finding the Testing folder for the saved PDF",
    "services/save_service.py:save_package": "Saving the valuation PDF",
    "services/change_marks.py:save_marks": "Saving the highlight marks",
    "services/outlook_service.py:write_draft": "Writing the email draft",
    "services/assembly_log.py:append_row": "Adding this run to the assembly log",
    "services/outlook_service.py:email_subject": "Building the email subject",
}


def summarize(value: object, *, depth: int = 0) -> object:
    """Summarize.

    Purpose:
        Summarize.

    Args:
        value: Value. Type: object.
        depth: Depth. Type: int.

    Returns:
        a object.

    Raises:
        None.

    Example:
        summarize(value, depth=1) returns a object.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (bytes, bytearray)):
        return {"type": "bytes", "length": len(value)}
    if isinstance(value, str):
        return _clip(_SSN.sub("[ssn]", value))
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, Path):
        return str(value)
    if depth >= 4:
        return {"type": type(value).__name__}
    if isinstance(value, BaseModel):
        fields = {}
        for name in type(value).model_fields:
            if name in _PROFILE_SKIP:
                item = getattr(value, name)
                fields[name] = {"type": type(item).__name__, "count": len(item)} if hasattr(item, "__len__") else {"type": type(item).__name__}
                continue
            fields[name] = summarize(getattr(value, name), depth=depth + 1)
        return {"type": type(value).__name__, **fields}
    if isinstance(value, dict):
        items = list(value.items())
        mapped = {str(key): summarize(item, depth=depth + 1) for key, item in items[:24]}
        if len(items) > 24:
            mapped["…"] = f"+{len(items) - 24} more keys"
        return mapped
    if isinstance(value, (list, tuple, set)):
        rows = list(value)
        if rows and all(_is_named_blob(item) for item in rows):
            return [str(item[0]) for item in rows]
        preview = [summarize(item, depth=depth + 1) for item in rows[:12]]
        if len(rows) > 12:
            preview.append(f"… +{len(rows) - 12} more")
        return preview
    page_count = getattr(value, "page_count", None)
    if isinstance(page_count, int):
        return {"type": "PDF", "pages": page_count}
    name = getattr(value, "name", None)
    action = getattr(value, "action", None)
    if isinstance(name, str) and action is not None:
        return {"name": name, "action": action, "skipped": bool(getattr(value, "skipped", False))}
    return {"type": type(value).__name__}


def start_trace(token: str) -> None:
    """Start trace.

    Purpose:
        Start trace.

    Args:
        token: Id for this assembly trace.

    Returns:
        None.

    Raises:
        HTTPException: The assembly input is not usable.

    Example:
        start_trace("text") returns None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    with _LOCK:
        for key, trace in list(_TRACES.items()):
            if trace["status"] != "running" and time.monotonic() - trace["created"] > 900:
                del _TRACES[key]
        if token in _TRACES:
            raise HTTPException(409, "This console trace already exists. Process again with a new trace ID.")
        if len(_TRACES) >= 20:
            finished = next((key for key, trace in _TRACES.items() if trace["status"] != "running"), None)
            if finished is None:
                raise HTTPException(429, "Too many active console traces.")
            del _TRACES[finished]
        _TRACES[token] = {"created": time.monotonic(), "status": "running", "events": [], "truncated": False}


def read_trace(token: str, after: int = 0) -> dict:
    """Read trace.

    Purpose:
        Read trace.

    Args:
        token: Id for this assembly trace.
        after: After. Type: int.

    Returns:
        a dict.

    Raises:
        HTTPException: The assembly input is not usable.

    Example:
        read_trace("text", 1) returns a dict.

    Side effects:
        None. This function only reads data and returns a value.
    """
    with _LOCK:
        trace = _TRACES.get(token)
        if trace is None:
            raise HTTPException(404, "Console trace not started or expired.")
        return {
            "events": list(trace["events"][after : after + 300]),
            "status": trace["status"],
            "total": len(trace["events"]),
            "truncated": trace["truncated"],
        }


def run_traced(token: str, function, *args, **kwargs):
    """Record one step per function the assembly procedure calls directly.

    Purpose:
        Record one step per function the assembly procedure calls directly.

    Args:
        token: Id for this assembly trace.
        function: Function. Type: unspecified.
        *args: Args. Type: unspecified.
        **kwargs: Kwargs. Type: unspecified.

    Returns:
        None.

    Raises:
        None.

    Example:
        run_traced("text", function) returns None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    open_calls: dict[int, tuple[dict, float]] = {}
    started = time.perf_counter()
    root_name = function.__name__

    def append(event: dict) -> None:
        """Append.

        Purpose:
            Append.

        Args:
            event: Event. Type: dict.

        Returns:
            None.

        Raises:
            None.

        Example:
            append({}) returns None.

        Side effects:
            None. This function only reads data and returns a value.
        """
        with _LOCK:
            trace = _TRACES[token]
            if len(trace["events"]) >= _MAX_EVENTS:
                trace["truncated"] = True
                return
            event["sequence"] = len(trace["events"]) + 1
            event["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
            trace["events"].append(event)

    def profile(frame, event, result):
        """Profile.

        Purpose:
            Profile.

        Args:
            frame: Frame. Type: unspecified.
            event: Event. Type: unspecified.
            result: Result. Type: unspecified.

        Returns:
            None.

        Raises:
            None.

        Example:
            profile(frame, event, result) returns None.

        Side effects:
            None. This function only reads data and returns a value.
        """
        if event not in {"call", "return"}:
            return
        code = frame.f_code
        filename = code.co_filename.replace("\\", "/")
        if code.co_name.startswith("<") or not filename.startswith(_SERVICE_PREFIX):
            return
        if filename == __file__.replace("\\", "/"):
            return
        if event == "call":
            caller = _outer_caller(frame)
            caller_name = caller.f_code.co_name if caller is not None else ""
            file_name = "services/" + Path(filename).name
            # Helpers such as _pdf_text run once per file. Only the named assembly steps are logged.
            if f"{file_name}:{code.co_name}" not in _PURPOSE:
                return
            if code.co_name != root_name and caller_name != root_name:
                return
            count = code.co_argcount + code.co_kwonlyargcount
            inputs = {
                name: summarize(frame.f_locals[name])
                for name in code.co_varnames[:count]
                if name in frame.f_locals and name not in _SKIP_LOCALS
            }
            open_calls[id(frame)] = (
                {
                    "function": code.co_name,
                    "file": file_name,
                    "purpose": _purpose(file_name, code.co_name, inputs),
                    "input": inputs,
                    "code_link": f"{file_name}:{code.co_firstlineno}",
                },
                time.perf_counter(),
            )
            return
        started_call = open_calls.pop(id(frame), None)
        if started_call is None:
            return
        details, began = started_call
        append(
            {
                "event": "step",
                **details,
                "output": summarize(result),
                "duration_ms": round((time.perf_counter() - began) * 1000, 2),
            }
        )

    previous = sys.getprofile()
    try:
        sys.setprofile(profile)
        result = function(*args, **kwargs)
    except BaseException as exc:
        append(
            {
                "event": "error",
                "exception_type": type(exc).__name__,
                "function": function.__name__,
                "purpose": f"Assembly raised {type(exc).__name__}",
                "file": "services/orchestrator.py" if function.__name__ == "process_uploads" else "",
                "input": {},
                "output": None,
                "code_link": "",
            }
        )
        with _LOCK:
            _TRACES[token]["status"] = "failed"
        raise
    else:
        with _LOCK:
            _TRACES[token]["status"] = "completed"
        return result
    finally:
        sys.setprofile(previous)


def _is_named_blob(item: object) -> bool:
    """Is named blob.

    Purpose:
        Is named blob.

    Args:
        item: Item. Type: object.

    Returns:
        True or False.

    Raises:
        None.

    Example:
        _is_named_blob(item) returns True or False.

    Side effects:
        None. This function only reads data and returns a value.
    """
    return (
        isinstance(item, tuple)
        and len(item) >= 2
        and isinstance(item[0], str)
        and isinstance(item[1], (bytes, bytearray, str))
    )


def _clip(text: str, limit: int = 160) -> str:
    """Clip.

    Purpose:
        Clip.

    Args:
        text: Text from a page or a file.
        limit: Limit. Type: int.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _clip("text", 1) returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[:limit] + "…"


def _outer_caller(frame):
    """Outer caller.

    Purpose:
        Outer caller.

    Args:
        frame: Frame. Type: unspecified.

    Returns:
        None.

    Raises:
        None.

    Example:
        _outer_caller(frame) returns None.

    Side effects:
        None. This function only reads data and returns a value.
    """
    back = frame.f_back
    while back is not None and back.f_code.co_name.startswith("<"):
        back = back.f_back
    return back


def _purpose(file_name: str, function_name: str, inputs: dict) -> str:
    """One short action for this step, including the file or phase when that makes it distinct.

    Purpose:
        One short action for this step, including the file or phase when that makes it distinct.

    Args:
        file_name: File name. Type: str.
        function_name: Function name. Type: str.
        inputs: Inputs. Type: dict.

    Returns:
        a str.

    Raises:
        None.

    Example:
        _purpose("text", "text", {}) returns a str.

    Side effects:
        None. This function only reads data and returns a value.
    """
    if function_name == "matched_spec":
        name = inputs.get("name") or inputs.get("filename")
        if isinstance(name, str) and name:
            return f"Matching {_clip(name, 60)} to its report section"
    if function_name == "write_profile_debug":
        phase = str(inputs.get("phase") or "")
        if "before" in phase:
            return "Saving the profile before the edits"
        if "after" in phase:
            return "Saving the profile after the edits"
    if function_name == "order_uploads" and isinstance(inputs.get("uploads"), list):
        kind = "mid-year letter files" if file_name.endswith("midyear.py") else "PDFs into report sequence"
        return f"Ordering {len(inputs['uploads'])} {kind}"
    if function_name == "parse_excel":
        return "Extracting plan answers from the Excel file"
    text = _PURPOSE.get(f"{file_name}:{function_name}") or _PURPOSE.get(function_name)
    if text:
        return text
    return function_name.replace("_", " ")

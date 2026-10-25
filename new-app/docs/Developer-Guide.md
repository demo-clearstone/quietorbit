# MOA Valuation Package — Developer Guide

**For:** another developer picking up the app, or debugging a package during UAT  
**Date:** 24 October 2026  
**Code:** `new-app/`

This guide matches the code that runs today. If an older note names `rules.yaml`, `paragraphs.yaml`, `sections.yaml`, or `package_map.yaml`, those files are gone. The live files are in section 7.

The business rules came from `POC/TEST23.docx` and the later client update `new-app/TEST23 (1).docx`. This guide tells you which file answers the question and how to see why a paragraph stayed or was removed.

---

## 1. Start it

From `new-app`:

```bash
source .venv/bin/activate
python main.py
```

On this Mac there is no `python` command until the virtual environment is active. If the prompt does not show `(.venv)`, use:

```bash
.venv/bin/python main.py
```

On Windows, from `new-app`:

```bat
.venv\Scripts\python.exe main.py
```

Open **http://127.0.0.1:8002**. The page is `templates/index.html`. It is not a separate frontend project.

Check the process before you blame the package:

```text
GET http://127.0.0.1:8002/health
{"status":"ok","phase":"1","console_trace":true}
```

`console_trace: true` means the server can log steps. It does not mean logging is turned on. Logging is a checkbox, and it is off until someone checks it.

| Setting | Default | What it changes |
|---|---|---|
| `MOA_PORT` | `8002` | The URL port |
| `MOA_HOST` | `127.0.0.1` | This computer only. Another PC cannot open the page unless this is changed. |
| `MOA_OUTPUT_DIR` | `new-app/output` | Where the PDF, `profile_debug.json`, and `ValAssemblyLog.xlsx` are written |

There is no database. A job lives in the `JOBS` dictionary in `api/jobs.py` until the process stops. The PDF on disk remains after a restart. The in-memory preview link does not.

`main.py` starts uvicorn with `reload=False`. A Python change does nothing until you stop the window and start `python main.py` again. The HTML response sends `Cache-Control: no-store`. After an HTML or JavaScript change, refresh the browser. You do not need to restart Python for that.

Do not look in `backend/`, `frontend/`, `electron/`, or the root `pdf-process.py`. Those are the old proof of concept. This application does not call them.

---

## 2. The path from the button to the files

1. `templates/index.html` builds a form and POSTs it to `/api/jobs`.
2. `api/jobs.py`, function `create_job`, reads the files and calls `process_uploads`.
3. `services/orchestrator.py`, function `process_uploads`, does the work and returns a `JobResult`.
4. `create_job` stores that result in `JOBS` and sends it back as JSON. The page then fills Keep / remove, Checks, Notes, preview, and the download links.

The browser does not merge PDFs. PyMuPDF does, inside the Python process.

`GET /api/inspect` returns 405. Inspection is `POST /api/inspect` only. Opening that URL in the address bar is not a failure of the app.

A browser message **Failed to fetch** means the page never got an HTTP response. Check `/health` first. Then check that the process was restarted after the last Python change, that the port is 8002, and that the upload is under the limit (50 MB per file, 80 files).

---

## 3. If they ask “where is that in the code?”

| They ask about | Open this |
|---|---|
| The page, the buttons, the preview | `templates/index.html` |
| Upload, folder path, Process, download, preview, log link | `api/jobs.py` |
| The order of every processing step | `services/orchestrator.py` → `process_uploads` |
| Every YAML read | `services/plan_config.py` |
| Action Required paragraphs | `config/action_required.yaml` |
| Excess Return Notice | `config/excess_return_notice.yaml` |
| 415 information and sample letters | `config/failure_letters.yaml` |
| Excess Summary | `config/excess_summary.yaml` |
| Year End Recap / Important Information | `config/year_end_recap.yaml` |
| 403(b) differences | `config/plan_403b.yaml` |
| 457 Year End Recap | `config/plan_457.yaml` |
| Page order and bookmark titles | `config/package_order.yaml` and `services/file_order.py` |
| Compliance Testing Summary line meanings | `config/compliance_summary.yaml` |
| Keep or remove decision | `services/rules_engine.py` → `evaluate` |
| Deleting a paragraph or filling a dollar amount | `services/pdf_modifier.py` |
| Why the heading was not found | `pdf_modifier._squash` and `plan_config._action_required_headings` |
| BRF, inner page order, banned wording, package checks | `services/package_polish.py` |
| Cover date, HCE %, 402(g) dates | `services/source_rewrite.py` |
| The facts the rules used | `output/<job id>/profile_debug.json`, written by `services/profile_debug.py` |
| Browser step log | `services/console_trace.py`, checkbox in `index.html` |
| Why Process stopped | `services/assembly_stops.py` → `stop_reasons` |
| Bookmarks | `services/bookmark_service.py` → `add_bookmarks` |
| Social Security number flag | `services/ssn_scan.py` |
| File name `{plan}_{year}-Valuation.pdf` | `services/save_service.py` → `valuation_filename` |
| Outlook draft | `services/outlook_service.py` |
| Assembly log columns | `services/assembly_log.py` → `build_log_row` |
| Reading plan number, dates, pass/fail from the PDF | `services/pdf_extractor.py` → `extract_plan_profile` |
| Reading the valuation log Excel | `services/source_profile.py` → `parse_excel` |
| The object every rule reads | `models/plan_profile.py` → class `PlanProfile` |

Each function in `services/` has a docstring with Purpose, Args, Returns, Raises, Example, and Side effects. Start with the Purpose line, then open the YAML file it names.

---

## 4. Inside Process, in order

`process_uploads` is the function to scroll. The comments in that function are the seven steps below.

**1. Sort the uploads.** PDFs stay in the package. `.xlsx` files are the valuation log and are not merged into the PDF. A separately uploaded Result/Test Summary PDF is read for pass/fail and is still included in the merged PDF. An embedded summary in the Valuation Pkg is not duplicated. Names that start with `~$` are Excel lock files and are skipped. Close Excel if you need that workbook read, and upload `Val Assembly.xlsx`, not the lock file.

**2. Choose the package type, drop BRF when required, then merge.** A 403(b) package keeps the BRF file. A 401(k) package drops it. If every file was a BRF report, Process stops. Auto-order uses `combine_order` in `config/package_order.yaml`. Files named Loc 1 sort before Loc 2 inside the same section. `SHMaVar` is Compensation Limit, not normal variance. Unknown names sort last. If Auto-order is off, the list on screen is the order. `pdf_assembler.merge_pdfs` rejects an encrypted PDF and an empty file.

**3. Read the plan, then let Excel and the summary override it.** `extract_plan_profile` fills a `PlanProfile`. Patterns live in `config/field_patterns.py`. Summary values are applied first for pass/fail. Excel then overlays identity, plan type, method, and HCE fields. The cover letter wins for 401(k) versus 403(b) versus 457 when `plan_family` can read it. Top heavy is true only when the percent is greater than 60. 60 is not top heavy. A missing plan number does not stop the run by itself. The saved name uses the word UNKNOWN.

**4. Check the profile and decide keep or remove.** `review_service.validate` checks the cover facts and the stamp. `rules_engine.evaluate` calls `plan_config.rules_for` and returns one keep, remove, or skipped decision per rule. The PDF is unchanged at this moment. The Keep / remove tab is this list. The same list is written into `profile_debug.json`.

**5. Edit the PDF.** `apply_decisions` removes an Action Required paragraph, an Excess Return Notice, a sample letter, or the Excess Summary whose rule said remove. `apply_recap_bullets` does the same for Year End Recap bullets. `fill_qnec_placeholders` types the QNEC and refund amounts. Then the code removes banned wording, drops 401(k) BRF pages, rewrites dates, builds the compliance overview, and renumbers footers.

The cover letter date is set to today on every Process. 402(g) dates are rewritten on every Process when the plan year does not end on 31 December. The checkbox **Retype 402(g) dates and HCE %** adds the HCE percent rewrite. If that box is unchecked, HCE percent is not recalculated.

**6. Bookmarks, SSN scan, and assembly stops.** Sections are detected again because pages may have been deleted. `add_bookmarks` replaces the outline. `scan_ssns` looks for `XXX-XX-XXXX` and ignores an EIN. A hit is a failed check. The digits are not removed. If Assembly stops is checked and `stop_reasons` returns anything, Process raises HTTP 400 and does not save the PDF. The checkbox is on by default. Leave it on for UAT.

**7. Save.** `save_package` writes `output/<job id>/<plan number>_<beginning year>-Valuation.pdf`. If the source path is a Valuation Package folder, a second copy is written in the parent Testing folder. `write_draft` writes `<same name>.eml` beside the PDF. Nothing is sent. `assembly_log.append_row` appends one row to `output/ValAssemblyLog.xlsx`.

The Notes area is the `warnings` list: what was removed, what was kept, how many bookmarks, and the email subject.

---

## 5. The screen, and the request behind each control

| Control | Request | Code |
|---|---|---|
| Show files, after a folder path | `GET /api/folder?path=...` | `list_source_folder` |
| After you drop files, before Process | `POST /api/inspect` | `inspect_uploads` returns page counts and keyword rank |
| Auto-order | form field `auto_order` | default true |
| Retype 402(g) dates and HCE % | form field `rewrite_sources` | default false. Cover date still changes when this is off. |
| Assembly stops | form field `check_assembly_stops` | default true |
| Log assembly steps in the browser console | form field `log_steps` | default false. See section 9. |
| Process package | `POST /api/jobs` | `create_job` |
| Preview | page images from `GET /api/jobs/{id}/pages/{n}` | not an iframe of the PDF |
| Download PDF | `GET /api/jobs/{id}/pdf` | the saved file, without preview highlights |
| Assembly log link | `GET /api/jobs/{id}/log` | `download_assembly_log` |
| Email draft link | `GET /api/jobs/{id}/email` | `download_job_email` |

Preview is a column of page images. Double-click a line to edit it in place. Enter calls `POST /api/jobs/{id}/edit` with `shift_line_down`. The toolbar can move a page earlier or later, rotate, undo, download, and zoom. **Highlight changes** draws rectangles on the preview copy. Download reads the saved file and does not paint those rectangles.

Highlight rectangles are also stored in `highlights.json` next to the PDF so a preview can be rebuilt after the in-memory job is gone, as long as you still have the job id.

---

## 6. Plan Profile — the one object the rules use

Class `PlanProfile` in `models/plan_profile.py`. If the question is “how does it know the plan failed ADP?”, the answer is this object, not a second read of the PDF at rule time.

| Field | Meaning |
|---|---|
| `plan_number`, `plan_name`, `company_name`, `company_address` | Cover, unless the Result Summary or Excel overlay replaced them |
| `plan_year_start`, `plan_year_end`, `beginning_plan_year` | The file name uses `beginning_plan_year` only |
| `plan_type` | `401k`, `403b`, or `457`. Bookmarks and YAML overlays use this |
| `testing_method` | `PRIOR` or `CURRENT` |
| `adp_failed`, `acp_failed`, `fail_402g`, `fail_415` | True, false, or unknown (`None`) |
| `fail_402g_after_deadline` | The 15 April note was found |
| `returns_required`, `returns_already_processed`, `adp_reclassified` | Whether a letter or notice should stay |
| `after_12_months` | Chooses the after-12-month wording |
| `top_heavy_percent`, `top_heavy` | Percent, and true only when the percent is greater than 60 |
| `hce_current`, `hce_future` | From the PDF, the Excel log, or a report file name |
| `variance_report`, `contributions_required` | Variance paragraph and contributions paragraph |
| `adp_qnec`, `acp_qnec`, `deferral_refund`, `match_refund`, `total_qnec` | Amounts typed onto the notice |
| `safe_harbor`, `catchup_disallowed`, `special_catchup_disallowed`, `per_payroll_match` | Recap bullets |
| `detected_sections` | Section name and page, used for bookmarks |
| `moa_logo_found`, `mentions_moa` | Stamp check |

`field_sources` inside `profile.extra` says where each filled field came from: PDF text, Excel, Result Summary, or a file name. Read that before you assume the PDF was wrong.

---

## 7. Config files — one file per page

All YAML is read in `services/plan_config.py`. Callers do not open the files themselves.

| File | Edit this when |
|---|---|
| `config/action_required.yaml` | An Action Required paragraph should stay or go, or its heading text changed. The `403b` list replaces B, C, D, and E. |
| `config/excess_return_notice.yaml` | The Excess Return Notice (rule I, and the after-12 notices D and E) |
| `config/failure_letters.yaml` | The 415 information page and the sample letters (J_ADP, J_ACP, K, L) |
| `config/excess_summary.yaml` | The Excess Summary (ES) |
| `config/year_end_recap.yaml` | A Year End Recap bullet (Y1–Y9). Y9 is a match with no rule. |
| `config/plan_403b.yaml` | 403(b) package flags, bookmark titles, and rules I, J_ADP, Y10 |
| `config/plan_457.yaml` | 457 package flags and Year End Recap Y11–Y13 |
| `config/package_order.yaml` | Page order (`combine_order`) or a bookmark title |
| `config/compliance_summary.yaml` | What a Compliance Testing Summary line means |
| `config/field_patterns.py` | A plan number or a pass/fail line is printed in a new shape |
| `config/settings.py` | Port, output folder, upload size limit |

`rules_for` builds the rule list in this order: Action Required A–M, then the page files (I, J_ADP, J_ACP, K, L, ES, Y1–Y8), then the 403(b) or 457 extras. A 403(b) rule replaces the same id from the page file.

`paragraphs_for` is the heading text the remover searches for. Action Required headings from both the 401(k) list and the 403(b) list are searched, so a 401(k) package can still find an ACP heading and a 403(b) package can still find an ADP/ACP heading.

### Action Required

Each entry has `id`, `section`, `keep_when`, `else: remove`, and `headings`. The `section` text is what the Keep / remove tab shows.

| Id | Section name | Kept when |
|---|---|---|
| A | Compliance test failure | Returns required, and 402(g) or 415 failed, and not past the 15 April note |
| B | ADP/ACP test failure, prior year | PRIOR, returns required, ADP or ACP failed, not reclassified. 403(b) section: ACP test failure, prior year |
| C | ADP/ACP test failure, current year, unless QNEC | CURRENT, returns required, ADP or ACP failed, not reclassified. 403(b) uses the ACP wording |
| D | Action Required and Excess Return Notice, after 12 months, current year | CURRENT and after 12 months. The same id also removes the after-12 notice |
| E | Action Required and Excess Return Notice, after 12 months, prior year | PRIOR and after 12 months. Same id on the notice |
| F | Top heavy | `top_heavy` is true. Two headings: IMMEDIATE ACTION REQUIRED and ATTENTION REQUIRED |
| G | No immediate action | Nothing else required action |
| H | Variance | A variance report is present |
| M | Contributions | Contributions are required |

Action Required rules set `missing: remove`. If a fact the rule needs is still `None`, the paragraph is removed. The code does not leave it because it is unsure.

Rules on the other pages do not do that. If a Year End Recap fact is missing, that rule is **skipped** and the bullet stays. Age-50 catch-up (Y6) and the 403(b) 15-year catch-up (Y10) stay unless Excel says catch-up is disallowed. A note such as “catch-up not allowed” is what sets `catchup_disallowed`. An empty Excel cell does not.

### Other keep / remove pages

| Id | Page | File |
|---|---|---|
| I | Excess Return Notice, current year, within 12 months | `excess_return_notice.yaml`. PRIOR within 12 months does not get this notice |
| J_ADP, J_ACP | Sample letters | `failure_letters.yaml` |
| K | 402(g) letter | `failure_letters.yaml`. The Compliance Testing Summary line “402(g) deferral limits tested” is a different page and stays |
| L | 415 information and sample letter | `failure_letters.yaml` |
| ES | Excess Summary | `excess_summary.yaml` |
| Y1–Y8 | Year End Recap bullets | `year_end_recap.yaml` |
| Y10 | 403(b) 15-year catch-up | `plan_403b.yaml` |
| Y11–Y13 | 457 recap bullets | `plan_457.yaml` |

Compensation Limit has no Action Required rule. The file can be in the package. The log column Failed Comp Limit is always N/A.

### Heading match

`pdf_modifier._squash` keeps only letters and digits. A dash, an en dash, a middle dot, or a hyphen inserted by a line break still matches the heading in the YAML. If a paragraph is still on the page, open `profile_debug.json` and look at `source_matches` for that rule. An empty list means the heading text was not found. A non-empty list means the heading was found and the keep/remove decision is the reason it stayed.

---

## 8. How to debug one UAT package

Do this before changing a rule.

1. Restart Python if the last change was a `.py` or `.yaml` file. Refresh the browser if the last change was `index.html`.
2. Process the same files with Assembly stops left on.
3. Open the **Keep / remove** tab. Each row is one rule: keep, remove, or skipped, plus the reason.
4. Open the **Notes** tab. It names the paragraph ids that were removed and the ids that were retained.
5. Open `output/<job id>/profile_debug.json`. The file on disk is the second write, `phase` `after_business_rule_edits`. The decisions in it are the decisions made before the PDF was edited. Use these fields:
   - `plan_type`, `testing_method`, `adp_failed`, `acp_failed`, `returns_required`, `after_12_months`, `top_heavy`
   - `section_decisions`: `rule_id`, `section`, `action`, `reason`, `skipped`, `source_matches`
   - `field` sources are on the job JSON under `plan_profile.extra.field_sources`
6. If Assembly stops, the page shows `Assembly stopped.` and the reason. No PDF is saved. The newest folder under `output/` can still contain `profile_debug.json`, because that file is written before the stop.

| What the client sees | What to check |
|---|---|
| A paragraph that should be gone is still there | Keep / remove for that id. `keep` means the facts matched `keep_when`. `skipped` means a non-Action-Required fact was missing, so the text was left. Empty `source_matches` means the heading on the PDF does not match the YAML even after squashing. |
| A paragraph that should stay was removed | The Action Required rule’s `missing: remove` path. A `None` fact removes it. Fill that fact from Excel or the summary, or change `keep_when` only if the business rule is wrong. |
| After-12 wording is gone, and so is the within-12 ADP paragraph | That is two different ids. D and E remove the after-12 Action Required block and the after-12 notice. They do not remove the within-12 paragraph C or notice I. |
| “402(g)” still appears after the letter was removed | Rule K removes the sample letter. The Compliance Testing Summary line stays. |
| Catch-up bullet stayed on a plan that does not allow catch-up | Y6 or Y10 was skipped. Excel did not say catch-up is disallowed, so `catchup_disallowed` is still `None`. |
| 403(b) package still has ADP wording, or a 401(k) package missed an ACP heading | `plan_type` in the debug file. 403(b) replaces B, C, D, E and rewrites ADP mentions. Both families’ Action Required headings are searched. |
| Process stopped | The message is the list from `assembly_stops.stop_reasons`: an SSN, unresolved “Plan is/is not” or “Pass/Fail” on the Result Summary, a missing report, Excel versus cover name or address or year end, or page order. |
| Wrong page order | Auto-order and `config/package_order.yaml`. A second order check runs after editing when Assembly stops is on. |
| Cover date is today even though the retype box was off | Expected. Cover date is rewritten on every Process. The checkbox is the HCE percent rewrite. |
| Preview edit did not move the line | The edit response must include `shifted`. Restart Python after a change to `api/jobs.py`. Refresh after a change to `index.html`. |
| Nothing in the browser console | The log checkbox is off by default. Check it, Process again, and open the browser console. The Python window does not print those steps. |
| `BadZipFile` or the Excel was ignored | A `~$` lock file was included. Close Excel and use `Val Assembly.xlsx`. The app skips `~$` names, but a test that globs every `*.xlsx` will still open the lock file. |

Sample packages to compare with a client result:

| Folder | Plan | Expected keep / remove |
|---|---|---|
| `sample-data/401k/pass` | Harbor 555001, CURRENT, tests pass | Action Required keeps G only. Year End Recap keeps Y3. Failure paragraphs, notices, and letters are removed. Y6 stays because catch-up is not marked disallowed. |
| `sample-data/401k/current-fail` | Northwind 555002, ADP and ACP fail, QNEC 185354.75 | Keeps C, notice I, and letters J_ADP and J_ACP. Prior-year, after-12, compliance-failure, and G are removed. |
| `sample-data/403b/pass` | Grace 555403 | Keeps G. Y10 stays unless Excel disallows the 15-year catch-up. BRF stays. There is no ADP report and no 410(b) report file. |
| `sample-data/401k/scenarios/unresolved-summary` | Summary still says Plan is/is not or Pass/Fail | Assembly stops. |
| `sample-data/401k/scenarios/masked-ssn` | Census has a masked SSN | Assembly stops. |

Upload every PDF in `input-pdfs/` plus `input-excel/Val Assembly.xlsx`. Saved names are `555001_2025-Valuation.pdf`, `555002_2025-Valuation.pdf`, and `555403_2025-Valuation.pdf`.

---

## 9. Logging

The checkbox **Log assembly steps in the browser console** is off by default.

When it is off, `create_job` calls `process_uploads` directly. Nothing is written to the Python window for those steps, and the browser console stays quiet.

When it is on, the page sends a `trace_id` and polls `GET /api/console-traces/{id}`. `console_trace.run_traced` records one step for each function that `process_uploads` calls directly. Nested helpers are not listed. PDF text and Social Security numbers are not logged. The events show up in the browser console as collapsed groups. The Python window is not written.

Turn it on for one UAT package when you need the order of calls. Turn it off for a normal run. The step recorder is `sys.setprofile`, so leave it off when you care about processing time.

Restart Python after a change to `console_trace.py` or `api/jobs.py`. An old process still traces even when the checkbox is off.

---

## 10. The assembly log

`assembly_log.build_log_row` fills one row. Headers are row 1. Row 2 column E says “Allocation Completed”. Data starts at row 3.

| Column | Value |
|---|---|
| Omni Plan Number, Plan Name | Result Summary text if that page was found, otherwise the Plan Profile |
| Future HCE | Yes if the Excel future-HCE answer is Yes or the Future HCE report lists a person. No if the answer is No |
| Current-year HCE | Same idea, from the current-HCE answer and the HCE/Key report |
| Allocation | Annual-Var if the note says annual allocation and true-up were both done. Annual if the note says annual allocation only. Variance with a cell note `0.00 variance` if the note says true-up and no variance. Variance if allocation was Yes and the note is not more specific. Blank if allocation was not Yes |
| ADP/ACP, 402(g), 410(b), ABP, 414(s), 401(a)(4), 415, BRF | F if that test failed. P if it passed. N/A if the plan does not have that test. Either ADP or ACP failing is F |
| Top Heavy | Yes or No from “Plan is / is not Top Heavy”, or from the profile |
| Failed Comp Limit | N/A |
| FIS, related plans, MEP, safe harbor | Blank. The client sheet says the tester fills these |

This file is not the Testing Log. The Testing Log is the shared workbook where a person types their name before anyone starts. There is no code that opens that workbook.

---

## 11. Bookmarks

`add_bookmarks` builds a table of contents and calls `doc.set_toc`. Titles come from `config/package_order.yaml`, with 403(b) title overrides from `plan_config.bookmark_overrides`. Page numbers are the pages after removals.

A 403(b) plan uses **HCE** and **ACP Test**, and it keeps BRF. A 401(k) package omits BRF. A 401(k) file named like an ADP-only report becomes **ADP Test**. A file that is both ADP and ACP becomes **ADP/ACP Tests**. A cover line such as `ADP Test: Fail` does not by itself create the ADP bookmark. A real ADP heading or an ADP file name does.

---

## 12. What you should not claim

| Topic | The honest sentence |
|---|---|
| Testing Log | We do not write the reviewer’s name into the shared testing workbook. |
| Email | We write a draft. We do not send it. |
| Plan number | A missing plan number does not stop the run. The file name uses UNKNOWN. |
| Non-PDF | Word and pictures are rejected. Excel is read only when it is the valuation log. It is not converted into a PDF page. |
| Scanned PDF | If the page is only a picture, extraction finds nothing. The merge still happens. Rules, bookmarks, the file name, and the log stay empty. |
| Other company names | The stamp check can pass and another company name can still be on the cover. That second look is visual. |
| Three compliance pages | We count them and flag a different count. We do not create the missing pages. |
| Variance page layout | We report name order, font size, zeroes, and text at the edge. We do not retype that page. |
| Tester log columns | FIS, related plans, MEP, and safe harbor are left blank on purpose. |
| Highlights | They exist on the preview. Download reads the saved file. |
| Terminal log | Assembly steps are not printed in the Python window. Use the browser checkbox. |
| Social Security numbers | A found number stops the run when Assembly stops is on. The digits are not deleted. Do not put a real SSN in sample data. |

---

## 13. Tests

Run from `new-app` with the virtual environment active:

```bash
.venv/bin/python -m pytest -q
```

The 401(k) pass sample fails if Excel has `sample-data/401k/pass/input-excel/~$Val Assembly.xlsx` open, because that lock file is not a workbook. Close Excel, or run the other tests. Do not delete the lock file while Excel has the workbook open.

| If they ask | Open |
|---|---|
| Action Required keep / remove, including a heading with a odd dash | `tests/test_action_required_blocks.py` |
| Full sample packages | `tests/test_assembly_pipeline.py` and `tests/test_assembly_requirements.py` |
| Bookmarks | `tests/test_bookmark_service.py` |
| Browser step log | `tests/test_console_trace.py` |
| Preview edit, page move, history | `tests/test_preview_editing.py` and `tests/test_preview_features.py` |
| Inspect before Process | `tests/test_upload_inspection.py` |

---

## 14. A short path through the code

1. The page is one HTML file. Process posts to `/api/jobs`.
2. `create_job` calls `process_uploads`. That function is the whole pipeline. The numbered comments are the seven steps.
3. We merge first, then read a Plan Profile. Rules look only at that object.
4. `plan_config.rules_for` loads the page YAML files. `rules_engine.evaluate` returns keep, remove, or skipped. `pdf_modifier.py` is what changes the PDF.
5. `output/<job id>/profile_debug.json` is the file to open when a client package disagrees with the rule.
6. We save the named PDF, an `.eml` draft, and one log row. We do not send mail, and we do not sign the Testing Log.

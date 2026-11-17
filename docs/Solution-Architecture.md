# Solution Document — Automating the Valuation Package Process

**Product:** MOA Valuation Package Automation  
**Audience:** delivery, architecture review, and client handover  
**Updated:** 24 October 2026  
**Requirements:** the requirements document (MOA Val Package Assembly and 401(k) Editing/Review), including the updated instructions and the assembly-log column sheet

The requirements document describes the **manual** process a reviewer follows in Adobe and Excel. This application automates that process on the reviewer’s computer. This document maps each manual step to what the application does, and states what the reviewer still does by hand.

---

## 1. The problem (manual process)

A reviewer assembles a Mutual of America Valuation Package for a plan year by hand:

1. Claim the plan on the Testing Log by entering their name, so others know it is being worked. That shared workbook is separate from the Val Assembly Log written after the package is finished.
2. Open the plan folder on `K:\Mutual of America\<Plan Number>\Testing\…\Valuation Package`.
3. Confirm every source file is a PDF. If it is not, convert it or send it back to the tester.
4. In Adobe, choose Combine Files, add every PDF, drag files into the required order, and remove pages that should not ship. Location files stay together (Contribution Analysis Loc 1, then Loc 2).
5. Combine into one PDF. Move individual pages with thumbnails if needed, including the inner order of ADP/ACP, 410(b), and a component Average Benefit Percentage test.
6. Save as `{PlanNumber}_{BeginningPlanYear}-Valuation.pdf` in the Testing folder. The year is the **start** of the plan year (for example 10/01/2017–09/30/2018 is 2017).
7. Review the package against the requirements:
   - Cover must show the Mutual of America stamp, and company, address, plan name, and plan year end must match the plan. The cover letter date must be today’s date.
   - Keep or remove Action Required paragraphs (compliance failure, PRIOR vs CURRENT ADP/ACP, after 12 months, variance, top heavy when the percent is greater than 60, “no immediate action”).
   - Keep or remove ADP/ACP failure notices and type the QNEC and refund amounts from the correction page. If only ADP or only ACP failed, drop the unused QNEC line.
   - Remove 415 failure information and the 415 sample letter if the plan did not fail 415.
   - Remove ADP/ACP and 402(g) sample letters when returns are not required (including 402(g) not processed by 15 April).
   - Keep Excess Summary only for non-ADP/ACP failures, or an ADP/ACP failure for a partially vested participant.
   - Keep or remove Year End Recap / Important Information bullets from the testing method, HCE, Safe Harbor, top heavy, and match rules.
   - Leave the BRF result on the Result Summary. A 401(k) package does not include a BRF report. A 403(b) package keeps the BRF report.
   - Do not include audited wording, Statement of Contribution, 5500 wording, or escalation wording.
   - Include the three Compliance and Administrative Report pages.
   - Check the Result Summary against the test reports, and check the client variance copy.
   - Add bookmarks with the required titles (HCE vs HCE/Key, ADP Test vs ACP Test vs ADP/ACP Tests). Variance is not bookmarked.
8. Email the tester. The subject must start with MOA, then plan number, plan name, and plan year end.
9. Update the Val Assembly Log in the client column sheet: plan number, plan name, future and current HCE, allocation, pass/fail, and top heavy. FIS, related plans, MEP, and safe harbor are filled by the tester.

That work is slow, easy to order wrong, and easy to leave the wrong paragraph in the package.

---

## 2. The solution

The application runs on the reviewer’s PC. The reviewer uploads the Valuation Package PDFs (or pastes the folder path) and, when they have it, the valuation package log Excel. The application combines the PDFs, applies the keep/remove rules, fills amounts, adds bookmarks, runs the package checks, and writes the named PDF, an email draft, and a log row in the client columns. Every Process sets the cover letter date to today and rewrites off-calendar 402(g) dates. If the reviewer checks **Retype 402(g) dates and HCE %**, it also rewrites the prior-year HCE percentage. **Assembly stops** is on by default and refuses to save a package that fails a required check.

The reviewer then checks the result, sends the email, and finishes any step the application does not own (listed in §4).

```
Manual today                         Application
────────────────────────             ────────────────────────────────
Adobe Combine + drag order    →      Upload or folder path, auto-order,
                                     including Loc 1 then Loc 2
Delete unneeded pages         →      Keep/remove rules edit the PDF.
                                     BRF report and disallowed wording
                                     are removed
Type QNEC and refund amounts  →      Amounts filled from the profile
Add bookmarks by hand         →      Bookmarks written from remaining
                                     sections. A 401(k) package does not
                                     bookmark BRF. A 403(b) package does
Save ######_YYYY-Valuation    →      Same filename, beginning plan year
Write the email               →      Outlook draft (.eml), reviewer sends it
Update the assembly log       →      One row in the client columns
Cover date and off-calendar   →      Every Process. The checkbox adds the
402(g) dates                         prior-year HCE % rewrite
Assembly stops                →      On by default. A failed check does
                                     not save the PDF
```

---

## 3. Manual step → what the application does

| Manual step in the requirements | What the application does |
|---|---|
| Open the Valuation Package folder and add the PDFs | Upload files, or paste the folder path. The application reads PDFs and the valuation package log Excel from that path. |
| Put reports in the required order | Auto-order matches filenames to section keywords (for example Valuation Pkg, ResultSumm, HCEKey, ADP, 402, Census). Location files stay with that report, Loc 1 before Loc 2. The reviewer can still move rows Up/Down or Remove. |
| Inner page order | Pages whose headings match are reordered: ADP/ACP as Summary, Detail, Excluded, Corrections; 410(b) as Detail, Excludable, Includable, Summary; a component Average Benefit Percentage test as Average Benefit Percentage, 401a1 Comp, Gateway, Overall Comp, Rate Group, then Sum Comp. |
| A multi-page cover / package that holds several front sections | A multi-page cover is split into separate rows named Cover Letter, Action required page 1–3, the excess notices, the failure letters, Year End Recap, and Compliance Report 1–3, so those pages can be reordered. |
| Remove files or pages that do not belong | Rules decide keep or remove for Action Required, notices, sample letters, Excess Summary, and recap bullets. A 401(k) BRF report is left out. A 403(b) BRF report stays. Audited wording, Statement of Contribution, 5500 wording, and escalation wording are removed. A 457 package keeps Statement of Contribution wording. |
| Cover: Mutual of America stamp; company, address, plan name, plan year end | Extracted into a Plan Profile and shown on the Checks tab, including the upper-right stamp. |
| Cover letter date is today | Every Process sets the cover letter date to today. If no letter date is found, the date stays as printed and the Notes say so. |
| Result Summary matches the test reports | The Checks tab compares top-heavy percent (including 0.00% and Plan is / is not Top Heavy) and pass/fail for 410(b), 401(a)(4), 414(s), 402(g), 415, ADP, and ACP. A failed 410(b) also looks for the Average Benefit Percentage wording. |
| Action Required paragraphs (failure, PRIOR, CURRENT, after 12 months, variance, top heavy, no action) | Kept or removed from the Plan Profile (testing method, returns, ADP/ACP, 402(g), 415, top heavy only when the percent is greater than 60, variance, contributions). A missing Action Required fact removes that paragraph. PRIOR / CURRENT, future HCE, current HCE, and the allocation answer are read from the valuation package log Excel when that file is uploaded. A 403(b) package uses the ACP wording for the prior-year, current-year, and after-12-month paragraphs. |
| Compensation Limit Failure Summary has no special Action Required wording | The file can be included in order. The application does not add a special Action Required paragraph for it. On the assembly log, Failed Comp Limit is always N/A. |
| CURRENT ADP/ACP notice: type total QNEC, ADP QNEC, ACP QNEC | Placeholders are filled. If only ADP or only ACP has a QNEC, the other line is removed. |
| After 12 months CURRENT: QNEC plus deferral and match refunds | Filled when those amounts are present. A missing amount drops that line. |
| After 12 months PRIOR: refunds only, no QNEC sentence | Refund lines are filled. PRIOR does not keep the within-12 CURRENT notice. |
| 415 failure information and 415 letter | Removed when the plan did not fail 415. |
| ADP and ACP sample letters | Each letter stays only if that test failed and returns are required. |
| 402(g) sample letter | Removed if there are no 402(g) returns, or the report notes the failure was not processed by 15 April. |
| Excess Summary | Kept for 402(g) or 415, or for ADP/ACP when a participant is partially vested. Plan number, plan name, and plan year end on the excess notice are checked. |
| Client variance copy | Checked for plan number, plan name, plan year end, Social Security numbers, zeroes shown as 0.00, one font size, names in Last, First order, and text at the page edge. The application flags problems. It does not retype the variance page. |
| Year End Recap bullets | Kept or removed from HCE, PRIOR/CURRENT, Safe Harbor, top heavy, catch-up, and per-payroll match. A missing recap fact leaves that bullet in the package. Age-50 catch-up stays unless Excel says catch-up is not allowed. A 403(b) package also has the 15-year catch-up bullet. A 457 package uses its own recap bullets. |
| BRF | The Result Summary line can remain. A 401(k) BRF report file or page is left out and is not bookmarked. A 403(b) package keeps the BRF report and bookmarks it. |
| Compliance reports | Included when the file is in the package. The Checks tab expects three Compliance and Administrative Report pages and flags a different count. Missing pages are not created. |
| Plan identity on each report | Plan number and plan name are checked on each report page. |
| Bookmarks | Created for sections that remain, with the required titles, including HCE and ACP Test for 403(b), and ADP Test / ACP Test / ADP/ACP Tests for 401(k). A 401(k) package does not bookmark BRF. A 403(b) package bookmarks BRF. The variance report is not bookmarked. |
| Save `{PlanNumber}_{BeginningPlanYear}-Valuation.pdf` | Same name. Off-calendar plans use the beginning year from the cover. If the source path is a Valuation Package folder, a copy is also written to the Testing folder when that path can be written. |
| Email the tester | An Outlook draft is written. Subject starts with MOA, then plan number, plan name, and plan year end. The reviewer sends it. |
| Update the Val Assembly Log | A row is appended in the client columns. Plan number and plan name come from the Result Summary. Future HCE and current-year HCE are Yes or No. Allocation is Variance, Annual, or Annual-Var. A true-up with no variance is Variance, with a cell note of 0.00 variance. ADP/ACP, 402(g), 410(b), ABP, 414(s), 401(a)(4), 415, and BRF are P, F, or N/A. Either ADP or ACP failing is F. A test the plan does not have is N/A. Top Heavy is Yes or No. Failed Comp Limit is N/A. FIS, related plans, MEP, and safe harbor are left blank for the tester. |
| Prior-year HCE percentage | Only when the reviewer checks **Retype 402(g) dates and HCE %**. Calculated only when the testing method is PRIOR and an NHCE % is on the package: under 2% → ×2; 2% to 7.99% → +2; 8% or more → ×1.25. A CURRENT plan is left as printed. The box is off by default. |
| 402(g) dates on an off-calendar plan | Every Process. An off-calendar plan year is rewritten to the calendar year before the plan year end, and only on a page that contains 402(g). A calendar plan (year ending 31 December) is left as printed. The saved filename still uses the beginning plan year from the cover. |
| A package that fails a required check | **Assembly stops** is on by default. Process does not save the PDF when it finds a Social Security number, unresolved “Plan is/is not” or “Pass/Fail” wording on the Result Summary, a missing required report, a mismatch between Excel and the cover, or pages out of the required order. The reason is shown on the page. |
| See what was rewritten | Preview has **Highlight changes**, on by default. Yellow marks sit on the rewritten words. Uncheck it for a plain preview. The downloaded PDF never includes the marks. |

---

## 4. What the reviewer still does

These steps stay manual because they are outside the PDF package, or they are a visual check the rules do not finish.

| Manual step | Why it stays manual |
|---|---|
| Enter your name on the Testing Log to claim the plan | This is the shared testing workbook (for example the 2023 testing log and the off-calendar testing log, on the assembly tab). The application does not open those workbooks, does not know which year’s file or which row to update, and does not have the reviewer’s name. The Val Assembly Log written at the end is a different file and does not claim the plan. |
| Convert a non-PDF to PDF, or send it back to the tester | A folder load skips a non-PDF and warns. Dropping a file that is not a PDF or the valuation Excel stops Process. A scanned PDF that is only a picture cannot be read, so rules, bookmarks, the filename, and the log stay empty. |
| Confirm no other company name appears besides Mutual of America | The stamp check is automated. Other names on the cover are still a visual check. |
| Send the email | The application prepares the draft. The reviewer sends it. |
| Fill FIS, related plans, MEP, and safe harbor on the assembly log | Those columns are left blank because the client sheet says the tester updates them. |
| Retype a client variance page that fails the check | The Checks tab reports name order, font size, zeroes, and cut-off text. It does not rebuild that page. |

The cover letter date is set to today on every Process, and off-calendar 402(g) dates are rewritten on every Process. The prior-year HCE % is rewritten only when the reviewer checks **Retype 402(g) dates and HCE %**. That box is off by default. If the package has no matching date or percentage, those lines stay as printed and the Notes say so.

---

## 5. How the application is built

The reviewer uses a browser on the same PC. There is no separate server and no database.

```
Browser (upload, order, preview, checks)
        │
        ▼
Application API  (http://127.0.0.1:8002)
        │
        ▼
Pipeline: order → merge PDFs → reorder inner pages
          → read plan facts (PDF + valuation log Excel)
          → apply rules → edit PDF
          → drop a 401(k) BRF report
          → remove disallowed wording
          → cover date and off-calendar 402(g) dates
          → optional prior-year HCE %
          → checks → bookmarks
          → stop if a required check fails
          → save PDF, email draft, assembly log
        │
        ▼
Files on disk (and optional K: Testing folder)
```

**Plan Profile** is the single set of facts every rule uses: plan number, names, dates, 401(k) vs 403(b) vs 457, CURRENT vs PRIOR, pass/fail, QNEC and refund amounts, top heavy, HCE, allocation notes, and whether returns are required. Rules do not re-read the PDF to decide keep or remove. The assembly log and the Checks tab do read the finished pages so the Result Summary, variance copy, and log values can be compared with what was printed. Each run also writes `profile_debug.json` next to the job, with the facts and the keep or remove decision for every rule.

Keep/remove text lives in one configuration file per page: Action Required, the Excess Return Notice, the failure letters, the Excess Summary, and the Year End Recap. A 403(b) or 457 plan then replaces the rules that differ. Page order and bookmark titles live in the package-order file. Those files can be adjusted without rewriting the pipeline. `services/plan_config.py` is the only code that reads them.

**Outputs**

- `{PlanNumber}_{BeginningPlanYear}-Valuation.pdf`
- Outlook `.eml` draft beside that PDF
- `ValAssemblyLog.xlsx` under the output folder (`MOA_OUTPUT_DIR`, or the application output folder), using the client column sheet

**On a client PC:** Python 3.11 or newer is installed. Run `run.bat`. The first run creates the virtual environment, installs the PDF and Excel libraries from the internet once, and opens http://127.0.0.1:8002. Leave that window open while the reviewer works.

Preview shows the finished package as page images. **Highlight changes** is on by default and marks rewritten words. The downloaded PDF does not include those marks. The reviewer can correct a line, move a page, or rotate a page in the preview before downloading. An optional checkbox writes the assembly steps to the browser console. It is off by default, and the Python window does not print those steps.

---

## 6. Processing sequence

1. Reviewer selects PDFs and the valuation package log Excel, or a Valuation Package folder.
2. The application lists files in requirement order, keeps location files together, and splits a multi-page cover into named pages. A BRF report file is left off the list.
3. Reviewer confirms order (or moves rows). Leaves **Assembly stops** checked. Optionally checks **Retype 402(g) dates and HCE %**, then clicks Process.
4. PDFs are merged. Inner ADP/ACP, 410(b), and component benefit-test pages are reordered when their headings match. Excel and a compliance testing summary, if present, fill the Plan Profile. A separately uploaded summary is included. An embedded summary is not duplicated.
5. Keep/remove is applied, amounts are filled, empty pages are dropped, a 401(k) BRF report and disallowed wording are removed, and the cover date and off-calendar 402(g) dates are rewritten. If the HCE box was checked, the prior-year HCE % is rewritten where the printed text matches. SSNs are flagged if found.
6. Checks run for the Result Summary, the three compliance pages, the client variance copy, and plan identity on the reports. Bookmarks are added. If Assembly stops is on and a required check fails, Process stops and does not save the PDF.
7. Otherwise the named PDF, email draft, and assembly-log row are written. The reviewer previews (with **Highlight changes** on or off) and downloads the clean PDF, then sends the draft and fills the tester columns on the log.

---

## 7. What to say in the review

The requirements document is the manual Adobe and Excel procedure. The application automates combine, order, inner-page order, keep/remove, amount fill, bookmarks, the package checks, the valuation filename, the email draft, and the assembly log in the client columns. Every Process sets the cover letter date to today and rewrites off-calendar 402(g) dates. When the reviewer checks **Retype 402(g) dates and HCE %**, it also rewrites the prior-year HCE percentage. Preview can highlight those words. The downloaded file does not. Assembly stops, which is on by default, does not save a package that fails a required check.

The reviewer still claims the plan on the Testing Log, sends the email, fills the tester columns on the assembly log, and checks any line that was left as printed.

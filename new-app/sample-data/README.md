# Sample valuation packages

Fictional 401(k) and 403(b) files for the MOA valuation-package app. Every person, company, and dollar amount is made up. There are no real Social Security numbers.

The PDFs in `expected-output/` were produced by `process_uploads` with Assembly stops turned on. They are not hand-drawn stand-ins. `run-result.json` in each of those folders is the record of that run. Regenerating the inputs and running the app again will rewrite the outputs, and the cover date will change to the day you run it.

The scanned files in `docs/drive-download-20261004T100241Z-1-001` were used as the visual reference. Those PDFs are images, so the samples below are text the app can extract.

## How to run a package

1. Start the app with `python main.py` and open `http://127.0.0.1:8002`.
2. Check **Assembly stops**. The three complete packages were processed with that box on.
3. Upload every PDF in the scenario's `input-pdfs/` folder and `input-excel/Val Assembly.xlsx` together.
4. The saved file is `{plan number}_{beginning year}-Valuation.pdf`.

To rebuild the inputs and run them through the app from this folder:

```bash
.venv/bin/python sample-data/build_samples.py
```

## Folders

| Folder | What it is |
| --- | --- |
| `401k/pass` | Harbor Manufacturing. Tests pass. No refunds. |
| `401k/current-fail` | Northwind Logistics. Current-year ADP and ACP fail, refunds required, within 12 months. |
| `403b/pass` | Grace Medical Home. ACP passes. No ADP report and no 410(b) report file. |
| `401k/scenarios/unresolved-summary` | Result Summary still says "Plan is/is not" and "Pass/Fail". |
| `401k/scenarios/masked-ssn` | Census contains a masked SSN. |

`input-pdfs` and `input-excel` are what you upload. `expected-output` is what the app wrote: the valuation PDF, the email draft, the assembly log, and `run-result.json`. A job subfolder next to the PDF is the directory the app saved during that run.

## Upload contents

The valuation packet is one multi-page PDF whose name contains `Valuation Pkg`. Report filenames use the keyword the app matches, and that keyword is the longest token in the name. Do not add `401k` or `403b` to a report filename. `401k` is longer than `ADP`, `402`, `410`, `415`, and `TH`, so the report would be filed as the wrong section.

### 401(k) pass — plan 555001

Required uploads:

- `555001 2025 401k Valuation Pkg.pdf` — cover, Action Required, both after-12 notices, the within-12 notice, the 415 information page, the three sample letters, and the year-end recap
- `555001 2025 ResultSumm.pdf`
- `555001 2025 HCEKey.pdf`
- `555001 2025 FYHCE.pdf` — plan year end `12/31/2026`
- `555001 2025 ADP.pdf` — summary, detail, and corrections
- `555001 2025 410.pdf`
- `555001 2025 402.pdf`
- `555001 2025 415.pdf`
- `555001 2025 TH.pdf`
- `555001 2025 Census.pdf`
- `555001 2025 Contri.pdf`
- `555001 2025 401a4.pdf`, `414s.pdf`, and `ABPT.pdf` — passing extra tests, included because the summary mentions them
- `Val Assembly.xlsx`

Not included, because this plan has no true-up and no variance note: MaVar, SHMaVar, PSVar, SHNEVar.

### 401(k) current fail — plan 555002

Same report set as the pass package, without 401(a)(4), 414(s), and ABPT. The ADP corrections page has both QNEC lines and both refund lines. The summary says ADP and ACP failed, refunds are required, and the correction is within 12 months.

### 403(b) pass — plan 555403

Same front matter, with ACP headings and Form W-4P on the current-method paragraphs. Reports are HCE/Key, Future HCE, `ACP Test.pdf` (not an ADP file), 402(g), 415, Top Heavy, Census, Contribution Analysis, and BRF. There is no 410(b) report file. The summary still has resolved 410(b) Standard, 401(k), and 401(m) lines because the contribution page says "employer contribution" and the app asks for those lines whenever that wording is present.

## Excel and cover

`Val Assembly.xlsx` uses the workbook the app reads. Row 1 is the header, row 2 is the values, and rows 6–13 are the yes/no questions.

| Field | Harbor 555001 | Northwind 555002 | Grace 555403 |
| --- | --- | --- | --- |
| Plan name | HARBOR MANUFACTURING 401(K) PLAN | NORTHWIND LOGISTICS 401(K) PLAN | GRACE MEDICAL HOME, INC. 403(B) PLAN |
| Company | HARBOR MANUFACTURING, LLC | NORTHWIND LOGISTICS, LLC | GRACE MEDICAL HOME, INC. |
| Address | 10 Harbor Way, Suite 200, Boston, MA 02110 | 400 Warehouse Road, Chicago, IL 60601 | 88 Chapel Street, Orlando, FL 32801 |
| Plan type | 401(k) | 401(k) | 403(b) |
| Plan year end | 12/31/2025 | 12/31/2025 | 12/31/2025 |
| Beginning year | 2025 | 2025 | 2025 |
| Testing method | CURRENT | CURRENT | CURRENT |
| Safe harbor | No | No | No |
| HCE current / future | Yes / Yes | Yes / Yes | Yes / Yes |
| Top heavy | No (report 8.85%, not top heavy) | No (report 12.40%, not top heavy) | 403b N/A (summary 5.00%, not top heavy) |
| Per-payroll match | Yes | Yes | No |
| Reclassified | No | No | No |
| Annual allocation | No | No | No |
| Rework / Rush | No / No | No / No | No / No |

The cover `RE:` line, company, address, and plan year end are the same strings as the Excel cells. The printed letter date is September 9, 2026. The app rewrites it to the processing date. In the generated outputs that date is October 21, 2026.

## What the app produced

Assembly stops were on. All three complete packages saved. The two scenario uploads stopped.

| Package | Saved file | Email subject | Pages |
| --- | --- | --- | --- |
| 401(k) pass | `555001_2025-Valuation.pdf` | MOA - 555001 - HARBOR MANUFACTURING 401(K) PLAN - PYE 12/31/2025 | 21 |
| 401(k) current fail | `555002_2025-Valuation.pdf` | MOA - 555002 - NORTHWIND LOGISTICS 401(K) PLAN - PYE 12/31/2025 | 20 |
| 403(b) pass | `555403_2025-Valuation.pdf` | MOA - 555403 - GRACE MEDICAL HOME, INC. 403(B) PLAN - PYE 12/31/2025 | 16 |

### 401(k) pass

Removed: compliance failure, both ADP/ACP failure paragraphs, contributions, after-12 paragraphs, top-heavy attention, both after-12 notices, the within-12 notice, the 415 information page, and the 402(g), 415, and ADP/ACP letters.

Kept: the green "NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME" line. Recap kept the current-year HCE rate bullet, the catch-up bullet, the per-payroll match bullet, and the Mutual of America boilerplate. It removed the no-HCE bullet, the prior-year bullet, the safe-harbor bullet, the "HCE this year but not next year" bullet, and the top-heavy bullet.

The app added the three Compliance and Administrative Reports pages. They sit after the recap and before the test reports.

Page order in the saved PDF: cover, action page, year-end recap, three overview pages, Result Summary, HCE/Key, Future HCE, ADP/ACP summary, detail, corrections, 410(b), 402(g), Contribution Analysis, Top Heavy, 415, Census, 401(a)(4), Average Benefit Percentage Test, 414(s).

### 401(k) current fail

Kept: the current-method "unless QNEC" paragraph, the within-12 Excess Return Notice, and the combined ADP/ACP sample letter.

Removed: the compliance paragraph, the prior-method paragraph, contributions, both after-12 paragraphs and notices, the green line, the top-heavy attention line, and the 402(g) and 415 letters.

QNEC from the corrections page: ADP `$142,540.41`, ACP `$42,814.34`, total `$185,354.75`. Deferral refund `$17,571.00`. Match refund `$116.60`. The app log says `Filled Excess Return Notice QNEC amounts: total=$185,354.75, adp=$142,540.41, acp=$42,814.34`. Those amounts are drawn on the notice. A plain text extract often lists them at the end of the page rather than inside the sentence.

### 403(b) pass

Plan type stayed 403(b). Bookmarks use **HCE** and **ACP Test**, and the BRF report is kept. There is no 410(b) report in the file.

Kept: the green line, the current-year rate bullet, catch-up, and the 403(b) special catch-up sentence ("fifteen or more years of service"). The per-payroll match bullet was removed because that Excel answer is No. ADP/ACP failure paragraphs, notices, and letters were removed.

### Scenarios that stop

With Assembly stops on:

- `unresolved-summary` stops with: The Result Summary still has unresolved wording such as "Plan is/is not" or "Pass/Fail".
- `masked-ssn` stops with: A full or masked Social Security number was found on page(s) 1.

Neither scenario writes a valuation PDF.

## Review result that does not stop the package

Each complete package has one failed review item, `package_order`. The checker compares the order in which section names are first detected with the keyword order. Detection uses the first page that contains an alias, so a short alias such as `TH` matches ordinary words like "the" on an earlier page. Bookmarks are written from that same detection, so a bookmark title can be right while its page is the first mention rather than the report itself. The 403(b) titles are HCE, ACP Test, and Benefits, Rights and Features test. The saved PDF page order listed above is the order the files were merged. Assembly stops did not treat this as a stop.

## Limits

- MaVar, SHMaVar, PSVar, and SHNEVar are not in these packages. Add one only when you want the contributions / variance path. Set Annual allocation to Yes, or put a variance note in the Excel notes cell, and include the variance PDF.
- The app does not read a separate census workbook. Census is the PDF section.
- A 403(b) package does not have to include a 410(b) report. It does have to include resolved 410(b) Standard, 401(k), and 401(m) summary lines if any page says "match", "profit sharing", "safe harbor", "QNEC", or "employer contribution".
- The reference scans have no text layer. These samples follow the headings and fields the application extracts. They are not a pixel copy of every scanned page.
- The cover-date rewrite reported two replacements, and a text extract of the cover can show the plan-year start as `01/1/2025`. The profile still stores plan year end `12/31/2025`.
- The email To line is blank. The draft is the `.eml` file in the job folder.

## Code change made while checking these files

Summary alignment was reading the auto-inserted compliance overview as if it were the Top Heavy report, so every package looked like the report said 60%. `services/package_polish.py` now skips overview pages in that report lookup, the same way assembly stops and the identity check already skip them. After that change, the Top Heavy percent on each sample summary matches its Top Heavy report.

One existing test expected the phrase "Actual Contribution Percentage (ACP)" to disappear from the whole PDF when the ADP/ACP letter is removed. That phrase also appears in the overview description. The test now ignores overview pages. The letter itself is still required to be gone.

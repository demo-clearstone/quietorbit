# Application Progress Report

**Product:** MOA Valuation Package Automation  
**Date:** 24 October 2026  
**For:** Manager review  
**Compared with:** the requirements document (manual assembly and 401(k) review), including the updated instructions and the assembly-log column sheet

The requirements document is the manual process (Adobe combine, keep/remove, amounts, bookmarks, save, email, assembly log). This report shows how much of that process the application now does.

---

## Overall

| | |
|---|---|
| **Application progress** | **88%** |
| Requirement items scored | 24 |
| Done | 20 |
| Partial | 2 |
| Not done | 2 |

**How the percentage is calculated**

Each requirement item is scored Done = 100, Partial = 50, Not done = 0.  
(20 × 100) + (2 × 50) + (2 × 0) = 2,100.  
2,100 ÷ 24 = 87.5%, reported as **88%**.

This is up from **83%** on 1 October. Two items moved to Done:

- Inner pages of ADP/ACP, 410(b), and a component Average Benefit Percentage test are reordered when the page headings match.
- The Val Assembly Log is filled in the columns from the client log sheet (plan number, plan name, HCE, allocation, pass/fail, top heavy).

Claiming the plan on the Testing Log, converting non-PDFs, and sending the live email stay in the 24 so the percentage is the full reviewer job, not only the PDF editing.

---

## By area

| Area | Progress | Meaning |
|---|---|---|
| Collect files and combine | 100% | Upload or folder path, merge, keyword order, location order, named save |
| Keep / remove and amounts | 100% | Action Required, notices, letters, Excess Summary, recap, QNEC and refunds. A 401(k) BRF report is left out. A 403(b) BRF report stays. Audited, 5500, and escalation wording are removed. A 457 package keeps the Statement of Contribution |
| Bookmarks and cover checks | 88% | Bookmarks, cover fields, and the cover-date check are done. “Only Mutual of America” is still partly visual |
| Dates and HCE % on the pages | 100% | Every Process sets the cover date to today and rewrites off-calendar 402(g) dates. The prior-year HCE % changes only when “Retype 402(g) dates and HCE %” is checked. Preview can highlight those spots. The download stays clean |
| Email and assembly log | 75% | The log row is written in the client columns. The email is still a draft the reviewer sends |
| Steps outside the PDF | 33% | Inner test pages are ordered from headings. The Testing Log and non-PDF conversion are not done |

---

## Item scores

| # | Requirement | Status | Score |
|---|---|---|---|
| 1 | Open the Valuation Package (upload or folder path) | Done | 100 |
| 2 | Combine the PDFs into one package | Done | 100 |
| 3 | Put reports in the required order, including location files (Loc 1, Loc 2) | Done | 100 |
| 4 | Split a multi-page cover into named pages for reorder | Done | 100 |
| 5 | Save `{Plan number}_{Beginning plan year}-Valuation.pdf` | Done | 100 |
| 6 | Off-calendar year uses the plan start year | Done | 100 |
| 7 | Keep or remove Action Required paragraphs | Done | 100 |
| 8 | CURRENT / PRIOR and after-12-month notices | Done | 100 |
| 9 | Fill QNEC and refund amounts; drop an unused ADP or ACP line | Done | 100 |
| 10 | ADP and ACP sample letters | Done | 100 |
| 11 | 402(g) letter, including the 15 April rule | Done | 100 |
| 12 | 415 failure information and 415 letter | Done | 100 |
| 13 | Excess Summary (including partially vested ADP/ACP) | Done | 100 |
| 14 | Year End Recap bullets | Done | 100 |
| 15 | Bookmarks, including 403(b) HCE and ADP Test / ACP Test. A 401(k) BRF report is not bookmarked. A 403(b) BRF report is kept and bookmarked | Done | 100 |
| 16 | Cover company, address, plan name, and plan year end | Done | 100 |
| 17 | Mutual of America is the only entity on the cover | Partial | 50 |
| 18 | Reorder inner ADP/ACP, 410(b), and component benefit-test pages | Done | 100 |
| 19 | Cover letter date is today’s date, set on every Process | Done | 100 |
| 20 | Email the tester | Partial | 50 |
| 21 | Update the Val Assembly Log in the client column sheet | Done | 100 |
| 22 | Claim the plan on the Testing Log | Not done | 0 |
| 23 | Convert non-PDF files to PDF | Not done | 0 |
| 24 | Prior-year HCE % when the box is checked, and off-calendar 402(g) dates on every Process | Done | 100 |

Partial items:

- **Only Mutual of America:** the stamp check is automated. Other company names are still a visual check.
- **Email:** an Outlook draft is created with the required subject. The reviewer still sends it.

Done since the last report:

- **Inner pages.** When the headings are on the page, ADP/ACP is ordered Summary, Detail, Excluded, Corrections. 410(b) is ordered Detail, Excludable, Includable, Summary. A component Average Benefit Percentage test is ordered Average Benefit Percentage, 401a1 Comp, Gateway, Overall Comp, Rate Group, then Sum Comp.
- **BRF.** A 401(k) BRF report file or page is left out and is not bookmarked. The Result Summary line stays. A 403(b) package keeps the BRF report and bookmarks it.
- **Wording MOA packages do not use.** Audited wording, Statement of Contribution, 5500 wording, and escalation wording are removed. A 457 package keeps the Statement of Contribution.
- **Valuation package log Excel.** PRIOR YEAR / CURRENT YEAR sets the testing method. Future HCE, current HCE, and the allocation answer are read. Annual allocation Yes, or a note that says include contributions, keeps the contributions wording.
- **Cover date.** Every Process sets the cover letter date to today. If no letter date is found, it stays as printed and the Notes say so.
- **Prior-year HCE %** uses the table (under 2% → ×2; 2% to 7.99% → +2; 8% or more → ×1.25), and only when **Retype 402(g) dates and HCE %** is checked, the testing method is PRIOR, and an NHCE % is on the package. That box is off by default.
- **402(g) dates** are rewritten on every Process, only on an off-calendar plan, and only when those plan-year dates are printed on a 402(g) page.
- **Highlight changes** on the preview stays optional. Yellow marks show the rewritten words. Download PDF never includes the marks.
- **Checks.** Result Summary top-heavy percent (including 0.00% and Plan is / is not Top Heavy; top heavy only when the percent is greater than 60) and pass/fail for 410(b), 401(a)(4), 414(s), 402(g), 415, ADP, and ACP. A failed 410(b) also looks for the Average Benefit Percentage wording. The three Compliance and Administrative Report pages are flagged if they are missing; they are not created. The client variance copy is checked for plan identity, Social Security numbers, 0.00 zeroes, one font size, Last-First name order, and text at the page edge. Plan number and plan name are checked on each report, and plan year end on the excess notice. **Assembly stops** is on by default. A failed required check does not save the PDF, the email draft, or the log.
- **Val Assembly Log.** One row is appended in the client columns: Omni Plan Number and Plan Name from the Result Summary; Future HCE and current-year HCE as Yes or No; allocation as Variance, Annual, or Annual-Var (a true-up with no variance is Variance, with a cell note of 0.00 variance); ADP/ACP, 402(g), 410(b), ABP, 414(s), 401(a)(4), 415, and BRF as P, F, or N/A; Top Heavy as Yes or No; Failed Comp Limit always N/A. FIS, related plans, MEP, and safe harbor are left blank for the tester.

Not done:

- **Claiming the plan on the Testing Log.** This is the shared workbook a reviewer opens before assembly and types their name into, so other people can see that plan is already being worked. The requirements point at files such as the 2023 testing log and the off-calendar testing log, on the assembly tab under the testing folders. The application does not open those shared workbooks. It does not know which year’s log or which row is the plan being picked up, and it does not have the reviewer’s name to write into that sheet. The Val Assembly Log that Process writes is a separate file. That one records the finished package. Filling it does not claim the plan.
- **Converting Word, Excel, or image files into PDF.** A folder load skips a non-PDF and warns. Dropping a file that is not a PDF or the valuation Excel stops Process. Scanned PDFs that are only pictures also cannot be read, so rules, bookmarks, the filename, and the log stay empty on those packages.

---

## What is ready to show

- Upload PDFs or a Valuation Package folder path.
- Auto-order, location order, and a reorder list.
- Process: keep/remove, filled amounts, bookmarks, a 401(k) BRF report left out, a 403(b) BRF report kept, and disallowed wording removed.
- Cover date and off-calendar 402(g) dates on every Process. Prior-year HCE % only when **Retype 402(g) dates and HCE %** is checked.
- Preview with optional highlights on the rewritten words, and a download of the named valuation PDF without those highlights.
- Checks for the Result Summary, the three compliance pages, the client variance copy, and plan identity on the reports. Assembly stops blocks the save when a required check fails.
- Outlook draft and an assembly-log row in the client columns.

---

## What to say if asked “is it finished?”

The application covers the manual PDF assembly and review rules at about **98%** of those editing steps (19 of 20 PDF items are done; one is partial).  
Across the **whole** reviewer job in the requirements, progress is **88%** (was 83% on 1 October).

The remaining work is a visual check for other company names on the cover, sending the email, claiming the plan on the Testing Log, and converting non-PDF files. The cover date is set on every Process. If no letter date, HCE percentage, or 402(g) date is found, that line stays as printed and the Notes say so.

# Valuation package requirements and implementation

This is the record of the assembly rules requested for the MOA valuation package, and how the app carries them out.

The finished file is `{plan number}_{beginning year}-Valuation.pdf`, for example `900062_2025-Valuation.pdf`. When the source folder is the plan’s Valuation Package folder, a copy is also saved in the plan Testing folder above it.

Check **Assembly stops** before Process when a bad address, name, Social Security number, Result Summary line, plan year end, or missing report must stop the package. With that box checked, the PDF, email draft, and log are not written until the issue is corrected.

## File name and order

Files are recognized by keyword and combined in this order: Cover Letter, Result Summary, the cover-packet pages (Action Required through the three compliance overview pages), then HCE/Key, Future HCE, ADP/ACP, 410(b), variance files, 402(g), Contribution Analysis, Top Heavy, 415, Census, 401(a)(4), Average Benefit Percentage, and 414(s).

Location files stay inside their test. Contribution Analysis Loc 1 comes before Contribution Analysis Loc 2. The same ordering applies to the other tests.

A control group is not combined by the app. The tester puts the plan name on those tests before upload. The app then checks that the plan name and plan number agree with the rest of the package.

## Cover letter

The cover keeps the Mutual of America stamp at the upper right. The company name, address, RE plan name, and plan year end are checked against the valuation package Excel. The letter date is rewritten to today, with no leading zero on the day.

The employer address must have line 1 and city, state, and ZIP. Line 2 is optional. A PO Box counts as line 1, so `PO BOX 7174` and `EDMOND, OK 73083` are a complete address. A missing street, city, state, or ZIP stops assembly.

Sample: `output/soboba-cover-letter.pdf`.

## Compliance Testing Summary

The summary drives the later pages. Top heavy percentage must match the Top Heavy report. `0%` is shown as `0.00%`. More than 60% means the plan is top heavy. Exactly `60.00%` is not top heavy.

410(b) lines mean: Standard is profit sharing and SHNE, 401(k) is salary deferral and Roth, and 401(m) is match and safe harbor match. If the plan has contributions other than deferrals and Roth, those 410(b) lines must be on the summary. A failed 410(b) with a passed average benefits test keeps the sentence “Average Benefits Test Passed; no action needed for Failed 410(b) Coverage Test”.

The BRF result stays on the summary. A 401(k) package does not include a BRF report. A 403(b) package may keep it.

401(a)(4), 414(s), 402(g), 415(c), ADP, and ACP on the summary must match their reports. An unresolved “Pass/Fail” or “Plan is/is not” stops assembly.

Sample: `output/our-house-compliance-summary.pdf`.

## Action Required

Pages follow package pages 2, 3, and 4.

- 402(g) or 415 failed, and a return is still required: keep the compliance-failure paragraph. A 402(g) failure that missed the April 15 deadline does not keep that paragraph unless 415 also failed.
- ADP or ACP failed, returns are required, and the returns were not all reclassified: keep the prior-year or current-year paragraph. Current-year wording includes “unless QNEC”. Prior-year wording does not.
- After 12 months, both the within-12 paragraph and the after-12 correction paragraph stay.
- A true-up, an annual allocation, a log note to include contribution wording, or a variance client copy keeps the contributions paragraph.
- Top heavy above 60% keeps the top-heavy paragraph.
- If none of those apply, the page keeps only the green line “NO IMMEDIATE ACTION IS REQUIRED AT THIS TIME”.
- After a paragraph is removed, the remaining text packs up. A page left with only the heading is removed.

Sample: `output/annual-valuation-action-required.pdf`.

## Excess return notices and QNEC amounts

Current-year testing after 12 months keeps the current Excess Return Notice. Prior-year testing after 12 months keeps the prior notice. The other notice is removed.

The first QNEC amount is the ADP QNEC plus the ACP QNEC. The next line is the ADP QNEC. The line after that is the ACP QNEC. If only one test fails, the missing line is dropped and the first amount is the single QNEC. Amounts are read from the ADP/ACP correction page.

The within-12 current notice is kept only for current-year testing when returns are still required. Prior-year testing before 12 months does not keep that notice.

One-to-one wording uses the deferral refund and the match refund. A missing match refund removes only the match clause.

These notices use Form W-4R. A 403(b) notice still uses Form W-4P.

Samples: `output/excess-return-notices.pdf`, `output/current-failure-notice.pdf`.

## 415 information and sample letters

These follow package pages 8 through 11.

| Page | Kept when |
| --- | --- |
| Annual Additions (IRC 415) Test Failure Information | The plan failed 415 |
| ADP/ACP sample letter | ADP or ACP failed and a return is required |
| 402(g) sample letter | A 402(g) return is required, and the failure was processed by April 15 |
| 415 sample letter | The plan failed 415 |

A page left with only its heading is removed.

Sample: `output/failure-letters.pdf`.

## Year End Recap

The Important Information page follows package page 12. One ADP/ACP bullet stays:

- No Highly Compensated Employees this year and none next year: the plan is not subject to ADP/ACP testing.
- Prior-year testing: the prior-year rate bullet. The NHCE percentage is read from the ADP test (“The ADP for the 65 NHCE(s) is 2.21%”). The HCE maximum is twice that rate when it is under 2%, the rate plus 2 points from 2% up to 8%, and 1.25 times the rate at 8% and above. 2.21% becomes 4.21%.
- Current-year testing: the current-year rate bullet.
- Safe Harbor, or a plan switching to Safe Harbor next year: the Safe Harbor bullet.

The ADP/ACP Test Results page decides the method. “ADP TEST USING PRIOR YEAR NHCE PERCENTAGES” means prior-year testing. A results page without that wording is current-year testing.

The other bullets:

- Highly Compensated Employees this year and none next year keeps that bullet.
- Catch-up stays unless the plan does not allow catch-up contributions.
- Top heavy stays when the plan is top heavy.
- The Mutual of America combined-testing bullet always stays.
- The per-payroll match bullet stays only when the match is calculated each payroll.

Sample: `output/year-end-recap.pdf`.

## Compliance overview and bookmarks

Every 401(k) and 403(b) package includes the three Compliance and Administrative Reports pages, laid out like package pages 13, 14, and 15. Those pages describe the reports. They do not count as the reports themselves. A mid-year package and a 457 package do not add these three pages.

After assembly, existing bookmarks are cleared and these titles are written from the first page forward:

Cover Letter, Test Summary, Contribution Analysis, HCE/Key for a 401(k) or HCE for a 403(b), Future HCE, then the ADP/ACP bookmark. A 401(k) with both tests uses ADP/ACP Tests, with Summary, Detail, and Corrections under it in that order. A 401(k) with ADP only uses ADP Test. A 403(b) uses ACP Test. Then 402(g) Test, 410(b) Test, 401(a)(4) Test, Average Benefit Percentage Test, and 414(s) Test when those reports are in the package, then 415 Limit Test, Top Heavy, and Census.

The variance report does not get a bookmark.

On an off-calendar plan, the 402(g) report uses the calendar year before the plan year end. A plan year ending 06/30/2026 is dated 01/01/2025–12/31/2025 on that report.

Sample: `output/compliance-overview.pdf`.

## Wording an MOA package does not keep

Audited wording, the Statement of Contribution, 5500 wording, and escalation wording are removed. A 457 package may keep the Statement of Contribution.

The app does not sweep an MOA plan and does not create a workflow task.

## When assembly stops

These run when **Assembly stops** is checked. The package is not saved until the issue is corrected.

- The employer address is missing line 1 or city, state, and ZIP, or it does not match the valuation package log.
- The plan name in the valuation package log does not match the cover letter or the test reports. The email subject uses that same plan name, so the email is not written with a different name.
- The employer name or the plan name differs from one report to another.
- A full or masked Social Security number appears, such as `123-45-6789` or `XXX-XX-1234`.
- The Result Summary still says “Plan is\is not” or “Pass/Fail”.
- A page shows a different plan year end. A Future HCE report may show the next year. An off-calendar 402(g) report may show the prior calendar year.
- A standard 401(k) package is missing one of these reports: valuation package, Result Summary, 402(g), 415, ADP/ACP, 410(b), HCE/Key, Future HCE, Top Heavy, Census, or Contribution Analysis.
- A Safe Harbor plan does not need the ADP/ACP report. A 403(b) package does not need the 410(b) report.
- A variance client copy is required for a true-up or when the summary calls for a variance. A 414(s), 401(a)(4), or average benefit report is required when the summary calls for it.
- The Mutual of America stamp is missing from the upper right of the cover letter.

## After a successful assembly

- The draft email says the valuation package is ready for review. The subject starts with **MOA**, then the plan number, the plan name, and the plan year end. Rush or Rework is added when the Excel checklist says so.
- The Val Assembly log records the date sent back to the tester and the time the build took.
- The file name is `{plan number}_{beginning year}-Valuation.pdf`, saved in the job folder and, when the source folder is known, in the plan Testing folder.

## What still needs a person

- Send the email. The draft subject and body are written, and the To line is left blank for the reviewer.
- Combine a control group and put the plan name on those tests before upload.
- Fill the tester columns on the Val Assembly log: FIS, related plans, MEP, and safe harbor.
- Turn on **Assembly stops** for the stop rules above. With the box off, the package is still built and the problems are reported on the review instead of blocking the save.

# MOA Valuation Package Automation — Software Requirements Document

Use this file as project context for Copilot/Cursor. Implementation lives in `new-app/` and starts at Phase 1.

## 1. Project overview

Automate the Mutual of America (MOA) Valuation Package assembly and review process currently performed manually by reviewers.

The system will:

- Upload valuation package source PDFs
- Assemble PDFs into a single valuation package
- Extract plan information and testing information
- Execute business rules currently performed manually
- Add/remove valuation package sections based on rules
- Generate bookmarks automatically
- Perform review validations
- Save the final package using the naming convention
- Generate a review summary for users

## 2. Technology stack

- Frontend: HTML, CSS, JavaScript (upload, extracted info, validations, download)
- Backend: Python, FastAPI
- PDF: PyMuPDF (`fitz`) — read, extract, search, replace, add text, delete pages, merge, bookmarks
- Excel (later): openpyxl, pandas — Val Assembly Logs, DocInfo.xls
- OCR (later): Azure Document Intelligence, fallback pytesseract

## 3. Frontend workflow

User selects files → upload PDFs → call API → process package → display results → download final package.

## 4. High-level architecture

HTML UI → FastAPI → PDF Assembly → Data Extraction → Plan Profile Builder → Rules Engine → PDF Modification → Bookmark Generator → Validation Engine → Save Package.

All business decisions use the Plan Profile object. Rules return keep/remove JSON before any PDF mutation.

## 5. Folder structure

See the repository `new-app/` tree. One job pipeline (`POST /api/jobs`) orchestrates the services.

## 6. Plan Profile

After extraction, one object contains all plan information (plan number, name, company, address, plan year, testing method, top-heavy, ADP/ACP, 402(g), 415, QNEC amounts, detected sections). Rules must not re-parse raw PDF text.

## 7. File naming

`{PlanNumber}_{BeginningPlanYear}-Valuation.pdf`

Use the beginning plan year only:

- 01/01/2017–12/31/2017 → 2017
- 02/01/2017–01/31/2018 → 2017
- 10/01/2017–09/30/2018 → 2017

## 8. PDF assembly

Merge uploaded PDFs in selected order into one valuation package. Encrypted files are rejected.

## 9. Data extraction

Cover page: plan number, plan name, company name, address, plan year start/end.

Test summary: top-heavy percent, pass/fail, test types, ADP/ACP testing method (CURRENT or PRIOR), QNEC amounts, refunds, 402(g), 415, variance.

Patterns live in `config/field_patterns.py` and must be tuned against real samples.

## 10. Validation engine

- Cover page: plan number, plan name, address, plan year end match source data
- SSN scan: `XXX-XX-XXXX` (9-digit only with extra checks to avoid EIN/plan-number hits)
- Package order: Cover Letter, Compliance Summary, Action Required, Variance, Year End Recap, Important Information, Compliance Reports, Contribution Analysis, Future HCE, ADP/ACP, 402(g), 410(b), 401(a)(4), 415, Top Heavy, Census

## 11. Rules engine (A–G)

Evaluated against Plan Profile only (`config/rules.yaml`):

- A: testing failed AND returns required → keep Compliance Failure Paragraph
- B: ADP/ACP PRIOR + returns required → keep PRIOR wording
- C: ADP/ACP CURRENT + returns required → keep CURRENT wording
- D: CURRENT + correction after 12 months → keep After 12 Months Current wording
- E: PRIOR + correction after 12 months → keep After 12 Months Prior wording
- F: top-heavy percent ≥ 60 → keep Top Heavy wording
- G: no action-required items → keep green No Action message

## 12. ADP/ACP calculation

Total QNEC = ADP QNEC + ACP QNEC. Populate notices in Phase 4.

## 13. PDF modification (Phase 4)

Remove unused sample letters/notices; insert calculated QNEC and refund amounts.

## 14. Bookmarks (Phase 4)

Create TOC from remaining sections with PyMuPDF. Do not bookmark removed sections.

## 15. Review dashboard

Cover page, package order, SSN, top heavy, action required, bookmarks.

## 16. Save final package

Destination (production): `K:\Mutual of America\<Plan Number>\Testing\<YYYY Testing Folder>`  
Dev: `MOA_OUTPUT_DIR` or `new-app/output/`.

## 17. Future enhancements

Outlook draft email (`MOA | Plan Number | Plan Name | PYE`) and Val Assembly Log Excel update.

## 18. MVP phases

- Phase 1: upload, assemble, extract, plan profile, save (current)
- Phase 2: validation engine, SSN scan, package order, cover page
- Phase 3: action required / ADP/ACP / 402(g) / 415 rules (JSON decisions exist; field completeness is the work)
- Phase 4: PDF modification, bookmarks, final package generation

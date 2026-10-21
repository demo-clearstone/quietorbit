# Sample valuation packages

Fictional 401(k) and 403(b) files for the app. Upload every PDF in `input-pdfs/` plus `input-excel/Val Assembly.xlsx`, with Assembly stops checked.

| Folder | Plan | What to expect |
| --- | --- | --- |
| `401k/pass` | 555001 Harbor Manufacturing, PYE 12/31/2025, CURRENT | Tests pass. Saved file `555001_2025-Valuation.pdf`. |
| `401k/current-fail` | 555002 Northwind Logistics | ADP and ACP fail. QNEC total $185,354.75. Saved file `555002_2025-Valuation.pdf`. |
| `403b/pass` | 555403 Grace Medical Home | ACP passes. No ADP report and no 410(b) report file. Saved file `555403_2025-Valuation.pdf`. |
| `401k/scenarios/unresolved-summary` | Result Summary still says Plan is/is not and Pass/Fail | Assembly stops. |
| `401k/scenarios/masked-ssn` | Census has a masked SSN | Assembly stops. |

`expected-output` holds the PDF, email draft, log, and `run-result.json` from the last app run. Rebuild with:

```bash
.venv/bin/python sample-data/build_samples.py
```

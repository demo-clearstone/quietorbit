# MOA Valuation Package Automation

Greenfield app in `new-app/`. It does **not** use the existing POC backend or `pdf-process.py`.

Workflow: upload PDFs and the Val Assembly Excel **or** a Valuation Package folder path → assemble in TEST23 SOP order → extract a Plan Profile → preview keep/remove rules → add bookmarks → save `{PlanNumber}_{BeginningPlanYear}-Valuation.pdf`. Required identity, result-summary, missing-report, SSN, and final-order checks stop saving by default when they fail.

The preview editor supports manual page rotation, reordering, deletion and insertion; crop and page-canvas sizing; text search; bookmark add/rename/delete/validation; undo/redo; text replacement/insertion; notes, stamps, shapes, drawn signatures and highlights; and permanent redaction. Preview edits use a working copy, leaving the assembled original untouched; choose **Save edited copy** to download a separate edited PDF. Search uses the PDF text layer (scanned-image pages need OCR), page-size changes adjust the canvas without scaling the page content, and drawn signatures are visual annotations rather than cryptographic signatures. Assembly-stop checks are enabled by default; keep them on for production assembly. The automated checks do not replace a visual review of the final package.

Developer onboarding (folder map, pipeline, how to change rules): [`docs/Developer-Guide.md`](docs/Developer-Guide.md).  
Solution architecture (for submission / handover): [`docs/Solution-Architecture.md`](docs/Solution-Architecture.md).

## Run

```bash
cd new-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

UI: http://127.0.0.1:8002  
API docs: http://127.0.0.1:8002/docs

## Client PC (Windows, Python already installed)

Do not minify the backend into one pasted file. The app still needs `pip install pymupdf` (a binary wheel).

On a developer Mac/PC:

```bash
cd new-app
python3 scripts/build_dist.py
```

That writes `dist/install_moa.py` — **email that one text file** (no zip).

On the client: save the paste as `install_moa.py`, run `python install_moa.py`, double-click `moa-app\run.bat`, open http://127.0.0.1:8002. The first run uses the network once for pip.

Optional: set `MOA_OUTPUT_DIR` to a Windows path such as `K:\Mutual of America` in production.

## Layout

```
new-app/
  main.py                 FastAPI entry
  api/jobs.py             POST /api/jobs, download PDF
  services/orchestrator.py
  services/pdf_assembler.py
  services/pdf_extractor.py
  services/plan_profile_service.py
  services/rules_engine.py      JSON keep/remove only
  services/review_service.py    cover-field checks
  services/save_service.py
  services/pdf_modifier.py      Phase 4 stub
  services/bookmark_service.py  Phase 4 stub
  models/plan_profile.py
  config/field_patterns.py      extraction regexes
  config/sections.yaml
  config/rules.yaml             rules A–G
  templates/index.html
  output/                       saved packages
```

## Sample PDFs

Upload these from `tests/fixtures/` at http://127.0.0.1:8002

| File | What it tests |
|------|----------------|
| `01_pass_no_action.pdf` | All sections; tests pass; Rule G keep |
| `02_current_fail_qnec.pdf` | CURRENT fail, QNEC, top heavy, after 12 months |
| `03_prior_fail_offcalendar.pdf` | PRIOR fail; plan year 10/01/2017–09/30/2018 → `333333_2017-Valuation.pdf` |
| `assemble-current-fail/*.pdf` | Same as #2 split into source files named like `222222 2024 401k Valuation Pkg.pdf`, `2024ResultSumm.pdf`, `2024Census.pdf` |

Regenerate:

```bash
python tests/fixtures/build_samples.py
```

## Tests

```bash
cd new-app
python -m pytest -q
```

## Next (do not skip)

1. Verify extraction and keep/remove results against each client's actual Testing Log/workbook and PDF package.
2. Run assembly with the default Assembly stops enabled and visually review the final PDF before sending it to the tester.
3. OCR remains necessary for scanned-image-only reports; current extraction is based on selectable PDF text.

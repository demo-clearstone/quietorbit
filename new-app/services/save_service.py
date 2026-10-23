from __future__ import annotations

from pathlib import Path

import fitz

from config.settings import OUTPUT_DIR
from models.plan_profile import PlanProfile


def valuation_filename(profile: PlanProfile) -> str:
    """{PlanNumber}_{BeginningPlanYear}-Valuation.pdf, or the mid-year test name."""
    number = (profile.plan_number or "UNKNOWN").strip()
    year = (profile.beginning_plan_year or "UNKNOWN").strip()
    if profile.midyear:
        return f"{number}_MidYearTesting_2_{year}_{year}-Mid-Year-ADP-Test.pdf"
    return f"{number}_{year}-Valuation.pdf"


def save_package(doc: fitz.Document, job_id: str, profile: PlanProfile, dest_dir: Path | None = None) -> Path:
    """Saving the valuation PDF."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    name = valuation_filename(profile)
    path = job_dir / name
    doc.save(path, garbage=3, deflate=True)
    if dest_dir:
        dest_dir.mkdir(parents=True, exist_ok=True)
        copy = dest_dir / name
        copy.write_bytes(path.read_bytes())
    return path


def testing_folder_from_source(source_folder: str | None) -> Path | None:
    """Save a copy in the YYYY Testing folder (parent of Valuation Package)."""
    if not source_folder:
        return None
    path = Path(source_folder).expanduser()
    if not path.exists():
        return None
    if path.is_file():
        path = path.parent
    if path.name.lower() == "valuation package":
        return path.parent
    return path

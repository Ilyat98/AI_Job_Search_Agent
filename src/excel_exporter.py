"""Create the ranked vacancy workbook requested by the user."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from src.database import PROJECT_ROOT

OUTPUT_PATH = PROJECT_ROOT / "data" / "vacancies.xlsx"

SCORE_FILLS = (
    (0, 50, "F4CCCC"),
    (50, 70, "FFE599"),
    (70, 85, "D9EAD3"),
    (85, 95, "CFE2F3"),
    (95, 101, "D9D2E9"),
)

_CITY_COUNTRIES = {
    "wrocław": "Poland", "wroclaw": "Poland", "warszawa": "Poland",
    "warsaw": "Poland", "kraków": "Poland", "krakow": "Poland",
    "gdańsk": "Poland", "gdansk": "Poland", "poznań": "Poland",
    "poznan": "Poland", "kyiv": "Ukraine", "lviv": "Ukraine",
    "odesa": "Ukraine", "Gdansk": "Poland", "Krakow": "Poland",
    "Poznan": "Poland",
}


def _employment_label(job: dict[str, Any]) -> str:
    title = str(job.get("title") or "")
    job_type = str(job.get("job_type") or "")
    lowered = f"{title} {job_type}".casefold().replace("_", " ")
    description = str(job.get("description") or "").casefold()
    contract_terms = (
        ("B2B", ("b2b", "business-to-business")),
        ("Employment contract", ("umowa o pracę", "umowa o prace")),
        ("Civil-law contract", ("umowa zlecenie", "umowa-zlecenie")),
        ("Employment contract", ("employment contract", "permanent contract")),
        ("Contract", ("contract", "contractor")),
        ("Freelance", ("freelance", "freelancer")),
    )
    contract = None
    for label, terms in contract_terms:
        in_title_or_type = any(term in lowered for term in terms)
        if label == "Contract":
            in_description = bool(re.search(
                r"\b(?:employment|contract) type\s*[:\-]\s*contract\b",
                description,
            ))
        else:
            in_description = any(term in description for term in terms)
        if in_title_or_type or in_description:
            contract = label
            break
    if "full time" in lowered or "full-time" in lowered:
        work_type = "Full-time"
    elif "part time" in lowered or "part-time" in lowered:
        work_type = "Part-time"
    elif "internship" in lowered or "staż" in lowered:
        work_type = "Internship"
    elif "temporary" in lowered or "fixed-term" in lowered:
        work_type = "Temporary"
    else:
        work_type = None
    if contract and work_type and contract.casefold() != work_type.casefold():
        return f"{work_type} · {contract}"
    if contract:
        return contract
    return work_type or "—"


def _location_label(value: str) -> str:
    location = " ".join(value.split()).strip(" ,;–—-")
    if not location:
        return ""
    for marker in ("віддалено", "віддалена", "remote", "zdalnie", "praca zdalna"):
        location = re.sub(re.escape(marker), "", location, flags=re.I)
    location = re.sub(r"\s*[,;|]\s*", ", ", location).strip(" ,;")
    location = " ".join(location.split())
    if not location:
        return ""
    lowered = location.casefold()
    for city, country in _CITY_COUNTRIES.items():
        if city in lowered and country.casefold() not in lowered:
            return f"{location}, {country}"
    return location


def _workplace_label(job: dict[str, Any]) -> str:
    location = _location_label(str(job.get("location") or ""))
    source_mode = str(job.get("work_mode") or "").casefold()
    text = " ".join(str(job.get(key) or "") for key in (
        "location", "title", "description"
    )).casefold()
    remote = ("віддалено", "віддалена", "remote", "zdalnie", "praca zdalna",
              "work from anywhere", "fully remote")
    hybrid = ("hybrid", "гібрид", "hybryd", "hybridowo")
    onsite = ("on-site", "onsite", "in-office", "in office", "stacjonarn",
              "офіс", "офис")
    has_remote = source_mode == "remote" or any(term in text for term in remote)
    has_hybrid = source_mode == "hybrid" or any(term in text for term in hybrid)
    if source_mode == "on-site":
        mode = "On-site"
    elif source_mode == "remote":
        mode = "Remote"
    elif source_mode == "hybrid":
        mode = "Hybrid"
    elif has_remote and has_hybrid:
        mode = "Remote / hybrid"
    elif has_hybrid:
        mode = "Hybrid"
    elif has_remote:
        mode = "Remote"
    elif any(term in text for term in onsite):
        mode = "On-site"
    else:
        mode = "Format not specified"
    return f"{mode} ({location})" if location else mode


def _display_date(value: str | None) -> str:
    if not value:
        return "—"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return parsed.strftime("%Y-%m-%d")


def _write_job_sheet(sheet, jobs: list[dict[str, Any]], *, note: str) -> None:
    sheet.append([
        "Job title", "Link", "Publication date", "Salary",
        "Fit score, %", "Employment / contract type", "Work mode / location",
        "Unconfirmed mandatory requirements", "Recommended CV",
        "Agent decision", "Assessment confidence", "Why it matches",
        "Ollama score, %", "Rule score, %", "Seniority / experience risk",
        "Ollama comment (verify)",
    ])
    header_fill = PatternFill("solid", fgColor="FF24364B")
    for cell in sheet[1]:
        cell.fill = header_fill
        cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    ordered_jobs = sorted(
        jobs,
        key=lambda item: (item.get("fit_score", 0), item.get("published_at") or ""),
        reverse=True,
    )
    for job in ordered_jobs:
        sheet.append([
            job.get("title") or "Untitled vacancy",
            job.get("url") or "",
            _display_date(job.get("published_at")),
            job.get("salary") or "—",
            int(job.get("fit_score") or 0),
            _employment_label(job),
            _workplace_label(job),
            ", ".join(job.get("missing_requirements") or []) or "—",
            job.get("recommended_cv") or "—",
            job.get("report_decision_label") or job.get("ai_decision") or "Not evaluated",
            {"high": "High", "medium": "Medium", "low": "Low"}.get(
                job.get("evaluation_confidence"), "—"
            ),
            job.get("match_explanation") or job.get("ai_summary") or "—",
            job.get("model_score") if job.get("model_score") is not None else "—",
            job.get("rule_score") if job.get("rule_score") is not None else "—",
            "; ".join(job.get("fit_warnings") or []) or "—",
            job.get("model_comment") or "—",
        ])
        row = sheet.max_row
        if job.get("previously_seen"):
            sheet.cell(row=row, column=1).font = Font(color="FFED7D31")
        link_cell = sheet.cell(row=row, column=2)
        if link_cell.value:
            link_cell.hyperlink = link_cell.value
            link_cell.style = "Hyperlink"
        score_cell = sheet.cell(row=row, column=5)
        score_cell.number_format = '0"%"'
        score = int(score_cell.value)
        for lower, upper, color in SCORE_FILLS:
            if lower <= score < upper:
                score_cell.fill = PatternFill("solid", fgColor=f"FF{color}")
                break

    data_end_row = sheet.max_row
    sheet.cell(row=data_end_row + 2, column=1, value=note).font = Font(
        italic=True, color="666666"
    )
    widths = {
        1: 42, 2: 55, 3: 20, 4: 24, 5: 20, 6: 29,
        7: 44, 8: 38, 9: 34, 10: 34, 11: 18, 12: 70,
        13: 20, 14: 20, 15: 42, 16: 70,
    }
    for index, width in widths.items():
        sheet.column_dimensions[get_column_letter(index)].width = width
    for row in sheet.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
    sheet.freeze_panes = "A2"
    table_ref = f"A1:{get_column_letter(len(sheet[1]))}{data_end_row}"
    sheet.auto_filter.ref = table_ref
    sheet.row_dimensions[1].height = 32
    if ordered_jobs:
        table = Table(
            displayName="Vacancies" if sheet.title == "Vacancies" else "ManualReview",
            ref=table_ref,
        )
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2", showFirstColumn=False, showLastColumn=False,
            showRowStripes=True, showColumnStripes=False,
        )
        sheet.add_table(table)


def export_jobs(
    jobs: list[dict[str, Any]],
    *,
    output_path: str | Path = OUTPUT_PATH,
    review_jobs: list[dict[str, Any]] | None = None,
) -> Path:
    """Write recommendations and, optionally, a separate near-miss review sheet."""
    output_path = Path(output_path)
    if not output_path.is_absolute():
        output_path = PROJECT_ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Vacancies"
    _write_job_sheet(
        sheet,
        jobs,
        note=(
            "Sources: DOU (RSS), Remotive (API), JustJoin.it (sitemap). "
            "Percentages are ranking scores, not the probability of getting a job. "
            "Rows marked “Manual Review” are not recommendations."
        ),
    )
    if review_jobs:
        review_sheet = workbook.create_sheet("Manual Review")
        _write_job_sheet(
            review_sheet,
            review_jobs,
            note=(
                "These are near-match candidates for manual review, not recommendations. "
                "Review the requirements and original listing before applying."
            ),
        )

    workbook.save(output_path)
    return output_path

# AI Job Search Agent

A local-first Python application that analyzes one or more CVs, searches configured job sources, ranks vacancies against the candidate profiles, and exports an Excel report.

## How it works

- Extracts structured CV profiles with a local Ollama model.
- Searches DOU, Remotive, and JustJoin.it using configured terms and CV-supported role tracks.
- Combines an Ollama assessment with rule-based checks for skills, required experience, and seniority.
- Saves local search history and profile caches in SQLite and creates an Excel workbook with recommendations and manual-review candidates.
- Does not submit job applications.

Fit scores are ranking aids, not probabilities of getting an interview or an offer. Review the original listing before applying.

## Requirements

- Windows and Python 3.12.
- Ollama running locally, with the model configured in `config/settings.json` downloaded.
- Network access to the enabled vacancy sources.

## Setup

Create a virtual environment and install dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull qwen2.5:3b
```

Create a `CV` folder in the project root and put your `.pdf` or `.docx` CV files there. The `CV` and `data` folders are excluded from Git.

## Run

Analyze CVs and search vacancies:

```powershell
.\.venv\Scripts\python.exe -m src.job_search
```

Force CV profile reanalysis:

```powershell
.\.venv\Scripts\python.exe -m src.job_search --reanalyze
```

Reuse verified CV profiles:

```powershell
.\.venv\Scripts\python.exe -m src.job_search --reuse-profiles
```

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The workbook is written to `data/vacancies.xlsx` by default. Use `--output path\to\report.xlsx` to choose another local output path.

## Configuration and privacy

Edit `config/settings.json` to configure sources, search terms, role tracks, thresholds, and Ollama. Raw CV text is sent to the configured Ollama endpoint during CV analysis. With the default settings, Ollama runs locally. Vacancy evaluation sends structured profile facts.

CVs, generated reports, local databases, IDE settings, environments, and secrets are excluded by `.gitignore`. Never force-add personal documents, reports, databases, or `.env` files.

See [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for implementation details and current limitations.

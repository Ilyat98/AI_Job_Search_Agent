# AI Job Search Agent

## What it does

A local-first Python application that reads one or more CVs, extracts a
structured candidate profile with Ollama, searches configured job sources,
scores listings against the available profiles, stores search history in
SQLite, and exports a formatted Excel report.

The application is a bounded, single-purpose AI agent. Python runs the
approved source adapters and keeps its search state; Python first ranks the
available CV profiles using role evidence, seniority, and explicit required
skills, then local Ollama assesses the strongest profile for each vacancy.
Python adds one bounded second pass of configured role synonyms when the first
pass returns too few plausible matches. It combines model judgment with rule
signals and writes the report. The agent never
applies to jobs or takes actions outside the configured search tools.

## Requirements

- Windows and Python 3.12 (the project has been developed with Python 3.12).
- Ollama installed and running locally for a full CV analysis.
- The model named in `config/settings.json` downloaded in Ollama.
- Network access to the configured job sources.

Install the Python dependencies in a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

With Ollama installed, download the configured model:

```powershell
ollama pull qwen2.5:3b
```

Ollama normally runs as a local service. If it is not already running, start
it in another terminal with `ollama serve`.

## Run it

Put one or more `.pdf` or `.docx` CV files in the local `CV` folder. Then run
from the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m src.job_search
```

This full run reads and analyzes the current CVs, searches enabled sources,
compares each vacancy against the best-ranked CV profile, asks Ollama to assess
that profile, and exports decisions, scores, missing required items, the
recommended CV, and explanations. Job
evaluations are cached by vacancy, profile, model, and prompt version. Later
runs reuse those evaluations unless one of these inputs changes.

To explicitly delete the cached CV profiles and build every profile again:

```powershell
.\.venv\Scripts\python.exe -m src.job_search --reanalyze
```

This clears only the cached CV profile rows. It preserves the original files
in `CV/` and the vacancy/search history in SQLite.

To skip Ollama when every CV is unchanged and has a complete successful cached
profile, use:

```powershell
.\.venv\Scripts\python.exe -m src.job_search --reuse-profiles
```

The reuse mode checks the extracted text against the current CV text. If any
profile is missing, stale, or incomplete, it warns and asks whether to rebuild
all profiles. `yes` clears the CV profile cache and reanalyzes all current
files; `no` stops without changing the cache. Reuse skips CV analysis but
still uses Ollama for uncached vacancy evaluations and, if needed, one
role-synonym search pass. The workbook can be written to a different path with
`--output path\\to\\report.xlsx`.

Run the automated test suite from the project root with:

```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

## Search and report behavior

- CV discovery is configured by `cv.directory` and
  `cv.supported_extensions` in `config/settings.json`.
- Search terms combine configured terms with role phrases inferred from the
current CV experience entries. Role-specific synonyms are enabled only for
tracks supported by a CV's work experience (QA, game design, technical support,
and electronics). The bounded second pass uses configured synonyms rather than
unverified Ollama-generated queries. Search titles remain limited to configured
roles, CV work experience, and those role-family synonyms.
- `job_categories` and `search.minimum_fit_score` control title filtering and
  the minimum score retained in the report.
- The initial search looks back 30 days. Later successful searches look back
  7 days. The timezone is configured under `app.timezone`.
- The Excel sheet contains title, link, publication date, salary, fit score,
  contract/employment type, work format/location, unconfirmed required items,
  recommended CV, agent decision, confidence, explanation, separate Ollama and
  rule scores, seniority warnings, and a clearly attributed Ollama comment.
- Explicit minimum years are compared with dated, role-relevant CV experience.
  Senior/Middle/Lead title mismatches produce a soft warning and score penalty;
  they are not treated as certain rejection without an explicit requirement.
- Salary is shown as `—` when it is unavailable. The score cell is colored by
  score band; previously seen vacancy titles use orange font.
- Listings are deduplicated by normalized URL and their history is stored in
  SQLite. The report is a snapshot of the current search window, not a
  permanent archive of all old vacancies.
- Ollama provides the primary fit judgment (default weight 70%); a
  deterministic score contributes the remaining 30%. The program applies a
  separate configurable penalty for requirements the model or rule catalog
  cannot confirm in that CV's skills or experience. Explicit missing years count
  as required gaps; title-only seniority mismatches are shown as warnings.
  `search.minimum_fit_score` sets the cutoff.
- Python ranks each CV against the role, seniority, experience dates, and
  configured required-skill catalog;
  Ollama assesses the highest-ranked CV in isolation. A strong decision requires
  the configured score threshold and no
  unconfirmed required items. By default, Ollama's `Not a match` decisions are
  kept in SQLite but omitted from Excel; `agent.include_no_match_in_excel`
  can include them. Low-confidence answers are identified in the report.
- The rule catalog in `job_matching.required_skill_aliases` checks common
  mandatory technical terms against each CV and can be extended in settings.
  Ollama returns a compact score, decision, confidence, and summary for the
  selected CV; these results are cached locally.
- Fit scores are ranking aids, not probabilities of getting an interview or
  an offer. Always check the original vacancy before applying.
- To calibrate the score boundary, copy `config/job_feedback_template.csv` to
  `data/job_feedback.csv`. Add a vacancy's `normalized_url`, its `fit_score`
  from Excel, and your label: `apply`, `reject`, or `review`. Calibration starts
  after at least three `apply` and three `reject` labels; `review` rows are not
  used as positive or negative examples. Until then the configured threshold is
  used.

## Vacancy sources

The enabled adapters are configured in `job_sources.enabled`:

- **DOU** — public vacancy RSS search feeds.
- **Remotive** — public remote-jobs API.
- **JustJoin.it** — public active-offer sitemap and job posting metadata. The
  adapter does not call the site's disallowed `/api/` paths.

Search limits, terms, and the JustJoin.it detail-page limit are configurable
in `config/settings.json`. Some sources can return overlapping listings; URL
normalization removes tracking parameters before deduplication. More sources
can be added through an adapter and registered in
`src/job_sources/registry.py`.

The `job_matching` section configures how many points to subtract for each
unconfirmed required item and the editable catalog used as a rule-based
cross-check. The `agent` section limits the single query replan, sets fit
thresholds, controls how Ollama's score is blended with rule signals, and sets
the seniority penalty and feedback CSV path.
Vacancy evaluation limits the description sent to Ollama and requests only a
compact score, decision, confidence, and short summary for the selected CV.
Python checks catalogued mandatory skills separately. `evaluation_max_tokens` sets
the generation ceiling. If a batch omits one CV, only that CV is retried in a
separate request; if that retry also fails, rules score only that CV. Mixed AI
and fallback assessments are not cached. An Ollama connection failure falls
back for the remaining uncached vacancies.

## Configuration

Edit `config/settings.json` to change the timezone, lookback period, score
threshold, CV directory and formats, enabled job sources, search terms, and
Ollama settings.

The `ai` section currently supports local Ollama:

```json
"ai": {
  "provider": "ollama",
  "enabled": true,
  "base_url": "http://localhost:11434",
  "model": "qwen2.5:3b",
  "request_timeout_seconds": 120
}
```

Changing `enabled` to `false` makes a full analysis run stop with a clear
configuration error for a fresh CV analysis. With `--reuse-profiles`, no CV
text extraction is performed. If Ollama is disabled or unavailable, matching
uses still-valid cached job judgments when possible and the deterministic
fallback for uncached jobs; configured role-synonym search remains available.
Raw CV text is sent to
the configured Ollama endpoint during CV analysis. During vacancy evaluation,
the agent sends structured profile facts rather than the full raw CV. With the
default URL both requests go to the local machine, not a hosted AI API.

The `user_preferences` section is intentionally separate from CV facts. Add
only preferences you want enforced or considered, such as preferred roles,
locations, work modes, contract types, or minimum salary; an empty list means
the agent should not assume that preference.

## Project layout

```text
config/settings.json          Search, CV, and Ollama settings
src/cv_parser.py              PDF and DOCX text extraction
src/profile_builder.py        Candidate source record construction
src/ai_profile_extractor.py   Structured CV fact extraction via Ollama
src/cv_service.py             CV processing and profile persistence
src/profile_cache.py          Cached-profile freshness and completeness checks
src/job_evaluator.py          Ollama vacancy judgments and evidence summaries
src/search_planner.py         CV-supported role tracks and bounded search synonyms
src/calibration.py            User-labeled score threshold calibration
src/job_sources/              DOU, Remotive, and JustJoin.it adapters
src/job_matcher.py            Role filtering and explainable fit scoring
src/job_search.py             Command-line end-to-end workflow
src/database.py               SQLite schema, state, and deduplication
                              Cached, fingerprinted Ollama vacancy evaluations
src/excel_exporter.py         Formatted Excel report generation
tests/                        Automated tests and source fixtures
CV/                           Local CVs; excluded from Git
data/                         Local database and reports; excluded from Git
```

## Privacy and GitHub

CV files, extracted CV profiles, SQLite databases, and generated Excel reports
are local user data and must stay out of the public repository. The root
`.gitignore` excludes all of `CV/` and `data/`, as well as local environments,
IDE files, databases, reports, logs, and `.env` files. Create the `CV` folder
locally after cloning and add your own CVs there.

`.gitignore` does not remove a file that was already committed. Review the
staged files before publishing and never commit real CVs, database files, or
personalized reports.

## Current scope and limitations

- The agent is bounded: it makes at most one deterministic query expansion
  and only calls the configured read-only vacancy sources. It does not submit
  applications.
- The local 3B model can misread nuanced requirements or evidence. Low
  confidence is surfaced, but all decisions still need human review.
- Threshold calibration needs user labels. Until there are at least three
  `apply` and three `reject` examples, the configured threshold remains active.
- The AI score depends on Ollama availability. If Ollama fails, the application
  marks the decision as a rule-based fallback.
- Telegram notifications, scheduled runs, and a separate vacancy validation
  service are not currently implemented.
- The app requires reachable job sources; a source outage can make a run
  incomplete. Source errors are printed and the run is not marked fully
  successful.
- The Excel file is regenerated on each run. SQLite keeps the underlying
  vacancy history and CV profiles locally.

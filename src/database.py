
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from contextlib import contextmanager
from collections.abc import Iterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "job_search.db"


def current_timestamp() -> str:
    """Return the current time as an ISO 8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection() -> sqlite3.Connection:
    """Open a connection to the SQLite database."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=10,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection

@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    """Open a database connection and always close it."""
    connection = get_connection()

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    """Create the initial database tables if they do not exist."""

    with db_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                source TEXT NOT NULL,
                source_job_id TEXT,

                url TEXT NOT NULL,
                normalized_url TEXT NOT NULL UNIQUE,

                company TEXT,
                title TEXT NOT NULL,
                description TEXT,
                location TEXT,
                job_type TEXT,
                work_mode TEXT,
                salary TEXT,

                published_at TEXT,
                discovered_at TEXT NOT NULL,
                last_checked_at TEXT,

                status TEXT NOT NULL DEFAULT 'unknown'
                    CHECK (status IN ('active', 'closed', 'unknown')),

                fit_score INTEGER
                    CHECK (
                        fit_score IS NULL
                        OR fit_score BETWEEN 0 AND 100
                    ),

                recommended_cv TEXT,
                match_explanation TEXT,

                missing_requirements TEXT NOT NULL DEFAULT '[]',
                rejection_reason TEXT,
                ai_decision TEXT,
                evaluation_source TEXT,
                evaluation_confidence TEXT,
                evaluation_requirements TEXT NOT NULL DEFAULT '[]',

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,

                UNIQUE (source, source_job_id)
            )
        """)

        job_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
        }
        for column in ("location", "job_type", "work_mode", "salary"):
            if column not in job_columns:
                connection.execute(f"ALTER TABLE jobs ADD COLUMN {column} TEXT")
        for column, definition in {
            "ai_decision": "TEXT",
            "evaluation_source": "TEXT",
            "evaluation_confidence": "TEXT",
            "evaluation_requirements": "TEXT NOT NULL DEFAULT '[]'",
        }.items():
            if column not in job_columns:
                connection.execute(f"ALTER TABLE jobs ADD COLUMN {column} {definition}")

        connection.execute("""
                  CREATE TABLE IF NOT EXISTS cv_profiles (
                      id INTEGER PRIMARY KEY AUTOINCREMENT,
                      source_file TEXT NOT NULL UNIQUE,
                      skills_json TEXT NOT NULL DEFAULT '[]',
                      languages_json TEXT NOT NULL DEFAULT '[]',
                      raw_text TEXT NOT NULL,
                      updated_at TEXT NOT NULL
                  )
              """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS job_fit_evaluations (
                normalized_url TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL,
                evaluation_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        # Add new columns to databases created by earlier versions.
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(cv_profiles)"
            ).fetchall()
        }

        if "job_titles_json" not in columns:
            connection.execute("""
                ALTER TABLE cv_profiles
                ADD COLUMN job_titles_json TEXT NOT NULL DEFAULT '[]'
            """)

        if "sections_json" not in columns:
            connection.execute("""
                ALTER TABLE cv_profiles
                ADD COLUMN sections_json TEXT NOT NULL DEFAULT '{}'
            """)
        if "ai_profile_json" not in columns:
            connection.execute("""
                ALTER TABLE cv_profiles
                ADD COLUMN ai_profile_json TEXT
            """)
        if "ai_status" not in columns:
            connection.execute("""
                ALTER TABLE cv_profiles
                ADD COLUMN ai_status TEXT NOT NULL DEFAULT 'not_processed'
            """)


        now = current_timestamp()

        connection.execute("""
            INSERT OR IGNORE INTO app_state (key, value, updated_at)
            VALUES (?, ?, ?)
        """, ("initial_search_completed", "false", now))

        connection.execute("""
            INSERT OR IGNORE INTO app_state (key, value, updated_at)
            VALUES (?, ?, ?)
        """, ("last_successful_search_at", "", now))


def get_state(key: str, default: str | None = None) -> str | None:
    """Read a value from app_state."""

    with db_connection() as connection:
        row = connection.execute(
            "SELECT value FROM app_state WHERE key = ?",
            (key,),
        ).fetchone()

    if row is None:
        return default

    return str(row["value"])


def set_state(key: str, value: str) -> None:
    """Insert or update a value in app_state."""

    now = current_timestamp()

    with db_connection() as connection:
        connection.execute("""
            INSERT INTO app_state (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
        """, (key, value, now))


def is_initial_search() -> bool:
    """Return True until the first successful search is recorded."""
    return get_state("initial_search_completed", "false") != "true"


def mark_initial_search_completed() -> None:
    """Record that the first search has completed successfully."""
    set_state("initial_search_completed", "true")
    set_state("last_successful_search_at", current_timestamp())


def get_existing_job_urls(normalized_urls: list[str]) -> set[str]:
    """Return URLs already stored before the current search run."""
    urls = list(dict.fromkeys(url for url in normalized_urls if url))
    existing: set[str] = set()
    with db_connection() as connection:
        for start in range(0, len(urls), 900):
            batch = urls[start:start + 900]
            if not batch:
                continue
            placeholders = ",".join("?" for _ in batch)
            rows = connection.execute(
                f"SELECT normalized_url FROM jobs WHERE normalized_url IN ({placeholders})",
                batch,
            ).fetchall()
            existing.update(str(row["normalized_url"]) for row in rows)
    return existing


def save_job(job: dict[str, Any]) -> int:
    """Insert a vacancy or update an existing vacancy by its unique key."""

    now = current_timestamp()

    missing_requirements = job.get("missing_requirements", [])
    if isinstance(missing_requirements, list):
        missing_requirements = json.dumps(
            missing_requirements,
            ensure_ascii=False,
        )
    evaluation_requirements = job.get("evaluation_requirements", [])
    if isinstance(evaluation_requirements, list):
        evaluation_requirements = json.dumps(
            evaluation_requirements,
            ensure_ascii=False,
        )

    values = (
        job["source"],
        job.get("source_job_id"),
        job["url"],
        job["normalized_url"],
        job.get("company"),
        job["title"],
        job.get("description"),
        job.get("location"),
        job.get("job_type"),
        job.get("work_mode"),
        job.get("salary"),
        job.get("published_at"),
        job.get("discovered_at", now),
        job.get("last_checked_at"),
        job.get("status", "unknown"),
        job.get("fit_score"),
        job.get("recommended_cv"),
        job.get("match_explanation"),
        missing_requirements,
        job.get("rejection_reason"),
        job.get("ai_decision"),
        job.get("evaluation_source"),
        job.get("evaluation_confidence"),
        evaluation_requirements,
        now,
        now,
    )

    with db_connection() as connection:
        connection.execute("""
            INSERT INTO jobs (
                source,
                source_job_id,
                url,
                normalized_url,
                company,
                title,
                description,
                location,
                job_type,
                work_mode,
                salary,
                published_at,
                discovered_at,
                last_checked_at,
                status,
                fit_score,
                recommended_cv,
                match_explanation,
                missing_requirements,
                rejection_reason,
                ai_decision,
                evaluation_source,
                evaluation_confidence,
                evaluation_requirements,
                created_at,
                updated_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT DO UPDATE SET
                url = excluded.url,
                company = COALESCE(excluded.company, jobs.company),
                title = excluded.title,
                description = COALESCE(
                    excluded.description, jobs.description
                ),
                location = COALESCE(excluded.location, jobs.location),
                job_type = COALESCE(excluded.job_type, jobs.job_type),
                work_mode = COALESCE(excluded.work_mode, jobs.work_mode),
                salary = COALESCE(excluded.salary, jobs.salary),
                published_at = COALESCE(
                    excluded.published_at, jobs.published_at
                ),
                last_checked_at = COALESCE(
                    excluded.last_checked_at, jobs.last_checked_at
                ),
                status = excluded.status,
                fit_score = excluded.fit_score,
                recommended_cv = excluded.recommended_cv,
                match_explanation = excluded.match_explanation,
                missing_requirements = excluded.missing_requirements,
                rejection_reason = excluded.rejection_reason,
                ai_decision = excluded.ai_decision,
                evaluation_source = excluded.evaluation_source,
                evaluation_confidence = excluded.evaluation_confidence,
                evaluation_requirements = excluded.evaluation_requirements,
                updated_at = excluded.updated_at
        """, values)

        row = connection.execute("""
            SELECT id
            FROM jobs
            WHERE normalized_url = ?
               OR (
                    source = ?
                    AND source_job_id = ?
                    AND source_job_id IS NOT NULL
               )
            LIMIT 1
        """, (
            job["normalized_url"],
            job["source"],
            job.get("source_job_id"),
        )).fetchone()

        if row is None:
            raise RuntimeError("Saved vacancy could not be retrieved.")

        return int(row["id"])


def count_jobs() -> int:
    """Return the number of stored vacancies."""

    with db_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM jobs"
        ).fetchone()

    return int(row["total"])


def save_cv_profile(profile: dict[str, Any]) -> int:
    """Save a CV profile or update the existing record."""

    source_file = profile["source_file"]
    skills_json = json.dumps(
        profile.get("skills", []),
        ensure_ascii=False,
    )
    languages_json = json.dumps(
        profile.get("languages", []),
        ensure_ascii=False,
    )
    job_titles_json = json.dumps(
        profile.get("job_titles", []),
        ensure_ascii=False,
    )
    sections_json = json.dumps(
        profile.get("sections", {}),
        ensure_ascii=False,
    )
    raw_text = profile["raw_text"]

    with db_connection() as connection:
        connection.execute(
            """

            INSERT INTO cv_profiles (
                source_file,
                skills_json,
                languages_json,
                job_titles_json,
                sections_json,
                raw_text,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_file) DO UPDATE SET
                skills_json = excluded.skills_json,
                languages_json = excluded.languages_json,
                job_titles_json = excluded.job_titles_json,
                sections_json = excluded.sections_json,
                ai_profile_json = CASE
                    WHEN cv_profiles.raw_text != excluded.raw_text THEN NULL
                    ELSE cv_profiles.ai_profile_json
                END,
                ai_status = CASE
                    WHEN cv_profiles.raw_text != excluded.raw_text
                        THEN 'not_processed'
                    ELSE cv_profiles.ai_status
                END,
                raw_text = excluded.raw_text,
                updated_at = excluded.updated_at
            """,
            (
                source_file,
                skills_json,
                languages_json,
                job_titles_json,
                sections_json,
                raw_text,
                current_timestamp(),
            ),
        )

        row = connection.execute(
            """
            SELECT id
            FROM cv_profiles
            WHERE source_file = ?
            """,
            (source_file,),
        ).fetchone()

        return row["id"]

def save_ai_profile(source_file: str, ai_profile: dict[str, Any]) -> None:
    """Save the AI-extracted profile for an existing CV."""
    ai_profile_json = json.dumps(
        ai_profile,
        ensure_ascii=False,
    )

    with db_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE cv_profiles
            SET ai_profile_json = ?, ai_status = 'success', updated_at = ?
            WHERE source_file = ?
            """,
            (
                ai_profile_json,
                current_timestamp(),
                source_file,
            ),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"CV profile not found in database: {source_file}"
            )


def update_ai_status(source_file: str, status: str) -> None:
    """Save the result of the latest AI processing attempt."""
    allowed_statuses = {
        "not_processed",
        "success",
        "timeout",
        "error",
    }

    if status not in allowed_statuses:
        raise ValueError(f"Unsupported AI status: {status}")

    with db_connection() as connection:
        cursor = connection.execute(
            """
            UPDATE cv_profiles
            SET ai_status = ?, updated_at = ?
            WHERE source_file = ?
            """,
            (status, current_timestamp(), source_file),
        )

        if cursor.rowcount == 0:
            raise ValueError(
                f"CV profile not found in database: {source_file}"
            )


def get_cv_profiles() -> list[dict[str, Any]]:
    """Read all stored CV profiles and decode their JSON fields."""

    with db_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM cv_profiles
            ORDER BY source_file
            """
        ).fetchall()

    profiles = []

    for row in rows:
        profiles.append({
            "id": row["id"],
            "source_file": row["source_file"],
            "skills": json.loads(row["skills_json"]),
            "languages": json.loads(row["languages_json"]),
            "raw_text": row["raw_text"],
            "updated_at": row["updated_at"],
            "job_titles": json.loads(row["job_titles_json"]),
            "sections": json.loads(row["sections_json"]),
            "ai_profile": (
                json.loads(row["ai_profile_json"])
                if row["ai_profile_json"] is not None
                else None
            ),
            "ai_status": row["ai_status"],
        })

    return profiles


def count_cv_profiles() -> int:
    """Return the number of stored CV profiles."""

    with db_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS total FROM cv_profiles"
        ).fetchone()

    return row["total"]


def clear_cv_profiles() -> None:
    """Delete cached CV text and extracted profiles, preserving job history."""
    with db_connection() as connection:
        connection.execute("DELETE FROM cv_profiles")


def get_cached_job_evaluation(
    normalized_url: str, fingerprint: str
) -> dict[str, Any] | None:
    """Load a job evaluation only when its job/profile fingerprint still matches."""
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT evaluation_json
            FROM job_fit_evaluations
            WHERE normalized_url = ? AND fingerprint = ?
            """,
            (normalized_url, fingerprint),
        ).fetchone()
    if row is None:
        return None
    try:
        value = json.loads(row["evaluation_json"])
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def save_cached_job_evaluation(
    normalized_url: str, fingerprint: str, evaluation: dict[str, Any]
) -> None:
    """Persist a successful local AI evaluation for later search runs."""
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO job_fit_evaluations (
                normalized_url, fingerprint, evaluation_json, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(normalized_url) DO UPDATE SET
                fingerprint = excluded.fingerprint,
                evaluation_json = excluded.evaluation_json,
                updated_at = excluded.updated_at
            """,
            (
                normalized_url,
                fingerprint,
                json.dumps(evaluation, ensure_ascii=False),
                current_timestamp(),
            ),
        )

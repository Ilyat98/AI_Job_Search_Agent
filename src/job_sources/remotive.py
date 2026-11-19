"""Fetch and store job listings from Remotive's public API."""

from __future__ import annotations

import argparse
import json
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from src import database
from src.job_sources.common import normalize_url

API_URL = "https://remotive.com/api/remote-jobs"
USER_AGENT = "LocalJobSearchAgent/0.1 (personal job search)"


def fetch_jobs(
    *, search: str | None = None, limit: int | None = None
) -> list[dict[str, Any]]:
    """Retrieve active listings from Remotive without third-party libraries."""
    params: dict[str, str] = {}
    if search:
        params["search"] = search
    if limit is not None:
        if limit < 1:
            raise ValueError("limit must be a positive integer")
        params["limit"] = str(limit)

    url = f"{API_URL}?{urlencode(params)}" if params else API_URL
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Could not retrieve Remotive jobs: {error}") from error

    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        raise ValueError("Remotive response does not contain a jobs list")
    # Enforce the requested cap locally too; the endpoint may return more.
    if limit is not None:
        jobs = jobs[:limit]
    return jobs


def normalize_job(item: dict[str, Any]) -> dict[str, Any]:
    """Map a Remotive listing into the existing SQLite job structure."""
    source_id = item.get("id")
    url = item.get("url")
    title = item.get("title")
    if (
        source_id is None
        or not isinstance(url, str)
        or not url
        or not isinstance(title, str)
        or not title
    ):
        raise ValueError("Remotive listing is missing its id, url, or title")

    return {
        "source": "remotive",
        "source_job_id": str(source_id),
        "url": url,
        "normalized_url": normalize_url(url),
        "company": item.get("company_name"),
        "title": title,
        "description": item.get("description"),
        "location": item.get("candidate_required_location"),
        "job_type": item.get("job_type"),
        "salary": item.get("salary"),
        "published_at": item.get("publication_date"),
        "status": "active",
    }


def sync_jobs(*, search: str | None = None, limit: int | None = None) -> int:
    """Fetch listings and upsert them through the existing DB deduplication."""
    listings = fetch_jobs(search=search, limit=limit)
    for listing in listings:
        database.save_job(normalize_job(listing))
    return len(listings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import jobs from Remotive")
    parser.add_argument("--search", help="Optional keyword search")
    parser.add_argument(
        "--limit", type=int, default=5, help="Maximum results (default: 5)"
    )
    args = parser.parse_args()

    database.init_db()
    count = sync_jobs(search=args.search, limit=args.limit)
    print(f"Remotive listings fetched and saved: {count}")
    print("Source attribution: Remotive")


if __name__ == "__main__":
    main()

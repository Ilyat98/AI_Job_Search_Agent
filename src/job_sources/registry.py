"""Collect listings from the source adapters enabled in settings."""

from __future__ import annotations

from typing import Any

from src.job_sources import dou_rss, justjoin_sitemap, remotive


def fetch_enabled_sources(
    settings: dict[str, Any],
    *, search_terms: list[str] | None = None,
    since: Any = None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    source_settings = settings.get("job_sources", {})
    enabled = source_settings.get("enabled", ["dou", "remotive"])
    terms = list(dict.fromkeys(search_terms or source_settings.get("search_terms", ["QA"])))
    feed_limit = source_settings.get("max_results_per_feed", 25)
    source_limit = source_settings.get("max_results_per_source", 50)

    jobs_by_url: dict[str, dict[str, Any]] = {}
    urls_by_source: dict[str, set[str]] = {}
    errors: list[str] = []
    succeeded: list[str] = []

    def add_listing(job: dict[str, Any]) -> bool:
        source = str(job.get("source") or "unknown")
        source_urls = urls_by_source.setdefault(source, set())
        url = str(job.get("normalized_url") or "")
        if url not in source_urls:
            if len(source_urls) >= source_limit:
                return False
            source_urls.add(url)
        jobs_by_url.setdefault(url, job)
        return True

    if "dou" in enabled:
        source_success = False
        for term in terms:
            if len(urls_by_source.get("dou", set())) >= source_limit:
                break
            try:
                for job in dou_rss.fetch_jobs(search=term, limit=feed_limit):
                    if not add_listing(job):
                        break
                source_success = True
            except (OSError, RuntimeError, ValueError) as error:
                errors.append(f"DOU ({term}): {error}")
        if source_success:
            succeeded.append("dou")

    if "remotive" in enabled:
        source_success = False
        for term in terms:
            if len(urls_by_source.get("remotive", set())) >= source_limit:
                break
            try:
                for job in remotive.fetch_jobs(search=term, limit=source_limit):
                    normalized = remotive.normalize_job(job)
                    if not add_listing(normalized):
                        break
                source_success = True
            except (OSError, RuntimeError, ValueError) as error:
                errors.append(f"Remotive ({term}): {error}")
        if source_success:
            succeeded.append("remotive")

    if "justjoin" in enabled:
        try:
            for job in justjoin_sitemap.fetch_jobs(
                search_terms=terms,
                limit=source_settings.get("justjoin_max_detail_pages", 25),
                since=since,
            ):
                add_listing(job)
            succeeded.append("justjoin")
        except (OSError, RuntimeError, ValueError) as error:
            errors.append(f"JustJoin.it: {error}")

    if not succeeded:
        detail = "; ".join(errors) or "no available source is enabled"
        raise RuntimeError(f"Could not retrieve vacancies from any source: {detail}")

    return list(jobs_by_url.values()), errors, succeeded

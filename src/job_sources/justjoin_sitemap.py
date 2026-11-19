"""Fetch matching JustJoin.it offers from its public, robots-listed sitemap."""

from __future__ import annotations

import html
import json
import logging
import re
import time
import unicodedata
from datetime import datetime, timezone
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from src.job_sources.common import normalize_url

SITEMAP_URL = "https://justjoin.it/sitemaps/active-jobs.xml"
USER_AGENT = "LocalJobSearchAgent/0.1 (personal job search; sitemap reader)"
REQUEST_TIMEOUT = 20
REQUEST_DELAY_SECONDS = 0.35
logger = logging.getLogger(__name__)


def _ascii(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _as_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _matches_search(slug: str, terms: list[str]) -> bool:
    normalized_slug = re.sub(r"[^\w+#]+", " ", _ascii(slug))
    for term in terms:
        words = re.sub(r"[^\w+#]+", " ", _ascii(term)).strip()
        if words and re.search(rf"(?<!\w){re.escape(words)}(?!\w)", normalized_slug):
            return True
    return False


def _find_job_posting(value: Any) -> dict[str, Any] | None:
    if isinstance(value, list):
        for item in value:
            result = _find_job_posting(item)
            if result:
                return result
    elif isinstance(value, dict):
        types = value.get("@type", [])
        if isinstance(types, str):
            types = [types]
        if "JobPosting" in types:
            return value
        return _find_job_posting(value.get("@graph", []))
    return None


def _job_posting_from_html(page: bytes) -> dict[str, Any]:
    page_text = page.decode("utf-8", errors="replace")
    scripts = re.findall(
        r"<script\b[^>]*type\s*=\s*['\"]application/ld\+json['\"][^>]*>(.*?)</script\s*>",
        page_text,
        flags=re.I | re.S,
    )
    for raw in scripts:
        try:
            payload = json.loads(html.unescape(raw.strip()))
        except json.JSONDecodeError:
            continue
        posting = _find_job_posting(payload)
        if posting:
            return posting
    raise ValueError("JustJoin.it page has no schema.org JobPosting data")


def _locations(value: Any) -> list[str]:
    if isinstance(value, dict):
        entries = [value]
    elif isinstance(value, list):
        entries = value
    else:
        entries = []
    result: list[str] = []
    country_names = {
        "PL": "Poland", "UA": "Ukraine", "US": "United States",
        "FR": "France", "PT": "Portugal", "IN": "India", "ES": "Spain",
        "GB": "United Kingdom", "UK": "United Kingdom", "IE": "Ireland",
        "NL": "Netherlands", "BE": "Belgium", "IT": "Italy",
        "SE": "Sweden", "NO": "Norway", "DE": "Germany",
        "CZ": "Czechia", "SK": "Slovakia", "RO": "Romania",
        "BG": "Bulgaria", "HU": "Hungary", "AT": "Austria",
        "CH": "Switzerland", "DK": "Denmark", "FI": "Finland",
        "EE": "Estonia", "LT": "Lithuania", "LV": "Latvia",
        "HR": "Croatia", "GR": "Greece", "CY": "Cyprus",
        "MT": "Malta",
    }
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        address = entry.get("address") or entry
        if not isinstance(address, dict):
            continue
        parts = []
        locality = address.get("addressLocality")
        region = address.get("addressRegion")
        country = address.get("addressCountry")
        if locality:
            parts.append(str(locality))
        if region and str(region).casefold() != str(locality or "").casefold():
            parts.append(str(region))
        if country:
            country = country_names.get(str(country).upper(), str(country))
            if str(country).casefold() not in " ".join(parts).casefold():
                parts.append(str(country))
        label = ", ".join(dict.fromkeys(parts))
        if label and label not in result:
            result.append(label)
    return result


def _salary(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    currency = str(value.get("currency") or "").strip()
    amount = value.get("value")
    if isinstance(amount, dict):
        minimum = amount.get("minValue")
        maximum = amount.get("maxValue")
        unit = str(amount.get("unitText") or "").casefold()
    else:
        minimum = maximum = amount
        unit = ""
    def display(number: Any) -> str | None:
        if not isinstance(number, (int, float)):
            return None
        return f"{number:,.0f}".replace(",", " ")
    low, high = display(minimum), display(maximum)
    if low and high and low != high:
        result = f"{low}–{high}"
    else:
        result = low or high
    if not result:
        return None
    frequency = {"month": "/ month", "hour": "/ hour", "year": "/ year"}.get(unit)
    return " ".join(part for part in (result, currency, frequency) if part)


def _employment_type(value: Any) -> str | None:
    labels = {
        "FULL_TIME": "Full-time", "PART_TIME": "Part-time",
        "CONTRACTOR": "Contractor", "TEMPORARY": "Temporary",
        "INTERN": "Internship", "VOLUNTEER": "Volunteer",
        "OTHER": "Other",
    }
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    parsed = [labels.get(str(item).upper(), str(item).replace("_", " ").title())
              for item in values if item]
    return ", ".join(dict.fromkeys(parsed)) or None


def normalize_posting(url: str, posting: dict[str, Any]) -> dict[str, Any]:
    title = posting.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("JustJoin.it JobPosting is missing a title")
    slug = urlparse(url).path.rstrip("/").split("/")[-1]
    employment_type = _employment_type(posting.get("employmentType"))
    description = html.unescape(str(posting.get("description") or ""))
    mode = str(posting.get("jobLocationType") or "").casefold()
    if "telecommute" in mode or "remote" in mode:
        work_mode = "remote"
    elif "hybrid" in description.casefold() or "hybryd" in description.casefold():
        work_mode = "hybrid"
    elif "on_site" in mode or "on-site" in description.casefold():
        work_mode = "on-site"
    else:
        work_mode = None
    locations = _locations(posting.get("jobLocation"))
    if not locations:
        locations = _locations(posting.get("applicantLocationRequirements"))
    valid_through = _as_datetime(posting.get("validThrough"))
    status = "closed" if valid_through and valid_through < datetime.now(timezone.utc) else "active"
    return {
        "source": "justjoin",
        "source_job_id": slug,
        "url": url,
        "normalized_url": normalize_url(url),
        "company": (posting.get("hiringOrganization") or {}).get("name")
        if isinstance(posting.get("hiringOrganization"), dict) else None,
        "title": html.unescape(title.strip()),
        "description": description,
        "location": "; ".join(locations) or None,
        "job_type": employment_type,
        "work_mode": work_mode,
        "salary": _salary(posting.get("baseSalary")),
        "published_at": posting.get("datePosted"),
        "status": status,
    }


def fetch_jobs(
    *, search_terms: list[str], limit: int = 25,
    since: datetime | None = None,
) -> list[dict[str, Any]]:
    """Read relevant, recent offers from the site's public active-offer sitemap.

    The source's `/api/` paths are intentionally not used. Only sitemap URLs
    under `/job-offer/` are read, with a small delay between page requests.
    """
    if limit < 1:
        raise ValueError("limit must be a positive integer")
    request = Request(SITEMAP_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            sitemap = ElementTree.fromstring(response.read())
    except (URLError, TimeoutError, ElementTree.ParseError) as error:
        raise RuntimeError(f"Could not retrieve JustJoin.it sitemap: {error}") from error

    namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    sitemap_files = [node.findtext(f"{namespace}loc") for node in sitemap.findall(f"{namespace}sitemap")]
    entries = []
    if sitemap_files:
        for sitemap_url in sitemap_files:
            if not sitemap_url:
                continue
            if urlparse(sitemap_url).hostname not in {"justjoin.it", "www.justjoin.it"}:
                logger.warning("Ignoring non-JustJoin sitemap URL: %s", sitemap_url)
                continue
            subrequest = Request(sitemap_url, headers={"User-Agent": USER_AGENT})
            try:
                with urlopen(subrequest, timeout=REQUEST_TIMEOUT) as response:
                    root = ElementTree.fromstring(response.read())
            except (URLError, TimeoutError, ElementTree.ParseError) as error:
                raise RuntimeError(f"Could not retrieve JustJoin.it offer sitemap: {error}") from error
            entries.extend(root.findall(f"{namespace}url"))
    else:
        entries = sitemap.findall(f"{namespace}url")

    candidates = []
    for entry in entries:
        url = entry.findtext(f"{namespace}loc")
        if not url:
            continue
        parsed_url = urlparse(url)
        if (
            parsed_url.hostname not in {"justjoin.it", "www.justjoin.it"}
            or not parsed_url.path.startswith("/job-offer/")
        ):
            continue
        lastmod = _as_datetime(entry.findtext(f"{namespace}lastmod"))
        if since and lastmod and lastmod < since:
            continue
        slug = urlparse(url).path.rstrip("/").split("/")[-1]
        if _matches_search(slug, search_terms):
            candidates.append((lastmod or datetime.min.replace(tzinfo=timezone.utc), url))
    candidates.sort(reverse=True)

    jobs = []
    errors = 0
    for index, (_, url) in enumerate(candidates[:limit]):
        if index:
            time.sleep(REQUEST_DELAY_SECONDS)
        try:
            page_request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(page_request, timeout=REQUEST_TIMEOUT) as response:
                posting = _job_posting_from_html(response.read())
            jobs.append(normalize_posting(url, posting))
        except (URLError, TimeoutError, ValueError, json.JSONDecodeError) as error:
            errors += 1
            logger.warning("Skipping JustJoin.it offer %s: %s", url, error)
    if candidates and not jobs and errors:
        raise RuntimeError(f"Could not parse any JustJoin.it offer ({errors} failures)")
    return jobs

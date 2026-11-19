"""Read job listings from DOU's published RSS vacancy feeds."""

from __future__ import annotations

import re
from datetime import timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from src.job_sources.common import normalize_url

FEED_URL = "https://jobs.dou.ua/vacancies/feeds/"
USER_AGENT = "LocalJobSearchAgent/0.1 (personal job search; DOU RSS)"


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        cleaned = " ".join(data.split())
        if cleaned:
            self.parts.append(cleaned)


def html_to_text(value: str) -> str:
    parser = _TextExtractor()
    parser.feed(unescape(value or ""))
    return " ".join(parser.parts)


def _parse_title(raw_title: str) -> tuple[str, str | None, str | None]:
    """Separate DOU's title, employer and location suffix when recognizable."""
    raw_title = unescape(raw_title)
    match = re.match(
        r"^(.*?)\s+(?:в|у|w|at)\s+([^,]+)(?:,\s*(.*))?$",
        raw_title,
        re.I,
    )
    if not match:
        return raw_title.strip(), None, None
    title = match.group(1).strip()
    company = match.group(2).strip()
    location = (match.group(3) or "").strip() or None
    return title, company, location


def _parse_published_at(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def _salary_from_text(text: str) -> str | None:
    patterns = (
        r"(?:\$|USD\s*)\s?\d[\d\s,.]*(?:\s*(?:-|–|—)\s*(?:\$|USD\s*)?\d[\d\s,.]*)?",
        r"\d[\d\s,.]*\s?(?:PLN|zł|EUR|€)(?:\s*(?:/|за|per)\s?(?:годину|місяць|hour|month|h|m))?",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return " ".join(match.group(0).split()).rstrip(" .,;")
    return None


def fetch_jobs(*, search: str, limit: int = 25) -> list[dict[str, Any]]:
    """Fetch a DOU RSS search feed; RSS is the site's published feed interface."""
    if not search.strip():
        raise ValueError("search must not be empty")
    if limit < 1:
        raise ValueError("limit must be a positive integer")

    url = f"{FEED_URL}?{urlencode({'search': search, 'descr': '1'})}"
    request = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(request, timeout=20) as response:
            root = ElementTree.fromstring(response.read())
    except (URLError, TimeoutError, ElementTree.ParseError) as error:
        raise RuntimeError(f"Could not retrieve DOU RSS feed: {error}") from error

    listings = []
    for item in root.findall(".//item")[:limit]:
        raw_title = item.findtext("title", default="").strip()
        url_value = item.findtext("link", default="").strip()
        description_html = item.findtext("description", default="")
        if not raw_title or not url_value:
            continue

        title, company, location = _parse_title(raw_title)
        description = html_to_text(description_html)
        salary = _salary_from_text(f"{location or ''} {description}")
        if location and salary:
            location = re.sub(re.escape(salary), " ", location, flags=re.I)
            location = re.sub(r"\s*,\s*", ", ", location)
            location = re.sub(r"(?:^\s*,|,\s*$)", "", location).strip()
            location = location or None
        identifier = re.search(r"/vacancies/(\d+)/", url_value)
        if identifier is None:
            identifier = re.search(r"/vacancies/(\d+)/?$", url_value)
        job_id = identifier.group(1) if identifier else normalize_url(url_value)
        published_at = _parse_published_at(item.findtext("pubDate"))

        listings.append({
            "source": "dou",
            "source_job_id": str(job_id),
            "url": url_value,
            "normalized_url": normalize_url(url_value),
            "company": company,
            "title": title,
            "description": description,
            "location": location,
            "job_type": None,
            "salary": salary,
            "published_at": published_at,
            "status": "active",
        })
    return listings

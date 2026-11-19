"""Shared helpers for job source adapters."""

from urllib.parse import urlsplit, urlunsplit


def normalize_url(url: str) -> str:
    """Remove tracking query and fragment while preserving the job path."""
    parts = urlsplit(url)
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", "")
    )
